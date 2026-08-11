"""Streamlit interface.

Run locally:  streamlit run app.py
Deploy:       push to GitHub, then connect the repo at share.streamlit.io
"""

import streamlit as st

from src.variance import decompose_gross_margin

st.set_page_config(page_title="Filing Analysis", layout="wide")

st.title("Financial Filings RAG + Variance Analysis")
st.caption("Computed variances paired with cited management commentary from SEC filings.")

tab_ask, tab_variance = st.tabs(["Ask the filings", "Variance calculator"])


with tab_ask:
    ticker = st.text_input("Ticker filter (optional)", placeholder="ULTA")
    query = st.text_input(
        "Question",
        placeholder="What drove the change in gross margin year over year?",
    )
    k = st.slider("Passages to retrieve", 3, 10, 5)

    if st.button("Ask", type="primary") and query:
        with st.spinner("Retrieving..."):
            try:
                from src.retrieve import answer
                result = answer(query, ticker=ticker.upper() or None, k=k)
            except Exception as e:
                st.error(f"Index not built yet, or API key missing. ({e})")
                st.stop()

        st.markdown(result["answer"])

        with st.expander(f"Retrieved passages ({len(result['passages'])})"):
            for i, p in enumerate(result["passages"], start=1):
                m = p["metadata"]
                st.markdown(
                    f"**[{i}]** {m['ticker']} {m['form']} filed {m['filing_date']} "
                    f"| section: {m['section']} | distance: {p['distance']:.3f}"
                )
                st.text(p["text"][:1200] + "...")
                st.divider()


with tab_variance:
    st.subheader("Gross margin decomposition")
    st.caption("Splits the gross profit change into a volume effect and a rate effect.")

    left, right = st.columns(2)
    with left:
        st.markdown("**Prior period**")
        pr = st.number_input("Revenue", value=1000.0, key="pr")
        pc = st.number_input("COGS", value=600.0, key="pc")
    with right:
        st.markdown("**Current period**")
        cr = st.number_input("Revenue", value=1200.0, key="cr")
        cc = st.number_input("COGS", value=680.0, key="cc")

    if st.button("Decompose", type="primary"):
        try:
            r = decompose_gross_margin(pr, pc, cr, cc)
        except ValueError as e:
            st.error(str(e))
            st.stop()

        a, b, c = st.columns(3)
        a.metric("Total change", f"{r['total_change']:,.0f}")
        b.metric("Volume effect", f"{r['volume_effect']:,.0f}")
        c.metric("Rate effect", f"{r['rate_effect']:,.0f}")

        st.write(
            f"Margin moved from {r['prior_margin_pct']:.2f}% "
            f"to {r['current_margin_pct']:.2f}%."
        )

        if abs(r["residual"]) > 0.01:
            st.warning(f"Decomposition does not reconcile. Residual {r['residual']:,.2f}")
        else:
            st.success("Effects reconcile to the total change.")
