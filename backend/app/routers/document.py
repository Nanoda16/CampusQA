"""文档管理 API 路由"""

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentUpdate,
)
from app.services.document_service import DocumentService, IngestionService
from app.services.rag_service import RAGService
from app.services.user_service import UserService
from app.routers.user import _get_current_user

router = APIRouter(prefix="/api/document", tags=["文档管理"])


def _success(data=None, message="success"):
    return {
        "code": 200,
        "message": message,
        "data": data,
        "timestamp": int(time.time()),
    }


@router.post("", status_code=202)
def create_document(
    data: DocumentCreate,
    user_id: int = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """创建文档（自动触发向量化入库，返回 202 表示已接受处理）"""
    doc = DocumentService.create(db, data, user_id)
    # 自动触发异步入库
    IngestionService().enqueue(doc.id, db)
    return _success(
        data=DocumentResponse.model_validate(doc).model_dump(),
        message="文档创建成功",
    )


@router.get("/list")
def get_document_list(
    page: int = 1,
    page_size: int = 20,
    category: str | None = None,
    department: str | None = None,
    status: int | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
):
    """文档列表（分页、筛选）"""
    docs, total = DocumentService.get_list(
        db,
        page=page,
        page_size=page_size,
        category=category,
        department=department,
        status=status,
        keyword=keyword,
    )
    return _success(
        data={
            "total": total,
            "items": [DocumentResponse.model_validate(d).model_dump() for d in docs],
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/categories")
def get_categories(db: Session = Depends(get_db)):
    """获取文档分类列表"""
    categories = DocumentService.get_categories(db)
    return _success(data={"categories": categories})


@router.get("/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    """获取文档详情"""
    doc = DocumentService.get_by_id(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return _success(data=DocumentResponse.model_validate(doc).model_dump())


@router.put("/{document_id}")
def update_document(
    document_id: int,
    data: DocumentUpdate,
    user_id: int = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """更新文档"""
    doc = DocumentService.update(db, document_id, data)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return _success(
        data=DocumentResponse.model_validate(doc).model_dump(),
        message="文档更新成功",
    )


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    user_id: int = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """删除文档（软删除）"""
    # 验证权限（仅创建者或管理员可删除）
    current_user = UserService.get_by_id(db, user_id)
    doc = DocumentService.get_by_id(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.created_by != user_id and (not current_user or current_user.role != "admin"):
        raise HTTPException(status_code=403, detail="无权限删除此文档")

    success = DocumentService.soft_delete(db, document_id)
    if not success:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 通知 ai_service 清理工件（fire-and-forget，不阻塞响应）
    try:
        RAGService.delete_doc(document_id)
    except Exception:
        pass

    return _success(message="文档已删除")


@router.post("/rebuild-index")
def rebuild_index(
    user_id: int = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """重建索引：清空所有向量，从 MySQL 全量文档重新构建索引（仅管理员）"""
    # 1. 验证管理员权限
    current_user = UserService.get_by_id(db, user_id)
    if not current_user or current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可执行重建索引操作")

    # 2. 获取所有文档（不过滤状态）
    docs = DocumentService.get_all_documents(db)
    if not docs:
        return _success(
            data={"docs_count": 0, "chunks_count": 0, "indexed_count": 0},
            message="数据库中没有文档",
        )

    # 3. 构建发送给 ai_service 的文档列表
    documents = [
        {
            "id": doc.id,
            "title": doc.title or "",
            "content": doc.content or "",
            "category": doc.category or "",
            "source_url": doc.source_url or "",
        }
        for doc in docs
    ]

    # 4. 调用 ai_service /rebuild
    try:
        result = RAGService.rebuild_index(documents)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AI 服务调用失败: {exc}",
        )

    return _success(
        data=result,
        message=f"重建索引完成: {result.get('docs_count', 0)} 篇文档, {result.get('chunks_count', 0)} 个切片",
    )
