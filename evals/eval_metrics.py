"""
eval_metrics — Pure metric computation functions for RAG evaluation.

All functions are deterministic (no I/O) and operate on plain Python
dicts/lists, making them easy to unit-test without fixtures or services.

Metric definitions
------------------
Hit@5
    Whether the *gold_title_contains* fragment appears in the title of
    any of the first 5 retrieved sources.

MRR@5
    Mean Reciprocal Rank: 1/rank of the first source whose title
    contains the gold fragment, averaged over queries (0 if none).

Precision@5
    Fraction of the top-5 sources whose title contains the gold fragment.

Recall@5
    1.0 if at least one top-5 source matches, else 0.0 (single-relevant
    ground-truth scenario).

OOD rejection rate
    Fraction of OOD queries whose answer matches a rejection phrase.

Citation accuracy
    Fraction of [Sx] references in the answer that point to a source
    index actually present in the returned sources list.

P95 latency
    95th-percentile of per-query wall-clock time across all queries.
"""

from __future__ import annotations

import re
from typing import Any

# -------------------------------------------------------------------
# Source-level metrics (retrieval quality)
# -------------------------------------------------------------------

DEFAULT_REJECTION_PHRASES = [
    "暂未找到",
    "未找到相关",
    "未找到信息",
    "无法回答",
]


def hit_at_5(
    sources: list[dict[str, Any]],
    gold_title_contains: str,
) -> bool:
    """Return True if *gold_title_contains* appears in any top-5 source title.

    Parameters
    ----------
    sources :
        Ordered list of retrieved source dicts, each containing a ``"title"`` key.
    gold_title_contains :
        Substring expected in a relevant source's title (case-insensitive).

    Returns
    -------
    bool
    """
    if not gold_title_contains:
        return False
    gold_lower = gold_title_contains.lower()
    for src in sources[:5]:
        if gold_lower in src.get("title", "").lower():
            return True
    return False


def reciprocal_rank(
    sources: list[dict[str, Any]],
    gold_title_contains: str,
) -> float:
    """Reciprocal rank of the first relevant source (0 if none).

    Parameters
    ----------
    sources :
        Ordered list of retrieved source dicts.
    gold_title_contains :
        Substring expected in a relevant source's title.

    Returns
    -------
    float
        ``1 / rank`` where rank is 1-indexed, or ``0.0``.
    """
    if not gold_title_contains:
        return 0.0
    gold_lower = gold_title_contains.lower()
    for rank, src in enumerate(sources[:5], start=1):
        if gold_lower in src.get("title", "").lower():
            return 1.0 / rank
    return 0.0


def precision_at_5(
    sources: list[dict[str, Any]],
    gold_title_contains: str,
) -> float:
    """Fraction of top-5 sources whose title contains the gold fragment."""
    if not gold_title_contains or not sources:
        return 0.0
    gold_lower = gold_title_contains.lower()
    top5 = sources[:5]
    if not top5:
        return 0.0
    matches = sum(1 for src in top5 if gold_lower in src.get("title", "").lower())
    return matches / len(top5)


def recall_at_5(
    sources: list[dict[str, Any]],
    gold_title_contains: str,
) -> float:
    """1.0 if at least one relevant source is in top-5, else 0.0.

    In a single-relevant-document scenario (our gold_title_contains
    refers to one ground-truth document), recall is identical to Hit@5.
    """
    return 1.0 if hit_at_5(sources, gold_title_contains) else 0.0


# -------------------------------------------------------------------
# Answer-level metrics (generation quality)
# -------------------------------------------------------------------


def is_ood_rejected(
    answer: str,
    rejection_phrases: list[str] | None = None,
) -> bool:
    """Check whether *answer* indicates an OOD rejection.

    Parameters
    ----------
    answer :
        The LLM-generated answer string.
    rejection_phrases :
        List of substrings to check.  Defaults to
        ``DEFAULT_REJECTION_PHRASES``.

    Returns
    -------
    bool
    """
    if rejection_phrases is None:
        rejection_phrases = DEFAULT_REJECTION_PHRASES
    return any(phrase in answer for phrase in rejection_phrases)


def extract_citations(answer: str) -> list[int]:
    """Extract all ``[S<digits>]`` references from *answer*.

    Returns
    -------
    list[int]
        Sorted list of citation numbers, e.g. ``[1, 3, 5]``.
    """
    return sorted({int(m) for m in re.findall(r"\[S(\d+)\]", answer)})


