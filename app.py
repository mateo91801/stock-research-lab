"""Stock Research Lab | responsive financial research web app."""
from __future__ import annotations
import html
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from analytics import (classify_phase, choose_profit_metric, format_billions,
                       yoy, annual_valuation, valuation_zones, STAGE_NAMES, STAGE_GUIDANCE)
from provider import fetch_stock, align
from valuation_history import monthly_valuation, annual_asfiled_monthly_valuation, distribution_bands
from growth_analysis import cagr, percent_margin, last_two
from valuation_metrics import usable_history
from data_quality import fiscal_year, audit_rows
from chart_helpers import revenue_cash_flow_figure
from valuation_view import valuation_viewport, multiple_figure
from investment_scorecard import analyze as evaluate_investment
from beginner_guide import (lens_notes, selection_explanation, disagreement_explanation,
                            verdict_in_one_sentence, score_coverage, next_steps)
from research_explainer import (fiscal_yoy, headline_reading, growth_reading,
                                margin_reading, valuation_reading,
                                verification_reading, GLOSSARY)

st.set_page_config(page_title="Stock Research Lab", page_icon="📈", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""<style>
:root {color-scheme:dark}
.stApp {background: #0b1020;color:#e4eaf6}
.block-container {max-width:1250px;padding-top:1.3rem;padding-bottom:4rem}
[data-testid="stMetric"] {background:#141d30;border:1px solid #293348;border-radius:13px;padding:1rem}
[data-testid="stMetricLabel"] {color:#a5b5cf}
.stButton>button[kind="primary"]{background:#9bdfc4!important;color:#101d24!important;border:none;border-radius:10px;font-weight:750}
.stButton>button {border-radius:10px}
[data-testid="stTextInput"] input{background:#161f31;color:white}
.sr-card{background:#141d30;border:1px solid #293348;border-radius:16px;padding:18px 22px;margin:12px 0}
.sr-head{font-size:13px;letter-spacing:.13em;color:#90dac4;font-weight:750;text-transform:uppercase}
.sr-hero{font-size:clamp(25px,3vw,41px);font-weight:850;line-height:1.1;margin:8px 0;color:white}
.sr-dim{color:#9caecc;font-size:14px}
.sr-row{display:flex;flex-wrap:wrap;gap:12px;align-items:center}
.sr-pill{border-radius:30px;background:#243447;color:#a8ebd2;padding:7px 12px;font-size:13px;font-weight:700;display:inline-block}
.phase-track{display:flex;gap:5px;flex-wrap:wrap;margin:15px 0 7px}
.phase-stop{flex:1;min-width:105px;padding:15px 8px;border-radius:11px;text-align:center;background:#182337;border:1px solid #2a364b;color:#9daec8;font-weight:650;font-size:12px}
.phase-current{background:#173e37;border-color:#81d9b7;color:white;box-shadow:inset 0 0 0 1px #81d9b7}
/* Version 1.4 readability refresh — higher text contrast at every level */
.stApp {background:#0b1020!important;color:#f5f8ff!important}
.stApp, .stApp p, .stApp li, .stApp label,
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"],
[data-testid="stText"], [data-testid="stWidgetLabel"] {color:#ecf3ff!important}
[data-testid="stCaptionContainer"] p, .stCaption, small {color:#c9d8ee!important}
[data-testid="stMetricLabel"] p, [data-testid="stMetricLabel"] {color:#e0eafd!important;font-weight:680!important}
[data-testid="stMetricValue"] {color:#ffffff!important}
[data-testid="stMetricDelta"] {color:#b6e8d8!important}
[data-baseweb="tab-list"] {gap:1rem;border-bottom:1px solid #42536d}
[data-baseweb="tab"] {color:#dae7fc!important;font-weight:760!important;font-size:1rem!important}
[data-baseweb="tab"]:hover {color:#ffffff!important;background:#1b2944!important}
[data-baseweb="tab"][aria-selected="true"] {color:#ff818b!important}
[data-baseweb="tab-highlight"] {background-color:#ff818b!important}
[data-testid="stRadio"] label {color:#e8f0ff!important;font-weight:650!important}
[data-testid="stExpander"] summary {color:#f8fbff!important;font-weight:700!important;background:#1a2a43!important;border-radius:10px}
[data-testid="stExpander"] summary:hover {background:#263b57!important}
[data-testid="stDataFrame"] {color:#f2f7ff}
[data-testid="stTextInput"] input {background:#1a2840!important;color:#ffffff!important;border-color:#7f9bbb!important}
.sr-head{color:#9df0d5!important}
.sr-dim{color:#d2def3!important}
.sr-pill{color:#dbfff0!important}
.phase-stop{color:#e1ecff!important}
.sr-warning{font-size:13px;color:#dbe8fb}
.sr-section-note{font-size:14px;color:#d9e6f9;font-weight:550}
.sr-kicker{font-size:13px;text-transform:uppercase;letter-spacing:.07em;font-weight:780;color:#b7f4de}
.sr-info{background:#15243b;border:1px solid #485d79;border-radius:12px;padding:16px 20px;margin:10px 0;color:#f3f7ff}
.sr-info p{color:#f0f6ff!important;margin:.35rem 0}
.sr-statline{display:flex;flex-wrap:wrap;gap:18px;padding:10px 0;font-size:15px;font-weight:600;color:#eef6ff}
.sr-loud{color:#ffffff!important;font-weight:800}
/* v1.4: ensure Plotly hover and supplementary text remain legible */
[data-testid="stMetric"] {background:#17253e!important;border:1px solid #506886!important}
[data-testid="stExpander"] details {background:#11213a!important;border:1px solid #4a6481!important}
[data-testid="stInfo"] p {color:#f4f8ff!important}
.sr-note-14{font-size:.92rem;line-height:1.6;color:#e2edff!important}
/* v1.5 high contrast, compact scorecard */
.sr-score-wrap{background:#13243c;border:1px solid #547096;border-radius:14px;padding:17px;margin:12px 0}
.sr-score-row{display:grid;grid-template-columns:minmax(150px,1fr) auto 46px;gap:14px;align-items:center;padding:10px 0;border-bottom:1px solid #32445e}
.sr-score-row:last-child{border-bottom:0}
.sr-score-title{font-weight:700;color:#f2f7ff}
.sr-score-note{font-size:12px;color:#d1e0f7;line-height:1.45}
.sr-score-dots{display:flex;gap:4px}
.sr-score-dot{height:11px;width:24px;min-width:12px;border-radius:4px;background:#344861}
.sr-score-digit{text-align:right;font-weight:850;color:#fff;font-size:17px}
.sr-verdict{border-radius:15px;padding:18px 21px;margin:15px 0;border:1px solid #587494;background:#1b2c47;color:#fff}
.sr-verdict-label{font-size:31px;font-weight:900;letter-spacing:.08em;margin-bottom:5px}
.sr-verdict-head{font-size:18px;font-weight:750;color:white}
.sr-gauge{height:20px;border-radius:8px;position:relative;overflow:visible;background:linear-gradient(90deg,#277d66 0%,#277d66 35%,#957e4a 35%,#957e4a 65%,#8f4d63 65%,#8f4d63 100%);border:1px solid #a1b6ce;margin:14px 0 8px}
.sr-gauge-pointer{position:absolute;top:-6px;height:30px;border-left:3px solid #fff;filter:drop-shadow(0px 0px 3px #101827)}
/* v1.6 beginner valuation explanations; high contrast */
.sr-learning-note{background:#192c46;border:1px solid #587a9e;border-radius:12px;padding:16px 19px;margin:12px 0;color:#f7fbff!important;line-height:1.65}
.sr-lesson-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:13px 0}
.sr-lesson{background:#172943;border:1px solid #526b8b;border-radius:12px;padding:16px;min-width:0}
.sr-lesson-title{font-size:20px;font-weight:850;color:#ffffff!important;margin:4px 0}
.sr-lesson-value{font-size:18px;font-weight:850;color:#fcfcff!important;margin:8px 0 2px}
.sr-lesson-label{font-size:14px;font-weight:750;color:#b9f2de!important}
.sr-lesson-sub{font-size:13px;color:#e1ecff!important;line-height:1.6;margin-top:6px}
.sr-lesson-status{font-size:13px;font-weight:800;color:#f8daa1!important}
@media(max-width:730px){.sr-lesson-list{grid-template-columns:1fr}}
@media(max-width:660px){.sr-score-row{grid-template-columns:minmax(130px,1fr) auto 46px;gap:6px}.sr-score-dot{width:11px;height:10px}}
</style>""", unsafe_allow_html=True)

@st.cache_data(ttl=60*60*3, show_spinner=False)
def cached_fetch(ticker: str, sec_user_agent: str):
    return fetch_stock(ticker, sec_user_agent=sec_user_agent)


def text_card(title, value, subtitle=''):
    st.markdown(f'<div class="sr-card"><div class="sr-head">{html.escape(title)}</div>'
                f'<div class="sr-hero">{html.escape(value)}</div><div class="sr-dim">{html.escape(subtitle)}</div></div>',
                unsafe_allow_html=True)


def chart_theme(fig, height=335):
    fig.update_layout(height=height, margin=dict(l=12,r=18,b=15,t=72),
                      paper_bgcolor='#141d30', plot_bgcolor='#141d30',
                      font=dict(color='#f5f8ff', size=14, family='Arial, sans-serif'),
                      hovermode='x unified',
                      hoverlabel=dict(bgcolor='#1b2b45', bordercolor='#90aacd', font=dict(color='#ffffff',size=13)),
                      legend=dict(orientation='h',y=1.14,x=0, font=dict(color='#f6f9ff',size=15),
                                  bgcolor='rgba(18,28,46,.88)',bordercolor='#4a5d77',borderwidth=1),
                      xaxis=dict(showgrid=False, tickfont=dict(color='#e5eeff',size=12),
                                 title_font=dict(color='#f6f9ff')),
                      yaxis=dict(gridcolor='#475674',zerolinecolor='#536681',
                                 tickfont=dict(color='#e5eeff',size=12), title_font=dict(color='#f6f9ff')))
    return fig


def annual_frame(values):
    rev = values.get('revenue', pd.Series(dtype='float64'))
    # Include all fiscal period ends, so quarantined revenue leaves a gap rather
    # than disappearing and visually connecting unrelated years on line charts.
    dates = sorted({pd.Timestamp(d) for field in ('revenue','operating_income','net_income','ocf','fcf','shares')
                    for d in values.get(field, pd.Series(dtype='float64')).index})
    out = pd.DataFrame({'date': dates})
    for key in ['revenue','operating_income','net_income','ocf','fcf','shares']:
        out[key] = align(values[key], dates) if dates else []
    return out

st.markdown('<div class="sr-head">Independent research dashboard · v1.7</div>', unsafe_allow_html=True)
st.markdown('<div class="sr-hero">Stock Research Lab <span style="color:#94dac2">↗</span></div>', unsafe_allow_html=True)
st.markdown('<div class="sr-dim">Understand the business. Identify its lifecycle. Put today’s valuation in context.</div>', unsafe_allow_html=True)
st.write('')
if 'ticker' not in st.session_state: st.session_state.ticker = 'GOOGL'
with st.form('search', border=False):
    left, right = st.columns([5,1], vertical_alignment='bottom')
    with left:
        ticker = st.text_input('U.S. stock ticker', value=st.session_state.ticker,
                               help='Try GOOGL, AAPL, MSFT, NVDA, COST or BRK-B. Individual companies, not ETFs.')
    with right:
        go_button = st.form_submit_button('Analyze stock', use_container_width=True, type='primary')
    if go_button: st.session_state.ticker = ticker.strip().upper()

with st.expander('Quick examples', expanded=False):
    st.caption('Enter any U.S. company ticker above: GOOGL · AAPL · MSFT · NVDA · COST · AMZN · BRK-B')

try:
    with st.spinner('Fetching market prices and annual financial statements...'):
        try:
            sec_ua = st.secrets.get('SEC_USER_AGENT', '')
        except Exception:
            sec_ua = ''
        d = cached_fetch(st.session_state.ticker, sec_ua)
except Exception as exc:
    st.error(f"Unable to analyze {st.session_state.ticker}: {exc}")
    st.info('The app needs an internet connection. Yahoo may also temporarily throttle free requests. Please retry later.')
    st.stop()

if d.get('sec_status'):
    st.warning('Annual financial-data note: ' + d['sec_status'])
st.caption('Data used: ' + d.get('data_provider', 'Price source unavailable'))

v = d['values']
frame = annual_frame(v)
latest = frame.iloc[-1] if not frame.empty else None
prior = frame.iloc[-2] if len(frame)>=2 else None
metric_name, metric_key = choose_profit_metric(d['sector'],d['industry'])
metric_series = v[metric_key]
years = list(v['revenue'].index)
profit_latest_first = align(metric_series, years)
shares_latest_first = align(v['shares'], years)
rev_latest_first = align(v['revenue'], years)
# FY common dividend: financial statement preferred; price history used as a limited fallback.
dividend_paid = None
if years:
    target = years[0]
    if target in v['dividends'].index and pd.notna(v['dividends'].loc[target]):
        dividend_paid = abs(float(v['dividends'].loc[target]))
    elif isinstance(d['dividends_history'], pd.Series):
        div_hist = d['dividends_history'].copy()
        if getattr(div_hist.index,'tz',None) is not None: div_hist.index = div_hist.index.tz_localize(None)
        if len(div_hist) and div_hist.index.min() <= target - pd.Timedelta(days=365):
            dividend_paid = float(div_hist.loc[(div_hist.index > target-pd.Timedelta(days=365)) & (div_hist.index <= target)].sum())
phase = classify_phase(rev_latest_first, profit_latest_first, dividend_paid,
                       shares_latest_first, metric_name)

st.markdown(f'''<div class="sr-card">
  <div class="sr-head">{html.escape(d['ticker'])} · {html.escape(d['exchange'])}</div>
  <div class="sr-hero">{html.escape(d['company'])}</div>
  <div class="sr-row"><span class="sr-pill">{html.escape(d['industry'] or d['sector'] or 'Company')}</span>
  <span class="sr-dim">Last close: ${d['price_latest']:,.2f} {html.escape(d['currency'])} · {html.escape(d['price_asof'])}</span></div>
</div>''', unsafe_allow_html=True)

mc = st.columns(4)
with mc[0]: st.metric('Last closing price', f"${d['price_latest']:,.2f}")
with mc[1]: st.metric('Latest annual revenue', format_billions(latest['revenue']) if latest is not None else 'N/A')
with mc[2]:
    growth = fiscal_yoy(latest, prior)
    st.metric('Revenue growth (FY)', f'{growth:+.1f}%' if growth is not None else 'N/A')
with mc[3]: st.metric('Operating cash flow (FY)', format_billions(latest['ocf']) if latest is not None else 'N/A')

# v1.4.4: Explain the actual headline readings, without generating any missing data.
with st.container(border=True):
    st.markdown('#### The numbers, explained')
    for title, explanation in headline_reading(latest, prior, d.get('price_latest')):
        st.markdown(f'**{title}:** {explanation}')
    st.caption('Figures describe the latest available source reports. ' 
               'They are not forecasts or recommendations to trade.')

st.write('')
st.markdown('### Business overview')
st.caption('Business profile: Yahoo Finance, SEC business-address metadata, and optional Wikidata reference data. Sources may be incomplete or stale.')
profile = d.get('profile') or {}
col_b1, col_b2 = st.columns([1.7, 1])
with col_b1:
    description = (profile.get('description') or '').strip()
    wikidata_description = (profile.get('wikidata_description') or '').strip()
    if description:
        with st.container(border=True):
            st.markdown('**What this business does**')
            st.write(description)
    elif wikidata_description:
        with st.container(border=True):
            st.markdown('**Community-maintained reference description**')
            st.write(wikidata_description)
            st.caption('From Wikidata (CC0); not SEC-verified. Check the business section of the latest 10-K.')
            if profile.get('wikidata_url'):
                st.markdown(f'[Wikidata record]({profile["wikidata_url"]})')
    else:
        st.info('A verified company description was not returned by the free profile provider. '
                'The financial metrics below are still available.')
with col_b2:
    with st.container(border=True):
        st.markdown('**Company at a glance**')
        st.write('**Sector:** ' + (d.get('sector') or 'Not available'))
        st.write('**Industry:** ' + (d.get('industry') or 'Not available'))
        hq = profile.get('headquarters') or ''
        if hq:
            st.write('**Headquarters (Yahoo):** ' + hq)
        elif profile.get('sec_business_address'):
            st.write('**SEC-reported business address:** ' + profile['sec_business_address'])
            st.caption('This filing address is not independently verified as corporate headquarters.')
        elif profile.get('wikidata_headquarters'):
            st.write('**Possible HQ (Wikidata):** ' + profile['wikidata_headquarters'])
            st.caption('Community-maintained; confirm with the company’s latest 10-K.')
        else:
            st.write('**Headquarters:** Not available')
        employees = profile.get('employees')
        st.write('**Employees (reported):** ' + (f'{int(employees):,}' if isinstance(employees, (int, float)) and pd.notna(employees) and employees >= 0 else 'Not available'))
        website = (profile.get('website') or '').strip()
        if website.startswith(('https://','http://')):
            st.link_button('Company website ↗', website)
with st.expander('Revenue segments & customers — source coverage'):
    st.write('**Segment revenue:** The free standardized financial data powering this version '
             'does not provide a consistent breakdown by product or geographic segment. '
             'We do not estimate segment percentages without a supporting filing.')
    st.write('**Customers:** The business description above may mention customer types, '
             'but we do not automatically infer or rank them.')
    st.caption('Company summaries and employee counts are provider-dependent. '
               'SEC addresses are sourced separately and may differ from headquarters.')
    st.markdown('For a verified segment breakdown, check the company’s latest '
                '[10-K annual filing on SEC EDGAR](https://www.sec.gov/edgar/search/), '
                'especially the business and segment reporting notes.')

st.markdown('### Data quality & source coverage')
audit = d.get('quality_audit')
if audit is None or audit.checked_years == 0:
    st.info('**Unverified:** No annual revenue figures were available to compare. '
            'Review the company’s original filings before relying on growth rates.')
else:
    checked_count = len(audit.verified_years)
    unverified_count = len(audit.unverified_years)
    flagged_count = len(audit.hidden_years)
    if flagged_count:
        st.warning(f'**Discrepancy:** {flagged_count} fiscal year(s) flagged and omitted from revenue-based '
                   'growth and profitability analysis: ' + ', '.join(f'FY{yr}' for yr in audit.hidden_years) + '.')
    if checked_count:
        st.success(f'**Cross-checked:** {checked_count} fiscal year(s) have matching-period SEC and Yahoo '
                   'annual revenue values within 2.5%. This is a source comparison, NOT an independent audit.')
    if unverified_count:
        st.info(f'**Unverified:** {unverified_count} fiscal year(s) lack a usable comparison from a second source. '
                'No automated red flag does NOT mean those years are verified.')
    if not flagged_count and not checked_count and not unverified_count:
        st.info('No revenue verification outcome available; inspect the report and original filings.')
st.caption(verification_reading(audit))
with st.expander('Data-quality report · year-by-year verification and sources'):
    st.write('**What the labels mean:** Cross-checked = matching fiscal periods agree within 2.5% '
             'between SEC and Yahoo; Discrepancy = conflicting or anomalous observation excluded '
             'from revenue-based calculations; Unverified = independent comparison unavailable. '
             'Cross-checking two feeds is not a financial-statement audit.')
    st.write('**Fiscal years:** Periods ending January 1–15 use the preceding calendar year. '
             'The report compares fiscal periods ending within 32 days, not just matching year labels.')
    if audit is not None and audit.statuses:
        st.dataframe(pd.DataFrame(audit.statuses), hide_index=True, use_container_width=True)
    else:
        st.info('No annual revenue comparison records were returned for this stock.')
    if audit is not None and audit.issues:
        st.markdown('**Observations withheld pending review**')
        st.dataframe(pd.DataFrame(audit_rows(audit)), hide_index=True, use_container_width=True)
    else:
        st.caption('No automated anomalies detected in the retrieved values. This does not mean '
                   'every fiscal year has been verified.')
    sources = d.get('annual_sources') or {}
    if sources:
        st.markdown('**Financial metric sources**')
        st.dataframe(pd.DataFrame([{'Metric': k.replace('_',' ').title(), 'Source': src}
                                   for k, src in sources.items()]), hide_index=True, use_container_width=True)
    st.caption('Official SEC annual data are preferred when available. Yahoo is used for '
               'stock prices and an optional annual-revenue cross-check; Wikidata metadata '
               'is never used in valuations. A source can be accurate without a second feed.')
    st.markdown('[Review company 10-K filings on SEC EDGAR](https://www.sec.gov/edgar/search/)')

st.markdown('### 1 · Company lifecycle')
if phase:
    phase_cells = ''.join(f'<div class="phase-stop {"phase-current" if i==phase.stage else ""}">'
                          f'{i}<br>{name}</div>' for i,name in STAGE_NAMES.items())
    st.markdown(f'<div class="phase-track">{phase_cells}</div>', unsafe_allow_html=True)
    a,b=st.columns([1.6,1])
    with a:
        text_card(f'Phase {phase.stage} · {STAGE_NAMES[phase.stage]}',
                  phase.reason, f'Profit metric used: {phase.metric_name}')
    with b:
        watch,method=STAGE_GUIDANCE[phase.stage]
        st.markdown('<div class="sr-card"><div class="sr-head">What to watch</div>'
                    f'<p>{html.escape(watch)}</p><div class="sr-head">Useful valuation lens</div>'
                    f'<p>{html.escape(method)}</p></div>', unsafe_allow_html=True)
    with st.expander('Why this stage? See the underlying decision rules'):
        for item in phase.evidence: st.write('• ' + item)
        st.caption('Order: (1) no revenue two years → Startup; (2) declining revenue two years → Decline; '
                   '(3) common dividends → Capital Return; (4) losses shrinking → Hyper Growth, otherwise Startup; '
                   '(5) profitable and shares shrinking → Capital Return, otherwise Operating Leverage. '
                   'Source: Brian Feroldi’s published Phase Check methodology. '
                   'A missing dividend field may make a classification provisional.')
else:
    st.warning('Insufficient annual revenue or profit data to determine a lifecycle stage reliably.')

st.markdown('### 2 · Business performance')
if not frame.empty:
    tab1, tab2, tab3 = st.tabs(['Revenue & cash flow', 'Profit trends', 'Annual figures'])
    with tab1:
        fig = revenue_cash_flow_figure(frame)
        st.plotly_chart(chart_theme(fig, 555), use_container_width=True)
        st.caption('Two separate USD-billion scales: the upper panel shows revenue, '
                   'and the lower panel shows operating cash flow. '
                   'The heights of the two lines are not directly comparable.')
    with tab2:
        # Keep the profit-trend fiscal-year labels defined inside this tab.
        # v1.4.2 accidentally referenced an undefined `x` and stopped the app.
        x = frame['date'].apply(lambda d: f'FY{fiscal_year(d)}')
        fig=go.Figure()
        fig.add_trace(go.Bar(x=x, y=frame.operating_income/1e9, name='Operating profit', marker_color='#9bdfc4'))
        fig.add_trace(go.Scatter(x=x,y=frame.net_income/1e9,name='Net income',
                                 mode='lines+markers',line=dict(color='#f4c77c',width=3)))
        fig.update_yaxes(title_text='USD billions')
        st.plotly_chart(chart_theme(fig),use_container_width=True)
    with tab3:
        show=frame[['date','revenue','operating_income','net_income','ocf','fcf']].copy()
        show['date']=show.date.dt.strftime('%Y-%m-%d')
        for c in show.columns[1:]: show[c]=show[c].apply(format_billions)
        show.columns=['Fiscal year end','Revenue','Operating profit','Net income','Operating cash flow','Free cash flow']
        st.dataframe(show.iloc[::-1],hide_index=True,use_container_width=True)
    st.caption('Annual figures from the named data provider above. Fiscal-year-end dates are not earnings release dates.')
else:
    st.info('Annual statements not available. For SEC-sourced annual data, configure SEC_USER_AGENT in your Streamlit app secrets with a real contact email. Some companies have limited standardized filings.')

st.markdown('### Growth analysis')
st.caption('Compound annual growth rates (CAGR) use matching fiscal-year periods. '
           'If a year is missing, or earnings start or end at zero/negative values, we show N/A instead of a misleading growth rate.')
if frame.empty:
    st.info('Annual financial statements are required for the growth analysis.')
else:
    revenue_cagrs = {n: cagr(v['revenue'], n) for n in (1, 3, 5)}
    earnings_cagrs = {n: cagr(v['net_income'], n) for n in (1, 3, 5)}
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('#### Revenue growth')
        k1, k2, k3 = st.columns(3)
        for box, n, label in zip([k1,k2,k3], [1,3,5], ['1Y','3Y','5Y']):
            res = revenue_cagrs[n]
            box.metric(f'{label} CAGR', f'{res:+.1f}%' if res is not None else 'N/A')
    with c2:
        st.markdown('#### Net income growth')
        k1, k2, k3 = st.columns(3)
        for box, n, label in zip([k1,k2,k3], [1,3,5], ['1Y','3Y','5Y']):
            res = earnings_cagrs[n]
            box.metric(f'{label} CAGR', f'{res:+.1f}%' if res is not None else 'N/A')
    with st.container(border=True):
        st.markdown('**How to read these growth rates**')
        st.markdown('**Sales:** ' + growth_reading(revenue_cagrs[1], revenue_cagrs[3],
                                                      revenue_cagrs[5], 'revenue'))
        st.markdown('**Earnings:** ' + growth_reading(earnings_cagrs[1], earnings_cagrs[3],
                                                         earnings_cagrs[5], 'net_income'))
        st.caption('CAGR smooths changes between two valid fiscal years. Compare it with actual annual '
                   'results: uneven years can hide behind a single average.')
    st.markdown('#### Latest annual profitability')
    c1, c2, c3 = st.columns(3)
    if latest is not None:
        margins = [percent_margin(latest.get('operating_income'), latest.get('revenue')),
                   percent_margin(latest.get('net_income'), latest.get('revenue')),
                   percent_margin(latest.get('fcf'), latest.get('revenue'))]
        for target,label,value in zip([c1,c2,c3],
                        ['Operating margin','Net income margin','Free cash flow margin'],margins):
            target.metric(label, f'{value:+.1f}%' if value is not None else 'N/A')
    if latest is not None:
        annual_fcf = latest.get('fcf')
        if annual_fcf is not None and pd.notna(annual_fcf):
            st.caption(f'Latest reported/derived fiscal-year free cash flow: '
                       f'**{format_billions(annual_fcf)}**. Method: operating cash flow '
                       'minus reported capital expenditures, or a provider-reported FCF figure.')
        else:
            st.caption('Free cash flow is unavailable because neither a trustworthy '
                       'reported FCF figure nor a matching operating cash flow and '
                       'capital-spending pair could be obtained. Missing capex is not zero.')
    if latest is not None:
        with st.container(border=True):
            st.markdown('**What the profit margins mean, per $100 in sales**')
            for explanation in margin_reading(*margins):
                st.markdown(explanation)
            st.caption('A higher margin is not automatically better across different industries. '
                       'One-time expenses, acquisitions, and accounting choices can change the picture.')
    st.markdown('#### Growth across fiscal years')
    fig_growth=go.Figure()
    gdates=frame['date'].apply(lambda d: f'FY{fiscal_year(d)}')
    fig_growth.add_trace(go.Bar(x=gdates, y=frame.revenue/1e9, name='Revenue (USD billions)',
                                marker_color='#98eacb'))
    fig_growth.update_yaxes(title_text='Annual revenue · USD billions')
    st.plotly_chart(chart_theme(fig_growth, 300),use_container_width=True)
    with st.expander('How CAGR and margins are calculated'):
        st.markdown('**CAGR = (ending value ÷ starting value)^(1 / elapsed years) − 1.** '
                    'We match actual fiscal-year dates rather than assuming consecutive rows '
                    'represent consecutive years. Non-positive starting or ending earnings '
                    'make conventional CAGR unsuitable; those fields display N/A. '
                    '**Profit margin = reported annual profit ÷ annual revenue** '
                    'and **FCF margin = reported free cash flow ÷ annual revenue**. '
                    'Free cash flow may be estimated as operating cash flow minus capital spending.')

valuation_histories = {}
st.markdown('### 3 · Historical P/OCF valuation')
st.caption('Historical price-to-operating-cash-flow (P/OCF) using split-adjusted month-end stock prices.\n\n'
           '**Green / yellow / red compare the stock with its own history, not intrinsic fair value.**')

period_col, foot_col = st.columns([1, 2], vertical_alignment='bottom')
with period_col:
    valuation_period = st.radio('Valuation history', ['5 years', '10 years'], horizontal=True,
                                help='Compare monthly valuation observations within the chosen lookback.')
lookback_years = 5 if valuation_period == '5 years' else 10
with st.spinner('Building filed-date-aware valuation history...'):
    monthly = monthly_valuation(d['prices'], d['splits'], d.get('valuation_facts') or {},
                                years=lookback_years)
bands = distribution_bands(monthly['multiple']) if not monthly.empty else None
valuation_method = 'ttm'
if bands is None:
    # Quarterly SEC histories differ widely by issuer. When the quarterly model
    # lacks coverage, provide an explicitly labeled annual-as-filed monthly
    # chart rather than a false rolling TTM estimate or invented observations.
    annual_monthly = annual_asfiled_monthly_valuation(
        d['prices'], d['splits'], d.get('valuation_facts') or {},
        years=lookback_years)
    annual_bands = distribution_bands(annual_monthly['multiple']) if not annual_monthly.empty else None
    if annual_bands:
        monthly, bands = annual_monthly, annual_bands
        valuation_method = 'filed_annual'
if bands:
    valuation_histories['pocf'] = {'history': monthly, 'method': valuation_method}
    if valuation_method == 'filed_annual':
        st.warning('**Monthly valuation — annual financial denominator.** SEC quarterly data ' 
                   'is insufficient for rolling TTM, so the monthly stock price is divided ' 
                   'by the most recently **filed fiscal-year** operating cash flow. The ' 
                   'denominator updates only after each 10-K filing. This is NOT a ' 
                   'trailing-12-month valuation series.')
    else:
        st.success('**Monthly valuation — rolling TTM operating cash flow.** '
                   'Cash flow updates when the underlying quarterly SEC filings become public.')
    last = monthly.iloc[-1]
    current = float(last['multiple'])
    median = bands['median']
    relative = (current/median-1)*100 if median else 0
    if current > bands['high']:
        level = 'Expensive'
    elif current < bands['low']:
        level = 'Attractive'
    else:
        level = 'Mid-range'
    m1, m2, m3, m4 = st.columns(4)
    m1.metric('Latest monthly P/OCF', f'{current:.1f}×', help=f'Last price date: {last["date"]:%b %d, %Y}; method: {valuation_method}')
    m2.metric(f'{lookback_years}Y historical median', f'{median:.1f}×')
    m3.metric('Relative to median', f'{relative:+.1f}%')
    m4.metric('Historical zone', level)
    with st.expander('In plain English: what does this valuation mean?', expanded=True):
        for explanation in valuation_reading('P/OCF', current, median, level,
                                             valuation_method, len(monthly)):
            st.markdown(explanation)
    x0 = monthly.date.min() - pd.Timedelta(days=10)
    x1 = monthly.date.max() + pd.Timedelta(days=10)
    ceiling = max(1.14 * monthly.multiple.max(), 1.2 * bands['high'])
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=bands['low'], fillcolor='rgba(75,166,116,.25)',
                  line_width=0, annotation_text='HISTORICALLY ATTRACTIVE', annotation_position='bottom right')
    fig.add_hrect(y0=bands['low'], y1=bands['high'], fillcolor='rgba(242,191,82,.18)',
                  line_width=0, annotation_text='MID-RANGE', annotation_position='top right')
    fig.add_hrect(y0=bands['high'], y1=ceiling, fillcolor='rgba(219,102,112,.19)',
                  line_width=0, annotation_text='HISTORICALLY EXPENSIVE', annotation_position='top right')
    fig.add_trace(go.Scatter(x=monthly.date, y=monthly.multiple, name=('Trailing TTM P/OCF' if valuation_method == 'ttm' else 'Last filed FY P/OCF (not TTM)'),
                             mode='lines', line=dict(color='#e5edf8', width=2.5),
                             hovertemplate='%{x|%b %Y}<br>P/OCF %{y:.1f}×<extra></extra>',
                             connectgaps=False))
    fig.add_hline(y=median, line_dash='dot', line_color='#e3c16f',
                  annotation_text=f'Median {median:.1f}×')
    fig.update_yaxes(title_text=('Price / trailing 12-mo OCF' if valuation_method == 'ttm' else 'Price / last filed fiscal-year OCF'), range=[0,ceiling], ticksuffix='×')
    fig.update_xaxes(range=[x0,x1])
    st.plotly_chart(chart_theme(fig,405),use_container_width=True)
    st.caption(f'**{len(monthly)} month-end observations** from {monthly.date.min():%b %Y}–{monthly.date.max():%b %Y}. '
               f'Most recent cash-flow filing: {last["ocf_filed"]:%b %d, %Y} '
               f'(period ended {last["ocf_period_end"]:%b %d, %Y}). '
               'Bands are the 25th/75th percentiles of this selected window. '
               + ('Denominator is most recently SEC-filed ANNUAL operating cash flow (not TTM); '
                  'it changes after a 10-K, not every quarter. ' if valuation_method == 'filed_annual' else
                  'Denominator is SEC-filed trailing 4-quarter operating cash flow. ')
               + 'No data enters the calculation before its SEC filing date.')
    with st.expander('How this monthly valuation works — and its limitations'):
        if valuation_method == 'ttm':
            st.markdown('**Method: trailing 12-month.** Four consecutive fiscal-quarter cash flows '
                        'are combined into TTM cash flow. SEC 10-Q filings usually present '
                        'year-to-date cash flows, so quarters are derived by subtraction.')
        else:
            st.markdown('**Method: last disclosed fiscal-year cash flow (fallback).** '
                        'The closing stock price at each month-end is divided by operating '
                        'cash flow from the most recent 10-K *already filed as of that month*. '
                        'Thus cash flow only updates once per annual filing. This is *not* '
                        'trailing-12-month cash flow and should not be treated as equivalent.')
        st.markdown('Market capitalization is approximated with SEC-filed diluted '
                    'weighted-average shares aligned to the cash-flow period and adjusted '
                    'for subsequent stock splits. Shares are not exact daily share counts.')
        st.markdown('**Important:** Diluted weighted-average shares are not the exact daily outstanding '
                    'share count. SEC filings may be late, incomplete, amended, or use incomparable tags. '
                    'A gap in source data is not filled with invented numbers. '
                    'This is a useful historical *relative-valuation* indicator, not an intrinsic '
                    'fair-value estimate, recommendation to buy or sell, or a validated investment backtest. '
                    'The valuation model is generally unsuitable for banks and some other financial firms.')
else:
    st.info('Not enough SEC-filed quarterly cash flow and share data for a dependable monthly P/OCF '
            f'chart ({len(monthly)} available months; at least 24 needed). We will not invent '
            'a continuous valuation history.')
    if d.get('valuation_status'):
        st.caption('SEC quarterly data note: ' + d['valuation_status'])
    if d.get('valuation_facts'):
        with st.expander('Data coverage diagnostics (no private settings shown)'):
            from valuation_history import trailing_cashflows, share_events, as_filed_annual_events, OCF_TAGS, SHARES_TAGS
            facts = d['valuation_facts']
            st.caption(f'Quarterly TTM cash-flow events: {len(trailing_cashflows(facts))}; '
                       f'quarterly share events: {len(share_events(facts))}; '
                       f'annual operating cash-flow events: {len(as_filed_annual_events(facts, OCF_TAGS, "USD"))}; '
                       f'annual share events: {len(as_filed_annual_events(facts, SHARES_TAGS, "shares"))}. '
                       'If both monthly methods are unavailable, these counts help identify the missing filing data.')
    annual_val = annual_valuation(d['prices'], v['ocf'], v['shares'], d['splits'])
    annual_val = annual_val[(annual_val.multiple>0) & (annual_val.multiple<250)] if not annual_val.empty else annual_val
    if len(annual_val)>=3:
        st.markdown('#### Available annual snapshots (fallback)')
        limits = valuation_zones(annual_val['multiple'])
        if limits:
            fig = go.Figure(go.Scatter(x=annual_val.date, y=annual_val.multiple,
                                       mode='lines+markers', name='Annual P/OCF',
                                       line=dict(color='#9bdfc4',width=3)))
            fig.update_yaxes(title_text='Annual P/OCF',ticksuffix='×')
            st.plotly_chart(chart_theme(fig,315),use_container_width=True)
            st.caption('Annual fiscal-year-end snapshots only—not monthly, not a historical backtest. '
                       'FY-end values might not have been published on that date.')

# Two new, independently sourced valuation lenses. Existing P/OCF retained intact.
st.markdown('### 4 · Additional valuation lenses')
st.caption('P/E and P/FCF use SEC-reported financials and historical month-end prices. '
           'Like the P/OCF chart, the shaded bands reflect **historical relative multiples, '
           'not a calculated fair price**. Negative earnings or FCF are not assigned a multiple.')
tab_pe, tab_pfcf = st.tabs(['Price / earnings (P/E)', 'Price / free cash flow (P/FCF)'])
for metric, tab in [('pe',tab_pe), ('pfcf',tab_pfcf)]:
    with tab:
        metric_label = 'P/E' if metric == 'pe' else 'P/FCF'
        if metric == 'pfcf':
            st.caption('Free cash flow = SEC operating cash flow minus SEC-reported '
                       'payments for property, plant & equipment or productive assets. '
                       'Missing capex is never treated as zero.')
        else:
            st.caption('P/E is estimated as market capitalization divided by '
                       'SEC-reported net income, with diluted weighted-average shares. '
                       'This is an approximation, not exact point-in-time EPS.')
        with st.spinner(f'Calculating {metric_label} valuation history...'):
            hist14, method14 = usable_history(d['prices'], d['splits'],
                                             d.get('valuation_facts') or {},
                                             metric, years=lookback_years)
        limits14 = distribution_bands(hist14['multiple']) if not hist14.empty else None
        if limits14 is None:
            st.info(f'Insufficient filed financial and share-count data for a dependable {metric_label} '
                    f'history: {len(hist14)} month-end observations (24 required). '
                    'This metric will stay unavailable instead of showing a made-up valuation.')
            if metric == 'pfcf':
                st.caption('Some companies disclose capital spending only in custom SEC XBRL tags; '
                           'those cases cannot be automatically reconstructed reliably here.')
        else:
            valuation_histories[metric] = {'history': hist14, 'method': method14}
            if method14 == 'annual':
                st.warning('**Annual filing fallback:** each month uses the most recently FILED '
                           '10-K figures, not true rolling-12-month financials.')
            else:
                st.success('**SEC quarterly TTM:** values update after the underlying '
                           'quarterly or annual filing is public.')
            current14 = float(hist14.iloc[-1]['multiple'])
            median14 = limits14['median']
            zone14 = ('Historically expensive' if current14 > limits14['high'] else
                      'Historically attractive' if current14 < limits14['low'] else 'Mid-range')
            v1,v2,v3 = st.columns(3)
            v1.metric(f'Latest {metric_label}', f'{current14:.1f}×')
            v2.metric('Historical median', f'{median14:.1f}×')
            v3.metric('Relative valuation zone', zone14)
            explanation14 = valuation_reading(metric_label, current14, median14,
                                               zone14, method14, len(hist14))
            st.markdown(explanation14[0])
            with st.expander(f'Explain the {metric_label} history and limitations'):
                st.markdown(explanation14[1])
                if metric == 'pe':
                    st.caption('Small positive earnings can make P/E unusually high. '
                               'A negative earnings figure is not a meaningful positive P/E.')
                else:
                    st.caption('Near-zero free cash flow can produce extreme P/FCF readings; '
                               'negative or unavailable free cash flow cannot support a positive multiple.')
            # v1.4.3: a presentation-only zoom for unusually high P/E or P/FCF
            # readings. The underlying historical series and percentile bands are
            # unchanged; missing or extreme data are NEVER silently replaced.
            viewport14 = valuation_viewport(hist14['multiple'],
                                             limits14['low'], limits14['high'], median14)
            focused14 = False
            if viewport14.has_outlier_focus:
                display_mode14 = st.radio(
                    f'{metric_label} chart view',
                    ['Readable view (high outliers marked)', 'Full range (all values)'],
                    horizontal=True,
                    key=f'valuation_chart_view_{metric}',
                    help='Only the y-axis presentation changes. Every SEC-derived value '
                         'is retained for the median, shaded bands, and metrics.')
                focused14 = display_mode14.startswith('Readable')
            display_top14 = (viewport14.focused_ceiling if focused14 else
                             viewport14.full_ceiling)
            graph14, above_range14 = multiple_figure(
                hist14, metric_label, method14, limits14, display_top14, focused14)
            st.plotly_chart(chart_theme(graph14,350),use_container_width=True,
                            key=f'additional_valuation_{metric}')
            if above_range14:
                st.caption(
                    f'**Readable view:** {above_range14} of {viewport14.total_count} '
                    f'observations exceed the visible {display_top14:.1f}× ceiling. '
                    'Gold ▲ markers show where the hidden high values occur; hover '
                    'over each marker for its actual value, or choose **Full range**. '
                    'The median, bands and valuation classification use ALL observations.')
            elif viewport14.has_outlier_focus:
                st.caption('Full range selected — all observations are displayed, '
                           'including rare spikes potentially caused by very low earnings or cash flow.')
            st.caption(f'{len(hist14)} monthly observations '
                       f'({hist14.date.min():%b %Y}–{hist14.date.max():%b %Y}); '
                       f'most recent earnings/cash-flow filing {hist14.iloc[-1]["denom_filed"]:%b %d, %Y}. '
                       f'Bands represent the 25th–75th percentile of available observations. '
                       'SEC-filed data are never used before their filing date.')
            with st.expander(f'{metric_label}: methods and assumptions'):
                st.markdown('We multiply split-adjusted closing share price by '
                            'SEC-reported diluted weighted-average shares, adjusted for subsequent '
                            'splits, then divide by the positive SEC-reported financial denominator. '
                            'Weighted-average shares are not actual daily market-cap shares. '
                            'For P/FCF, capital spending is **subtracted**, never treated as zero '
                            'when unreported. Quarterly figures are reconstructed from fiscal '
                            'year-to-date filings, and all financial numbers enter only after '
                            'their SEC filing dates. This is a **relative-history research tool**, '
                            'not intrinsic value or an investment recommendation.')

# v1.5: Management snapshot — no inferred CEO tenure, founder status, or moat.
st.markdown('### 5 · Management snapshot')
st.caption('CEO: Yahoo profile with a conservative SEC-filing fallback when available. Leadership information and analyst '
           'estimates are NOT sufficient to assign a management-skill rating.')
management = d.get('management') or {}
ceo = management.get('ceo') or {}
insider_fraction = management.get('insider_fraction')
mg1, mg2, mg3 = st.columns(3)
mg1.metric('CEO', ceo.get('name') or 'Not available')
mg2.metric('CEO title', ceo.get('title') or 'Not available')
mg3.metric('Insider ownership (Yahoo)',
           f'{insider_fraction*100:.1f}%' if isinstance(insider_fraction, (int, float)) else 'Not available')
if ceo.get('name'):
    ceo_source = ceo.get('source') or 'Third-party company profile'
    ceo_asof = f' · filing date {ceo["asof"]}' if ceo.get('asof') else ' · undated provider information'
    if ceo.get('source_url'):
        st.caption(f'**CEO source:** [{ceo_source}]({ceo["source_url"]}){ceo_asof}. '
                   'A filing verifies the executive as of its date—not necessarily today.')
    else:
        st.caption(f'**CEO source:** {ceo_source}{ceo_asof}.')
else:
    st.info('CEO information was not returned by Yahoo or confirmed from a recent accessible '
            'SEC filing. This is a **source-coverage gap**, not a negative management rating. '
            'A valid SEC_USER_AGENT contact in Streamlit Secrets enables the SEC fallback.')
with st.expander('CEO lookup status · why information may be missing', expanded=not bool(ceo.get('name'))):
    st.write(management.get('ceo_lookup_status') or
             'Lookup details are not available from this run. Refresh the stock to retry.')
    st.caption('This reports data availability, not management quality. SEC documents can show '
               'who signed a filing on a given date, but not necessarily who leads the company today.')
    if st.button('Retry CEO lookup · refresh stock data', key='retry_ceo_lookup'):
        cached_fetch.clear()
        st.rerun()
with st.expander('Beginner guide: where the CEO information comes from'):
    st.markdown(
        '**Why does this matter?** Leadership is worth researching, but a CEO name '
        'by itself cannot tell us whether management is good at allocating money '
        'or growing shareholder value.\n\n'
        '**Where the Lab looks:** First, Yahoo Finance company-officer metadata. '
        'If that is unavailable, the Lab checks recent SEC 10-K/10-Q signatures '
        'and signed CEO certification exhibits. Filing-based names are dated: '
        'they verify who signed on that date, **not necessarily today**.\n\n'
        '**Why might a field still say Not available?** Data providers can omit '
        'officers; SEC filings can be unavailable or inaccessible; or an executive '
        'signature may not be clear enough to verify. The Lab deliberately avoids '
        'guessing. Missing CEO or insider-ownership data are **not negative scores**.\n\n'
        '**What to check next:** Open the cited filing or the company investor-relations '
        'leadership page to verify current officeholders. Check a recent proxy '
        'statement (DEF 14A) for executive compensation and ownership.'
    )
if not isinstance(insider_fraction, (int, float)):
    st.caption('Insider ownership is unreported by this feed. The SEC DEF 14A proxy statement '
               'often contains management ownership disclosures, but is not automatically '
               'converted into a current total insider-ownership percentage. '
               '[Review company SEC filings](https://www.sec.gov/edgar/search/).')
results_eps = management.get('earnings_surprises') or []
with st.expander('Earnings-per-share beats and misses · optional Yahoo feed', expanded=bool(results_eps)):
    if results_eps:
        beats = sum(1 for row in results_eps if row.get('beat'))
        misses = sum(1 for row in results_eps if row.get('miss'))
        inline = len(results_eps) - beats - misses
        st.write(f'**{beats} beats · {misses} misses · {inline} in line** out of '
                 f'{len(results_eps)} returned earnings dates with actual and estimated EPS.')
        eps_table = pd.DataFrame(results_eps).rename(columns={
            'date':'Earnings date', 'reported_eps':'Reported EPS',
            'estimate_eps':'Estimated EPS', 'beat':'Beat', 'miss':'Miss'})
        st.dataframe(eps_table, hide_index=True, use_container_width=True)
        st.caption('EPS estimates are not revenue estimates. Different data providers may disagree.')
    else:
        st.info('No usable quarterly EPS surprises were returned; missing results are never counted as misses.')
st.caption('Founder status, tenure, employee ratings, and a defensible moat rating require '
           'additional, source-verified research and are intentionally left unscored.')

st.markdown('### 6 · Automatic investment verdict')
st.caption('An automatic evidence-based research screen, not personalized trading advice. '
           'Valuation zones compare this stock with its own history, not with intrinsic fair value.')
report = evaluate_investment(v, histories=valuation_histories,
                             financial_position=d.get('financial_position'),
                             quality_audit=d.get('quality_audit'),
                             price_asof=d.get('price_asof'),
                             sector=d.get('sector', ''), industry=d.get('industry', ''))
verdict_color = {'BUY':'#9ce4ba', 'WATCH':'#f4d184', 'HOLD':'#bfd4ff',
                 'PASS':'#d8dce8', 'SELL':'#ff9ba1'}.get(report.verdict, '#ffffff')
st.markdown(f'''<div class="sr-verdict">
<div class="sr-head">Lab V1.7 · Automatic five-way verdict</div>
<div class="sr-verdict-label" style="color:{verdict_color}">{report.verdict}</div>
<div class="sr-verdict-head">{html.escape(report.headline)}</div>
<p style="color:#e3edff;line-height:1.65">{html.escape(report.explanation)}</p>
</div>''', unsafe_allow_html=True)
st.markdown('### Start here: what the verdict means')
st.markdown(f'<div class="sr-learning-note">{html.escape(verdict_in_one_sentence(report.verdict))}</div>',
            unsafe_allow_html=True)
score_a, score_b, score_c = st.columns(3)
score_a.metric('Business fundamentals (unweighted)',
               f'{report.quality:.2f} / 5' if report.quality is not None else 'Not rated',
               help='Average of available categories; NOT a validated stock-return prediction.')
score_b.metric('Historical valuation score',
               f'{report.valuation_rating} / 5' if report.valuation_rating is not None else 'Not rated',
               help='Higher number means the multiple is in a lower part of its own observed history.')
score_c.metric('Evidence coverage', report.confidence)
measured_count, all_categories, missing_categories = score_coverage(report.items)
st.markdown(f'**Data completeness:** {measured_count} of {all_categories} business categories could be scored. '
            'The score is an average of **only the measured categories**, not a complete company rating. '
            'Missing information is **not** counted as zero.')
if missing_categories:
    st.info('**Still unmeasured:** ' + ', '.join(missing_categories) + '. '
            'A high average score does not eliminate unknown financial risks.')
st.markdown('#### How each category scored')
ratings_html = ''
for item in report.items:
    rating = item.rating
    dots = ''.join(
        ('<span class="sr-score-dot" style="background:' +
        ('#8ce6b9' if rating>=4 else '#edc87e' if rating==3 else '#f2a3a3') +
        '"></span>') if rating is not None and index <= rating else '<span class="sr-score-dot"></span>'
        for index in range(1,6))
    ratings_html += (f'<div class="sr-score-row"><div><div class="sr-score-title">{html.escape(item.name)}</div>'
                     f'<div class="sr-score-note">{html.escape(item.explanation)}</div></div>'
                     f'<div class="sr-score-dots">{dots}</div>'
                     f'<div class="sr-score-digit">{rating if rating is not None else "N/A"}</div></div>')
st.markdown('<div class="sr-score-wrap">' + ratings_html + '</div>', unsafe_allow_html=True)
st.markdown('### Valuation made simple: three ways to look at price')
st.caption('Each ratio compares market price with a different financial measure. A lower multiple '
           'versus its OWN history can be interesting, but is never proof the stock is undervalued.')
readings = lens_notes(valuation_histories, d.get('price_asof'))
cards = []
for lens in readings:
    price_val = f'{lens.current:.1f}×' if lens.current is not None else 'N/A'
    median_val = f'{lens.median:.1f}×' if lens.median is not None else 'N/A'
    change = lens.relative_percent
    trend = (f'{abs(change):.1f}% {"above" if change > 0 else "below"} its median'
             if change is not None and abs(change) >= .05 else
             'near its historical median' if change is not None else 'no dependable comparison')
    chosen = ' · Used for verdict' if lens.label == report.valuation_lens else ''
    cards.append('<div class="sr-lesson">'
                 f'<div class="sr-lesson-label">{html.escape(lens.label)}{html.escape(chosen)}</div>'
                 f'<div class="sr-lesson-title">{html.escape(lens.nickname)}</div>'
                 f'<div class="sr-lesson-value">{html.escape(price_val)} '
                 f'<span style="font-size:13px;font-weight:550;color:#d1e0f7">vs {html.escape(median_val)} median</span></div>'
                 f'<div class="sr-lesson-status">{html.escape(lens.position_text)}</div>'
                 f'<div class="sr-lesson-sub">{html.escape(trend)}. {html.escape(lens.meaning)}</div>'
                 '</div>')
st.markdown('<div class="sr-lesson-list">' + ''.join(cards) + '</div>',
            unsafe_allow_html=True)
st.markdown(selection_explanation(readings, report.valuation_lens))
st.markdown(disagreement_explanation(readings, report.valuation_lens))
with st.expander('Beginner tip: why earnings and cash flow can differ'):
    st.markdown('''**Profit (P/E)** comes from accounting rules. **Operating cash (P/OCF)** tracks
cash generated by running the business before large asset purchases. **Free cash flow (P/FCF)**
subtracts capital spending from operating cash flow. A company may report strong profit and
less free cash because it is investing heavily, because of timing, or for other reasons.
A comparison alone cannot prove which cause is responsible. Read cash-flow statements
and the notes before interpreting a gap. Higher or lower *relative to history* is
not a fair-value calculation.''')

if report.valuation_rating is not None:
    st.markdown('**Valuation score explained**')
    st.write(f'{report.valuation_lens}: **{report.valuation_multiple:.1f}×** versus a '
             f'**{report.valuation_median:.1f}×** historical median. The current reading ranks '
             f'around the **{report.valuation_percentile:.0f}th percentile** among '
             f'{report.observations} monthly observations (through {report.valuation_date}). '
             'A low percentile means a lower past multiple, not necessarily fair value.')
    position = min(99., max(1., float(report.valuation_percentile)))
    st.markdown(f'<div class="sr-gauge"><span class="sr-gauge-pointer" '
                f'style="left:{position:.1f}%"></span></div>', unsafe_allow_html=True)
    g1, g2, g3 = st.columns(3)
    g1.caption('Lower historical multiple')
    g2.caption('Mid-range')
    g3.caption('Higher historical multiple')
    if report.valuation_method in ('annual', 'filed_annual'):
        st.caption('Valuation denominator: latest filed annual report, not rolling 12 months.')
    else:
        st.caption('Valuation denominator: SEC-filed trailing four quarters.')
else:
    st.info('Without a sufficiently complete and recent historical valuation series, '
            'the Lab will not issue a positive buying signal.')
st.markdown('### What would need to change for a stronger verdict?')
st.caption('These are the Lab’s checklist conditions, not predicted stock prices or advice to trade.')
for n, step in enumerate(next_steps(report), 1):
    st.markdown(f'**{n}.** {step}')
if report.warnings:
    with st.expander('Data gaps and screen limitations', expanded=True):
        for msg in report.warnings: st.write('• ' + msg)
with st.expander('Show the precise score and verdict rules'):
    st.markdown('''**This is a rules-based research model, not a forecast or fair-value estimate.**

Five fundamental metrics are rated from 1–5 using fixed heuristic thresholds:
revenue growth (3-year CAGR), profitability (operating margin), cash generation
(free-cash-flow margin and positive operating cash flow), annual earnings consistency,
and balance-sheet health (net debt / annual operating cash flow). Available ratings
receive equal weight. Missing figures are NOT treated as zero. Thresholds are
not calibrated against industry peers.

Valuation uses P/FCF first, then P/OCF, then P/E if necessary. Each history
must have 24+ valid monthly observations and a latest point within 45 days of
market prices. Valuation score 5 means the multiple is in the lowest 15% of
observations; 4 is 15–35%; 3 is 35–65%; 2 is 65–85%; 1 is above 85%.

Verdicts are applied in this priority:
- **PASS (insufficient evidence):** under three fundamentals, missing revenue or
  cash score, no eligible valuation, stale financials, or unsuitable financial-sector business.
- **SELL:** quality ≤2, valuation ≤2, and profitability and cash generation each ≤2.
- **BUY:** quality ≥4 and valuation ≥4; profit and cash scores ≥3;
  earnings and leverage (if scored) ≥3; no flagged revenue observations.
- **WATCH:** quality ≥3.5 without clearing BUY.
- **HOLD:** quality ≥3 and valuation ≥3, without clearing the above.
- **PASS:** all other situations.

**SELL** is a risk flag for someone already holding the stock; **HOLD** is
conditional on an existing position. The Lab does not know your holdings.
The framework omits management skill, competitive moat, peer comparisons, forward
forecasts, taxes, and your investment situation. The historical data may be stale
or misleading, and neither these ratings nor their weights have been backtested.''')
    for item in report.items:
        st.write(f'**{item.name}:** {item.evidence}')

with st.expander('Plain-English glossary · financial terms and abbreviations'):
    st.caption('Definitions for interpreting the Lab. The same metric can be more or less useful '
               'depending on the company and industry.')
    for term, definition in GLOSSARY:
        st.markdown(f'**{term}:** {definition}')

with st.expander('See the actual stock price chart (different from valuation!)'):
    period=st.select_slider('Price history',options=['1Y','3Y','5Y','10Y'],value='5Y')
    hist=d['prices'].copy()
    years_back=int(period[:-1]); start=hist.index.max()-pd.DateOffset(years=years_back)
    hist=hist.loc[hist.index>=start]
    fig=go.Figure(go.Scatter(x=hist.index,y=hist.Close,name='Closing price',
                             line=dict(color='#9bdfc4',width=2)))
    fig.update_yaxes(title_text='Stock price (USD)')
    st.plotly_chart(chart_theme(fig,340), use_container_width=True)

st.divider()
st.markdown('#### Data quality & important limitations')
st.caption('For individual U.S. companies. Prices come from Yahoo Finance (unofficial yfinance library); '
           'annual statements come from Yahoo Finance or the SEC EDGAR filing fallback. '
           'Updates, coverage, and access are not guaranteed. '
           'This is a research aid, not investment advice. The stage and valuation calculations are '
           'transparent interpretations, not a reproduction of Stock Simplifier’s proprietary charts. '
           'Always verify important numbers against the company’s 10-K / 10-Q filings before investing.')
st.markdown('Financial statements: [Yahoo Finance](https://finance.yahoo.com) and '
            '[SEC EDGAR](https://www.sec.gov/edgar/search/) · '
            'Lifecycle framework: [Brian Feroldi Phase Check](https://stocksimplifier.com/phase-check)')
