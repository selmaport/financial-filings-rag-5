"""Run the eval set and write scored results.

Scoring is partly automated, partly manual, on purpose. Automated grading of
open-ended financial answers is unreliable, and a score you cannot defend is
worse than a smaller honest one.

Automated:  refusal behavior, citation presence, and the 8 computation rows
            (net revenue change, margins, etc.) computed directly from
            data/financials/financials.csv
Manual:     factual correctness of the retrieval and paired rows, graded by
            reading the filing once and marking TRUE/FALSE in results.csv

Usage:
    python eval/run_eval.py            # run the system, write results.csv
    python eval/run_eval.py --summary  # re-summarize an already graded file
    python eval/run_eval.py --compute  # just print the computation answers
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EVAL_SET = Path(__file__).parent / "eval_set.csv"
RESULTS = Path(__file__).parent / "results.csv"
FIN_PATH = Path(__file__).resolve().parent.parent / "data" / "financials" / "financials.csv"

REFUSAL_MARKERS = [
    "do not contain", "does not contain", "not in the excerpts",
    "cannot answer", "no information", "not provided", "unable to determine",
    "cannot be made", "not disclosed", "should decline",
]


def looks_like_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def has_citation(text: str) -> bool:
    return bool(re.search(r"\[\d+\]", text))


# ------------------------------------------------------ automatic computations

def _latest_two(fin, ticker, metric):
    sub = fin[(fin["ticker"] == ticker) & (fin["metric"] == metric)]
    sub = sub.sort_values("fiscal_year")
    if len(sub) < 2:
        return None
    prior, current = sub.iloc[-2], sub.iloc[-1]
    return prior["fiscal_year"], prior["value"], current["fiscal_year"], current["value"]


def compute_answers() -> dict:
    """Compute the 8 computation-row expected answers from financials.csv."""
    if not FIN_PATH.exists():
        return {}
    fin = pd.read_csv(FIN_PATH)
    out = {}

    def yoy(ticker, metric):
        r = _latest_two(fin, ticker, metric)
        if not r:
            return None
        py, pv, cy, cv = r
        pct = (cv - pv) / abs(pv) * 100 if pv else None
        pct_s = f"{pct:+.1f}%" if pct is not None else "n/a"
        return f"FY{int(py)} {pv/1e9:,.2f}B to FY{int(cy)} {cv/1e9:,.2f}B ({pct_s})"

    def margin_latest(ticker):
        rev = _latest_two(fin, ticker, "revenue")
        oi = _latest_two(fin, ticker, "operating_income")
        if not rev or not oi:
            return None
        m = oi[3] / rev[3] * 100 if rev[3] else None
        return f"{m:.1f}%" if m is not None else "n/a"

    def margin_change_ppt(ticker):
        rev = _latest_two(fin, ticker, "revenue")
        oi = _latest_two(fin, ticker, "operating_income")
        if not rev or not oi:
            return None
        prior_m = oi[1] / rev[1] * 100 if rev[1] else None
        cur_m = oi[3] / rev[3] * 100 if rev[3] else None
        if prior_m is None or cur_m is None:
            return None
        return f"{cur_m - prior_m:+.1f} ppt (from {prior_m:.1f}% to {cur_m:.1f}%)"

    out[11] = yoy("V", "revenue")
    out[12] = margin_change_ppt("V")
    out[14] = yoy("MA", "revenue")
    out[15] = margin_latest("MA")
    out[16] = yoy("AXP", "revenue")
    out[17] = yoy("AXP", "interest_income_net")

    # provision as % of revenue, latest year, Amex
    r = _latest_two(fin, "AXP", "provision_credit_losses")
    rev = _latest_two(fin, "AXP", "revenue")
    if r and rev and rev[3]:
        out[18] = f"{r[3]/rev[3]*100:.1f}% of revenue (FY{int(r[2])})"

    # client incentives change, Visa, if present
    ci = _latest_two(fin, "V", "client_incentives")
    if ci:
        out[13] = yoy("V", "client_incentives")
    else:
        out[13] = "metric not in financials.csv (client incentives not separately tagged)"

    return {k: v for k, v in out.items() if v is not None}


# --------------------------------------------------------------------- run/grade

def run():
    from src.retrieve import answer

    df = pd.read_csv(EVAL_SET)
    computed = compute_answers()
    rows = []

    for _, item in df.iterrows():
        ident = int(item["id"])
        print(f"[{ident:>3}] {item['category']:<12} {str(item['question'])[:56]}")

        raw_ticker = item.get("ticker")
        tickers = [raw_ticker] if isinstance(raw_ticker, str) and raw_ticker.strip() else None

        try:
            result = answer(str(item["question"]), tickers=tickers)
            text, passages = result["answer"], result["passages"]
        except Exception as e:
            text, passages = f"ERROR: {e}", []

        should_refuse = str(item["should_refuse"]).strip().upper() == "TRUE"
        refused = looks_like_refusal(text)

        expected = item.get("expected_answer")
        if ident in computed:
            expected = computed[ident]  # fill AUTO rows with the real computed value

        rows.append({
            "id": ident,
            "category": item["category"],
            "question": item["question"],
            "expected_answer": expected,
            "system_answer": text,
            "should_refuse": should_refuse,
            "did_refuse": refused,
            "refusal_correct": refused == should_refuse,
            "has_citation": has_citation(text),
            "sources": " | ".join(
                f"{p['metadata']['ticker']} {p['metadata']['filing_date']} {p['metadata']['section']}"
                for p in passages
            ),
            # Grade these by hand for retrieval and paired rows
            "factually_correct": "",
            "citation_supports_claim": "",
        })

    out = pd.DataFrame(rows)
    out.to_csv(RESULTS, index=False)
    print(f"\nWrote {len(out)} results to {RESULTS}")
    print("Open results.csv and mark factually_correct TRUE/FALSE for the")
    print("retrieval and paired rows. Refusal and computation rows are auto-scored.")
    summarize(out)


def summarize(df: pd.DataFrame | None = None):
    if df is None:
        df = pd.read_csv(RESULTS)

    print("\n" + "=" * 50)
    print("AUTOMATED")
    refusal_rows = df[df["should_refuse"] == True]  # noqa: E712
    if len(refusal_rows):
        print(f"  Refusal accuracy      {refusal_rows['refusal_correct'].mean():.0%}  (n={len(refusal_rows)})")

    answered = df[df["should_refuse"] == False]  # noqa: E712
    if len(answered):
        print(f"  Citation present      {answered['has_citation'].mean():.0%}  (n={len(answered)})")

    print("\nMANUAL (blank until you grade)")
    graded = df[df["factually_correct"].astype(str).str.upper().isin(["TRUE", "FALSE"])]
    if len(graded):
        rate = graded["factually_correct"].astype(str).str.upper().eq("TRUE").mean()
        print(f"  Factual accuracy      {rate:.0%}  (n={len(graded)} graded)")
    else:
        print("  Factual accuracy      not yet graded")
    print("=" * 50)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--summary", action="store_true", help="Summarize existing results.csv")
    p.add_argument("--compute", action="store_true", help="Print computed answers and exit")
    args = p.parse_args()

    if args.compute:
        for k, v in sorted(compute_answers().items()):
            print(f"Row {k}: {v}")
    elif args.summary:
        summarize()
    else:
        run()
