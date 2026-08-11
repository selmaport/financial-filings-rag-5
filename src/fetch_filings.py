"""Pull 10-K and 10-Q filings from SEC EDGAR.

EDGAR is free and requires no key. It does require a User-Agent header
identifying you, or it will block the request. Set SEC_USER_AGENT in .env.

Usage:
    python -m src.fetch_filings --tickers ULTA,ELF --years 2023,2024
"""

import argparse
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

RAW_DIR = Path("data/raw")
HEADERS = {"User-Agent": os.getenv("SEC_USER_AGENT", "student research example@example.com")}
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"


def get_cik(ticker: str) -> str:
    """Look up the zero-padded CIK for a ticker."""
    resp = requests.get(TICKER_MAP_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    for entry in resp.json().values():
        if entry["ticker"].upper() == ticker.upper():
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"Ticker not found in EDGAR map: {ticker}")


def list_filings(cik: str, forms=("10-K", "10-Q")) -> list[dict]:
    """Return recent filings of the given form types for a CIK."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    recent = resp.json()["filings"]["recent"]

    out = []
    for i, form in enumerate(recent["form"]):
        if form in forms:
            out.append({
                "form": form,
                "filing_date": recent["filingDate"][i],
                "accession": recent["accessionNumber"][i].replace("-", ""),
                "document": recent["primaryDocument"][i],
            })
    return out


def download(cik: str, ticker: str, filing: dict) -> Path:
    """Download one filing document to data/raw/."""
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{filing['accession']}/{filing['document']}"
    )
    dest = RAW_DIR / ticker / f"{filing['filing_date']}_{filing['form']}.html"
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        print(f"  skip (already have) {dest.name}")
        return dest

    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    dest.write_text(resp.text, encoding="utf-8")
    print(f"  saved {dest.name}")
    time.sleep(0.2)  # EDGAR asks for max 10 requests/sec
    return dest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", required=True, help="Comma separated, e.g. ULTA,ELF")
    parser.add_argument("--years", required=True, help="Comma separated, e.g. 2023,2024")
    args = parser.parse_args()

    years = set(args.years.split(","))

    for ticker in args.tickers.split(","):
        ticker = ticker.strip().upper()
        print(f"\n{ticker}")
        cik = get_cik(ticker)
        filings = [f for f in list_filings(cik) if f["filing_date"][:4] in years]

        if not filings:
            print("  no filings matched those years")
            continue

        manifest = []
        for f in filings:
            path = download(cik, ticker, f)
            manifest.append({**f, "ticker": ticker, "path": str(path)})

        man_path = RAW_DIR / ticker / "manifest.json"
        man_path.write_text(json.dumps(manifest, indent=2))
        print(f"  {len(manifest)} filings, manifest written")


if __name__ == "__main__":
    main()
