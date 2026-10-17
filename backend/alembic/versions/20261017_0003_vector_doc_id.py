"""Add vector_doc_id to kb_document

The knowledge directory is now the single source of truth for what should be
searchable.  A full rebuild scans it and returns a manifest, and the backend
mirrors ``kb_document`` from that manifest.  To match rows to index entries we
need to remember the id the index assigned to each file (``md5`` of the file's
absolute path), instead of relying on ``kb_document.id``.

Create Date: 2026-10-17 17:20:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20261017_0003"
down_revision: Union[str, None] = "20260716_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kb_document",
        sa.Column(
            "vector_doc_id",
            sa.String(64),
            nullable=True,
            comment="向量索引里的文档 ID（知识目录内文件绝对路径的 md5）",
        ),
    )
    op.create_index(
        "idx_kb_document_vector_doc_id",
        "kb_document",
        ["vector_doc_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_kb_document_vector_doc_id", table_name="kb_document")
    op.drop_column("kb_document", "vector_doc_id")
