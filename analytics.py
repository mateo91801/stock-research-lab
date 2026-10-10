"""Pure analytics for the Stock Research Lab. No networking or UI dependencies."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import math
from typing import Optional

import pandas as pd

STAGE_NAMES = {
    1: "Startup", 2: "Hyper Growth", 3: "Operating Leverage",
    4: "Capital Return", 5: "Decline",
}
STAGE_GUIDANCE = {
    1: ("Cash runway and milestones", "Price / sales (with caution)"),
    2: ("Sales growth and narrowing losses", "Price / sales, gross margin"),
    3: ("Margin expansion and profit growth", "Forward P/E or free cash flow"),
    4: ("Cash generation and capital allocation", "P/E or price / free cash flow"),
    5: ("Durability of earnings and reinvestment", "Normalized earnings / cash flow"),
}

@dataclass
class PhaseResult:
    stage: int
    reason: str
    evidence: list[str]
    metric_name: str


def num(value) -> Optional[float]:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except (TypeError, ValueError):
        return None


def classify_phase(revenue: list, profit: list, dividend_paid: Optional[float],
                   shares: list, metric_name: str = "Operating profit") -> Optional[PhaseResult]:
    """Annual data in newest-first order. Mirrors the five-question Phase Check rule.

    A missing mandatory field is *unknown*, not a negative answer. Never silently
    classify a company from absent profit / dividends / shares data.
    """
    r = [num(x) for x in revenue]
    p = [num(x) for x in profit]
    s = [num(x) for x in shares]
    evidence = []
    if len(r) < 2 or None in r[:2]:
        return None
    evidence.append(f"Latest revenue: {format_billions(r[0])}")
    if r[0] == 0 and r[1] == 0:
        return PhaseResult(1, "No revenue in either of the last two fiscal years.", evidence, metric_name)
    if len(r) >= 3 and None not in r[:3] and r[0] < r[1] < r[2]:
        return PhaseResult(5, "Annual revenue declined for two consecutive years.", evidence, metric_name)
    if dividend_paid is not None:
        evidence.append("Common dividend paid" if abs(dividend_paid) > 0 else "No common dividend recorded")
        if abs(dividend_paid) > 0:
            return PhaseResult(4, "The company paid a common dividend during the latest fiscal year.", evidence, metric_name)
    else:
        # Dividend data are sometimes absent for non-payers. We can still infer a
        # preliminary stage, but explain why it is not definitive in the UI.
        evidence.append("Dividend payment data unavailable (stage is provisional)")
    if not p or p[0] is None:
        return None
    evidence.append(f"Latest {metric_name.lower()}: {format_billions(p[0])}")
    if p[0] < 0:
        if len(p) >= 2 and p[1] is not None and p[1] < 0 and p[0] > p[1]:
            return PhaseResult(2, "The company is losing money, but its annual loss is narrowing.", evidence, metric_name)
        return PhaseResult(1, "The company is not yet profitable and its annual loss is not clearly narrowing.", evidence, metric_name)
    if len(s) >= 2 and s[0] is not None and s[1] is not None and s[0] < s[1]:
        evidence.append("Period-end shares outstanding decreased")
        return PhaseResult(4, "Profitable and the reported share count decreased year over year.", evidence, metric_name)
    evidence.append("Shares are flat, increasing, or unavailable")
    return PhaseResult(3, "The company is profitable without confirmed net share-count reduction or dividends.", evidence, metric_name)


def format_billions(value: Optional[float]) -> str:
    if value is None: return "N/A"
    v = abs(value)
    if v >= 1e12: return f"{'−' if value < 0 else ''}${v/1e12:.2f}T"
    if v >= 1e9: return f"{'−' if value < 0 else ''}${v/1e9:.1f}B"
    if v >= 1e6: return f"{'−' if value < 0 else ''}${v/1e6:.1f}M"
    return f"{'−' if value < 0 else ''}${v:,.0f}"


def yoy(latest, previous):
    latest, previous = num(latest), num(previous)
    return None if latest is None or previous is None or previous <= 0 else (latest/previous-1)*100


def choose_profit_metric(sector: str, industry: str):
    """Heuristic adaptation of Phase Check's industry-specific profit metric."""
    s, i = (sector or "").lower(), (industry or "").lower()
    financial_markers = ["bank", "insurance", "capital market", "consumer finance", "financial services", "mortgage reit"]
    ocf_markers = ["software", "it services", "information technology services", "payment", "biotech", "pharma", "health care technolog", "life science", "media", "entertainment", "professional services"]
    if any(m in i for m in financial_markers): return "Net income", "net_income"
    if any(m in i for m in ocf_markers): return "Operating cash flow", "ocf"
    return "Operating profit", "operating_income"


def valuation_zones(ratios: pd.Series):
    v = pd.to_numeric(ratios, errors='coerce').dropna()
    v = v[(v > 0) & (v < 1000)]
    if len(v) < 3:
        return None
    return {"lower": float(v.quantile(0.25)), "median": float(v.median()),
            "upper": float(v.quantile(0.75)), "observations": len(v)}


def split_factor_after(at_date, splits: pd.Series) -> float:
    """Shares from the original statement need split adjustment to match Yahoo's
    historical close series (split-adjusted). ONLY adjust for splits AFTER the
    statement date. Assumes the ticker's Yahoo price history uses split adjustments.
    """
    factor = 1.0
    if splits is None or splits.empty: return factor
    moment = pd.Timestamp(at_date)
    if moment.tzinfo is not None: moment = moment.tz_localize(None)
    for d, v in splits.items():
        d = pd.Timestamp(d)
        if d.tzinfo is not None: d = d.tz_localize(None)
        if d > moment and num(v) is not None and float(v) > 0:
            factor *= float(v)
    return factor


def annual_valuation(price_history: pd.DataFrame, annual_ocf: pd.Series,
                     annual_shares: pd.Series, splits: pd.Series) -> pd.DataFrame:
    """Fiscal-year-end snapshots, not a continuously calculated trailing multiple.

    Prices are from nearest trading day on/before fiscal year end; SEC release
    dates are not used. This is descriptive history, not a no-look-ahead backtest.
    """
    if price_history is None or price_history.empty or 'Close' not in price_history:
        return pd.DataFrame(columns=['date','multiple','price','ocf','shares'])
    closes = price_history['Close'].dropna().copy()
    if getattr(closes.index, 'tz', None) is not None:
        closes.index = closes.index.tz_localize(None)
    out = []
    for d, op in annual_ocf.items():
        op = num(op)
        if op is None or op <= 0: continue
        statement_date = pd.Timestamp(d).tz_localize(None) if pd.Timestamp(d).tzinfo else pd.Timestamp(d)
        if statement_date not in annual_shares.index: continue
        share = num(annual_shares.loc[statement_date])
        if share is None or share <= 0: continue
        recent = closes.loc[closes.index <= statement_date]
        if recent.empty or (statement_date - recent.index[-1]).days > 15: continue
        p = num(recent.iloc[-1])
        if p is None or p <= 0: continue
        adjusted_shares = share * split_factor_after(statement_date, splits)
        out.append({'date':statement_date, 'multiple':p*adjusted_shares/op,
                    'price':p, 'ocf':op, 'shares':adjusted_shares})
    return pd.DataFrame(out).sort_values('date') if out else pd.DataFrame(columns=['date','multiple','price','ocf','shares'])