def citation_accuracy(
    answer: str,
    source_count: int,
) -> float:
    """Fraction of ``[Sx]`` references that point to valid source indices.

    A citation to ``[Sx]`` is *valid* when ``1 <= x <= source_count``.
    If the answer contains no citations at all, returns ``float("nan")``
    to indicate "not applicable".

    Parameters
    ----------
    answer :
        LLM-generated answer.
    source_count :
        Number of retrieved sources returned by the pipeline.

    Returns
    -------
    float
        0.0 to 1.0, or ``float("nan")`` when no citations present.
    """
    citations = extract_citations(answer)
    if not citations:
        return float("nan")
    valid = sum(1 for c in citations if 1 <= c <= source_count)
    return valid / len(citations)


# -------------------------------------------------------------------
# Aggregation helpers
# -------------------------------------------------------------------


def compute_p95(values: list[float]) -> float:
    """95th percentile of *values*.

    Parameters
    ----------
    values :
        Sorted or unsorted list of numeric latencies in seconds (or any
        unit).  At least 1 element required.

    Returns
    -------
    float
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = max(0, min(len(sorted_vals) - 1, int(0.95 * len(sorted_vals))))
    return sorted_vals[idx]


def aggregate_metrics(
    per_case_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate per-case results into summary metrics.

    Parameters
    ----------
    per_case_results :
        List of per-case dicts, each containing at minimum:
        ``hit``, ``rr``, ``precision``, ``recall``, ``ood_rejected``
        (or ``None`` for answerable), ``citation_acc`` (or ``float('nan')``
        when N/A), ``latency_s``, ``answerable``, ``group``.

    Returns
    -------
    dict
        Aggregated metrics suitable for JSON serialisation.
    """
    answerable_cases = [r for r in per_case_results if r.get("answerable", True)]
    ood_cases = [r for r in per_case_results if r.get("group") == "ood"]
    all_cases = per_case_results

    # Retrieval metrics (answerable only)
    hit_list = [r["hit"] for r in answerable_cases]
    rr_list = [r["rr"] for r in answerable_cases]
    prec_list = [r["precision"] for r in answerable_cases]
    rec_list = [r["recall"] for r in answerable_cases]

    # OOD rejection
    ood_rejected = [r["ood_rejected"] for r in ood_cases if r["ood_rejected"] is not None]
    ood_total = len(ood_cases)

    # Citation accuracy (across all answerable cases with citations)
    cit_accs = [
        r["citation_acc"]
        for r in answerable_cases
        if r.get("citation_acc") is not None and not (isinstance(r["citation_acc"], float) and r["citation_acc"] != r["citation_acc"])  # not nan
    ]

    # Latencies
    latencies = [r["latency_s"] for r in all_cases if r.get("latency_s") is not None]

    metrics: dict[str, Any] = {
        "total_cases": len(all_cases),
        "answerable_cases": len(answerable_cases),
        "ood_cases": ood_total,
    }

    if answerable_cases:
        metrics["hit_at_5"] = round(sum(hit_list) / len(hit_list), 4) if hit_list else 0.0
        metrics["hit_at_5_detail"] = f"{sum(hit_list)}/{len(hit_list)}"
        metrics["mrr_at_5"] = round(sum(rr_list) / len(rr_list), 4) if rr_list else 0.0
        metrics["precision_at_5"] = round(sum(prec_list) / len(prec_list), 4) if prec_list else 0.0
        metrics["recall_at_5"] = round(sum(rec_list) / len(rec_list), 4) if rec_list else 0.0

    if ood_total > 0:
        rejected_count = sum(ood_rejected)
        metrics["ood_rejection_rate"] = round(rejected_count / ood_total, 4)
        metrics["ood_rejection_detail"] = f"{rejected_count}/{ood_total}"
    else:
        metrics["ood_rejection_rate"] = 0.0
        metrics["ood_rejection_detail"] = "0/0"

    if cit_accs:
        metrics["citation_accuracy"] = round(sum(cit_accs) / len(cit_accs), 4)
    else:
        metrics["citation_accuracy"] = None

    if latencies:
        metrics["avg_latency_s"] = round(sum(latencies) / len(latencies), 3)
        metrics["p95_latency_s"] = round(compute_p95(latencies), 3)
    else:
        metrics["avg_latency_s"] = 0.0
        metrics["p95_latency_s"] = 0.0

    return metrics
