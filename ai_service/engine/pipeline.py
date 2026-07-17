"""
RAG pipeline — orchestrates the full retrieval-augmented generation workflow.

Connects Retriever → Prompts → Generator in a single callable interface,
with both synchronous and streaming modes, plus full indexing utilities.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Generator as GeneratorType

from . import chunker, embedding, loader, prompts
from .bm25_retriever import BM25Retriever
from .citation import validate_citations
from .fusion import rrf_fuse
from .generator import Generator
from .retriever import Retriever
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


def _make_chunk_id(d: dict) -> str:
    """Build ``{doc_id}_{chunk_index}`` from a chunk dict."""
    doc_id = d.get("doc_id", "")
    chunk_idx = d.get("chunk_index", 0)
    return f"{doc_id}_{chunk_idx}"


class RAGPipeline:
    """End-to-end RAG pipeline that orchestrates retrieval, prompt assembly,
    and LLM generation.

    Parameters
    ----------
    retriever : Retriever, optional
        Pre-configured retriever instance.  Created automatically from
        *vector_store* when omitted.
    generator : Generator, optional
        Pre-configured LLM generator instance.  Created automatically
        when omitted.
    vector_store : VectorStore, optional
        Pre-configured vector store instance.  When omitted a new one is
        created, which auto-loads persisted index files from disk if they
        exist.
    """

    def __init__(
        self,
        retriever: Retriever | None = None,
        generator: Generator | None = None,
        vector_store: VectorStore | None = None,
        bm25_retriever: BM25Retriever | None = None,
    ):
        self.vector_store = vector_store or VectorStore()
        self.retriever = retriever or Retriever(vector_store=self.vector_store)
        self.generator = generator or Generator()
        self.bm25_retriever = bm25_retriever or BM25Retriever()
        # Pipeline state: populated by query methods for downstream fusion
        self._bm25_results: list[tuple[str, float]] = []
        self._fused_results: list[tuple[str, float, list[float]]] = []

        # Reranker (lazy — only loaded when enabled and first used)
        self.reranker: Any | None = None
        self._reranker_enabled: bool = (
            os.environ.get("RERANKER_ENABLED", "true").lower() == "true"
        )
        self._reranker_top_k: int = 3

        logger.info(
            "RAGPipeline initialised (reranker=%s)",
            "enabled" if self._reranker_enabled else "disabled",
        )

        # Auto-rebuild FAISS + BM25 from artifacts if the index is missing
        self._check_auto_rebuild()

    # ------------------------------------------------------------------
    # Auto-rebuild on startup
    # ------------------------------------------------------------------

    def _check_auto_rebuild(self) -> None:
        """If ``data/faiss.index`` is missing but artifacts exist, rebuild.

        Scans the artifact directory; if at least one ``.json`` artifact is
        found and ``faiss.index`` does not exist, calls
        :meth:`ArtifactStore.rebuild_index` and then reloads the vector
        store so it reflects the newly-built index.
        """
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        index_path = os.path.join(base_dir, "data", "faiss.index")
        artifact_dir = os.path.join(base_dir, "data", "artifacts")

        if os.path.isfile(index_path):
            return  # Index already exists — nothing to do

        if not os.path.isdir(artifact_dir):
            return  # No artifact directory yet

        artifacts = [f for f in os.listdir(artifact_dir) if f.endswith(".json")]
        if not artifacts:
            return

        logger.info(
            "FAISS index missing, %d artifact(s) found. Rebuilding index...",
            len(artifacts),
        )
        from .artifact_store import ArtifactStore

        store = ArtifactStore()
        result = store.rebuild_index()
        logger.info(
            "Auto-rebuild complete: %d docs, %d chunks",
            result.get("docs_count", 0),
            result.get("chunks_count", 0),
        )

        # Reload vector store so the newly-built index is available in-memory
        self.vector_store.load()

    # ------------------------------------------------------------------
    # Rejection template
    # ------------------------------------------------------------------

    _REJECTION_TEMPLATE = "根据现有校园知识库，暂未找到关于「{question}」的可靠信息。"

    # ------------------------------------------------------------------
    # Small-talk detection
    # ------------------------------------------------------------------

    _GREETINGS = [
        "你好", "您好", "hi", "hello", "嗨", "在吗", "在不在",
        "谢谢", "感谢", "多谢", "你是谁", "你叫什么",
    ]

    @staticmethod
    def _is_small_talk(query: str) -> bool:
        """Return True if *query* is just a greeting or chit-chat."""
        q = query.strip().lower()
        return any(g in q for g in RAGPipeline._GREETINGS)

    # ------------------------------------------------------------------
    # Reranker integration
    # ------------------------------------------------------------------

    def _rerank_chunks(self, query: str, chunks: list[dict]) -> list[dict]:
        """Re-rank retrieved chunks with the cross-encoder and keep top-N.

        Results are re-sorted by descending cross-encoder score.  A new
        ``rerank_score`` key is added to each chunk dict (the original
        ``score`` from dense retrieval is preserved).

        Returns
        -------
        list[dict]
            The top ``self._reranker_top_k`` chunks in reranker order.
            Returns the original list unchanged if the reranker model cannot
            be loaded.
        """
        if self.reranker is None:
            from .reranker import Reranker

            self.reranker = Reranker()

        candidates = [(c["doc_id"], c["content"]) for c in chunks]
        reranked = self.reranker.rerank(query, candidates)

        # Build score lookup and re-sort
        score_map = {cid: score for cid, score in reranked}
        sorted_chunks = sorted(
            chunks,
            key=lambda c: score_map.get(c["doc_id"], 0.0),
            reverse=True,
        )

        # Annotate with reranker score (preserving original score)
        for c in sorted_chunks:
            c["rerank_score"] = score_map.get(c["doc_id"], c.get("score", 0.0))

        return sorted_chunks[: self._reranker_top_k]

    @staticmethod
    def _reorder_by_fusion(
        chunks: list[dict],
        fused_results: list[tuple[str, float, list[float]]],
    ) -> list[dict]:
        """Reorder dense chunks to match RRF fused ranking.

        Builds an ordering from *fused_results* while preserving the full
        chunk dicts.  Chunks that only appear in BM25 (not in *chunks*) are
        silently dropped because their metadata is unavailable.

        Parameters
        ----------
        chunks : list[dict]
            Dense retriever result dicts.
        fused_results : list[tuple[str, float, list[float]]]
            Output from :func:`rrf_fuse`.

        Returns
        -------
        list[dict]
            Input chunks reordered by descending fused score, then by
            descending dense score for ties.
        """
        chunk_map = {_make_chunk_id(c): c for c in chunks}
        ordered: list[dict] = []
        seen: set[str] = set()
        for cid, _, _ in fused_results:
            if cid in chunk_map and cid not in seen:
                ordered.append(chunk_map[cid])
                seen.add(cid)

        # Append any dense chunks that were not ranked by fusion
        # (shouldn't happen in practice, but defensive)
        for c in chunks:
            cid = _make_chunk_id(c)
            if cid not in seen:
                ordered.append(c)
                seen.add(cid)

        return ordered

    # ------------------------------------------------------------------
    # Sync pipeline
    # ------------------------------------------------------------------

    def run(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        history: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Run the full RAG pipeline synchronously.

        Parameters
        ----------
        query : str
            The user's question.
        top_k : int
            Number of chunks to retrieve (default 5).
        min_score : float
            Minimum similarity score threshold (default 0.0).
        temperature : float
            LLM sampling temperature (default 0.3).
        max_tokens : int
            Maximum tokens in the generated response (default 1024).
        history : list[dict] | None
            Prior conversation turns for multi-turn context resolution.

        Returns
        -------
        dict
            ``{"answer": str, "sources": list[dict]}``.
            When no relevant documents are found the *answer* will be
            ``"未找到相关校园信息"`` and *sources* an empty list.
            When retrieval confidence is too low the *answer* will be a
            rejection message indicating the knowledge base does not contain
            reliable information on the query topic.
        """
        # 0. Greeting / small-talk shortcut — skip RAG entirely
        if self._is_small_talk(query):
            return {
                "answer": (
                    "你好！我是河海大学校园知识问答助手 🤖\n\n"
                    "我可以帮你查询关于河海大学的各种信息，比如：\n"
                    "- 学校概况、校史、校训、校歌\n"
                    "- 招生政策、考试报名、研究生通知\n"
                    "- 学院介绍、专业设置、师资力量\n"
                    "- 校园活动、讲座、学术会议\n\n"
                    "直接告诉我你想了解什么就好！"
                ),
                "sources": [],
            }

        # 1. Dense retrieval (vectors)
        chunks = self.retriever.retrieve(query, top_k, min_score)

        # 1b. BM25 keyword retrieval (runs in parallel — results stored for fusion)
        self._bm25_results = self.bm25_retriever.retrieve(query, top_k)

        # 2. Graceful fallback when no results
        if not chunks:
            logger.info("No relevant chunks found for query: %s", query[:60])
            return {"answer": "未找到相关校园信息", "sources": []}

        # 2b. Low-confidence rejection (OOD query)
        if getattr(self.retriever, "low_confidence", False):
            logger.info(
                "OOD query rejected (low confidence): %s", query[:60]
            )
            return {
                "answer": self._REJECTION_TEMPLATE.format(question=query),
                "sources": [],
            }

        # 2c. RRF fusion — combine dense + BM25 rankings
        self._fused_results = rrf_fuse(chunks, self._bm25_results, top_k=top_k)
        logger.debug(
            "RRF fusion: %d dense + %d BM25 → %d fused results for query: %s",
            len(chunks), len(self._bm25_results), len(self._fused_results),
            query[:60],
        )
        chunks = self._reorder_by_fusion(chunks, self._fused_results)

        # 2d. Optional cross-encoder rerank (take top-5, re-rank, keep top-3)
        if self._reranker_enabled and chunks:
            logger.debug("Reranking %d chunks for query: %s", len(chunks), query[:60])
            chunks = self._rerank_chunks(query, chunks)

        # 3. Build prompt pair from retrieved chunks (+ optional history)
        system_prompt, user_prompt = prompts.build_prompt(query, chunks, history)

        # 4. Generate answer
        answer = self.generator.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # 4b. Post-process — remove invalid [Sx] citations
        validation = validate_citations(answer, chunks)
        if validation["invalid_count"] > 0:
            logger.info(
                "Removed %d invalid citation(s) from answer",
                validation["invalid_count"],
            )
        answer = validation["answer"]

        # 5. Structure output with source metadata
        return prompts.format_answer(answer, chunks)

    # ------------------------------------------------------------------
    # Streaming pipeline
    # ------------------------------------------------------------------

    def run_stream(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        history: list[dict] | None = None,
    ) -> GeneratorType[dict[str, Any], None, None]:
        """Run the RAG pipeline with streaming token output.

        Yields intermediate event dicts so callers can display progress
        indicators, show retrieved sources, and stream the answer token
        by token to the user.

        Parameters
        ----------
        query : str
            The user's question.
        top_k : int
            Number of chunks to retrieve (default 5).
        min_score : float
            Minimum similarity score threshold (default 0.0).
        temperature : float
            LLM sampling temperature (default 0.3).
        max_tokens : int
            Maximum tokens in the generated response (default 1024).

        Yields
        ------
        dict
            Event dicts with a ``"type"`` discriminator:

            - ``{"type": "status", "message": "检索中..."}``
            - ``{"type": "sources", "data": [...]}``
            - ``{"type": "token", "content": "..."}``
            - ``{"type": "done", "answer": "...", "sources": [...]}``
        """
        # 0. Greeting / small-talk shortcut
        if self._is_small_talk(query):
            yield {
                "type": "done",
                "answer": (
                    "你好！我是河海大学校园知识问答助手 🤖\n\n"
                    "我可以帮你查询关于河海大学的各种信息，比如：\n"
                    "- 学校概况、校史、校训、校歌\n"
                    "- 招生政策、考试报名、研究生通知\n"
                    "- 学院介绍、专业设置、师资力量\n"
                    "- 校园活动、讲座、学术会议\n\n"
                    "直接告诉我你想了解什么就好！"
                ),
                "sources": [],
            }
            return

        # 1. Status — retrieval phase
        yield {"type": "status", "message": "检索中..."}

        # 2. Retrieve (dense)
        chunks = self.retriever.retrieve(query, top_k, min_score)

        # 2b. BM25 keyword retrieval (parallel — stored for fusion in Task 8)
        self._bm25_results = self.bm25_retriever.retrieve(query, top_k)

        # 3. No results — short-circuit with fallback
        if not chunks:
            yield {
                "type": "done",
                "answer": "未找到相关校园信息",
                "sources": [],
            }
            return

        # 3b. Low-confidence rejection (OOD query)
        if getattr(self.retriever, "low_confidence", False):
            logger.info(
                "OOD query rejected (low confidence, stream): %s", query[:60]
            )
            yield {
                "type": "done",
                "answer": self._REJECTION_TEMPLATE.format(question=query),
                "sources": [],
            }
            return

        # 3c. RRF fusion — combine dense + BM25 rankings
        self._fused_results = rrf_fuse(chunks, self._bm25_results, top_k=top_k)
        logger.debug(
            "RRF fusion: %d dense + %d BM25 → %d fused results (stream)",
            len(chunks), len(self._bm25_results), len(self._fused_results),
        )
        chunks = self._reorder_by_fusion(chunks, self._fused_results)

        # 3d. Optional cross-encoder rerank (take top-5, re-rank, keep top-3)
        if self._reranker_enabled and chunks:
            logger.debug(
                "Reranking %d chunks for query (stream): %s",
                len(chunks), query[:60],
            )
            chunks = self._rerank_chunks(query, chunks)

        # 4. Emit sources for frontend display
        sources = [
            {
                "title": c.get("title", ""),
                "content_preview": c.get("content", "")[:100],
                "score": c.get("score", 0.0),
            }
            for c in chunks
        ]
        yield {"type": "sources", "data": sources}

        # 5. Build prompt (+ optional history for multi-turn context)
        system_prompt, user_prompt = prompts.build_prompt(query, chunks, history)

        # 6. Stream tokens from the LLM
        answer_parts: list[str] = []
        for token in self.generator.generate_stream(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            answer_parts.append(token)
            yield {"type": "token", "content": token}

        # 7. Signal completion with full answer + sources
        full_answer = "".join(answer_parts)

        # 7b. Post-process — remove invalid [Sx] citations
        validation = validate_citations(full_answer, chunks)
        if validation["invalid_count"] > 0:
            logger.info(
                "Removed %d invalid citation(s) from streaming answer",
                validation["invalid_count"],
            )
        full_answer = validation["answer"]

        yield {"type": "done", "answer": full_answer, "sources": sources}

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_documents(
        self,
        docs_dir: str | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> dict[str, Any]:
        """Load, chunk, embed, and index all knowledge documents.

        This is a full indexing pipeline that replaces any existing index
        in the vector store.  When *docs_dir* is ``None`` the default
        ``knowledge_docs/`` directory (relative to the project root) is
        used.

        Parameters
        ----------
        docs_dir : str, optional
            Path to the directory containing knowledge documents
            (``.md`` / ``.txt`` files).  Defaults to the project-level
            ``knowledge_docs/`` folder.
        chunk_size : int
            Maximum number of characters per chunk (default 500).
        chunk_overlap : int
            Overlap between consecutive chunks (default 50).

        Returns
        -------
        dict
            ``{"docs_count", "chunks_count", "indexed_count",
            "time_seconds"}``.
        """
        t0 = time.time()

        # 1. Load documents from disk
        docs = loader.load_knowledge_docs(docs_dir)
        doc_count = len(docs)
        logger.info("Loaded %d document(s)", doc_count)

        if doc_count == 0:
            elapsed = time.time() - t0
            logger.warning("No documents found to index")
            return {
                "docs_count": 0,
                "chunks_count": 0,
                "indexed_count": 0,
                "time_seconds": round(elapsed, 2),
            }

        # 2. Split into overlapping chunks
        chunks = chunker.chunk_docs(docs, chunk_size, chunk_overlap)
        chunk_count = len(chunks)
        logger.info("Created %d chunk(s)", chunk_count)

        # 3. Embed all chunk texts in a single batch
        texts = [c["content"] for c in chunks]
        vectors = embedding.embed(texts)

        # 4. Build parallel metadata list
        metadata = [
            {
                "content": c["content"],
                "doc_id": c["doc_id"],
                "chunk_index": c["chunk_index"],
                "chunk_id": f"{c['doc_id']}_{c['chunk_index']}",
                "title": c["title"],
                "category": c["category"],
                "source_url": c["source_url"],
            }
            for c in chunks
        ]

        # 5. Build / replace the FAISS index and persist
        self.vector_store.build(vectors, metadata)
        self.vector_store.save()

        # 6. Build BM25 keyword index in parallel
        chunk_ids = [f"{c['doc_id']}_{c['chunk_index']}" for c in chunks]
        self.bm25_retriever.build(texts, chunk_ids)
        bm25_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "bm25",
        )
        self.bm25_retriever.save(bm25_path)

        elapsed = time.time() - t0
        logger.info("Indexed %d chunks (dense + BM25) in %.2fs", chunk_count, elapsed)

        return {
            "docs_count": doc_count,
            "chunks_count": chunk_count,
            "indexed_count": chunk_count,
            "time_seconds": round(elapsed, 2),
        }

    def add_document(
        self,
        file_path: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        doc_id: str | None = None,
    ) -> dict[str, Any]:
        """Add a single document to the existing vector store.

        Parameters
        ----------
        file_path : str
            Absolute or relative path to the document (``.md`` or ``.txt``).
        chunk_size : int
            Maximum number of characters per chunk (default 500).
        chunk_overlap : int
            Overlap between consecutive chunks (default 50).
        doc_id : str, optional
            Override the auto-generated document ID.  When provided, this
            ID is used for artifact naming and vector store metadata,
            enabling consistent cleanup via ``remove_document()``.

        Returns
        -------
        dict
            ``{"chunks_count", "indexed", "doc_id"}``.
        """
        # 1. Load the single document
        doc = loader.load_file(file_path)
        doc_id = doc_id or doc["doc_id"]

        # 2. Chunk
        chunks = chunker.chunk_docs([doc], chunk_size, chunk_overlap)
        chunk_count = len(chunks)
        logger.info("Created %d chunk(s) for %s", chunk_count, file_path)

        if chunk_count == 0:
            return {"chunks_count": 0, "indexed": 0, "doc_id": doc_id}

        # 3. Embed
        texts = [c["content"] for c in chunks]
        vectors = embedding.embed(texts)

        # 4. Metadata
        metadata = [
            {
                "content": c["content"],
                "doc_id": c["doc_id"],
                "chunk_index": c["chunk_index"],
                "title": c["title"],
                "category": c["category"],
                "source_url": c["source_url"],
            }
            for c in chunks
        ]

        # 5. Incrementally add to the existing index and persist
        self.vector_store.add(vectors, metadata)
        self.vector_store.save()

        logger.info("Added %d chunk(s) (doc_id=%s)", chunk_count, doc_id)
        return {
            "chunks_count": chunk_count,
            "indexed": chunk_count,
            "doc_id": doc_id,
        }

    def rebuild_from_documents(self, documents: list[dict]) -> dict[str, Any]:
        """Rebuild the entire index from a list of document dicts (no file I/O).

        Clears existing artifacts and vector store, then rebuilds from scratch
        using the provided document data.  Each document is chunked, embedded,
        and added to a fresh FAISS + BM25 index.

        Parameters
        ----------
        documents : list[dict]
            Each dict must contain ``id``, ``title``, ``content``,
            ``category``, ``source_url``.

        Returns
        -------
        dict
            ``{"docs_count", "chunks_count", "indexed_count"}``.
        """
        t0 = time.time()

        # 1. Convert to the internal doc format expected by chunker
        docs = []
        for doc in documents:
            docs.append(
                {
                    "doc_id": str(doc["id"]),
                    "title": doc.get("title", ""),
                    "content": doc.get("content", ""),
                    "category": doc.get("category", ""),
                    "source_url": doc.get("source_url", ""),
                }
            )

        doc_count = len(docs)
        logger.info("Rebuilding index from %d document(s)", doc_count)

        # Always clear old artifacts + reset vector store + BM25 first
        import numpy as np
        from .artifact_store import ArtifactStore
        store = ArtifactStore()
        for existing_id in store.list_docs():
            store.delete_doc(existing_id)
        self.vector_store.build(
            np.empty((0, 512), dtype=np.float32), []
        )
        self.vector_store.save()
        self.bm25_retriever.build([], [])
        bm25_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "bm25"
        )
        self.bm25_retriever.save(bm25_dir)

        if doc_count == 0:
            return {"docs_count": 0, "chunks_count": 0, "indexed_count": 0}

        # 3. Chunk all documents
        chunks = chunker.chunk_docs(docs)
        chunk_count = len(chunks)
        logger.info("Created %d chunk(s)", chunk_count)

        # 4. Save per-document artifacts
        from collections import defaultdict

        doc_chunks_map: dict[str, list[dict]] = defaultdict(list)
        for c in chunks:
            doc_chunks_map[c["doc_id"]].append(c)

        for doc_id, doc_chunks_list in doc_chunks_map.items():
            doc_info = next((d for d in docs if d["doc_id"] == doc_id), {})
            store.save_doc(
                doc_id=doc_id,
                chunks=doc_chunks_list,
                title=doc_info.get("title", ""),
                category=doc_info.get("category", ""),
                source_url=doc_info.get("source_url", ""),
            )

        # 5. Embed all chunk texts in a single batch
        texts = [c["content"] for c in chunks]
        vectors = embedding.embed(texts)

        # 6. Build parallel metadata list
        metadata = [
            {
                "content": c["content"],
                "doc_id": c["doc_id"],
                "chunk_index": c["chunk_index"],
                "chunk_id": f"{c['doc_id']}_{c['chunk_index']}",
                "title": c["title"],
                "category": c["category"],
                "source_url": c["source_url"],
            }
            for c in chunks
        ]

        # 7. Build / replace the FAISS index and persist
        self.vector_store.build(vectors, metadata)
        self.vector_store.save()

        # 8. Build BM25 keyword index in parallel
        chunk_ids = [m["chunk_id"] for m in metadata]
        self.bm25_retriever.build(texts, chunk_ids)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bm25_path = os.path.join(base_dir, "data", "bm25")
        self.bm25_retriever.save(bm25_path)

        elapsed = time.time() - t0
        logger.info(
            "Rebuilt index from %d docs (%d chunks) in %.2fs",
            doc_count,
            chunk_count,
            elapsed,
        )

        return {
            "docs_count": doc_count,
            "chunks_count": chunk_count,
            "indexed_count": chunk_count,
        }

    # ------------------------------------------------------------------
    # Remove document
    # ------------------------------------------------------------------

    def remove_document(self, doc_id: str) -> dict[str, Any]:
        """Remove a document from the artifact store and vector index.

        Parameters
        ----------
        doc_id : str
            Document identifier (backend integer ID).

        Returns
        -------
        dict
            ``{"artifact_deleted": bool, "vectors_deleted": int}``.
        """
        from .artifact_store import ArtifactStore

        store = ArtifactStore()
        artifact_deleted = store.delete_doc(doc_id)

        vectors_deleted = self.vector_store.delete(doc_id)
        self.vector_store.save()

        logger.info(
            "Removed document %s (artifact=%s, vectors=%d)",
            doc_id,
            artifact_deleted,
            vectors_deleted,
        )
        return {
            "artifact_deleted": artifact_deleted,
            "vectors_deleted": vectors_deleted,
        }

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return combined pipeline and vector store statistics.

        Returns
        -------
        dict
            Top-level keys ``"pipeline"`` and ``"vector_store"``.
        """
        store_stats = self.vector_store.get_stats()
        return {
            "pipeline": {
                "retriever_ready": self.vector_store.index is not None,
                "default_top_k": 5,
                "default_min_score": 0.0,
                "bm25_ready": self.bm25_retriever.count > 0,
            },
            "vector_store": store_stats,
        }
