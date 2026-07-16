"""Initial schema: sys_user, kb_document, qa_record

Create Date: 2026-07-16 12:49:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "20260716_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── sys_user ────────────────────────────────────────────────
    op.create_table(
        "sys_user",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("nickname", sa.String(50), nullable=True),
        sa.Column("email", sa.String(100), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="student"),
        sa.Column("avatar", sa.String(255), nullable=True),
        sa.Column(
            "status", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sys_user")),
        sa.UniqueConstraint("username", name=op.f("uq_sys_user_username")),
        mysql_engine="InnoDB",
        mysql_default_charset="utf8mb4",
        mysql_comment="系统用户表",
    )
    op.create_index("idx_sys_user_role", "sys_user", ["role"])
    op.create_index("idx_sys_user_status", "sys_user", ["status"])

    # ── kb_document (without error_message/processed_at) ────────
    op.create_table(
        "kb_document",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "content",
            sa.Text().with_variant(mysql.LONGTEXT, "mysql"),
            nullable=True,
        ),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("file_type", sa.String(20), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column(
            "chunk_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "status", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kb_document")),
        mysql_engine="InnoDB",
        mysql_default_charset="utf8mb4",
        mysql_comment="知识库文档表",
    )
    op.create_index("idx_kb_document_category", "kb_document", ["category"])
    op.create_index("idx_kb_document_department", "kb_document", ["department"])
    op.create_index("idx_kb_document_status", "kb_document", ["status"])
    op.create_index("idx_kb_document_created_by", "kb_document", ["created_by"])

    # ── qa_record ───────────────────────────────────────────────
    op.create_table(
        "qa_record",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column(
            "answer",
            sa.Text().with_variant(mysql.LONGTEXT, "mysql"),
            nullable=True,
        ),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column(
            "tokens_used", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "feedback", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qa_record")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["sys_user.id"],
            name=op.f("fk_qa_record_user_id"),
        ),
        mysql_engine="InnoDB",
        mysql_default_charset="utf8mb4",
        mysql_comment="问答记录表",
    )
    op.create_index("idx_qa_record_user_id", "qa_record", ["user_id"])
    op.create_index("idx_qa_record_session_id", "qa_record", ["session_id"])
    op.create_index("idx_qa_record_created_at", "qa_record", ["created_at"])


def downgrade() -> None:
    op.drop_table("qa_record")
    op.drop_table("kb_document")
    op.drop_table("sys_user")
