"""
BM25 keyword retriever using rank_bm25 with jieba Chinese tokenization.

Provides sparse (keyword-based) retrieval alongside the existing dense
(embedding-based) retriever.  Results are fused later in the pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from typing import Optional

import jieba
import numpy as np
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Retriever:
    """BM25 keyword retriever with jieba tokenization.

    Parameters
    ----------
    k1 : float
        BM25 k1 parameter (default 1.5).
    b : float
        BM25 b parameter (default 0.75).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self._k1 = k1
        self._b = b
        self._bm25: BM25Okapi | None = None
        self._chunk_ids: list[str] = []
        self._tokenized_corpus: list[list[str]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, corpus: list[str], chunk_ids: list[str]) -> None:
        """Build the BM25 index from a corpus of documents.

        Parameters
        ----------
        corpus : list[str]
            Raw document texts.
        chunk_ids : list[str]
            Parallel list of chunk identifiers, one per document.

        Raises
        ------
        ValueError
            If *corpus* and *chunk_ids* have different lengths.
        """
        if len(corpus) != len(chunk_ids):
            raise ValueError(
                f"corpus ({len(corpus)}) and chunk_ids ({len(chunk_ids)}) "
                "must have the same length"
            )

        self._chunk_ids = list(chunk_ids)
        self._tokenized_corpus = [self._tokenize(doc) for doc in corpus]

        if not self._tokenized_corpus:
            self._bm25 = None
            logger.info("Built BM25 index with 0 documents (empty corpus)")
            return

        self._bm25 = BM25Okapi(
            self._tokenized_corpus,
            k1=self._k1,
            b=self._b,
        )
        logger.info(
            "Built BM25 index with %d documents", len(self._tokenized_corpus)
        )

    def retrieve(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Retrieve the top-*k* most relevant chunks for *query*.

        Parameters
        ----------
        query : str
            The query string.
        top_k : int
            Number of results to return (default 5).

        Returns
        -------
        list[tuple[str, float]]
            List of ``(chunk_id, score)`` pairs, sorted descending by score.
        """
        if self._bm25 is None or not query or not query.strip():
            return []

        tokenized_query = self._tokenize(query)
        scores = self._bm25.get_scores(tokenized_query)

        # Get top-k indices
        top_n = min(top_k, len(scores))
        if top_n == 0:
            return []

        top_indices = np.argsort(scores)[::-1][:top_n]

        results = [
            (self._chunk_ids[int(idx)], float(scores[int(idx)]))
            for idx in top_indices
        ]
        return results

    def save(self, path: str) -> None:
        """Persist the BM25 index to disk.

        Parameters
        ----------
        path : str
            Directory path (will be created if it doesn't exist).
            Two files are written: ``{path}/bm25.pkl`` and
            ``{path}/meta.json``.
        """
        os.makedirs(path, exist_ok=True)

        # Save BM25 index via pickle (rank_bm25 objects are picklable)
        pkl_path = os.path.join(path, "bm25.pkl")
        with open(pkl_path, "wb") as f:
            pickle.dump(self._bm25, f)

        # Save metadata (chunk_ids, tokenized corpus, params)
        meta_path = os.path.join(path, "meta.json")
        meta = {
            "chunk_ids": self._chunk_ids,
            "tokenized_corpus": self._tokenized_corpus,
            "k1": self._k1,
            "b": self._b,
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)

        logger.info("Saved BM25 index to %s (%d docs)", path, self.count)

    def load(self, path: str) -> None:
        """Load a persisted BM25 index from disk.

        Parameters
        ----------
        path : str
            Directory path containing ``bm25.pkl`` and ``meta.json``.

        Raises
        ------
        FileNotFoundError
            If the directory or required files do not exist.
        """
        pkl_path = os.path.join(path, "bm25.pkl")
        meta_path = os.path.join(path, "meta.json")

        if not os.path.isdir(path):
            raise FileNotFoundError(f"BM25 index directory not found: {path}")
        if not os.path.isfile(pkl_path):
            raise FileNotFoundError(f"BM25 pickle not found: {pkl_path}")
        if not os.path.isfile(meta_path):
            raise FileNotFoundError(f"BM25 meta not found: {meta_path}")

        with open(pkl_path, "rb") as f:
            self._bm25 = pickle.load(f)

        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        self._chunk_ids = meta["chunk_ids"]
        self._tokenized_corpus = meta["tokenized_corpus"]

        logger.info(
            "Loaded BM25 index from %s (%d docs)", path, self.count
        )

    @property
    def count(self) -> int:
        """Return the number of indexed documents."""
        if self._bm25 is None:
            return 0
        return self._bm25.corpus_size

    # ------------------------------------------------------------------
    # Tokenization
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tokenize *text* into lower-cased tokens using jieba.

        For Chinese text, jieba performs accurate segmentation.
        For English text, tokens are lower-cased for consistency.

        Parameters
        ----------
        text : str
            Raw text to tokenize.

        Returns
        -------
        list[str]
            List of lower-cased tokens.
        """
        tokens = jieba.lcut(text)
        return [t.lower().strip() for t in tokens if t.strip()]
