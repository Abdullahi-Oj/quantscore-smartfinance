# ₦ SmartFinance Dashboard

A financial intelligence dashboard built specifically for Nigerian SMEs. Upload your transaction Excel file and instantly get answers to your 5 most critical business questions.

## The 5 Questions It Answers

| # | Question | Where to Find It |
|---|----------|-----------------|
| 1 | How much money did I make this month? | 🏠 Home Dashboard → Current Month KPIs |
| 2 | What are my biggest expenses? | 💸 Expense Analysis |
| 3 | Is my revenue growing or declining? | 📊 Financial Performance |
| 4 | Am I making profit? | 🏠 Home Dashboard → Net Profit |
| 5 | Will I have a cash shortage soon? | 💰 Cashflow & Forecast |

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Your Data Template

Create an Excel file called `Transactions.xlsx` with these exact columns:

| Date | Description | Category | Type | Amount |
|------|-------------|----------|------|--------|
| 2026-01-02 | Product Sale | Sales | Revenue | 250000 |
| 2026-01-03 | Rent | Rent | Expense | 50000 |
| 2026-01-05 | Salary | Staff Cost | Expense | 120000 |

**Rules:**
- `Date`: YYYY-MM-DD format
- `Type`: Must be exactly `Revenue` or `Expense`
- `Amount`: Numbers only (no ₦ symbol, no commas)

## Project Structure

```
smart_finance_dashboard/
├── app.py               # Streamlit entry point — run this
├── data_loader.py       # Load & validate Excel files
├── cleaner.py           # Handle missing/dirty data
├── analytics.py         # FinanceAnalytics class — all KPIs
├── forecasting.py       # 3-month cashflow projection
├── charts.py            # Plotly visualizations
├── reports.py           # Export Excel report
├── data/
│   └── sample_data.xlsx # 82 sample transactions (Jan–Jun 2026)
└── requirements.txt
```

## Dashboard Pages

- **🏠 Home Dashboard** — Key metrics at a glance + cash shortage alert
- **📊 Financial Performance** — Profit trends, margins, MoM growth
- **📈 Revenue Analysis** — Revenue by category and trend
- **💸 Expense Analysis** — Top expenses + donut breakdown
- **💰 Cashflow & Forecast** — 1–6 month projection with slider
- **📥 Download Report** — Full Excel export with 5 sheets
