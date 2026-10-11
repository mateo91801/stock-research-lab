"""Presentation-only valuation chart helpers for Stock Research Lab v1.4.3.

Outlier-aware *display* never changes the observations used for valuation metrics,
median or percentile bands. Focusing the y-axis is not a data-cleaning operation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go


@dataclass(frozen=True)
class MultipleViewport:
    focused_ceiling: float
    full_ceiling: float
    has_outlier_focus: bool
    clipped_count: int
    total_count: int
    highest_multiple: float


def valuation_viewport(values: pd.Series, low: float, high: float, median: float) -> MultipleViewport:
    """Suggest an uncluttered y range when a few high observations compress the chart.

    All statistics are calculated outside this helper using the original full series.
    The focused ceiling is based on a robust upper quartile/median and *does not*
    change the data or relative valuation zones.
    """
    series = pd.to_numeric(values, errors='coerce').replace([np.inf, -np.inf], np.nan).dropna()
    series = series.loc[series > 0]
    if series.empty:
        raise ValueError('Expected at least one positive valuation multiple.')
    largest = float(series.max())
    typical_top = max(5.0, 1.45*float(high), 1.7*float(median))
    full_top = max(1.13*largest, 1.2*float(high), 1.0)
    higher = int((series > typical_top).sum())
    # Only offer the focus if large spikes make normal observations hard to read,
    # and fewer than 25% of observations would appear as out-of-range markers.
    allow_focus = (len(series) >= 24 and higher > 0 and
                   higher / len(series) <= 0.25 and full_top > 1.65*typical_top)
    return MultipleViewport(
        focused_ceiling=round(typical_top, 2) if allow_focus else round(full_top, 2),
        full_ceiling=round(full_top, 2),
        has_outlier_focus=bool(allow_focus),
        clipped_count=higher if allow_focus else 0,
        total_count=len(series),
        highest_multiple=largest,
    )


def multiple_figure(history: pd.DataFrame, metric_label: str, method: str,
                    limits: dict, y_ceiling: float, focused: bool) -> tuple[go.Figure, int]:
    """Build a chart with explicit clipped-point markers in focused mode.

    Traces over the focused cap are broken instead of falsifying them by
    connecting lines through the cap. Their actual values remain in hover labels.
    """
    dates = pd.to_datetime(history['date'])
    actual = pd.to_numeric(history['multiple'], errors='coerce')
    exceed = actual > y_ceiling if focused else pd.Series(False, index=history.index)
    shown = actual.mask(exceed)
    fig = go.Figure()
    y_low = float(limits['low'])
    y_high = float(limits['high'])
    median = float(limits['median'])
    fig.add_hrect(y0=0, y1=min(y_low, y_ceiling),
                  fillcolor='rgba(74,171,112,.26)', line_width=0)
    if y_ceiling > y_low:
        fig.add_hrect(y0=y_low, y1=min(y_high,y_ceiling),
                      fillcolor='rgba(241,190,90,.22)', line_width=0)
    if y_ceiling > y_high:
        fig.add_hrect(y0=y_high, y1=y_ceiling,
                      fillcolor='rgba(225,91,112,.22)', line_width=0)
    fig.add_trace(go.Scatter(
        x=dates, y=shown, mode='lines', connectgaps=False,
        name=f'{metric_label} ({method})',
        line=dict(color='#f5fbff',width=2.7),
        hovertemplate=f'%{{x|%b %Y}}<br>{metric_label}: %{{y:.1f}}×<extra></extra>',
    ))
    outliers = int(exceed.sum())
    if outliers:
        fig.add_trace(go.Scatter(
            x=dates.loc[exceed], y=[y_ceiling*0.974]*outliers,
            customdata=actual.loc[exceed], mode='markers',
            marker=dict(symbol='triangle-up',size=11,color='#ffc877',line=dict(color='#ffffff',width=1)),
            name='Above visible range',
            hovertemplate=f'%{{x|%b %Y}}<br>Actual {metric_label}: %{{customdata:.1f}}×<br>Above chart limit<extra></extra>',
        ))
    fig.add_hline(y=median, line_dash='dot',line_color='#f5d77e',
                  annotation_text=f'Median {median:.1f}×',
                  annotation_position='top right')
    fig.update_yaxes(title_text=metric_label,range=[0,y_ceiling],ticksuffix='×')
    return fig, outliers
