"""ETF-focused research tools. No SEC company-earnings rules are used for funds."""
from __future__ import annotations

import math
import re
import pandas as pd

POPULAR_ETFS = frozenset({
    "VOO", "QQQM", "QQQ", "VTI", "IVV", "SPY", "SPLG", "SPYM",
    "SCHD", "VUG", "VTV", "VGT", "VXUS", "VT", "BND", "AGG",
    "IWM", "DIA", "XLK", "XLF", "XLV", "VYM", "SOXX", "SMH",
    "ARKK", "JEPI", "JEPQ", "SCHG", "VIG", "ITOT", "RSP",
})

def clean_ticker(symbol: str) -> str:
    value = (symbol or "").strip().upper().replace(".", "-")
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9^-]{0,14}", value):
        raise ValueError("Enter a ticker such as VOO, QQQM, AAPL or MSFT.")
    return value


def safe_number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def is_etf_type(ticker: str, info: dict | None) -> bool:
    """Use provider quote type; known ETFs are a fallback if metadata is unavailable."""
    kind = str((info or {}).get("quoteType") or (info or {}).get("typeDisp") or "").upper()
    if kind in {"ETF", "EXCHANGE TRADED FUND", "EXCHANGE-TRADED FUND"}:
        return True
    if kind in {"EQUITY", "STOCK", "MUTUALFUND", "MUTUAL FUND", "INDEX", "CRYPTOCURRENCY"}:
        return False
    return clean_ticker(ticker) in POPULAR_ETFS


def instrument_type(symbol: str) -> str:
    """Automatic detection is best-effort; never pretend missing metadata is verified."""
    import yfinance as yf
    symbol = clean_ticker(symbol)
    try:
        info = yf.Ticker(symbol).info
        if isinstance(info, dict) and info:
            return "ETF" if is_etf_type(symbol, info) else "STOCK"
    except Exception:
        pass
    return "ETF" if symbol in POPULAR_ETFS else "STOCK"


def _fraction(value):
    number = safe_number(value)
    if number is None or number < 0:
        return None
    # Yahoo fund holdings and sector weights are usually ratios between 0 and 1.
    # Some feeds provide percentages; normalize only when clearly > 1.
    return number / 100 if 1 < number <= 100 else number if number <= 1 else None


def _fund_rows(data, weight_names, name_names, limit=50):
    if not isinstance(data, pd.DataFrame) or data.empty:
        return []
    weight_col = next((name for name in weight_names if name in data.columns), None)
    name_col = next((name for name in name_names if name in data.columns), None)
    if weight_col is None:
        return []
    out = []
    for symbol, item in data.head(limit).iterrows():
        weight = _fraction(item.get(weight_col))
        if weight is None or weight <= 0 or weight > 1:
            continue
        name = str(item.get(name_col) or symbol) if name_col else str(symbol)
        out.append({"symbol": str(symbol)[:25], "name": name[:110], "weight": weight})
    return sorted(out, key=lambda item: item["weight"], reverse=True)


def _sector_rows(data):
    if not isinstance(data, dict):
        return []
    out = []
    for key, weight in data.items():
        fraction = _fraction(weight)
        if fraction is not None and 0 < fraction <= 1:
            title = str(key).replace("_", " ").replace("-", " ").strip().title()
            out.append({"name": title, "weight": fraction})
    return sorted(out, key=lambda item: item["weight"], reverse=True)


def _annualized_return(adjusted: pd.Series, years: int):
    if not isinstance(adjusted, pd.Series) or adjusted.empty:
        return None
    end = pd.Timestamp(adjusted.index[-1])
    start_at = end - pd.DateOffset(years=years)
    before = adjusted.loc[:start_at]
    if before.empty:
        return None
    start_time = pd.Timestamp(before.index[-1])
    # Do not label a partial ETF track record as a 3-, 5-, or 10-year return.
    if (start_at - start_time).days > 10:
        return None
    start, finish = safe_number(before.iloc[-1]), safe_number(adjusted.iloc[-1])
    if not start or not finish or start <= 0 or finish <= 0:
        return None
    return 100 * ((finish / start) ** (1 / years) - 1)


def performance(prices: pd.DataFrame):
    if not isinstance(prices, pd.DataFrame) or prices.empty:
        return {"returns": {}, "max_drawdown": None, "method": "unavailable"}
    adjusted = prices.get("Adj Close")
    method = "dividend/split-adjusted closing prices (approximation)"
    if not isinstance(adjusted, pd.Series) or adjusted.dropna().empty:
        adjusted = prices.get("Close")
        method = "price-only closing prices (dividends excluded)"
    if not isinstance(adjusted, pd.Series):
        return {"returns": {}, "max_drawdown": None, "method": "unavailable"}
    adjusted = pd.to_numeric(adjusted, errors="coerce").dropna()
    adjusted = adjusted[adjusted > 0].sort_index()
    if len(adjusted) < 2:
        return {"returns": {}, "max_drawdown": None, "method": "unavailable"}
    returns = {years: _annualized_return(adjusted, years) for years in (1, 3, 5, 10)}
    drawdown = (adjusted / adjusted.cummax() - 1).min()
    return {"returns": returns, "max_drawdown": float(drawdown) * 100,
            "method": method, "start": str(adjusted.index[0].date()),
            "end": str(adjusted.index[-1].date())}


