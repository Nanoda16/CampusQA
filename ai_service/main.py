"""
AI Service — FastAPI server for RAG query, streaming, and indexing.

Endpoints
---------
GET  /health        → Health check
POST /query         → Synchronous RAG query
GET  /query/stream  → SSE streaming query
GET  /reindex       → Full re-index all documents
POST /process       → Index a single file
GET  /stats         → Knowledge base statistics
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from engine.pipeline import RAGPipeline

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("ai_service")

# ---------------------------------------------------------------------------
# App & CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="AI Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global pipeline instance
# ---------------------------------------------------------------------------

pipeline: RAGPipeline = RAGPipeline()

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class HistoryTurn(BaseModel):
    role: str = Field(..., description='"user" or "ai"')
    content: str = Field(default="", description="Turn text")


class QueryRequest(BaseModel):
    question: str = Field(..., description="The user's question")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of chunks to retrieve")
    history: list[HistoryTurn] = Field(
        default_factory=list, description="Prior conversation turns for multi-turn context"
    )


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]]


class ProcessRequest(BaseModel):
    file_path: str = Field(..., description="Path to the document file")
    doc_id: str | None = Field(None, description="Override doc_id for consistent cleanup")


class ProcessResponse(BaseModel):
    chunks_count: int
    indexed: int
    doc_id: str


class RebuildDocument(BaseModel):
    id: int = Field(..., description="Document ID from MySQL")
    title: str = Field(default="", description="Document title")
    content: str = Field(default="", description="Document content")
    category: str = Field(default="", description="Document category")
    source_url: str = Field(default="", description="Original source URL")


class RebuildRequest(BaseModel):
    documents: list[RebuildDocument] = Field(
        ..., description="List of documents to index"
    )


class RebuildResponse(BaseModel):
    docs_count: int
    chunks_count: int
    indexed_count: int


# ---------------------------------------------------------------------------
# Startup event
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup_event() -> None:
    logger.info("AI Service running on port 8003")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Sync query
# ---------------------------------------------------------------------------


@app.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest) -> dict[str, Any]:
    try:
        history = [t.model_dump() for t in body.history]
        result = pipeline.run(query=body.question, top_k=body.top_k, history=history)
        return result
    except Exception as exc:
        logger.exception("Sync query failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# SSE streaming query
# ---------------------------------------------------------------------------


@app.get("/query/stream")
async def query_stream(
    question: str = Query(..., description="The user's question"),
    top_k: int = Query(default=5, ge=1, le=50),
    history: str = Query(default="", description="JSON-encoded prior turns"),
) -> EventSourceResponse:
    # history arrives as a JSON string (GET query param); parse defensively
    parsed_history: list[dict] = []
    if history:
        try:
            import json as _json

            raw = _json.loads(history)
            if isinstance(raw, list):
                parsed_history = [
                    {"role": t.get("role", ""), "content": t.get("content", "")}
                    for t in raw
                    if isinstance(t, dict)
                ]
        except (ValueError, TypeError):
            logger.warning("Failed to parse history query param; ignoring")

    async def event_generator():
        import json as _json

        try:
            for event in pipeline.run_stream(
                query=question, top_k=top_k, history=parsed_history
            ):
                event_type = event.pop("type", None) or "unknown"
                # data 必须是合法 JSON 字符串（默认 str(dict) 会产生单引号，
                # 前端 JSON.parse 会失败，导致 token 无法渲染）
                yield {
                    "event": event_type,
                    "data": _json.dumps(event, ensure_ascii=False),
                }
        except Exception as exc:
            logger.exception("Streaming query failed")
            yield {"event": "error", "data": _json.dumps({"message": str(exc)})}

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Rebuild index from MySQL documents (new)
# ---------------------------------------------------------------------------


@app.post("/rebuild", response_model=RebuildResponse)
async def rebuild(body: RebuildRequest) -> dict[str, Any]:
    """Clear all vectors and rebuild index from provided documents.

    Accepts a list of documents (id, title, content, category, source_url),
    clears existing FAISS + BM25 indices and artifacts, then chunks, embeds,
    and indexes every document.  Returns count statistics.
    """
    try:
        docs = [d.model_dump() for d in body.documents]
        if not docs:
            return {"docs_count": 0, "chunks_count": 0, "indexed_count": 0}

        result = pipeline.rebuild_from_documents(docs)
        return result
    except Exception as exc:
        logger.exception("/rebuild failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Re-index (legacy — keep backward compat)
# ---------------------------------------------------------------------------


@app.get("/reindex")
async def reindex() -> dict[str, Any]:
    try:
        result = pipeline.index_documents()
        return result
    except Exception as exc:
        logger.exception("Re-index failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Process single file
# ---------------------------------------------------------------------------


@app.post("/process", response_model=ProcessResponse)
async def process(body: ProcessRequest) -> dict[str, Any]:
    try:
        result = pipeline.add_document(
            file_path=body.file_path,
            doc_id=body.doc_id,
        )
        return result
    except Exception as exc:
        logger.exception("Process document failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/document/{doc_id}")
async def delete_document(doc_id: str) -> dict[str, Any]:
    """Remove a document artifact and its vectors from the index."""
    try:
        result = pipeline.remove_document(doc_id)
        return result
    except Exception as exc:
        logger.exception("Delete document failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@app.get("/stats")
async def stats() -> dict[str, Any]:
    try:
        return pipeline.get_stats()
    except Exception as exc:
        logger.exception("Get stats failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=False)
