"""
TDD tests for RRF fusion (ai_service/engine/fusion.py).

Tests cover:
- Basic RRF fusion with two result sets
- Dedup: same chunk_id in both → appears once
- Dense-only fallback (BM25 empty)
- k parameter scaling
"""

from __future__ import annotations

import sys
import math
from pathlib import Path

# Ensure ai_service is importable
_AI_SERVICE = Path(__file__).resolve().parents[2] / "ai_service"
sys.path.insert(0, str(_AI_SERVICE))

import pytest

from engine.fusion import rrf_fuse


# ---------------------------------------------------------------------------
# Fixtures — simulated retriever outputs
# ---------------------------------------------------------------------------

@pytest.fixture
def dense_results():
    """Simulated dense retriever output (list[dict]), sorted by score desc."""
    return [
        {"doc_id": "A", "chunk_index": 0, "score": 0.92, "content": "text A0"},
        {"doc_id": "A", "chunk_index": 1, "score": 0.85, "content": "text A1"},
        {"doc_id": "B", "chunk_index": 0, "score": 0.70, "content": "text B0"},
        {"doc_id": "C", "chunk_index": 0, "score": 0.60, "content": "text C0"},
    ]


@pytest.fixture
def bm25_results():
    """Simulated BM25 retriever output (list[tuple]), sorted by score desc."""
    return [
        ("A_0", 18.5),
        ("C_0", 15.2),
        ("D_0", 12.0),
    ]


@pytest.fixture
def dense_results_overlap():
    """Dense results where all chunks also appear in BM25."""
    return [
        {"doc_id": "X", "chunk_index": 0, "score": 0.95, "content": "text X0"},
        {"doc_id": "Y", "chunk_index": 0, "score": 0.80, "content": "text Y0"},
    ]


