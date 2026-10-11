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
from valuation_history import monthly_valuation, distribution_bands

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
.sr-warning{font-size:13px;color:#adbcd3}
</style>""", unsafe_allow_html=True)

@st.cache_data(ttl=60*60*3, show_spinner=False)
def cached_fetch(ticker: str, sec_user_agent: str):
    return fetch_stock(ticker, sec_user_agent=sec_user_agent)


def text_card(title, value, subtitle=''):
    st.markdown(f'<div class="sr-card"><div class="sr-head">{html.escape(title)}</div>'
                f'<div class="sr-hero">{html.escape(value)}</div><div class="sr-dim">{html.escape(subtitle)}</div></div>',
                unsafe_allow_html=True)


def chart_theme(fig, height=335):
    fig.update_layout(height=height, margin=dict(l=0,r=12,b=8,t=20),
                      paper_bgcolor='#141d30', plot_bgcolor='#141d30',
                      font=dict(color='#c7d5ea', size=12),
                      hovermode='x unified', legend=dict(orientation='h',y=1.11,x=0),
                      xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#293348',zerolinecolor='#35445c'))
    return fig


def annual_frame(values):
    rev = values.get('revenue', pd.Series(dtype='float64'))
    dates = list(rev.index.sort_values()) if not rev.empty else []
    out = pd.DataFrame({'date': dates})
    for key in ['revenue','operating_income','net_income','ocf','fcf','shares']:
        out[key] = align(values[key], dates) if dates else []
    return out

st.markdown('<div class="sr-head">Independent research dashboard · v1.2</div>', unsafe_allow_html=True)
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
        fig=go.Figure()
        x=frame['date'].dt.strftime('%Y')
        fig.add_trace(go.Scatter(x=x,y=frame.revenue/1e9,name='Revenue',mode='lines+markers',
                                 line=dict(color='#9bdfc4',width=3)))
        fig.add_trace(go.Scatter(x=x,y=frame.ocf/1e9,name='Operating cash flow',mode='lines+markers',
                                 line=dict(color='#f4c77c',width=3)))
        fig.update_yaxes(title_text='USD billions')
        st.plotly_chart(chart_theme(fig),use_container_width=True)
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

st.markdown('### 3 · Historical valuation')
st.caption('Monthly price / trailing 12-month operating cash flow (P/OCF), derived from SEC-filed quarterly statements and split-adjusted stock closing prices.\n\n'
           '**Green / yellow / red are relative to this company’s own history, not fair-value estimates.**')

period_col, foot_col = st.columns([1, 2], vertical_alignment='bottom')
with period_col:
    valuation_period = st.radio('Valuation history', ['5 years', '10 years'], horizontal=True,
                                help='Compare monthly valuation observations within the chosen lookback.')
lookback_years = 5 if valuation_period == '5 years' else 10
with st.spinner('Building filed-date-aware valuation history...'):
    monthly = monthly_valuation(d['prices'], d['splits'], d.get('valuation_facts') or {},
                                years=lookback_years)
bands = distribution_bands(monthly['multiple']) if not monthly.empty else None
if bands:
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
    m1.metric('Latest monthly P/OCF', f'{current:.1f}×', help=f'Last price date: {last["date"]:%b %d, %Y}')
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
    fig.add_trace(go.Scatter(x=monthly.date, y=monthly.multiple, name='Filed-date-aware monthly P/OCF',
                             mode='lines', line=dict(color='#e5edf8', width=2.5),
                             hovertemplate='%{x|%b %Y}<br>P/OCF %{y:.1f}×<extra></extra>',
                             connectgaps=False))
    fig.add_hline(y=median, line_dash='dot', line_color='#e3c16f',
                  annotation_text=f'Median {median:.1f}×')
    fig.update_yaxes(title_text='Price / TTM operating cash flow',range=[0,ceiling], ticksuffix='×')
    fig.update_xaxes(range=[x0,x1])
    st.plotly_chart(chart_theme(fig,405),use_container_width=True)
    st.caption(f'**{len(monthly)} month-end observations** from {monthly.date.min():%b %Y}–{monthly.date.max():%b %Y}. '
               f'Most recent cash-flow filing: {last["ocf_filed"]:%b %d, %Y} '
               f'(period ended {last["ocf_period_end"]:%b %d, %Y}). '
               'Bands are the 25th/75th percentiles of this selected window; a higher multiple means '
               'investors are paying more per dollar of cash flow. Monthly points use the latest results '
               'already filed with the SEC by that month-end—not later results.')
    with st.expander('How this monthly valuation works — and its limitations'):
        st.markdown('**Method:** Four consecutive fiscal-quarter operating cash flows are combined into '
                    'trailing-12-month (TTM) cash flow. SEC 10-Q filings typically present year-to-date '
                    'cash flows, so individual quarters are reconstructed by subtracting previous periods. '
                    'Each month uses the last available daily closing price and the latest **already filed** '
                    'TTM figures. Market capitalization is approximated using the latest filed diluted '
                    'weighted-average share count, adjusted for subsequent splits.')
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
