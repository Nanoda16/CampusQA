"""文档状态机单元测试

验证 DocumentStatus 枚举、默认值、状态迁移、错误信息，
以及现有 CRUD API 不受影响。
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.enums import DocumentStatus


# ── 辅助 ──────────────────────────────────────────────
REGISTER_URL = "/api/user/register"
LOGIN_URL = "/api/user/login"
DOCUMENT_URL = "/api/document"


def _login_and_get_token(
    client: TestClient, username: str = "state_test", password: str = "Pass1234"
) -> str:
    """注册并登录，返回 access_token"""
    client.post(
        REGISTER_URL,
        json={
            "username": username,
            "password": password,
            "role": "student",
            "nickname": "State Tester",
        },
    )
    resp = client.post(
        LOGIN_URL, json={"username": username, "password": password}
    )
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


# ── 模型层测试 ────────────────────────────────────────


class TestDocumentStatusEnum:
    """DocumentStatus 枚举行为"""

    def test_enum_values(self):
        """枚举值定义正确"""
        assert DocumentStatus.UPLOADED.value == 1
        assert DocumentStatus.PROCESSING.value == 2
        assert DocumentStatus.READY.value == 3
        assert DocumentStatus.FAILED.value == 4

    def test_enum_membership(self):
        """所有状态在枚举中"""
        names = {e.name for e in DocumentStatus}
        assert names == {"UPLOADED", "PROCESSING", "READY", "FAILED"}


class TestDocumentDefaults:
    """Document 模型默认值"""

    def test_document_default_status(self, db_session: Session):
        """新文档默认 status=UPLOADED"""
        doc = Document(title="默认状态文档")
        db_session.add(doc)
        db_session.flush()
        assert doc.status == DocumentStatus.UPLOADED
        assert doc.status.value == 1

    def test_document_default_chunk_count(self, db_session: Session):
        """新文档默认 chunk_count=0"""
        doc = Document(title="默认切片文档")
        db_session.add(doc)
        db_session.flush()
        assert doc.chunk_count == 0

    def test_document_default_error_message(self, db_session: Session):
        """新文档默认 error_message=None"""
        doc = Document(title="默认错误信息文档")
        db_session.add(doc)
        db_session.flush()
        assert doc.error_message is None

    def test_document_default_processed_at(self, db_session: Session):
        """新文档默认 processed_at=None"""
        doc = Document(title="默认处理时间文档")
        db_session.add(doc)
        db_session.flush()
        assert doc.processed_at is None


class TestDocumentStatusTransition:
    """文档状态迁移"""

    @pytest.fixture
    def doc(self, db_session: Session) -> Document:
        d = Document(title="状态迁移测试文档")
        db_session.add(d)
        db_session.flush()
        return d

    def test_uploaded_to_processing(self, doc: Document, db_session: Session):
        """UPLOADED → PROCESSING"""
        doc.status = DocumentStatus.PROCESSING
        db_session.flush()
        assert doc.status == DocumentStatus.PROCESSING

    def test_processing_to_ready(self, doc: Document, db_session: Session):
        """UPLOADED → PROCESSING → READY"""
        doc.status = DocumentStatus.PROCESSING
        db_session.flush()

        doc.status = DocumentStatus.READY
        doc.processed_at = datetime.now()
        db_session.flush()

        assert doc.status == DocumentStatus.READY
        assert doc.processed_at is not None

    def test_processing_to_failed(self, doc: Document, db_session: Session):
        """UPLOADED → PROCESSING → FAILED（含错误信息）"""
        doc.status = DocumentStatus.PROCESSING
        db_session.flush()

        doc.status = DocumentStatus.FAILED
        doc.error_message = "解析文档失败: 文件格式不支持"
        db_session.flush()

        assert doc.status == DocumentStatus.FAILED
        assert doc.error_message == "解析文档失败: 文件格式不支持"

    def test_direct_to_failed(self, doc: Document, db_session: Session):
        """UPLOADED → FAILED（上传后直接标记失败）"""
        doc.status = DocumentStatus.FAILED
        doc.error_message = "文件损坏无法读取"
        db_session.flush()

        assert doc.status == DocumentStatus.FAILED
        assert doc.error_message == "文件损坏无法读取"


class TestDocumentErrorMessage:
    """错误信息字段"""

    def test_error_message_cleared_on_retry(self, db_session: Session):
        """重新处理时清空错误信息"""
        doc = Document(title="重试文档", status=DocumentStatus.FAILED,
                       error_message="初次失败")
        db_session.add(doc)
        db_session.flush()

        # 模拟重新处理：设置为 PROCESSING，清空错误信息
        doc.status = DocumentStatus.PROCESSING
        doc.error_message = None
        db_session.flush()

        assert doc.status == DocumentStatus.PROCESSING
        assert doc.error_message is None

    def test_error_message_long_value(self, db_session: Session):
        """错误信息可存储较长文本"""
        long_msg = "x" * 450
        doc = Document(title="长错误信息文档", status=DocumentStatus.FAILED,
                       error_message=long_msg)
        db_session.add(doc)
        db_session.flush()

        loaded = db_session.get(Document, doc.id)
        assert loaded is not None
        assert loaded.error_message == long_msg


# ── API 层测试（确保现有 CRUD 不受影响）─────────────


class TestExistingApi:
    """现有文档 CRUD API 不受新字段影响"""

    def test_create_document_returns_new_fields(self, client: TestClient):
        """创建文档返回包含 error_message 和 processed_at"""
        token = _login_and_get_token(client, "crud_test1")
        resp = client.post(
            DOCUMENT_URL,
            json={"title": "新字段测试文档", "content": "测试内容"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 202
        data = resp.json()["data"]
        assert "error_message" in data
        assert "processed_at" in data
        assert data["error_message"] is None
        assert data["processed_at"] is None

    def test_create_document_has_default_status(self, client: TestClient):
        """新创建的文档 status=PROCESSING(2)（创建后自动入队）"""
        token = _login_and_get_token(client, "crud_test2")
        resp = client.post(
            DOCUMENT_URL,
            json={"title": "默认状态测试", "content": "测试"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 202
        data = resp.json()["data"]
        assert data["status"] == DocumentStatus.PROCESSING.value

    def test_get_document_list_returns_new_fields(self, client: TestClient):
        """文档列表返回新字段"""
        token = _login_and_get_token(client, "crud_test3")
        client.post(
            DOCUMENT_URL,
            json={"title": "列表测试文档", "content": "列表测试"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.get(
            f"{DOCUMENT_URL}/list",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) > 0
        item = items[0]
        assert "error_message" in item
        assert "processed_at" in item

    def test_create_document_with_old_status_still_works(
        self, client: TestClient
    ):
        """兼容旧 status 字段——即使传入 status=1，enqueue 后返回 PROCESSING(2)"""
        token = _login_and_get_token(client, "crud_test4")
        resp = client.post(
            DOCUMENT_URL,
            json={"title": "旧字段兼容测试", "status": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 202
        data = resp.json()["data"]
        assert data["status"] == DocumentStatus.PROCESSING.value

    def test_update_document_preserves_new_fields(
        self, client: TestClient, db_session: Session
    ):
        """更新文档时新字段不被清除"""
        token = _login_and_get_token(client, "crud_test5")
        # 创建文档（API 使用 override_get_db 的独立 session）
        resp = client.post(
            DOCUMENT_URL,
            json={"title": "更新保留测试"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 202
        doc_id = resp.json()["data"]["id"]

        # 用测试 db_session 直接设置状态和错误信息并提交
        doc = db_session.get(Document, doc_id)
        assert doc is not None, "db_session 应能看到 API 创建的文档"
        doc.status = DocumentStatus.FAILED
        doc.error_message = "模拟错误"
        db_session.commit()

        # 通过 API 更新标题（不应清除 error_message）
        resp = client.put(
            f"{DOCUMENT_URL}/{doc_id}",
            json={"title": "更新后的标题"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title"] == "更新后的标题"

        # 错误信息应保留（PUT 不修改 error_message，且包含它在响应中）
        assert data["error_message"] == "模拟错误"

        # 状态也应保留
        assert data["status"] == DocumentStatus.FAILED.value

    def test_delete_document_still_works(self, client: TestClient):
        """软删除不受新字段影响"""
        token = _login_and_get_token(client, "crud_test6")
        resp = client.post(
            DOCUMENT_URL,
            json={"title": "删除测试文档"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 202
        doc_id = resp.json()["data"]["id"]

        resp = client.delete(
            f"{DOCUMENT_URL}/{doc_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "文档已删除"
