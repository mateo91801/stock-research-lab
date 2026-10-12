"""Price data via Yahoo Finance; annual SEC EDGAR fallback for fundamentals."""
from __future__ import annotations
import re
import pandas as pd

FIELDS = {
    'revenue': ('Total Revenue', 'Operating Revenue'),
    'operating_income': ('Operating Income', 'EBIT'),
    'net_income': ('Net Income', 'Net Income Common Stockholders'),
    'ocf': ('Operating Cash Flow', 'Total Cash From Operating Activities'),
    'fcf': ('Free Cash Flow',),
    'capex': ('Capital Expenditure', 'Capital Expenditures', 'Purchase Of PPE', 'Net PPE Purchase And Sale'),
    'dividends': ('Cash Dividends Paid', 'Common Stock Dividend Paid', 'Cash Dividends Paid to Common Stockholders'),
    'shares': ('Ordinary Shares Number', 'Common Stock Shares Outstanding'),
}


def row_from(statement: pd.DataFrame, candidates) -> pd.Series:
    if statement is None or statement.empty:
        return pd.Series(dtype='float64')
    for name in candidates:
        if name in statement.index:
            out = pd.to_numeric(statement.loc[name], errors='coerce')
            if isinstance(out, pd.DataFrame): out = out.iloc[0]
            out.index = pd.to_datetime(out.index).tz_localize(None)
            return out.sort_index(ascending=False)
    return pd.Series(dtype='float64')


def align(series: pd.Series, dates: list) -> list:
    return [float(series.loc[d]) if d in series.index and pd.notna(series.loc[d]) else None for d in dates]


def blank():
    return pd.DataFrame()


