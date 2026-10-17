"""RAG 问答服务 — ai_service HTTP 客户端"""

import httpx

AI_SERVICE_URL = "http://localhost:8003"


class RAGService:
    """封装与 ai_service 的 HTTP 通信"""

    @staticmethod
    async def query(question: str, top_k: int = 5, history: list[dict] | None = None) -> dict:
        """调用 ai_service /query 端点获取 RAG 问答结果"""
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{AI_SERVICE_URL}/query",
                json={"question": question, "top_k": top_k, "history": history or []},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def query_stream(question: str, top_k: int = 5, history: list[dict] | None = None):
        """调用 ai_service /query/stream 端点，逐行 yield SSE 事件"""
        import json

        params: dict = {"question": question, "top_k": top_k}
        if history:
            params["history"] = json.dumps(history, ensure_ascii=False)
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "GET",
                f"{AI_SERVICE_URL}/query/stream",
                params=params,
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line[6:]

    @staticmethod
    async def reindex() -> dict:
        """触发 ai_service 全量重新索引"""
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.get(f"{AI_SERVICE_URL}/reindex")
            return resp.json()

    @staticmethod
    async def stats() -> dict:
        """获取知识库统计信息"""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{AI_SERVICE_URL}/stats")
            return resp.json()

    @staticmethod
    async def process_file(file_path: str) -> dict:
        """提交文件路径给 ai_service 处理"""
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{AI_SERVICE_URL}/process",
                json={"file_path": file_path},
            )
            return resp.json()

    @staticmethod
    def rebuild_index_from_directory() -> dict:
        """让 ai_service 扫描知识目录并全量重建索引（同步调用）。

        这是唯一正确的重建方式：知识目录是内容的唯一真相，返回的
        ``documents`` 清单用于把 ``kb_document`` 对齐到磁盘。

        Returns
        -------
        dict
            ``{"docs_count", "chunks_count", "indexed_count",
            "time_seconds", "documents"}``。
        """
        with httpx.Client(timeout=600) as client:
            resp = client.get(f"{AI_SERVICE_URL}/reindex")
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def delete_doc(doc_id: str, keep_file: bool = False) -> dict:
        """通知 ai_service 删除索引条目（以及知识目录里的文件）。

        Parameters
        ----------
        doc_id : str
            索引里的文档 ID（即 ``kb_document.vector_doc_id``）。
        keep_file : bool
            为 ``True`` 时只删索引不删文件——“重新处理”需要这种语义。
        """
        with httpx.Client(timeout=30) as client:
            resp = client.delete(
                f"{AI_SERVICE_URL}/document/{doc_id}",
                params={"delete_file": not keep_file},
            )
            resp.raise_for_status()
            return resp.json()
