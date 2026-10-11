"""SEC EDGAR XBRL annual financial data fallback for US-listed SEC registrants.

Uses official SEC companyfacts. Credentials are not needed, but the SEC requires a
User-Agent containing an identifiable application and a real contact address.
Store the User-Agent in Streamlit Secrets, not in a publicly visible repository.
"""
from __future__ import annotations
from datetime import date
import re
from functools import lru_cache
import pandas as pd
import requests

# Use company-wide XBRL tags only. Do not infer figures from unrelated segment tags.
TAGS = {
    'revenue': ('RevenueFromContractWithCustomerExcludingAssessedTax',
                'RevenueFromContractWithCustomerIncludingAssessedTax',
                'Revenues', 'SalesRevenueNet', 'SalesRevenueGoodsNet',
                'RevenueFromContractWithCustomer'),
    'operating_income': ('OperatingIncomeLoss',),
    'net_income': ('NetIncomeLoss', 'ProfitLoss'),
    'ocf': ('NetCashProvidedByUsedInOperatingActivities',),
    'capex': ('PaymentsToAcquirePropertyPlantAndEquipment',),
    'dividends': ('PaymentsOfDividendsCommonStock', 'PaymentsOfDividends',
                  'PaymentsOfDividendsAndDividendEquivalentsOnCommonStockAndRestrictedStockUnits'),
    'shares': ('WeightedAverageNumberOfDilutedSharesOutstanding',
               'WeightedAverageNumberOfSharesOutstandingBasic'),
}


def valid_agent(s: str) -> bool:
    """Avoid making unidentified requests to the SEC."""
    return bool(s and re.search(r'[^\s@]+@[^\s@]+\.[^\s@]+', s) and len(s) >= 12)


def _headers(user_agent):
    return {'User-Agent': user_agent, 'Accept-Encoding': 'gzip, deflate',
            'Accept': 'application/json'}


def _download(url, user_agent):
    try:
        response = requests.get(url, headers=_headers(user_agent), timeout=22)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as ex:
        if ex.response is not None and ex.response.status_code in (403, 429):
            raise RuntimeError('SEC access was rejected or rate-limited. Try again later or check the SEC User-Agent contact.') from ex
        raise RuntimeError('SEC data was not available for this stock.') from ex
    except (requests.RequestException, ValueError) as ex:
        raise RuntimeError('Could not reach the SEC financial-data service.') from ex


@lru_cache(maxsize=3)
def _ticker_directory(user_agent):
    content = _download('https://www.sec.gov/files/company_tickers.json', user_agent)
    return {str(item['ticker']).upper().replace('.', '-') : int(item['cik_str'])
            for item in content.values() if item.get('ticker') and item.get('cik_str')}


def sec_cik(ticker, user_agent):
    mapping = _ticker_directory(user_agent)
    # BRK-B on Yahoo is BRK-B; SEC uses BRK-B or BRK.B depending on feed version.
    return mapping.get(ticker.upper().replace('.', '-'))


def _records(facts, tag, unit):
    return facts.get('us-gaap', {}).get(tag, {}).get('units', {}).get(unit, [])


def extract_annual(facts: dict, tags: tuple, unit: str = 'USD') -> pd.Series:
    """Extract 10-K 12-month durations, keyed by fiscal year-end.

    Require an actual 12-month start/end, not the filing-year label, to avoid
    mistakenly using Q4 or a restated comparative as the wrong fiscal year.
    """
    picked = {}
    for priority, tag in enumerate(tags):
        for rec in _records(facts, tag, unit):
            if rec.get('form') not in ('10-K', '10-K/A'):
                continue
            try:
                end = pd.Timestamp(rec['end'])
                start = pd.Timestamp(rec['start'])
                filed = pd.Timestamp(rec['filed'])
                amount = float(rec['val'])
            except (KeyError, ValueError, TypeError, OverflowError):
                continue
            days = (end - start).days
            if not (325 <= days <= 396):
                continue
            # Annual comparative restatements are allowed, but eliminate data
            # entered for a fiscal year far older than the SEC's structured era.
            if end.year < 2010 or end > pd.Timestamp.today():
                continue
            # Prefer the first-priority matching tag; within it, latest filing.
            previous = picked.get(end)
            if previous is None or (priority, -filed.value) < (previous[0], -previous[1].value):
                picked[end] = (priority, filed, amount)
    if not picked:
        return pd.Series(dtype='float64')
    return pd.Series({d: entry[2] for d, entry in picked.items()}, dtype='float64').sort_index(ascending=False)


@lru_cache(maxsize=3)
def load_companyfacts(ticker: str, user_agent: str) -> dict:
    """Fetch official structured SEC data; reused by annual and quarterly models."""
    if not valid_agent(user_agent):
        raise RuntimeError('Set SEC_USER_AGENT in Streamlit Secrets, including a contact email, to enable SEC financials.')
    cik = sec_cik(ticker, user_agent)
    if not cik:
        raise RuntimeError('No SEC CIK found for this ticker. SEC financial statements may not be available.')
    return _download(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json', user_agent)


def load_financials(ticker: str, user_agent: str) -> tuple[dict, str]:
    """Return SEC financial series and SEC entity name. Raises a readable error."""
    raw = load_companyfacts(ticker, user_agent)
    facts = raw.get('facts', {})
    series = {}
    for name, tags in TAGS.items():
        series[name] = extract_annual(facts, tags, 'shares' if name == 'shares' else 'USD')
    # Simple FCF definition: OCF minus PP&E purchases, aligned by fiscal end.
    if not series['ocf'].empty and not series['capex'].empty:
        common = series['ocf'].index.intersection(series['capex'].index)
        series['fcf'] = (series['ocf'].loc[common] - series['capex'].loc[common]).sort_index(ascending=False)
    else:
        series['fcf'] = pd.Series(dtype='float64')
    del series['capex']
    return series, raw.get('entityName', ticker)
