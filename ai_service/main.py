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
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description=(
            "Candidate depth per retriever before RRF fusion. The fused "
            "ranking is truncated to the pipeline's final window (3 chunks)."
        ),
    )
    history: list[HistoryTurn] = Field(
        default_factory=list, description="Prior conversation turns for multi-turn context"
    )


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]]


class ProcessRequest(BaseModel):
    file_path: str = Field(..., description="Path to the document file")
    doc_id: str | None = Field(
        None,
        description=(
            "Override doc_id. Normally the id is md5(abs path), so the same "
            "file always maps to the same id."
        ),
    )
    persist: bool = Field(
        True,
        description=(
            "Copy the parsed text into the knowledge directory before indexing. "
            "Required for uploads: a full rebuild scans that directory, so a "
            "document that never landed there would vanish on the next rebuild. "
            "Pass false when re-indexing a file that already lives in the "
            "directory."
        ),
    )
    category: str | None = Field(
        None,
        description="Sub-folder / category used when persisting the document",
    )


class ProcessResponse(BaseModel):
    chunks_count: int
    indexed: int
    doc_id: str
    bm25_chunks: int = 0
    title: str = ""
    category: str = ""
    source_url: str = ""
    file_path: str = ""
    persisted_path: str | None = None


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
    top_k: int = Query(
        default=5,
        ge=1,
        le=50,
        description="Candidate depth per retriever before RRF fusion",
    ),
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
# Re-index — scan the knowledge directory and rebuild everything
# ---------------------------------------------------------------------------


@app.get("/reindex")
async def reindex() -> dict[str, Any]:
    """Rebuild the whole index from the knowledge directory.

    Returns the counts plus a ``documents`` manifest so the backend can mirror
    its ``kb_document`` table to whatever is actually on disk.
    """
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
    """Index one document.

    With ``persist=True`` (the default, used for uploads) the parsed text is
    first written into the knowledge directory and then indexed, so a later
    ``/reindex`` still finds it.  With ``persist=False`` the file is indexed in
    place — use that when re-processing a file that already lives there.
    """
    try:
        if body.persist:
            result = pipeline.import_document(
                source_path=body.file_path,
                category=body.category,
            )
        else:
            result = pipeline.add_document(
                file_path=body.file_path,
                doc_id=body.doc_id,
            )
        return result
    except Exception as exc:
        logger.exception("Process document failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/document/{doc_id}")
async def delete_document(doc_id: str, delete_file: bool = True) -> dict[str, Any]:
    """Remove a document from the index and from the knowledge directory.

    Set ``delete_file=false`` to keep the file on disk while dropping its
    vectors — that is what "re-process this document" needs.
    """
    try:
        result = pipeline.remove_document(doc_id, delete_file=delete_file)
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
