"""
TDD tests for evaluation metric computation functions (evals/eval_metrics.py).

All tests use pure function calls with fictitious data — no service calls,
no fixtures, no I/O.
"""

from __future__ import annotations

import sys
import math
from pathlib import Path

# Ensure the project root is on sys.path so we can import evals.eval_metrics
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest

from evals.eval_metrics import (
    aggregate_metrics,
    citation_accuracy,
    compute_p95,
    extract_citations,
    hit_at_5,
    is_ood_rejected,
    precision_at_5,
    recall_at_5,
    reciprocal_rank,
)

# ════════════════════════════════════════════════════════════════
# Fictitious test data
# ════════════════════════════════════════════════════════════════

SOURCES_CASE_1 = [
    {"title": "校园文化", "score": 0.85},
    {"title": "河海大学", "score": 0.72},
    {"title": "通知公告", "score": 0.65},
    {"title": "河海大学商学院", "score": 0.60},
    {"title": "法学院", "score": 0.55},
]
# gold_title_contains = "校园文化" → match at rank 1

SOURCES_CASE_2 = [
    {"title": "河海大学", "score": 0.80},
    {"title": "河海大学研究生院", "score": 0.75},
    {"title": "AI for Water学术联盟成立大会", "score": 0.70},
    {"title": "通知公告", "score": 0.62},
    {"title": "法学院", "score": 0.58},
]
# gold_title_contains = "AI for Water" → match at rank 3

SOURCES_CASE_3 = [
    {"title": "河海大学", "score": 0.82},
    {"title": "通知公告", "score": 0.71},
    {"title": "法学院", "score": 0.68},
    {"title": "河海大学商学院", "score": 0.63},
    {"title": "常用电话", "score": 0.60},
]
# gold_title_contains = "校训" → no match

SOURCES_EMPTY: list[dict] = []

# ════════════════════════════════════════════════════════════════
# 1. Hit@5
# ════════════════════════════════════════════════════════════════


class TestHitAt5:
    """test_hit_at_5_computation — 3 fictitious results → correct Hit@5"""

    def test_hit_at_rank_1(self):
        """gold title present at rank 1 → True"""
        assert hit_at_5(SOURCES_CASE_1, "校园文化") is True

    def test_hit_at_rank_3(self):
        """gold title present at rank 3 → True"""
        assert hit_at_5(SOURCES_CASE_2, "AI for Water") is True

    def test_no_hit(self):
        """gold title not present in any source → False"""
        assert hit_at_5(SOURCES_CASE_3, "校训") is False

    def test_empty_gold_title(self):
        """empty gold title → False (no ground truth to match)"""
        assert hit_at_5(SOURCES_CASE_1, "") is False

    def test_empty_sources(self):
        """empty sources list → False"""
        assert hit_at_5(SOURCES_EMPTY, "校园文化") is False

    def test_case_insensitive(self):
        """match is case-insensitive"""
        assert hit_at_5(SOURCES_CASE_1, "校园") is True
        assert hit_at_5(SOURCES_CASE_1, "校园文化") is True

    def test_hit_beyond_top_5_ignored(self):
        """only first 5 sources are considered"""
        many_sources = [
            {"title": "无关1"},
            {"title": "无关2"},
            {"title": "无关3"},
            {"title": "无关4"},
            {"title": "无关5"},
            {"title": "校园文化"},  # rank 6, should NOT count
        ]
        assert hit_at_5(many_sources, "校园文化") is False


# ════════════════════════════════════════════════════════════════
# 2. MRR@5 (reciprocal_rank)
# ════════════════════════════════════════════════════════════════


class TestMRRAt5:
    """test_mrr_at_5_computation — 3 fictitious results → correct MRR@5"""

    def test_rr_rank_1(self):
        """match at rank 1 → RR = 1.0"""
        assert reciprocal_rank(SOURCES_CASE_1, "校园文化") == pytest.approx(1.0)

    def test_rr_rank_3(self):
        """match at rank 3 → RR = 1/3"""
        assert reciprocal_rank(SOURCES_CASE_2, "AI for Water") == pytest.approx(1.0 / 3.0)

    def test_rr_no_match(self):
        """no match → RR = 0.0"""
        assert reciprocal_rank(SOURCES_CASE_3, "校训") == pytest.approx(0.0)

    def test_rr_empty_gold(self):
        """empty gold title → RR = 0.0"""
        assert reciprocal_rank(SOURCES_CASE_1, "") == pytest.approx(0.0)

    def test_rr_empty_sources(self):
        """empty sources → RR = 0.0"""
        assert reciprocal_rank(SOURCES_EMPTY, "校园文化") == pytest.approx(0.0)

    def test_rr_first_match_counts(self):
        """when gold matches multiple sources, use the earliest rank"""
        sources = [
            {"title": "校园文化"},
            {"title": "校园文化相关"},
            {"title": "其他"},
        ]
        # First match at rank 1
        assert reciprocal_rank(sources, "校园文化") == pytest.approx(1.0)


