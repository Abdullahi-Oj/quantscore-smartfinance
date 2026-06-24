import re
from analytics import FinanceAnalytics
from insights import business_health_score, generate_recommendations
from forecasting import forecast_cashflow, cash_shortage_alert


SUGGESTED_QUESTIONS = [
    "Why did profit drop in April?",
    "How can I improve my sales?",
    "What should I do to improve performance?",
    "Which expense is growing too fast?",
    "How many months can I survive?",
    "What should I do this month?",
    "How healthy is my business?",
    "Where does my revenue come from?",
    "What are my biggest expenses?",
    "How is revenue trending?",
]

# ── Fuzzy intent classification layer ───────────────────────────────────
# A maintainable, extensible safety net: instead of one-off regex per phrase,
# each intent has a small list of representative example questions. New
# phrasings can be supported just by adding a line here — no new regex.
# This only runs when the precise regex matchers above find no match, so it
# can't regress behavior that already works.

INTENT_EXAMPLES = {
    'sales_growth': [
        "improve my sales", "increase my sales", "grow my sales", "boost revenue",
        "sell more", "make more sales", "get more customers", "increase sales",
        "how do i sell more",
    ],
    'business_improvement': [
        "improve performance", "grow my business", "increase profit", "make more money",
        "what should i focus on", "make my business better", "grow my company",
        "what are my weaknesses", "how can i do better", "boost profit",
        "how can i do better overall",
    ],
    'action': [
        "what should i do this month", "give me recommendations", "what are my priorities",
        "what actions should i take", "any advice for me", "what should i focus on next month",
        "what do you recommend",
    ],
    'health': [
        "how healthy is my business", "what is my health score", "how am i doing overall",
        "is my business doing well", "rate my business", "how is my business doing",
    ],
    'revenue_source': [
        "where does my revenue come from", "what are my revenue sources",
        "how concentrated is my revenue", "am i too dependent on one revenue source",
        "revenue breakdown by category",
    ],
    'top_expense': [
        "what are my biggest expenses", "where is my money going", "top expense categories",
        "what am i spending the most on", "where am i wasting money",
    ],
    'revenue_trend': [
        "is my revenue growing", "is my revenue declining", "how is revenue trending",
        "sales trend over time", "is income going up or down",
    ],
    'forecast': [
        "what is my forecast", "predict next month revenue", "what should i expect next month",
        "project my cashflow", "what will my balance be soon",
    ],
    'margin': [
        "what is my profit margin", "how profitable am i", "are my margins good",
        "is my margin healthy",
    ],
    'staff': [
        "how much do i spend on staff", "payroll analysis", "salary costs breakdown",
        "is payroll too high",
    ],
    'compare': [
        "compare this month to last month", "how does this month compare",
        "month over month comparison",
    ],
    'summary': [
        "give me a business summary", "business overview", "snapshot of my finances",
        "tell me about my business", "give me the big picture",
    ],
}

# Maps each intent key above to the existing handler method that already
# knows how to answer it — the classifier only decides *which* handler to
# call, it doesn't replace the handlers themselves.
INTENT_HANDLER_NAMES = {
    'sales_growth': '_answer_sales_growth',
    'business_improvement': '_answer_business_improvement',
    'action': '_answer_actions',
    'health': '_answer_health',
    'revenue_source': '_answer_revenue_sources',
    'top_expense': '_answer_top_expenses',
    'revenue_trend': '_answer_revenue_trend',
    'forecast': '_answer_forecast',
    'margin': '_answer_margin',
    'staff': '_answer_staff',
    'compare': '_answer_compare',
    'summary': '_answer_summary',
}

# Confidence floor: below this, we'd rather show the honest fallback than
# guess wrong. Tuned by hand against the test phrasings in this file's tests.
INTENT_CONFIDENCE_THRESHOLD = 0.34

_STOPWORDS = {
    'i', 'my', 'me', 'is', 'are', 'do', 'does', 'did', 'what', 'how', 'can',
    'could', 'would', 'should', 'to', 'of', 'in', 'on', 'for', 'with', 'this',
    'that', 'it', 'will', 'a', 'an', 'the', 'you', 'your', 'be', 'am',
}


