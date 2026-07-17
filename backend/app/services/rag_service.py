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
    def rebuild_index(documents: list[dict]) -> dict:
        """向 ai_service 发送重建索引请求（同步调用）。

        Parameters
        ----------
        documents : list[dict]
            每个 dict 包含 ``id``, ``title``, ``content``, ``category``,
            ``source_url``。

        Returns
        -------
        dict
            ``{"docs_count", "chunks_count", "indexed_count"}``。
        """
        with httpx.Client(timeout=300) as client:
            resp = client.post(
                f"{AI_SERVICE_URL}/rebuild",
                json={"documents": documents},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def delete_doc(doc_id: int) -> dict:
        """通知 ai_service 删除文档工件和向量（同步调用）。"""
        with httpx.Client(timeout=10) as client:
            resp = client.delete(f"{AI_SERVICE_URL}/document/{doc_id}")
            return resp.json()
