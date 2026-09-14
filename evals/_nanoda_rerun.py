"""Run retrieval-grade evaluation over evals/campus_qa.jsonl.

Why not `python evals/run_baseline.py`:
  run_baseline.py constructs a real Generator (RAGPipeline()), which raises
  without DEEPSEEK_API_KEY.  Since it cannot be constructed, the script cannot
  run at all in this environment.

  But the *retrieval* metrics (hit@5 / MRR@5 / precision@5 / recall@5) are
  computed from `sources[*]["title"]` and never touch the LLM.  So we swap in
  the same `_FastGenerator` stub that evals/calibrate.py already uses
  (see calibrate.py:317) and get byte-identical retrieval results.

Configurations tested (same two as calibrate.py CONFIGS):
  hybrid            Dense + BM25 + RRF, reranker off
  hybrid+reranker   Dense + BM25 + RRF + cross-encoder reranker

Note: "dense-only" is NOT testable -- pipeline.run() always calls
`self.bm25_retriever.retrieve()` unconditionally (pipeline.py:286) and then
RRF-fuses; there is no env toggle to disable BM25.

OOD rejection is measured as "pipeline emitted its rejection template", which
per pipeline.py:293-299 happens when top dense score < REJECTION_THRESHOLD
(default 0.35).  This is stricter than run_baseline.py, which only checks
whether the answer text contains a rejection phrase -- and since the empty
index made *every* query return a rejection, that check reported 0/10 for OOD
even though 10/10 were in fact rejected.
"""
import importlib.util
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(r"D:\b1ss\CampusQA")
AI_DIR = ROOT / "ai_service"
EVALS = ROOT / "evals"
sys.path.insert(0, str(AI_DIR))

os.environ.setdefault("DEEPSEEK_API_KEY", "sk-placeholder-not-used")
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")

# Import the metric functions by path (evals/ is not a package).
spec = importlib.util.spec_from_file_location("eval_metrics", EVALS / "eval_metrics.py")
em = importlib.util.module_from_spec(spec)
spec.loader.exec_module(em)

from engine.bm25_retriever import BM25Retriever  # noqa: E402
from engine.generator import Generator  # noqa: E402
from engine.pipeline import RAGPipeline  # noqa: E402

AI_DATA = AI_DIR / "data"


class _FastGenerator(Generator):
    """Same stub as calibrate.py:317 -- skips the DeepSeek API entirely."""

    def generate(self, *args: Any, **kwargs: Any) -> str:
        return ""

    def generate_stream(self, *args: Any, **kwargs: Any) -> Any:
        yield ""


def load_cases() -> list[dict]:
    path = EVALS / "campus_qa.jsonl"
    with io.open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def make_pipeline(reranker_enabled: bool) -> RAGPipeline:
    os.environ["RERANKER_ENABLED"] = str(reranker_enabled).lower()
    # BM25Retriever.save()/load() take a DIRECTORY containing bm25.pkl +
    # meta.json -- that directory is data/bm25, not data/.
    bm25 = BM25Retriever()
    bm25_dir = AI_DATA / "bm25"
    if bm25_dir.is_dir():
        bm25.load(str(bm25_dir))
    pipe = RAGPipeline(generator=_FastGenerator(), bm25_retriever=bm25)
    pipe.retriever.rejection_threshold = float(os.environ.get("REJECTION_THRESHOLD", "0.35"))
    return pipe


