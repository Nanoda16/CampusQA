"""
AI service configuration via Pydantic Settings.

Loads all config from ``.env`` with sensible defaults.  This module
centralises every tunable parameter used across the RAG engine
(retrieval, BM25, RRF fusion, reranker, embedding, LLM, and storage).

Usage
-----
    from config import settings

    threshold = settings.REJECTION_THRESHOLD
    model = settings.LLM_MODEL
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Retrieval ──────────────────────────────────────────────────────
    REJECTION_THRESHOLD: float = 0.35
    """Min top-1 similarity to accept retrieval (OOD rejection)."""

    CHUNK_SIZE: int = 512
    """Max characters per chunk."""

    CHUNK_OVERLAP: int = 64
    """Overlap between consecutive chunks."""

    TOP_K: int = 3
    """Default number of chunks to retrieve."""

    # ── BM25 ───────────────────────────────────────────────────────────
    BM25_K1: float = 1.5
    """BM25 k1 parameter (term saturation)."""

    BM25_B: float = 0.75
    """BM25 b parameter (length normalisation)."""

    # ── RRF Fusion ─────────────────────────────────────────────────────
    RRF_K: float = 60.0
    """RRF smoothing constant (denominator: k + rank)."""

    # ── Cross-encoder Reranker ─────────────────────────────────────────
    RERANKER_ENABLED: bool = True
    """Enable cross-encoder reranking after RRF fusion."""

    RERANKER_MODEL: str = "BAAI/bge-reranker-base"
    """HuggingFace model ID for the reranker."""

    RERANKER_MAX_LENGTH: int = 512
    """Max token length for reranker input pairs."""

    RERANKER_TOP_K: int = 3
    """Number of top chunks kept after reranking."""

    # ── Embedding ──────────────────────────────────────────────────────
    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"
    """HuggingFace model ID for bi-encoder embeddings."""

    EMBEDDING_DIM: int = 512
    """Output dimension of the embedding model."""

    # ── LLM / DeepSeek ────────────────────────────────────────────────
    # New standardised names (set these in .env for clarity).
    LLM_MODEL: str = "deepseek-chat"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 1024

    # Legacy names — kept for backward compatibility with existing .env
    # files that use DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL.
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ── Storage ────────────────────────────────────────────────────────
    ARTIFACT_DIR: str = "data/artifacts"
    """Directory for per-document JSON artifacts (relative to ai_service/)."""

    INGESTION_TIMEOUT_S: int = 300
    """Max seconds to wait for a single document ingestion."""

    # ── Pydantic settings ──────────────────────────────────────────────
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Module-level singleton — import and use directly.
settings = Settings()
