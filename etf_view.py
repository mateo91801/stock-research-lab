"""Beginner-focused ETF view; no corporate lifecycle or CEO scoring."""
from __future__ import annotations
import html
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from etf_research import assessment

def pct(value, precision=2):
    return f"{value * 100:.{precision}f}%" if value is not None else "N/A"

def short_usd(value):
    if value is None:
        return "N/A"
    for scale, suffix in ((1e12,"T"),(1e9,"B"),(1e6,"M")):
        if value >= scale:
            return "USD " + f"{value/scale:,.2f}{suffix}"
    return "USD " + f"{value:,.0f}"

def esc(value):
    return html.escape(str(value or ""))

def show_etf_dashboard(fund):
    results = assessment(fund)
    st.markdown(
        '<div class="sr-card">'
        f'<div class="sr-head">{esc(fund["ticker"])} · EXCHANGE-TRADED FUND</div>'
        f'<div class="sr-hero">{esc(fund["name"])}</div>'
        f'<div class="sr-dim">Last close: {fund["price"]:,.2f} '
        f'{esc(fund["currency"])} · {esc(fund["asof"])}</div>'
        '</div>', unsafe_allow_html=True)
    st.caption("ETFs hold a basket of investments. Their analysis is different from the "
               "company CEO, operating margin, lifecycle and share-price valuation model.")
    cols = st.columns(4)
    labels = [
        ("Last closing price", f'{fund["price"]:,.2f} {fund["currency"]}'),
        ("Annual expense ratio", pct(fund["expense_ratio"])),
        ("Fund assets (AUM)", short_usd(fund["assets"])),
        ("Top 10 concentration", pct(results["top_ten"],1)),
    ]
    for col, (name, value) in zip(cols, labels):
        with col:
            st.metric(name, value)

    st.markdown("#### The numbers, explained")
    st.write("**Expense ratio:** What you pay the fund annually as a share of the investment. "
             "A 0.03% fee works out to about 3 dollars per year for every 10,000 dollars invested. "
             "It is typically reflected within the fund's performance, not billed separately.")
    st.write("**Top ten concentration:** How much of the ETF is invested in its ten largest positions. "
             "Greater concentration can mean bigger swings if those holdings move together.")
    profile = fund.get("profile") or {}
    if profile.get("family"):
        st.write("**Fund family:**", profile["family"])
    if profile.get("category"):
        st.write("**Fund category:**", profile["category"])
    if profile.get("index"):
        st.write("**Reported index:**", profile["index"])
    if profile.get("description"):
        with st.expander("What this ETF invests in (provider description)"):
            st.write(profile["description"])

    st.markdown("### 1 · Historical returns and risk")
    st.caption("Returns are annualized historical changes, not forecasts. "
               "Data gaps are shown as N/A rather than estimated.")
    perf = fund.get("performance") or {}
    for col, years in zip(st.columns(4), (1,3,5,10)):
        result = (perf.get("returns") or {}).get(years)
        with col:
            st.metric(f"{years}-year annualized", f"{result:+.1f}%" if result is not None else "N/A")
    drawdown = perf.get("max_drawdown")
    st.write("**Largest observed historical decline from a prior peak:** " +
             (f"{drawdown:.1f}%" if drawdown is not None else "N/A"))
    st.caption("Return method: " + str(perf.get("method","unavailable")) +
               ". Adjusted prices approximately reflect dividends and splits; "
               "realized returns differ with taxes, timing and trading costs.")
    prices = fund.get("prices")
    if isinstance(prices, pd.DataFrame) and not prices.empty:
        line = prices.get("Adj Close")
        name = "Adjusted closing price"
        if not isinstance(line, pd.Series) or line.dropna().empty:
            line = prices.get("Close")
            name = "Closing price, dividends excluded"
        if isinstance(line, pd.Series):
            line = pd.to_numeric(line, errors="coerce").dropna()
            line = line[line > 0]
            if not line.empty:
                fig = go.Figure(go.Scatter(x=line.index,y=line,name=name,
                                           line=dict(color="#a2f1d5",width=3)))
                fig.update_layout(height=340,margin=dict(t=25,b=35,l=15,r=15),
                                  paper_bgcolor="#141d30",plot_bgcolor="#141d30",
                                  font=dict(color="#f5f8ff",size=13),
                                  xaxis=dict(showgrid=False),
                                  yaxis=dict(gridcolor="#475674",title="Price per share"),
                                  hovermode="x unified")
                st.plotly_chart(fig,use_container_width=True)

    st.markdown("### 2 · Holdings and sector exposure")
    with st.container():
        left,right = st.columns(2)
        with left:
            st.markdown("#### Largest investments")
            holdings = fund.get("holdings") or []
            if holdings:
                table = pd.DataFrame([{"Symbol":r["symbol"],"Holding":r["name"],
                                       "Weight":pct(r["weight"])} for r in holdings[:10]])
                st.dataframe(table,hide_index=True,use_container_width=True)
                if len(holdings)<10:
                    st.info("Fewer than ten weights were available, so concentration is not scored.")
            else:
                st.info("Holdings were not returned by the free provider.")
        with right:
            st.markdown("#### Sectors")
            sectors = fund.get("sectors") or []
            if sectors:
                table = pd.DataFrame([{"Sector":r["name"],"Weight":pct(r["weight"],1)}
                                      for r in sectors])
                st.dataframe(table,hide_index=True,use_container_width=True)
                st.caption("These provider-supplied categories may not add up to exactly 100%.")
            else:
                st.info("Sector weights are not available from the provider.")

    st.markdown("### 3 · Automatic ETF research screen")
    st.markdown(
        '<div class="sr-verdict">'
        '<div class="sr-head">LAB v1.8 · ETF-ONLY EVIDENCE SCREEN</div>'
        f'<div class="sr-verdict-label">{esc(results["verdict"])}</div>'
        f'<div class="sr-verdict-head">Evidence coverage: {esc(results["coverage"])}</div>'
        '</div>', unsafe_allow_html=True)
    for reason in results["reasons"]:
        st.write("•", reason)
    with st.expander("How the ETF screen works · full rules"):
        st.write("For BUY, this starter research model requires: fees at or below 0.10%, "
                 "ten-largest-holdings concentration at or below 40%, and positive five-year "
                 "historical annualized price change. HOLD allows 0.35% fees and 60% concentration "
                 "with positive five-year change. At least 1% fees or 75% concentration yields PASS. "
                 "Incomplete evidence and other cases yield WATCH. "
                 "These thresholds are illustrative, not proven forecasts.")
        st.write(results["note"])
    st.info("**Beginner takeaway:** Low fees are not proof of a bargain. "
            "Before investing, consider your timeframe, risk tolerance, holdings overlap "
            "and the fund's official factsheet.")
    st.caption("Data source: " + fund["source"] + ". Historical performance and composition "
               "may cover different dates. Verify all important figures with the ETF issuer.")
