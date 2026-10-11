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

st.markdown('<div class="sr-head">Independent research dashboard · v1.4.2</div>', unsafe_allow_html=True)
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
    growth = yoy(latest['revenue'], prior['revenue']) if latest is not None and prior is not None else None
    st.metric('Revenue growth (FY)', f'{growth:+.1f}%' if growth is not None else 'N/A')
with mc[3]: st.metric('Operating cash flow (FY)', format_billions(latest['ocf']) if latest is not None else 'N/A')

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
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('#### Revenue growth')
        k1, k2, k3 = st.columns(3)
        for box, n, label in zip([k1,k2,k3], [1,3,5], ['1Y','3Y','5Y']):
            res = cagr(v['revenue'], n)
            box.metric(f'{label} CAGR', f'{res:+.1f}%' if res is not None else 'N/A')
    with c2:
        st.markdown('#### Net income growth')
        k1, k2, k3 = st.columns(3)
        for box, n, label in zip([k1,k2,k3], [1,3,5], ['1Y','3Y','5Y']):
            res = cagr(v['net_income'], n)
            box.metric(f'{label} CAGR', f'{res:+.1f}%' if res is not None else 'N/A')
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
            high14=max(1.2*limits14['high'],1.15*hist14.multiple.max())
            graph14=go.Figure()
            graph14.add_hrect(y0=0,y1=limits14['low'],fillcolor='rgba(74,171,112,.26)',line_width=0)
            graph14.add_hrect(y0=limits14['low'],y1=limits14['high'],fillcolor='rgba(241,190,90,.22)',line_width=0)
            graph14.add_hrect(y0=limits14['high'],y1=high14,fillcolor='rgba(225,91,112,.22)',line_width=0)
            graph14.add_trace(go.Scatter(x=hist14.date,y=hist14.multiple,mode='lines',
                                         name=f'{metric_label} ({method14})',
                                         line=dict(color='#f5fbff',width=2.7),
                                         hovertemplate=f'%{{x|%b %Y}}<br>{metric_label}: %{{y:.1f}}×<extra></extra>'))
            graph14.add_hline(y=median14,line_dash='dot',line_color='#f5d77e',
                              annotation_text=f'Median {median14:.1f}×')
            graph14.update_yaxes(title_text=metric_label,range=[0,high14],ticksuffix='×')
            st.plotly_chart(chart_theme(graph14,350),use_container_width=True,
                            key=f'additional_valuation_{metric}')
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
