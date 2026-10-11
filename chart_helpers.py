"""Separate-scale performance chart for Stock Research Lab v1.4.2.

Two vertically stacked plots are preferable to a dual-axis chart: it is
possible to read both billions-scale cash flows and much larger revenues
without suggesting that their magnitudes share the same vertical scale.
"""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from data_quality import fiscal_year


def revenue_cash_flow_figure(frame: pd.DataFrame) -> go.Figure:
    fy = frame['date'].map(lambda d: f'FY{fiscal_year(d)}')
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[.52, .48], vertical_spacing=.17,
                        subplot_titles=('Annual revenue', 'Annual operating cash flow'))
    fig.add_trace(go.Scatter(x=fy, y=frame['revenue']/1e9,
                             name='Revenue', mode='lines+markers', connectgaps=False,
                             line=dict(color='#9bdfc4', width=3),
                             marker=dict(size=7),
                             hovertemplate='%{x}<br>Revenue: $%{y:,.2f}B<extra></extra>'),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=fy, y=frame['ocf']/1e9,
                             name='Operating cash flow', mode='lines+markers', connectgaps=False,
                             line=dict(color='#f4c77c', width=3),
                             marker=dict(size=7),
                             hovertemplate='%{x}<br>Operating cash flow: $%{y:,.2f}B<extra></extra>'),
                  row=2, col=1)
    for row in (1, 2):
        fig.update_yaxes(title_text='USD billions', zeroline=True, rangemode='tozero',
                         tickfont=dict(color='#e5eeff', size=12),
                         title_font=dict(color='#f6f9ff'),
                         gridcolor='#475674', zerolinecolor='#536681', row=row, col=1)
    fig.update_xaxes(type='category', categoryorder='array', categoryarray=list(fy),
                     tickfont=dict(color='#e5eeff', size=12), showgrid=False, row=2, col=1)
    fig.update_layout(hovermode='x', showlegend=True)
    for annotation in fig.layout.annotations:
        annotation.update(font=dict(color='#f6f9ff', size=15))
    return fig
