"""
Retriever for the RAG engine.

Wraps the VectorStore with query-embedding logic and scoring thresholds.
"""

import logging
import os
from typing import Optional

import numpy as np

from .embedding import embed, embed_query
from .vector_store import VectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default / env-based rejection threshold
# ---------------------------------------------------------------------------

_REJECTION_THRESHOLD_DEFAULT = 0.35


def _get_rejection_threshold() -> float:
    """Read ``REJECTION_THRESHOLD`` from the environment, fall back to 0.35.

    Returns
    -------
    float
        The threshold value.
    """
    raw = os.environ.get("REJECTION_THRESHOLD", str(_REJECTION_THRESHOLD_DEFAULT))
    try:
        return float(raw)
    except (ValueError, TypeError):
        return _REJECTION_THRESHOLD_DEFAULT


class Retriever:
    """Simple Top-K retriever backed by a VectorStore.

    Parameters
    ----------
    vector_store : VectorStore, optional
        An existing VectorStore instance. If ``None``, a new one is created
        (which auto-loads from disk if persisted files exist).
    rejection_threshold : float, optional
        Minimum top-1 similarity score for accepting retrieval results.
        Queries whose best score falls below this threshold are marked as
        low-confidence (``self.low_confidence = True``).
        Falls back to the ``REJECTION_THRESHOLD`` env var, then 0.35.
    """

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        rejection_threshold: Optional[float] = None,
    ):
        self._vector_store = vector_store or VectorStore()
        self.rejection_threshold = (
            rejection_threshold
            if rejection_threshold is not None
            else _get_rejection_threshold()
        )
        self.low_confidence: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[dict]:
        """Embed *query* and return the top-*k* most similar documents.

        Parameters
        ----------
        query : str
            The query string.
        top_k : int
            Number of nearest neighbours to return (default 5).
        min_score : float
            Minimum similarity score threshold (default 0.0).
            Results with ``score <= min_score`` are excluded.

        Returns
        -------
        list[dict]
            Each result contains *content*, *doc_id*, *title*, *category*,
            *source_url*, *score*, and *chunk_index*.
            Empty list when the knowledge base has not been built yet.
        """
        if not query or not query.strip():
            return []

        if not self._is_ready():
            # Empty knowledge base — nothing to retrieve yet.  Returning an
            # empty list lets the caller answer "未找到相关校园信息" instead of
            # surfacing a 500 on a freshly installed instance.
            self.low_confidence = False
            return []

        query_vec = embed_query(query)                     # (1, dim)
        results = self._vector_store.search(query_vec, top_k)

        if min_score > 0.0:
            results = [r for r in results if r["score"] > min_score]

        # Low-confidence check: if the best score is below the threshold,
        # mark this query as potentially out-of-distribution.
        self.low_confidence = bool(
            results
            and results[0]["score"] < self.rejection_threshold
        )
        if self.low_confidence:
            logger.info(
                "Low confidence for query=%r (top_score=%.4f < threshold=%.4f)",
                query[:60],
                results[0]["score"],
                self.rejection_threshold,
            )

        return results

    def batch_retrieve(
        self,
        queries: list[str],
        top_k: int = 5,
    ) -> list[list[dict]]:
        """Retrieve results for multiple queries at once.

        All valid (non-empty) queries are embedded in a single batch call
        for efficiency.  Empty queries produce an empty result list.

        Parameters
        ----------
        queries : list[str]
            List of query strings.
        top_k : int
            Number of results per query (default 5).

        Returns
        -------
        list[list[dict]]
            Outer list corresponds to each query; inner lists contain result
            dicts.  Every inner list is empty when the knowledge base has not
            been built yet.
        """
        if not queries:
            return []

        if not self._is_ready():
            return [[] for _ in queries]

        # Separate valid queries from blank ones while tracking positions
        valid_indices: list[int] = []
        valid_texts: list[str] = []
        for i, q in enumerate(queries):
            if q and q.strip():
                valid_indices.append(i)
                valid_texts.append(q)

        if not valid_texts:
            return [[] for _ in queries]

        # Batch embed all valid queries at once
        query_vectors = embed(valid_texts)  # (n_valid, dim)

        # Search each query vector
        result_lists: list[list[dict]] = [[] for _ in queries]
        for pos, idx in enumerate(valid_indices):
            q_vec = query_vectors[pos : pos + 1]  # keep 2-D
            result_lists[idx] = self._vector_store.search(q_vec, top_k)

        return result_lists

    def get_params(self) -> dict:
        """Return default retrieval parameters.

        Returns
        -------
        dict
            Keys: *top_k*, *min_score*.
        """
        return {
            "top_k": 5,
            "min_score": 0.0,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_ready(self) -> bool:
        """True when the vector index exists and holds at least one vector.

        An unbuilt index is a legitimate state — a fresh install has an empty
        knowledge base until the user uploads something — so callers must get
        an empty result rather than an exception that the HTTP layer turns into
        a 500.
        """
        index = self._vector_store.index
        return index is not None and index.ntotal > 0
