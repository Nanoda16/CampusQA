"""数据模型包

集中导出三张核心表的 ORM 模型，供 ``alembic/env.py`` 及服务层使用：

    from app.models import User, Document, QARecord
"""

from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.qa_record import QARecord
from app.models.user import User

__all__ = ["User", "Document", "QARecord", "DocumentStatus"]
