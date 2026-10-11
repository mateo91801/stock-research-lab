"""Stock Research Lab: conservative fiscal-year audit of annual financials.

This does not pretend that an unusual result is necessarily wrong: it WITHHOLDS
suspect observations from ratios / CAGR and tells the reader to check the 10-K.
No third-party data is fabricated or interpolated.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math
import pandas as pd


def fiscal_year(period_end) -> int:
    """Display convention for 52/53-week December fiscal years ending in early Jan.

    SEC companyfacts stores exact period ends; this helper affects presentation and
    comparisons, not the original fiscal period date.
    """
    d = pd.Timestamp(period_end)
    return d.year - 1 if d.month == 1 and d.day <= 15 else d.year


def _values_by_year(series: pd.Series) -> dict[int, tuple[pd.Timestamp, float]]:
    result = {}
    if series is None or series.empty:
        return result
    for end, value in pd.to_numeric(series, errors='coerce').dropna().items():
        try:
            t = pd.Timestamp(end)
            v = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(v):
            continue
        year = fiscal_year(t)
        # If two periods map to one fiscal year, don't silently sum or combine.
        # Take the later fiscal end as the presentation candidate; a separate
        # duplicate flag is produced by the audit routine.
        if year not in result or t > result[year][0]:
            result[year] = (t, v)
    return result


def isolated_outliers(series: pd.Series, *, high=1.45, low=0.58) -> dict[int, str]:
    """Detect a one-year spike/drop bracketed by broadly similar adjacent years.

    A permanent step-change (e.g. sustained acquisition growth) is not called an
    outlier. All findings are REVIEW flags, not assertions of bad accounting.
    """
    vals = _values_by_year(series)
    flagged = {}
    for year, (_, current) in vals.items():
        if year-1 not in vals or year+1 not in vals:
            continue
        before, after = vals[year-1][1], vals[year+1][1]
        if min(current, before, after) <= 0:
            continue
        neighbor_ratio = before/after
        if not 0.65 <= neighbor_ratio <= 1.55:
            continue
        if current > high*max(before, after):
            flagged[year] = 'isolated upward spike compared with adjacent fiscal years'
        elif current < low*min(before, after):
            flagged[year] = 'isolated downward dip compared with adjacent fiscal years'
    return flagged


@dataclass
class RevenueAudit:
    accepted: pd.Series
    issues: list[dict] = field(default_factory=list)
    checked_years: int = 0
    hidden_years: list[int] = field(default_factory=list)
    source: str = ''


def audit_revenue(preferred: pd.Series, corroborating: pd.Series | None = None,
                  source: str = 'SEC EDGAR', *, discrepancy=0.12) -> RevenueAudit:
    """Review SEC-versus-other-source periods and suppress unresolved anomalies.

    Other source is a CROSS-CHECK only; never silently replace official SEC values
    with a commercial feed when reports conflict. Detailed period ends are retained.
    """
    primary = pd.to_numeric(preferred, errors='coerce').sort_index(ascending=False).copy() if preferred is not None else pd.Series(dtype='float64')
    secondary = _values_by_year(corroborating)
    years = _values_by_year(primary)
    issues = []
    excluded = set()
    counts = {}
    for end, value in primary.dropna().items():
        yr = fiscal_year(end)
        counts[yr] = counts.get(yr, 0) + 1
    for yr, n in counts.items():
        if n > 1:
            excluded.add(yr)
            issues.append({'fiscal_year':yr, 'issue':'multiple fiscal period ends mapped to the same year',
                           'detail':'Review period-end dates and fiscal calendar in the annual filing.'})
    for yr, reason in isolated_outliers(primary).items():
        excluded.add(yr)
        issues.append({'fiscal_year':yr, 'issue':reason,
                       'detail':'Potential tag/period mismatch. Check the company’s annual 10-K before using this value.'})
    for yr, (_, amount) in years.items():
        if amount <= 0:
            excluded.add(yr)
            issues.append({'fiscal_year':yr, 'issue':'non-positive reported annual revenue',
                           'detail':'Revenue ratios are suppressed until the figure is verified.'})
        if yr in secondary:
            other = secondary[yr][1]
            if amount > 0 and other > 0 and abs(amount-other)/max(amount, other) > discrepancy:
                excluded.add(yr)
                issues.append({'fiscal_year':yr, 'issue':'SEC and Yahoo annual revenue disagree by over 12%',
                               'detail':'SEC ${:,.2f}B vs Yahoo ${:,.2f}B. Check identical fiscal periods and the 10-K.'.format(amount/1e9, other/1e9)})
    accepted = primary.copy()
    for period in list(accepted.index):
        if fiscal_year(period) in excluded:
            accepted = accepted.drop(period)
    return RevenueAudit(accepted=accepted, issues=sorted(issues, key=lambda x: x['fiscal_year'], reverse=True),
                        checked_years=len(years), hidden_years=sorted(excluded,reverse=True),source=source)


def audit_rows(audit: RevenueAudit):
    return [{'Fiscal year': r['fiscal_year'], 'Flag':r['issue'], 'Details':r['detail']} for r in audit.issues]