def _tokenize(text: str) -> set:
    words = re.findall(r'[a-z]+', text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _fmt(amount: float) -> str:
    return f"₦{amount:,.0f}"


class FinancialCopilot:
    def __init__(self, analytics: FinanceAnalytics, shortage: dict, health: dict, recommendations: list):
        self.a = analytics
        self.shortage = shortage
        self.health = health
        self.recommendations = recommendations

    def answer(self, question: str) -> str:
        q = question.strip().lower()
        if not q:
            return "Please ask me a question about your finances."

        handlers = [
            (self._is_profit_question, self._answer_profit),
            (self._is_expense_growth_question, self._answer_expense_growth),
            (self._is_runway_question, self._answer_runway),
            (self._is_sales_growth_question, self._answer_sales_growth),
            (self._is_business_improvement_question, self._answer_business_improvement),
            (self._is_action_question, self._answer_actions),
            (self._is_health_question, self._answer_health),
            (self._is_revenue_source_question, self._answer_revenue_sources),
            (self._is_top_expense_question, self._answer_top_expenses),
            (self._is_revenue_trend_question, self._answer_revenue_trend),
            (self._is_forecast_question, self._answer_forecast),
            (self._is_margin_question, self._answer_margin),
            (self._is_staff_question, self._answer_staff),
            (self._is_compare_question, self._answer_compare),
            (self._is_summary_question, self._answer_summary),
        ]

        for matcher, handler in handlers:
            if matcher(q):
                return handler(q)

        intent, score = self._classify_intent(q)
        if intent and score >= INTENT_CONFIDENCE_THRESHOLD:
            handler = getattr(self, INTENT_HANDLER_NAMES[intent])
            return handler(q)

        return self._answer_fallback(q)

    def _classify_intent(self, q: str):
        """Fuzzy backup classifier: scores the question against INTENT_EXAMPLES
        using word-overlap (Jaccard) similarity. Only consulted when none of the
        precise regex matchers above fire, so it's purely additive."""
        q_tokens = _tokenize(q)
        if not q_tokens:
            return None, 0.0

        best_intent, best_score = None, 0.0
        for intent, phrases in INTENT_EXAMPLES.items():
            for phrase in phrases:
                score = _jaccard(q_tokens, _tokenize(phrase))
                if score > best_score:
                    best_score, best_intent = score, intent

        return best_intent, best_score

    # ── Intent matchers ──────────────────────────────────────────────────

    def _is_profit_question(self, q: str) -> bool:
        return bool(re.search(r'profit|margin|loss|losing|earn', q)) and bool(
            re.search(r'why|drop|fell|decline|decrease|lower|down|explain', q)
            or self.a.resolve_month(q)
        )

    def _is_expense_growth_question(self, q: str) -> bool:
        return bool(re.search(
            r'growing|grow|increase|rising|rise|fast|trend|spending more|cost.*up',
            q,
        )) and bool(re.search(r'expense|cost|spend|payroll|staff|marketing|rent', q))

    def _is_runway_question(self, q: str) -> bool:
        return bool(re.search(
            r'runway|survive|survival|how long|how many month|cash last|run out|cash position',
            q,
        ))

    def _is_sales_growth_question(self, q: str) -> bool:
        return bool(re.search(
            r'(improve|increase|boost|grow|raise|drive up).{0,20}(sales|revenue|income)'
            r'|sell more|make more sales|more customers',
            q,
        )) and not bool(re.search(r'revenue come|income come|concentrat|diversif', q))

    def _is_business_improvement_question(self, q: str) -> bool:
        return bool(re.search(
            r'improve (my )?(business|performance|company|profit)'
            r'|increase profit|boost profit'
            r'|grow (my )?(business|company)'
            r'|make.*business better'
            r'|what should i improve'
            r'|what are my weakness'
            r'|do better overall'
            r'|business better',
            q,
        ))

    def _is_action_question(self, q: str) -> bool:
        return bool(re.search(
            r'what should|recommend|advice|suggest|do this month|priorit|action|focus on',
            q,
        ))

    def _is_health_question(self, q: str) -> bool:
        return bool(re.search(r'health|score|healthy|how am i doing|overall|business doing', q))

    def _is_revenue_source_question(self, q: str) -> bool:
        return bool(re.search(r'revenue come|income come|revenue source|where.*revenue|sales vs|diversif|concentrat', q))

    def _is_top_expense_question(self, q: str) -> bool:
        return bool(re.search(r'biggest expense|top expense|largest cost|where.*money go|spending most', q))

    def _is_revenue_trend_question(self, q: str) -> bool:
        return bool(re.search(r'revenue trend|revenue grow|revenue declin|sales trend|income trend', q))

    def _is_forecast_question(self, q: str) -> bool:
        return bool(re.search(r'forecast|project|predict|next month|future|expect', q))

    def _is_margin_question(self, q: str) -> bool:
        return bool(re.search(r'profit margin|margin|profitability', q)) and not self._is_profit_question(q)

    def _is_staff_question(self, q: str) -> bool:
        return bool(re.search(r'staff|salary|salaries|payroll|wage', q))

    def _is_compare_question(self, q: str) -> bool:
        return bool(re.search(r'compare|vs|versus|difference between', q))

    def _is_summary_question(self, q: str) -> bool:
        return bool(re.search(r'summary|overview|tell me about|how is my business|snapshot', q))

    # ── Answer handlers ──────────────────────────────────────────────────

    def _answer_profit(self, q: str) -> str:
        month = self.a.resolve_month(q)
        if month is None:
            comparison = self.a.latest_complete_month_comparison()
            if comparison and comparison['profit_growth'] < 0:
                month_text = comparison['current_month']
                analysis = self.a.profit_change_analysis(month_text)
            else:
                return (
                    "I can explain profit changes for a specific month. "
                    "Try asking: **\"Why did profit drop in April?\"**"
                )
        else:
            analysis = self.a.profit_change_analysis(q)

        if analysis is None:
            return "I couldn't find data for that month. Check the month name and try again."

        if analysis.get('previous') is None:
            return f"I only have data for **{analysis['month_label']}** with no prior month to compare."

        curr, prev = analysis['current'], analysis['previous']
        change = analysis['profit_change']
        direction = 'dropped' if change < 0 else 'increased'

        lines = [
            f"### Profit {direction} in {analysis['month_label']}",
            "",
            f"**{analysis['month_label']}** profit: **{_fmt(curr['profit'])}** (margin {curr['margin']:.1f}%)",
            f"**{analysis['previous_label']}** profit: **{_fmt(prev['profit'])}** (margin {prev['margin']:.1f}%)",
            f"Change: **{_fmt(abs(change))}** ({analysis['profit_pct']:+.1f}%)",
            "",
        ]

        if not curr['is_complete']:
            lines.append(
                f"⚠️ Note: {analysis['month_label']} data may be incomplete — "
                f"comparisons should be interpreted cautiously."
            )
            lines.append("")

        rev_chg = analysis['revenue_change']
        if rev_chg < 0:
            lines.append(f"- Revenue fell by **{_fmt(abs(rev_chg))}** vs {analysis['previous_label']}")
        elif rev_chg > 0:
            lines.append(f"- Revenue grew by **{_fmt(rev_chg)}** vs {analysis['previous_label']}")

        exp_chg = curr['expense'] - prev['expense']
        if exp_chg > 0:
            lines.append(f"- Expenses rose by **{_fmt(exp_chg)}** vs {analysis['previous_label']}")
        elif exp_chg < 0:
            lines.append(f"- Expenses fell by **{_fmt(abs(exp_chg))}** vs {analysis['previous_label']}")

        if analysis['expense_changes']:
            lines.append("")
            lines.append("**Biggest expense movers:**")
            for item in analysis['expense_changes']:
                sign = '+' if item['change'] > 0 else ''
                lines.append(
                    f"- **{item['category']}**: {sign}{_fmt(item['change'])} "
                    f"({_fmt(item['previous'])} → {_fmt(item['current'])})"
                )

        if change < 0 and analysis['expense_changes']:
            top = analysis['expense_changes'][0]
            if top['change'] > 0:
                lines.append("")
                lines.append(
                    f"**Bottom line:** The main driver was **{top['category']}**, "
                    f"which increased by {_fmt(top['change'])}."
                )

        return "\n".join(lines)

    def _answer_expense_growth(self, q: str) -> str:
        growing = self.a.fastest_growing_expenses()
        if not growing:
            return "I don't have enough data across multiple months to detect expense trends yet."

        lines = ["### Fastest-growing expenses", ""]
        for i, item in enumerate(growing, 1):
            lines.append(
                f"{i}. **{item['category']}** — up **{item['pct_change']:.1f}%** "
                f"({_fmt(item['first_amount'])} in {item['first_month']} → "
                f"{_fmt(item['last_amount'])} in {item['last_month']})"
            )

        top = growing[0]
        lines.append("")
        lines.append(
            f"**Watch closely:** **{top['category']}** is growing fastest. "
            f"Ensure this spending is driving revenue or operational efficiency."
        )
        return "\n".join(lines)

    def _answer_runway(self, q: str) -> str:
        s = self.shortage
        runway = s['months_runway']
        balance = s['estimated_balance']
        avg_exp = s['avg_monthly_expense']

        if runway < 2:
            status = "🚨 **Critical** — immediate action needed."
        elif runway < 4:
            status = "⚠️ **Caution** — monitor closely."
        else:
            status = "✅ **Healthy** — comfortable buffer."

        partial_note = ""
        if s.get('excludes_partial_month'):
            partial_note = "\n\n*Runway calculated using complete months only for average expenses.*"

        return (
            f"### Cash Runway\n\n"
            f"At your current spending rate, you have approximately **{runway} months** "
            f"of cash runway.\n\n"
            f"- Estimated cash balance: **{_fmt(balance)}**\n"
            f"- Average monthly expenses: **{_fmt(avg_exp)}**\n"
            f"- Status: {status}"
            f"{partial_note}"
        )

    def _gather_business_issues(self) -> list:
        """Key issues/opportunities derived from analytics — shared by the business
        improvement plan and the smarter fallback so both stay consistent."""
        issues = []

        conc = self.a.revenue_concentration()
        if conc and conc['is_concentrated']:
            issues.append({
                'title': 'Revenue diversification',
                'detail': (
                    f"{conc['top_pct']:.0f}% of your revenue comes from **{conc['top_category']}**. "
                    f"Growing a second income stream would reduce risk."
                ),
            })

        marketing_trend = self.a.category_cost_trend('Marketing')
        if marketing_trend and abs(marketing_trend['pct_change']) >= 10:
            direction = 'increased' if marketing_trend['pct_change'] > 0 else 'decreased'
            issues.append({
                'title': 'Marketing efficiency',
                'detail': (
                    f"Marketing spend has {direction} {abs(marketing_trend['pct_change']):.1f}% from "
                    f"{marketing_trend['first_month']} to {marketing_trend['last_month']} — check whether "
                    f"that's translating into more sales."
                ),
            })

        staff = self.a.staff_cost_ratio()
        if staff:
            issues.append({
                'title': 'Payroll control',
                'detail': (
                    f"**{staff['category']}** is your largest expense at {staff['expense_pct']:.1f}% of total "
                    f"costs (₦{staff['revenue_ratio']:.0f} of every ₦100 earned). Keep staffing growth slower "
                    f"than revenue growth."
                ),
            })

        margin = self.a.profit_margin()
        if margin > 20:
            issues.append({
                'title': 'Protect your margin',
                'detail': (
                    f"Overall profit margin is strong at {margin:.1f}%. Maintain cost discipline rather than "
                    f"cutting into what's working."
                ),
            })
        else:
            issues.append({
                'title': 'Improve your margin',
                'detail': (
                    f"Overall profit margin is {margin:.1f}% — review your largest expense categories for "
                    f"room to improve."
                ),
            })

        best_month = self.a.best_revenue_month()
        if best_month and best_month['revenue'] > 0:
            issues.append({
                'title': 'Revenue consistency',
                'detail': (
                    f"**{best_month['month_label']}** was your strongest month with "
                    f"{_fmt(best_month['revenue'])} in revenue. Study what drove it and try to repeat "
                    f"those conditions."
                ),
            })

        return issues

    def _answer_business_improvement(self, q: str) -> str:
        issues = self._gather_business_issues()
        h = self.health
        margin = self.a.profit_margin()
        runway = self.shortage['months_runway']

        lines = [
            "### Business Performance Improvement Plan",
            "",
            f"Your business has a SmartFinance Score of **{h['score']}/100** ({h['label']}). "
            f"Here's where the biggest opportunities are:",
            "",
        ]
        for i, issue in enumerate(issues, 1):
            lines.append(f"**{i}. {issue['title']}**")
            lines.append(issue['detail'])
            lines.append("")

        if runway < 2:
            bottom = "Your biggest priority is cash preservation — runway is tight, so slow non-essential spending now."
        elif margin >= 20 and runway >= 4:
            bottom = "Your biggest priority isn't cost-cutting — it's growing revenue while protecting your strong margins."
        else:
            bottom = "Balance modest cost control with steady revenue growth to strengthen your position."

        lines.append(f"**Bottom line:** {bottom}")
        return "\n".join(lines)

    def _answer_sales_growth(self, q: str) -> str:
        rev_cat = self.a.revenue_by_category()
        if rev_cat.empty:
            return "I don't have revenue data yet, so I can't suggest growth actions."

        total_rev = self.a.total_revenue()
        top = rev_cat.iloc[0]
        top_pct = (top['Amount'] / total_rev * 100) if total_rev else 0
        conc = self.a.revenue_concentration()
        best_month = self.a.best_revenue_month()
        trend = self.a.revenue_trend_insight()

        lines = ["### How to improve sales", ""]
        lines.append(
            f"**{top['Category']}** is your main revenue driver, contributing "
            f"**{_fmt(top['Amount'])}** ({top_pct:.0f}% of total revenue)."
        )

        if best_month and best_month['revenue'] > 0:
            note = "" if best_month['is_complete'] else " — note this month isn't fully closed yet, so the real number may be higher"
            lines.append(
                f"Your strongest month so far was **{best_month['month_label']}** "
                f"with **{_fmt(best_month['revenue'])}** in revenue{note}."
            )

        lines.append("")
        lines.append(trend['message'])

        actions = []
        if best_month:
            actions.append(
                f"Review what was different about **{best_month['month_label']}** "
                f"(pricing, timing, marketing push) and try to repeat those conditions."
            )
        if conc and conc['is_concentrated']:
            actions.append(
                f"You're concentrated in **{conc['top_category']}** ({conc['top_pct']:.0f}% of revenue) — "
                f"introducing or growing a second revenue stream would reduce risk and add upside."
            )
        marketing_trend = self.a.category_cost_trend('Marketing')
        if marketing_trend:
            direction = 'rising' if marketing_trend['pct_change'] > 0 else 'falling'
            actions.append(
                f"Marketing spend is {direction} ({marketing_trend['pct_change']:+.1f}% from "
                f"{marketing_trend['first_month']} to {marketing_trend['last_month']}) — check whether "
                f"that spend is actually moving revenue, not just cost."
            )
        actions.append(
            f"Look at pricing or bundling for **{top['Category']}** — small adjustments there move the most "
            f"money since it's your biggest category."
        )
        actions.append(
            "Focus on repeat business from existing customers — retention is usually cheaper than acquisition."
        )

        lines.append("")
        lines.append("**Recommended actions:**")
        for i, a in enumerate(actions, 1):
            lines.append(f"{i}. {a}")

        lines.append("")
        lines.append(
            "*I don't have customer- or promotion-level data, so this is based on category and "
            "month-level trends only — not specific campaigns.*"
        )

        return "\n".join(lines)

    def _answer_actions(self, q: str) -> str:
        if not self.recommendations:
            return "Your finances look stable — no urgent actions flagged right now."

        lines = ["### Recommended actions this month", ""]
        for i, rec in enumerate(self.recommendations[:5], 1):
            lines.append(f"{i}. {rec['icon']} **{rec['title']}**")
            lines.append(f"   {rec['text']}")
            lines.append("")

        return "\n".join(lines)

    def _answer_health(self, q: str) -> str:
        h = self.health
        b = h['breakdown']
        emoji = '🟢' if h['score'] >= 80 else '🟡' if h['score'] >= 60 else '🔴'

        return (
            f"### Business Health Score\n\n"
            f"{emoji} **{h['score']}/100** — {h['label']}\n\n"
            f"| Dimension | Score |\n"
            f"|---|---|\n"
            f"| Profit Margin | {b['profit_margin']:.0f}/100 |\n"
            f"| Revenue Growth | {b['revenue_growth']:.0f}/100 |\n"
            f"| Expense Control | {b['expense_control']:.0f}/100 |\n"
            f"| Cash Runway | {b['cash_runway']:.0f}/100 |\n"
            f"| Revenue Diversification | {b['diversification']:.0f}/100 |"
        )

    def _answer_revenue_sources(self, q: str) -> str:
        rev_cat = self.a.revenue_by_category()
        if rev_cat.empty:
            return "No revenue data found."

        total = rev_cat['Amount'].sum()
        lines = ["### Revenue breakdown", ""]
        for _, row in rev_cat.iterrows():
            pct = row['Amount'] / total * 100
            lines.append(f"- **{row['Category']}**: {_fmt(row['Amount'])} ({pct:.1f}%)")

        conc = self.a.revenue_concentration()
        if conc and conc['is_concentrated']:
            lines.append("")
            lines.append(
                f"⚠️ **Concentration risk:** {conc['top_pct']:.0f}% of revenue comes from "
                f"**{conc['top_category']}**. Consider diversifying income streams."
            )

        return "\n".join(lines)

    def _answer_top_expenses(self, q: str) -> str:
        exp_cat = self.a.expense_by_category()
        if exp_cat.empty:
            return "No expense data found."

        total = self.a.total_expenses()
        lines = ["### Top expenses", ""]
        for i, row in exp_cat.head(5).iterrows():
            pct = row['Amount'] / total * 100
            lines.append(f"{i + 1}. **{row['Category']}**: {_fmt(row['Amount'])} ({pct:.1f}% of total)")

        staff = self.a.staff_cost_ratio()
        if staff:
            lines.append("")
            lines.append(
                f"**Efficiency note:** {_fmt(staff['amount'])} in {staff['category']} = "
                f"**{staff['revenue_ratio']:.1f}%** of revenue "
                f"(₦{staff['revenue_ratio']:.0f} of every ₦100 earned)."
            )

        return "\n".join(lines)

    def _answer_revenue_trend(self, q: str) -> str:
        trend = self.a.revenue_trend_insight()
        lines = [f"### Revenue trend\n\n{trend['message']}"]
        if trend.get('detail'):
            lines.append(f"\n{trend['detail']}")
        return "\n".join(lines)

    def _answer_forecast(self, q: str) -> str:
        fc = forecast_cashflow(self.a.df, months_ahead=3)
        proj = fc[fc['Type'] == 'Forecast']
        if proj.empty:
            return "Not enough historical data to generate a forecast."

        lines = ["### 3-month forecast", ""]
        if self.shortage.get('excludes_partial_month'):
            partial = self.a.partial_month_info()
            if partial:
                lines.append(
                    f"*Based on complete months only ({partial['month']} excluded as partial).*"
                )
                lines.append("")

        for _, row in proj.iterrows():
            lines.append(
                f"- **{row['MonthLabel']}**: Revenue {_fmt(row['Revenue'])}, "
                f"Expense {_fmt(row['Expense'])}, Profit {_fmt(row['Profit'])}"
            )

        rev_vals = proj['Revenue'].values
        if len(rev_vals) >= 2:
            if rev_vals[-1] > rev_vals[0]:
                lines.append("\n📈 Projected revenue trend: **upward**")
            elif rev_vals[-1] < rev_vals[0]:
                lines.append("\n📉 Projected revenue trend: **downward**")
            else:
                lines.append("\n➡️ Projected revenue trend: **stable**")

        return "\n".join(lines)

    def _answer_margin(self, q: str) -> str:
        overall = self.a.profit_margin()
        complete = self.a.complete_months_summary()

        lines = [
            f"### Profitability\n\n"
            f"**Overall margin:** {overall:.1f}% "
            f"({_fmt(self.a.net_profit())} profit on {_fmt(self.a.total_revenue())} revenue)",
        ]

        if not complete.empty:
            lines.append("\n**Monthly margins:**")
            for _, row in complete.iterrows():
                lines.append(f"- {row['MonthLabel']}: {row['Margin']:.1f}%")

        if overall > 20:
            lines.append("\n✅ Strong margins for an SME.")
        elif overall > 10:
            lines.append("\n🟡 Decent margins — room to improve cost efficiency.")
        else:
            lines.append("\n🔴 Margins are thin — review your largest expense categories.")

        return "\n".join(lines)

    def _answer_staff(self, q: str) -> str:
        staff = self.a.staff_cost_ratio()
        if not staff:
            return "I couldn't find staff or payroll expenses in your data."

        lines = [
            f"### Payroll analysis\n\n"
            f"**{staff['category']}** total: **{_fmt(staff['amount'])}**\n"
            f"- {staff['expense_pct']:.1f}% of total expenses\n"
            f"- {staff['revenue_ratio']:.1f}% of total revenue\n"
            f"- ₦{staff['revenue_ratio']:.0f} out of every ₦100 earned goes to salaries",
        ]

        trend = self.a.category_cost_trend(staff['category'])
        if trend:
            direction = 'increased' if trend['pct_change'] > 0 else 'decreased'
            lines.append(
                f"\nPayroll has **{direction}** by {abs(trend['pct_change']):.1f}% "
                f"from {trend['first_month']} ({_fmt(trend['first_amount'])}) to "
                f"{trend['last_month']} ({_fmt(trend['last_amount'])})."
            )

        return "\n".join(lines)

    def _answer_compare(self, q: str) -> str:
        comp = self.a.latest_complete_month_comparison()
        if not comp:
            return "Not enough complete months to make a comparison."

        return (
            f"### {comp['current_month']} vs {comp['previous_month']}\n\n"
            f"| Metric | Change |\n"
            f"|---|---|\n"
            f"| Revenue | {comp['revenue_growth']:+.1f}% |\n"
            f"| Expenses | {comp['expense_change']:+.1f}% |\n"
            f"| Profit | {comp['profit_growth']:+.1f}% |\n\n"
            f"- Revenue: {_fmt(comp['current_revenue'])}\n"
            f"- Expenses: {_fmt(comp['current_expense'])}\n"
            f"- Profit: {_fmt(comp['current_profit'])}"
        )

    def _answer_summary(self, q: str) -> str:
        kpis = self.a.current_month_kpis()
        partial = self.a.partial_month_info()

        lines = [
            "### Business snapshot",
            "",
            f"**Total revenue:** {_fmt(self.a.total_revenue())}",
            f"**Total expenses:** {_fmt(self.a.total_expenses())}",
            f"**Net profit:** {_fmt(self.a.net_profit())} ({self.a.profit_margin():.1f}% margin)",
            f"**Cash runway:** {self.shortage['months_runway']} months",
            f"**Health score:** {self.health['score']}/100 — {self.health['label']}",
            "",
            f"**Current month ({kpis['month']}){'  — partial data' if partial else ''}:**",
            f"- Revenue: {_fmt(kpis['revenue'])}",
            f"- Expenses: {_fmt(kpis['expenses'])}",
            f"- Profit: {_fmt(kpis['profit'])}",
        ]

        if self.recommendations:
            top = self.recommendations[0]
            lines.append("")
            lines.append(f"**Top priority:** {top['icon']} {top['title']} — {top['text']}")

        return "\n".join(lines)

    def _answer_fallback(self, q: str) -> str:
        issues = self._gather_business_issues()
        lines = [
            "I don't have a specific answer for that question yet, but based on your financial "
            "data, here are the areas that need the most attention:",
            "",
        ]
        for issue in issues:
            lines.append(f"- **{issue['title']}:** {issue['detail']}")

        lines.append("")
        lines.append("You can also try asking things like:")
        for s in SUGGESTED_QUESTIONS[:5]:
            lines.append(f"- {s}")

        return "\n".join(lines)


def create_copilot(analytics: FinanceAnalytics, shortage: dict | None = None) -> FinancialCopilot:
    if shortage is None:
        shortage = cash_shortage_alert(analytics.df)
    health = business_health_score(analytics, shortage)
    recommendations = generate_recommendations(analytics, shortage)
    return FinancialCopilot(analytics, shortage, health, recommendations)
