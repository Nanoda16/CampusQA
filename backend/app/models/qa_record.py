"""问答记录模型"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class QARecord(Base):
    """问答记录表（``qa_record``）

    字段与 ``alembic/versions/20260716_0001_initial.py`` 中的建表语句一一对应。

    这里只声明外键约束，不额外声明 ``relationship()``：现有消费方
    （``QAService`` / ``UserService.delete_user``）都直接用 ``user_id`` 过滤，
    没有对象图导航需求；用户删除由服务层显式清理 QARecord 行完成。
    """

    __tablename__ = "qa_record"
    __table_args__ = (
        Index("idx_qa_record_user_id", "user_id"),
        Index("idx_qa_record_session_id", "session_id"),
        Index("idx_qa_record_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sys_user.id", name="fk_qa_record_user_id"),
        nullable=False,
    )
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(
        Text().with_variant(mysql.LONGTEXT, "mysql"), nullable=True
    )
    sources: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    tokens_used: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    feedback: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<QARecord id={self.id} user_id={self.user_id}>"
