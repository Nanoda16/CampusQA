"""
TDD tests for BM25 keyword retriever (ai_service/engine/bm25_retriever.py).

Tests cover:
- Building BM25 index from tokenized documents
- Keyword retrieval returns correct chunk_id
- Save/load round-trip preserves results
- Chinese jieba tokenization correctness
"""

from __future__ import annotations

import sys
import json
import tempfile
import os
from pathlib import Path

# Ensure ai_service is importable
_AI_SERVICE = Path(__file__).resolve().parents[2] / "ai_service"
sys.path.insert(0, str(_AI_SERVICE))

import pytest

from engine.bm25_retriever import BM25Retriever


# ---------------------------------------------------------------------------
# Fictitious test corpus (mix of Chinese and English)
# ---------------------------------------------------------------------------

CORPUS = [
    "河海大学计算机学院位于南京市鼓楼区",
    "河海大学水利工程专业在全国排名前列",
    "南京大学计算机科学系在仙林校区",
    "东南大学土木工程学院在九龙湖校区",
    "This is an English document about water resources management",
    "人工智能与机器学习是计算机科学的重要分支",
]

CHUNK_IDS = [
    "doc1_chunk0",
    "doc1_chunk1",
    "doc2_chunk0",
    "doc3_chunk0",
    "doc4_chunk0",
    "doc5_chunk0",
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBM25Build:
    """Building the BM25 index from tokenized documents."""

    def test_bm25_build_creates_index(self):
        """Building index should succeed and count > 0."""
        retriever = BM25Retriever()
        retriever.build(CORPUS, CHUNK_IDS)
        assert retriever.count > 0
        assert retriever.count == len(CORPUS)

    def test_bm25_build_with_empty_corpus(self):
        """Building with empty corpus should result in count == 0."""
        retriever = BM25Retriever()
        retriever.build([], [])
        assert retriever.count == 0

    def test_bm25_build_mismatched_lengths(self):
        """Mismatched corpus and chunk_ids should raise ValueError."""
        retriever = BM25Retriever()
        with pytest.raises(ValueError, match="must have the same length"):
            retriever.build(CORPUS, ["only_one"])

    def test_bm25_build_tokenizes(self):
        """After build, internal tokenized corpus should be populated."""
        retriever = BM25Retriever()
        retriever.build(CORPUS, CHUNK_IDS)
        assert len(retriever._tokenized_corpus) == len(CORPUS)
        # Each entry should be a list of tokens
        for tokens in retriever._tokenized_corpus:
            assert isinstance(tokens, list)
            assert len(tokens) > 0


class TestBM25Retrieve:
    """Keyword retrieval returns correct chunk_ids."""

    def test_bm25_retrieve_chinese_keyword(self):
        """Chinese keyword query should return the correct chunk."""
        retriever = BM25Retriever()
        retriever.build(CORPUS, CHUNK_IDS)
        results = retriever.retrieve("计算机学院", top_k=3)
        assert len(results) > 0
        # First result should be the most relevant
        top_chunk_id = results[0][0]
        assert top_chunk_id == "doc1_chunk0", (
            f"Expected doc1_chunk0 for '计算机学院', got {top_chunk_id}"
        )

    def test_bm25_retrieve_english_keyword(self):
        """English keyword query should return the correct chunk."""
        retriever = BM25Retriever()
        retriever.build(CORPUS, CHUNK_IDS)
        results = retriever.retrieve("water resources", top_k=3)
        assert len(results) > 0
        top_chunk_id = results[0][0]
        assert top_chunk_id == "doc4_chunk0", (
            f"Expected doc4_chunk0 for 'water resources', got {top_chunk_id}"
        )

    def test_bm25_retrieve_top_k_respected(self):
        """top_k parameter should limit the number of results."""
        retriever = BM25Retriever()
        retriever.build(CORPUS, CHUNK_IDS)
        results = retriever.retrieve("计算机", top_k=2)
        assert len(results) <= 2

    def test_bm25_retrieve_empty_query(self):
        """Empty query should return empty list."""
        retriever = BM25Retriever()
        retriever.build(CORPUS, CHUNK_IDS)
        results = retriever.retrieve("", top_k=3)
        assert results == []

    def test_bm25_retrieve_no_match(self):
        """Query with no matching terms should still return results (BM25
        always returns top_k, but with very low scores)."""
        retriever = BM25Retriever()
        retriever.build(CORPUS, CHUNK_IDS)
        results = retriever.retrieve("zzzzzxyznonexistent", top_k=3)
        # BM25Okapi always returns top_k results even for out-of-vocab queries
        assert len(results) <= 3
        # All scores should be 0.0 for OOV query
        for _, score in results:
            assert score == 0.0

    def test_bm25_retrieve_scores_descending(self):
        """Results should be sorted by score in descending order."""
        retriever = BM25Retriever()
        retriever.build(CORPUS, CHUNK_IDS)
        results = retriever.retrieve("计算机", top_k=5)
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True), (
            "Scores should be in descending order"
        )


