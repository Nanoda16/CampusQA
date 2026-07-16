"""Alembic 迁移测试

测试循环：upgrade head → downgrade -1 → upgrade head 验证幂等性。

注意事项：
  1. 使用临时 SQLite 文件作为测试数据库。
  2. 通过 ALEMBIC_DB_URL 环境变量注入测试连接串。
  3. 每个测试方法使用独立的数据库文件，互不干扰。
"""

import os
import tempfile

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def _make_alembic_config(db_url: str) -> Config:
    """构建指向临时数据库的 Alembic 配置"""
    alembic_ini = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "alembic.ini",
    )
    cfg = Config(alembic_ini)
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


@pytest.fixture
def alembic_cfg():
    """每个测试：独立的临时 SQLite 数据库 + Alembic 配置"""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="alembic_test_")
    os.close(fd)
    db_url = f"sqlite:///{path}"
    cfg = _make_alembic_config(db_url)
    yield cfg, db_url, path
    # 清理
    if os.path.exists(path):
        try:
            os.remove(path)
        except PermissionError:
            pass


class TestAlembicMigrations:
    """Alembic 迁移生命周期测试"""

    def _get_table_names(self, db_url: str) -> set[str]:
        """辅助方法：获取数据库中的表名集合"""
        engine = create_engine(db_url)
        with engine.connect() as conn:
            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
        engine.dispose()
        return tables

    def _get_column_names(self, db_url: str, table: str) -> set[str]:
        """辅助方法：获取指定表的所有列名"""
        engine = create_engine(db_url)
        with engine.connect() as conn:
            inspector = inspect(conn)
            columns = {col["name"] for col in inspector.get_columns(table)}
        engine.dispose()
        return columns

    # ────────────────────────────────────────────────────────
    # 正向迁移：upgrade head → 所有表就绪
    # ────────────────────────────────────────────────────────

    def test_upgrade_head_creates_all_tables(self, alembic_cfg):
        """验证 upgrade head 后所有核心表均已创建"""
        cfg, db_url, _ = alembic_cfg

        command.upgrade(cfg, "head")

        tables = self._get_table_names(db_url)
        assert "sys_user" in tables, "sys_user 表未创建"
        assert "kb_document" in tables, "kb_document 表未创建"
        assert "qa_record" in tables, "qa_record 表未创建"

    def test_upgrade_head_has_document_status_columns(self, alembic_cfg):
        """验证 upgrade head 后 kb_document 包含 Task 12 新增字段"""
        cfg, db_url, _ = alembic_cfg

        command.upgrade(cfg, "head")

        columns = self._get_column_names(db_url, "kb_document")
        assert "error_message" in columns, "缺少 error_message 列"
        assert "processed_at" in columns, "缺少 processed_at 列"

    def test_upgrade_head_has_foreign_keys(self, alembic_cfg):
        """验证 qa_record 存在指向 sys_user 的外键"""
        cfg, db_url, _ = alembic_cfg

        command.upgrade(cfg, "head")

        engine = create_engine(db_url)
        with engine.connect() as conn:
            inspector = inspect(conn)
            fks = inspector.get_foreign_keys("qa_record")
        engine.dispose()

        assert len(fks) > 0, "qa_record 缺少外键"
        assert fks[0]["referred_table"] == "sys_user"

    def test_upgrade_head_has_indexes(self, alembic_cfg):
        """验证核心表上的关键索引已创建"""
        cfg, db_url, _ = alembic_cfg

        command.upgrade(cfg, "head")

        engine = create_engine(db_url)
        with engine.connect() as conn:
            inspector = inspect(conn)
            sys_user_indexes = {ix["name"] for ix in inspector.get_indexes("sys_user")}
            doc_indexes = {ix["name"] for ix in inspector.get_indexes("kb_document")}
            qa_indexes = {ix["name"] for ix in inspector.get_indexes("qa_record")}
        engine.dispose()

        assert "idx_sys_user_role" in sys_user_indexes
        assert "idx_kb_document_category" in doc_indexes
        assert "idx_qa_record_user_id" in qa_indexes

    # ────────────────────────────────────────────────────────
    # 降级测试：downgrade -1 → 回退一个版本
    # ────────────────────────────────────────────────────────

    def test_downgrade_removes_document_status_columns(self, alembic_cfg):
        """验证 downgrade -1 后 error_message / processed_at 被移除"""
        cfg, db_url, _ = alembic_cfg

        command.upgrade(cfg, "head")
        command.downgrade(cfg, "-1")

        columns = self._get_column_names(db_url, "kb_document")
        assert "error_message" not in columns, "error_message 应被移除"
        assert "processed_at" not in columns, "processed_at 应被移除"

    def test_downgrade_preserves_other_tables(self, alembic_cfg):
        """验证 downgrade -1 后核心表依然存在"""
        cfg, db_url, _ = alembic_cfg

        command.upgrade(cfg, "head")
        command.downgrade(cfg, "-1")

        tables = self._get_table_names(db_url)
        assert "sys_user" in tables
        assert "kb_document" in tables
        assert "qa_record" in tables

    # ────────────────────────────────────────────────────────
    # 幂等性测试：re-upgrade 后状态与 head 一致
    # ────────────────────────────────────────────────────────

    def test_reupgrade_restores_columns(self, alembic_cfg):
        """验证 downgrade -1 → upgrade head 后列被恢复"""
        cfg, db_url, _ = alembic_cfg

        command.upgrade(cfg, "head")
        command.downgrade(cfg, "-1")
        command.upgrade(cfg, "head")

        columns = self._get_column_names(db_url, "kb_document")
        assert "error_message" in columns, "re-upgrade 后 error_message 应恢复"
        assert "processed_at" in columns, "re-upgrade 后 processed_at 应恢复"

    def test_reupgrade_is_idempotent(self, alembic_cfg):
        """验证连续 upgrade head 两次不会报错"""
        cfg, db_url, _ = alembic_cfg

        command.upgrade(cfg, "head")
        command.upgrade(cfg, "head")  # 第二次应该无操作

        tables = self._get_table_names(db_url)
        assert "sys_user" in tables
        assert "kb_document" in tables
        assert "qa_record" in tables

    def test_full_upgrade_downgrade_cycle(self, alembic_cfg):
        """验证完整周期：upgrade head → 检查 → downgrade 0001 → 检查 → upgrade head → 检查"""
        cfg, db_url, _ = alembic_cfg

        # 1. upgrade to head
        command.upgrade(cfg, "head")
        assert "error_message" in self._get_column_names(db_url, "kb_document")
        assert "processed_at" in self._get_column_names(db_url, "kb_document")

        # 2. downgrade to initial (0001)
        command.downgrade(cfg, "20260716_0001")
        cols = self._get_column_names(db_url, "kb_document")
        assert "error_message" not in cols
        assert "processed_at" not in cols

        # 3. upgrade to head again
        command.upgrade(cfg, "head")
        cols2 = self._get_column_names(db_url, "kb_document")
        assert "error_message" in cols2
        assert "processed_at" in cols2