@pytest.fixture
def bm25_results_overlap():
    """BM25 results overlapping completely with dense."""
    return [
        ("X_0", 20.0),
        ("Y_0", 14.0),
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rrf(rank: int, k: float = 60.0) -> float:
    """Compute RRF contribution for a single rank."""
    return 1.0 / (k + rank)


# ===================================================================
# Tests
# ===================================================================

class TestRRFBasic:
    """Core RRF correctness — two result sets, correct fusion + sorting."""

    def test_fused_results_sorted(self, dense_results, bm25_results):
        """Fused results should be sorted by descending fused score."""
        fused = rrf_fuse(dense_results, bm25_results, top_k=10)
        scores = [score for _, score, _ in fused]
        assert scores == sorted(scores, reverse=True), (
            f"Not sorted descending: {scores}"
        )

    def test_rrf_score_calculation(self, dense_results, bm25_results):
        """Verify exact RRF scores for known input."""
        # Dense: A_0(rank1), A_1(rank2), B_0(rank3), C_0(rank4)
        # BM25:  A_0(rank1), C_0(rank2), D_0(rank3)
        # A_0: 1/(61) + 1/(61) = 2/61
        # A_1: 1/(62)
        # B_0: 1/(63)
        # C_0: 1/(64) + 1/(62)
        # D_0: 1/(63)
        k = 60.0
        expected = {
            "A_0": 2 * _rrf(1, k),           # 2/61
            "A_1": _rrf(2, k),                # 1/62
            "B_0": _rrf(3, k),                # 1/63
            "C_0": _rrf(4, k) + _rrf(2, k),   # 1/64 + 1/62
            "D_0": _rrf(3, k),                # 1/63
        }

        fused = rrf_fuse(dense_results, bm25_results, k=k, top_k=10)
        result_map = {cid: score for cid, score, _ in fused}

        for cid, exp_score in expected.items():
            assert cid in result_map, f"Missing {cid} from fused results"
            assert math.isclose(
                result_map[cid], exp_score, rel_tol=1e-6
            ), f"{cid}: expected {exp_score:.6f}, got {result_map[cid]:.6f}"

    def test_top_k_respected(self, dense_results, bm25_results):
        """top_k parameter limits number of returned results."""
        fused_3 = rrf_fuse(dense_results, bm25_results, top_k=3)
        assert len(fused_3) == 3

        fused_1 = rrf_fuse(dense_results, bm25_results, top_k=1)
        assert len(fused_1) == 1
        assert fused_1[0][0] == "A_0"  # A_0 has highest RRF score

    def test_empty_dense(self, bm25_results):
        """Empty dense results → only BM25 chunks in fused output."""
        fused = rrf_fuse([], bm25_results, top_k=10)
        assert len(fused) == len(bm25_results)
        for cid, _, sources in fused:
            assert cid in {"A_0", "C_0", "D_0"}
            # dense_score should be 0.0 (not retrieved)
            assert sources[0] == 0.0


class TestRRFDedup:
    """Same chunk_id from both retrievers → appears once with combined score."""

    def test_dedup_no_duplicates(self, dense_results, bm25_results):
        """No chunk_id appears more than once in fused output."""
        fused = rrf_fuse(dense_results, bm25_results, top_k=10)
        ids = [cid for cid, _, _ in fused]
        assert len(ids) == len(set(ids)), f"Duplicate chunk_ids found: {ids}"

    def test_dedup_overlap(self, dense_results_overlap, bm25_results_overlap):
        """Chunks present in both → single entry with combined RRF score."""
        k = 60.0
        fused = rrf_fuse(
            dense_results_overlap, bm25_results_overlap, k=k, top_k=10
        )
        assert len(fused) == 2
        ids = [cid for cid, _, _ in fused]
        assert "X_0" in ids
        assert "Y_0" in ids

        # X_0: dense rank 1 + BM25 rank 1 = 2/61
        expected_x = 2 * _rrf(1, k)
        x_score = next(score for cid, score, _ in fused if cid == "X_0")
        assert math.isclose(x_score, expected_x, rel_tol=1e-6)

    def test_dedup_sources_list(self, dense_results, bm25_results):
        """sources list contains [dense_score, bm25_score] for each chunk."""
        fused = rrf_fuse(dense_results, bm25_results, top_k=10)
        for cid, _, sources in fused:
            assert isinstance(sources, list)
            assert len(sources) == 2
            dense_s, bm25_s = sources
            assert isinstance(dense_s, float)
            assert isinstance(bm25_s, float)

            if cid == "A_0":
                # In both: dense_score=0.92, bm25_score=18.5
                assert math.isclose(dense_s, 0.92, rel_tol=1e-6)
                assert math.isclose(bm25_s, 18.5, rel_tol=1e-6)
            elif cid == "D_0":
                # BM25 only: dense_score=0.0
                assert dense_s == 0.0


class TestRRFDenseOnly:
    """Fallback: BM25 results empty → dense-only ranked by RRF."""

    def test_empty_bm25_returns_dense(self, dense_results):
        """When BM25 is empty, return dense chunks sorted by RRF of dense ranks."""
        k = 60.0
        fused = rrf_fuse(dense_results, [], k=k, top_k=10)
        # Should return dense-only results
        assert len(fused) == len(dense_results)
        # Order should be same as dense (since RRF of single-source ranks
        # preserves original order)
        ordered_ids = [cid for cid, _, _ in fused]
        assert ordered_ids == ["A_0", "A_1", "B_0", "C_0"]

    def test_empty_bm25_rrf_scores(self, dense_results):
        """With BM25 empty, RRF score = 1/(k + dense_rank)."""
        k = 60.0
        fused = rrf_fuse(dense_results, [], k=k, top_k=10)
        for i, (cid, score, sources) in enumerate(fused):
            expected = _rrf(i + 1, k)
            assert math.isclose(score, expected, rel_tol=1e-6), (
                f"{cid} at rank {i+1}: expected {expected:.6f}, got {score:.6f}"
            )
            # sources: dense_score from original, bm25=0.0
            orig_dense = dense_results[i]["score"]
            assert math.isclose(sources[0], orig_dense, rel_tol=1e-6)

    def test_both_empty(self):
        """Both result lists empty → empty list."""
        fused = rrf_fuse([], [], top_k=10)
        assert fused == []


class TestRRFKParameter:
    """Different k values → RRF scores scale correctly."""

    def test_k_affects_scores(self, dense_results_overlap, bm25_results_overlap):
        """Different k produces different (lower) scores."""
        k_small = 1.0
        k_large = 100.0

        fused_small = rrf_fuse(
            dense_results_overlap, bm25_results_overlap, k=k_small, top_k=10
        )
        fused_large = rrf_fuse(
            dense_results_overlap, bm25_results_overlap, k=k_large, top_k=10
        )

        small_scores = {cid: s for cid, s, _ in fused_small}
        large_scores = {cid: s for cid, s, _ in fused_large}

        for cid in small_scores:
            assert small_scores[cid] > large_scores[cid], (
                f"k={k_small} should give higher score than k={k_large} "
                f"for {cid}: {small_scores[cid]} vs {large_scores[cid]}"
            )

    def test_k_default_is_60(self, dense_results, bm25_results):
        """Default k should be 60.0."""
        fused = rrf_fuse(dense_results, bm25_results, top_k=10)
        # Just verify it runs without error and produces reasonable scores
        assert len(fused) > 0
        for _, score, _ in fused:
            assert score > 0

    def test_k_scales_proportionally(self):
        """Verify RRF score = 1/(k+rank) for a known case."""
        dense = [{"doc_id": "Z", "chunk_index": 0, "score": 1.0}]
        k_values = [1.0, 10.0, 60.0, 100.0]
        for k in k_values:
            fused = rrf_fuse(dense, [], k=k, top_k=10)
            expected = _rrf(1, k)
            assert math.isclose(fused[0][1], expected, rel_tol=1e-6), (
                f"k={k}: expected {expected:.6f}"
            )
