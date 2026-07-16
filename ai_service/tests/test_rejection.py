"""
Tests for low-confidence OOD query rejection.

Covers:
- ``test_rejection_threshold_below``: score below threshold → rejection
- ``test_rejection_threshold_above``: score above threshold → normal path
- ``test_rejection_configurable``: env var changes threshold behaviour
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from engine.pipeline import RAGPipeline
from engine.retriever import Retriever

REJECTION_TEMPLATE = "根据现有校园知识库，暂未找到关于「{question}」的可靠信息。"


# ======================================================================
# Retriever-level tests
# ======================================================================


class TestRetrieverLowConfidence:
    """Tests for ``Retriever.low_confidence`` flag."""

    def test_low_confidence_below_default_threshold(self, mock_search):
        """Score 0.2 < 0.35 → ``low_confidence`` should be ``True``."""
        r = Retriever()
        mock_vs = mock_search([0.20, 0.15, 0.10])
        r._vector_store = mock_vs
        r._ensure_built = MagicMock()

        with patch("engine.retriever.embed_query", return_value=[[0.5, 0.3]]):
            results = r.retrieve("irrelevant query")

        assert r.low_confidence is True, "Top score 0.20 < 0.35 → low_confidence"
        assert len(results) == 3  # results are still returned

    def test_normal_confidence_above_default_threshold(self, mock_search):
        """Score 0.70 ≥ 0.35 → ``low_confidence`` should be ``False``."""
        r = Retriever()
        mock_vs = mock_search([0.70, 0.55, 0.40])
        r._vector_store = mock_vs
        r._ensure_built = MagicMock()

        with patch("engine.retriever.embed_query", return_value=[[0.5, 0.3]]):
            results = r.retrieve("normal query")

        assert r.low_confidence is False, "Top score 0.70 ≥ 0.35 → normal confidence"
        assert len(results) == 3

    def test_empty_results_not_low_confidence(self, mock_search):
        """Empty result list should NOT set ``low_confidence`` (handled separately)."""
        r = Retriever()
        mock_vs = mock_search([])
        r._vector_store = mock_vs
        r._ensure_built = MagicMock()

        with patch("engine.retriever.embed_query", return_value=[[0.5, 0.3]]):
            results = r.retrieve("query with no match")

        assert r.low_confidence is False, "Empty results ≠ low confidence"
        assert len(results) == 0

    def test_tie_at_threshold_is_acceptable(self, mock_search):
        """Score exactly at threshold (0.35) should be acceptable, not rejected."""
        r = Retriever(rejection_threshold=0.35)
        mock_vs = mock_search([0.35, 0.20, 0.10])
        r._vector_store = mock_vs
        r._ensure_built = MagicMock()

        with patch("engine.retriever.embed_query", return_value=[[0.5, 0.3]]):
            r.retrieve("boundary query")

        assert r.low_confidence is False, "Score == threshold → acceptable"

    def test_configurable_threshold_from_env(self, mock_search, monkeypatch):
        """Setting ``REJECTION_THRESHOLD`` env var should change behaviour."""
        monkeypatch.setenv("REJECTION_THRESHOLD", "0.50")

        r = Retriever()  # reads from env
        mock_vs = mock_search([0.40, 0.30, 0.20])
        r._vector_store = mock_vs
        r._ensure_built = MagicMock()

        with patch("engine.retriever.embed_query", return_value=[[0.5, 0.3]]):
            r.retrieve("query for env test")

        assert r.low_confidence is True, "0.40 < 0.50 (from env) → low_confidence"

    def test_explicit_threshold_overrides_env(self, mock_search, monkeypatch):
        """Constructor argument should take precedence over env var."""
        monkeypatch.setenv("REJECTION_THRESHOLD", "0.10")  # very permissive

        r = Retriever(rejection_threshold=0.50)  # explicit
        mock_vs = mock_search([0.30, 0.20])
        r._vector_store = mock_vs
        r._ensure_built = MagicMock()

        with patch("engine.retriever.embed_query", return_value=[[0.5, 0.3]]):
            r.retrieve("explicit threshold test")

        assert r.low_confidence is True, "0.30 < 0.50 (explicit) → low_confidence"


# ======================================================================
# Pipeline-level tests
# ======================================================================


class TestPipelineRejection:
    """Tests that the pipeline short-circuits to the rejection template."""

    def test_pipeline_returns_rejection_when_low_confidence(self):
        """When retriever reports low confidence, pipeline returns rejection."""
        retriever = MagicMock(spec=Retriever)
        retriever.low_confidence = True
        # return dummy results so pipeline doesn't hit the empty-chunks branch
        retriever.retrieve.return_value = [
            {"content": "dummy", "title": "dummy", "score": 0.15},
        ]

        pipeline = RAGPipeline(retriever=retriever)
        result = pipeline.run(query="什么是永动机？")

        assert result["answer"] == REJECTION_TEMPLATE.format(question="什么是永动机？")
        assert result["sources"] == []
        retriever.retrieve.assert_called_once()

    def test_pipeline_normal_path_when_not_low_confidence(self):
        """When confidence is fine, pipeline proceeds to generation."""
        retriever = MagicMock(spec=Retriever)
        retriever.low_confidence = False
        retriever.retrieve.return_value = [
            {"content": "河海大学是一所水利名校", "title": "学校简介", "score": 0.75},
        ]

        generator = MagicMock()
        generator.generate.return_value = "河海大学是一所水利名校。"

        pipeline = RAGPipeline(retriever=retriever, generator=generator)
        result = pipeline.run(query="介绍一下河海大学")

        assert "error" not in result.get("answer", "").lower()
        assert generator.generate.called, "Generator should have been called"


# ======================================================================
# Endpoint-level test (optional smoke test)
# ======================================================================


def test_env_var_makes_all_queries_low_confidence(monkeypatch):
    """With REJECTION_THRESHOLD=0.99, a query with score 0.3 should be rejected."""
    monkeypatch.setenv("REJECTION_THRESHOLD", "0.99")

    r = Retriever()  # reads threshold=0.99 from env
    mock_vs = MagicMock()
    mock_vs.search.return_value = [
        {"content": "some info", "doc_id": "d1", "title": "T", "category": "c",
         "source_url": "u", "score": 0.30, "chunk_index": 0},
    ]
    r._vector_store = mock_vs
    r._ensure_built = MagicMock()

    with patch("engine.retriever.embed_query", return_value=[[0.5, 0.3]]):
        r.retrieve("anything")

    assert r.low_confidence is True, "0.30 < 0.99 → rejected"
