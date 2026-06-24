import pandas as pd
import io
from pathlib import Path
from analytics import FinanceAnalytics
from forecasting import cash_shortage_alert, forecast_cashflow
from insights import business_health_score

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, ListFlowable, ListItem,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Fonts ────────────────────────────────────────────────────────────────
# The base-14 PDF fonts (Helvetica etc.) silently drop the ₦ glyph — it
# renders as nothing at all, not even a box, so totals would look broken.
# DejaVu Sans does have the glyph. Fonts are bundled in fonts/ alongside
# this file rather than relying on system fonts, since production hosts
# (Render, Streamlit Cloud) aren't guaranteed to have them installed.
_FONTS_DIR = Path(__file__).parent / "fonts"
_FONT_REGULAR = "DejaVuSans"
_FONT_BOLD = "DejaVuSans-Bold"


def _register_fonts():
    registered = pdfmetrics.getRegisteredFontNames()
    if _FONT_REGULAR not in registered:
        pdfmetrics.registerFont(TTFont(_FONT_REGULAR, str(_FONTS_DIR / "DejaVuSans.ttf")))
    if _FONT_BOLD not in registered:
        pdfmetrics.registerFont(TTFont(_FONT_BOLD, str(_FONTS_DIR / "DejaVuSans-Bold.ttf")))


def _fmt_millions(amount: float) -> str:
    """Reads naturally for an SME owner: ₦20.5 million instead of ₦20,500,000."""
    if abs(amount) >= 1_000_000:
        return f"₦{amount / 1_000_000:,.1f} million"
    return f"₦{amount:,.0f}"


def _build_executive_assessment(analytics: FinanceAnalytics, shortage: dict, business_name: str) -> str:
    """A single synthesized paragraph answering 'so what?' rather than just
    'what happened?' — this is what most SME owners will actually read first."""
    margin = analytics.profit_margin()
    runway = shortage['months_runway']
    conc = analytics.revenue_concentration()
    marketing_trend = analytics.category_cost_trend('Marketing')
    staff = analytics.staff_cost_ratio()

    if margin >= 30:
        margin_phrase = f"strong margins ({margin:.1f}%)"
    elif margin >= 10:
        margin_phrase = f"solid margins ({margin:.1f}%)"
    elif margin >= 0:
        margin_phrase = f"thin margins ({margin:.1f}%)"
    else:
        margin_phrase = f"a net loss ({margin:.1f}% margin)"

    if runway >= 6:
        runway_phrase = f"a healthy cash runway of {runway} months"
    elif runway >= 2:
        runway_phrase = f"a moderate cash runway of {runway} months"
    else:
        runway_phrase = f"a critically short cash runway of {runway} months"

    if margin >= 0:
        opening = f"{business_name} is a profitable business with {margin_phrase} and {runway_phrase}."
    else:
        opening = f"{business_name} is currently operating at {margin_phrase}, with {runway_phrase}."

    risks = []
    if conc and conc['is_concentrated']:
        risks.append("heavy dependence on a single revenue source")
    if marketing_trend and marketing_trend['pct_change'] >= 30:
        risks.append("rapidly rising marketing spend")
    if staff and staff['expense_pct'] >= 30:
        risks.append("payroll consuming a large share of expenses")

    if not risks:
        risk_sentence = "No major risk factors stand out this period."
    elif len(risks) == 1:
        risk_sentence = f"The primary risk is {risks[0]}."
    else:
        risk_sentence = f"The primary risks are {', '.join(risks[:-1])} and {risks[-1]}."

    priorities = []
    if conc and conc['is_concentrated']:
        priorities.append("revenue diversification")
    if marketing_trend and marketing_trend['pct_change'] >= 30:
        priorities.append("marketing efficiency")
    if staff and staff['expense_pct'] >= 30:
        priorities.append("payroll discipline")

    if priorities:
        priority_sentence = f"The business should prioritize {' and '.join(priorities)}"
    else:
        priority_sentence = "The business should continue its current approach"
    priority_sentence += (
        " while maintaining current cost discipline."
        if margin >= 20 else
        " while improving overall cost control."
    )

    return f"{opening} {risk_sentence} {priority_sentence}"


