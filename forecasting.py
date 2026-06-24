import pandas as pd
import numpy as np
from analytics import FinanceAnalytics


def forecast_cashflow(df: pd.DataFrame, months_ahead: int = 3) -> pd.DataFrame:
    analytics = FinanceAnalytics(df)
    full_summary = analytics.monthly_summary()

    # Use only complete months for forecasting to avoid partial-month bias
    complete_summary = analytics.complete_months_summary()

    if len(complete_summary) < 2:
        return pd.DataFrame()

    revenues = complete_summary['Revenue'].values
    expenses = complete_summary['Expense'].values

    window = min(3, len(revenues) - 1)
    rev_diffs = np.diff(revenues[-window - 1:]) / revenues[-window - 1:-1]
    exp_diffs = np.diff(expenses[-window - 1:]) / expenses[-window - 1:-1]
    rev_growth = np.mean(rev_diffs)
    exp_growth = np.mean(exp_diffs)

    rev_growth = np.clip(rev_growth, -0.3, 0.5)
    exp_growth = np.clip(exp_growth, -0.2, 0.4)

    last_complete_month = complete_summary['Month'].iloc[-1]
    last_rev = revenues[-1]
    last_exp = expenses[-1]

    # Forecasting must start from the month AFTER the most recent month
    # actually present in the data (complete OR partial) — not from the
    # last *complete* month. Otherwise, if the current month is partial
    # (e.g. June, 21 of 30 days in), this would "forecast" June itself —
    # producing a second, conflicting Forecast row for a month that
    # already has real Actual data. The growth-rate compounding base
    # still anchors to the last complete month, since that's the reliable
    # figure; only the starting point for which months get forecasted
    # shifts forward past whatever's already on the books.
    last_present_month = full_summary['Month'].iloc[-1]

    forecast_rows = []
    for i in range(1, months_ahead + 1):
        future_month = last_present_month + i
        periods_from_base = future_month.ordinal - last_complete_month.ordinal
        projected_rev = last_rev * ((1 + rev_growth) ** periods_from_base)
        projected_exp = last_exp * ((1 + exp_growth) ** periods_from_base)
        projected_profit = projected_rev - projected_exp
        forecast_rows.append({
            'Month': future_month,
            'MonthLabel': future_month.strftime('%b %Y'),
            'Revenue': round(projected_rev),
            'Expense': round(projected_exp),
            'Profit': round(projected_profit),
            'Type': 'Forecast',
        })

    historical = full_summary[['Month', 'MonthLabel', 'Revenue', 'Expense', 'Profit']].copy()
    historical['Type'] = 'Actual'

    return pd.concat([historical, pd.DataFrame(forecast_rows)], ignore_index=True)


def cash_shortage_alert(df: pd.DataFrame, cash_balance: float = None) -> dict:
    analytics = FinanceAnalytics(df)
    # Use complete months for average expense to avoid partial-month skew
    summary = analytics.complete_months_summary()
    if summary.empty:
        summary = analytics.monthly_summary()

    if cash_balance is None:
        cash_balance = analytics.monthly_summary()['Profit'].sum()

    avg_monthly_expense = summary['Expense'].mean()
    months_of_runway = cash_balance / avg_monthly_expense if avg_monthly_expense > 0 else 999

    return {
        'estimated_balance': cash_balance,
        'avg_monthly_expense': avg_monthly_expense,
        'months_runway': round(months_of_runway, 1),
        'alert': months_of_runway < 2,
        'warning': 2 <= months_of_runway < 4,
        'excludes_partial_month': analytics.partial_month_info() is not None,
    }