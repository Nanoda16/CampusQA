"""IngestionService 异步入库单元测试

测试异步文档处理管线（TDD）：
  1. enqueue → 状态变为 PROCESSING
  2. _process_document 成功 → status=READY, chunk_count>0
  3. _process_document 失败 → status=FAILED, error_message 非空
  4. reset_processing_docs → PROCESSING 重置为 UPLOADED
"""

import threading
import time
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.enums import DocumentStatus
from app.services.document_service import IngestionService
from tests.conftest import TestingSessionLocal


# ── Fixtures ──


@pytest.fixture
def session_factory():
    """后台线程用的会话工厂（指向同一个测试数据库）"""
    return TestingSessionLocal


@pytest.fixture
def svc(session_factory):
    """每个测试独立的 IngestionService 实例（含独立线程池）"""
    from concurrent.futures import ThreadPoolExecutor
    svc = IngestionService(session_factory=session_factory)
    svc._executor = ThreadPoolExecutor(max_workers=1)
    yield svc
    svc._executor.shutdown(wait=True, cancel_futures=True)


# ── enqueue 测试 ──


class TestEnqueue:
    """enqueue 方法——同步修改状态，异步执行处理"""

    def test_enqueue_changes_status(self, db_session: Session):
        """enqueue 后文档状态变为 PROCESSING（同步部分）"""
        doc = Document(title="入队测试文档", content="测试内容")
        db_session.add(doc)
        db_session.commit()
        doc_id = doc.id

        # 用 mock 避免后台线程真的调用 ai_service
        svc = IngestionService(session_factory=TestingSessionLocal)
        with patch.object(svc, "_call_process_api") as mock_process:
            svc.enqueue(doc_id, db_session)

            # 状态在 submit() 之前已同步修改 + commit
            updated = db_session.get(Document, doc_id)
            assert updated.status == DocumentStatus.PROCESSING
            assert updated.error_message is None

            # 等待线程池执行完毕
            svc._executor.shutdown(wait=True, cancel_futures=False)

        # 确认 mock 被调用了（说明任务确实提交到了线程池）
        mock_process.assert_called_once()


# ── _process_document 测试（同步调用，直接验证逻辑）──


class TestProcessDocument:
    """后台工作线程核心逻辑——直接调用 _process_document"""

    def test_completion_sets_ready(self, db_session: Session, svc):
        """处理完成后 status=READY, chunk_count>0"""
        doc = Document(title="成功处理文档", content="正常内容")
        db_session.add(doc)
        db_session.commit()
        doc_id = doc.id

        with patch.object(svc, "_call_process_api", return_value={"chunks_count": 5}):
            svc._process_document(doc_id)

        # 用新 session 检查（后台线程使用自己的 session）
        check_db = TestingSessionLocal()
        try:
            updated = check_db.get(Document, doc_id)
            assert updated.status == DocumentStatus.READY
            assert updated.chunk_count == 5
            assert updated.processed_at is None  # processed_at 由 ai_service 设置，这里不修改
        finally:
            check_db.close()

    def test_failure_sets_failed(self, db_session: Session, svc):
        """处理异常时 status=FAILED, error_message 非空"""
        doc = Document(title="失败处理文档", content="异常内容")
        db_session.add(doc)
        db_session.commit()
        doc_id = doc.id

        with patch.object(
            svc, "_call_process_api", side_effect=RuntimeError("模拟处理失败")
        ):
            svc._process_document(doc_id)

        check_db = TestingSessionLocal()
        try:
            updated = check_db.get(Document, doc_id)
            assert updated.status == DocumentStatus.FAILED
            assert updated.error_message is not None
            assert "模拟处理失败" in updated.error_message
        finally:
            check_db.close()


# ── reset_processing_docs 测试 ──


class TestResetProcessing:
    """启动恢复：重置 PROCESSING 状态"""

    def test_startup_resets_processing(self, db_session: Session):
        """PROCESSING 状态的文档被重置为 UPLOADED，READY 不受影响"""
        doc1 = Document(title="中断文档1", status=DocumentStatus.PROCESSING)
        doc2 = Document(
            title="中断文档2",
            status=DocumentStatus.PROCESSING,
            error_message="残留错误",
        )
        doc3 = Document(title="已完成文档", status=DocumentStatus.READY, chunk_count=3)
        db_session.add_all([doc1, doc2, doc3])
        db_session.commit()

        IngestionService.reset_processing_docs(db_session)

        assert db_session.get(Document, doc1.id).status == DocumentStatus.UPLOADED
        assert db_session.get(Document, doc2.id).status == DocumentStatus.UPLOADED
        assert db_session.get(Document, doc2.id).error_message is None
        assert db_session.get(Document, doc3.id).status == DocumentStatus.READY
