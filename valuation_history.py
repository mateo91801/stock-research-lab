"""Filing-date-aware monthly P/OCF valuation research.

SEC 10-Q cash flows are fiscal-YTD, not individual quarters. Compute quarterly
amounts by subtracting successive YTD reports, then sum the latest four
consecutive *filed* quarters. Use split-adjusted historical prices with diluted
weighted-average shares restated for later splits. This is an approximation of
market cap / trailing operating cash flow, NOT an intrinsic-value calculation.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd

OCF_TAGS = ('NetCashProvidedByUsedInOperatingActivities',)
SHARES_TAGS = ('WeightedAverageNumberOfDilutedSharesOutstanding',
               'WeightedAverageNumberOfSharesOutstandingBasic')


@dataclass(frozen=True)
class FinancialPoint:
    end: pd.Timestamp
    filed: pd.Timestamp
    value: float
    source: str


def _period_number(days: int) -> Optional[int]:
    # 52/53-week fiscal calendars and slight filing date shifts are supported.
    for quarter, low, high in ((1, 69, 115), (2, 153, 214),
                               (3, 235, 309), (4, 330, 402)):
        if low <= days <= high:
            return quarter
    return None


def _ytd_records(companyfacts: dict, tags: tuple[str, ...], unit: str,
                 now: pd.Timestamp | None = None) -> dict[tuple[pd.Timestamp, int], FinancialPoint]:
    """Extract originally published YTD facts, avoiding retrospective changes.

    Comparative facts included in later filings are deliberately excluded if
    they arrive >160 days after a fiscal period-end. For each period we use the
    *earliest* filed record, not whichever restated fact is newest today.
    """
    cutoff = now if now is not None else pd.Timestamp.today().normalize()
    selected = {}
    facts = companyfacts.get('facts', {}).get('us-gaap', {})
    for priority, tag in enumerate(tags):
        for raw in facts.get(tag, {}).get('units', {}).get(unit, []):
            if raw.get('form') not in ('10-Q', '10-K', '10-Q/A', '10-K/A'):
                continue
            try:
                start = pd.Timestamp(raw['start']).normalize()
                end = pd.Timestamp(raw['end']).normalize()
                filed = pd.Timestamp(raw['filed']).normalize()
                value = float(raw['val'])
            except (KeyError, ValueError, OverflowError, TypeError):
                continue
            q = _period_number((end - start).days)
            if (q is None or not np.isfinite(value) or end > cutoff or filed > cutoff
                    or filed < end or (filed - end).days > 160):
                continue
            if q == 4 and not raw['form'].startswith('10-K'):
                continue
            if q != 4 and not raw['form'].startswith('10-Q'):
                continue
            # Group by the exact fiscal year start so that adjacent fiscal
            # years cannot accidentally be subtracted from one another.
            key = (start, q)
            prior = selected.get(key)
            # First observed as-filed data; ties favor the preferred tag.
            ordering = (filed, priority, end)
            if prior is None or ordering < prior[0]:
                selected[key] = (ordering, FinancialPoint(end, filed, value, tag))
    return {key: entry[1] for key, entry in selected.items()}


def quarter_cashflows(companyfacts: dict, now: pd.Timestamp | None = None) -> list[FinancialPoint]:
    """Derive standalone operating cash flows from cumulative fiscal YTD."""
    ytd = _ytd_records(companyfacts, OCF_TAGS, 'USD', now)
    quarters = []
    for (fy_start, quarter), this in ytd.items():
        if quarter == 1:
            value, filed = this.value, this.filed
        else:
            previous = ytd.get((fy_start, quarter-1))
            if previous is None or (this.end - previous.end).days not in range(65, 112):
                continue
            value, filed = this.value - previous.value, max(this.filed, previous.filed)
        quarters.append(FinancialPoint(this.end, filed, value, this.source))
    return sorted(quarters, key=lambda item: (item.end, item.filed))


def trailing_cashflows(companyfacts: dict, now: pd.Timestamp | None = None) -> list[FinancialPoint]:
    """Four consecutive *available* standalone quarters, filed as of date."""
    qs = quarter_cashflows(companyfacts, now)
    events = []
    for i in range(3, len(qs)):
        four = qs[i-3:i+1]
        if all(65 <= (b.end-a.end).days <= 111 for a,b in zip(four, four[1:])):
            filed = max(q.filed for q in four)
            ocf = sum(q.value for q in four)
            # Keep losses in the quarterly calculations; don't draw an invalid
            # positive P/OCF multiple when total operating cash flow <= 0.
            events.append(FinancialPoint(four[-1].end, filed, ocf, 'SEC filed TTM OCF'))
    return events


def share_events(companyfacts: dict, now: pd.Timestamp | None = None) -> list[FinancialPoint]:
    """Prefer diluted YTD weighted-average shares, fallback basic if missing.

    Reported weighted average is a market-cap approximation, not the exact
    outstanding shares on each historical trading day.
    """
    records = _ytd_records(companyfacts, SHARES_TAGS, 'shares', now)
    by_end = {}
    for (_, _), p in records.items():
        if p.value <= 0:
            continue
        previous = by_end.get(p.end)
        if previous is None or (p.filed, p.source != SHARES_TAGS[0]) < (previous.filed, previous.source != SHARES_TAGS[0]):
            by_end[p.end] = p
    return sorted(by_end.values(), key=lambda event: (event.filed, event.end))


def _close_series(prices: pd.DataFrame) -> pd.Series:
    if prices is None or prices.empty or 'Close' not in prices:
        return pd.Series(dtype='float64')
    p = pd.to_numeric(prices.Close, errors='coerce').dropna()
    p.index = pd.DatetimeIndex(p.index).tz_localize(None).normalize()
    p = p[p > 0]
    return p.sort_index()[~p.index.duplicated(keep='last')]


def _share_split_multiplier(report_end: pd.Timestamp, splits: pd.Series,
                            last_price_date: pd.Timestamp) -> float:
    """Yahoo daily Close is split-adjusted even with auto_adjust=False.

    Therefore convert the old share count to the split basis of today's
    price series by applying subsequent stock splits.
    """
    factor = 1.0
    if splits is None or splits.empty:
        return factor
    for when, ratio in splits.items():
        moment = pd.Timestamp(when).tz_localize(None) if pd.Timestamp(when).tzinfo else pd.Timestamp(when)
        try:
            ratio = float(ratio)
        except (TypeError, ValueError):
            continue
        if report_end < moment <= last_price_date and np.isfinite(ratio) and ratio > 0:
            factor *= ratio
    return factor


def monthly_valuation(prices: pd.DataFrame, splits: pd.Series,
                      companyfacts: dict, years: int = 10,
                      now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Monthly as-of-known P/OCF using actual historical closing stock prices.

    Data from 10-K/10-Q enters the model on its SEC *filed* date. Never use
    results published after the month-end. Require fresh-enough known TTM and
    share data. Missing SEC quarters produce gaps, not interpolations.
    """
    close = _close_series(prices)
    cols = ['date', 'multiple', 'price', 'ocf_ttm', 'shares', 'ocf_period_end', 'ocf_filed', 'shares_filed']
    if close.empty:
        return pd.DataFrame(columns=cols)
    asof = min(pd.Timestamp(now).normalize(), close.index.max()) if now is not None else close.index.max()
    close = close[close.index <= asof]
    if close.empty:
        return pd.DataFrame(columns=cols)
    ttm = sorted(trailing_cashflows(companyfacts, asof), key=lambda p: (p.filed, p.end))
    shares = share_events(companyfacts, asof)
    if not ttm or not shares:
        return pd.DataFrame(columns=cols)
    # Group each calendar month to its *last available trading close*.
    monthly = close.groupby(close.index.to_period('M')).tail(1)
    monthly = monthly[monthly.index >= (asof - pd.DateOffset(years=years))]
    # Do not put the very latest quote in a past, unfiled quarter.
    rows = []
    for day, price in monthly.items():
        candidate_cash = [p for p in ttm if p.filed <= day and p.end <= day]
        candidate_shares = [p for p in shares if p.filed <= day and p.end <= day]
        if not candidate_cash or not candidate_shares:
            continue
        ocf_point = max(candidate_cash, key=lambda p: (p.end, p.filed))
        share_point = max(candidate_shares, key=lambda p: (p.end, p.filed))
        if ((day - ocf_point.end).days > 215 or (day - share_point.end).days > 215
                or ocf_point.value <= 0 or share_point.value <= 0):
            continue
        adjusted_shares = share_point.value * _share_split_multiplier(share_point.end, splits, asof)
        multiple = float(price) * adjusted_shares / ocf_point.value
        if 0 < multiple < 500 and np.isfinite(multiple):
            rows.append({'date': day, 'multiple': multiple, 'price': float(price),
                         'ocf_ttm': ocf_point.value, 'shares': adjusted_shares,
                         'ocf_period_end': ocf_point.end, 'ocf_filed': ocf_point.filed,
                         'shares_filed': share_point.filed})
    return pd.DataFrame(rows, columns=cols)


