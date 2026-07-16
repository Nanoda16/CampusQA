#!/usr/bin/env python3.11
"""
calibrate — Retrieval threshold calibration for RAG pipeline configurations.

For each configuration (hybrid, hybrid+reranker) the script:

1. **Data collection** — runs all 50 eval queries through the real pipeline
   (with a no-op generator to skip LLM cost), capturing per-query:
   - ``top_score``: best dense-retrieval similarity score
   - ``hit``:     whether *gold_title_contains* appears in final sources

2. **Offline threshold sweep** — for each candidate threshold T:
   - Answerable queries with ``top_score < T`` are *rejected* (system
     returns the rejection template instead of answering).
   - Answerable queries with ``top_score >= T`` are *accepted* (system
     runs its full retrieval pipeline, including RRF + reranker).
   - OOD queries with ``top_score < T`` are correctly rejected (true
     negative); those with ``top_score >= T`` are false accepts.

   Computes for each T:
   - **FAR** (False Accept Rate) = OOD_accepted / total_OOD
   - **Precision** = accepted_answerable / total_accepted
   - **Recall**   = accepted_answerable / total_answerable
   - **F1**       = harmonic mean of Precision and Recall

3. **Selection** — picks the threshold where FAR ≤ 0.10 AND F1 is
   maximised.  The result is stored in ``evals/calibration_report.json``.

Usage
-----
    # Calibrate both configs (default)
    python3.11 evals/calibrate.py

    # Single config
    python3.11 evals/calibrate.py --config hybrid

Rounds
------
Max 3 rounds per config:
  Round 1 — data collection (threshold=0.0, all queries pass)
  Round 2 — verification (eval at optimal threshold)
  Round 3 — fine-tune if FAR constraint violated

Configuration
-------------
- ``hybrid``:  Dense + BM25 + RRF, reranker disabled
- ``hybrid+reranker``: Dense + BM25 + RRF + cross-encoder reranker

**Note**: "dense-only" (without BM25) is not separately tested because BM25
is now always-on in the pipeline.  The "dense-only" label here refers to
thresholding on dense scores, which is the same mechanism for all configs.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# Ensure both project root (for evals.*) and ai_service/ (for engine.*) are importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_AI_SERVICE_DIR = _PROJECT_ROOT / "ai_service"

for _p in [str(_PROJECT_ROOT), str(_AI_SERVICE_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from evals.eval_metrics import hit_at_5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("calibrate")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVAL_DATA = _PROJECT_ROOT / "evals" / "campus_qa.jsonl"
OUTPUT_DIR = _PROJECT_ROOT / "evals" / "results"
CALIBRATION_REPORT = _PROJECT_ROOT / "evals" / "calibration_report.json"
_AI_DATA = _AI_SERVICE_DIR / "data" / "bm25"
MAX_ROUNDS = 3

# Config definitions
CONFIGS: dict[str, dict[str, Any]] = {
    "hybrid": {
        "reranker_enabled": False,
        "description": "Dense + BM25 + RRF (no reranker)",
    },
    "hybrid+reranker": {
        "reranker_enabled": True,
        "description": "Dense + BM25 + RRF + cross-encoder reranker",
    },
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PerQueryData:
    """Score and retrieval outcome for a single eval query."""

    qid: str
    answerable: bool
    group: str
    top_score: float
    hit: bool


@dataclass
class ThresholdResult:
    """Metrics for a single candidate threshold."""

    threshold: float
    tp: int  # answerable accepted
    fn: int  # answerable rejected
    fp: int  # OOD accepted (false accept)
    tn: int  # OOD rejected
    far: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0


@dataclass
class CalibrationRound:
    """Data collected in one calibration round."""

    round_num: int
    config_name: str
    per_query: list[dict[str, Any]] = field(default_factory=list)
    thresholds: list[dict[str, Any]] = field(default_factory=list)
    best_threshold: float | None = None
    hit_at_5_at_best: float = 0.0


@dataclass
class ConfigResult:
    """Full result for one pipeline configuration."""

    config_name: str
    description: str
    rounds: list[CalibrationRound] = field(default_factory=list)
    final_threshold: float | None = None
    final_hit_at_5: float = 0.0


# ---------------------------------------------------------------------------
# Test data loading
# ---------------------------------------------------------------------------


def load_test_cases(path: str | Path) -> list[dict[str, Any]]:
    """Load JSONL test cases."""
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
                cases.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning("Skipping line %d: invalid JSON — %s", line_no, e)

    logger.info("Loaded %d test cases from %s", len(cases), path)
    return cases


# ---------------------------------------------------------------------------
# Calibration core
# ---------------------------------------------------------------------------


def _compute_threshold_metrics(
    per_query: list[PerQueryData],
    threshold: float,
) -> ThresholdResult:
    """Compute classification metrics at a single threshold.

    Classification scheme:
      - **TP**: answerable query with ``top_score >= threshold`` (accepted)
      - **FN**: answerable query with ``top_score < threshold`` (rejected)
      - **FP**: OOD query with ``top_score >= threshold`` (false accept)
      - **TN**: OOD query with ``top_score < threshold`` (correctly rejected)
    """
    tp = sum(1 for d in per_query if d.answerable and d.top_score >= threshold)
    fn = sum(1 for d in per_query if d.answerable and d.top_score < threshold)
    fp = sum(1 for d in per_query if not d.answerable and d.top_score >= threshold)
    tn = sum(1 for d in per_query if not d.answerable and d.top_score < threshold)

    total_ood = fp + tn
    far = fp / total_ood if total_ood > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0 if tp > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return ThresholdResult(
        threshold=threshold,
        tp=tp,
        fn=fn,
        fp=fp,
        tn=tn,
        far=far,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def select_best_threshold(
    per_query: list[PerQueryData],
    far_limit: float = 0.10,
) -> tuple[float, list[dict[str, Any]]]:
    """Select the optimal threshold.

    Iterates over all unique scores present in the data (plus sentinel
    extremes: -1.0 and 1.000001), computes classification metrics at each
    candidate, and picks the one where ``far <= far_limit`` with the highest
    F1 score.

    Parameters
    ----------
    per_query : list[PerQueryData]
        Per-query data collected from a pipeline run.
    far_limit : float
        Maximum acceptable false-accept rate for OOD queries (default 0.10).

    Returns
    -------
    tuple[float, list[dict]]
        ``(best_threshold, list_of_all_threshold_results)``.
    """
    # Build candidate thresholds from actual score distribution
    scores = sorted({d.top_score for d in per_query})
    candidates = [-1.0] + scores + [1.000001]

    results: list[ThresholdResult] = []
    for t in candidates:
        results.append(_compute_threshold_metrics(per_query, t))

    # Filter: only thresholds that meet FAR constraint
    valid = [r for r in results if r.far <= far_limit]

    if not valid:
        # Fallback: threshold with lowest FAR
        logger.warning(
            "No threshold meets FAR ≤ %.2f — falling back to min-FAR threshold",
            far_limit,
        )
        best = min(results, key=lambda r: r.far)
    else:
        best = max(valid, key=lambda r: r.f1)

    logger.info(
        "Selected threshold=%.4f (FAR=%.4f, F1=%.4f, P=%.4f, R=%.4f)",
        best.threshold,
        best.far,
        best.f1,
        best.precision,
        best.recall,
    )

    # Serialize results for the report
    serialized = []
    for r in results:
        d = asdict(r)
        d["far"] = round(d["far"], 6)
        d["precision"] = round(d["precision"], 6)
        d["recall"] = round(d["recall"], 6)
        d["f1"] = round(d["f1"], 6)
        serialized.append(d)

    return best.threshold, serialized


# ---------------------------------------------------------------------------
# Pipeline runner (data collection)
# ---------------------------------------------------------------------------


def create_pipeline(
    reranker_enabled: bool,
) -> Any:
    """Create a RAGPipeline instance with the given config.

    The pipeline is created with a fast mock generator so that calibration
    runs are fast and do not incur DeepSeek API costs.  Only retrieval
    scores and source titles are needed — not the generated answer.
    """
    # Set env vars before importing pipeline (they're read at init time)
    os.environ["RERANKER_ENABLED"] = str(reranker_enabled).lower()

    # Import here so env vars are set before pipeline module internals
    from engine.generator import Generator
    from engine.pipeline import RAGPipeline

    # Fast mock generator that returns immediately (no API call)
    class _FastGenerator(Generator):
        """Generator stub that skips DeepSeek API for fast calibration."""

        def generate(self, *args: Any, **kwargs: Any) -> str:
            return ""

        def generate_stream(self, *args: Any, **kwargs: Any) -> Any:
            yield ""

    # The BM25 retriever loads from disk automatically
    from engine.bm25_retriever import BM25Retriever

    bm25 = BM25Retriever()
    if _AI_DATA.exists():
        bm25.load(str(_AI_DATA))
        logger.info("BM25 loaded from %s (%d docs)", _AI_DATA, bm25.count)
    else:
        logger.warning("BM25 index not found at %s", _AI_DATA)

    pipe = RAGPipeline(generator=_FastGenerator(), bm25_retriever=bm25)

    # Force rejection threshold to 0.0 so all queries pass through
    pipe.retriever.rejection_threshold = 0.0

    return pipe


def collect_per_query_data(
    pipe: Any,
    cases: list[dict[str, Any]],
    top_k: int = 5,
) -> list[PerQueryData]:
    """Run all eval queries through the pipeline and collect per-query data.

    For each query, we capture:
    - The **dense retrieval max score** (threshold candidate)
    - The **hit** outcome (whether gold_title appears in final sources)

    The pipeline runs the full retrieval pipeline (dense → BM25 → RRF →
    optionally reranker) but returns immediately via the fast mock generator.
    """
    results: list[PerQueryData] = []
    total = len(cases)

    for idx, case in enumerate(cases, start=1):
        qid = case.get("id", f"case_{idx}")
        question = case.get("question", "")
        gold = case.get("gold_title_contains", "")
        answerable = case.get("answerable", True)
        group = case.get("group", "")

        logger.info("[%d/%d] %s: %s", idx, total, qid, question[:60])

        try:
            output = pipe.run(query=question, top_k=top_k)
            sources = output.get("sources", [])
            top_score = max((s.get("score", 0.0) for s in sources), default=0.0)
            hit = hit_at_5(sources, gold) if gold else False
        except Exception as exc:
            logger.warning("  → Error for %s: %s", qid, exc)
            top_score = 0.0
            hit = False

        results.append(
            PerQueryData(
                qid=qid,
                answerable=answerable,
                group=group,
                top_score=round(top_score, 6),
                hit=hit,
            )
        )

        logger.info(
            "  → score=%.4f hit=%s ans=%s grp=%s",
            top_score,
            "✓" if hit else "✗",
            answerable,
            group,
        )

    return results


# ---------------------------------------------------------------------------
# Verification round
# ---------------------------------------------------------------------------


def run_verification_eval(
    config_name: str,
    reranker_enabled: bool,
    threshold: float,
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run a full eval at the given threshold to verify calibration.

    This uses the real pipeline (with mock generator).  We report the
    Hit@5 for answerable queries and OOD rejection rate.
    """
    logger.info(
        "Verification round for %s at threshold=%.4f",
        config_name,
        threshold,
    )

    pipe = create_pipeline(reranker_enabled)
    pipe.retriever.rejection_threshold = threshold

    per_query = collect_per_query_data(pipe, cases)
    answerable = [d for d in per_query if d.answerable]
    ood = [d for d in per_query if not d.answerable]

    hit_rate = sum(d.hit for d in answerable) / len(answerable) if answerable else 0.0
    ood_rejected = sum(1 for d in ood if d.top_score < threshold)
    ood_rejection = ood_rejected / len(ood) if ood else 0.0

    logger.info(
        "Verification: Hit@5=%.4f (%d/%d), OOD reject=%.4f (%d/%d)",
        hit_rate,
        sum(d.hit for d in answerable),
        len(answerable),
        ood_rejection,
        ood_rejected,
        len(ood),
    )

    return {
        "config": config_name,
        "threshold": threshold,
        "hit_at_5": round(hit_rate, 4),
        "hit_detail": f"{sum(d.hit for d in answerable)}/{len(answerable)}",
        "ood_rejection_rate": round(ood_rejection, 4),
        "ood_rejection_detail": f"{ood_rejected}/{len(ood)}",
        "total_answerable": len(answerable),
        "total_ood": len(ood),
        "per_query": [
            {
                "qid": d.qid,
                "answerable": d.answerable,
                "top_score": d.top_score,
                "hit": d.hit,
            }
            for d in per_query
        ],
    }


