"""OOD threshold sweep -- diagnose whether REJECTION_THRESHOLD=0.35 is too low.

Measures, for every eval query, the *top dense similarity score* returned by
Retriever.retrieve().  Then sweeps candidate thresholds and reports, for each:

  FAR   (False Accept Rate) = OOD queries accepted / total OOD
  recall                    = answerable queries accepted / total answerable
  F1                        = harmonic mean

This is the measurement evals/calibrate.py performs, reproduced directly so we
can see the raw score distribution and judge whether a threshold exists that
separates answerable from OOD queries at all.

Why retrieve() and not pipeline.run(): we need the score even when the
retriever decides to reject, and run() discards it.
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

from engine.generator import Generator  # noqa: E402
from engine.pipeline import RAGPipeline  # noqa: E402


class _FastGenerator(Generator):
    def generate(self, *args, **kwargs):
        return ""

    def generate_stream(self, *args, **kwargs):
        yield ""


def load_cases():
    with io.open(EVALS / "campus_qa.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    cases = load_cases()
    pipe = RAGPipeline(generator=_FastGenerator())
    retr = pipe.retriever

    rows = []
    for c in cases:
        # Bypass the threshold to see the raw top score for every query.
        res = retr.retrieve(c["question"], top_k=5, min_score=0.0)
        top = res[0]["score"] if res else 0.0
        rows.append({
            "id": c["id"],
            "group": c.get("group"),
            "answerable": c.get("answerable", True),
            "top_score": round(float(top), 4),
            "n_sources": len(res),
        })

    ans = [r for r in rows if r["answerable"]]
    ood = [r for r in rows if not r["answerable"]]

    print("=" * 66)
    print("TOP DENSE SCORE DISTRIBUTION (threshold bypassed, min_score=0.0)")
    print("=" * 66)
    for label, group in (("ANSWERABLE", ans), ("OOD", ood)):
        scores = sorted(r["top_score"] for r in group)
        if not scores:
            continue
        n = len(scores)
        print(f"\n{label} (n={n})")
        print(f"  min    {scores[0]:.4f}   ({group[[r['top_score'] for r in group].index(scores[0])]['id']})")
        print(f"  median {scores[n // 2]:.4f}")
        print(f"  max    {scores[-1]:.4f}")
        print(f"  all: {[round(s, 3) for s in scores]}")

    print("\n" + "=" * 66)
    print("THRESHOLD SWEEP")
    print("=" * 66)
    cands = [round(0.20 + 0.02 * i, 2) for i in range(31)]  # 0.20 .. 0.80
    print(f"{'T':>6} {'FAR':>8} {'recall':>8} {'prec':>8} {'F1':>8}  ans_pass ood_pass")
    best = None
    for t in cands:
        a_pass = sum(1 for r in ans if r["top_score"] >= t)
        o_pass = sum(1 for r in ood if r["top_score"] >= t)
        far = o_pass / len(ood) if ood else 0.0
        rec = a_pass / len(ans) if ans else 0.0
        prec = a_pass / (a_pass + o_pass) if (a_pass + o_pass) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        mark = ""
        if far <= 0.10 and (best is None or f1 > best[1]):
            best = (t, f1, far, rec)
            mark = "  <-- FAR<=0.10, best F1"
        print(f"{t:>6.2f} {far:>8.3f} {rec:>8.3f} {prec:>8.3f} {f1:>8.3f}  {a_pass:>8} {o_pass:>8}{mark}")

    print("\n" + "=" * 66)
    if best:
        print(f"BEST under FAR<=0.10 : threshold={best[0]}  F1={best[1]:.3f}  "
              f"FAR={best[2]:.3f}  recall={best[3]:.3f}")
    else:
        print("NO threshold achieves FAR<=0.10 -- the score distributions overlap")
        print("too heavily for a single dense-score cut to separate OOD from answerable.")

    # Where is the current 0.35 relative to the distributions?
    print(f"\ncurrent REJECTION_THRESHOLD = 0.35")
    print(f"  answerable accepted: {sum(1 for r in ans if r['top_score'] >= 0.35)}/{len(ans)}")
    print(f"  OOD accepted       : {sum(1 for r in ood if r['top_score'] >= 0.35)}/{len(ood)}")

    out = EVALS / "results" / "nanoda-rerun"
    out.mkdir(parents=True, exist_ok=True)
    with io.open(out / "threshold_sweep.json", "w", encoding="utf-8") as f:
        json.dump({"per_case": rows, "best": best,
                   "current_threshold": 0.35}, f, ensure_ascii=False, indent=2)
    print(f"\nsaved: {out / 'threshold_sweep.json'}")


if __name__ == "__main__":
    main()
