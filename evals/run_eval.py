#!/usr/bin/env python3.11
"""
run_eval — RAG evaluation framework.

Loads ``campus_qa.jsonl`` test cases, calls the ai_service ``/query`` endpoint
for each case, computes retrieval and generation metrics, and outputs a JSON
report.

Usage
-----
    # Retrieval-only evaluation (no answer-level metrics)
    python run_eval.py --mode retrieval --top-k 5

    # Full evaluation (retrieval + generation + citation validation)
    python run_eval.py --mode full --top-k 5

    # Ablation: label the run for comparison
    python run_eval.py --mode full --top-k 10 --tag dense-only

    # Compare two result files
    python run_eval.py --compare results/run_001 results/run_002

Modes
-----
retrieval
    Evaluate only source-level metrics: Hit@5, MRR@5, Precision@5, Recall@5,
    P95 latency.  Still calls ``/query`` (which internally runs retrieval +
    generation), but only analyses the ``sources`` portion of the response.
generation
    Evaluate source-level + answer-level metrics: adds OOD rejection rate,
    citation accuracy.
full
    Same as *generation* — all metrics are computed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# Ensure project root is on sys.path for evals.eval_metrics imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from evals.eval_metrics import (
    aggregate_metrics,
    citation_accuracy,
    hit_at_5,
    is_ood_rejected,
    precision_at_5,
    recall_at_5,
    reciprocal_rank,
)

# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("run_eval")

# -------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------

DEFAULT_AI_SERVICE_URL = "http://localhost:8003"
DEFAULT_EVAL_DATA = _PROJECT_ROOT / "evals" / "campus_qa.jsonl"
DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "evals" / "results"
DEFAULT_TOP_K = 5

# -------------------------------------------------------------------
# Data loading
# -------------------------------------------------------------------


def load_test_cases(path: str | Path) -> list[dict[str, Any]]:
    """Load JSONL test cases from *path*.

    Returns
    -------
    list[dict]
        Each dict contains keys: ``id``, ``group``, ``question``,
        ``answerable``, ``gold_title_contains``, ``expected_terms``.
        Multi-turn cases also have ``history``.
    """
    cases: list[dict[str, Any]] = []
    path = Path(path)
    if not path.exists():
        logger.error("Test data not found: %s", path)
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("Skipping line %d: invalid JSON — %s", line_no, e)
                continue
            cases.append(case)

    logger.info("Loaded %d test cases from %s", len(cases), path)
    return cases


# -------------------------------------------------------------------
# API call
# -------------------------------------------------------------------


def call_query(
    question: str,
    top_k: int = DEFAULT_TOP_K,
    base_url: str = DEFAULT_AI_SERVICE_URL,
    timeout_s: int = 120,
) -> dict[str, Any] | None:
    """Call the ai_service ``/query`` endpoint.

    Returns
    -------
    dict or None
        The JSON response body on success, or ``None`` on failure.
    """
    url = f"{base_url.rstrip('/')}/query"
    payload = {"question": question, "top_k": top_k}
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_s)) as client:
            resp = client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("HTTP %s for question=%r: %s", e.response.status_code, question[:60], e)
    except httpx.RequestError as e:
        logger.error("Request failed for question=%r: %s", question[:60], e)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON response for question=%r: %s", question[:60], e)
    return None


# -------------------------------------------------------------------
# Per-case evaluation
# -------------------------------------------------------------------


def evaluate_case(
    case: dict[str, Any],
    response: dict[str, Any],
    mode: str,
    top_k: int,
) -> dict[str, Any]:
    """Compute per-case metrics from the API response.

    Parameters
    ----------
    case :
        Original test case dict.
    response :
        Parsed ``/query`` response (``{"answer": ..., "sources": [...]}``).
    mode :
        ``"retrieval"``, ``"generation"``, or ``"full"``.
    top_k :
        Number of top results requested.

    Returns
    -------
    dict
        Per-case result with keys: ``id``, ``group``, ``question``,
        ``answerable``, ``hit``, ``rr``, ``precision``, ``recall``,
        ``ood_rejected``, ``citation_acc``, ``source_count``,
        ``answer``, ``latency_s``.
    """
    sources = response.get("sources", [])
    answer = response.get("answer", "")

    gold = case.get("gold_title_contains", "")
    is_answerable = case.get("answerable", True)

    # Retrieval metrics
    hit = hit_at_5(sources, gold) if gold else False
    rr = reciprocal_rank(sources, gold) if gold else 0.0
    prec = precision_at_5(sources, gold) if gold else 0.0
    rec = recall_at_5(sources, gold) if gold else 0.0

    # Answer-level metrics (only in generation / full mode)
    ood_rejected: bool | None = None
    citation_acc: float | None = None

    if mode in ("generation", "full"):
        if not is_answerable:
            ood_rejected = is_ood_rejected(answer)
        if is_answerable and answer:
            cit_acc = citation_accuracy(answer, len(sources))
            citation_acc = cit_acc if not (isinstance(cit_acc, float) and cit_acc != cit_acc) else None  # nan → None

    return {
        "id": case.get("id", "unknown"),
        "group": case.get("group", "unknown"),
        "question": case.get("question", ""),
        "answerable": is_answerable,
        "answer": answer,
        "hit": hit,
        "rr": rr,
        "precision": prec,
        "recall": rec,
        "ood_rejected": ood_rejected,
        "citation_acc": citation_acc,
        "source_count": len(sources),
    }


# -------------------------------------------------------------------
# Main evaluation loop
# -------------------------------------------------------------------


def run_eval(
    cases: list[dict[str, Any]],
    mode: str = "retrieval",
    top_k: int = DEFAULT_TOP_K,
    base_url: str = DEFAULT_AI_SERVICE_URL,
    tag: str | None = None,
) -> dict[str, Any]:
    """Run evaluation on all test cases.

    Parameters
    ----------
    cases :
        List of test case dicts.
    mode :
        Evaluation mode.
    top_k :
        Number of top results to request.
    base_url :
        ai_service base URL.
    tag :
        Optional run tag for the report.

    Returns
    -------
    dict
        Full evaluation report (config + metrics + per-case results).
    """
    per_case_results: list[dict[str, Any]] = []
    latencies_s: list[float] = []
    errors: int = 0

    logger.info(
        "Starting eval: mode=%s, top_k=%d, cases=%d, tag=%s",
        mode,
        top_k,
        len(cases),
        tag or "default",
    )

    for idx, case in enumerate(cases, start=1):
        case_id = case.get("id", f"case_{idx}")
        question = case.get("question", "")

        logger.info("[%d/%d] %s: %s", idx, len(cases), case_id, question[:60])

        t0 = time.time()
        response = call_query(question, top_k=top_k, base_url=base_url)
        elapsed = time.time() - t0
        latencies_s.append(elapsed)

        if response is None:
            logger.warning("  → No response (error)")
            per_case_results.append({
                "id": case_id,
                "group": case.get("group", "unknown"),
                "question": question,
                "answerable": case.get("answerable", True),
                "answer": "",
                "hit": False,
                "rr": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "ood_rejected": None,
                "citation_acc": None,
                "source_count": 0,
                "error": True,
            })
            errors += 1
            continue

        result = evaluate_case(case, response, mode, top_k)
        result["latency_s"] = round(elapsed, 3)
        result["error"] = False
        per_case_results.append(result)

        hit_str = "✓" if result["hit"] else "✗"
        logger.info(
            "  → hit=%s rr=%.3f prec=%.3f src=%d [%.1fs]",
            hit_str,
            result["rr"],
            result["precision"],
            result["source_count"],
            elapsed,
        )

    # Aggregate
    metrics = aggregate_metrics(per_case_results)

    report: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "mode": mode,
            "top_k": top_k,
            "tag": tag,
            "ai_service_url": base_url,
        },
        "summary": {
            "total_cases": len(cases),
            "errors": errors,
            "success": len(cases) - errors,
        },
        "metrics": metrics,
        "results": per_case_results,
    }

    logger.info(
        "Eval complete: Hit@5=%.4f, MRR@5=%.4f, OOD_reject=%.4f, P95=%.1fs, errors=%d",
        metrics.get("hit_at_5", 0),
        metrics.get("mrr_at_5", 0),
        metrics.get("ood_rejection_rate", 0),
        metrics.get("p95_latency_s", 0),
        errors,
    )

    return report


# -------------------------------------------------------------------
# Output
# -------------------------------------------------------------------


def save_report(
    report: dict[str, Any],
    output_dir: str | Path,
    tag: str | None = None,
) -> Path:
    """Save the evaluation report as a JSON file.

    Creates a timestamped subdirectory under *output_dir* and writes
    ``report.json``.  Also writes a ``config.json`` sidecar with just
    the config section for quick comparison.

    Parameters
    ----------
    report :
        Full evaluation report dict.
    output_dir :
        Base directory for results.
    tag :
        Optional run tag (used in filename).

    Returns
    -------
    Path
        Path to the saved report file.
    """
    output_dir = Path(output_dir)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag_suffix = f"_{tag}" if tag else ""
    run_dir = output_dir / f"{timestamp}{tag_suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)

    report_path = run_dir / "report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("Report saved to %s", report_path)

    # Sidecar: config-only for quick comparison
    config_path = run_dir / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(report["config"], f, ensure_ascii=False, indent=2)
    logger.info("Config saved to %s", config_path)

    return report_path


# -------------------------------------------------------------------
# Ablation comparison
# -------------------------------------------------------------------


def compare_results(result_paths: list[str]) -> None:
    """Compare multiple evaluation result files side-by-side.

    Reads ``report.json`` from each path and prints a comparison table
    of metrics and config to stdout.

    Parameters
    ----------
    result_paths :
        Paths to result directories or ``report.json`` files.
    """
    reports: list[dict[str, Any]] = []
    for rp in result_paths:
        p = Path(rp)
        if p.is_dir():
            p = p / "report.json"
        if not p.exists():
            logger.error("Result file not found: %s", p)
            continue
        with open(p, encoding="utf-8") as f:
            reports.append(json.load(f))

    if not reports:
        logger.error("No valid result files to compare.")
        return

    print()
    print("=" * 80)
    print("ABLATION COMPARISON")
    print("=" * 80)

    # Header row
    headers = ["Metric"] + [f"Run {i+1}" for i in range(len(reports))]
    col_width = max(len(h) for h in headers) + 2
    print(f"{'Metric':<30}", end="")
    for i in range(len(reports)):
        tag = reports[i].get("config", {}).get("tag", f"run-{i+1}")
        print(f"{tag:<20}", end="")
    print()
    print("-" * 80)

    # Config
    config_keys = ["mode", "top_k", "tag"]
    for key in config_keys:
        print(f"{'config/' + key:<30}", end="")
        for r in reports:
            val = r.get("config", {}).get(key, "-")
            print(f"{str(val):<20}", end="")
        print()

    # Metrics
    metric_keys = [
        "hit_at_5",
        "mrr_at_5",
        "precision_at_5",
        "recall_at_5",
        "ood_rejection_rate",
        "citation_accuracy",
        "avg_latency_s",
        "p95_latency_s",
    ]
    for key in metric_keys:
        print(f"{key:<30}", end="")
        for r in reports:
            val = r.get("metrics", {}).get(key)
            if val is None:
                print(f"{'N/A':<20}", end="")
            elif isinstance(val, float):
                print(f"{val:<20.4f}", end="")
            else:
                print(f"{str(val):<20}", end="")
        print()

    print("=" * 80)
    print()


# -------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RAG evaluation framework — run test cases and compute metrics.",
    )
    parser.add_argument(
        "--mode",
        choices=["retrieval", "generation", "full"],
        default="retrieval",
        help="Evaluation mode (default: retrieval)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Number of top results to request (default: {DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Confidence threshold for analysis (default: no threshold)",
    )
    parser.add_argument(
        "--reranker",
        action="store_true",
        default=False,
        help="Flag indicating reranker is enabled (for ablation naming)",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="Arbitrary run tag (dense-only, hybrid, reranker, etc.)",
    )
    parser.add_argument(
        "--data",
        type=str,
        default=str(DEFAULT_EVAL_DATA),
        help=f"Path to test data JSONL (default: {DEFAULT_EVAL_DATA})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_AI_SERVICE_URL,
        help=f"ai_service base URL (default: {DEFAULT_AI_SERVICE_URL})",
    )
    parser.add_argument(
        "--compare",
        type=str,
        nargs="+",
        default=None,
        metavar="PATH",
        help="Compare result directories/files (disables normal run)",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()

    # Comparison mode
    if args.compare:
        compare_results(args.compare)
        return

    # Auto-tag if reranker flag set
    tag = args.tag
    if tag is None and args.reranker:
        tag = "with-reranker"
    if tag is None and args.threshold is not None:
        tag = f"thresh-{args.threshold}"

    # Load test cases
    cases = load_test_cases(args.data)

    # Run evaluation
    report = run_eval(
        cases=cases,
        mode=args.mode,
        top_k=args.top_k,
        base_url=args.url,
        tag=tag,
    )

    # Save report
    report_path = save_report(report, args.output, tag=tag)
    print()
    print(f"Report saved to: {report_path}")
    print(f"Metrics: {json.dumps(report['metrics'], ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()
