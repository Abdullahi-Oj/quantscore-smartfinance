import calendar
import pandas as pd
import numpy as np


class FinanceAnalytics:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.revenue_df = df[df['Type'] == 'Revenue']
        self.expense_df = df[df['Type'] == 'Expense']
        self._data_end_date = df['Date'].max()
        self._latest_month = df['Month'].max()

    def total_revenue(self) -> float:
        return self.revenue_df['Amount'].sum()

    def total_expenses(self) -> float:
        return self.expense_df['Amount'].sum()

    def net_profit(self) -> float:
        return self.total_revenue() - self.total_expenses()

    def profit_margin(self) -> float:
        rev = self.total_revenue()
        if rev == 0:
            return 0.0
        return (self.net_profit() / rev) * 100

    def is_month_complete(self, month=None) -> bool:
        """Return True if data covers the full calendar month."""
        if month is None:
            month = self._latest_month
        year, mon = month.year, month.month
        last_day = calendar.monthrange(year, mon)[1]
        month_end = pd.Timestamp(year=year, month=mon, day=last_day)
        return self._data_end_date >= month_end

    def partial_month_info(self) -> dict | None:
        """Return metadata when the latest month is incomplete, else None."""
        if self.is_month_complete():
            return None

        year, mon = self._latest_month.year, self._latest_month.month
        days_in_month = calendar.monthrange(year, mon)[1]
        day_of_month = self._data_end_date.day

        current = self.df[self.df['Month'] == self._latest_month]
        cur_rev = current[current['Type'] == 'Revenue']['Amount'].sum()
        cur_exp = current[current['Type'] == 'Expense']['Amount'].sum()

        projected_rev = cur_rev / day_of_month * days_in_month if day_of_month else 0
        projected_exp = cur_exp / day_of_month * days_in_month if day_of_month else 0

        return {
            'month': self._latest_month.strftime('%B %Y'),
            'month_label': self._latest_month.strftime('%b %Y'),
            'data_through': self._data_end_date.strftime('%d %B %Y'),
            'day_of_month': day_of_month,
            'days_in_month': days_in_month,
            'revenue': cur_rev,
            'expenses': cur_exp,
            'profit': cur_rev - cur_exp,
            'projected_revenue': projected_rev,
            'projected_expenses': projected_exp,
            'projected_profit': projected_rev - projected_exp,
        }

    def complete_months_summary(self) -> pd.DataFrame:
        """Monthly summary excluding the current partial month."""
        summary = self.monthly_summary()
        if self.partial_month_info() is not None:
            return summary[summary['Month'] != self._latest_month]
        return summary

    def monthly_summary(self) -> pd.DataFrame:
        monthly = self.df.groupby(['Month', 'MonthLabel', 'Type'])['Amount'].sum().unstack(fill_value=0)
        monthly.columns.name = None
        if 'Revenue' not in monthly.columns:
            monthly['Revenue'] = 0
        if 'Expense' not in monthly.columns:
            monthly['Expense'] = 0
        monthly['Profit'] = monthly['Revenue'] - monthly['Expense']
        monthly['Margin'] = (monthly['Profit'] / monthly['Revenue'].replace(0, np.nan) * 100).fillna(0)
        monthly = monthly.reset_index()
        monthly['MonthLabel'] = monthly['Month'].dt.strftime('%b %Y')
        monthly['IsComplete'] = monthly['Month'].apply(self.is_month_complete)
        return monthly.sort_values('Month')

    def monthly_growth(self) -> pd.DataFrame:
        summary = self.monthly_summary()
        summary['Revenue_Growth'] = summary['Revenue'].pct_change() * 100
        summary['Expense_Growth'] = summary['Expense'].pct_change() * 100
        summary['Profit_Growth'] = summary['Profit'].pct_change() * 100
        return summary

    def expense_by_category(self) -> pd.DataFrame:
        return (
            self.expense_df.groupby('Category')['Amount']
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )

    def revenue_by_category(self) -> pd.DataFrame:
        return (
            self.revenue_df.groupby('Category')['Amount']
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )

    def expense_by_category_monthly(self, category: str) -> pd.DataFrame:
        cat_df = self.expense_df[self.expense_df['Category'] == category]
        return (
            cat_df.groupby('Month')['Amount']
            .sum()
            .reset_index()
            .sort_values('Month')
        )

    def current_month_kpis(self) -> dict:
        latest_month = self._latest_month
        current = self.df[self.df['Month'] == latest_month]
        prev_month = latest_month - 1
        previous = self.df[self.df['Month'] == prev_month]

        cur_rev = current[current['Type'] == 'Revenue']['Amount'].sum()
        cur_exp = current[current['Type'] == 'Expense']['Amount'].sum()
        prev_rev = previous[previous['Type'] == 'Revenue']['Amount'].sum()
        prev_exp = previous[previous['Type'] == 'Expense']['Amount'].sum()

        partial = self.partial_month_info()
        rev_growth = ((cur_rev - prev_rev) / prev_rev * 100) if prev_rev else 0
        exp_growth = ((cur_exp - prev_exp) / prev_exp * 100) if prev_exp else 0

        return {
            'month': latest_month.strftime('%B %Y'),
            'revenue': cur_rev,
            'expenses': cur_exp,
            'profit': cur_rev - cur_exp,
            'margin': (cur_rev - cur_exp) / cur_rev * 100 if cur_rev else 0,
            'revenue_growth': rev_growth,
            'expense_growth': exp_growth,
            'is_partial': partial is not None,
            'partial_info': partial,
        }

    def latest_complete_month_comparison(self) -> dict | None:
        """MoM comparison using the two most recent complete months."""
        complete = self.complete_months_summary()
        if len(complete) < 2:
            return None

        prev, curr = complete.iloc[-2], complete.iloc[-1]
        rev_growth = ((curr['Revenue'] - prev['Revenue']) / prev['Revenue'] * 100) if prev['Revenue'] else 0
        exp_change = ((curr['Expense'] - prev['Expense']) / prev['Expense'] * 100) if prev['Expense'] else 0
        profit_growth = ((curr['Profit'] - prev['Profit']) / abs(prev['Profit']) * 100) if prev['Profit'] else 0

        return {
            'current_month': curr['MonthLabel'],
            'previous_month': prev['MonthLabel'],
            'revenue_growth': rev_growth,
            'expense_change': exp_change,
            'profit_growth': profit_growth,
            'current_revenue': curr['Revenue'],
            'current_profit': curr['Profit'],
            'current_expense': curr['Expense'],
        }

    def revenue_trend_insight(self) -> dict:
        """Smart revenue trend that accounts for partial months."""
        partial = self.partial_month_info()
        complete = self.complete_months_summary()

        if partial:
            return {
                'type': 'partial_month',
                'severity': 'warning',
                'message': (
                    f"{partial['month']} data is incomplete. Revenue currently stands at "
                    f"₦{partial['revenue']:,.0f} as of {partial['data_through']}. "
                    f"A full month comparison is not yet available."
                ),
                'detail': (
                    f"Projected full-month revenue: ~₦{partial['projected_revenue']:,.0f} "
                    f"({partial['day_of_month']}/{partial['days_in_month']} days recorded)."
                ),
            }

        if len(complete) < 2:
            return {
                'type': 'insufficient_data',
                'severity': 'info',
                'message': 'Not enough data to determine revenue trend.',
                'detail': None,
            }

        last_two = complete.tail(2)['Revenue'].values
        growing = last_two[1] > last_two[0]
        pct = abs((last_two[1] - last_two[0]) / last_two[0] * 100) if last_two[0] else 0
        months = complete.tail(2)['MonthLabel'].tolist()

        if growing:
            return {
                'type': 'growing',
                'severity': 'success',
                'message': f"Revenue is growing month over month (+{pct:.1f}%).",
                'detail': f"{months[1]} vs {months[0]}",
            }
        return {
            'type': 'declining',
            'severity': 'danger',
            'message': f"Revenue is declining month over month (-{pct:.1f}%).",
            'detail': f"{months[1]} vs {months[0]}",
        }

    def is_revenue_growing(self) -> bool:
        """Legacy method — uses complete months only."""
        complete = self.complete_months_summary()
        if len(complete) < 2:
            return False
        last_two = complete.tail(2)['Revenue'].values
        return last_two[1] > last_two[0]

    def staff_cost_ratio(self) -> dict | None:
        """Staff cost as a percentage of total revenue."""
        staff_categories = ['Staff', 'Salaries', 'Payroll', 'Staff Salaries', 'Wages']
        exp_cat = self.expense_by_category()
        staff_row = exp_cat[exp_cat['Category'].isin(staff_categories)]
        if staff_row.empty:
            staff_row = exp_cat[exp_cat['Category'].str.contains('staff|salary|payroll|wage', case=False, na=False)]
        if staff_row.empty:
            return None

        staff_total = staff_row['Amount'].sum()
        staff_cat = staff_row.iloc[0]['Category']
        total_rev = self.total_revenue()
        total_exp = self.total_expenses()
        ratio = (staff_total / total_rev * 100) if total_rev else 0
        pct_of_expenses = (staff_total / total_exp * 100) if total_exp else 0

        return {
            'category': staff_cat,
            'amount': staff_total,
            'revenue_ratio': ratio,
            'expense_pct': pct_of_expenses,
        }

    def category_cost_trend(self, category: str) -> dict | None:
        """Detect cost trend for a category across first and last complete months."""
        monthly = self.expense_by_category_monthly(category)
        if monthly.empty:
            return None

        if not self.is_month_complete(monthly['Month'].iloc[-1]):
            monthly = monthly[monthly['Month'] != monthly['Month'].iloc[-1]]
        if len(monthly) < 2:
            return None

        first_amt = monthly.iloc[0]['Amount']
        last_amt = monthly.iloc[-1]['Amount']
        if first_amt == 0:
            return None

        pct_change = (last_amt - first_amt) / first_amt * 100
        return {
            'category': category,
            'first_month': monthly.iloc[0]['Month'].strftime('%b %Y'),
            'last_month': monthly.iloc[-1]['Month'].strftime('%b %Y'),
            'first_amount': first_amt,
            'last_amount': last_amt,
            'pct_change': pct_change,
        }

    def revenue_concentration(self) -> dict | None:
        """Top revenue source concentration risk."""
        rev_cat = self.revenue_by_category()
        if rev_cat.empty:
            return None

        total = rev_cat['Amount'].sum()
        top = rev_cat.iloc[0]
        pct = top['Amount'] / total * 100 if total else 0

        return {
            'top_category': top['Category'],
            'top_amount': top['Amount'],
            'top_pct': pct,
            'is_concentrated': pct >= 70,
        }

    def top_expenses(self, n=5) -> pd.DataFrame:
        return self.expense_by_category().head(n)

    def best_revenue_month(self) -> dict | None:
        """The month with the highest recorded revenue (may be a partial month)."""
        summary = self.monthly_summary()
        if summary.empty or summary['Revenue'].sum() == 0:
            return None
        row = summary.loc[summary['Revenue'].idxmax()]
        return {
            'month': row['Month'],
            'month_label': row['MonthLabel'],
            'revenue': row['Revenue'],
            'is_complete': bool(row['IsComplete']),
        }

    def resolve_month(self, text: str) -> pd.Period | None:
        """Resolve a month name or abbreviation from free text."""
        import re
        months_map = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
            'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
            'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
            'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12,
        }
        text_lower = text.lower()
        for name, num in months_map.items():
            if re.search(rf'\b{name}\b', text_lower):
                year = self._latest_month.year
                if num > self._latest_month.month:
                    year -= 1
                return pd.Period(year=year, month=num, freq='M')
        return None

    def month_row(self, month: pd.Period) -> dict | None:
        """Get revenue, expense, profit for a specific month."""
        summary = self.monthly_summary()
        row = summary[summary['Month'] == month]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            'month': month,
            'month_label': r['MonthLabel'],
            'revenue': r['Revenue'],
            'expense': r['Expense'],
            'profit': r['Profit'],
            'margin': r['Margin'],
            'is_complete': bool(r['IsComplete']),
        }

    def profit_change_analysis(self, month_text: str) -> dict | None:
        """Explain profit change for a month vs the previous month."""
        month = self.resolve_month(month_text)
        if month is None:
            return None

        curr = self.month_row(month)
        if curr is None:
            return None

        prev_month = month - 1
        prev = self.month_row(prev_month)
        if prev is None:
            return {'month_label': curr['month_label'], 'current': curr, 'previous': None}

        profit_change = curr['profit'] - prev['profit']
        profit_pct = (profit_change / abs(prev['profit']) * 100) if prev['profit'] else 0

        curr_exp = self.expense_df[self.expense_df['Month'] == month].groupby('Category')['Amount'].sum()
        prev_exp = self.expense_df[self.expense_df['Month'] == prev_month].groupby('Category')['Amount'].sum()
        all_cats = curr_exp.index.union(prev_exp.index)
        changes = []
        for cat in all_cats:
            c_amt = curr_exp.get(cat, 0)
            p_amt = prev_exp.get(cat, 0)
            diff = c_amt - p_amt
            if diff != 0:
                changes.append({'category': cat, 'current': c_amt, 'previous': p_amt, 'change': diff})
        changes.sort(key=lambda x: abs(x['change']), reverse=True)

        return {
            'month_label': curr['month_label'],
            'previous_label': prev['month_label'],
            'current': curr,
            'previous': prev,
            'profit_change': profit_change,
            'profit_pct': profit_pct,
            'expense_changes': changes[:5],
            'revenue_change': curr['revenue'] - prev['revenue'],
        }

    def fastest_growing_expenses(self, n: int = 3) -> list[dict]:
        """Categories with the largest % increase from first to last complete month."""
        complete = self.complete_months_summary()
        if len(complete) < 2:
            return []

        first_m, last_m = complete.iloc[0]['Month'], complete.iloc[-1]['Month']
        first_exp = self.expense_df[self.expense_df['Month'] == first_m].groupby('Category')['Amount'].sum()
        last_exp = self.expense_df[self.expense_df['Month'] == last_m].groupby('Category')['Amount'].sum()

        trends = []
        for cat in first_exp.index.union(last_exp.index):
            f_amt = first_exp.get(cat, 0)
            l_amt = last_exp.get(cat, 0)
            if f_amt > 0 and l_amt > f_amt:
                pct = (l_amt - f_amt) / f_amt * 100
                trends.append({
                    'category': cat,
                    'first_amount': f_amt,
                    'last_amount': l_amt,
                    'pct_change': pct,
                    'first_month': first_m.strftime('%b %Y'),
                    'last_month': last_m.strftime('%b %Y'),
                })
        trends.sort(key=lambda x: x['pct_change'], reverse=True)
        return trends[:n]

