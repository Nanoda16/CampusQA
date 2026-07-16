"""
Per-document artifact storage for the RAG engine.

Persists document chunks and metadata as individual JSON files inside
``data/artifacts/``.  Artifacts serve as the authoritative document store;
the FAISS and BM25 indices are derived from them via :meth:`rebuild_index`.

Thread safety for concurrent writes is provided by a ``threading.Lock``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class ArtifactStore:
    """Persist, load, and manage per-document JSON artifacts.

    Each document is stored as a single JSON file under *artifact_dir*,
    named ``{doc_id}.json``.

    Parameters
    ----------
    artifact_dir : str, optional
        Directory path for artifact files, relative to the ``ai_service/``
        package root.  Defaults to ``data/artifacts``.
    """

    def __init__(self, artifact_dir: str = "data/artifacts"):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._artifact_dir = os.path.join(base_dir, artifact_dir)
        self._lock = threading.Lock()

        os.makedirs(self._artifact_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_doc(
        self,
        doc_id: str,
        chunks: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
        title: str = "",
        category: str = "",
        source_url: str = "",
    ) -> str:
        """Save a document artifact to disk.

        Parameters
        ----------
        doc_id : str
            Unique document identifier (used as the file name).
        chunks : list[dict]
            Chunk dicts, each at least containing ``content`` and
            ``chunk_index``.  A ``vector_id`` is auto-generated as
            ``{doc_id}_{chunk_index}`` if not already present.
        metadata : dict, optional
            Optional document-level metadata (e.g. ``created_at``,
            ``doc_length``, ``chunk_count``).  ``chunk_count`` and
            ``doc_length`` are auto-populated when omitted.
        title : str
            Document title.
        category : str
            Document category.
        source_url : str
            Original source URL of the document.

        Returns
        -------
        str
            The absolute path to the written artifact file.
        """
        # Normalise chunks — ensure vector_id is present
        normalized_chunks = []
        doc_length = 0
        for c in chunks:
            chunk_index = c.get("chunk_index", 0)
            normalized_chunks.append(
                {
                    "content": c["content"],
                    "chunk_index": chunk_index,
                    "vector_id": c.get("vector_id", f"{doc_id}_{chunk_index}"),
                }
            )
            doc_length += len(c["content"])

        # Build optional metadata
        doc_meta = dict(metadata or {})
        doc_meta.setdefault("chunk_count", len(normalized_chunks))
        doc_meta.setdefault("doc_length", doc_length)
        doc_meta.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S"))

        artifact = {
            "doc_id": doc_id,
            "title": title,
            "category": category,
            "source_url": source_url,
            "chunks": normalized_chunks,
            "metadata": doc_meta,
        }

        path = os.path.join(self._artifact_dir, f"{doc_id}.json")
        with self._lock:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(artifact, f, ensure_ascii=False, indent=2)

        logger.debug("Saved artifact: %s (%d chunks)", path, len(normalized_chunks))
        return path

    def load_doc(self, doc_id: str) -> dict[str, Any] | None:
        """Load a document artifact from disk.

        Parameters
        ----------
        doc_id : str
            Document identifier (file name without ``.json``).

        Returns
        -------
        dict | None
            The artifact dict (same structure as saved), or ``None`` when
            the artifact does not exist.
        """
        path = os.path.join(self._artifact_dir, f"{doc_id}.json")
        if not os.path.isfile(path):
            return None

        with self._lock:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

    def delete_doc(self, doc_id: str) -> bool:
        """Delete a document artifact from disk.

        Parameters
        ----------
        doc_id : str
            Document identifier to remove.

        Returns
        -------
        bool
            ``True`` if the file was deleted, ``False`` if it did not exist.
        """
        path = os.path.join(self._artifact_dir, f"{doc_id}.json")
        if not os.path.isfile(path):
            return False

        with self._lock:
            os.remove(path)

        logger.debug("Deleted artifact: %s", path)
        return True

    def list_docs(self) -> list[str]:
        """List all stored document identifiers.

        Returns
        -------
        list[str]
            Sorted list of ``doc_id`` strings, one per artifact file.
        """
        if not os.path.isdir(self._artifact_dir):
            return []

        doc_ids: list[str] = []
        with self._lock:
            for name in os.listdir(self._artifact_dir):
                if name.endswith(".json"):
                    doc_ids.append(name[:-5])  # strip ".json"

        return sorted(doc_ids)

    def rebuild_index(self) -> dict[str, Any]:
        """Scan all artifacts and rebuild the FAISS + BM25 indices.

        Reads every artifact file, embeds all chunk texts, builds a fresh
        :class:`~engine.vector_store.VectorStore`, persists both the FAISS
        index and metadata, then rebuilds and persists the BM25 keyword
        index.

        Returns
        -------
        dict
            ``{"docs_count", "chunks_count", "time_seconds"}``.
            Returns zero counts when no artifacts exist.
        """
        t0 = time.time()
        doc_ids = self.list_docs()
        if not doc_ids:
            logger.info("No artifacts to rebuild from")
            return {"docs_count": 0, "chunks_count": 0, "time_seconds": 0.0}

        # 1. Collect all chunks with their document-level metadata
        all_chunks: list[dict[str, Any]] = []
        for doc_id in doc_ids:
            doc = self.load_doc(doc_id)
            if doc is None:
                continue
            for chunk in doc.get("chunks", []):
                all_chunks.append(
                    {
                        "content": chunk["content"],
                        "chunk_index": chunk["chunk_index"],
                        "doc_id": doc_id,
                        "title": doc.get("title", ""),
                        "category": doc.get("category", ""),
                        "source_url": doc.get("source_url", ""),
                    }
                )

        if not all_chunks:
            logger.info("No chunk data found in artifacts")
            return {"docs_count": len(doc_ids), "chunks_count": 0, "time_seconds": 0.0}

        texts = [c["content"] for c in all_chunks]

        # 2. Embed all texts
        from . import embedding

        vectors = embedding.embed(texts)

        # 3. Build parallel metadata list (matching VectorStore schema)
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
            for c in all_chunks
        ]

        # 4. Build / replace the FAISS index and persist
        from .vector_store import VectorStore

        vs = VectorStore()
        vs.build(vectors, metadata)
        vs.save()

        # 5. Build BM25 keyword index in parallel
        from .bm25_retriever import BM25Retriever

        chunk_ids = [m["chunk_id"] for m in metadata]
        bm25 = BM25Retriever()
        bm25.build(texts, chunk_ids)

        # BM25 save path: ai_service/data/bm25/
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bm25_path = os.path.join(base_dir, "data", "bm25")
        bm25.save(bm25_path)

        elapsed = time.time() - t0
        logger.info(
            "Rebuilt index from %d artifacts (%d chunks) in %.2fs",
            len(doc_ids),
            len(all_chunks),
            elapsed,
        )

        return {
            "docs_count": len(doc_ids),
            "chunks_count": len(all_chunks),
            "time_seconds": round(elapsed, 2),
        }