class TestBM25SaveLoad:
    """Save/load round-trip preserves results."""

    def test_bm25_save_load_round_trip(self, tmp_path):
        """After save then load, retrieval results should match."""
        # Build and save
        retriever = BM25Retriever()
        retriever.build(CORPUS, CHUNK_IDS)
        save_path = str(tmp_path / "bm25_index")
        retriever.save(save_path)

        # Load into a new instance
        loaded = BM25Retriever()
        loaded.load(save_path)
        assert loaded.count == len(CORPUS)

        # Check retrieval results match
        orig_results = retriever.retrieve("计算机学院", top_k=3)
        loaded_results = loaded.retrieve("计算机学院", top_k=3)
        assert orig_results == loaded_results

    def test_bm25_save_load_preserves_chunk_ids(self, tmp_path):
        """Chunk ID mapping should be preserved after save/load."""
        retriever = BM25Retriever()
        retriever.build(CORPUS, CHUNK_IDS)
        save_path = str(tmp_path / "bm25_index")
        retriever.save(save_path)

        loaded = BM25Retriever()
        loaded.load(save_path)
        assert loaded._chunk_ids == CHUNK_IDS

    def test_bm25_load_nonexistent_path(self):
        """Loading from a nonexistent path should raise FileNotFoundError."""
        retriever = BM25Retriever()
        with pytest.raises(FileNotFoundError):
            retriever.load("/nonexistent/path/bm25_index")

    def test_bm25_count_property(self):
        """Count property should reflect number of indexed documents."""
        retriever = BM25Retriever()
        assert retriever.count == 0
        retriever.build(CORPUS, CHUNK_IDS)
        assert retriever.count == len(CORPUS)


class TestBM25JiebaTokenization:
    """Chinese jieba tokenization correctness."""

    def test_jieba_segments_chinese_correctly(self):
        """Jieba should correctly segment Chinese academic text."""
        retriever = BM25Retriever()
        tokens = retriever._tokenize("河海大学计算机学院")
        assert "河海大学" in tokens
        assert "计算机" in tokens
        assert "学院" in tokens

    def test_jieba_handles_mixed_text(self):
        """Jieba should handle mixed Chinese/English text."""
        retriever = BM25Retriever()
        tokens = retriever._tokenize("AI for Water 学术联盟")
        # English tokens are preserved
        assert "ai" in tokens or "AI" in tokens
        assert "water" in tokens or "Water" in tokens
        # Chinese tokens should be segmented
        assert "学术" in tokens
        assert "联盟" in tokens

    def test_jieba_returns_lowercase_tokens(self):
        """Jieba tokenizer should return lowercase tokens for consistency."""
        retriever = BM25Retriever()
        tokens = retriever._tokenize("Hello World 河海大学")
        for t in tokens:
            assert t == t.lower(), f"Token '{t}' is not lowercase"
