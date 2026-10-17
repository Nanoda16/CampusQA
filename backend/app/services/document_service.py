"""文档业务服务"""

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.enums import DocumentStatus
from app.schemas.document import DocumentCreate, DocumentUpdate

# ai_service 基础 URL（与 RAGService 保持一致）
AI_SERVICE_URL = "http://localhost:8003"

# 上传暂存目录：解析并写入知识目录后即可清理，它不参与索引
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


class DocumentService:
    """文档服务"""

    @staticmethod
    def create(db: Session, data: DocumentCreate, user_id: int) -> Document:
        """创建文档"""
        document = Document(
            title=data.title,
            content=data.content,
            category=data.category,
            department=data.department,
            file_type=data.file_type,
            file_path=data.file_path,
            source_url=data.source_url,
            tags=data.tags,
            status=data.status,
            created_by=user_id,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document

    @staticmethod
    def get_by_id(db: Session, document_id: int) -> Document | None:
        """根据ID获取文档"""
        return db.query(Document).filter(Document.id == document_id).first()

    @staticmethod
    def update(db: Session, document_id: int, data: DocumentUpdate) -> Document | None:
        """更新文档"""
        document = DocumentService.get_by_id(db, document_id)
        if not document:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(document, key, value)

        db.commit()
        db.refresh(document)
        return document

    @staticmethod
    def soft_delete(db: Session, document_id: int) -> bool:
        """删除文档（状态机无"已归档"状态，改为硬删除）"""
        document = DocumentService.get_by_id(db, document_id)
        if not document:
            return False
        db.delete(document)
        db.commit()
        return True

    @staticmethod
    def get_list(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        department: str | None = None,
        status: int | None = None,
        keyword: str | None = None,
    ) -> tuple[list[Document], int]:
        """获取文档列表（分页 + 筛选）"""
        query = db.query(Document)

        if category:
            query = query.filter(Document.category == category)
        if department:
            query = query.filter(Document.department == department)
        if status is not None:
            query = query.filter(Document.status == status)
        # 不再默认排除任何状态 — Day4 需要看到 FAILED 的记录
        if keyword:
            like_pattern = f"%{keyword}%"
            query = query.filter(
                Document.title.ilike(like_pattern)
                | Document.content.ilike(like_pattern)
            )

        total = query.count()
        documents = (
            query.order_by(Document.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return documents, total

    @staticmethod
    def get_all_documents(db: Session) -> list[Document]:
        """获取所有文档（重建索引用，不过滤状态）"""
        return (
            db.query(Document)
            .order_by(Document.id)
            .all()
        )

    @staticmethod
    def get_categories(db: Session) -> list[str]:
        """获取所有文档分类"""
        results = (
            db.query(Document.category)
            .filter(Document.category.isnot(None), Document.status == DocumentStatus.READY)
            .distinct()
            .all()
        )
        return [r[0] for r in results if r[0]]

    @staticmethod
    def sync_from_manifest(db: Session, manifest: list[dict]) -> dict:
        """把 ``kb_document`` 对齐到知识目录扫描出来的清单。

        知识目录是唯一真相：重建索引时 ai_service 返回它实际索引了哪些文件，
        这里据此增删改数据库记录，避免出现“数据库里有但索引里没有”或者反过来的
        情况（这正是原先两个重建入口互相清空内容的根因）。
        """
        existing = {
            doc.vector_doc_id: doc
            for doc in db.query(Document)
            .filter(Document.vector_doc_id.isnot(None))
            .all()
        }

        seen: set[str] = set()
        created = 0
        updated = 0

        for item in manifest:
            vector_doc_id = item.get("doc_id")
            if not vector_doc_id:
                continue
            seen.add(vector_doc_id)

            file_path = item.get("file_path") or ""
            file_type = os.path.splitext(file_path)[1].lstrip(".").lower() or None

            row = existing.get(vector_doc_id)
            if row is None:
                row = Document(
                    title=item.get("title") or vector_doc_id,
                    category=item.get("category") or None,
                    file_type=file_type,
                    file_path=file_path or None,
                    vector_doc_id=vector_doc_id,
                    source_url=item.get("source_url") or None,
                    chunk_count=int(item.get("chunk_count") or 0),
                    status=DocumentStatus.READY,
                )
                db.add(row)
                created += 1
                continue

            row.title = item.get("title") or row.title
            row.category = item.get("category") or row.category
            row.file_path = file_path or row.file_path
            row.source_url = item.get("source_url") or row.source_url
            row.chunk_count = int(item.get("chunk_count") or row.chunk_count or 0)
            row.status = DocumentStatus.READY
            row.error_message = None
            updated += 1

        deleted = 0
        for vector_doc_id, row in existing.items():
            if vector_doc_id not in seen:
                db.delete(row)
                deleted += 1

        db.commit()
        return {"created": created, "updated": updated, "deleted": deleted}


class IngestionService:
    """异步文档入库服务

    使用单工作线程的 ThreadPoolExecutor 处理文档入库：
    - enqueue: 将文档加入处理队列，状态 → PROCESSING
    - 后台线程：读取文档内容 → 调 ai_service /process → 状态 → READY
    - 异常时状态 → FAILED，记录 error_message
    - reset_processing_docs: 启动时恢复中断的文档
    """

    _executor = ThreadPoolExecutor(max_workers=1)

    @classmethod
    def _get_executor(cls) -> ThreadPoolExecutor:
        """获取或重建线程池，防止在 shutdown 后无法提交新任务"""
        if cls._executor is None or getattr(cls._executor, "_shutdown", False):
            cls._executor = ThreadPoolExecutor(max_workers=1)
        return cls._executor

    def __init__(self, session_factory=None):
        """初始化入库服务

        Parameters
        ----------
        session_factory : callable, optional
            创建数据库会话的工厂函数（测试时注入 TestingSessionLocal）。
            默认为 ``app.database.SessionLocal``。
        """
        from app.database import SessionLocal

        self._session_factory = session_factory or SessionLocal

    def enqueue(self, document_id: int, db: Session) -> None:
        """将文档加入处理队列

        同步修改状态为 PROCESSING 并提交，然后异步执行入库。
        """
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.status = DocumentStatus.PROCESSING
        doc.error_message = None
        db.commit()
        # 后台异步执行
        self._get_executor().submit(self._process_document, document_id)

    # ── 后台工作线程 ──────────────────────────────────────

    def _process_document(self, document_id: int) -> None:
        """后台工作：处理单篇文档

        1. 用独立 session 读取文档
        2. 交给 ai_service 解析 → 写入知识目录 → 建索引
        3. 回写 chunk_count / vector_doc_id / 知识目录里的文件路径
        """
        db = self._session_factory()
        try:
            doc = db.get(Document, document_id)
            if doc is None:
                return

            staging_path = doc.file_path
            result = self._call_process_api(doc)

            doc.status = DocumentStatus.READY
            doc.chunk_count = result.get("chunks_count", 0)
            doc.vector_doc_id = result.get("doc_id") or doc.vector_doc_id

            persisted_path = result.get("persisted_path") or result.get("file_path")
            if persisted_path:
                doc.file_path = persisted_path
            if result.get("title") and not doc.title:
                doc.title = result["title"]
            if result.get("category") and not doc.category:
                doc.category = result["category"]
            if result.get("source_url") and not doc.source_url:
                doc.source_url = result["source_url"]
            if not doc.file_type and persisted_path:
                doc.file_type = (
                    os.path.splitext(persisted_path)[1].lstrip(".").lower() or None
                )
            doc.error_message = None
            db.commit()

            # 知识目录里已经有规范化的副本了，暂存文件不再需要，
            # 否则 uploads/ 会随着每次上传无限增长。
            self._cleanup_staging(staging_path, persisted_path)
        except Exception as exc:
            try:
                doc = db.get(Document, document_id)
                if doc is not None:
                    doc.status = DocumentStatus.FAILED
                    doc.error_message = str(exc)[:500]
                    db.commit()
            except Exception:
                pass
        finally:
            db.close()

    @staticmethod
    def _cleanup_staging(staging_path: str | None, persisted_path: str | None) -> None:
        """删除已成功转换的上传暂存文件。"""
        if not staging_path or not persisted_path:
            return
        try:
            if os.path.abspath(staging_path) == os.path.abspath(persisted_path):
                return
            if not str(Path(staging_path).resolve()).startswith(str(UPLOAD_DIR.resolve())):
                return
            os.unlink(staging_path)
        except OSError:
            pass

    def _call_process_api(self, doc: Document) -> dict:
        """向 ai_service 提交文档处理

        首次入库（还没有 vector_doc_id）用 ``persist=True``：ai_service 会把解析出的
        纯文本写进知识目录再建索引，这样以后一次全量重建（扫目录）仍然找得到它。

        重新处理用 ``persist=False``：文件已经在知识目录里，原地重建索引即可，
        否则每点一次“重新处理”都会在目录里多出一个副本。
        """
        already_in_knowledge_dir = bool(doc.vector_doc_id) and bool(doc.file_path) and os.path.isfile(doc.file_path)

        # ── 优先使用已上传的真实文件 ──────────────────────────
        if doc.file_path and os.path.isfile(doc.file_path):
            return self._post_process(
                file_path=doc.file_path,
                persist=not already_in_knowledge_dir,
                category=doc.category,
            )

        # ── 回退：从 title + content 写临时 .md ───────────────
        fd, path = tempfile.mkstemp(suffix=".md", prefix=f"doc_{doc.id}_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"# {doc.title}\n\n{doc.content or ''}")
            return self._post_process(
                file_path=path,
                persist=True,
                category=doc.category,
            )
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    @staticmethod
    def _post_process(
        file_path: str,
        persist: bool,
        category: str | None,
    ) -> dict:
        """调用 ai_service /process 并返回结果。"""
        resp = httpx.post(
            f"{AI_SERVICE_URL}/process",
            json={
                "file_path": file_path,
                "persist": persist,
                "category": category,
            },
            timeout=300.0,
        )
        resp.raise_for_status()
        return resp.json()

    # ── 启动恢复 ──────────────────────────────────────────

    @staticmethod
    def reset_processing_docs(db: Session) -> None:
        """启动时恢复：将 PROCESSING 状态的文档重置为 UPLOADED

        服务重启时调用，清理因异常中断而残留在 PROCESSING 状态的文档。
        """
        docs = (
            db.query(Document)
            .filter(Document.status == DocumentStatus.PROCESSING)
            .all()
        )
        for doc in docs:
            doc.status = DocumentStatus.UPLOADED
            doc.error_message = None
        db.commit()
