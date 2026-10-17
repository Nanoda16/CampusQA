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
        self._recompute()

    def add_documents(self, corpus: list[str], chunk_ids: list[str]) -> None:
        """Append documents to the BM25 index.

        BM25 is a collection-level statistic — the IDF term depends on the
        whole corpus — so appending requires recomputing it.  The cached
        tokenizations are reused, which means only the newly added texts are
        segmented again by jieba.

        Chunk ids that already exist are dropped first, so re-processing a
        document replaces its previous chunks instead of duplicating them.

        Parameters
        ----------
        corpus : list[str]
            Raw texts of the new chunks.
        chunk_ids : list[str]
            Parallel list of chunk identifiers, one per text.

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
        if not corpus:
            return

        duplicates = set(chunk_ids) & set(self._chunk_ids)
        if duplicates:
            self._drop(duplicates)

        self._chunk_ids.extend(chunk_ids)
        self._tokenized_corpus.extend(self._tokenize(text) for text in corpus)
        self._recompute()

    def remove_documents(self, chunk_ids: list[str] | set[str]) -> int:
        """Drop documents from the BM25 index.

        Parameters
        ----------
        chunk_ids : list[str] | set[str]
            Chunk identifiers to remove.

        Returns
        -------
        int
            Number of indexed chunks that were actually removed.
        """
        return self._drop(set(chunk_ids))

    def _drop(self, chunk_ids: set[str]) -> int:
        """Remove *chunk_ids* from the inverted corpus and refresh BM25."""
        if not chunk_ids:
            return 0

        kept = [
            (cid, tokens)
            for cid, tokens in zip(self._chunk_ids, self._tokenized_corpus)
            if cid not in chunk_ids
        ]
        removed = len(self._chunk_ids) - len(kept)
        if removed:
            self._chunk_ids = [cid for cid, _ in kept]
            self._tokenized_corpus = [tokens for _, tokens in kept]
            self._recompute()
        return removed

    def _recompute(self) -> None:
        """Rebuild ``BM25Okapi`` statistics from the cached tokenizations."""
        if not self._tokenized_corpus:
            self._bm25 = None
            logger.info("BM25 index is empty")
            return

        self._bm25 = BM25Okapi(
            self._tokenized_corpus,
            k1=self._k1,
            b=self._b,
        )
        logger.info(
            "BM25 index now holds %d document(s)", len(self._tokenized_corpus)
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

        # ``argsort`` always returns *top_n* indices, even when every score is
        # exactly zero because the query shares no token with the corpus.  Those
        # hits carry no information and would otherwise pollute the RRF fusion,
        # so they are dropped here.
        #
        # Only *exactly* zero is dropped.  A very small corpus pushes the IDF
        # term negative (rank_bm25 replaces negative IDF with
        # ``epsilon * average_idf``, which stays negative when the average is
        # negative), so a plain ``> 0`` filter would make the very first
        # uploaded document impossible to find by keyword.
        top_indices = np.argsort(scores)[::-1][:top_n]

        results = [
            (self._chunk_ids[int(idx)], float(scores[int(idx)]))
            for idx in top_indices
            if scores[int(idx)] != 0.0
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
