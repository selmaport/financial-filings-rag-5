"""Pull structured financial statement data from SEC XBRL.

Design decision worth explaining in an interview.

The obvious approach is parsing financial tables out of the filing HTML.
It is also fragile. Layouts differ per company, per year, and per filer agent.

SEC publishes the same numbers as structured XBRL through the companyfacts
API. Same source, already tagged to US-GAAP concepts, no parsing. Free, no key.

Tradeoff: XBRL tags are inconsistent across companies. Visa reports revenue
under one concept, American Express under another. So this module keeps an
explicit tag-preference list per metric and records which tag actually
matched. That record is the audit trail. Never report a number without it.

Usage:
    python -m src.parse_financials --tickers V,MA,AXP
"""

import argparse
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

OUT_DIR = Path("data/financials")
HEADERS = {"User-Agent": os.getenv("SEC_USER_AGENT", "student research example@example.com")}
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Ordered preference. First tag that exists for the company wins.
# Expand these as you find gaps. Document every addition.
METRIC_TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenuesNetOfInterestExpense",  # American Express caption
    ],
    "operating_income": [
        "OperatingIncomeLoss",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "operating_expenses": [
        "OperatingExpenses",
        "CostsAndExpenses",
        "BenefitsLossesAndExpenses",
    ],
    "total_assets": [
        "Assets",
    ],
    "provision_credit_losses": [
        "ProvisionForLoanLeaseAndOtherLosses",
        "ProvisionForDoubtfulAccounts",
        "ProvisionForCreditLossesExpenseReversal",
    ],
    "interest_income_net": [
        "InterestIncomeExpenseNet",
        "InterestIncomeExpenseAfterProvisionForLoanLoss",
    ],
}


def get_cik(ticker: str) -> str:
    resp = requests.get(
        "https://www.sec.gov/files/company_tickers.json", headers=HEADERS, timeout=30
    )
    resp.raise_for_status()
    for entry in resp.json().values():
        if entry["ticker"].upper() == ticker.upper():
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"Ticker not found in EDGAR map: {ticker}")


def fetch_facts(cik: str) -> dict:
    resp = requests.get(FACTS_URL.format(cik=cik), headers=HEADERS, timeout=60)
    resp.raise_for_status()
    time.sleep(0.2)  # EDGAR asks for max 10 requests/sec
    return resp.json()


def annual_values(facts: dict, tag: str) -> list[dict]:
    """Return annual (10-K, full year) USD values for one US-GAAP tag."""
    node = facts.get("facts", {}).get("us-gaap", {}).get(tag)
    if not node:
        return []

    units = node.get("units", {}).get("USD", [])
    rows = []
    for u in units:
        if u.get("form") != "10-K" or u.get("fp") != "FY":
            continue
        # Income statement items have a start date. Balance sheet items do not.
        if "start" in u:
            days = (pd.Timestamp(u["end"]) - pd.Timestamp(u["start"])).days
            if not 330 <= days <= 400:  # keep full years only, drop quarters
                continue
        rows.append({
            "fiscal_year": u["fy"],
            "period_end": u["end"],
            "value": u["val"],
            "tag_used": tag,
            "accession": u.get("accn"),
        })

    # Filings restate. Keep the most recently filed value per fiscal year.
    if not rows:
        return []
    df = pd.DataFrame(rows).sort_values("accession").drop_duplicates("fiscal_year", keep="last")
    return df.to_dict("records")


def extract(ticker: str) -> pd.DataFrame:
    cik = get_cik(ticker)
    facts = fetch_facts(cik)

    records = []
    for metric, candidate_tags in METRIC_TAGS.items():
        for tag in candidate_tags:
            values = annual_values(facts, tag)
            if values:
                for v in values:
                    records.append({"ticker": ticker, "metric": metric, **v})
                break  # first matching tag wins
        else:
            print(f"  no tag matched for {metric}")

    return pd.DataFrame(records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", required=True, help="Comma separated, e.g. V,MA,AXP")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = []

    for ticker in args.tickers.split(","):
        ticker = ticker.strip().upper()
        print(f"\n{ticker}")
        df = extract(ticker)
        if df.empty:
            print("  nothing extracted")
            continue
        frames.append(df)
        print(f"  {len(df)} metric-years, "
              f"fiscal years {df['fiscal_year'].min()} to {df['fiscal_year'].max()}")

    if not frames:
        print("\nNothing extracted. Check your SEC_USER_AGENT in .env")
        return

    combined = pd.concat(frames, ignore_index=True)
    out = OUT_DIR / "financials.csv"
    combined.to_csv(out, index=False)
    print(f"\nWrote {len(combined)} rows to {out}")
    print("\nTag audit trail (verify these against the filings before using any number):")
    print(combined.groupby(["ticker", "metric"])["tag_used"].first().to_string())


if __name__ == "__main__":
    main()