def distribution_bands(series: pd.Series, min_points=24) -> Optional[dict]:
    """25th/50th/75th percentiles; relative history, not intrinsic value."""
    clean = pd.to_numeric(series, errors='coerce').replace([np.inf, -np.inf], np.nan).dropna()
    clean = clean[(clean > 0) & (clean < 500)]
    if len(clean) < min_points:
        return None
    return {'low': float(clean.quantile(.25)), 'median': float(clean.median()),
            'high': float(clean.quantile(.75)), 'observations': len(clean)}


def as_filed_annual_events(companyfacts: dict, tags: tuple[str, ...],
                           unit: str, now: pd.Timestamp | None = None) -> list[FinancialPoint]:
    """Earliest original 10-K annual disclosures for each FY end.

    Companyfacts includes *later comparative facts* for earlier reporting years.
    For historical research these must not replace the figures known back then.
    """
    cutoff = (pd.Timestamp(now).normalize() if now is not None
              else pd.Timestamp.today().normalize())
    group = companyfacts.get('facts', {}).get('us-gaap', {})
    selected = {}
    for priority, tag in enumerate(tags):
        for raw in group.get(tag, {}).get('units', {}).get(unit, []):
            if raw.get('form') != '10-K':
                continue
            try:
                start = pd.Timestamp(raw['start']).normalize()
                end = pd.Timestamp(raw['end']).normalize()
                filed = pd.Timestamp(raw['filed']).normalize()
                value = float(raw['val'])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            days = (end - start).days
            if (not 325 <= days <= 402 or end > cutoff or filed > cutoff
                    or filed < end or (filed - end).days > 180
                    or not np.isfinite(value) or value <= 0):
                continue
            # Prefer primary tagged annual figure; if multiple filings use
            # first as-filed release, not hindsight revisions.
            order = (priority, filed)
            if end not in selected or order < selected[end][0]:
                selected[end] = (order, FinancialPoint(end, filed, value, tag))
    return sorted((item[1] for item in selected.values()), key=lambda r: r.end)


