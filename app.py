"""Streamlit interface.

Run locally:  streamlit run app.py
Deploy:       push to GitHub, then connect the repo at share.streamlit.io
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.variance import Variance, build_variance_table, flag_material

st.set_page_config(
    page_title="Payments Filings Analysis",
    page_icon="§",
    layout="wide",
)

COMPANIES = {
    "V": "Visa",
    "MA": "Mastercard",
    "AXP": "American Express",
}

RAW_DIR = Path("data/raw")
FIN_PATH = Path("data/financials/financials.csv")

SAMPLE_QUESTIONS = [
    "What drove the change in operating margin?",
    "How did provisions for credit losses change and why?",
    "What does management say about cross-border volume trends?",
    "Why does American Express report credit losses when Visa does not?",
]


# ---------------------------------------------------------------- data loading

@st.cache_data
def load_corpus_stats() -> dict:
    """Count indexed filings per company from the manifests on disk."""
    stats = {"filings": 0, "per_company": {}}
    for ticker in COMPANIES:
        manifest = RAW_DIR / ticker / "manifest.json"
        if manifest.exists():
            n = len(json.loads(manifest.read_text()))
            stats["per_company"][ticker] = n
            stats["filings"] += n
    return stats


@st.cache_data
def load_financials() -> pd.DataFrame:
    if FIN_PATH.exists():
        return pd.read_csv(FIN_PATH)
    return pd.DataFrame()


@st.cache_resource
def ensure_index() -> int:
    """Build the vector index on first launch if it is missing.

    On a fresh deploy the repo ships the filings but not the prebuilt index,
    so the first run builds it once. Streamlit caches the result, so this
    happens a single time per app instance, not per visitor.
    """
    import chromadb

    client = chromadb.PersistentClient(path="data/chroma")
    try:
        existing = client.get_collection("filings").count()
        if existing > 0:
            return existing
    except Exception:
        pass

    with st.spinner("First launch: building the search index from filings. "
                    "This takes a minute and only happens once."):
        from src.build_index import main as build_main
        build_main()

    try:
        return client.get_collection("filings").count()
    except Exception:
        return 0


@st.cache_resource
def index_size() -> int:
    """Chunk count in the vector store, shown as a scale signal."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path="data/chroma")
        return client.get_collection("filings").count()
    except Exception:
        return 0


stats = load_corpus_stats()
fin = load_financials()
chunk_count = ensure_index()


# ---------------------------------------------------------------------- header

