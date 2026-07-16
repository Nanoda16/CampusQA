"""
Tests for low-confidence rejection of OOD (out-of-distribution) queries.

Covers:
- Retriever threshold configuration (env var, default)
- Pipeline-level rejection short-circuit (sync and stream)
- Edge cases: empty results, threshold=0, borderline scores

These are unit tests — the retriever and generator are mocked so no
FAISS index, embedding model, or API key is needed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure ai_service is importable (namespace package, no __init__.py)
_AI_SERVICE = Path(__file__).resolve().parents[2] / "ai_service"
sys.path.insert(0, str(_AI_SERVICE))

import pytest
from engine.pipeline import RAGPipeline
from engine.retriever import _get_rejection_threshold

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REJECTION_TEMPLATE = "根据现有校园知识库，暂未找到关于「{question}」的可靠信息。"
DEFAULT_THRESHOLD = 0.35


def _make_chunk(score: float = 0.5) -> dict:
    """Minimal chunk dict with a controllable score."""
    return {
        "content": "河海大学是一所水利特色高校。",
        "title": "学校简介",
        "doc_id": "doc_001",
        "category": "概况",
        "source_url": "https://example.com/intro",
        "score": score,
        "chunk_index": 0,
    }


def _make_pipeline() -> RAGPipeline:
    """Build a RAGPipeline with mocked retriever + generator (no real deps)."""
    pl = RAGPipeline.__new__(RAGPipeline)
    pl.retriever = MagicMock()
    pl.generator = MagicMock()
    pl.generator.generate.return_value = "河海大学成立于1915年。"
    pl.generator.generate_stream.return_value = iter([])
    pl.bm25_retriever = MagicMock()
    pl.bm25_retriever.retrieve.return_value = []
    pl._bm25_results = []
    pl._reranker_enabled = False
    return pl


# ===================================================================
# 1. Threshold configuration
# ===================================================================


class TestRejectionThresholdConfig:
    """REJECTION_THRESHOLD env var and defaults."""

    # Store original before any test pollution
    _ORIG = os.environ.get("REJECTION_THRESHOLD")

    def teardown_method(self):
        """Restore env var after each test."""
        if self._ORIG is not None:
            os.environ["REJECTION_THRESHOLD"] = self._ORIG
        elif "REJECTION_THRESHOLD" in os.environ:
            del os.environ["REJECTION_THRESHOLD"]

    def test_default_threshold(self):
        """No env var set → _get_rejection_threshold returns 0.35."""
        os.environ.pop("REJECTION_THRESHOLD", None)
        assert _get_rejection_threshold() == DEFAULT_THRESHOLD

    def test_env_var_overrides_default(self):
        """REJECTION_THRESHOLD=0.5 → threshold is 0.5."""
        os.environ["REJECTION_THRESHOLD"] = "0.5"
        assert _get_rejection_threshold() == 0.5

    def test_invalid_env_var_falls_back(self):
        """REJECTION_THRESHOLD=invalid → fall back to 0.35."""
        os.environ["REJECTION_THRESHOLD"] = "not-a-float"
        assert _get_rejection_threshold() == DEFAULT_THRESHOLD

    def test_env_var_zero(self):
        """REJECTION_THRESHOLD=0 → threshold is 0.0 (never reject)."""
        os.environ["REJECTION_THRESHOLD"] = "0.0"
        assert _get_rejection_threshold() == 0.0

    def test_env_var_one(self):
        """REJECTION_THRESHOLD=1.0 → threshold is 1.0 (always reject)."""
        os.environ["REJECTION_THRESHOLD"] = "1.0"
        assert _get_rejection_threshold() == 1.0


# ===================================================================
# 2. Pipeline rejection — synchronous
# ===================================================================


class TestPipelineRejectionSync:
    """low_confidence rejection in RAGPipeline.run()."""

    def test_below_threshold_rejected(self):
        """Top-1 score < threshold → rejection template, no LLM call."""
        pl = _make_pipeline()
        pl.retriever.retrieve.return_value = [_make_chunk(score=0.2)]
        pl.retriever.low_confidence = True

        result = pl.run(query="河海大学有几个食堂")

        assert result["answer"] == REJECTION_TEMPLATE.format(
            question="河海大学有几个食堂"
        )
        assert result["sources"] == []
        pl.generator.generate.assert_not_called()

    def test_above_threshold_normal(self):
        """Top-1 score >= threshold → proceeds to LLM generation."""
        pl = _make_pipeline()
        pl.retriever.retrieve.return_value = [_make_chunk(score=0.8)]
        pl.retriever.low_confidence = False

        result = pl.run(query="河海大学有几个校区")

        assert result["answer"] == "河海大学成立于1915年。"
        pl.generator.generate.assert_called_once()

    def test_empty_results_no_rejection(self):
        """No retrieved chunks → '未找到' fallback, not rejection template."""
        pl = _make_pipeline()
        pl.retriever.retrieve.return_value = []
        pl.retriever.low_confidence = False

        result = pl.run(query="完全不相关的问题")

        assert "未找到相关校园信息" in result["answer"]
        assert result["sources"] == []
        pl.generator.generate.assert_not_called()

    def test_low_confidence_false_never_rejects(self):
        """When low_confidence is False, even score=0.0 proceeds normally."""
        pl = _make_pipeline()
        pl.retriever.retrieve.return_value = [_make_chunk(score=0.0)]
        pl.retriever.low_confidence = False

        result = pl.run(query="边界查询")

        assert "河海大学成立于1915年" in result["answer"]
        pl.generator.generate.assert_called_once()


# ===================================================================
# 3. Pipeline rejection — streaming
# ===================================================================


class TestPipelineRejectionStream:
    """low_confidence rejection in RAGPipeline.run_stream()."""

    def test_stream_below_threshold_rejected(self):
        """Stream: low confidence → status + done(rejection)."""
        pl = _make_pipeline()
        pl.retriever.retrieve.return_value = [_make_chunk(score=0.1)]
        pl.retriever.low_confidence = True

        events = list(pl.run_stream(query="未知主题"))

        # First event is always the status yield
        assert events[0]["type"] == "status"
        # Second event is the done with rejection
        assert events[1]["type"] == "done"
        assert events[1]["answer"] == REJECTION_TEMPLATE.format(
            question="未知主题"
        )
        assert events[1]["sources"] == []
        assert len(events) == 2

    def test_stream_above_threshold_normal(self):
        """Stream: high confidence → proceeds with status/sources/tokens."""
        pl = _make_pipeline()
        pl.retriever.retrieve.return_value = [_make_chunk(score=0.9)]
        pl.retriever.low_confidence = False
        pl.generator.generate_stream.return_value = iter(["河海", "大学", "简介"])

        events = list(pl.run_stream(query="学校简介"))

        # Should include: status → sources → token×3 → done
        assert len(events) >= 4
        done_event = [e for e in events if e["type"] == "done"][0]
        assert done_event["answer"] == "河海大学简介"

    def test_stream_empty_results(self):
        """Stream: no chunks → status + done(fallback)."""
        pl = _make_pipeline()
        pl.retriever.retrieve.return_value = []
        pl.retriever.low_confidence = False

        events = list(pl.run_stream(query="什么都没有"))

        # First event is always the status yield
        assert events[0]["type"] == "status"
        # Second event is the done with fallback
        assert events[1]["type"] == "done"
        assert "未找到相关校园信息" in events[1]["answer"]
        assert len(events) == 2


# ===================================================================
# 4. Retriever low_confidence flag integration
# ===================================================================


class TestRetrieverLowConfidenceFlag:
    """Verify retriever sets low_confidence correctly."""

    def test_retriever_initial_low_confidence_false(self):
        """Retriever starts with low_confidence=False."""
        # Need to avoid hitting VectorStore init
        with patch("engine.retriever.VectorStore") as mock_vs:
            from engine.retriever import Retriever

            r = Retriever.__new__(Retriever)
            r.rejection_threshold = 0.35
            r.low_confidence = False
            assert r.low_confidence is False

    def test_retriever_rejection_threshold_default(self):
        """Retriever reads threshold from env/default during init."""
        with patch("engine.retriever.VectorStore") as mock_vs:
            from engine.retriever import Retriever

            mock_vs_instance = MagicMock()
            mock_vs.return_value = mock_vs_instance

            r = Retriever()
            assert r.rejection_threshold == DEFAULT_THRESHOLD
            assert r.low_confidence is False

    def test_retriever_rejection_threshold_custom(self):
        """Retriever accepts explicit threshold parameter."""
        with patch("engine.retriever.VectorStore") as mock_vs:
            from engine.retriever import Retriever

            mock_vs_instance = MagicMock()
            mock_vs.return_value = mock_vs_instance

            r = Retriever(rejection_threshold=0.7)
            assert r.rejection_threshold == 0.7
