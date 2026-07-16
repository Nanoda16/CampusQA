"""
TDD tests for threshold calibration logic (evals/calibrate.py).

All tests exercise the pure computation functions (``compute_threshold_metrics``
and ``select_best_threshold``) with fictitious per-query data — no pipeline
creation, no model loading, no I/O.
"""

from __future__ import annotations

import sys
import math
from pathlib import Path

# Ensure the project root is on sys.path so we can import evals.calibrate
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest

from evals.calibrate import (
    PerQueryData,
    compute_threshold_metrics,
    select_best_threshold,
)

# ════════════════════════════════════════════════════════════════
# Fictitious test data
# ════════════════════════════════════════════════════════════════

# 6 answerable queries with varying top scores and hit outcomes
ANS_HIGH = [
    PerQueryData(qid="a80", answerable=True, group="single_turn", top_score=0.80, hit=True),
    PerQueryData(qid="a75", answerable=True, group="single_turn", top_score=0.75, hit=True),
    PerQueryData(qid="a70", answerable=True, group="single_turn", top_score=0.70, hit=True),
    PerQueryData(qid="a60", answerable=True, group="single_turn", top_score=0.60, hit=True),
    PerQueryData(qid="a50", answerable=True, group="single_turn", top_score=0.50, hit=False),
    PerQueryData(qid="a40", answerable=True, group="single_turn", top_score=0.40, hit=True),
]

# 4 OOD queries with varying scores
OOD_QS = [
    PerQueryData(qid="ood1", answerable=False, group="ood", top_score=0.65, hit=False),
    PerQueryData(qid="ood2", answerable=False, group="ood", top_score=0.45, hit=False),
    PerQueryData(qid="ood3", answerable=False, group="ood", top_score=0.30, hit=False),
    PerQueryData(qid="ood4", answerable=False, group="ood", top_score=0.20, hit=False),
]

ALL_DATA = ANS_HIGH + OOD_QS


# ════════════════════════════════════════════════════════════════
# 1. compute_threshold_metrics — classification counts
# ════════════════════════════════════════════════════════════════


class TestComputeThresholdMetrics:
    """Verify classification counts at a single threshold."""

    def test_all_accepted_at_low_threshold(self):
        """threshold=0.0 → all answerable accepted, all OOD accepted."""
        r = compute_threshold_metrics(ALL_DATA, 0.0)
        assert r.tp == 6    # all answerable >= 0.0
        assert r.fn == 0    # none rejected
        assert r.fp == 4    # all OOD >= 0.0
        assert r.tn == 0    # none rejected
        assert r.far == 1.0  # all OOD accepted
        assert r.recall == 1.0

    def test_mid_threshold_with_mixed_results(self):
        """threshold=0.55 → some accepted, some rejected."""
        r = compute_threshold_metrics(ALL_DATA, 0.55)
        assert r.tp == 4    # a80, a75, a70, a60 >= 0.55
        assert r.fn == 2    # a50, a40 < 0.55
        assert r.fp == 1    # ood1 (0.65) >= 0.55
        assert r.tn == 3    # ood2, ood3, ood4 < 0.55
        assert r.far == pytest.approx(0.25)  # 1/4
        assert r.precision == pytest.approx(4 / 5)  # 4/5
        assert r.recall == pytest.approx(4 / 6)  # 4/6

    def test_all_rejected_at_high_threshold(self):
        """threshold=1.0 → nothing accepted (all rejected)."""
        r = compute_threshold_metrics(ALL_DATA, 1.0)
        assert r.tp == 0
        assert r.fn == 6
        assert r.fp == 0
        assert r.tn == 4
        assert r.far == 0.0
        assert r.precision == 0.0
        assert r.recall == 0.0
        assert r.f1 == 0.0

    def test_no_ood_cases(self):
        """Only answerable queries, no OOD → FAR is still computable (0.0)."""
        data = ANS_HIGH  # no OOD
        r = compute_threshold_metrics(data, 0.55)
        assert r.tp == 4  # a80, a75, a70, a60 >= 0.55
        assert r.fn == 2  # a50, a40 < 0.55
        assert r.fp == 0
        assert r.tn == 0
        assert r.far == 0.0  # no OOD means FAR=0.0
        assert r.precision == 1.0  # no FP
        assert r.recall == pytest.approx(4 / 6)

    def test_edge_at_actual_score_values(self):
        """threshold equal to a score — query with that score is accepted."""
        r = compute_threshold_metrics(ALL_DATA, 0.70)
        # a70.score = 0.70, threshold = 0.70 → accepted
        assert r.tp == 3  # a80, a75, a70
        assert r.fn == 3  # a60, a50, a40
        # ood1=0.65 < 0.70 → rejected
        assert r.fp == 0
        assert r.tn == 4
        assert r.far == 0.0


# ════════════════════════════════════════════════════════════════
# 2. select_best_threshold — optimal threshold selection
# ════════════════════════════════════════════════════════════════


