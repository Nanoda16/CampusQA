"""Fair comparison: does the cross-encoder reranker actually help?

The recorded "hybrid vs hybrid+reranker" numbers are NOT comparable:

  hybrid            -> pipeline keeps top-5 chunks          -> hit@5 over 5 items
  hybrid+reranker   -> pipeline truncates to reranker_top_k=3 -> "hit@5" over 3 items

hit@5 is defined as "gold title in the first 5 sources" (eval_metrics.py:72).
On the reranker path only 3 sources ever exist, so the metric silently becomes
hit@3 and is guaranteed to score lower or equal. The earlier conclusion
"the reranker lowers hit@5 by 10 points" is therefore an artefact.

This script measures the SAME candidate pool on both orderings:

  hybrid            RRF ordering,           top-5
  rerank(top5)      cross-encoder ordering, top-5     <- the fair comparison
  rerank(top3)      cross-encoder ordering, top-3     <- what the pipeline does today

It also quantifies a second defect. _rerank_chunks() builds

    candidates = [(c["doc_id"], c["content"]) for c in chunks]      # pipeline.py:198
    score_map  = {cid: score for cid, score in reranked}            # pipeline.py:202

keyed by doc_id while the rest of the pipeline identifies chunks by
chunk_id = f"{doc_id}_{chunk_index}" (fusion.py:108). When one document
contributes several chunks to the candidate list, those chunks share a
doc_id, so score_map collapses them to whichever score came last and every
copy of that doc_id receives the same rerank score. Whether that actually
reorders anything incorrectly is measured below.
"""
import importlib.util
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(r"D:\b1ss\CampusQA")
AI_DIR = ROOT / "ai_service"
EVALS = ROOT / "evals"
sys.path.insert(0, str(AI_DIR))
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-placeholder-not-used")
os.environ["RERANKER_ENABLED"] = "true"

spec = importlib.util.spec_from_file_location("eval_metrics", EVALS / "eval_metrics.py")
em = importlib.util.module_from_spec(spec)
spec.loader.exec_module(em)

from engine.bm25_retriever import BM25Retriever  # noqa: E402
from engine.generator import Generator  # noqa: E402
from engine.pipeline import RAGPipeline  # noqa: E402
from engine.reranker import Reranker  # noqa: E402

AI_DATA = AI_DIR / "data"


class _FastGenerator(Generator):
    def generate(self, *a, **k):
        return ""

    def generate_stream(self, *a, **k):
        yield ""


def load_cases():
    with io.open(EVALS / "campus_qa.jsonl", encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def gold_rank(titles, gold):
    g = (gold or "").lower()
    for i, t in enumerate(titles, 1):
        if g and g in (t or "").lower():
            return i
    return None


def main():
    cases = load_cases()
    bm25 = BM25Retriever()
    bm25.load(str(AI_DATA / "bm25"))
    pipe = RAGPipeline(generator=_FastGenerator(), bm25_retriever=bm25)
    reranker = Reranker()

    # Documents that contribute >1 chunk to a top-5 list are where doc_id
    # keying can collide. Report how often that happens.
    collisions = 0
    stats = {k: {"hit": 0, "rr": 0.0, "n": 0, "ranks": []} for k in ("rrf5", "rk5", "rk3")}
    per_case = []

    for c in cases:
        if not c.get("answerable"):
            continue
        q, gold = c["question"], c.get("gold_title_contains", "")
        chunks = pipe.retriever.retrieve(q, 5, 0.0)
        bm = pipe.bm25_retriever.retrieve(q, 5)
        fused = pipe._reorder_by_fusion(chunks, __import__("engine.fusion", fromlist=["rrf_fuse"]).rrf_fuse(chunks, bm, top_k=5))

        if len({x["doc_id"] for x in fused}) != len(fused):
            collisions += 1

        # --- RRF ordering, top 5 ---
        t_rrf = [x.get("title", "") for x in fused[:5]]

        # --- cross-encoder ordering of the same candidates ---
        cands = [(x["doc_id"], x["content"]) for x in fused]
        ranked = reranker.rerank(q, cands)
        smap = {cid: s for cid, s in ranked}
        ordered = sorted(fused, key=lambda x: smap.get(x["doc_id"], 0.0), reverse=True)
        t_rk5 = [x.get("title", "") for x in ordered[:5]]
        t_rk3 = [x.get("title", "") for x in ordered[:3]]

        for key, titles in (("rrf5", t_rrf), ("rk5", t_rk5), ("rk3", t_rk3)):
            r = gold_rank(titles, gold)
            s = stats[key]
            s["n"] += 1
            if r:
                s["hit"] += 1
                s["rr"] += 1.0 / r
                s["ranks"].append(r)
            else:
                s["ranks"].append(None)

        per_case.append({"id": c["id"], "gold": gold,
                         "rrf5": t_rrf, "rk5": t_rk5, "rk3": t_rk3,
                         "rank_rrf": gold_rank(t_rrf, gold),
                         "rank_rk": gold_rank(t_rk5, gold)})

    print("=" * 72)
    print("FAIR COMPARISON — identical candidate pool, different orderings")
    print("=" * 72)
    print(f"{'ordering':<26} {'hit@k':>8} {'MRR':>9}   k used")
    for key, label, k in (("rrf5", "RRF ordering, top-5", 5),
                          ("rk5", "cross-encoder, top-5", 5),
                          ("rk3", "cross-encoder, top-3", 3)):
        s = stats[key]
        print(f"{label:<26} {s['hit']/s['n']:>8.3f} {s['rr']/s['n']:>9.4f}   (n={s['n']}, k={k})")

    print()
    print(f"cases where >1 chunk of the same doc_id entered the top-5: "
          f"{collisions}/{stats['rrf5']['n']}")
    print("  (doc_id keying in _rerank_chunks only misbehaves when this is > 0)")

    # Did reranking change the gold rank at all?
    moved_up = moved_down = same = lost = 0
    for r in per_case:
        a, b = r["rank_rrf"], r["rank_rk"]
        if a is None and b is None:
            same += 1
        elif a is None and b is not None:
            moved_up += 1
        elif a is not None and b is None:
            lost += 1
        elif a == b:
            same += 1
        elif b < a:
            moved_up += 1
        else:
            moved_down += 1
    print()
    print("gold rank after cross-encoder vs after RRF (top-5 window):")
    print(f"  improved: {moved_up}   unchanged: {same}   worsened: {moved_down}   lost: {lost}")

    out = EVALS / "results" / "nanoda-rerun" / "reranker_fairness.json"
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump({"stats": {k: {kk: vv for kk, vv in v.items() if kk != 'ranks'}
                             for k, v in stats.items()},
                   "doc_id_collisions": collisions,
                   "rank_change": {"improved": moved_up, "unchanged": same,
                                   "worsened": moved_down, "lost": lost},
                   "per_case": per_case}, f, ensure_ascii=False, indent=2)
    print(f"\nsaved: {out}")


if __name__ == "__main__":
    main()