def _previous_month_health_score(df: pd.DataFrame) -> int:
    """Recomputes the health score using only data up to the start of the
    most recent month present, as a trend baseline. Returns None if there
    isn't a distinct prior month to compare against — never fabricates a
    number to fill the gap."""
    latest_month_start = df['Date'].max().to_period('M').to_timestamp()
    prior_df = df[df['Date'] < latest_month_start]
    if prior_df.empty or prior_df['Date'].dt.to_period('M').nunique() < 1:
        return None
    try:
        prior_analytics = FinanceAnalytics(prior_df)
        prior_shortage = cash_shortage_alert(prior_df)
        prior_health = business_health_score(prior_analytics, prior_shortage)
        return prior_health['score']
    except Exception:
        return None


def _next_month_outlook(df: pd.DataFrame, shortage: dict) -> dict:
    """Pulls the first forecasted month's revenue (reusing the existing
    growth-rate forecast, not a new model) plus a simple risk label. Returns
    None if there isn't enough history to forecast at all."""
    forecast_df = forecast_cashflow(df, months_ahead=1)
    if forecast_df.empty:
        return None
    forecast_rows = forecast_df[forecast_df['Type'] == 'Forecast']
    if forecast_rows.empty:
        return None

    if shortage['alert']:
        risk_level = 'High'
    elif shortage['warning']:
        risk_level = 'Medium'
    else:
        risk_level = 'Low'

    row = forecast_rows.iloc[0]
    return {'month_label': row['MonthLabel'], 'revenue': row['Revenue'], 'risk_level': risk_level}


def generate_pdf_report(
    df: pd.DataFrame,
    analytics: FinanceAnalytics,
    shortage: dict,
    health: dict,
    recommendations: list,
    business_name: str = "Your Business",
) -> bytes:
    """A short, narrative one-pager an SME owner can hand to a partner or
    pin on a wall — distinct from the multi-sheet Excel export, which is
    for someone who wants to dig into the numbers."""
    _register_fonts()

    styles = getSampleStyleSheet()
    base = ParagraphStyle('Base', parent=styles['Normal'], fontName=_FONT_REGULAR, fontSize=10, leading=14)
    title_style = ParagraphStyle('TitleX', parent=styles['Title'], fontName=_FONT_BOLD, fontSize=20, textColor=colors.HexColor('#0f172a'))
    meta_style = ParagraphStyle('Meta', parent=base, fontSize=10, textColor=colors.HexColor('#475569'), alignment=TA_CENTER)
    h2 = ParagraphStyle('H2', parent=base, fontName=_FONT_BOLD, fontSize=13, textColor=colors.HexColor('#0f172a'), spaceBefore=8, spaceAfter=4)
    bullet_style = ParagraphStyle('Bullet', parent=base, fontSize=10, leading=14)
    assessment_style = ParagraphStyle('Assessment', parent=base, fontSize=10.5, leading=15, textColor=colors.HexColor('#1e293b'))
    footer_style = ParagraphStyle('Footer', parent=base, fontSize=8, textColor=colors.HexColor('#94a3b8'))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )
    story = []

    # ── Letterhead ──
    story.append(Paragraph("QuantScore SmartFinance Report", title_style))
    story.append(Spacer(1, 4))
    period_start = df['Date'].min().strftime('%b %Y')
    period_end = df['Date'].max().strftime('%b %Y')
    story.append(Paragraph(f"Business: {business_name}", meta_style))
    story.append(Paragraph(f"Period: {period_start} – {period_end}", meta_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", color=colors.HexColor('#cbd5e1'), thickness=1))
    story.append(Spacer(1, 8))

    # ── Summary ── (all KPIs in one table, including Cash Runway, with
    # Health Score and Status as separate rows rather than one combined cell)
    story.append(Paragraph("Summary", h2))
    total_rev = analytics.total_revenue()
    total_exp = analytics.total_expenses()
    net_profit = analytics.net_profit()
    margin = analytics.profit_margin()

    summary_rows = [
        ["Revenue", _fmt_millions(total_rev)],
        ["Expenses", _fmt_millions(total_exp)],
        ["Profit", f"{_fmt_millions(net_profit)}  ({margin:.1f}% margin)"],
        ["Health Score", f"{health['score']}/100"],
        ["Status", health['label']],
        ["Cash Runway", f"{shortage['months_runway']} months"],
    ]
    table = Table(summary_rows, colWidths=[5.5 * cm, 9.5 * cm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), _FONT_REGULAR),
        ('FONTNAME', (1, 2), (1, 2), _FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#475569')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#0f172a')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    story.append(table)

    # ── Executive Assessment ── ("so what?", not just "what happened?")
    story.append(Paragraph("Executive Assessment", h2))
    assessment = _build_executive_assessment(analytics, shortage, business_name)
    story.append(Paragraph(assessment, assessment_style))

    # ── Business Health Trend ── (only shown if a real prior month exists —
    # never fabricated)
    prev_score = _previous_month_health_score(df)
    if prev_score is not None:
        change = health['score'] - prev_score
        change_str = f"+{change}" if change > 0 else str(change)
        story.append(Paragraph("Business Health Trend", h2))
        trend_rows = [
            ["Previous Month Score", f"{prev_score}/100"],
            ["Current Score", f"{health['score']}/100"],
            ["Change", f"{change_str} points"],
        ]
        trend_table = Table(trend_rows, colWidths=[5.5 * cm, 9.5 * cm])
        trend_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), _FONT_REGULAR),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#475569')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#0f172a')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(trend_table)

    # ── Business Outlook ── (reuses the existing growth-rate forecast;
    # only shown if there's enough history to forecast from at all)
    outlook = _next_month_outlook(df, shortage)
    if outlook is not None:
        story.append(Paragraph("Business Outlook", h2))
        outlook_rows = [
            [f"Expected Revenue ({outlook['month_label']})", _fmt_millions(outlook['revenue'])],
            ["Risk Level", outlook['risk_level']],
        ]
        outlook_table = Table(outlook_rows, colWidths=[7.5 * cm, 7.5 * cm])
        outlook_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), _FONT_REGULAR),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#475569')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#0f172a')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(outlook_table)

    # ── Key Risks ── (observations only — what's true, not what to do)
    story.append(Paragraph("Key Risks", h2))
    risk_recs = [r for r in recommendations if r['priority'] in ('critical', 'high')]
    if not risk_recs:
        risk_recs = recommendations[:3]

    if risk_recs:
        items = [ListItem(Paragraph(r['title'], bullet_style), leftIndent=4) for r in risk_recs[:5]]
        story.append(ListFlowable(items, bulletType='bullet', start='•', leftIndent=12))
    else:
        story.append(Paragraph("No significant risks flagged this period.", bullet_style))

    # ── Recommended Actions ── (imperative directives only, not the
    # observation text — that's what Key Risks is for)
    story.append(Paragraph("Recommended Actions", h2))
    if recommendations:
        items = [ListItem(Paragraph(r.get('action', r['text']), bullet_style), leftIndent=4) for r in recommendations[:5]]
        story.append(ListFlowable(items, bulletType='bullet', start='•', leftIndent=12))
    else:
        story.append(Paragraph("No specific recommendations at this time.", bullet_style))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", color=colors.HexColor('#e2e8f0'), thickness=0.5))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Generated by SmartFinance. Figures are based on uploaded transaction data and "
        "are for informational purposes only — not financial or tax advice.",
        footer_style,
    ))

    doc.build(story)
    return buf.getvalue()


