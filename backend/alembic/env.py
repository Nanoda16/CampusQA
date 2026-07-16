"""Alembic 迁移环境配置

从 SQLAlchemy Base 元数据自动生成迁移。
生产环境使用 MySQL（通过 app.config），测试可覆盖 sqlalchemy.url。
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Alembic Config 对象 ──────────────────────────────────────
config = context.config

# ── 日志配置 ─────────────────────────────────────────────────
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── 导入所有模型，确保 Base.metadata 完整 ────────────────────
from app.database import Base  # noqa: E402
from app.models import User, Document, QARecord  # noqa: E402  # noqa: F401

target_metadata = Base.metadata

# ── 数据库 URL 解析 ──────────────────────────────────────────
# 优先级：1) config 中已有的值（测试注入）→ 2) ALEMBIC_DB_URL 环境变量 → 3) app.config
_url = config.get_main_option("sqlalchemy.url")
if not _url:
    _url = os.environ.get("ALEMBIC_DB_URL")
if not _url:
    from app.config import settings  # noqa: E402
    _url = settings.DATABASE_URL
    if _url is None:
        raise RuntimeError(
            "Database URL not configured — set sqlalchemy.url in alembic.ini, "
            "set ALEMBIC_DB_URL env var, or configure app.config"
        )

config.set_main_option("sqlalchemy.url", _url)


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL 脚本，不连接数据库"""
    context.configure(
        url=_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直接连接数据库执行迁移"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