def run_config(name: str, reranker_enabled: bool, cases: list[dict], top_k: int = 5) -> dict:
    print("\n" + "=" * 64)
    print(f"CONFIG: {name}  (reranker={reranker_enabled})")
    print("=" * 64)

    pipe = make_pipeline(reranker_enabled)
    vs_stats = pipe.vector_store.get_stats()
    vs_count = vs_stats.get("total_vectors", "?")
    print(f"vector store count : {vs_count}")
    print(f"bm25 count         : {pipe.bm25_retriever.count}")
    print(f"rejection threshold: {pipe.retriever.rejection_threshold}")

    per_case = []
    for i, case in enumerate(cases, 1):
        query = case["question"]
        history = case.get("history")
        gold = case.get("gold_title_contains", "")
        answerable = case.get("answerable", True)

        t0 = time.perf_counter()
        try:
            result = pipe.run(query=query, top_k=top_k, history=history)
            sources = result.get("sources") or []
            answer = result.get("answer") or ""
            err = None
        except Exception as exc:  # noqa: BLE001
            sources, answer, err = [], "", f"{type(exc).__name__}: {exc}"
        latency = time.perf_counter() - t0

        row = {
            "id": case["id"],
            "group": case.get("group"),
            "answerable": answerable,
            "question": query,
            "source_count": len(sources),
            "top_titles": [s.get("title", "") for s in sources[:5]],
            "hit": em.hit_at_5(sources, gold) if answerable else False,
            "rr": em.reciprocal_rank(sources, gold) if answerable else 0.0,
            "precision": em.precision_at_5(sources, gold) if answerable else 0.0,
            "recall": em.recall_at_5(sources, gold) if answerable else 0.0,
            # aggregate_metrics() reads r["ood_rejected"], not r["rejected"].
            "ood_rejected": em.is_ood_rejected(answer) or len(sources) == 0,
            "latency_s": round(latency, 3),
            "error": err,
        }
        per_case.append(row)

        if i % 10 == 0:
            print(f"  ... {i}/{len(cases)} done")

    metrics = em.aggregate_metrics(per_case)
    metrics["vector_store_count"] = vs_count
    metrics["bm25_count"] = pipe.bm25_retriever.count
    errors = [r for r in per_case if r["error"]]
    if errors:
        metrics["errors"] = len(errors)
        metrics["first_error"] = errors[0]["error"]

    print("-" * 64)
    print(f"hit@5       : {metrics.get('hit_at_5')}  ({metrics.get('hit_at_5_detail')})")
    print(f"MRR@5       : {metrics.get('mrr_at_5')}")
    print(f"precision@5 : {metrics.get('precision_at_5')}")
    print(f"recall@5    : {metrics.get('recall_at_5')}")
    print(f"OOD reject  : {metrics.get('ood_rejection_rate')}  ({metrics.get('ood_rejection_detail')})")
    print(f"avg latency : {metrics.get('avg_latency_s')} s")

    return {"config": name, "reranker_enabled": reranker_enabled,
            "metrics": metrics, "per_case": per_case}


def main() -> None:
    cases = load_cases()
    print(f"Loaded {len(cases)} test cases")
    answerable = [c for c in cases if c.get("answerable")]
    ood = [c for c in cases if not c.get("answerable")]
    print(f"  answerable: {len(answerable)}   ood: {len(ood)}")

    results = []
    for name, reranker in (("hybrid", False), ("hybrid+reranker", True)):
        results.append(run_config(name, reranker, cases))

    out = EVALS / "results" / "nanoda-rerun"
    out.mkdir(parents=True, exist_ok=True)
    for r in results:
        safe = r["config"].replace("+", "_")
        with io.open(out / f"{safe}.json", "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 64)
    print("SUMMARY")
    print("=" * 64)
    print(f"{'config':<20} {'hit@5':>8} {'MRR@5':>8} {'P@5':>8} {'R@5':>8} {'OOD':>8}")
    for r in results:
        m = r["metrics"]
        print(f"{r['config']:<20} {str(m.get('hit_at_5')):>8} {str(m.get('mrr_at_5')):>8} "
              f"{str(m.get('precision_at_5')):>8} {str(m.get('recall_at_5')):>8} "
              f"{str(m.get('ood_rejection_rate')):>8}")
    print(f"\nsaved to: {out}")


if __name__ == "__main__":
    main()
