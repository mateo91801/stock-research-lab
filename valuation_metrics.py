"""P/E and P/FCF history from SEC facts with as-filed date protections.

Research multiples only. Denominator uses positive SEC-filed TTM net income or
TTM FCF (operating cash flow less capex) and *approximate* diluted shares.
If quarterly coverage is missing, last-filed annual figures are explicitly
labeled and not misrepresented as trailing-twelve-month metrics.
"""
from __future__ import annotations
import math
import pandas as pd
import numpy as np
from valuation_history import (FinancialPoint, _ytd_records, _close_series,
                               _share_split_multiplier, share_events,
                               trailing_cashflows, as_filed_annual_events)

INCOME_TAGS = ('NetIncomeLoss', 'ProfitLoss')
CAPEX_TAGS = ('PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets')
OCF_TAGS = ('NetCashProvidedByUsedInOperatingActivities',)
SHARE_TAGS = ('WeightedAverageNumberOfDilutedSharesOutstanding',
              'WeightedAverageNumberOfSharesOutstandingBasic')


def quarter_events(facts: dict, tags: tuple[str,...], now=None) -> list[FinancialPoint]:
    """De-cumulate 10-Q fiscal-YTD values; source values may be negative."""
    ytd = _ytd_records(facts, tags, 'USD', now)
    out = []
    for (fy_start, q), item in ytd.items():
        if q == 1:
            amount, filed = item.value, item.filed
        else:
            prev = ytd.get((fy_start, q-1))
            if prev is None or not 65 <= (item.end-prev.end).days <= 111:
                continue
            amount, filed = item.value-prev.value, max(item.filed, prev.filed)
        if math.isfinite(amount):
            out.append(FinancialPoint(item.end, filed, float(amount), item.source))
    # Distinct period ends, only one chosen for an as-filed point.
    by_end = {}
    for event in sorted(out, key=lambda p: (p.filed, p.end)):
        previous = by_end.get(event.end)
        if previous is None or event.filed < previous.filed:
            by_end[event.end] = event
    return sorted(by_end.values(), key=lambda p: p.end)


def trailing_events(facts: dict, tags: tuple[str,...], now=None) -> list[FinancialPoint]:
    quarters = quarter_events(facts, tags, now)
    out = []
    for i in range(3, len(quarters)):
        seq = quarters[i-3:i+1]
        if all(65 <= (b.end-a.end).days <= 111 for a,b in zip(seq,seq[1:])):
            out.append(FinancialPoint(seq[-1].end, max(q.filed for q in seq),
                                      sum(q.value for q in seq), 'SEC filed TTM'))
    return out


def denominator_events(facts: dict, metric: str, method: str, now=None) -> list[FinancialPoint]:
    if metric not in ('pe','pfcf') or method not in ('ttm','annual'):
        raise ValueError('Unsupported valuation metric or method')
    if method == 'annual':
        earnings = as_filed_annual_events(facts, INCOME_TAGS, 'USD', now)
        ocf = as_filed_annual_events(facts, OCF_TAGS, 'USD', now)
        capex = as_filed_annual_events(facts, CAPEX_TAGS, 'USD', now)
    else:
        earnings = trailing_events(facts, INCOME_TAGS, now)
        ocf = trailing_cashflows(facts, now)
        capex = trailing_events(facts, CAPEX_TAGS, now)
    if metric == 'pe':
        return [p for p in earnings if p.value > 0]
    # Pair ONLY data for the same fiscal period; if capex absent, show N/A.
    expense = {p.end: p for p in capex}
    result = []
    for cash in ocf:
        asset = expense.get(cash.end)
        if asset is None or not math.isfinite(asset.value) or asset.value < 0:
            continue
        fcf = cash.value - asset.value
        if math.isfinite(fcf) and fcf > 0:
            result.append(FinancialPoint(cash.end, max(cash.filed, asset.filed), fcf,
                                         'SEC filed cash flow less capex'))
    return result


def valuation_months(prices: pd.DataFrame, splits: pd.Series,
                     facts: dict, metric: str, method: str = 'ttm',
                     years: int = 5, now=None) -> pd.DataFrame:
    """As-of month-end multiple. Requires *filed* positive financial denominator.

    Does not extrapolate or interpolate and does not compute when share counts
    are missing or older than 215 days (TTM) / 485 days (annual).  P/E is
    approximate market cap / TTM net income, NOT exact reported EPS P/E.
    """
    columns=['date','multiple','price','denominator','denom_filed','denom_end',
             'shares','shares_filed','metric','method']
    closes = _close_series(prices)
    if closes.empty or not facts:
        return pd.DataFrame(columns=columns)
    asof = min(pd.Timestamp(now).normalize(), closes.index.max()) if now is not None else closes.index.max()
    events = denominator_events(facts, metric, method, asof)
    share_points = (share_events(facts, asof) if method == 'ttm' else
                    as_filed_annual_events(facts, SHARE_TAGS, 'shares', asof))
    if not events or not share_points:
        return pd.DataFrame(columns=columns)
    months = closes[closes.index <= asof].groupby(closes[closes.index <= asof].index.to_period('M')).tail(1)
    months = months[months.index >= asof - pd.DateOffset(years=years)]
    out = []
    for day, price in months.items():
        qualified = [p for p in events if p.filed <= day and p.end <= day]
        shares = [s for s in share_points if s.filed <= day and s.end <= day and s.value > 0]
        if not qualified or not shares: continue
        den = max(qualified, key=lambda p: (p.end,p.filed))
        if method == 'ttm':
            sh = max(shares, key=lambda p: (p.end,p.filed))
            if (day-den.end).days > 215 or (day-sh.end).days > 215: continue
        else:
            # Annual financial denominator and shares from the *same fiscal period*.
            matching_shares = [s for s in shares if s.end == den.end]
            if not matching_shares or (day-den.end).days > 485: continue
            sh = min(matching_shares, key=lambda p: p.filed)
        share_count = sh.value * _share_split_multiplier(sh.end, splits, asof)
        multiple = float(price)*share_count/den.value
        if np.isfinite(multiple) and 0 < multiple < 500:
            out.append({'date':day,'multiple':multiple, 'price':float(price),
                        'denominator':den.value,'denom_filed':den.filed,'denom_end':den.end,
                        'shares':share_count,'shares_filed':sh.filed,'metric':metric,'method':method})
    return pd.DataFrame(out,columns=columns)


def usable_history(prices,splits,facts,metric,years=5,min_points=24,now=None):
    """TTM preferred; permit *explicitly labeled* annual fallback."""
    from valuation_history import distribution_bands
    ttm=valuation_months(prices,splits,facts,metric,'ttm',years,now)
    if distribution_bands(ttm.multiple,min_points) is not None:
        return ttm,'ttm'
    annual=valuation_months(prices,splits,facts,metric,'annual',years,now)
    if distribution_bands(annual.multiple,min_points) is not None:
        return annual,'annual'
    return (ttm if len(ttm) >= len(annual) else annual), 'insufficient'
