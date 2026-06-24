import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

COLORS = {
    'revenue': '#2ecc71',
    'expense': '#e74c3c',
    'profit': '#3498db',
    'forecast': '#f39c12',
    'bg': '#0f172a',
    'card': '#1e293b',
    'text': '#f1f5f9',
    'grid': '#334155',
}

LAYOUT_DEFAULTS = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(color=COLORS['text'], family='Inter, sans-serif'),
    margin=dict(t=40, b=40, l=40, r=20),
    legend=dict(bgcolor='rgba(0,0,0,0)', bordercolor='rgba(0,0,0,0)'),
)


def revenue_vs_expense_bar(summary: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=summary['MonthLabel'], y=summary['Revenue'],
        name='Revenue', marker_color=COLORS['revenue'], opacity=0.9,
    ))
    fig.add_trace(go.Bar(
        x=summary['MonthLabel'], y=summary['Expense'],
        name='Expense', marker_color=COLORS['expense'], opacity=0.9,
    ))
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title='Revenue vs Expenses by Month',
        barmode='group',
        xaxis=dict(gridcolor=COLORS['grid']),
        yaxis=dict(gridcolor=COLORS['grid'], tickprefix='₦', tickformat=',.0f'),
    )
    return fig


def profit_trend_line(summary: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=summary['MonthLabel'], y=summary['Profit'],
        mode='lines+markers',
        name='Net Profit',
        line=dict(color=COLORS['profit'], width=3),
        marker=dict(size=8),
        fill='tozeroy',
        fillcolor='rgba(52, 152, 219, 0.15)',
    ))
    fig.add_hline(y=0, line_dash='dash', line_color='rgba(255,255,255,0.3)')
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title='Net Profit Trend',
        xaxis=dict(gridcolor=COLORS['grid']),
        yaxis=dict(gridcolor=COLORS['grid'], tickprefix='₦', tickformat=',.0f'),
    )
    return fig


def expense_donut(expense_cat: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=expense_cat['Category'],
        values=expense_cat['Amount'],
        hole=0.55,
        marker=dict(colors=px.colors.qualitative.Set3),
        textinfo='label+percent',
        textfont_size=12,
    ))
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title='Expense Breakdown by Category',
        showlegend=True,
    )
    return fig


def cashflow_forecast_chart(forecast_df: pd.DataFrame) -> go.Figure:
    actual = forecast_df[forecast_df['Type'] == 'Actual']
    projected = forecast_df[forecast_df['Type'] == 'Forecast']

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=actual['MonthLabel'], y=actual['Revenue'],
        name='Actual Revenue', marker_color=COLORS['revenue'], opacity=0.8,
    ))
    fig.add_trace(go.Bar(
        x=actual['MonthLabel'], y=actual['Expense'],
        name='Actual Expense', marker_color=COLORS['expense'], opacity=0.8,
    ))
    fig.add_trace(go.Bar(
        x=projected['MonthLabel'], y=projected['Revenue'],
        name='Projected Revenue', marker_color=COLORS['revenue'],
        opacity=0.4, marker_pattern_shape='/',
    ))
    fig.add_trace(go.Bar(
        x=projected['MonthLabel'], y=projected['Expense'],
        name='Projected Expense', marker_color=COLORS['expense'],
        opacity=0.4, marker_pattern_shape='/',
    ))

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title='Cashflow Forecast (Actual + Projected)',
        barmode='group',
        xaxis=dict(gridcolor=COLORS['grid']),
        yaxis=dict(gridcolor=COLORS['grid'], tickprefix='₦', tickformat=',.0f'),
    )
    return fig


def monthly_growth_chart(summary: pd.DataFrame) -> go.Figure:
    summary = summary.copy().dropna(subset=['Revenue_Growth'])
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=summary['MonthLabel'], y=summary['Revenue_Growth'],
        name='Revenue Growth %',
        marker_color=[COLORS['revenue'] if v >= 0 else COLORS['expense'] for v in summary['Revenue_Growth']],
    ))
    fig.add_hline(y=0, line_color='rgba(255,255,255,0.3)', line_dash='dash')
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title='Month-over-Month Revenue Growth (%)',
        xaxis=dict(gridcolor=COLORS['grid']),
        yaxis=dict(gridcolor=COLORS['grid'], ticksuffix='%'),
    )
    return fig


def revenue_category_bar(revenue_cat: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=revenue_cat['Amount'],
        y=revenue_cat['Category'],
        orientation='h',
        marker_color=COLORS['revenue'],
        opacity=0.85,
    ))
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title='Revenue by Category',
        xaxis=dict(gridcolor=COLORS['grid'], tickprefix='₦', tickformat=',.0f'),
        yaxis=dict(gridcolor=COLORS['grid']),
    )
    return fig