# ════════════════════════════════════════════════════════════════
# 3. Precision@5 & Recall@5
# ════════════════════════════════════════════════════════════════


class TestPrecisionRecall:
    def test_precision_all_match(self):
        """all 5 sources match → precision = 1.0"""
        sources = [
            {"title": "校园文化"},
            {"title": "校园文化_2"},
            {"title": "校园文化_3"},
            {"title": "校园文化_4"},
            {"title": "校园文化_5"},
        ]
        assert precision_at_5(sources, "校园文化") == pytest.approx(1.0)

    def test_precision_partial(self):
        """2/5 match → precision = 0.4"""
        sources = [
            {"title": "校园文化"},
            {"title": "河海大学"},
            {"title": "校园文化相关"},
            {"title": "通知公告"},
            {"title": "法学院"},
        ]
        assert precision_at_5(sources, "校园文化") == pytest.approx(0.4)

    def test_precision_no_match(self):
        """0/5 match → precision = 0.0"""
        assert precision_at_5(SOURCES_CASE_3, "不存在") == pytest.approx(0.0)

    def test_recall_match(self):
        """relevant doc found → recall = 1.0"""
        assert recall_at_5(SOURCES_CASE_1, "校园文化") == pytest.approx(1.0)

    def test_recall_no_match(self):
        """no relevant doc → recall = 0.0"""
        assert recall_at_5(SOURCES_CASE_3, "校训") == pytest.approx(0.0)


# ════════════════════════════════════════════════════════════════
# 4. OOD rejection rate
# ════════════════════════════════════════════════════════════════


class TestOODRejection:
    """test_ood_rejection_rate — mixed OOD → correct rejection rate"""

    REJECTION_TEMPLATE = "根据现有校园知识库，暂未找到关于「xxx」的可靠信息。"
    NORMAL_ANSWER = "河海大学的校训是艰苦朴素、实事求是、严格要求、勇于探索。[S1]"
    EMPTY_ANSWER = ""

    def test_rejected_with_template(self):
        """OOD answer contains rejection phrase → rejected = True"""
        assert is_ood_rejected(self.REJECTION_TEMPLATE) is True

    def test_not_rejected_normal(self):
        """normal answer does not contain rejection phrase → False"""
        assert is_ood_rejected(self.NORMAL_ANSWER) is False

    def test_rejected_with_standard_phrases(self):
        """answers with '未找到相关信息' or '无法回答' are rejected"""
        assert is_ood_rejected("未找到相关信息") is True
        assert is_ood_rejected("未找到相关校园信息") is True
        assert is_ood_rejected("无法回答该问题") is True

    def test_empty_answer(self):
        """empty string → not rejected (no phrase matched)"""
        assert is_ood_rejected(self.EMPTY_ANSWER) is False

    def test_custom_rejection_phrases(self):
        """custom rejection phrases override defaults"""
        custom = ["据我所知"]
        assert is_ood_rejected("据我所知没有相关信息", rejection_phrases=custom) is True
        assert is_ood_rejected("暂未找到相关信息", rejection_phrases=custom) is False


# ════════════════════════════════════════════════════════════════
# 5. Citation accuracy
# ════════════════════════════════════════════════════════════════


class TestCitationAccuracy:
    """test_citation_accuracy — mixed valid/invalid citations → correct accuracy"""

    def test_all_valid(self):
        """all citations point to existing sources → accuracy = 1.0"""
        answer = "校训是艰苦朴素[S1][S2]，要实事求是[S3]。"
        assert citation_accuracy(answer, source_count=3) == pytest.approx(1.0)

    def test_some_invalid(self):
        """some citations point to non-existent sources → accuracy < 1.0"""
        answer = "正确[S1]和错误[S5]。"
        # 5 > source_count=3 → invalid
        assert citation_accuracy(answer, source_count=3) == pytest.approx(0.5)

    def test_all_invalid(self):
        """all citations are invalid → accuracy = 0.0"""
        answer = "无效[S5][S10]引用。"
        assert citation_accuracy(answer, source_count=3) == pytest.approx(0.0)

    def test_no_citations(self):
        """answer has no [Sx] references → nan"""
        answer = "这是一个没有引用的回答。"
        assert math.isnan(citation_accuracy(answer, source_count=3))

    def test_mixed_format(self):
        """citations with different spacing and formats"""
        answer = "校训[S1]很好[S2]。"
        assert citation_accuracy(answer, source_count=2) == pytest.approx(1.0)
        assert citation_accuracy(answer, source_count=0) == pytest.approx(0.0)

    def test_extract_citations(self):
        """extract_citations returns correct sorted unique numbers"""
        assert extract_citations("[S1][S2]text[S3]") == [1, 2, 3]
        assert extract_citations("[S3][S1][S2]") == [1, 2, 3]
        assert extract_citations("no citations") == []
        assert extract_citations("[S1][S1][S2]") == [1, 2]  # deduplicated


