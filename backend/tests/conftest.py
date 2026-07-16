"""pytest 共享 fixtures

所有测试文件共享的 fixtures：
- db_session: SQLite 数据库会话
- client: FastAPI TestClient（依赖已重写为测试环境）
- mock_redis: fakeredis 实例
- mock_ai_service: AsyncMock mock（阻止真实 AI 服务调用）

注意事项：
  1. 使用 :memory: SQLite 时每个连接独享数据库，故改用临时文件。
  2. frontend/dist 中的 catch-all 路由注册早于 /api/health，
     必须在导入 app 前临时移除 dist 目录。
  3. SQLite 的 BIGINT 不支持 AUTOINCREMENT，需编译时映射为 INTEGER。
"""

import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

# ═══════════════════════════════════════════════════════════
# 必须在导入 app 之前完成：
#   1. 禁用 frontend/dist（catch-all 路由抢先于 /api/health）
#   2. 设置环境变量确保 fakeredis 降级
# ═══════════════════════════════════════════════════════════

_FRONTEND_DIST = (
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
)
_FRONTEND_DIST_BAK = _FRONTEND_DIST.with_suffix(".dist.bak")

_frontend_was_renamed = False
if _FRONTEND_DIST.exists():
    _FRONTEND_DIST.rename(_FRONTEND_DIST_BAK)
    _frontend_was_renamed = True

os.environ.setdefault("REDIS_FALLBACK_TO_FAKE", "True")


# SQLite BIGINT → INTEGER 编译钩子（支持 autoincrement）
@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(element, compiler, **kw):
    """SQLite 仅支持 INTEGER PRIMARY KEY AUTOINCREMENT，而非 BIGINT"""
    return compiler.visit_integer(element, **kw)


from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.redis_client import get_redis  # noqa: E402

# ═══════════════════════════════════════════════════════════
# SQLite 临时文件数据库
# ═══════════════════════════════════════════════════════════
TEST_DB_FD, TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="campus_qa_test_")
os.close(TEST_DB_FD)
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(test_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=OFF")
    cursor.close()


TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)


def override_get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖覆盖：使用 SQLite 测试数据库"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def override_get_redis():
    """FastAPI 依赖覆盖：使用独立的 fakeredis 实例"""
    return fakeredis.FakeRedis(decode_responses=True)


# ═══════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """会话级别：在 SQLite 中创建所有表，测试结束后清理"""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except PermissionError:
            pass


@pytest.fixture(scope="session", autouse=True)
def _restore_frontend_dist():
    """会话级别：恢复 frontend/dist（在 session 结束时还原）"""
    yield
    global _frontend_was_renamed
    if _frontend_was_renamed and _FRONTEND_DIST_BAK.exists():
        _FRONTEND_DIST_BAK.rename(_FRONTEND_DIST)
        _frontend_was_renamed = False


@pytest.fixture
def db_session(setup_database: None) -> Generator[Session, None, None]:
    """每个测试：提供独立的数据库会话"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """FastAPI TestClient，所有外部依赖已重写为测试环境"""
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def mock_redis(client: TestClient):
    """返回测试中使用的 fakeredis 实例，可直接操作缓存"""
    import app.redis_client as rc

    fake = fakeredis.FakeRedis(decode_responses=True)
    rc.redis_client = fake
    return fake


@pytest.fixture(autouse=True)
def mock_ai_service():
    """自动 mock ai_service 的 HTTP 调用，防止测试时真实请求"""
    with patch(
        "app.services.rag_service.RAGService.query", new_callable=AsyncMock
    ) as mock_query, patch(
        "app.services.rag_service.RAGService.query_stream",
        new_callable=AsyncMock,
    ) as mock_stream, patch(
        "app.services.rag_service.RAGService.reindex", new_callable=AsyncMock
    ) as mock_reindex, patch(
        "app.services.rag_service.RAGService.stats", new_callable=AsyncMock
    ) as mock_stats, patch(
        "app.services.rag_service.RAGService.process_file",
        new_callable=AsyncMock,
    ) as mock_process:
        mock_query.return_value = {"answer": "Mocked answer", "sources": []}
        mock_stream.return_value = [
            {"type": "answer", "content": "Mocked stream answer"}
        ]
        mock_reindex.return_value = {"status": "ok", "indexed": 0}
        mock_stats.return_value = {"total_docs": 0, "total_chunks": 0}
        mock_process.return_value = {"status": "ok", "chunks": 0}
        yield