def fetch_etf(symbol: str) -> dict:
    """Yahoo data is best-effort. Unavailable values remain missing, never zero."""
    import yfinance as yf
    symbol = clean_ticker(symbol)
    fund = yf.Ticker(symbol)
    try:
        prices = fund.history(period="10y", interval="1d", auto_adjust=False, actions=False)
    except Exception as exc:
        raise RuntimeError("The fund price history could not be retrieved right now.") from exc
    if not isinstance(prices, pd.DataFrame) or prices.empty or "Close" not in prices:
        raise RuntimeError("No ETF price history was found; verify the ticker or retry later.")
    prices = prices.copy()
    dates = pd.to_datetime(prices.index)
    if dates.tz is not None:
        prices.index = dates.tz_localize(None)
    else:
        prices.index = dates
    prices = prices.sort_index()

    try:
        info = fund.info or {}
        if not isinstance(info, dict):
            info = {}
    except Exception:
        info = {}
    # Refuse fund accounting analysis if the returned instrument is an equity.
    if not is_etf_type(symbol, info):
        kind = str(info.get("quoteType") or "")
        if kind:
            raise ValueError(f"{symbol} is identified by the data provider as {kind}, not an ETF.")

    try:
        fd = fund.funds_data
        holdings = _fund_rows(fd.top_holdings,
                             ("Holding Percent", "Holding Percentage", "Weight", "weight"),
                             ("Holding Name", "Name", "name"))
        sectors = _sector_rows(fd.sector_weightings)
        overview = fd.fund_overview if isinstance(fd.fund_overview, dict) else {}
    except Exception:
        holdings, sectors, overview = [], [], {}
    # Fetch sections separately when just one optional endpoint failed.
    if not holdings:
        try:
            holdings = _fund_rows(fund.funds_data.top_holdings,
                                 ("Holding Percent", "Holding Percentage", "Weight", "weight"),
                                 ("Holding Name", "Name", "name"))
        except Exception:
            pass
    if not sectors:
        try:
            sectors = _sector_rows(fund.funds_data.sector_weightings)
        except Exception:
            pass
    price_points = pd.to_numeric(prices.Close, errors="coerce").dropna()
    if price_points.empty:
        raise RuntimeError("The price history had no usable closing prices.")
    ratio = None
    for field in ("annualReportExpenseRatio", "totalExpenseRatio"):
        ratio = _fraction(info.get(field))
        if ratio is not None:
            break
    assets = safe_number(info.get("totalAssets"))
    if assets is not None and assets < 0:
        assets = None
    profile = {
        "category": str(info.get("category") or overview.get("categoryName") or ""),
        "family": str(info.get("fundFamily") or overview.get("family") or ""),
        "index": str(info.get("indexName") or overview.get("indexName") or ""),
        "description": str(info.get("longBusinessSummary") or "")[:2000],
    }
    return {
        "ticker": symbol, "name": str(info.get("longName") or info.get("shortName") or symbol),
        "price": float(price_points.iloc[-1]), "asof": str(price_points.index[-1].date()),
        "currency": str(info.get("currency") or "USD"), "expense_ratio": ratio,
        "assets": assets, "holdings": holdings, "sectors": sectors,
        "profile": profile, "prices": prices, "performance": performance(prices),
        "source": "Yahoo Finance via unofficial yfinance; coverage may be incomplete or delayed",
    }


def assessment(data: dict) -> dict:
    """A transparent research screen, NOT a recommendation or a price target.

    Selling requires personal tax, portfolio and cost basis context; this automatic
    ETF screen never assigns SELL. It also never treats past returns as fair value.
    """
    expense = safe_number(data.get("expense_ratio"))
    holdings = data.get("holdings") or []
    top_ten = sum(row["weight"] for row in holdings[:10]) if len(holdings) >= 10 else None
    returns = (data.get("performance") or {}).get("returns") or {}
    years5 = safe_number(returns.get(5))
    evidence = sum(x is not None for x in (expense, top_ten, years5))
    reasons = []
    if expense is None:
        reasons.append("The fund fee was not available from the provider.")
    if top_ten is None:
        reasons.append("Ten holdings with weights were not available to measure concentration.")
    if years5 is None:
        reasons.append("Five years of comparable price history were not available.")
    # Thresholds are openly stated screening rules, not scientifically proven buy signals.
    if expense is not None and expense >= .01:
        verdict = "PASS"
        reasons.append("The reported annual expense ratio is at least 1%, an unusually high hurdle for a core ETF.")
    elif top_ten is not None and top_ten >= .75:
        verdict = "PASS"
        reasons.append("The ten largest holdings represent at least 75% of assets: very concentrated.")
    elif evidence < 3:
        verdict = "WATCH"
        reasons.append("Important facts are missing, so the screen cannot award its strongest label.")
    elif expense <= .001 and top_ten <= .40 and years5 > 0:
        verdict = "BUY"
        reasons.append("Low reported fees, a less-concentrated top ten and positive five-year adjusted-price growth meet the strict research screen.")
    elif expense <= .0035 and top_ten <= .60 and years5 > 0:
        verdict = "HOLD"
        reasons.append("Fees and concentration fit the middle research range. Assess fit and purchase price separately.")
    else:
        verdict = "WATCH"
        reasons.append("Costs, concentration or historical performance deserve a closer look before making a decision.")
    return {
        "verdict": verdict, "reasons": reasons, "evidence": evidence,
        "coverage": "Good" if evidence == 3 else "Partial" if evidence else "Limited",
        "top_ten": top_ten,
        "note": ("BUY, WATCH, HOLD and PASS are rule-based research labels, not transaction "
                 "instructions. SELL requires your portfolio and tax circumstances and is not "
                 "assigned automatically. No ETF intrinsic/fair-value estimate is calculated."),
    }
