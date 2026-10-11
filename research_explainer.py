"""Plain-English, data-aware financial explanations for Stock Research Lab v1.4.4.

Presentation ONLY: does not supply or alter source facts, pricing, phase decisions,
valuation observations, percentile bands, or investment recommendations.
Missing or incomparable observations are described, never invented.
"""
from __future__ import annotations

import math
from typing import Any
import pandas as pd


def valid_number(value: Any) -> float | None:
    """Convert available finite numeric values; reject NaN/NaT/inf and nulls."""
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def usd(value: Any) -> str:
    """Readable magnitude, including negative signs, without hiding sign."""
    n = valid_number(value)
    if n is None:
        return 'N/A'
    magnitude = abs(n)
    sign = '−' if n < 0 else ''
    if magnitude >= 1e12:
        return f'{sign}${magnitude/1e12:,.2f}T'
    if magnitude >= 1e9:
        return f'{sign}${magnitude/1e9:,.1f}B'
    if magnitude >= 1e6:
        return f'{sign}${magnitude/1e6:,.1f}M'
    return f'{sign}${magnitude:,.0f}'


def fiscal_yoy(latest: Any, prior: Any) -> float | None:
    """YoY growth ONLY across roughly one matching fiscal-year interval.

    Prevent a quarantined/missing year from masquerading as a one-year change.
    Financial values in rows are expected to have a date and revenue key.
    """
    if latest is None or prior is None:
        return None
    try:
        days = (pd.Timestamp(latest['date']) - pd.Timestamp(prior['date'])).days
        a = valid_number(latest['revenue'])
        b = valid_number(prior['revenue'])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not 315 <= days <= 415 or a is None or b is None or a < 0 or b <= 0:
        return None
    return (a / b - 1) * 100


def headline_reading(latest: Any, prior: Any, price: Any) -> list[tuple[str, str]]:
    """Explain price, revenue, operating cash flow using available annual facts."""
    price_n = valid_number(price)
    price_text = (f'The last closing price of ${price_n:,.2f} is the market price for one share. '
                  'A low share price does not necessarily mean a cheap business, and a high '
                  'share price does not necessarily mean an expensive one.'
                  if price_n is not None else
                  'A recent share price is unavailable. Share price alone would not tell you whether a business is cheap.')
    if latest is None:
        sales_text = 'Annual revenue is unavailable, so we cannot determine sales size or year-over-year growth.'
        cash_text = 'Annual operating cash flow is unavailable; it cannot safely be inferred from revenue.'
    else:
        sales = valid_number(latest.get('revenue'))
        yoy_rate = fiscal_yoy(latest, prior)
        if sales is None:
            sales_text = 'Annual revenue is unavailable, so the sales trend cannot be evaluated.'
        elif yoy_rate is None:
            sales_text = (f'Annual revenue of {usd(sales)} is total sales during the latest reported fiscal year, '
                          'not profit. A matching prior fiscal year is unavailable, so one-year growth cannot be confirmed.')
        else:
            direction = 'rose' if yoy_rate > 0 else ('fell' if yoy_rate < 0 else 'was unchanged')
            sales_text = (f'Annual revenue is {usd(sales)} and {direction} {abs(yoy_rate):.1f}% '
                          'from the preceding fiscal year. Revenue measures sales, not how much the company kept.')
        ocf = valid_number(latest.get('ocf'))
        if ocf is None:
            cash_text = ('Operating cash flow was not available for the latest fiscal year. '
                         'This is different from saying the company generated $0.')
        else:
            verb = ('generated' if ocf >= 0 else 'used')
            cash_text = (f'The business {verb} {usd(abs(ocf))} of cash through normal operations '
                         'during the latest fiscal year. This is BEFORE capital expenditures; '
                         'it is not the same as net profit or free cash flow.')
    return [('Share price', price_text), ('Revenue', sales_text), ('Operating cash flow', cash_text)]


def growth_reading(one_year: Any, three_year: Any, five_year: Any, kind: str) -> str:
    """Interpret growth figures only by comparison within the same metric."""
    a, b, c = (valid_number(v) for v in (one_year, three_year, five_year))
    measure = 'Revenue' if kind == 'revenue' else 'Net income'
    if a is None and b is None and c is None:
        return (f'{measure} CAGR is unavailable for these periods. This can happen when a fiscal year '
                'is missing or the starting/ending value is zero or negative; N/A does not mean 0% growth.')
    if a is not None and c is not None:
        gap = abs(a - c)
        if gap < 1:
            change = 'roughly in line with'
        elif a > c:
            change = 'above'
        else:
            change = 'below'
        return (f'{measure} changed {a:+.1f}% over the latest fiscal year, '
                f'versus {c:+.1f}% per year over five years. The recent pace is {change} '
                'the longer-term annualized rate. This describes the past, not a forecast.')
    points = []
    for label, value in [('1-year', a), ('3-year', b), ('5-year', c)]:
        if value is not None:
            points.append(f'{label}: {value:+.1f}%')
    return (f'{measure} growth with available periods — {"; ".join(points)}. '
            'Missing periods or non-positive endpoints are not assigned a made-up rate.')


