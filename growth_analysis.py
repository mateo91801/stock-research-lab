"""Pure, conservative growth calculations for Stock Research Lab 1.3.

Never interpolate a missing financial year or compute conventional CAGR across
negative/zero endpoints. Numbers are annual SEC/Yahoo filed-report figures.
"""
from __future__ import annotations
import math
import pandas as pd


def _valid(v):
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def cagr(series: pd.Series, years: int):
    """Annualized percentage growth across approximately `years` fiscal years.

    Use fiscal-year dates, not the number of rows; protect against unavailable
    years, an incomplete time span, and non-positive values.
    """
    if years < 1 or series is None or len(series) < 2:
        return None
    numeric = pd.to_numeric(series, errors='coerce').dropna()
    if len(numeric) < 2:
        return None
    numeric.index = pd.to_datetime(numeric.index)
    numeric = numeric.sort_index()
    latest_date = numeric.index[-1]
    latest = _valid(numeric.iloc[-1])
    if latest is None or latest <= 0:
        return None
    target = latest_date - pd.DateOffset(years=years)
    candidates = []
    for d, v in numeric.iloc[:-1].items():
        gap = abs((pd.Timestamp(d)-target).days)
        if gap <= 120:
            candidates.append((gap, pd.Timestamp(d), _valid(v)))
    if not candidates:
        return None
    _, prior_date, prior = min(candidates, key=lambda x: x[0])
    if prior is None or prior <= 0:
        return None
    actual_years = (latest_date - prior_date).days / 365.2425
    if abs(actual_years - years) > 0.35:
        return None
    return 100*((latest/prior)**(1/actual_years)-1)


def percent_margin(numerator, denominator):
    n = _valid(numerator)
    d = _valid(denominator)
    if n is None or d is None or d <= 0:
        return None
    return 100*n/d


def last_two(series: pd.Series):
    """Return (latest, prior) by fiscal date, even if input is newest-first."""
    if series is None or series.empty:
        return None, None
    v = pd.to_numeric(series, errors='coerce').dropna().sort_index(ascending=False)
    return (_valid(v.iloc[0]) if len(v) else None,
            _valid(v.iloc[1]) if len(v)>1 else None)
