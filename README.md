# Financial Filings RAG + Variance Analysis

A retrieval system over public SEC filings that pairs **computed financial variances** with **cited management commentary** from the same filing.

**Companies:** Visa (V), Mastercard (MA), American Express (AXP)

Ask "what drove the change in operating margin" and get the number, the driver breakdown, and the exact filing language behind it.

**Live demo:** _(add Streamlit URL after first deploy)_

---

## Problem

Financial analysts answer two questions at once. What changed, and why. The first lives in the statement tables. The second lives in the MD&A narrative, dozens of pages away. Most tools do one or the other.

This system does both and cites its sources so the answer can be verified against the filing.

## Why these three companies

Visa and Mastercard are open loop networks. They move money between issuers and acquirers and take a fee. They do not lend, so they carry no consumer credit risk.

American Express is closed loop. It issues its own cards and holds the receivables, which means provisions for credit losses, net interest income, and card member rewards liabilities appear on its statements and have no equivalent at Visa or Mastercard.

Same industry, structurally different economics. That contrast is what makes the variance analysis interesting rather than mechanical.

**Fiscal year note.** Mastercard and American Express close December 31. Visa closes September 30. Cross-company comparisons in this system are annotated accordingly.

## What it does

1. Pulls 10-K and 10-Q filings from SEC EDGAR for a defined company set
2. Parses financial statement tables into structured data
3. Computes period-over-period variances with driver decomposition
4. Indexes MD&A and risk factor sections for semantic retrieval
5. Returns a paired answer, the calculated number plus the cited narrative

## Architecture

```
EDGAR XBRL API ──> parse_financials.py ──> data/financials/
EDGAR documents ──> fetch_filings.py ──> data/raw/
                    │                                   │
                    ▼                                   ▼
          (structured statements)                build_index.py
                                                 (MD&A chunks)
                    │                                   │
                    ▼                                   ▼
             variance.py                          retrieve.py
          (YoY, QoQ, drivers)                  (vector search)
                    │                                   │
                    └─────────────────┬─────────────────┘
                                      ▼
                                   app.py
                            (Streamlit interface)
```

_(Replace with a real diagram before this goes on the resume.)_

## Design decisions

| Decision | Choice | Why |
|---|---|---|
| Statement data | SEC XBRL companyfacts API | Structured at source, avoids fragile HTML table parsing |
| Tag resolution | Ordered preference list per metric, tag recorded | Filers use different US-GAAP tags. The record is the audit trail. |
| Vector store | ChromaDB | Local, no infra, sufficient at this corpus size |
| Chunking | Section-aware, ~800 tokens | Filing sections have real semantic boundaries, naive fixed splits break them |
| Embeddings | ChromaDB default, runs locally | Free, no API key, adequate at this corpus size |
| Retrieval count | _(record k after tuning)_ | _(record how you tuned it)_ |
| Generation model | Gemini Flash, temperature 0 | Free tier, deterministic so eval runs are comparable |

## Evaluation

See `eval/`. The system is scored on a fixed question set with known answers.

| Metric | Result | Notes |
|---|---|---|
| Citation accuracy | _(fill in)_ | Cited passage actually supports the claim |
| Variance accuracy | _(fill in)_ | Computed figure reconciles to the filing |
| Retrieval hit rate | _(fill in)_ | Correct section in top-k |
| Refusal accuracy | _(fill in)_ | Correctly declines when the answer is not in the corpus |
| False premise handling | _(fill in)_ | Corrects rather than agrees with unsupported premises |

34 questions across six categories. Retrieval, computation, paired, comparative, refusal, and adversarial. The last two matter most. A system that answers everything confidently is not a system an analyst can use.

## Failure analysis

_(Write this as you find them. This section is the most valuable part of the repo. Real examples of what broke and what you did about it.)_

## Limitations

- Covers only the companies and periods in the indexed corpus
- Table parsing is fragile on non-standard statement layouts
- Does not compute segment-level variances
- Not investment advice, and not a substitute for reading the filing

## Setup

See **SETUP.md** for the step by step version.

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then add your API key
```

## Run

```bash
python -m tests.smoke_test                                    # no key needed
python -m src.parse_financials --tickers V,MA,AXP
python -m src.fetch_filings --tickers V,MA,AXP --years 2024,2025
python -m src.build_index
streamlit run app.py
```

## Evaluate

```bash
python eval/run_eval.py
```

## Cost

Runs on free tiers end to end. SEC EDGAR is public and requires no account. Embeddings run locally. Gemini's free tier covers generation. Hosting is Streamlit Community Cloud.

## Roadmap

- [ ] Segment-level variance decomposition
- [ ] Multi-company comparison view
- [ ] Expand eval set from 34 to 60 questions
- [ ] Add a second industry for cross-sector comparison

## Author

Selma Satti