# ---------------------------------------------------------------------------
# Calibration orchestration
# ---------------------------------------------------------------------------


def calibrate_config(
    config_name: str,
    config_spec: dict[str, Any],
    cases: list[dict[str, Any]],
    far_limit: float = 0.10,
) -> ConfigResult:
    """Run full calibration for one pipeline configuration (max 3 rounds).

    1. Round 1: collect per-query data at threshold=0.0, find optimal threshold.
    2. Round 2: verify with optimal threshold.
    3. Round 3: fine-tune if FAR constraint not met (rare).
    """
    logger.info("=" * 60)
    logger.info("Calibrating config: %s", config_name)
    logger.info("  %s", config_spec["description"])
    logger.info("=" * 60)

    config_result = ConfigResult(
        config_name=config_name,
        description=config_spec["description"],
    )

    # ---- Round 1: Data collection ----
    logger.info("\n--- Round 1: Data collection (threshold=0.0) ---")
    pipe = create_pipeline(reranker_enabled=config_spec["reranker_enabled"])
    per_query = collect_per_query_data(pipe, cases)

    logger.info("\n--- Score distribution ---")
    scores = [d.top_score for d in per_query]
    logger.info("  Range: [%.4f, %.4f]", min(scores), max(scores))
    for d in per_query:
        logger.info("  %-8s ans=%-5s score=%.4f hit=%s", d.qid, d.answerable, d.top_score, d.hit)

    answerable = [d for d in per_query if d.answerable]
    ood = [d for d in per_query if not d.answerable]
    logger.info(
        "\nRound 1 summary: %d answerable, %d OOD | Hit@5=%.4f (%d/%d)",
        len(answerable),
        len(ood),
        sum(d.hit for d in answerable) / len(answerable) if answerable else 0.0,
        sum(d.hit for d in answerable),
        len(answerable),
    )

    # Compute best threshold from collected data
    best_threshold, threshold_results = select_best_threshold(per_query, far_limit)
    hit_at_5_best = (
        sum(1 for d in answerable if d.top_score >= best_threshold and d.hit)
        / sum(1 for d in answerable if d.top_score >= best_threshold)
        if sum(1 for d in answerable if d.top_score >= best_threshold) > 0
        else 0.0
    )

    round1 = CalibrationRound(
        round_num=1,
        config_name=config_name,
        per_query=[asdict(d) for d in per_query],
        thresholds=threshold_results,
        best_threshold=best_threshold,
        hit_at_5_at_best=hit_at_5_best,
    )
    config_result.rounds.append(round1)

    # ---- Round 2: Verification ----
    logger.info("\n--- Round 2: Verification at threshold=%.4f ---", best_threshold)
    pipe2 = create_pipeline(reranker_enabled=config_spec["reranker_enabled"])
    pipe2.retriever.rejection_threshold = best_threshold
    per_query2 = collect_per_query_data(pipe2, cases)

    answerable2 = [d for d in per_query2 if d.answerable]
    ood2 = [d for d in per_query2 if not d.answerable]
    hit_at_5_vfy = (
        sum(d.hit for d in answerable2) / len(answerable2) if answerable2 else 0.0
    )
    ood_rejected_vfy = sum(1 for d in ood2 if d.top_score < best_threshold)
    ood_accept_vfy = sum(1 for d in ood2 if d.top_score >= best_threshold)

    logger.info(
        "Verified: Hit@5=%.4f (%d/%d), OOD rejected=%d/%d (FAR=%.4f)",
        hit_at_5_vfy,
        sum(d.hit for d in answerable2),
        len(answerable2),
        ood_rejected_vfy,
        len(ood2),
        ood_accept_vfy / len(ood2) if ood2 else 0.0,
    )

    round2 = CalibrationRound(
        round_num=2,
        config_name=config_name,
        per_query=[asdict(d) for d in per_query2],
        thresholds=[],
        best_threshold=best_threshold,
        hit_at_5_at_best=hit_at_5_vfy,
    )
    config_result.rounds.append(round2)

    # ---- Round 3: Fine-tune (only if FAR constraint violated) ----
    if ood2 and (ood_accept_vfy / len(ood2)) > far_limit:
        logger.warning(
            "FAR=%.4f exceeds limit %.2f — running Round 3 fine-tune",
            ood_accept_vfy / len(ood2),
            far_limit,
        )

        # Re-calibrate on Round 2 data
        per_query2_data = [
            PerQueryData(
                qid=d.qid,
                answerable=d.answerable,
                group=d.group,
                top_score=d.top_score,
                hit=d.hit,
            )
            for d in per_query2
        ]
        refined_threshold, _ = select_best_threshold(
            per_query2_data, far_limit
        )

        pipe3 = create_pipeline(reranker_enabled=config_spec["reranker_enabled"])
        pipe3.retriever.rejection_threshold = refined_threshold
        per_query3 = collect_per_query_data(pipe3, cases)

        answerable3 = [d for d in per_query3 if d.answerable]
        ood3 = [d for d in per_query3 if not d.answerable]
        hit_at_5_r3 = (
            sum(d.hit for d in answerable3) / len(answerable3) if answerable3 else 0.0
        )

        round3 = CalibrationRound(
            round_num=3,
            config_name=config_name,
            per_query=[asdict(d) for d in per_query3],
            thresholds=[],
            best_threshold=refined_threshold,
            hit_at_5_at_best=hit_at_5_r3,
        )
        config_result.rounds.append(round3)
        config_result.final_threshold = refined_threshold
        config_result.final_hit_at_5 = hit_at_5_r3

        logger.info(
            "Fine-tuned threshold: %.4f → Hit@5=%.4f",
            refined_threshold,
            hit_at_5_r3,
        )
    else:
        config_result.final_threshold = best_threshold
        config_result.final_hit_at_5 = hit_at_5_vfy
        logger.info(
            "FAR constraint met — final threshold=%.4f, Hit@5=%.4f",
            best_threshold,
            hit_at_5_vfy,
        )

    return config_result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def build_report(
    config_results: list[ConfigResult],
    elapsed_s: float,
) -> dict[str, Any]:
    """Build the calibration report dict."""
    report: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "config": {
            "far_limit": 0.10,
            "max_rounds": MAX_ROUNDS,
            "eval_data": str(EVAL_DATA),
            "configs_tested": [cr.config_name for cr in config_results],
        },
        "summary": {
            "total_time_seconds": round(elapsed_s, 2),
            "configs_completed": len(config_results),
        },
        "results": [],
    }

    for cr in config_results:
        cr_dict: dict[str, Any] = {
            "config_name": cr.config_name,
            "description": cr.description,
            "final_threshold": cr.final_threshold,
            "final_hit_at_5": round(cr.final_hit_at_5, 4),
            "rounds": [],
        }
        for rnd in cr.rounds:
            rnd_dict = {
                "round_num": rnd.round_num,
                "best_threshold": rnd.best_threshold,
                "hit_at_5_at_best": round(rnd.hit_at_5_at_best, 4),
                "threshold_sweep": rnd.thresholds,
                "per_query_count": len(rnd.per_query),
                "per_query": rnd.per_query,
            }
            cr_dict["rounds"].append(rnd_dict)
        report["results"].append(cr_dict)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> Any:
    import argparse

    parser = argparse.ArgumentParser(
        description="Calibrate retrieval rejection thresholds for RAG pipeline configs.",
    )
    parser.add_argument(
        "--config",
        choices=list(CONFIGS.keys()) + ["all"],
        default="all",
        help="Which pipeline configuration to calibrate (default: all)",
    )
    parser.add_argument(
        "--far-limit",
        type=float,
        default=0.10,
        help="Maximum OOD false-accept rate (default: 0.10)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(CALIBRATION_REPORT),
        help=f"Output path for calibration report (default: {CALIBRATION_REPORT})",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    t0 = time.time()

    # Load test cases
    cases = load_test_cases(EVAL_DATA)

    # Determine which configs to calibrate
    configs_to_run: dict[str, dict[str, Any]] = {}
    if args.config == "all":
        configs_to_run = dict(CONFIGS)
    else:
        configs_to_run[args.config] = CONFIGS[args.config]

    # Run calibration for each config
    config_results: list[ConfigResult] = []
    for cfg_name, cfg_spec in configs_to_run.items():
        result = calibrate_config(
            config_name=cfg_name,
            config_spec=cfg_spec,
            cases=cases,
            far_limit=args.far_limit,
        )
        config_results.append(result)

    elapsed = time.time() - t0

    # Build and save report
    report = build_report(config_results, elapsed)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("Calibration report saved to %s", output_path)

    # Print summary
    print()
    print("=" * 70)
    print("CALIBRATION SUMMARY")
    print("=" * 70)
    for cr in config_results:
        print(f"  Config: {cr.config_name}")
        print(f"    {cr.description}")
        print(f"    Final threshold: {cr.final_threshold}")
        print(f"    Hit@5 at threshold: {cr.final_hit_at_5:.4f}")
        print(f"    Rounds completed: {len(cr.rounds)}")
        print()
    print(f"  Total time: {elapsed:.1f}s")
    print(f"  Report: {output_path}")
    print("=" * 70)

    # Write recommended thresholds to a sidecar JSON for easy consumption
    recommendations = {}
    for cr in config_results:
        recommendations[cr.config_name] = {
            "threshold": cr.final_threshold,
            "hit_at_5": round(cr.final_hit_at_5, 4),
            "description": cr.description,
        }
    rec_path = output_path.parent / "threshold_recommendations.json"
    with open(rec_path, "w", encoding="utf-8") as f:
        json.dump(recommendations, f, ensure_ascii=False, indent=2)
    logger.info("Threshold recommendations saved to %s", rec_path)


# ---------------------------------------------------------------------------
# Exported API for testing
# ---------------------------------------------------------------------------

__all__ = [
    "PerQueryData",
    "ThresholdResult",
    "load_test_cases",
    "compute_threshold_metrics",
    "select_best_threshold",
    "collect_per_query_data",
    "calibrate_config",
]

# Make compute_threshold_metrics available (prefixed to avoid clash)
compute_threshold_metrics = _compute_threshold_metrics


if __name__ == "__main__":
    main()
