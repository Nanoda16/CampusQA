"""Add error_message and processed_at to kb_document (Task 12)

Create Date: 2026-07-16 12:49:01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260716_0002"
down_revision: Union[str, None] = "20260716_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kb_document",
        sa.Column(
            "error_message",
            sa.String(500),
            nullable=True,
            comment="处理失败时的错误信息",
        ),
    )
    op.add_column(
        "kb_document",
        sa.Column(
            "processed_at",
            sa.DateTime(),
            nullable=True,
            default=None,
            comment="处理完成时间",
        ),
    )


def downgrade() -> None:
    op.drop_column("kb_document", "processed_at")
    op.drop_column("kb_document", "error_message")
