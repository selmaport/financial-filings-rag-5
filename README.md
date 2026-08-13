# Financial Filings RAG + Variance Analysis

A retrieval system over public SEC filings that pairs **computed financial variances** with **cited management commentary** from the same filing.

**Companies:** Visa (V), Mastercard (MA), American Express (AXP)

Ask "what drove the change in operating margin" and get the number, the driver breakdown, and the exact filing language behind it, with sources you can verify.

**Live demo:** https://selma-payments-filings.streamlit.app

---

## Problem

Financial analysts answer two questions at once. What changed, and why. The first lives in the statement tables. The second lives in the MD&A narrative, dozens of pages away. Most tools do one or the other.

This system does both, and it cites its sources so every answer can be checked against the filing.

## Why these three companies

Visa and Mastercard are open-loop networks. They move money between issuers and acquirers and take a fee. They do not lend, so they carry no consumer credit risk.

American Express is closed-loop. It issues its own cards and holds the receivables, so provisions for credit losses, net interest income, and card member rewards liabilities appear on its statements and have no equivalent at Visa or Mastercard.

Same industry, structurally different economics. That contrast is what makes the variance analysis meaningful rather than mechanical, and the system surfaces it directly: ask why American Express reports credit-loss provisions when Visa does not, and it explains the closed-loop versus open-loop distinction from the filings themselves.

**Fiscal year note.** Mastercard and American Express close December 31. Visa closes September 30. Cross-company comparisons account for this.

## What it does

- Pulls 10-K and 10-Q filings from SEC EDGAR for the three companies
- Extracts structured financial data from SEC XBRL and computes period-over-period variances
- Indexes the full filing text for semantic retrieval
- Returns a grounded answer that pairs the computed figure with the cited management narrative, and declines when the filings do not contain the answer

## Architecture

```
EDGAR XBRL API  ──> parse_financials.py ──> data/financials/   (structured statements)
EDGAR documents ──> fetch_filings.py    ──> data/raw/          (raw 10-K / 10-Q)
                                                 │
                          ┌──────────────────────┴──────────────────────┐
                          ▼                                              ▼
                     variance.py                                   build_index.py
              (YoY change, driver decomposition)          (chunk + embed into ChromaDB)
                          │                                              │
                          │                                        retrieve.py
                          │                               (semantic search + grounded answer)
                          └──────────────────────┬──────────────────────┘
                                                 ▼
                                              app.py
                                     (Streamlit interface, 3 tabs)
```

## Design decisions

| Decision | Choice | Why |
|---|---|---|
| Statement data | SEC XBRL companyfacts API | Structured at the source, avoids fragile HTML table parsing |
| Tag resolution | Ordered preference list per metric, with the matched tag recorded | Filers use different US-GAAP tags. Recording the tag is the audit trail behind each number. |
| Vector store | ChromaDB | Local, no infrastructure, sufficient at this corpus size |
| Indexing | Full filing body, semantic search | See failure analysis. Section-label splitting mislabeled content and hurt retrieval, so the system indexes the whole body and lets meaning find the passage. |
| Embeddings | ChromaDB default, runs locally | Free, no API key, adequate at this corpus size |
| Generation model | Gemini (gemini-3.6-flash), temperature 0 | Free tier, deterministic so behavior is reproducible |

## Evaluation

The system is tested against a fixed set of 34 questions in `eval/eval_set.csv`, spanning six categories:

| Category | What it checks |
|---|---|
| Retrieval | Finds the right passage for a factual question |
| Computation | Returned figure reconciles to the filing |
| Paired | Combines the computed number with the cited narrative |
| Comparative | Reasons across companies (e.g. closed-loop vs open-loop) |
| Refusal | Declines when the answer is not in the filings |
| Adversarial | Rejects false premises instead of agreeing with them |

The refusal and adversarial categories matter most. A system that answers everything confidently, including questions the filings do not support, is not one an analyst can trust. `eval/run_eval.py` runs the set and auto-scores refusal behavior, citation presence, and the computation rows against the structured data.

## Failure analysis

**Section labels were unreliable, and it silently degraded answers.** The first version split each filing into labeled sections (Item 7 MD&A, Item 1A Risk Factors) and tagged every chunk accordingly. In practice the splitter routinely mislabeled MD&A content as risk factors, because 10-K and 10-Q item numbering differs and the table of contents repeats the labels. The visible symptom was the system answering financial-performance questions with "not in the excerpts," even though the answer was in the filing, just hidden under the wrong label. The fix was to stop gating retrieval on fragile labels: index the full filing body and let semantic search find the right passage by meaning. Section became a display hint, not a filter. This removed the false "not in the excerpts" failures on margin and driver questions.

**The model correctly refuses to invent absent data, which reads as a limitation but is the point.** Asking about credit-loss provisions while filtered to Visa returns a refusal, because Visa carries no consumer credit risk and its filings contain nothing to retrieve. The absence is the correct answer. This surfaced a real design principle: the system reports what the filings support, and an honest refusal is more valuable than a fabricated narrative.

**Free-tier rate limits shape usage.** The generation model runs on a small free-tier daily request cap. This is fine for normal interactive use, and `run_eval.py` paces requests to stay within limits, but a large batch evaluation must be spread across the daily quota rather than run all at once.

## Limitations

- Covers only the three companies and the fiscal years in the indexed corpus
- Does not compute segment-level variances
- Runs on a free-tier model with a small daily request cap
- Not investment advice, and not a substitute for reading the filing

## Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then add your Gemini API key
```

## Run

```bash
python -m tests.smoke_test                                    # no key needed, checks the math
python -m src.parse_financials --tickers V,MA,AXP
python -m src.fetch_filings --tickers V,MA,AXP --years 2024,2025
python -m src.build_index
streamlit run app.py
```

## Evaluate

```bash
python -m eval.run_eval
```

## Cost

Runs on free tiers end to end. SEC EDGAR is public and requires no account. Embeddings run locally. Gemini's free tier covers generation. Hosting is Streamlit Community Cloud.

## Tech stack

Python, ChromaDB, Google Gemini, Streamlit, pandas, BeautifulSoup, SEC EDGAR (XBRL + filings).

## Author

Selma Satti
[LinkedIn](https://linkedin.com/in/selma-satti)
