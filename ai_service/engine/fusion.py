"""
RRF (Reciprocal Rank Fusion) for combining dense + BM25 retrieval results.

RRF formula (Cormack et al., TREC 2009)::

    score(d) = Σ  1 / (k + r_i(d))
               i

where *r_i(d)* is the rank of document *d* in system *i*'s results (1-indexed)
and *k* is a smoothing constant (default 60).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def rrf_fuse(
    dense_results: list[dict[str, Any]],
    bm25_results: list[tuple[str, float]],
    k: float = 60.0,
    top_k: int = 10,
) -> list[tuple[str, float, list[float]]]:
    """Fuse dense and BM25 retrieval results with Reciprocal Rank Fusion.

    Parameters
    ----------
    dense_results : list[dict]
        Dense retriever results, each dict containing at least ``doc_id``,
        ``chunk_index`` and ``score``.  Assumed sorted descending by score.
    bm25_results : list[tuple[str, float]]
        BM25 results as ``(chunk_id, score)`` pairs.
        Assumed sorted descending by score.
    k : float
        RRF smoothing constant (default 60.0).
    top_k : int
        Maximum number of fused results to return (default 10).

    Returns
    -------
    list[tuple[str, float, list[float]]]
        Top-*k* results, each as ``(chunk_id, fused_score, [dense_score,
        bm25_score])``, sorted descending by *fused_score*.

        *chunk_id* is the unique chunk identifier (``{doc_id}_{chunk_index}``).
        *fused_score* is the RRF score (sum of reciprocal ranks).
        The source list contains the **original** scores from each retriever
        (0.0 if a chunk was not returned by that retriever).

    Examples
    --------
    >>> dense = [{"doc_id": "A", "chunk_index": 0, "score": 0.9}]
    >>> bm25 = [("A_0", 15.0)]
    >>> rrf_fuse(dense, bm25, k=60.0, top_k=5)
    [('A_0', 0.03278688524590164, [0.9, 15.0])]
    """
    # ------------------------------------------------------------------
    # 1. Assign 1-indexed ranks for each system
    # ------------------------------------------------------------------
    # Dense: chunk_id -> (rank, original_score)
    dense_map: dict[str, tuple[int, float]] = {}
    for rank, d in enumerate(dense_results, start=1):
        chunk_id = _make_chunk_id(d)
        if chunk_id not in dense_map:
            dense_map[chunk_id] = (rank, d.get("score", 0.0))

    # BM25: chunk_id -> (rank, original_score)
    bm25_map: dict[str, tuple[int, float]] = {}
    for rank, (chunk_id, score) in enumerate(bm25_results, start=1):
        if chunk_id not in bm25_map:
            bm25_map[chunk_id] = (rank, score)

    # ------------------------------------------------------------------
    # 2. Compute RRF score for every unique chunk
    # ------------------------------------------------------------------
    all_chunk_ids: set[str] = set(dense_map.keys()) | set(bm25_map.keys())

    fused: list[tuple[str, float, list[float]]] = []
    for cid in all_chunk_ids:
        rrf_score = 0.0

        dense_rank, dense_orig = dense_map.get(cid, (None, 0.0))
        bm25_rank, bm25_orig = bm25_map.get(cid, (None, 0.0))

        if dense_rank is not None:
            rrf_score += 1.0 / (k + dense_rank)
        if bm25_rank is not None:
            rrf_score += 1.0 / (k + bm25_rank)

        sources: list[float] = [dense_orig, bm25_orig]
        fused.append((cid, rrf_score, sources))

    # ------------------------------------------------------------------
    # 3. Sort descending by fused_score; tie-break by dense original score
    # ------------------------------------------------------------------
    fused.sort(key=lambda x: (-x[1], -x[2][0]))

    return fused[:top_k]


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _make_chunk_id(d: dict[str, Any]) -> str:
    """Build ``{doc_id}_{chunk_index}`` from a dense result dict."""
    doc_id = d.get("doc_id", "")
    chunk_idx = d.get("chunk_index", 0)
    return f"{doc_id}_{chunk_idx}"
