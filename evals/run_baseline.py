"""
Baseline evaluation script.
Loads campus_qa.jsonl, runs each question through the RAGPipeline,
saves results to baseline_results.json.
"""
from __future__ import annotations

import json
import os
import sys
import time

# Make engine modules importable
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_AI_DIR = os.path.join(_THIS_DIR, "..", "ai_service")
if _AI_DIR not in sys.path:
    sys.path.insert(0, _AI_DIR)

from engine.pipeline import RAGPipeline

# ---------------------------------------------------------------------------
# Load test data
# ---------------------------------------------------------------------------

data_path = os.path.join(_THIS_DIR, "campus_qa.jsonl")
with open(data_path, encoding="utf-8") as f:
    cases = [json.loads(line) for line in f if line.strip()]

print(f"Loaded {len(cases)} test cases")

# ---------------------------------------------------------------------------
# Init pipeline
# ---------------------------------------------------------------------------

print("Initialising pipeline...")
pipeline = RAGPipeline()
print("Pipeline ready.")

# ---------------------------------------------------------------------------
# Run queries
# ---------------------------------------------------------------------------

results = []
latencies = []

for i, case in enumerate(cases):
    cid = case["id"]
    group = case["group"]
    question = case["question"]
    answerable = case["answerable"]

    # For multi-turn, we just run the final question as-is (context in history)
    # The baseline dense-only system doesn't support multi-turn natively
    query = question

    print(f"  [{i+1:2d}/{len(cases)}] {cid}  {query[:60]}...", end="", flush=True)

    t0 = time.time()
    try:
        result = pipeline.run(query=query, top_k=5)
        elapsed = time.time() - t0
        latencies.append(elapsed)

        answer = result.get("answer", "")
        sources = result.get("sources", [])

        results.append({
            "id": cid,
            "group": group,
            "question": question,
            "answerable": answerable,
            "answer": answer,
            "sources": [
                {
                    "title": s.get("title", ""),
                    "score": s.get("score", 0.0),
                    "content_preview": s.get("content", "")[:200],
                }
                for s in sources
            ],
            "source_count": len(sources),
            "latency_s": round(elapsed, 3),
        })
        print(f"  {len(sources)} sources, {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ERROR: {e}")
        results.append({
            "id": cid,
            "group": group,
            "question": question,
            "answerable": answerable,
            "answer": f"ERROR: {e}",
            "sources": [],
            "source_count": 0,
            "latency_s": round(elapsed, 3),
        })

# ---------------------------------------------------------------------------
# Compute baseline metrics
# ---------------------------------------------------------------------------

def compute_hit_at_5(results, cases_lookup):
    """Hit@5: gold_title_contains appears in any source title."""
    hits = 0
    total = 0
    for r in results:
        case = cases_lookup.get(r["id"])
        if not case or not case.get("gold_title_contains"):
            continue
        total += 1
        gold = case["gold_title_contains"]
        titles = [s.get("title", "") for s in r.get("sources", [])]
        if any(gold in t for t in titles):
            hits += 1
    return hits / total if total > 0 else 0.0, hits, total


def compute_mrr_at_5(results, cases_lookup):
    """MRR@5: reciprocal rank of first relevant source."""
    total = 0
    reciprocal_sum = 0.0
    for r in results:
        case = cases_lookup.get(r["id"])
        if not case or not case.get("gold_title_contains"):
            continue
        total += 1
        gold = case["gold_title_contains"]
        titles = [s.get("title", "") for s in r.get("sources", [])]
        found_rank = None
        for rank, t in enumerate(titles, 1):
            if gold in t:
                found_rank = rank
                break
        if found_rank:
            reciprocal_sum += 1.0 / found_rank
    return reciprocal_sum / total if total > 0 else 0.0


def compute_ood_rejection(results, cases_lookup):
    """OOD rejection rate: fraction of OOD queries that return empty/fallback."""
    ood_results = [r for r in results if cases_lookup.get(r["id"], {}).get("group") == "ood"]
    if not ood_results:
        return 0.0, 0, 0
    rejected = 0
    for r in ood_results:
        answer = r.get("answer", "")
        is_fallback = (
            "未找到相关校园信息" in answer
            or "暂未找到" in answer
        )
        if is_fallback:
            rejected += 1
    return rejected / len(ood_results), rejected, len(ood_results)


def compute_precision_at_5(results, cases_lookup):
    """Precision@5: fraction of top-5 sources that mention gold terms."""
    total_precisions = []
    for r in results:
        case = cases_lookup.get(r["id"])
        if not case or not case.get("gold_title_contains"):
            continue
        gold = case["gold_title_contains"]
        titles = [s.get("title", "") for s in r.get("sources", [])[:5]]
        if not titles:
            total_precisions.append(0.0)
            continue
        hits = sum(1 for t in titles if gold in t)
        total_precisions.append(hits / len(titles))
    return sum(total_precisions) / len(total_precisions) if total_precisions else 0.0


# Build lookup
cases_lookup = {c["id"]: c for c in cases}

hit_at_5, hit_num, hit_den = compute_hit_at_5(results, cases_lookup)
mrr_at_5 = compute_mrr_at_5(results, cases_lookup)
precision_at_5 = compute_precision_at_5(results, cases_lookup)
ood_reject, ood_rej, ood_tot = compute_ood_rejection(results, cases_lookup)

metrics = {
    "hit_at_5": round(hit_at_5, 4),
    "hit_at_5_detail": f"{hit_num}/{hit_den}",
    "mrr_at_5": round(mrr_at_5, 4),
    "precision_at_5": round(precision_at_5, 4),
    "ood_rejection_rate": round(ood_reject, 4),
    "ood_rejection_detail": f"{ood_rej}/{ood_tot}",
    "p95_latency_s": round(sorted(latencies)[int(len(latencies) * 0.95)], 3) if latencies else 0,
    "avg_latency_s": round(sum(latencies) / len(latencies), 3) if latencies else 0,
    "total_cases": len(cases),
    "answerable_cases": hit_den,
    "ood_cases": ood_tot,
}

print("\n" + "=" * 60)
print("  BASELINE METRICS (Dense-only)")
print("=" * 60)
for k, v in metrics.items():
    print(f"  {k}: {v}")

# ---------------------------------------------------------------------------
# Save results
# ---------------------------------------------------------------------------

output = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "config": {
        "retrieval": "dense-only (BGE-small-zh + FAISS IndexFlatIP)",
        "generator": "DeepSeek",
        "top_k": 5,
    },
    "metrics": metrics,
    "results": results,
}

output_path = os.path.join(_THIS_DIR, "baseline_results.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\nResults saved to {output_path}")
