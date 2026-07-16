"""文档管理 API 烟雾测试

涉及需要 JWT 认证的文档创建流程。
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.enums import DocumentStatus

REGISTER_URL = "/api/user/register"
LOGIN_URL = "/api/user/login"
DOCUMENT_URL = "/api/document"


def _login_and_get_token(
    client: TestClient, username: str = "doc_test", password: str = "DocPass123"
) -> str:
    """辅助函数：注册并登录，返回 access_token"""
    client.post(
        REGISTER_URL,
        json={
            "username": username,
            "password": password,
            "role": "student",
            "nickname": "Doc Tester",
        },
    )
    resp = client.post(
        LOGIN_URL, json={"username": username, "password": password}
    )
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


def test_create_document_success(client: TestClient) -> None:
    """认证用户创建文档 → 202（异步处理已接受）"""
    token = _login_and_get_token(client)

    resp = client.post(
        DOCUMENT_URL,
        json={
            "title": "测试文档标题",
            "content": "这是一篇测试文档的内容。",
            "category": "academic",
            "department": "计算机学院",
            "status": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 202

    data = resp.json()
    assert data["code"] == 200
    assert data["message"] == "文档创建成功"

    doc = data["data"]
    assert doc["title"] == "测试文档标题"
    assert doc["content"] == "这是一篇测试文档的内容。"
    assert doc["category"] == "academic"
    assert doc["department"] == "计算机学院"
    assert doc["status"] == 2  # enqueue 将状态变为 PROCESSING
    assert doc["id"] > 0
    assert "created_at" in doc


def test_create_document_without_auth(client: TestClient) -> None:
    """未认证用户创建文档 → 401"""
    resp = client.post(
        DOCUMENT_URL,
        json={"title": "未认证文档", "content": "不应该创建成功"},
    )
    assert resp.status_code == 401

    data = resp.json()
    assert "detail" in data


def test_create_document_without_title(client: TestClient) -> None:
    """缺少必填字段 title → 422"""
    token = _login_and_get_token(client)

    resp = client.post(
        DOCUMENT_URL,
        json={"content": "缺少标题的文档"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── Upload→auto-index integration tests ──


def test_create_triggers_ingestion(
    client: TestClient, db_session: Session
) -> None:
    """创建文档后自动触发入库 → 202 + status=PROCESSING(2)"""
    token = _login_and_get_token(client, "triggers_ingest")

    resp = client.post(
        DOCUMENT_URL,
        json={"title": "自动入库文档", "content": "触发入库的内容"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # API 返回 202 Accepted
    assert resp.status_code == 202
    data = resp.json()
    assert data["code"] == 200
    assert data["message"] == "文档创建成功"

    # 文档状态应为 PROCESSING（enqueue 同步修改）
    doc_id = data["data"]["id"]
    doc = db_session.get(Document, doc_id)
    assert doc is not None
    assert doc.status == DocumentStatus.PROCESSING
    assert doc.error_message is None


def test_delete_triggers_cleanup(client: TestClient) -> None:
    """删除文档后返回成功（工件清理 fire-and-forget 不阻塞）"""
    token = _login_and_get_token(client, "triggers_delete")

    # 先创建
    resp = client.post(
        DOCUMENT_URL,
        json={"title": "待删除文档", "content": "将被删除"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 202
    doc_id = resp.json()["data"]["id"]

    # 删除
    resp = client.delete(
        f"{DOCUMENT_URL}/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "文档已删除"

    # 验证文档已从数据库移除
    resp = client.get(
        f"{DOCUMENT_URL}/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_doc_searchable_after_ingestion(
    client: TestClient, db_session: Session
) -> None:
    """创建文档 → 模拟后台处理完成 → 文档变为 READY(3)"""
    from unittest.mock import patch
    from tests.conftest import TestingSessionLocal
    from app.services.document_service import IngestionService

    token = _login_and_get_token(client, "searchable_test")

    resp = client.post(
        DOCUMENT_URL,
        json={"title": "可搜索文档", "content": "搜索测试内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 202
    doc_id = resp.json()["data"]["id"]

    # 模拟后台线程处理完成
    svc = IngestionService(session_factory=TestingSessionLocal)
    with patch.object(svc, "_call_process_api", return_value={"chunks_count": 3}):
        svc._process_document(doc_id)

    # 用独立会话验证状态
    check_db = TestingSessionLocal()
    try:
        doc = check_db.get(Document, doc_id)
        assert doc is not None
        assert doc.status == DocumentStatus.READY
        assert doc.chunk_count == 3
    finally:
        check_db.close()
