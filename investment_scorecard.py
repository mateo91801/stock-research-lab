"""Stock Research Lab v1.5 — transparent, reproducible rule-based screen.

Not investment advice, a forecast or a proxy for intrinsic value. Never infer
management skill, business moat, or missing financial values from a ticker.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import pandas as pd
from data_quality import fiscal_year


@dataclass(frozen=True)
class Item:
    name: str
    rating: int | None
    explanation: str
    evidence: str


@dataclass(frozen=True)
class Decision:
    verdict: str
    headline: str
    explanation: str
    confidence: str
    quality: float | None
    valuation_rating: int | None
    valuation_lens: str
    valuation_multiple: float | None
    valuation_median: float | None
    valuation_percentile: float | None
    valuation_method: str
    observations: int
    valuation_date: str
    items: tuple[Item, ...]
    warnings: tuple[str, ...]


def _num(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def _series(values, key):
    s = values.get(key)
    if not isinstance(s, pd.Series) or s.empty:
        return pd.Series(dtype='float64')
    s = pd.to_numeric(s, errors='coerce').dropna()
    return s.sort_index(ascending=False)


def _latest_matching(values, key, target_date, days=45):
    s = _series(values, key)
    if target_date is None or s.empty:
        return None
    try:
        dates = pd.to_datetime(s.index)
        differences = abs((dates - pd.Timestamp(target_date)).days)
        matches = [(diff, i) for i, diff in enumerate(differences) if diff <= days]
        if not matches:
            return None
        _, i = min(matches)
        return _num(s.iloc[i])
    except (TypeError, ValueError):
        return None


def _latest_revenue(values):
    rev = _series(values, 'revenue')
    if rev.empty:
        return None, None
    return pd.Timestamp(rev.index[0]), _num(rev.iloc[0])


def _growth(values):
    rev = _series(values, 'revenue')
    by_fy = {fiscal_year(d): n for d, n in rev.items() if _num(n) is not None}
    if not by_fy:
        return Item('Revenue growth', None, 'No usable annual revenue.', 'No growth score')
    fy = max(by_fy)
    if not all(y in by_fy for y in (fy, fy-1, fy-2, fy-3)):
        return Item('Revenue growth', None, 'Need four consecutive fiscal-year revenue figures.', 'No growth score')
    end, start = by_fy[fy], by_fy[fy-3]
    if start <= 0 or end <= 0:
        return Item('Revenue growth', None, 'Growth is not meaningful with nonpositive starting or ending revenue.', 'No growth score')
    cagr = ((end/start)**(1/3)-1)*100
    one = ((end/by_fy[fy-1])-1)*100 if by_fy[fy-1]>0 else None
    rating = 5 if cagr >= 15 else 4 if cagr >= 8 else 3 if cagr >= 3 else 2 if cagr >= 0 else 1
    if one is not None and one < -10:
        rating = min(2, rating)
    return Item('Revenue growth', rating,
                f'Revenue grew {cagr:+.1f}% annually over 3 years' + (f'; latest year {one:+.1f}%.' if one is not None else '.'),
                'Three-year revenue CAGR, with a recent-decline safeguard')


def _profitability(values):
    date, rev = _latest_revenue(values)
    op = _latest_matching(values, 'operating_income', date)
    if rev is None or rev <= 0 or op is None:
        return Item('Profitability', None, 'A comparable fiscal-year revenue and operating-profit pair is unavailable.', 'No profitability score')
    margin = op / rev * 100
    rating = 5 if margin >= 20 else 4 if margin >= 8 else 3 if margin >= 3 else 2 if margin > 0 else 1
    return Item('Profitability', rating,
                f'Operating margin is {margin:.1f}%; approximately ${margin:.2f} operating profit per $100 of sales.',
                'Latest fiscal-year operating profit divided by revenue')


def _cash(values):
    date, rev = _latest_revenue(values)
    fcf = _latest_matching(values, 'fcf', date)
    ocf = _latest_matching(values, 'ocf', date)
    if rev is None or rev <= 0 or fcf is None or ocf is None:
        return Item('Cash generation', None, 'Both operating cash flow and free cash flow for the latest revenue year are required.', 'No cash score')
    margin = fcf/rev*100
    rating = (1 if ocf <= 0 or fcf <= 0 else 5 if margin >= 15 else 4 if margin >= 8
              else 3 if margin >= 3 else 2)
    return Item('Cash generation', rating,
                f'Free-cash-flow margin is {margin:.1f}%; operating cash flow is {"positive" if ocf>0 else "not positive"}.',
                'Same-year free cash flow and operating cash flow divided by revenue')


def _earnings(values):
    earnings = _series(values, 'net_income')
    by_fy = {fiscal_year(d): _num(n) for d, n in earnings.items() if _num(n) is not None}
    if not by_fy:
        return Item('Earnings consistency', None, 'No usable annual net income series.', 'No earnings score')
    fy = max(by_fy)
    years = [fy-i for i in range(5)]
    if any(year not in by_fy for year in years[:3]):
        return Item('Earnings consistency', None, 'Need at least three consecutive fiscal years of net income.', 'No earnings score')
    observed = [by_fy[year] for year in years if year in by_fy]
    positive = sum(x > 0 for x in observed)
    if all(year in by_fy for year in years):
        rating = 5 if positive==5 and observed[0]>=observed[-1] else 4 if positive>=4 else 3 if positive==3 else 2 if positive==2 else 1
    else:
        rating = 4 if positive == len(observed) and observed[0]>=observed[-1] else 3 if positive==len(observed) else 2 if positive>=2 else 1
    if observed[0] <= 0:
        rating = min(rating,2)
    return Item('Earnings consistency', rating,
                f'Profitable in {positive} of {len(observed)} available recent fiscal years'
                + ('; latest year is a loss.' if observed[0] <= 0 else '.'),
                'Three to five consecutive or recent annual net-income results; shorter history capped at 4')


def _balance(values, financial_position):
    p = financial_position or {}
    cash = _num(p.get('cash'))
    debt = _num(p.get('total_debt'))
    date, _ = _latest_revenue(values)
    ocf = _latest_matching(values, 'ocf', date)
    statement = p.get('date')
    if cash is None or debt is None or ocf is None or ocf <= 0 or not statement or date is None:
        return Item('Balance sheet', None, 'Cash, total debt, current annual operating cash flow, or their dates are unavailable.', 'No leverage score')
    try:
        if abs((pd.Timestamp(statement)-date).days) > 410:
            return Item('Balance sheet', None, 'Balance-sheet figures are not close enough to the reported fiscal year.', 'No leverage score')
    except (TypeError, ValueError):
        return Item('Balance sheet', None, 'Cannot confirm a comparable balance-sheet date.', 'No leverage score')
    ratio = (debt - cash) / ocf
    rating = 5 if ratio<=0 else 4 if ratio<=1 else 3 if ratio<=2 else 2 if ratio<=4 else 1
    return Item('Balance sheet', rating,
                f'Net debt is {ratio:.1f}× annual operating cash flow (debt minus cash, then divided by cash flow).',
                'Yahoo balance-sheet cash and total debt versus annual operating cash flow; rough leverage proxy')


def _valuation(histories, price_asof):
    # Prefer distributable free cash flow, then operating cash flow, then earnings.
    # Every history was already constructed as-of SEC filing availability by the Lab.
    for key, label in [('pfcf','P/FCF'),('pocf','P/OCF'),('pe','P/E')]:
        candidate = (histories or {}).get(key) or {}
        df, method = candidate.get('history'), candidate.get('method', '')
        if not isinstance(df, pd.DataFrame) or 'multiple' not in df.columns or 'date' not in df.columns:
            continue
        subset = df[['date','multiple']].copy()
        subset['date'] = pd.to_datetime(subset['date'], errors='coerce')
        subset['multiple'] = pd.to_numeric(subset['multiple'], errors='coerce')
        subset = subset.dropna()
        subset = subset[(subset.multiple > 0) & (subset.multiple < 500)].sort_values('date')
        if len(subset) < 24:
            continue
        last = subset.iloc[-1]
        try:
            age = (pd.Timestamp(price_asof) - pd.Timestamp(last.date)).days
        except (ValueError, TypeError):
            continue
        if age < -3 or age > 45:
            continue
        mult = float(last.multiple)
        vals = subset.multiple
        pct = 100*(float((vals < mult).sum()) + 0.5*float((vals == mult).sum()))/len(vals)
        rating = 5 if pct <= 15 else 4 if pct <= 35 else 3 if pct < 65 else 2 if pct < 85 else 1
        return rating, label, mult, float(vals.median()), pct, method, len(vals), pd.Timestamp(last.date).strftime('%Y-%m-%d')
    return None, '', None, None, None, '', 0, ''


def analyze(values, *, histories=None, financial_position=None, quality_audit=None,
            price_asof=None, sector='', industry='') -> Decision:
    """Returns a rule-based five-way result with full evidence; no external calls."""
    items = (_growth(values), _profitability(values), _cash(values),
             _earnings(values), _balance(values, financial_position))
    ratings = {i.name:i.rating for i in items}
    scored = [s for s in ratings.values() if s is not None]
    quality = round(sum(scored)/len(scored), 2) if scored else None
    val, lens, mult, med, pct, method, count, date = _valuation(histories, price_asof)
    warnings = []
    audit = quality_audit
    if audit is not None and getattr(audit,'hidden_years',[]):
        warnings.append('Revenue observations flagged and excluded; inspect the data-quality report.')
    date_last, _ = _latest_revenue(values)
    if price_asof and date_last is not None and (pd.Timestamp(price_asof)-date_last).days > 550:
        warnings.append('Latest annual revenue is stale relative to the last stock-price observation.')
    if val is None:
        warnings.append('No sufficiently complete and recent 24+ observation valuation history.')
    if ratings['Balance sheet'] is None:
        warnings.append('Debt and cash coverage is incomplete; financial-health scoring is partial.')
    financial_industry = any(x in (sector+' '+industry).lower() for x in
                             ('bank','insurance','asset management','financial services','capital markets','reit','credit services'))
    if financial_industry:
        warnings.append('This general-purpose operating-company scoring model is not suitable for financial firms and REITs.')
    enough = (len(scored)>=3 and ratings['Revenue growth'] is not None and
              ratings['Cash generation'] is not None and val is not None and
              not financial_industry and not any('stale' in s.lower() for s in warnings))
    confidence = 'Moderate' if enough else 'Limited'
    if enough and len(scored)==5 and not warnings:
        confidence = 'Higher (rule coverage only)'
    if not enough:
        verdict, headline = 'PASS', 'Insufficient evidence for a dependable buy/hold signal'
        explanation = ('The Lab is passing on making a positive investment call because some essential '
                       'company fundamentals or recent historical valuation data are unavailable. '
                       'PASS here means insufficient support—not proof this is a bad company.')
    elif quality <= 2 and val <= 2 and ratings['Cash generation'] is not None and ratings['Profitability'] is not None and ratings['Cash generation'] <= 2 and ratings['Profitability'] <= 2:
        verdict, headline = 'SELL', 'Weak underlying performance and an unfavorable valuation'
        explanation = ('Multiple measurable business fundamentals are weak, while this stock is not '
                       'cheap relative to its own valuation history. SELL is a screening warning for current '
                       'holders—not a personalized instruction to trade.')
    elif (quality>=4 and val>=4 and (ratings['Profitability'] or 0)>=3 and
          (ratings['Cash generation'] or 0)>=3 and
          (ratings['Earnings consistency'] is None or ratings['Earnings consistency']>=3) and
          (ratings['Balance sheet'] is None or ratings['Balance sheet']>=3) and
          not (audit is not None and getattr(audit,'hidden_years',[]))):
        verdict, headline = 'BUY', 'Strong fundamentals with a historically attractive valuation'
        explanation = ('The company clears conservative fundamental thresholds and trades at a '
                       'relatively low multiple versus its own observed history. This is a rules-based '
                       'research signal—not an estimate of intrinsic fair value or a guarantee of returns.')
    elif quality>=3.5:
        verdict, headline = 'WATCH', 'Business looks solid; monitor valuation and remaining risks'
        explanation = ('Several business metrics score well, but price, financial risks, or '
                       'outstanding data issues keep this outside the Lab’s stricter BUY screen.')
    elif quality>=3 and val>=3:
        verdict, headline = 'HOLD', 'Mixed-to-reasonable fundamentals; no compelling buy signal'
        explanation = ('The business does not clear the stronger BUY criteria. HOLD is a contextual '
                       'screening label for existing holders, not advice to establish a position.')
    else:
        verdict, headline = 'PASS', 'Current evidence does not clear the quality-and-price screen'
        explanation = ('The combination of business scores and valuation is not strong enough '
                       'under the Lab’s rule set. This does not predict future share-price performance.')
    return Decision(verdict, headline, explanation, confidence, quality, val,
                    lens, mult, med, pct, method, count, date,
                    items, tuple(warnings))