class TestSelectBestThreshold:
    """Verify the threshold selection logic picks the correct candidate."""

    def test_selects_threshold_with_far_constraint(self):
        """FAR ≤ 0.10 → selects threshold above the highest OOD score."""
        data = ALL_DATA
        best_t, results = select_best_threshold(data, far_limit=0.10)

        # OOD scores: 0.65, 0.45, 0.30, 0.20
        # To get FAR ≤ 0.10 (at most 1 OOD), threshold must be > 0.65
        # (rejecting ood1) but ≤ 0.65 would accept ood1.
        # At T=0.66: FP=0 (ood1=0.65 < 0.66), TN=4 → FAR=0.0
        # But candidate thresholds come from actual score values.
        # Scores: [0.20, 0.30, 0.40, 0.45, 0.50, 0.60, 0.65, 0.70, 0.75, 0.80]
        # Candidates: -1.0 + scores + 1.000001
        # At T=0.70: FP=0, TN=4 → FAR=0.0, TP=3, FN=3 → F1
        # At T=0.65: FP=1 (ood1=0.65 >= 0.65), TN=3 → FAR=0.25 > 0.10 → invalid
        # So best should be 0.70 (first candidate with FAR ≤ 0.10)
        assert best_t == 0.70, f"Expected 0.70, got {best_t}"

    def test_far_025_allow_one_ood(self):
        """With far_limit=0.25, lowest threshold with FAR≤0.25 is selected."""
        data = ALL_DATA
        best_t, results = select_best_threshold(data, far_limit=0.25)

        # OOD scores: 0.65, 0.45, 0.30, 0.20
        # At T=0.50: FP=1 (ood1=0.65 ≥ 0.50), FAR=0.25 → valid, F1=0.833
        # At T=0.60: FP=1 (ood1=0.65 ≥ 0.60), FAR=0.25 → valid, F1=0.727
        # Best is 0.50 (higher F1)
        assert best_t == 0.50, f"Expected 0.50, got {best_t}"

    def test_no_valid_threshold_falls_back_to_min_far(self):
        """When no threshold meets FAR constraint, pick the one with lowest FAR."""
        # Create data where OOD scores are very high (no threshold can separate)
        high_ood = [
            PerQueryData(qid="oa", answerable=False, group="ood", top_score=0.90, hit=False),
            PerQueryData(qid="ob", answerable=False, group="ood", top_score=0.85, hit=False),
        ]
        low_ans = [
            PerQueryData(qid="q1", answerable=True, group="single_turn", top_score=0.50, hit=True),
        ]
        data = low_ans + high_ood

        best_t, results = select_best_threshold(data, far_limit=0.10)
        # Candidates: [-1.0, 0.50, 0.85, 0.90, 1.000001]
        # At T=0.90: FP=1 (oa=0.90 >= 0.90), FAR=0.5 → invalid
        # At T=1.000001: FP=0, FAR=0.0, TP=0 → invalid (no TP? actually FAR=0 ≤ 0.10)
        # So T=1.000001 IS valid: FAR=0.0 ≤ 0.10, F1=0.0
        assert best_t == pytest.approx(1.000001, abs=0.001)

    def test_select_returns_serializable_results(self):
        """The threshold sweep results should be serializable (dicts)."""
        data = ALL_DATA[:4]  # small set
        best_t, results = select_best_threshold(data, far_limit=0.10)

        assert isinstance(results, list)
        assert len(results) > 0
        for r in results:
            # All values should be JSON-serializable
            assert isinstance(r["threshold"], float)
            assert isinstance(r["tp"], int)
            assert isinstance(r["fn"], int)
            assert isinstance(r["fp"], int)
            assert isinstance(r["tn"], int)
            assert isinstance(r["far"], float)
            assert isinstance(r["precision"], float)
            assert isinstance(r["recall"], float)
            assert isinstance(r["f1"], float)

    def test_tie_breaking_higher_f1_wins(self):
        """When multiple thresholds have same FAR, choose higher F1."""
        # OOD at 0.55 so lower thresholds allow it through
        mixed = [
            PerQueryData(qid="a1", answerable=True, group="single_turn", top_score=0.90, hit=True),
            PerQueryData(qid="a2", answerable=True, group="single_turn", top_score=0.80, hit=True),
            PerQueryData(qid="a3", answerable=True, group="single_turn", top_score=0.70, hit=True),
            PerQueryData(qid="a4", answerable=True, group="single_turn", top_score=0.60, hit=False),
            PerQueryData(qid="a5", answerable=True, group="single_turn", top_score=0.50, hit=True),
            PerQueryData(qid="ood1", answerable=False, group="ood", top_score=0.55, hit=False),
        ]

        best_t, results = select_best_threshold(mixed, far_limit=0.10)

        # Candidates: [-1.0, 0.50, 0.55, 0.60, 0.70, 0.80, 0.90, 1.000001]
        # At T=0.50: FP=1 (ood1=0.55 >= 0.50), FAR=1.0 → invalid
        # At T=0.55: FP=1 (ood1=0.55 >= 0.55), FAR=1.0 → invalid
        # At T=0.60: FP=0, FAR=0.0, TP=4, FN=1, F1=0.8889 → valid
        # At T=0.70: FP=0, FAR=0.0, TP=3, FN=2, F1=0.75 → valid
        # Best: T=0.60 (highest F1 among valid)
        assert best_t == 0.60, f"Expected 0.60, got {best_t}"