# ════════════════════════════════════════════════════════════════
# 6. P95 latency
# ════════════════════════════════════════════════════════════════


class TestP95:
    def test_single_value(self):
        """single value returns itself"""
        assert compute_p95([5.0]) == pytest.approx(5.0)

    def test_three_values(self):
        """3 values: 1, 2, 10 → P95 ~= 10 (ceiling)"""
        assert compute_p95([1.0, 2.0, 10.0]) == pytest.approx(10.0)

    def test_empty(self):
        """empty list returns 0.0"""
        assert compute_p95([]) == pytest.approx(0.0)


# ════════════════════════════════════════════════════════════════
# 7. Aggregate metrics (integration smoke test)
# ════════════════════════════════════════════════════════════════


class TestAggregateMetrics:
    """verify aggregate_metrics produces the expected output format"""

    def test_aggregate_basic(self):
        """3 answerable + 2 OOD cases → correct structure"""
        results = [
            # Answerable — hit, rr=1.0, precision=0.2, recall=1.0, citation valid
            {
                "id": "q1",
                "hit": True,
                "rr": 1.0,
                "precision": 0.2,
                "recall": 1.0,
                "ood_rejected": False,
                "citation_acc": 1.0,
                "latency_s": 2.0,
                "answerable": True,
                "group": "single_turn",
            },
            # Answerable — no hit, rr=0, precision=0, recall=0
            {
                "id": "q2",
                "hit": False,
                "rr": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "ood_rejected": False,
                "citation_acc": float("nan"),
                "latency_s": 3.0,
                "answerable": True,
                "group": "single_turn",
            },
            # Answerable — hit at rank 3, precision=0.4
            {
                "id": "q3",
                "hit": True,
                "rr": 1.0 / 3.0,
                "precision": 0.4,
                "recall": 1.0,
                "ood_rejected": False,
                "citation_acc": 0.5,
                "latency_s": 5.0,
                "answerable": True,
                "group": "multi_turn",
            },
            # OOD — rejected
            {
                "id": "ood1",
                "hit": False,
                "rr": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "ood_rejected": True,
                "citation_acc": None,
                "latency_s": 1.5,
                "answerable": False,
                "group": "ood",
            },
            # OOD — not rejected
            {
                "id": "ood2",
                "hit": False,
                "rr": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "ood_rejected": False,
                "citation_acc": None,
                "latency_s": 1.2,
                "answerable": False,
                "group": "ood",
            },
        ]

        metrics = aggregate_metrics(results)

        # Structure checks
        assert metrics["total_cases"] == 5
        assert metrics["answerable_cases"] == 3
        assert metrics["ood_cases"] == 2

        # Hit@5 = 2/3 = 0.6667 (rounded to 4dp in aggregate_metrics)
        assert metrics["hit_at_5"] == pytest.approx(0.6667, abs=1e-4)
        assert metrics["hit_at_5_detail"] == "2/3"

        # MRR@5 = (1.0 + 0.0 + 0.333) / 3 = 0.4444 (rounded to 4dp)
        expected_mrr = round((1.0 + 0.0 + 1.0 / 3.0) / 3.0, 4)
        assert metrics["mrr_at_5"] == pytest.approx(expected_mrr, abs=1e-4)

        # Precision@5 = (0.2 + 0.0 + 0.4) / 3 = 0.2 (0.2000 rounded)
        assert metrics["precision_at_5"] == pytest.approx(0.2, abs=1e-4)

        # Recall@5 = (1.0 + 0.0 + 1.0) / 3 = 0.6667 (rounded to 4dp)
        assert metrics["recall_at_5"] == pytest.approx(0.6667, abs=1e-4)

        # OOD rejection = 1/2 = 0.5
        assert metrics["ood_rejection_rate"] == pytest.approx(0.5)
        assert metrics["ood_rejection_detail"] == "1/2"

        # Citation accuracy = (1.0 + 0.5) / 2 = 0.75
        assert metrics["citation_accuracy"] == pytest.approx(0.75)

        # P95 latency: sorted [1.2, 1.5, 2.0, 3.0, 5.0]
        assert metrics["p95_latency_s"] == pytest.approx(5.0)
        assert metrics["avg_latency_s"] == pytest.approx((2.0 + 3.0 + 5.0 + 1.5 + 1.2) / 5.0)
