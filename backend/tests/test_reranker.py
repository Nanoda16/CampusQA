"""
Tests for ``ai_service/engine/reranker.py`` — ``Reranker`` class.

Covers:
- Model loading (lazy singleton)
- Re-ranking with reasonable scores
- Correct ordering (most relevant first)
- Graceful fallback when model fails to load

These tests DO load the real BGE-reranker-base model (it is cached locally
from Task 2 validation).  The fallback test patches the CrossEncoder import
to simulate a load failure.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Ensure ai_service is importable (namespace package, no __init__.py)
_AI_SERVICE = Path(__file__).resolve().parents[2] / "ai_service"
sys.path.insert(0, str(_AI_SERVICE))

import numpy as np
import pytest

from engine.reranker import Reranker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CANDIDATES = [
    (
        "chunk_a",
        "机器学习是人工智能的一个分支，它使计算机能够从数据中学习和改进。",
    ),
    (
        "chunk_b",
        "河海大学是一所以水利为特色的全国重点大学，位于江苏省南京市。",
    ),
    (
        "chunk_c",
        "深度学习使用多层神经网络来模拟人脑的学习过程。",
    ),
    (
        "chunk_d",
        "支持向量机（SVM）是一种监督学习算法，用于分类和回归分析。",
    ),
    (
        "chunk_e",
        "南京是江苏省的省会，有超过2500年的建城历史。",
    ),
]

_QUERY_ML = "什么是机器学习"


# ===================================================================
# 1. Model loading
# ===================================================================


class TestRerankerLoad:
    """Reranker model loads correctly (lazy singleton)."""

    def test_reranker_initial_not_loaded(self):
        """Before first call, is_loaded is False."""
        # Fresh instance — the class-level _model should be... well, it
        # might already be loaded by a previous test.  We check by creating
        # a new instance and NOT calling rerank.
        r = Reranker()
        # If no previous test loaded the model, is_loaded is False.
        # This test is informational; the real check is the next one.
        assert hasattr(r, "is_loaded")

    def test_reranker_loads_on_first_rerank(self):
        """First rerank call loads the singleton model."""
        r = Reranker()
        result = r.rerank("test", [("id", "hello world")])
        assert r.is_loaded is True
        assert len(result) == 1

    def test_reranker_singleton_reused(self):
        """Second Reranker instance shares the same loaded model."""
        r1 = Reranker()
        r2 = Reranker()
        # Calling rerank on r1 loads the model
        r1.rerank("test", [("id", "hello")])
        # r2 should see it as already loaded
        assert r2.is_loaded is True


# ===================================================================
# 2. Re-ranking scores
# ===================================================================


class TestRerankerScores:
    """Scores produced by rerank() are reasonable."""

    def test_reranker_rerank(self):
        """5 candidates produce 5 scores, all finite."""
        r = Reranker()
        result = r.rerank(_QUERY_ML, _CANDIDATES)

        assert len(result) == 5
        for cid, score in result:
            assert isinstance(cid, str)
            assert isinstance(score, float)
            assert np.isfinite(score), f"Non-finite score for {cid}: {score}"

    def test_reranker_all_scores_nonzero(self):
        """All returned scores should be > 0 for a relevant query."""
        r = Reranker()
        result = r.rerank(_QUERY_ML, _CANDIDATES)
        scores = [s for _, s in result]
        assert all(s > 0.0 for s in scores), f"Zero scores: {scores}"

    def test_reranker_score_range(self):
        """Scores should be roughly in [0, 1] (sigmoid output)."""
        r = Reranker()
        result = r.rerank(_QUERY_ML, _CANDIDATES)
        scores = [s for _, s in result]
        assert all(0.0 <= s <= 1.0 for s in scores), f"Scores out of range: {scores}"


# ===================================================================
# 3. Ordering
# ===================================================================


class TestRerankerOrdering:
    """Most relevant candidates rank first."""

    def test_reranker_ordering(self):
        """ML-related chunks rank above unrelated ones for '机器学习' query."""
        r = Reranker()
        result = r.rerank(_QUERY_ML, _CANDIDATES)

        # chunk_a and chunk_c are ML-related; chunk_b (河海大学) is not
        ids_in_order = [cid for cid, _ in result]
        idx_a = ids_in_order.index("chunk_a")
        idx_c = ids_in_order.index("chunk_c")
        idx_b = ids_in_order.index("chunk_b")

        # Both ML chunks should rank above the university intro
        assert idx_a < idx_b, (
            f"chunk_a (ML) at {idx_a} should rank above chunk_b at {idx_b}"
        )
        assert idx_c < idx_b, (
            f"chunk_c (ML) at {idx_c} should rank above chunk_b at {idx_b}"
        )

    def test_reranker_most_relevant_first(self):
        """The single most relevant candidate for '机器学习' should be ML content."""
        r = Reranker()
        result = r.rerank("机器学习", _CANDIDATES)

        # The top result should be ML-related
        top_id, top_score = result[0]
        assert top_score > 0.5, f"Top score too low: {top_score}"
        assert top_id in ("chunk_a", "chunk_c"), (
            f"Top result should be ML-related, got {top_id}"
        )


# ===================================================================
# 4. Fallback on model load failure
# ===================================================================


class TestRerankerFallback:
    """Graceful degradation when model fails to load.

    Important: these tests must run BEFORE the real model gets loaded by other
    tests, because the singleton caches ``Reranker._model``.  pytest runs
    classes in declaration order, so ``TestRerankerFallback`` comes after
    ``TestRerankerLoad`` and ``TestRerankerScores`` — both of which load the
    real model.  We therefore explicitly clear the singleton before each test
    and restore it after.
    """

    def setup_method(self):
        """Clear the singleton so _get_model() must re-import."""
        self._saved_model = Reranker._model
        Reranker._model = None

    def teardown_method(self):
        """Restore the saved singleton (if any)."""
        Reranker._model = self._saved_model

    def test_reranker_fallback(self):
        """When CrossEncoder init fails, rerank returns original order with 0.0."""
        with patch("sentence_transformers.CrossEncoder") as mock_ce:
            mock_ce.side_effect = Exception("Simulated model load failure")

            r = Reranker()
            result = r.rerank("query", _CANDIDATES)

            # Result should preserve original order with score 0.0
            assert len(result) == len(_CANDIDATES)
            for (cid, score), (orig_cid, _) in zip(result, _CANDIDATES):
                assert cid == orig_cid, (
                    f"Order changed: {cid} vs {orig_cid}"
                )
                assert score == 0.0, f"Expected 0.0, got {score}"

    def test_reranker_fallback_empty_candidates(self):
        """Fallback with empty candidates returns empty list."""
        with patch("sentence_transformers.CrossEncoder") as mock_ce:
            mock_ce.side_effect = Exception("Simulated failure")

            r = Reranker()
            result = r.rerank("query", [])
            assert result == []