st.title("Payments Sector Filings Analysis")
st.markdown(
    "Retrieval and variance analysis over SEC filings for the three major "
    "card networks. Computed figures paired with cited management commentary."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Companies", len(COMPANIES))
c2.metric("Filings indexed", stats["filings"])
c3.metric("Searchable passages", f"{chunk_count:,}")
c4.metric("Fiscal years", "2024 to 2025")

st.caption(
    "Coverage: "
    + "  ·  ".join(
        f"{name} ({stats['per_company'].get(t, 0)} filings)"
        for t, name in COMPANIES.items()
    )
)

st.divider()

tab_ask, tab_variance, tab_data = st.tabs(
    ["Ask the filings", "Variance analysis", "Financial data"]
)


# ------------------------------------------------------------------- ask tab

with tab_ask:
    st.subheader("Ask a question")
    st.write(
        "Every answer is grounded in retrieved filing passages and cites its "
        "sources. The system declines when the filings do not contain the answer."
    )

    # Sample questions load into the editable box below. Tapping one sets the
    # box text; the box stays fully editable so users can tweak or replace it.
    if "question_text" not in st.session_state:
        st.session_state.question_text = ""

    st.caption("Try one of these, then edit it or write your own:")
    cols = st.columns(2)
    for i, q in enumerate(SAMPLE_QUESTIONS):
        if cols[i % 2].button(q, key=f"sample_{i}", width="stretch"):
            st.session_state.question_text = q

    query = st.text_area(
        "Your question",
        key="question_text",
        placeholder="What drove the change in operating margin?",
        height=80,
    )

    companies_picked = st.multiselect(
        "Companies to search (leave empty for all)",
        list(COMPANIES.values()),
        default=[],
        help="Pick any combination. Empty searches all three.",
    )

    k = st.slider("Passages to retrieve", 3, 12, 8)

    if st.button("Ask", type="primary") and query.strip():
        tickers = [t for t, name in COMPANIES.items() if name in companies_picked]
        tickers = tickers or None  # empty means search everything

        with st.spinner("Retrieving filings and generating a grounded answer..."):
            try:
                from src.retrieve import answer
                result = answer(query, tickers=tickers, k=k)
            except Exception as e:
                st.error(f"Index not built yet, or API key missing. ({e})")
                st.stop()

        st.markdown("#### Answer")
        st.markdown(result["answer"])

        passages = result["passages"]
        st.markdown(f"#### Sources ({len(passages)})")

        source_rows = [
            {
                "Ref": f"[{i}]",
                "Company": COMPANIES.get(p["metadata"]["ticker"], p["metadata"]["ticker"]),
                "Form": p["metadata"]["form"],
                "Filed": p["metadata"]["filing_date"],
                "Section": p["metadata"]["section"],
                "Match": f"{1 - p['distance']:.0%}",
            }
            for i, p in enumerate(passages, start=1)
        ]
        st.dataframe(pd.DataFrame(source_rows), hide_index=True, width="stretch")

        for i, p in enumerate(passages, start=1):
            m = p["metadata"]
            with st.expander(
                f"[{i}]  {COMPANIES.get(m['ticker'], m['ticker'])}  ·  "
                f"{m['form']} filed {m['filing_date']}  ·  {m['section']}"
            ):
                st.text(p["text"][:1500] + "...")


# -------------------------------------------------------------- variance tab

with tab_variance:
    st.subheader("Year over year variance")
    st.write(
        "Computed directly from SEC XBRL data. These figures are deterministic "
        "arithmetic, not model output, and reconcile to the filings."
    )

    if fin.empty:
        st.info("Run the financial data step first. See SETUP.md.")
    else:
        company = st.selectbox(
            "Company",
            list(COMPANIES.values()),
            key="var_company",
        )
        ticker = [t for t, n in COMPANIES.items() if n == company][0]

        sub = fin[fin["ticker"] == ticker]
        years = sorted(sub["fiscal_year"].unique())

        if len(years) < 2:
            st.info("Not enough fiscal years available for this company.")
        else:
            cy = st.selectbox("Current fiscal year", years[::-1], key="cy")
            prior_options = [y for y in years if y < cy]
            py = st.selectbox("Prior fiscal year", prior_options[::-1], key="py")

            prior = dict(zip(sub[sub["fiscal_year"] == py]["metric"],
                             sub[sub["fiscal_year"] == py]["value"]))
            current = dict(zip(sub[sub["fiscal_year"] == cy]["metric"],
                               sub[sub["fiscal_year"] == cy]["value"]))

            variances = build_variance_table(prior, current)

            if not variances:
                st.info("No shared metrics between those years.")
            else:
                rows = []
                for v in variances:
                    pct = f"{v.percent:+.1f}%" if v.percent is not None else "n/a"
                    rows.append({
                        "Metric": v.metric.replace("_", " ").title(),
                        f"FY{py}": f"${v.prior/1e9:,.2f}B",
                        f"FY{cy}": f"${v.current/1e9:,.2f}B",
                        "Change": f"${v.absolute/1e9:+,.2f}B",
                        "%": pct,
                    })

                st.markdown(f"#### {company}: FY{py} to FY{cy}")
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

                material = flag_material(variances, threshold_pct=10.0)
                if material:
                    st.markdown("#### Material moves (over 10%)")
                    for v in material:
                        st.markdown(
                            f"- **{v.metric.replace('_', ' ').title()}** "
                            f"moved {v.percent:+.1f}%"
                        )


# ------------------------------------------------------------------ data tab

with tab_data:
    st.subheader("Underlying financial data")
    st.write(
        "Pulled from SEC XBRL. Every figure carries the exact US-GAAP tag it "
        "was sourced from, which is the audit trail behind the analysis."
    )

    if fin.empty:
        st.info("Run the financial data step first. See SETUP.md.")
    else:
        pick = st.multiselect(
            "Companies",
            list(COMPANIES.values()),
            default=list(COMPANIES.values()),
        )
        tickers = [t for t, n in COMPANIES.items() if n in pick]
        view = fin[fin["ticker"].isin(tickers)].copy()
        view["company"] = view["ticker"].map(COMPANIES)
        view["value ($B)"] = (view["value"] / 1e9).round(2)
        view = view[["company", "metric", "fiscal_year", "value ($B)", "tag_used"]]
        view = view.sort_values(["company", "metric", "fiscal_year"])
        st.dataframe(view, hide_index=True, width="stretch")