def generate_summary_report(df: pd.DataFrame) -> bytes:
    analytics = FinanceAnalytics(df)
    summary = analytics.monthly_summary()
    kpis = analytics.current_month_kpis()
    exp_cat = analytics.expense_by_category()
    rev_cat = analytics.revenue_by_category()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # KPI Summary sheet
        kpi_data = {
            'Metric': [
                'Total Revenue (All Time)', 'Total Expenses (All Time)',
                'Net Profit (All Time)', 'Overall Profit Margin (%)',
                f"Revenue ({kpis['month']})", f"Expenses ({kpis['month']})",
                f"Net Profit ({kpis['month']})", f"Profit Margin ({kpis['month']}) (%)",
                'Revenue Growth MoM (%)',
            ],
            'Value': [
                analytics.total_revenue(), analytics.total_expenses(),
                analytics.net_profit(), round(analytics.profit_margin(), 2),
                kpis['revenue'], kpis['expenses'],
                kpis['profit'], round(kpis['margin'], 2),
                round(kpis['revenue_growth'], 2),
            ]
        }
        pd.DataFrame(kpi_data).to_excel(writer, sheet_name='KPI Summary', index=False)

        # Monthly Summary
        summary[['MonthLabel', 'Revenue', 'Expense', 'Profit', 'Margin']].to_excel(
            writer, sheet_name='Monthly Summary', index=False
        )

        # Expense Breakdown
        exp_cat.to_excel(writer, sheet_name='Expense Breakdown', index=False)

        # Revenue Breakdown
        rev_cat.to_excel(writer, sheet_name='Revenue Breakdown', index=False)

        # Raw Transactions
        df[['Date', 'Description', 'Category', 'Type', 'Amount']].to_excel(
            writer, sheet_name='Transactions', index=False
        )

    return output.getvalue()