"""模型层枚举

``DocumentStatus`` 描述 ``kb_document.status`` 列的取值。

设计说明
--------
数据库中的 ``status`` 列是 **Integer**（迁移 20260716_0001 里就是
``sa.Column("status", sa.Integer(), ...)``），不是 SQLAlchemy ``Enum``。
因此这里用 Python 侧 ``IntEnum`` 表达同一套取值：

* 存入数据库时是普通整数（SQLite / MySQL 行为一致）；
* 从数据库读回来的是 ``int``，但 ``IntEnum`` 是 ``int`` 的子类，
  ``doc.status == DocumentStatus.READY`` 这类比较依然成立；
* 调用方也可以显式使用 ``DocumentStatus.UPLOADED.value``。
"""

from enum import IntEnum


class DocumentStatus(IntEnum):
    """文档处理状态（对应 init_db.sql 第 46 行的列注释）

    1 = UPLOADED   已上传，等待处理
    2 = PROCESSING 处理中
    3 = READY      处理完成，可检索
    4 = FAILED     处理失败
    """

    UPLOADED = 1
    PROCESSING = 2
    READY = 3
    FAILED = 4
