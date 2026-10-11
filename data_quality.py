"""Conservative SEC/Yahoo annual revenue reconciliation (Stock Research Lab v1.4.2).

Cross-checked means SEC annual revenue and an independently retrieved Yahoo
annual-revenue observation agree for the SAME fiscal period; it is not a
financial-statement audit or verification of the underlying accounting.
The dashboard explicitly reports each year that cannot be cross-checked.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math
import pandas as pd


def fiscal_year(period_end) -> int:
    """Label fiscal years ending Jan 1-15 with the preceding calendar year."""
    d = pd.Timestamp(period_end)
    return d.year - 1 if d.month == 1 and d.day <= 15 else d.year


def _values_by_year(series: pd.Series | None) -> dict[int, tuple[pd.Timestamp, float]]:
    result = {}
    if series is None or series.empty:
        return result
    for end, value in pd.to_numeric(series, errors='coerce').dropna().items():
        try:
            t, v = pd.Timestamp(end), float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(v):
            continue
        year = fiscal_year(t)
        if year not in result or t > result[year][0]:
            result[year] = (t, v)
    return result


def isolated_outliers(series: pd.Series, *, high=1.45, low=0.58) -> dict[int, str]:
    """Flag isolated one-year anomalies, never a sustained acquisition step."""
    vals = _values_by_year(series)
    flagged = {}
    for year, (_, value) in vals.items():
        if year-1 not in vals or year+1 not in vals:
            continue
        before, after = vals[year-1][1], vals[year+1][1]
        if min(value, before, after) <= 0 or not 0.65 <= before/after <= 1.55:
            continue
        if value > high * max(before, after):
            flagged[year] = 'Isolated upward spike relative to adjacent fiscal years'
        elif value < low * min(before, after):
            flagged[year] = 'Isolated downward dip relative to adjacent fiscal years'
    return flagged


@dataclass
class RevenueAudit:
    accepted: pd.Series
    issues: list[dict] = field(default_factory=list)
    checked_years: int = 0
    hidden_years: list[int] = field(default_factory=list)
    source: str = ''
    verified_years: list[int] = field(default_factory=list)
    unverified_years: list[int] = field(default_factory=list)
    statuses: list[dict] = field(default_factory=list)


def audit_revenue(preferred: pd.Series, corroborating: pd.Series | None = None,
                  source: str = 'SEC EDGAR', *, discrepancy=0.025,
                  max_period_gap_days=32) -> RevenueAudit:
    """Classify per fiscal year; quarantine significant discrepancies/anomalies.

    Do NOT call two values independently corroborated if both originate from
    Yahoo. Also require same FY and near-matching YEAR-END dates to avoid
    comparing fiscal periods that merely share a display-year label.
    """
    primary = (pd.to_numeric(preferred, errors='coerce').sort_index(ascending=False).copy()
               if preferred is not None else pd.Series(dtype='float64'))
    secondary = _values_by_year(corroborating)
    years = _values_by_year(primary)
    has_sec_primary = source.strip().upper().startswith('SEC')
    issues, excluded, statuses = [], set(), []
    counts = {}
    for end, value in primary.dropna().items():
        yr = fiscal_year(end)
        counts[yr] = counts.get(yr, 0) + 1
    for yr, n in counts.items():
        if n > 1:
            excluded.add(yr)
            issues.append({'fiscal_year': yr,
                           'issue': 'Multiple fiscal period ends mapped to the same year',
                           'detail': 'Review the fiscal calendar and original annual 10-K.'})
    for yr, reason in isolated_outliers(primary).items():
        excluded.add(yr)
        issues.append({'fiscal_year': yr, 'issue': reason,
                       'detail': 'Potential annual tag/period mismatch; review the original 10-K.'})

    for yr, (end, amount) in sorted(years.items(), reverse=True):
        other = secondary.get(yr) if has_sec_primary else None
        status, detail, difference, compare_val = 'Unverified', '', None, None
        if amount <= 0:
            excluded.add(yr)
            detail = 'Non-positive reported annual revenue; investigate the source.'
            issues.append({'fiscal_year': yr, 'issue': 'Non-positive annual revenue', 'detail': detail})
        elif not has_sec_primary:
            detail = 'SEC annual revenue unavailable; Yahoo-only value cannot be independently cross-checked.'
        elif other is None:
            detail = 'SEC annual figure available; no corresponding Yahoo annual figure returned.'
        else:
            other_end, compare_val = other
            gap = abs((end - other_end).days)
            if gap > max_period_gap_days:
                detail = f'Fiscal period ends differ by {gap} days; not compared.'
                compare_val = None
            elif compare_val <= 0:
                detail = 'Yahoo returned a non-positive figure; cannot compare.'
                compare_val = None
            else:
                difference = 100 * abs(amount - compare_val) / max(abs(amount), abs(compare_val))
                if difference <= discrepancy * 100:
                    status = 'Cross-checked'
                    detail = f'SEC and Yahoo annual values agree within {100*discrepancy:g}% for matching FY ends.'
                else:
                    status = 'Discrepancy'
                    detail = f'SEC and Yahoo differ by {difference:.1f}%; investigate fiscal period and accounting basis.'
                    excluded.add(yr)
                    issues.append({'fiscal_year': yr, 'issue': 'SEC/Yahoo annual revenue disagreement',
                                   'detail': detail + f' SEC ${amount/1e9:,.2f}B vs Yahoo ${compare_val/1e9:,.2f}B.'})
        if yr in excluded:
            status = 'Discrepancy'
            if not detail or status == 'Discrepancy' and difference is None:
                detail = (detail + ' ' if detail else '') + 'Flagged or ambiguous financial period; excluded from revenue analysis.'
        statuses.append({'Fiscal year': f'FY{yr}', 'Status': status,
                         'Primary source': source, 'SEC/Yahoo primary (USD B)': round(amount/1e9, 3),
                         'Yahoo comparison (USD B)': round(compare_val/1e9, 3) if compare_val is not None else None,
                         'Difference (%)': round(difference, 2) if difference is not None else None,
                         'Period end': end.strftime('%Y-%m-%d'), 'Details': detail})

    accepted = primary.drop(index=[end for end in primary.index if fiscal_year(end) in excluded])
    checked = [int(r['Fiscal year'][2:]) for r in statuses if r['Status'] == 'Cross-checked']
    unverified = [int(r['Fiscal year'][2:]) for r in statuses if r['Status'] == 'Unverified']
    return RevenueAudit(accepted=accepted,
                        issues=sorted(issues, key=lambda r: r['fiscal_year'], reverse=True),
                        checked_years=len(years), hidden_years=sorted(excluded, reverse=True),
                        source=source, verified_years=checked,
                        unverified_years=unverified, statuses=statuses)


def audit_rows(audit: RevenueAudit):
    return [{'Fiscal year': r['fiscal_year'], 'Flag': r['issue'], 'Details': r['detail']}
            for r in audit.issues]
