from analytics import FinanceAnalytics


def business_health_score(analytics: FinanceAnalytics, shortage: dict) -> dict:
    """Composite health score (0–100) from five financial dimensions."""
    scores = {}

    margin = analytics.profit_margin()
    scores['profit_margin'] = min(100, max(0, margin * 2.5))  # 40% margin → 100

    complete = analytics.complete_months_summary()
    if len(complete) >= 2:
        rev_vals = complete.tail(3)['Revenue'].values
        if len(rev_vals) >= 2 and rev_vals[0] > 0:
            growth = (rev_vals[-1] - rev_vals[0]) / rev_vals[0] * 100
            scores['revenue_growth'] = min(100, max(0, 50 + growth))
        else:
            scores['revenue_growth'] = 50
    else:
        scores['revenue_growth'] = 50

    if len(complete) >= 2:
        exp_vals = complete.tail(3)['Expense'].values
        if len(exp_vals) >= 2 and exp_vals[0] > 0:
            exp_growth = (exp_vals[-1] - exp_vals[0]) / exp_vals[0] * 100
            scores['expense_control'] = min(100, max(0, 100 - exp_growth))
        else:
            scores['expense_control'] = 70
    else:
        scores['expense_control'] = 70

    runway = shortage['months_runway']
    if runway >= 12:
        scores['cash_runway'] = 100
    elif runway >= 6:
        scores['cash_runway'] = 80
    elif runway >= 3:
        scores['cash_runway'] = 60
    elif runway >= 2:
        scores['cash_runway'] = 40
    else:
        scores['cash_runway'] = 20

    concentration = analytics.revenue_concentration()
    if concentration:
        top_pct = concentration['top_pct']
        scores['diversification'] = min(100, max(0, 100 - (top_pct - 50) * 2)) if top_pct > 50 else 100
    else:
        scores['diversification'] = 50

    weights = {
        'profit_margin': 0.25,
        'revenue_growth': 0.20,
        'expense_control': 0.20,
        'cash_runway': 0.20,
        'diversification': 0.15,
    }
    total = sum(scores[k] * weights[k] for k in weights)

    if total >= 80:
        label, color = 'Healthy Business', '#2ecc71'
    elif total >= 60:
        label, color = 'Stable — Monitor Closely', '#f39c12'
    elif total >= 40:
        label, color = 'At Risk', '#e67e22'
    else:
        label, color = 'Critical — Action Needed', '#e74c3c'

    return {
        'score': round(total),
        'label': label,
        'color': color,
        'breakdown': scores,
    }


def generate_recommendations(analytics: FinanceAnalytics, shortage: dict) -> list[dict]:
    """Rule-based financial advisor recommendations."""
    recs = []

    concentration = analytics.revenue_concentration()
    if concentration and concentration['is_concentrated']:
        recs.append({
            'icon': '⚠️',
            'title': 'Revenue concentration risk',
            'text': (
                f"{concentration['top_pct']:.0f}% of revenue comes from "
                f"{concentration['top_category']}. Consider growing other income "
                f"streams to reduce dependence on one source."
            ),
            'action': f"Develop a second revenue stream alongside {concentration['top_category']}.",
            'priority': 'high',
        })

    staff = analytics.staff_cost_ratio()
    if staff:
        recs.append({
            'icon': '👥',
            'title': 'Payroll is your largest expense driver',
            'text': (
                f"{staff['category']} accounts for {staff['expense_pct']:.1f}% of total "
                f"expenses (₦{staff['amount']:,.0f}). "
                f"₦{staff['revenue_ratio']:.1f} out of every ₦100 earned goes to salaries. "
                f"Monitor staff productivity as revenue scales."
            ),
            'action': "Keep payroll growth at or below revenue growth.",
            'priority': 'high',
        })

        trend = analytics.category_cost_trend(staff['category'])
        if trend and abs(trend['pct_change']) >= 5:
            direction = 'increased' if trend['pct_change'] > 0 else 'decreased'
            recs.append({
                'icon': '📈' if trend['pct_change'] > 0 else '📉',
                'title': f"{staff['category']} has {direction}",
                'text': (
                    f"{staff['category']} {direction} by {abs(trend['pct_change']):.1f}% "
                    f"from {trend['first_month']} (₦{trend['first_amount']:,.0f}) to "
                    f"{trend['last_month']} (₦{trend['last_amount']:,.0f}). "
                    f"{'Ensure revenue growth continues to justify payroll expansion.' if trend['pct_change'] > 0 else 'Good cost control on payroll.'}"
                ),
                'action': (
                    "Confirm revenue growth is matching payroll growth before adding headcount."
                    if trend['pct_change'] > 0 else
                    "Maintain current payroll discipline."
                ),
                'priority': 'medium',
            })

    comparison = analytics.latest_complete_month_comparison()
    if comparison and comparison['profit_growth'] < -20:
        recs.append({
            'icon': '📉',
            'title': f"Profitability dropped in {comparison['current_month']}",
            'text': (
                f"Net profit fell {abs(comparison['profit_growth']):.1f}% vs "
                f"{comparison['previous_month']}. Review large one-off expenses "
                f"or capital expenditure in that period."
            ),
            'action': f"Review large or one-off expenses in {comparison['current_month']} before adjusting budgets.",
            'priority': 'medium',
        })

    marketing_trend = analytics.category_cost_trend('Marketing')
    if marketing_trend and marketing_trend['pct_change'] >= 30:
        recs.append({
            'icon': '📣',
            'title': 'Marketing spend is rising fast',
            'text': (
                f"Marketing increased {marketing_trend['pct_change']:.1f}% from "
                f"{marketing_trend['first_month']} to {marketing_trend['last_month']}. "
                f"Measure return on advertising spend to ensure campaigns are paying off."
            ),
            'action': "Track marketing ROI monthly to confirm campaigns are paying off.",
            'priority': 'medium',
        })

    partial = analytics.partial_month_info()
    if partial:
        recs.append({
            'icon': '📅',
            'title': f"{partial['month']} data is incomplete",
            'text': (
                f"Data recorded through {partial['data_through']} "
                f"({partial['day_of_month']}/{partial['days_in_month']} days). "
                f"Month-over-month comparisons may be misleading until the month closes."
            ),
            'action': f"Complete {partial['month']}'s transaction records before drawing trend conclusions.",
            'priority': 'low',
        })

    if shortage['alert']:
        recs.append({
            'icon': '🚨',
            'title': 'Cash runway is critically low',
            'text': (
                f"Estimated runway is only {shortage['months_runway']} months at current "
                f"spend levels. Prioritize cash preservation and revenue acceleration."
            ),
            'action': "Prioritize cash preservation and accelerate revenue collection immediately.",
            'priority': 'critical',
        })
    elif shortage['warning']:
        recs.append({
            'icon': '⚠️',
            'title': 'Monitor cash position',
            'text': (
                f"Cash runway of {shortage['months_runway']} months is manageable but "
                f"worth watching. Consider building a larger cash buffer."
            ),
            'action': "Build a larger cash buffer over the next few months.",
            'priority': 'medium',
        })

    margin = analytics.profit_margin()
    if margin > 20:
        recs.append({
            'icon': '✅',
            'title': 'Strong profit margins',
            'text': (
                f"Overall profit margin of {margin:.1f}% is healthy for an SME. "
                f"Maintain cost discipline while investing in growth."
            ),
            'action': "Maintain current cost discipline while reinvesting in growth.",
            'priority': 'low',
        })

    priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    recs.sort(key=lambda r: priority_order.get(r['priority'], 9))
    return recs