def margin_reading(operating: Any, net: Any, fcf: Any) -> list[str]:
    """Translate margins to money retained for each $100 of sales."""
    def describe(value: Any, name: str, qualifier: str) -> str:
        n = valid_number(value)
        if n is None:
            return f'**{name}:** N/A — there are not enough matching reported figures to calculate this margin.'
        outcome = ('earned' if n >= 0 else 'lost/used')
        return (f'**{name}:** For every $100 of sales, the company {outcome} '
                f'about ${abs(n):.2f} {qualifier}.')
    return [
        describe(operating, 'Operating margin', 'from operations before interest and taxes'),
        describe(net, 'Net income margin', 'in accounting profit after all reported expenses and taxes'),
        describe(fcf, 'Free cash flow margin', 'in free cash flow after capital spending'),
    ]


def valuation_reading(name: str, current: Any, median: Any, zone: str,
                      method: str, observations: int) -> list[str]:
    """Interpret multiples as historical context, not intrinsic value."""
    n, m = valid_number(current), valid_number(median)
    if n is None or m is None or n <= 0 or m <= 0:
        return [f'{name} cannot be explained numerically because the necessary multiple or median is unavailable.']
    denominator = {
        'P/OCF': 'operating cash flow',
        'P/E': 'earnings',
        'P/FCF': 'free cash flow',
    }.get(name, 'the financial measure')
    relative = (n/m-1)*100
    position = ('above' if relative > 0 else ('below' if relative < 0 else 'in line with'))
    relative_text = (f'{abs(relative):.1f}% {position}' if relative != 0 else 'in line with')
    if relative == 0:
        relative_text = 'in line with'
    first = (f'**{name} {n:.1f}×:** Investors are paying approximately ${n:.2f} in market value '
             f'for each $1 of {denominator} in the reported period used by this model. '
             f'The observed multiple is {relative_text} its {m:.1f}× median '
             f'across {observations} available month-end readings.')
    if method in ('filed_annual', 'annual'):
        method_text = ('The denominator is from the most recently FILED annual report, '
                       'not rolling 12-month results; the stock price changes monthly while '
                       'the denominator updates only after annual filings.')
    else:
        method_text = ('The denominator is based on SEC-filed trailing four-quarter results, '
                       'which update only when quarterly or annual filings become public.')
    second = (f'**Reading the zone ({zone}):** It compares this multiple with the company’s '
              'own historical range, not with fair value or a guaranteed buying opportunity. '
              'A low multiple could signal weaker business prospects, and a high one could reflect '
              'higher growth expectations. ' + method_text)
    return [first, second]


def verification_reading(audit: Any) -> str:
    """State only what the source comparison establishes."""
    if audit is None or getattr(audit, 'checked_years', 0) == 0:
        return ('The annual revenue figures do not have an automated second-source comparison. '
                'That means **unverified**, not necessarily incorrect; confirm important figures in the 10-K.')
    verified = len(getattr(audit, 'verified_years', []))
    unverified = len(getattr(audit, 'unverified_years', []))
    flagged = len(getattr(audit, 'hidden_years', []))
    return (f'**What the source checks mean:** {verified} fiscal years cross-checked, '
            f'{unverified} lack a matching comparison, and {flagged} have withheld discrepancies. '
            'Cross-checked means two feeds agreed within the app’s tolerance, '
            '**not** that the numbers were independently audited.')


GLOSSARY = [
    ('Revenue', 'The money a company brings in from selling its products or services, before expenses.'),
    ('Operating cash flow (OCF)', 'Cash produced or consumed by normal business operations; it excludes capital spending.'),
    ('Free cash flow (FCF)', 'Operating cash flow minus capital expenditures, when the reported figures are available.'),
    ('Operating profit', 'Profit from running the business before interest and taxes; may differ from net income.'),
    ('Net income', 'Accounting profit remaining after operating costs, interest, taxes, and other reported items.'),
    ('Margin', 'The portion of revenue left as a particular type of profit or cash flow, often described per $100 of sales.'),
    ('CAGR', 'Compound annual growth rate: the smoothed annual rate between two valid dates; individual years can differ.'),
    ('P/E', 'Market value divided by annual earnings. A lower ratio is not automatically a better investment.'),
    ('P/OCF', 'Market value divided by annual operating cash flow, using shares and market prices from the app model.'),
    ('P/FCF', 'Market value divided by annual free cash flow; very small positive FCF can create an extreme multiple.'),
    ('Historical median', 'Middle observation over the selected available time window—not an estimate of fair value.'),
    ('TTM', 'Trailing twelve months: financial results from the four most recently filed fiscal quarters.'),
    ('N/A', 'Not available or not meaningful with the source figures. It never automatically means zero.'),
]