def fetch_stock(ticker: str, sec_user_agent: str = "") -> dict:
    """Returns live-source data or raises; never fabricates missing figures."""
    import yfinance as yf
    ticker = (ticker or '').strip().upper().replace('.', '-')
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9^-]{0,14}', ticker):
        raise ValueError("Enter a valid ticker such as GOOGL, AAPL, or BRK-B.")
    t = yf.Ticker(ticker)
    try:
        price = t.history(period='10y', interval='1d', auto_adjust=False, actions=True)
    except Exception as ex:
        raise RuntimeError("Price data unavailable from Yahoo Finance at the moment.") from ex
    if price is None or price.empty or 'Close' not in price:
        raise RuntimeError("No price history returned. Check the ticker or try later.")

    def safe(getter):
        try:
            result = getter()
            return result if result is not None else blank()
        except Exception:
            return blank()

    info = safe(lambda: t.info)
    if not isinstance(info, dict): info = {}
    income = safe(lambda: t.get_income_stmt(freq='yearly'))
    cash = safe(lambda: t.get_cash_flow(freq='yearly'))
    balance = safe(lambda: t.get_balance_sheet(freq='yearly'))
    dividends = safe(lambda: t.dividends)
    splits = safe(lambda: t.splits)
    # Optional Yahoo earnings-calendar feed; may be empty or unavailable.
    earnings_dates = safe(lambda: t.get_earnings_dates(limit=8))
    if not isinstance(splits, pd.Series): splits = pd.Series(dtype='float64')
    if not isinstance(dividends, pd.Series): dividends = pd.Series(dtype='float64')

    values = {
        'revenue': row_from(income, FIELDS['revenue']),
        'operating_income': row_from(income, FIELDS['operating_income']),
        'net_income': row_from(income, FIELDS['net_income']),
        'ocf': row_from(cash, FIELDS['ocf']),
        'fcf': row_from(cash, FIELDS['fcf']),
        'capex': row_from(cash, FIELDS['capex']),
        'dividends': row_from(cash, FIELDS['dividends']),
        'shares': row_from(balance, FIELDS['shares']),
    }
    # If Yahoo has OCF and capex but no derived FCF, use one coherent
    # Yahoo cash-flow statement for each matching fiscal year.
    if values['fcf'].empty and not values['ocf'].empty and not values['capex'].empty:
        common = values['ocf'].index.intersection(values['capex'].index)
        if len(common):
            # Cash outflow may be negative in Yahoo; use absolute expenditure.
            values['fcf'] = (values['ocf'].loc[common] - values['capex'].loc[common].abs()).sort_index(ascending=False)
    # Prefer authoritative SEC annual figures where supplied; Yahoo serves as a
    # cross-check and fallback. Keep an explicit source per metric instead of
    # silently intermixing years from the two feeds.
    source = 'Yahoo Finance (unofficial yfinance)'
    sec_status = ''
    valuation_facts = {}
    valuation_status = ''
    quality_audit = None
    series_sources = {name: ('Yahoo Finance' if not series.empty else 'Unavailable')
                      for name, series in values.items()}
    yahoo_revenue = values['revenue'].copy()
    try:
        from sec_fundamentals import load_financials
        from data_quality import audit_revenue
        sec_values, company_from_sec = load_financials(ticker, sec_user_agent)
        for name, sec_series in sec_values.items():
            if name in values and not sec_series.empty:
                # SEC is the source of record for fiscal-year annual data.
                values[name] = sec_series
                series_sources[name] = 'SEC EDGAR XBRL'
        if not values['revenue'].empty:
            quality_audit = audit_revenue(values['revenue'], yahoo_revenue,
                source=series_sources.get('revenue','Yahoo Finance'))
            values['revenue'] = quality_audit.accepted
        if any(not series.empty for series in sec_values.values()):
            source = 'SEC EDGAR (annual financials) + Yahoo Finance (prices; secondary cross-check)'
        if not info.get('longName') and not info.get('shortName'):
            info['shortName'] = company_from_sec
    except Exception as exc:
        sec_status = str(exc)
        # When SEC is unavailable still check the Yahoo-only series for obvious
        # isolated errors. Mark its different level of verification explicitly.
        if not values['revenue'].empty:
            from data_quality import audit_revenue
            quality_audit = audit_revenue(values['revenue'], source='Yahoo Finance — not SEC verified')
            values['revenue'] = quality_audit.accepted
    # Always attempt SEC quarterly data for the new monthly valuation, even
    # when Yahoo supplies the shorter annual income/cash-flow statements.
    try:
        from sec_fundamentals import load_companyfacts
        valuation_facts = load_companyfacts(ticker, sec_user_agent)
    except Exception as exc:
        valuation_status = str(exc)
    # SEC public filer address is a useful fallback when Yahoo omits HQ.
    sec_profile = {}
    if not (info.get('city') and info.get('country')):
        try:
            from sec_fundamentals import load_sec_profile
            sec_profile = load_sec_profile(ticker, sec_user_agent)
        except Exception:
            pass
    # Optional public-domain Wikidata reference metadata, never financials.
    extra_profile = {}
    if not (info.get('longBusinessSummary') and info.get('city')):
        try:
            from reference_profile import wikidata_profile
            extra_profile = wikidata_profile(ticker, info.get('longName') or info.get('shortName') or ticker)
        except Exception:
            pass
    # Management information is provider metadata; it is NOT an SEC-verified
    # assessment of skill, founder status, or stock performance.
    executive = None
    officers = info.get('companyOfficers') or []
    if isinstance(officers, list):
        for person in officers:
            if not isinstance(person, dict):
                continue
            title = str(person.get('title') or '').lower()
            if 'chief executive officer' in title or re.search(r'\bceo\b', title):
                executive = {'name': str(person.get('name') or '')[:100],
                             'title': str(person.get('title') or '')[:150],
                             'source': 'Yahoo Finance company profile',
                             'source_url': f'https://finance.yahoo.com/quote/{ticker}/profile/',
                             'source_note': 'Unofficial company metadata; check company filings.'}
                break
    # If Yahoo omits its officers, try conservative signed-SEC evidence.
    # Keep a human-readable status so network errors aren't mistaken for
    # evidence that a company has no CEO.
    if executive and executive.get('name'):
        ceo_lookup_status = 'Yahoo Finance company-officer profile provided the CEO name; SEC fallback not needed.'
    else:
        try:
            from leadership_sources import sec_ceo_from_recent_filing_diagnostic
            verified_ceo, detail = sec_ceo_from_recent_filing_diagnostic(ticker, sec_user_agent)
            executive = verified_ceo or None
            ceo_lookup_status = 'Yahoo did not return CEO officer metadata. ' + detail
        except Exception:
            executive = None
            ceo_lookup_status = ('Yahoo did not return CEO officer metadata. The SEC lookup '
                                 'encountered an unexpected error; check the Streamlit app logs.')
    held = info.get('heldPercentInsiders')
    try:
        held = float(held)
        if not 0 <= held <= 1: held = None
    except (TypeError, ValueError):
        held = None
    surprises = []
    if isinstance(earnings_dates, pd.DataFrame) and not earnings_dates.empty:
        for date, earning in earnings_dates.sort_index(ascending=False).head(8).iterrows():
            try:
                reported = float(earning.get('Reported EPS'))
                estimate = float(earning.get('EPS Estimate'))
                if not pd.notna(reported) or not pd.notna(estimate): continue
                surprises.append({'date':str(pd.Timestamp(date).date()),
                                  'reported_eps':reported, 'estimate_eps':estimate,
                                  'beat':reported > estimate, 'miss':reported < estimate})
            except (TypeError, ValueError):
                continue
    # Balance-sheet amounts from a single dated Yahoo report. Do not use
    # unidentified or unmatched debt / cash data to infer financial health.
    debt_series = row_from(balance, ('Total Debt',))
    cash_series = row_from(balance, ('Cash And Cash Equivalents',
                                    'Cash Cash Equivalents And Short Term Investments',
                                    'Cash And Short Term Investments'))
    financial_position = {}
    matched_dates = debt_series.index.intersection(cash_series.index)
    if len(matched_dates):
        bdate = max(matched_dates)
        if pd.notna(debt_series.loc[bdate]) and pd.notna(cash_series.loc[bdate]):
            financial_position = {'date': str(pd.Timestamp(bdate).date()),
                                  'total_debt': float(debt_series.loc[bdate]),
                                  'cash': float(cash_series.loc[bdate]),
                                  'source': 'Yahoo Finance yearly balance sheet'}
    management = {'ceo': executive, 'insider_fraction': held,
                  'ceo_lookup_status': ceo_lookup_status,
                  'earnings_surprises': surprises,
                  'source': 'Yahoo Finance company profile and earnings calendar (unofficial)'}
    price.index = pd.to_datetime(price.index)
    if price.index.tz is not None: price.index = price.index.tz_localize(None)
    price = price.sort_index()
    profile = {
        'description': str(info.get('longBusinessSummary') or '')[:4500],
        'website': str(info.get('website') or ''),
        'headquarters': ', '.join(str(x) for x in
            [info.get('city'), info.get('state'), info.get('country')] if x),
        'employees': info.get('fullTimeEmployees'),
        'sec_business_address': sec_profile.get('sec_business_address') or '',
        'wikidata_description': extra_profile.get('description') or '',
        'wikidata_headquarters': extra_profile.get('headquarters') or '',
        'wikidata_url': extra_profile.get('source_url') or '',
    }
    return {'ticker':ticker, 'company':info.get('longName') or info.get('shortName') or ticker,
            'profile':profile, 'management': management,
            'financial_position': financial_position,
            'sector':info.get('sector') or '', 'industry':info.get('industry') or '',
            'currency':info.get('currency') or 'USD', 'exchange':info.get('exchange') or '',
            'values':values, 'prices':price, 'splits':splits, 'dividends_history':dividends,
            'price_latest':float(price.Close.dropna().iloc[-1]), 'price_asof':str(price.Close.dropna().index[-1].date()),
            'data_provider':source, 'sec_status':sec_status,
            'valuation_facts':valuation_facts, 'valuation_status':valuation_status,
            'quality_audit':quality_audit, 'annual_sources':series_sources}
