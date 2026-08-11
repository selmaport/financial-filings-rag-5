# Setup

Do these in order. Stop at the first thing that breaks and come back with the error.

---

## 1. Open the terminal

Open this folder in VS Code, then press **Ctrl + `** (backtick, above Tab).
A panel opens at the bottom. That is the terminal. Everything below runs there.

Check Python is there.

```
python3 --version
```

Anything 3.10 or higher is fine.

---

## 2. Create the environment

```
python3 -m venv venv
source venv/bin/activate
```

Windows uses `venv\Scripts\activate` instead of the second line.

You will see `(venv)` appear at the start of your prompt. That means it worked.
You need to run the activate line every time you open a new terminal.

---

## 3. Install the packages

```
pip install -r requirements.txt
```

Takes a few minutes. ChromaDB is the slow one.

---

## 4. Verify before going further

```
python -m tests.smoke_test
```

This needs no key and no internet. If it passes, your environment is good
and the variance math is correct. If anything later breaks, you will know
it is not the install.

---

## 5. Get a free Gemini key

Go to **aistudio.google.com**, sign in with Google, click **Get API key**.
No credit card.

---

## 6. Create your .env file

Rename `.env.example` to `.env`, then fill in both lines.

```
GEMINI_API_KEY=paste_your_key_here
SEC_USER_AGENT=Selma Satti youremail@example.com
```

The SEC line must be a real name and real email. EDGAR blocks requests
without it. This is the single most common failure in step 7.

`.env` is already gitignored. Your key never reaches GitHub.

---

## 7. Pull the financial statement data

```
python -m src.parse_financials --tickers V,MA,AXP
```

Writes `data/financials/financials.csv` and prints which XBRL tag matched
each metric. Read that tag list. It is your audit trail.

---

## 8. Pull the filing documents

```
python -m src.fetch_filings --tickers V,MA,AXP --years 2024,2025
```

HTML files land in `data/raw/`. This is the milestone that means setup is done.

---

## 9. Build the search index

```
python -m src.build_index
```

Slow the first time. It downloads a local embedding model, then chunks
and indexes every filing. No API calls, no cost.

---

## 10. Run it

```
streamlit run app.py
```

Opens in your browser. Ask something on the first tab.

---

## 11. Run the eval

```
python eval/run_eval.py
```

Writes `eval/results.csv`. Open it and grade the two manual columns by hand.
Those grades are what make your accuracy numbers defensible.

---

## 12. Deploy

Push to GitHub, then go to **share.streamlit.io** and connect the repo.

Paste your Gemini key into Streamlit's **Secrets** settings in their
dashboard. Not into any file in the repo.

---

## Common errors

| What you see | What it means |
|---|---|
| `403` from EDGAR | Your `SEC_USER_AGENT` is still the placeholder |
| `command not found: python3` | Try `python` instead |
| `no module named src` | You are not in the project folder, or venv is not active |
| `get_collection` fails | You skipped step 9 |
| `API key not valid` | Key is missing from `.env` or has a stray space |
| Streamlit deploy fails | Key not added to Streamlit Secrets |