def annual_asfiled_monthly_valuation(prices: pd.DataFrame, splits: pd.Series,
                                      companyfacts: dict, years: int = 5,
                                      now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Monthly price divided by last PUBLICLY FILED annual operating cash flow.

    Fallback only: denominator is a fixed FY number between 10-K publications,
    not trailing-four-quarter cash flow. Prevents future FY hindsight leakage.
    """
    close = _close_series(prices)
    cols = ['date', 'multiple', 'price', 'ocf_annual', 'shares',
            'ocf_period_end', 'ocf_filed', 'shares_filed']
    if close.empty:
        return pd.DataFrame(columns=cols)
    asof = (min(pd.Timestamp(now).normalize(), close.index.max()) if now is not None
            else close.index.max())
    cash = as_filed_annual_events(companyfacts, OCF_TAGS, 'USD', asof)
    shares = as_filed_annual_events(companyfacts, SHARES_TAGS, 'shares', asof)
    share_by_end = {item.end: item for item in shares}
    # Require same FY for cash flow and annual share denominator: no mixing
    # between companies' or eras' different reporting periods.
    paired = [(event, share_by_end[event.end]) for event in cash if event.end in share_by_end]
    if not paired:
        return pd.DataFrame(columns=cols)
    monthly_close = close.groupby(close.index.to_period('M')).tail(1)
    monthly_close = monthly_close[monthly_close.index >= asof - pd.DateOffset(years=years)]
    rows = []
    for day, price in monthly_close.items():
        eligible = [(cashp, sharep) for cashp, sharep in paired
                    if cashp.filed <= day and sharep.filed <= day]
        if not eligible:
            continue
        cashp, sharep = max(eligible, key=lambda pair: pair[0].end)
        # An annual report should cease to be a useful valuation basis if
        # more than ~16 months have passed since its FY end.
        if (day - cashp.end).days > 485:
            continue
        adjusted_shares = sharep.value * _share_split_multiplier(sharep.end, splits, asof)
        multiple = float(price) * adjusted_shares / cashp.value
        if np.isfinite(multiple) and 0 < multiple < 500:
            rows.append(dict(date=day, multiple=multiple, price=float(price),
                             ocf_annual=cashp.value, shares=adjusted_shares,
                             ocf_period_end=cashp.end, ocf_filed=cashp.filed,
                             shares_filed=sharep.filed))
    return pd.DataFrame(rows, columns=cols)
