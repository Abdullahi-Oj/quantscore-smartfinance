import streamlit as st
import pandas as pd
from io import BytesIO
from pathlib import Path
from data_loader import load_data
from cleaner import clean_data
from analytics import FinanceAnalytics
from forecasting import forecast_cashflow, cash_shortage_alert
from insights import business_health_score, generate_recommendations
from copilot import create_copilot, SUGGESTED_QUESTIONS
from charts import (
    revenue_vs_expense_bar, profit_trend_line, expense_donut,
    cashflow_forecast_chart, monthly_growth_chart, revenue_category_bar,
)
from reports import generate_summary_report, generate_pdf_report

# ─── Page Config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SmartFinance Dashboard",
    page_icon="₦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp { background-color: #0f172a; color: #f1f5f9; }

.metric-card {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 20px 24px;
    text-align: center;
}
.metric-label { font-size: 13px; color: #94a3b8; font-weight: 500; letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 8px; }
.metric-value { font-size: 26px; font-weight: 700; color: #f1f5f9; }
.metric-delta-pos { font-size: 13px; color: #2ecc71; margin-top: 4px; }
.metric-delta-neg { font-size: 13px; color: #e74c3c; margin-top: 4px; }
.metric-delta-neu { font-size: 13px; color: #94a3b8; margin-top: 4px; }

.alert-danger { background: linear-gradient(135deg, #7f1d1d, #450a0a); border: 1px solid #dc2626; border-radius: 10px; padding: 16px; margin: 12px 0; }
.alert-warning { background: linear-gradient(135deg, #78350f, #431407); border: 1px solid #d97706; border-radius: 10px; padding: 16px; margin: 12px 0; }
.alert-success { background: linear-gradient(135deg, #064e3b, #022c22); border: 1px solid #10b981; border-radius: 10px; padding: 16px; margin: 12px 0; }
.alert-info { background: linear-gradient(135deg, #1e3a5f, #0f172a); border: 1px solid #3b82f6; border-radius: 10px; padding: 16px; margin: 12px 0; }

.health-score-card {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #334155; border-radius: 12px; padding: 24px; text-align: center;
}
.health-score-value { font-size: 48px; font-weight: 700; line-height: 1; }
.health-score-label { font-size: 14px; color: #94a3b8; margin-top: 8px; }

.rec-card {
    background: #1e293b; border: 1px solid #334155; border-radius: 10px;
    padding: 14px 18px; margin-bottom: 10px;
}
.rec-title { font-weight: 600; color: #f1f5f9; margin-bottom: 4px; }
.rec-text { font-size: 13px; color: #94a3b8; line-height: 1.5; }

.page-title { font-size: 28px; font-weight: 700; color: #f1f5f9; margin-bottom: 4px; }
.page-sub { font-size: 14px; color: #64748b; margin-bottom: 24px; }
.section-title { font-size: 16px; font-weight: 600; color: #94a3b8; letter-spacing: 0.05em; text-transform: uppercase; margin: 24px 0 12px; }

div[data-testid="stSidebar"] { background-color: #1e293b; }

div[data-testid="stChatMessage"] {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 4px 8px;
}
.suggest-btn button {
    font-size: 12px !important;
    border: 1px solid #334155 !important;
    background: #0f172a !important;
    color: #94a3b8 !important;
}
.suggest-btn button:hover {
    border-color: #3b82f6 !important;
    color: #f1f5f9 !important;
}
</style>
""", unsafe_allow_html=True)

# ─── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ₦ SmartFinance")
    st.markdown("---")

    uploaded_file = st.file_uploader(
        "Upload Transactions.xlsx",
        type=['xlsx'],
        help="Upload your Excel file with columns: Date, Description, Category, Type, Amount",
    )

    use_sample = st.checkbox("Use Sample Data", value=True)

    business_name = st.text_input(
        "Business Name",
        value="Your Business",
        help="Used as the letterhead on the downloadable PDF report",
    )

    st.markdown("---")

    page = st.radio(
        "Navigate",
        ["🏠 Home Dashboard", "🤖 Financial Copilot", "📊 Financial Performance", "📈 Revenue Analysis",
         "💸 Expense Analysis", "💰 Cashflow & Forecast", "📥 Download Report"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("<small style='color:#475569'>SmartFinance v1.2<br>Built for Nigerian SMEs</small>", unsafe_allow_html=True)

# ─── Load Data ───────────────────────────────────────────────────────────────
SAMPLE_DATA_PATH = Path(__file__).parent / "data" / "sample_data.xlsx"

@st.cache_data
def get_data(source_id: str, file_bytes: bytes | None = None):
    source = BytesIO(file_bytes) if file_bytes is not None else source_id
    df = load_data(source)
    if df is not None:
        df = clean_data(df)
    return df

if uploaded_file:
    df = get_data(uploaded_file.name, uploaded_file.getvalue())
elif use_sample:
    if SAMPLE_DATA_PATH.exists():
        df = get_data(str(SAMPLE_DATA_PATH))
    else:
        st.error(f"❌ Sample data not found at `{SAMPLE_DATA_PATH}`")
        df = None
else:
    df = None

if df is None or df.empty:
    st.warning("⚠️ No data loaded. Upload a file or enable sample data.")
    st.stop()

analytics = FinanceAnalytics(df)
kpis = analytics.current_month_kpis()
summary = analytics.monthly_growth()
shortage = cash_shortage_alert(df)
health = business_health_score(analytics, shortage)
recommendations = generate_recommendations(analytics, shortage)
mom_comparison = analytics.latest_complete_month_comparison()


# ─── Helper: Format Naira ───────────────────────────────────────────────────
def fmt(amount): return f"₦{amount:,.0f}"
def delta_html(val, suffix='%', reverse=False, label='vs last month'):
    good = val >= 0 if not reverse else val <= 0
    cls = 'metric-delta-pos' if good else 'metric-delta-neg'
    arrow = '▲' if val >= 0 else '▼'
    return f'<div class="{cls}">{arrow} {abs(val):.1f}{suffix} {label}</div>'

def insight_box(severity, message, detail=None):
    cls = {'success': 'alert-success', 'warning': 'alert-warning', 'danger': 'alert-danger', 'info': 'alert-info'}.get(severity, 'alert-info')
    detail_html = f'<br><small style="color:#94a3b8">{detail}</small>' if detail else ''
    return f'<div class="{cls}">{message}{detail_html}</div>'


# ─── PAGE: Home Dashboard ────────────────────────────────────────────────────
if page == "🏠 Home Dashboard":
    st.markdown(f'<div class="page-title">📊 Business Overview</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-sub">Showing data up to {df["Date"].max().strftime("%d %B %Y")}</div>', unsafe_allow_html=True)

    # Business Health Score + Cashflow alert row
    hc1, hc2 = st.columns([1, 2])
    with hc1:
        st.markdown(f"""<div class="health-score-card">
            <div class="metric-label">SmartFinance Score</div>
            <div class="health-score-value" style="color:{health['color']}">{health['score']}/100</div>
            <div class="health-score-label" style="color:{health['color']}">{'🟢' if health['score'] >= 80 else '🟡' if health['score'] >= 60 else '🔴'} {health['label']}</div>
        </div>""", unsafe_allow_html=True)
    with hc2:
        if shortage['alert']:
            st.markdown(f"""<div class="alert-danger">🚨 <strong>Cash Shortage Risk!</strong> 
            Estimated runway: <strong>{shortage['months_runway']} months</strong>. 
            Average monthly expenses: <strong>{fmt(shortage['avg_monthly_expense'])}</strong>. Take action now.</div>""", unsafe_allow_html=True)
        elif shortage['warning']:
            st.markdown(f"""<div class="alert-warning">⚠️ <strong>Monitor Cash Position.</strong> 
            Runway: <strong>{shortage['months_runway']} months</strong>. 
            Consider reducing expenses or boosting revenue.</div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div class="alert-success">✅ <strong>Cash Position Healthy.</strong> 
            Estimated runway: <strong>{shortage['months_runway']} months</strong>.</div>""", unsafe_allow_html=True)

    # Monthly comparison cards (complete months only)
    if mom_comparison:
        st.markdown('<div class="section-title">Latest Complete Month — ' + mom_comparison['current_month'] + ' vs ' + mom_comparison['previous_month'] + '</div>', unsafe_allow_html=True)
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.markdown(f"""<div class="metric-card">
                <div class="metric-label">Revenue Growth</div>
                <div class="metric-value">{mom_comparison['revenue_growth']:+.1f}%</div>
                {delta_html(mom_comparison['revenue_growth'], label=f"vs {mom_comparison['previous_month']}")}
            </div>""", unsafe_allow_html=True)
        with mc2:
            st.markdown(f"""<div class="metric-card">
                <div class="metric-label">Profit Growth</div>
                <div class="metric-value">{mom_comparison['profit_growth']:+.1f}%</div>
                {delta_html(mom_comparison['profit_growth'], label=f"vs {mom_comparison['previous_month']}")}
            </div>""", unsafe_allow_html=True)
        with mc3:
            st.markdown(f"""<div class="metric-card">
                <div class="metric-label">Expense Change</div>
                <div class="metric-value">{mom_comparison['expense_change']:+.1f}%</div>
                {delta_html(mom_comparison['expense_change'], reverse=True, label=f"vs {mom_comparison['previous_month']}")}
            </div>""", unsafe_allow_html=True)

    # KPI Row 1 — Current Month
    partial_label = ' (partial month)' if kpis['is_partial'] else ''
    st.markdown('<div class="section-title">Current Month — ' + kpis['month'] + partial_label + '</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        growth_label = 'vs last month (partial — not comparable)' if kpis['is_partial'] else 'vs last month'
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Revenue</div>
            <div class="metric-value">{fmt(kpis['revenue'])}</div>
            {delta_html(kpis['revenue_growth'], label=growth_label) if not kpis['is_partial'] else '<div class="metric-delta-neu">Partial month — MoM not comparable</div>'}
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Expenses</div>
            <div class="metric-value">{fmt(kpis['expenses'])}</div>
            {delta_html(kpis['expense_growth'], reverse=True)}
        </div>""", unsafe_allow_html=True)
    with c3:
        profit_cls = 'metric-delta-pos' if kpis['profit'] >= 0 else 'metric-delta-neg'
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Net Profit</div>
            <div class="metric-value" style="color: {'#2ecc71' if kpis['profit'] >= 0 else '#e74c3c'}">{fmt(kpis['profit'])}</div>
            <div class="{profit_cls}">{'✅ Profitable' if kpis['profit'] >= 0 else '❌ In Loss'}</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        margin = kpis['margin']
        color = '#2ecc71' if margin > 15 else '#f39c12' if margin > 0 else '#e74c3c'
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Profit Margin</div>
            <div class="metric-value" style="color:{color}">{margin:.1f}%</div>
            <div class="metric-delta-neu">{'Excellent' if margin > 20 else 'Good' if margin > 10 else 'Low' if margin > 0 else 'Negative'}</div>
        </div>""", unsafe_allow_html=True)

    # KPI Row 2 — All Time
    st.markdown('<div class="section-title">All-Time Summary</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Total Revenue</div>
            <div class="metric-value">{fmt(analytics.total_revenue())}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Total Expenses</div>
            <div class="metric-value">{fmt(analytics.total_expenses())}</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        np_ = analytics.net_profit()
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Net Profit</div>
            <div class="metric-value" style="color:{'#2ecc71' if np_ >= 0 else '#e74c3c'}">{fmt(np_)}</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Overall Margin</div>
            <div class="metric-value">{analytics.profit_margin():.1f}%</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    col1, col2 = st.columns([3, 2])
    with col1:
        st.plotly_chart(revenue_vs_expense_bar(summary), use_container_width=True)
    with col2:
        st.plotly_chart(expense_donut(analytics.expense_by_category()), use_container_width=True)

    # AI Financial Advisor panel
    st.markdown('<div class="section-title">🧠 AI Financial Advisor</div>', unsafe_allow_html=True)
    for rec in recommendations[:6]:
        st.markdown(f"""<div class="rec-card">
            <div class="rec-title">{rec['icon']} {rec['title']}</div>
            <div class="rec-text">{rec['text']}</div>
        </div>""", unsafe_allow_html=True)


# ─── PAGE: Financial Copilot ─────────────────────────────────────────────────
elif page == "🤖 Financial Copilot":
    st.markdown('<div class="page-title">🤖 Financial Copilot</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-sub">Ask questions about your business in plain English — powered by your transaction data</div>',
        unsafe_allow_html=True,
    )

    if "copilot_messages" not in st.session_state:
        st.session_state.copilot_messages = [{
            "role": "assistant",
            "content": (
                "Hi! I'm your **Financial Copilot**. I analyse your transaction data to answer "
                "questions like *\"Why did profit drop in April?\"* or *\"How many months can I survive?\"*\n\n"
                "Pick a suggested question below, or type your own."
            ),
        }]

    copilot = create_copilot(analytics, shortage)

    for msg in st.session_state.copilot_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    st.markdown('<div class="section-title">Suggested questions</div>', unsafe_allow_html=True)
    for row_start in range(0, len(SUGGESTED_QUESTIONS), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            idx = row_start + j
            if idx < len(SUGGESTED_QUESTIONS):
                with col:
                    if st.button(SUGGESTED_QUESTIONS[idx], key=f"suggest_{idx}", use_container_width=True):
                        q = SUGGESTED_QUESTIONS[idx]
                        st.session_state.copilot_messages.append({"role": "user", "content": q})
                        st.session_state.copilot_messages.append({
                            "role": "assistant",
                            "content": copilot.answer(q),
                        })
                        st.rerun()

    if st.button("🗑️ Clear conversation", type="secondary"):
        st.session_state.copilot_messages = st.session_state.copilot_messages[:1]
        st.rerun()

    if prompt := st.chat_input("Ask your Financial Copilot..."):
        st.session_state.copilot_messages.append({"role": "user", "content": prompt})
        st.session_state.copilot_messages.append({
            "role": "assistant",
            "content": copilot.answer(prompt),
        })
        st.rerun()


# ─── PAGE: Financial Performance ─────────────────────────────────────────────
elif page == "📊 Financial Performance":
    st.markdown('<div class="page-title">📊 Financial Performance</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Profit trends, margins, and growth rates</div>', unsafe_allow_html=True)

    trend = analytics.revenue_trend_insight()
    st.markdown(insight_box(trend['severity'], trend['message'], trend.get('detail')), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(profit_trend_line(summary), use_container_width=True)
    with col2:
        st.plotly_chart(monthly_growth_chart(summary), use_container_width=True)

    st.markdown("### Monthly Breakdown")
    display_cols = ['MonthLabel', 'Revenue', 'Expense', 'Profit', 'Margin', 'Revenue_Growth']
    display = summary[display_cols].copy()
    display.columns = ['Month', 'Revenue (₦)', 'Expense (₦)', 'Profit (₦)', 'Margin (%)', 'Rev Growth (%)']
    for col in ['Revenue (₦)', 'Expense (₦)', 'Profit (₦)']:
        display[col] = display[col].apply(lambda x: f"₦{x:,.0f}")
    for col in ['Margin (%)', 'Rev Growth (%)']:
        display[col] = display[col].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
    st.dataframe(display, use_container_width=True, hide_index=True)


# ─── PAGE: Revenue Analysis ───────────────────────────────────────────────────
elif page == "📈 Revenue Analysis":
    st.markdown('<div class="page-title">📈 Revenue Analysis</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Where your money comes from</div>', unsafe_allow_html=True)

    rev_cat = analytics.revenue_by_category()
    top_cat = rev_cat.iloc[0]['Category'] if not rev_cat.empty else "N/A"
    top_amt = rev_cat.iloc[0]['Amount'] if not rev_cat.empty else 0
    concentration = analytics.revenue_concentration()

    st.info(f"🏆 Top revenue source: **{top_cat}** contributing **{fmt(top_amt)}**")

    if concentration and concentration['is_concentrated']:
        st.markdown(insight_box(
            'warning',
            f"⚠️ Revenue concentration risk: {concentration['top_pct']:.0f}% of income comes from "
            f"<strong>{concentration['top_category']}</strong>. Consider growing service-based revenue "
            f"to reduce dependence on one income stream.",
        ), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(revenue_category_bar(rev_cat), use_container_width=True)
    with col2:
        fig = revenue_vs_expense_bar(summary)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Revenue by Category")
    rev_display = rev_cat.copy()
    rev_display['Amount'] = rev_display['Amount'].apply(fmt)
    rev_display['% of Total'] = (rev_cat['Amount'] / rev_cat['Amount'].sum() * 100).apply(lambda x: f"{x:.1f}%")
    st.dataframe(rev_display, use_container_width=True, hide_index=True)


# ─── PAGE: Expense Analysis ───────────────────────────────────────────────────
elif page == "💸 Expense Analysis":
    st.markdown('<div class="page-title">💸 Expense Analysis</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Your biggest cost drivers</div>', unsafe_allow_html=True)

    exp_cat = analytics.expense_by_category()
    top_exp = analytics.top_expenses()
    staff = analytics.staff_cost_ratio()

    if staff:
        st.markdown(insight_box(
            'warning',
            f"👥 <strong>Payroll Alert:</strong> {staff['category']} accounts for "
            f"<strong>{staff['expense_pct']:.1f}%</strong> of total expenses, making it the largest cost driver.",
            f"Staff Cost / Revenue ratio: <strong>{staff['revenue_ratio']:.1f}%</strong> — "
            f"₦{staff['revenue_ratio']:.0f} out of every ₦100 earned goes to salaries.",
        ), unsafe_allow_html=True)

        trend = analytics.category_cost_trend(staff['category'])
        if trend and abs(trend['pct_change']) >= 5:
            direction = 'increased' if trend['pct_change'] > 0 else 'decreased'
            st.markdown(insight_box(
                'warning' if trend['pct_change'] > 0 else 'success',
                f"📈 {staff['category']} has {direction} by <strong>{abs(trend['pct_change']):.1f}%</strong> "
                f"from {trend['first_month']} (₦{trend['first_amount']:,.0f}) to "
                f"{trend['last_month']} (₦{trend['last_amount']:,.0f}).",
                'Ensure revenue growth continues to justify payroll expansion.' if trend['pct_change'] > 0 else None,
            ), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(expense_donut(exp_cat), use_container_width=True)
    with col2:
        st.markdown("### 🔴 Top 5 Biggest Expenses")
        for _, row in top_exp.iterrows():
            pct = row['Amount'] / analytics.total_expenses() * 100
            st.markdown(f"""
            <div class="metric-card" style="margin-bottom:10px; text-align:left; padding:14px 18px;">
                <span style="font-weight:600;color:#f1f5f9">{row['Category']}</span>
                <span style="float:right;color:#e74c3c;font-weight:700">{fmt(row['Amount'])}</span>
                <br><small style="color:#64748b">{pct:.1f}% of total expenses</small>
            </div>""", unsafe_allow_html=True)

    st.markdown("### Full Expense Breakdown")
    exp_display = exp_cat.copy()
    exp_display['Amount'] = exp_display['Amount'].apply(fmt)
    exp_display['% of Total'] = (exp_cat['Amount'] / exp_cat['Amount'].sum() * 100).apply(lambda x: f"{x:.1f}%")
    st.dataframe(exp_display, use_container_width=True, hide_index=True)


# ─── PAGE: Cashflow & Forecast ────────────────────────────────────────────────
elif page == "💰 Cashflow & Forecast":
    st.markdown('<div class="page-title">💰 Cashflow & Forecast</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Projected cash position for the next few months</div>', unsafe_allow_html=True)

    months = st.slider("Months to forecast ahead", min_value=1, max_value=6, value=3)

    forecast_df = forecast_cashflow(df, months_ahead=months)

    if shortage.get('excludes_partial_month'):
        partial = analytics.partial_month_info()
        st.markdown(insight_box(
            'info',
            f"ℹ️ Forecast uses complete months only ({partial['month']} excluded — data through "
            f"{partial['data_through']}). Partial-month figures can skew projections.",
        ), unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Est. Cash Balance</div>
            <div class="metric-value">{fmt(shortage['estimated_balance'])}</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Avg Monthly Expense</div>
            <div class="metric-value">{fmt(shortage['avg_monthly_expense'])}</div>
        </div>""", unsafe_allow_html=True)
    with col3:
        runway = shortage['months_runway']
        color = '#e74c3c' if runway < 2 else '#f39c12' if runway < 4 else '#2ecc71'
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Cash Runway</div>
            <div class="metric-value" style="color:{color}">{runway} months</div>
        </div>""", unsafe_allow_html=True)

    st.plotly_chart(cashflow_forecast_chart(forecast_df), use_container_width=True)

    st.markdown("### Forecast Table")
    proj = forecast_df[forecast_df['Type'] == 'Forecast'][['MonthLabel', 'Revenue', 'Expense', 'Profit']].copy()
    for col in ['Revenue', 'Expense', 'Profit']:
        proj[col] = proj[col].apply(fmt)
    proj.columns = ['Month', 'Projected Revenue', 'Projected Expense', 'Projected Profit']
    st.dataframe(proj, use_container_width=True, hide_index=True)


# ─── PAGE: Download Report ────────────────────────────────────────────────────
elif page == "📥 Download Report":
    st.markdown('<div class="page-title">📥 Download Report</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Export your financial summary as a PDF summary or full Excel workbook</div>', unsafe_allow_html=True)

    col_pdf, col_xlsx = st.columns(2)

    with col_pdf:
        st.markdown("#### 📄 PDF Summary")
        st.markdown("""
        A one-page narrative report — ideal to print, email, or hand to
        a partner or lender:
        - Revenue, expenses, profit & margin
        - SmartFinance Score & cash runway
        - Key risks and recommended actions
        """)
        pdf_report = generate_pdf_report(df, analytics, shortage, health, recommendations, business_name=business_name)
        st.download_button(
            label="⬇️ Download PDF Report",
            data=pdf_report,
            file_name=f"{business_name.replace(' ', '_')}_SmartFinance_Report.pdf",
            mime="application/pdf",
        )

    with col_xlsx:
        st.markdown("#### 📊 Excel Workbook")
        st.markdown("""
        The full data export, for digging into the numbers:
        - **KPI Summary** — Total revenue, expenses, profit, margins
        - **Monthly Summary** — Month-by-month breakdown
        - **Expense Breakdown** — By category
        - **Revenue Breakdown** — By category
        - **All Transactions** — Raw data
        """)
        report = generate_summary_report(df)
        st.download_button(
            label="⬇️ Download Excel Report",
            data=report,
            file_name="SmartFinance_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.markdown("### Transaction Log")
    st.dataframe(
        df[['Date', 'Description', 'Category', 'Type', 'Amount']].sort_values('Date', ascending=False),
        use_container_width=True, hide_index=True,
    )