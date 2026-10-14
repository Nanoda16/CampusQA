"""系统用户模型"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """系统用户表（``sys_user``）

    字段与 ``alembic/versions/20260716_0001_initial.py`` 中的建表语句一一对应。
    """

    __tablename__ = "sys_user"
    __table_args__ = (
        UniqueConstraint("username", name="uq_sys_user_username"),
        Index("idx_sys_user_role", "role"),
        Index("idx_sys_user_status", "status"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="student"
    )
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"
