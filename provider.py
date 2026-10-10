"""Market data adapter (Yahoo Finance via yfinance; unofficial and may be limited)."""
from __future__ import annotations
import re
from dataclasses import dataclass
import pandas as pd

FIELDS = {
    'revenue': ('Total Revenue', 'Operating Revenue'),
    'operating_income': ('Operating Income', 'EBIT'),
    'net_income': ('Net Income', 'Net Income Common Stockholders'),
    'ocf': ('Operating Cash Flow', 'Total Cash From Operating Activities'),
    'fcf': ('Free Cash Flow',),
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


def fetch_stock(ticker: str) -> dict:
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
    if not isinstance(splits, pd.Series): splits = pd.Series(dtype='float64')
    if not isinstance(dividends, pd.Series): dividends = pd.Series(dtype='float64')

    values = {
        'revenue': row_from(income, FIELDS['revenue']),
        'operating_income': row_from(income, FIELDS['operating_income']),
        'net_income': row_from(income, FIELDS['net_income']),
        'ocf': row_from(cash, FIELDS['ocf']),
        'fcf': row_from(cash, FIELDS['fcf']),
        'dividends': row_from(cash, FIELDS['dividends']),
        'shares': row_from(balance, FIELDS['shares']),
    }
    price.index = pd.to_datetime(price.index)
    if price.index.tz is not None: price.index = price.index.tz_localize(None)
    price = price.sort_index()
    return {'ticker':ticker, 'company':info.get('longName') or info.get('shortName') or ticker,
            'sector':info.get('sector') or '', 'industry':info.get('industry') or '',
            'currency':info.get('currency') or 'USD', 'exchange':info.get('exchange') or '',
            'values':values, 'prices':price, 'splits':splits, 'dividends_history':dividends,
            'price_latest':float(price.Close.dropna().iloc[-1]), 'price_asof':str(price.Close.dropna().index[-1].date()),
            'data_provider':'Yahoo Finance (via yfinance; unofficial)'}
