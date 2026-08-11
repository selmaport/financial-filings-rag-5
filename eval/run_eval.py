"""Run the eval set and write scored results.

The scoring here is intentionally partly manual. Automated grading of
open-ended financial answers is unreliable, and claiming an automated
score you cannot defend is worse than a smaller honest one.

Automated:  refusal behavior, citation presence, retrieval hit rate
Manual:     factual correctness, citation support

Usage:
    python eval/run_eval.py               # run and write results
    python eval/run_eval.py --summary     # summarize a graded results file
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EVAL_SET = Path(__file__).parent / "eval_set.csv"
RESULTS = Path(__file__).parent / "results.csv"

REFUSAL_MARKERS = [
    "do not contain", "does not contain", "not in the excerpts",
    "cannot answer", "no information", "not provided", "unable to determine",
]


def looks_like_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def has_citation(text: str) -> bool:
    return bool(re.search(r"\[\d+\]", text))


def retrieval_hit(passages: list[dict], expected_section: str) -> bool | None:
    """Did the expected section appear in the retrieved set?"""
    if not expected_section or pd.isna(expected_section):
        return None
    return any(p["metadata"].get("section") == expected_section for p in passages)


def run():
    from src.retrieve import answer

    df = pd.read_csv(EVAL_SET)
    rows = []

    for _, item in df.iterrows():
        print(f"[{item['id']:>3}] {item['category']:<12} {item['question'][:60]}")
        try:
            result = answer(item["question"], ticker=item.get("ticker"))
            text, passages = result["answer"], result["passages"]
        except Exception as e:
            text, passages = f"ERROR: {e}", []

        should_refuse = str(item["should_refuse"]).strip().upper() == "TRUE"
        refused = looks_like_refusal(text)

        rows.append({
            "id": item["id"],
            "category": item["category"],
            "question": item["question"],
            "expected_answer": item.get("expected_answer"),
            "system_answer": text,
            "should_refuse": should_refuse,
            "did_refuse": refused,
            "refusal_correct": refused == should_refuse,
            "has_citation": has_citation(text),
            "retrieval_hit": retrieval_hit(passages, item.get("expected_section")),
            "sources": " | ".join(
                f"{p['metadata']['ticker']} {p['metadata']['filing_date']} {p['metadata']['section']}"
                for p in passages
            ),
            # Grade these two by hand after the run
            "factually_correct": "",
            "citation_supports_claim": "",
        })

    out = pd.DataFrame(rows)
    out.to_csv(RESULTS, index=False)
    print(f"\nWrote {len(out)} results to {RESULTS}")
    print("Now open it and fill in factually_correct and citation_supports_claim.")
    summarize(out)


def summarize(df: pd.DataFrame | None = None):
    if df is None:
        df = pd.read_csv(RESULTS)

    print("\n" + "=" * 46)
    print("AUTOMATED")
    print(f"  Refusal accuracy      {df['refusal_correct'].mean():.1%}")

    answered = df[~df["should_refuse"]]
    if len(answered):
        print(f"  Citation present      {answered['has_citation'].mean():.1%}")

    hits = df["retrieval_hit"].dropna()
    if len(hits):
        print(f"  Retrieval hit rate    {hits.mean():.1%}")

    print("\nMANUAL (blank until you grade)")
    for col, label in [
        ("factually_correct", "Factual accuracy    "),
        ("citation_supports_claim", "Citation support    "),
    ]:
        graded = df[df[col].astype(str).str.upper().isin(["TRUE", "FALSE"])]
        if len(graded):
            rate = graded[col].astype(str).str.upper().eq("TRUE").mean()
            print(f"  {label}  {rate:.1%}  (n={len(graded)})")
        else:
            print(f"  {label}  not yet graded")
    print("=" * 46)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--summary", action="store_true", help="Summarize existing results.csv")
    args = p.parse_args()
    summarize() if args.summary else run()
