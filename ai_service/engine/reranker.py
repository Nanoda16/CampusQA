"""
Cross-encoder reranker using ``BAAI/bge-reranker-base``.

Re-ranks a short list of candidate chunks by computing query-chunk relevance
scores with a cross-encoder, producing more accurate top results than a
bi-encoder (dense) retriever alone.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_NAME: str = "BAAI/bge-reranker-base"
"""Default HuggingFace model identifier for the cross-encoder."""


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------


class Reranker:
    """Cross-encoder reranker with lazy-loaded singleton model.

    The underlying ``CrossEncoder`` is cached as a class-level singleton so
    that multiple ``Reranker`` instances (or repeated calls) share the same
    model without redundant loading.

    Parameters
    ----------
    model_name : str, optional
        HuggingFace model identifier.  Defaults to ``BAAI/bge-reranker-base``.
    """

    _model = None
    """Class-level singleton cache for the CrossEncoder instance."""

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name

    # ------------------------------------------------------------------
    # Model loading (lazy singleton)
    # ------------------------------------------------------------------

    def _get_model(self):
        """Return the CrossEncoder singleton, loading on first call."""
        if Reranker._model is not None:
            return Reranker._model

        # Suppress verbose logging from underlying libraries
        logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
        logging.getLogger("transformers").setLevel(logging.WARNING)

        from sentence_transformers import CrossEncoder

        try:
            Reranker._model = CrossEncoder(
                self.model_name,
                device="cpu",
                max_length=512,  # safe default for BGE-reranker-base
            )
            logger.info("Loaded reranker model: %s", self.model_name)
        except Exception as exc:
            logger.error(
                "Failed to load reranker model '%s': %s", self.model_name, exc
            )
            Reranker._model = None
            raise

        return Reranker._model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rerank(
        self,
        query: str,
        candidates: list[tuple[str, str]],
        max_length: int = 256,
    ) -> list[tuple[str, float]]:
        """Re-rank candidate chunks by query-relevance.

        Parameters
        ----------
        query : str
            The user's query string.
        candidates : list of (chunk_id, text)
            Candidate chunks from the retriever.  Each element is a
            ``(chunk_id, text)`` pair.
        max_length : int
            Maximum token length for each input sequence (query + text).
            Texts longer than this are truncated automatically by the
            cross-encoder.  Default 256.

        Returns
        -------
        list of (chunk_id, rerank_score)
            Candidates sorted by descending relevance score.  When the model
            cannot be loaded, returns the **original order** with score 0.0
            for every candidate (graceful degradation).

        Notes
        -----
        The cross-encoder considers the query jointly with each candidate
        text, producing a relevance score in roughly ``[0, 1]`` (the exact
        range depends on the model's sigmoid output).
        """
        if not candidates:
            return []

        try:
            model = self._get_model()
        except Exception:
            # Graceful fallback: return original order with neutral scores
            logger.warning(
                "Reranker unavailable — returning candidates in original order"
            )
            return [(cid, 0.0) for cid, _ in candidates]

        # Build query–document pairs for the cross-encoder
        pairs = [(query, text) for _, text in candidates]

        try:
            scores = model.predict(pairs, batch_size=32)
        except Exception as exc:
            logger.error("Reranker inference failed: %s", exc)
            return [(cid, 0.0) for cid, _ in candidates]

        # Ensure scores is a flat 1-D array of floats
        scores = np.asarray(scores, dtype=np.float64).ravel()

        # Zip, sort descending by score
        ranked = list(zip([cid for cid, _ in candidates], scores))
        ranked.sort(key=lambda x: x[1], reverse=True)

        return ranked

    # ------------------------------------------------------------------
    # Convenience property
    # ------------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        """``True`` if the cross-encoder model has been loaded."""
        return Reranker._model is not None
