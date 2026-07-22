import streamlit as st
import pandas as pd
import json
import os
from io import BytesIO
from pathlib import Path
import tempfile
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
from pos_engine.financial_engine import MerchantPricing, Transaction, daily_pnl
from pos_engine import providers as pos_engine_providers
from evidence_layer import EvidenceProcessor
from pos_engine.transaction_adapter import daily_pnl_to_transactions
from database import init_db, get_session, save_day_to_ledger, get_ledger_for_merchant, save_evidence
from database.repositories import MerchantRepository
from database.models import Merchant as MerchantModel, DailyFinancial
from bootstrap import seed_if_needed

if seed_if_needed():
    st.toast("First-time setup: seeded provider pricing data.", icon="📦")

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
div[data-testid="stChatMessage"] div[data-testid="stMarkdownContainer"],
div[data-testid="stChatMessage"] p,
div[data-testid="stChatMessage"] li,
div[data-testid="stChatMessage"] strong,
div[data-testid="stChatMessage"] em {
    color: #f1f5f9 !important;
}

/* Suggested-question buttons and the "Clear conversation" button.
   Previously targeted a .suggest-btn wrapper class that nothing in the
   page actually applied, so this CSS never matched anything — buttons
   fell back to Streamlit's unthemed default styling, which is hard to
   read against this page's dark background. */
div[data-testid="stButton"] button {
    border: 1px solid #334155 !important;
    background-color: #0f172a !important;
    color: #f1f5f9 !important;
}
div[data-testid="stButton"] button:hover {
    border-color: #3b82f6 !important;
    color: #ffffff !important;
}
div[data-testid="stButton"] button p {
    color: inherit !important;
}

/* st.info / st.warning / st.error boxes — same issue: the global white
   text color set on .stApp was overriding these components' own (dark,
   light-theme-default) text color, leaving white text on their pale
   default backgrounds. */
div[data-testid="stAlertContainer"] {
    background-color: #1e293b !important;
    border: 1px solid #334155 !important;
}
div[data-testid="stAlertContainer"] p,
div[data-testid="stAlertContainer"] li,
div[data-testid="stAlertContainer"] strong {
    color: #f1f5f9 !important;
}
</style>
""", unsafe_allow_html=True)

# ─── Merchant helpers ────────────────────────────────────────────────────────
def get_or_create_merchant(name: str, provider: str, level: str) -> int:
    """Gets or creates a merchant row keyed on name+provider.
    Returns the merchant's integer id.
    Full auth/multi-merchant comes later; for a pilot, one row per
    business name is the right level of complexity."""
    db = get_session()
    try:
        merchant = db.query(MerchantModel).filter(
            MerchantModel.name == name,
        ).first()
        if merchant is None:
            merchant = MerchantRepository(db).create_merchant(
                name=name,
                provider_code=provider,
                level_code=level,
                business_type="POS Agent",
            )
        return merchant.id
    finally:
        db.close()


# ─── Session state initialisation ────────────────────────────────────────────
if "pos_today_transactions" not in st.session_state:
    st.session_state.pos_today_transactions = []
if "pos_out_of_bracket_transactions" not in st.session_state:
    st.session_state.pos_out_of_bracket_transactions = []
if "pos_all_rows" not in st.session_state:
    st.session_state.pos_all_rows = []
if "pos_merchant_id" not in st.session_state:
    st.session_state.pos_merchant_id = None

with st.sidebar:
    st.markdown("## ₦ SmartFinance")
    st.markdown("---")

    business_type = st.radio(
        "Business Type",
        ["General SME", "POS Agent"],
        help="POS Agent uses a different daily-entry flow suited to per-transaction fee economics, "
             "instead of an Excel upload.",
    )

    if business_type == "General SME":
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
    else:
        uploaded_file = None
        use_sample = False
        business_name = st.text_input("Merchant Name", value="Your POS Business")
        st.markdown("##### Merchant Setup")
        pos_provider = st.selectbox(
            "Provider", ["OPay", "Moniepoint"],
            help="OPay's schedule is from a documented rate card. Moniepoint's is provisional, "
                 "derived from limited observed data — see the caption below.",
        )
        if pos_provider == "OPay":
            pos_level = st.selectbox("Merchant Level", ["Platinum", "Gold", "Regular"])
        else:
            pos_level = st.selectbox("Merchant Level", ["Standard"])
            st.caption(
                "⚠️ Moniepoint's fee schedule is provisional — derived from one real "
                "statement's observed fees, not an official rate card. Treat calculated "
                "fees here with more caution than OPay's."
            )

        # Resolve (or create) the merchant record whenever name/provider changes.
        merchant_key = f"{business_name}:{pos_provider}"
        if st.session_state.get("_merchant_key") != merchant_key:
            st.session_state.pos_merchant_id = get_or_create_merchant(business_name, pos_provider, pos_level)
            st.session_state._merchant_key = merchant_key

        db_session = get_session()
        days_in_db = db_session.query(DailyFinancial).filter(
            DailyFinancial.merchant_id == st.session_state.pos_merchant_id
        ).count()
        db_session.close()
        st.caption(f"📦 {days_in_db} day(s) saved to database · {len(st.session_state.pos_all_rows) // 3} in this session")

    st.markdown("---")

    if business_type == "POS Agent":
        page_options = ["🧾 POS Daily Entry", "🏠 Home Dashboard", "🤖 Financial Copilot",
                         "📊 Financial Performance", "📈 Revenue Analysis", "💸 Expense Analysis",
                         "💰 Cashflow & Forecast", "📥 Download Report"]
    else:
        page_options = ["🏠 Home Dashboard", "🤖 Financial Copilot", "📊 Financial Performance", "📈 Revenue Analysis",
                         "💸 Expense Analysis", "💰 Cashflow & Forecast", "📥 Download Report"]

    page = st.radio("Navigate", page_options, label_visibility="collapsed")

    st.markdown("---")
    st.markdown("<small style='color:#475569'>SmartFinance v1.2<br>Built for Nigerian SMEs</small>", unsafe_allow_html=True)

# ─── POS Daily Entry (doesn't need analytics — generates the data instead) ──
if business_type == "POS Agent" and page == "🧾 POS Daily Entry":
    st.markdown('<div class="page-title">🧾 POS Daily Entry</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Log today\'s transactions, then save the day to build your financial history</div>', unsafe_allow_html=True)

    with st.expander("📂 Load / Save Your History", expanded=(len(st.session_state.pos_all_rows) == 0)):
        st.caption(
            "⚠️ Your data only lives in this browser session — it is lost on refresh, app restart, "
            "or if this sits idle long enough to sleep. Download your history after each session, "
            "and load it back in next time, until real persistent storage is built."
        )
        load_col, save_col = st.columns(2)
        with load_col:
            history_file = st.file_uploader("Load previous history (.json)", type=["json"], key="pos_history_upload")
            if history_file is not None:
                try:
                    loaded_rows = json.load(history_file)
                    for row in loaded_rows:
                        row["Date"] = pd.Timestamp(row["Date"])
                    st.session_state.pos_all_rows = loaded_rows
                    st.success(f"Loaded {len(loaded_rows) // 1} row(s) from history. Switch pages to see it reflected.")
                except Exception as e:
                    st.error(f"❌ Couldn't read that history file: {e}")
        with save_col:
            if st.session_state.pos_all_rows:
                export_rows = [
                    {**row, "Date": row["Date"].isoformat() if hasattr(row["Date"], "isoformat") else str(row["Date"])}
                    for row in st.session_state.pos_all_rows
                ]
                st.download_button(
                    "💾 Download current history (.json)",
                    data=json.dumps(export_rows, indent=2),
                    file_name=f"{business_name.replace(' ', '_')}_pos_history.json",
                    mime="application/json",
                )
            else:
                st.caption("Nothing to download yet — save at least one day first.")

    with st.expander("Personal Pricing — what YOU charge customers", expanded=True):
        st.caption("Every operator prices differently. Set what you actually charge per bracket. Transactions outside these ranges? Use custom pricing in manual entry.")

        # Define pricing brackets: (min, max, charge_label). Withdrawal and
        # Bank Transfer are priced separately below (they use the same
        # bracket ranges, but the actual ₦ charge per bracket is NOT the
        # same for both service types on any real POS provider — collapsing
        # them into one shared price was the bug being fixed here).
        pricing_ranges = [
            (1, 5000, "₦1 – ₦5,000"),
            (5001, 9999, "₦5,001 – ₦9,999"),
            (10000, 19999, "₦10,000 – ₦19,999"),
            (20000, 29999, "₦20,000 – ₦29,999"),
            (30000, 39999, "₦30,000 – ₦39,999"),
            (40000, 49999, "₦40,000 – ₦49,999"),
            (50000, 59999, "₦50,000 – ₦59,999"),
            (60000, 69999, "₦60,000 – ₦69,999"),
            (70000, 79999, "₦70,000 – ₦79,999"),
            (80000, 89999, "₦80,000 – ₦89,999"),
            (90000, 99999, "₦90,000 – ₦99,999"),
            (100000, 109999, "₦100,000 – ₦109,999"),
            (110000, 199999, "₦110,000 – ₦199,999"),
            (200000, float("inf"), "₦200,000+"),
        ]

        # Initialize pricing in session state if not exists — one charge
        # map per service type, no longer shared.
        if "_withdrawal_charges" not in st.session_state:
            st.session_state._withdrawal_charges = {
                f"{low}-{high}": 0 for low, high, _ in pricing_ranges
            }
        if "_transfer_to_bank_charges" not in st.session_state:
            st.session_state._transfer_to_bank_charges = {
                f"{low}-{high}": 0 for low, high, _ in pricing_ranges
            }
        if "_airtime_charge" not in st.session_state:
            st.session_state._airtime_charge = 0
        if "_pos_transfer_charge" not in st.session_state:
            st.session_state._pos_transfer_charge = 0

        def _render_bracket_inputs(section_label, state_key, key_prefix):
            """Renders one set of per-bracket number inputs bound to its own
            session_state charge map, so Withdrawal and Bank Transfer can be
            priced independently instead of sharing one set of charges."""
            st.markdown(f"**{section_label}**")
            charge_map = st.session_state[state_key]
            cols_per_row = 3
            for i in range(0, len(pricing_ranges), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, col in enumerate(cols):
                    if i + j < len(pricing_ranges):
                        low, high, label = pricing_ranges[i + j]
                        key = f"{low}-{high}"
                        with col:
                            charge = st.number_input(
                                f"Charge for {label}",
                                value=charge_map.get(key, 0),
                                step=10,
                                key=f"{key_prefix}_{key}",
                            )
                            charge_map[key] = charge

        # Withdrawal pricing (separate from Bank Transfer — see note above)
        _render_bracket_inputs(
            "💵 Withdrawal Brackets", "_withdrawal_charges", "wd_charge"
        )

        st.markdown("---")

        # Bank Transfer pricing (separate from Withdrawal)
        _render_bracket_inputs(
            "🏦 Bank Transfer Brackets", "_transfer_to_bank_charges", "tb_charge"
        )

        # Airtime / Data / Bills pricing (flat fee, not per bracket)
        st.markdown("**📱 Airtime / Data / Bills Payment** (flat fee per transaction)")
        airtime_charge = st.number_input(
            "Charge per airtime/data/bills transaction",
            value=st.session_state._airtime_charge,
            step=10,
            key="airtime_charge_input",
        )
        st.session_state._airtime_charge = airtime_charge

        # POS Transfer / QR pricing (flat fee, not per bracket)
        st.markdown("**🔄 POS Transfer / QR** (flat fee per transaction)")
        pos_transfer_charge = st.number_input(
            "Charge per POS transfer/QR transaction",
            value=st.session_state._pos_transfer_charge,
            step=10,
            key="pos_transfer_charge_input",
        )
        st.session_state._pos_transfer_charge = pos_transfer_charge

    def _build_brackets(charge_map, defaults):
        """Turns a {'low-high': charge} map into the (low, high, charge)
        tuple list MerchantPricing expects, skipping unconfigured (₦0)
        brackets. Falls back to `defaults` only if NOTHING was configured
        at all, so a partially-configured set of brackets is respected
        rather than silently replaced."""
        brackets = [
            (low, high, charge_map.get(f"{low}-{high}", 0))
            for low, high, _ in pricing_ranges
            if charge_map.get(f"{low}-{high}", 0) > 0
        ]
        return brackets if brackets else defaults

    _withdrawal_defaults = [
        (1, 5000, 100), (5001, 9999, 150), (10000, 19999, 200),
        (20000, 29999, 300), (30000, 199999, 350), (200000, float("inf"), 400),
    ]
    _transfer_to_bank_defaults = [
        (1, 5000, 100), (5001, 9999, 150), (10000, 19999, 200),
        (20000, 29999, 300), (30000, 199999, 350), (200000, float("inf"), 400),
    ]

    withdrawal_brackets = _build_brackets(st.session_state._withdrawal_charges, _withdrawal_defaults)
    transfer_to_bank_brackets = _build_brackets(st.session_state._transfer_to_bank_charges, _transfer_to_bank_defaults)

    # Kept for the out-of-bracket check below: the union of both bracket
    # sets' configured (non-catch-all) ranges, used to decide whether a
    # manually-entered amount falls inside a bracket the operator actually
    # configured, or only lands there via the open-ended catch-all / a
    # custom override.
    _configured_finite_ranges = [
        (low, high) for low, high, _ in pricing_ranges if high != float("inf")
    ]

    pricing = MerchantPricing(
        cash_out_brackets=withdrawal_brackets,
        transfer_to_bank_brackets=transfer_to_bank_brackets,
        airtime_data_bills_bracket=(st.session_state._airtime_charge,),
        pos_transfers_qr_bracket=(st.session_state._pos_transfer_charge,),
    )

    st.markdown("##### Upload Evidence — instead of typing transactions by hand")
    st.caption(
        "Currently supported: **OPay** (.pdf statement export, app screenshot) and "
        "**Moniepoint** (.xlsx statement export, app screenshot). Other providers/formats "
        "aren't validated yet and won't be accepted."
    )
    ev_col1, ev_col2 = st.columns(2)
    with ev_col1:
        evidence_provider = st.selectbox("Evidence source provider", ["OPay", "Moniepoint"], key="evidence_provider")
    with ev_col2:
        evidence_file = st.file_uploader(
            "Statement or screenshot",
            type=["pdf", "xlsx", "xls", "png", "jpg", "jpeg"],
            key="evidence_file_upload",
        )

    if evidence_file is not None:
        evidence_bytes = evidence_file.getvalue()
        suffix = Path(evidence_file.name).suffix

        # Re-extract only when the uploaded file actually changes, so a Streamlit
        # rerun (e.g. from editing a correction below) doesn't re-run OCR every time.
        cache_key = f"{evidence_provider}:{evidence_file.name}:{len(evidence_bytes)}"
        if st.session_state.get("_evidence_cache_key") != cache_key:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                tmp_file.write(evidence_bytes)
                tmp_path = tmp_file.name
            processor = EvidenceProcessor(provider=evidence_provider)
            with st.spinner("Extracting transactions..."):
                raw_result = processor.process_file(tmp_path)
            os.unlink(tmp_path)
            # IMMUTABLE: this is the original OCR/extraction output, stored exactly as
            # produced. It is never edited in place — corrections live in a SEPARATE
            # structure below, preserving a full evidence -> extraction -> correction ->
            # validated-transaction audit trail (per explicit design decision).
            st.session_state._evidence_cache_key = cache_key
            st.session_state._evidence_raw_result = raw_result
            st.session_state._evidence_corrections = {}  # index -> {field: corrected_value, reason: str}

        result = st.session_state._evidence_raw_result

        if not result["success"]:
            errs = (result.get("raw_extraction") or {}).get("errors") or \
                   (result.get("validation_result") or {}).get("errors") or ["Unknown extraction failure."]
            for e in errs:
                st.error(f"❌ {e}")
        else:
            vr = result["validation_result"]
            level_info = (result.get("raw_extraction") or {}).get("confidence_level") or {}
            level_badge = f"Level {level_info.get('level', '?')} — {level_info.get('label', 'Unknown source')}"
            st.info(f"📋 Evidence confidence: **{level_badge}** (extraction confidence: {vr['confidence_score']:.0%})")
            st.success(f"Extracted {vr['summary']['valid']} of {vr['summary']['total_extracted']} transaction(s).")

            if vr["requires_manual_review"]:
                st.warning("⚠️ This extraction needs your review before it can be saved.")
            for w in vr["warnings"][-4:]:
                st.caption(f"• {w}")

            review_rows = [r for r in vr["transactions"] if not r.get("is_levy_line")]
            if review_rows:
                flagged_rows = [r for r in review_rows if r.get("needs_amount_confirmation") or r.get("needs_date_confirmation")]
                clean_rows = [r for r in review_rows if r not in flagged_rows]

                all_confirmed = True

                if clean_rows:
                    st.markdown(
                        f"**{len(clean_rows)} transaction(s)** came from a high-confidence source "
                        f"and don't need row-by-row correction — review the totals below."
                    )
                    clean_df = pd.DataFrame([
                        {"Date": r.get("date"), "Description": r.get("description", "")[:45],
                         "Amount": r["amount"], "Direction": r["direction"]}
                        for r in clean_rows
                    ])
                    st.dataframe(clean_df, use_container_width=True, hide_index=True, height=min(300, 38 * (len(clean_rows) + 1)))
                    clean_total = sum(r["amount"] for r in clean_rows if r["direction"] == "in")
                    st.caption(f"Total credited across these {len(clean_rows)} transactions: ₦{clean_total:,.2f}")
                    bulk_confirm = st.checkbox(
                        f"I've spot-checked these {len(clean_rows)} transactions against the source "
                        f"document's totals and confirm they're correct.",
                        key="bulk_confirm_clean",
                    )
                    if not bulk_confirm:
                        all_confirmed = False

                if flagged_rows:
                    st.markdown(
                        f"**{len(flagged_rows)} transaction(s) need individual review** "
                        f"(OCR-derived — amounts and/or dates aren't fully reliable):"
                    )

                for idx, r in enumerate(flagged_rows):

                    corr = st.session_state._evidence_corrections.get(idx, {})
                    needs_attention = r.get("needs_amount_confirmation") or r.get("needs_date_confirmation")

                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2, 2, 2])
                        with c1:
                            st.caption("Original (OCR/extraction) — never edited")
                            st.write(f"**{r.get('description', '')[:45]}**")
                            st.write(f"Date: `{r.get('date') or '⚠️ not detected'}`")
                            st.write(f"Amount: `₦{r['amount']:,.2f}`")
                        with c2:
                            st.caption("Your correction (if needed)")
                            corrected_date = st.text_input(
                                "Date (YYYY-MM-DD)", value=corr.get("date", r.get("date") or ""),
                                key=f"corr_date_{idx}",
                            )
                            corrected_amount = st.number_input(
                                "Amount (₦)", value=float(corr.get("amount", r["amount"])),
                                key=f"corr_amount_{idx}", step=1.0,
                            )
                        with c3:
                            st.caption("Reason for correction (if any)")
                            reason = st.selectbox(
                                "Reason", ["No correction needed", "OCR misread currency symbol",
                                           "OCR misread digit(s)", "Date not visible in source", "Other"],
                                key=f"corr_reason_{idx}",
                                index=1 if needs_attention else 0,
                            )
                            row_confirmed = st.checkbox("✓ Confirmed correct", key=f"corr_confirm_{idx}")

                        st.session_state._evidence_corrections[idx] = {
                            "date": corrected_date, "amount": corrected_amount, "reason": reason,
                        }
                        if not row_confirmed:
                            all_confirmed = False

                st.markdown("---")
                if st.button("📥 Add Confirmed Transactions to Today's Log", disabled=not all_confirmed):
                    added = 0
                    for r in clean_rows:
                        st.session_state.pos_today_transactions.append({
                            "amount": r["amount"],
                            "service_type": r["service_type"],
                            "is_emtl_qualifying": r.get("is_emtl_qualifying", False),
                        })
                        added += 1
                    for idx, r in enumerate(flagged_rows):
                        corr = st.session_state._evidence_corrections.get(idx, {})
                        st.session_state.pos_today_transactions.append({
                            "amount": corr.get("amount", r["amount"]),
                            "service_type": r["service_type"],
                            "is_emtl_qualifying": r.get("is_emtl_qualifying", False),
                        })
                        added += 1
                    # Store evidence metadata so Save Day can attach the
                    # correct evidence_id when writing to the ledger
                    source_format = result.get("raw_extraction", {}).get("source_format", "").strip().lower()
                    TYPE_MAP = {
                        "pdf": "pdf_statement",
                        "excel": "excel_export",
                        "xlsx": "excel_export",
                        "screenshot": "screenshot",
                        "image": "screenshot",
                        "manual": "manual_entry",
                    }
                    st.session_state._pending_evidence = {
                        "type": TYPE_MAP.get(source_format, "manual_entry"),
                        "file_bytes": evidence_bytes,
                        "file_name": evidence_file.name,
                        "extraction_result": result.get("raw_extraction") or result,
                        "confidence_score": vr.get("confidence_score", 0.8),
                        "is_validated": vr.get("is_valid", True),
                        "warnings": str(vr.get("warnings", [])),
                    }
                    st.success(f"Added {added} transaction(s) to today's log below.")
                    del st.session_state._evidence_cache_key  # force re-extraction if the same file is reused
                    st.rerun()

    st.markdown("---")
    def _get_bracket_charge(amount, service_type):
        """Returns the bracket-derived charge for (amount, service_type)
        using the exact same MerchantPricing methods the Financial Engine
        calls in transaction_profit(), or None if no configured bracket
        covers this amount. Reusing the real pricing object here (instead
        of re-deriving bracket coverage separately) means this check can
        never silently drift out of sync with what daily_pnl() would
        actually charge."""
        try:
            if service_type in ("withdrawal", "purchase"):
                return pricing.charge_for_cash_out(amount)
            elif service_type == "transfer_to_bank":
                return pricing.charge_for_transfer_to_bank(amount)
            elif service_type in ("airtime", "data", "bills_payment"):
                charge = pricing.charge_for_airtime_data_bills()
                return charge if charge > 0 else None
            elif service_type in ("pos_transfer", "pos_qr"):
                charge = pricing.charge_for_pos_transfers_qr()
                return charge if charge > 0 else None
        except ValueError:
            return None
        return None

    def add_manual_transaction(amount, service_type, custom_charge, is_emtl_qualifying):
        """Adds one manually-entered transaction to today's log. If the
        amount doesn't fall inside a bracket the operator actually
        configured, and no custom charge was supplied to cover it, this
        is flagged (out_of_bracket=True) and the transaction is ALSO
        appended to pos_out_of_bracket_transactions — a dedicated list
        surfaced separately below, so it's easy to review which
        transactions needed pricing outside the configured brackets,
        per the "Transactions outside these ranges? Use custom pricing"
        guidance shown above this form. Returns True if the transaction
        was out of bracket, else False."""
        bracket_charge = _get_bracket_charge(amount, service_type)
        out_of_bracket = bracket_charge is None and not custom_charge

        txn_entry = {
            "amount": amount,
            "service_type": service_type,
            "is_emtl_qualifying": is_emtl_qualifying,
            "out_of_bracket": out_of_bracket,
        }
        if custom_charge and custom_charge > 0:
            txn_entry["custom_charge"] = custom_charge

        st.session_state.pos_today_transactions.append(txn_entry)
        if out_of_bracket:
            st.session_state.pos_out_of_bracket_transactions.append(dict(txn_entry))
        return out_of_bracket

    st.markdown("##### Or Add a Transaction Manually")
    st.caption("💡 Leave custom charge empty to use bracket pricing. Set it only for amounts outside your configured ranges.")
    c1, c2, c3, c4, c5 = st.columns([2, 2, 1.5, 1.5, 1])
    with c1:
        txn_amount = st.number_input("Amount (₦)", min_value=0, step=500, key="txn_amount_input")
    with c2:
        txn_service = st.selectbox(
            "Service",
            ["withdrawal", "purchase", "pos_transfer", "pos_qr", "transfer_to_bank"],
            format_func=lambda s: s.replace("_", " ").title(),
            key="txn_service_input",
        )
    with c3:
        txn_custom_charge = st.number_input(
            "Custom charge (₦)", 
            min_value=0, 
            value=0,
            step=10, 
            key="txn_custom_charge_input",
            help="Override bracket pricing for this transaction. Leave as 0 to use configured brackets."
        )
    with c4:
        txn_emtl = st.checkbox("Stamp Duty", key="txn_emtl_input", help="Check if ≥₦10k bank transfer")
    with c5:
        st.markdown("&nbsp;")
        if st.button("➕ Add", use_container_width=True):
            if txn_amount > 0:
                was_out_of_bracket = add_manual_transaction(
                    txn_amount, txn_service, txn_custom_charge, txn_emtl
                )
                if was_out_of_bracket:
                    st.warning(
                        f"₦{txn_amount:,.0f} doesn't fall inside a configured "
                        f"{txn_service.replace('_', ' ')} bracket and no custom charge "
                        f"was set — added to today's log AND flagged in "
                        f"'Out-of-Bracket Transactions' below for review."
                    )
                st.rerun()
            else:
                st.warning("Enter an amount above ₦0 first.")

    if st.session_state.pos_today_transactions:
        st.markdown("##### Today's Transactions So Far")
        log_df = pd.DataFrame(st.session_state.pos_today_transactions)
        st.dataframe(log_df, use_container_width=True, hide_index=True)
        if st.button("🗑️ Clear today's log"):
            st.session_state.pos_today_transactions = []
            st.session_state.pos_out_of_bracket_transactions = []
            st.rerun()
    else:
        st.caption("No transactions added yet today.")

    if st.session_state.pos_out_of_bracket_transactions:
        st.markdown("##### ⚠️ Out-of-Bracket Transactions")
        st.caption(
            "These amounts didn't match any bracket you configured above and "
            "had no custom charge set — review and set a custom charge, or add "
            "a bracket that covers them."
        )
        oob_df = pd.DataFrame(st.session_state.pos_out_of_bracket_transactions)
        st.dataframe(oob_df, use_container_width=True, hide_index=True)

    st.markdown("##### Today's Expenses")
    e1, e2, e3, e4 = st.columns(4)
    with e1: opex_fuel = st.number_input("Fuel", value=0, step=100)
    with e2: opex_elec = st.number_input("Electricity", value=0, step=100)
    with e3: opex_data = st.number_input("Data", value=0, step=100)
    with e4: opex_other = st.number_input("Other", value=0, step=100)

    entry_date = st.date_input("Date for this entry", value=pd.Timestamp.now())

    if st.button("💾 Save Day & Compute", type="primary"):
        if not st.session_state.pos_today_transactions:
            st.warning("Add at least one transaction before saving the day.")
        else:
            txns = []
            for t in st.session_state.pos_today_transactions:
                txn = Transaction(
                    amount=t["amount"],
                    service_type=t["service_type"],
                    provider=pos_provider,
                    is_emtl_qualifying=t["is_emtl_qualifying"],
                    customer_charge=t.get("custom_charge"),  # Pass custom charge override if set
                )
                setattr(txn, "transaction_date", str(entry_date))
                txns.append(txn)
            opex = {"fuel": opex_fuel, "electricity": opex_elec, "data": opex_data, "other": opex_other}
            try:
                pnl = daily_pnl(txns, pricing, level=pos_level, opex=opex)

                # ── Write to database ─────────────────────────────────────────
                merchant_id = st.session_state.get("pos_merchant_id")
                if merchant_id:
                    db = get_session()
                    try:
                        # Step 1 — Evidence Repository
                        # Use file-upload evidence if the user added transactions
                        # from an uploaded statement; otherwise create a manual record.
                        pending_ev = st.session_state.pop("_pending_evidence", None)
                        if pending_ev:
                            evidence_record, is_duplicate = save_evidence(
                                db,
                                merchant_id=merchant_id,
                                evidence_type=pending_ev["type"],
                                file_bytes=pending_ev["file_bytes"],
                                file_path=pending_ev["file_name"],
                                extraction_result=pending_ev["extraction_result"],
                                confidence_score=pending_ev["confidence_score"],
                                is_validated=pending_ev["is_validated"],
                                validation_notes=pending_ev["warnings"],
                            )
                            if is_duplicate:
                                st.warning("⚠️ This statement has already been processed.")
                                st.stop()
                        else:
                            evidence_record, is_duplicate = save_evidence(
                                db,
                                merchant_id=merchant_id,
                                evidence_type="manual_entry",
                                file_bytes=None,
                                file_path=None,
                                extraction_result={
                                    "source": "manual_entry",
                                    "entry_date": str(entry_date),
                                    "transactions": [
                                        {"amount": t["amount"], "service_type": t["service_type"]}
                                        for t in st.session_state.pos_today_transactions
                                    ],
                                    "opex": opex,
                                },
                                confidence_score=1.0,
                                is_validated=True,
                                validation_notes="Manual entry — user confirmed at time of entry.",
                            )
                        evidence_id = evidence_record.id

                        # Step 2 — Ledger write with evidence_id
                        save_day_to_ledger(
                            db,
                            merchant_id=merchant_id,
                            pnl_result=pnl,
                            merchant_level=pos_level,
                            transaction_date=entry_date,
                            evidence_id=evidence_id,
                        )
                    except Exception as db_err:
                        st.warning(f"⚠️ Day computed but database write failed: {db_err}. "
                                   f"Results are shown below — download your history to avoid losing them.")
                        st.stop()  # do NOT fall through to the "Day saved" success message below -
                                   # the write demonstrably failed, so claiming success would be false
                    finally:
                        db.close()

                # ── Also update session state (for the in-session dashboard) ──
                new_rows = daily_pnl_to_transactions(pnl, date=entry_date)
                st.session_state.pos_all_rows.extend(new_rows)
                st.session_state.pos_today_transactions = []

                emtl_str = f" · Stamp Duty: ₦{pnl['emtl']:,.0f}" if pnl['emtl'] > 0 else ""
                success_msg = (
                    f"✅ Day saved. Revenue: ₦{pnl['revenue']:,.0f} · "
                    f"Provider fees: ₦{pnl['provider_fees']:,.0f}{emtl_str} · "
                    f"Net profit: ₦{pnl['net_profit']:,.0f}"
                )
                pending_info = pnl.get("pending") or {}
                pending_count = pending_info.get("count", 0)
                if pending_count > 0:
                    service_types = pending_info.get("service_types") or []
                    success_msg += (
                        f" · ⏳ {pending_count} transaction(s) pending pricing rule "
                        f"({', '.join(service_types)}) — stored but excluded from totals above."
                    )
                st.success(success_msg)

                # Show detailed transaction breakdown
                with st.expander("📊 Detailed Breakdown", expanded=False):
                    breakdown_data = []
                    for txn in pnl.get("transactions", []):
                        breakdown_data.append({
                            "Amount": f"₦{txn['amount']:,.0f}",
                            "Service": txn['service_type'],
                            "Your Charge": f"₦{txn['customer_charge']:,.0f}",
                            "Provider Fee": f"₦{txn['provider_fee']:,.0f}",
                            "Stamp Duty": f"₦{txn['emtl']:,.0f}" if txn['emtl'] > 0 else "—",
                            "Profit": f"₦{txn['profit']:,.0f}",
                        })
                    breakdown_df = pd.DataFrame(breakdown_data)
                    st.dataframe(breakdown_df, use_container_width=True, hide_index=True)
                    
                    # Show opex if any
                    if pnl['opex_breakdown']:
                        st.write("**Operating Expenses (Opex):**")
                        opex_data = [{"Category": k, "Amount": f"₦{v:,.0f}"} for k, v in pnl['opex_breakdown'].items() if v > 0]
                        if opex_data:
                            st.dataframe(pd.DataFrame(opex_data), use_container_width=True, hide_index=True)

                if pnl.get("caveats"):
                    with st.expander("⚠️ What this number does NOT yet include — read before trusting it"):
                        for c in pnl["caveats"]:
                            st.caption(f"• {c}")

                get_rule_confidence = getattr(pos_engine_providers, "get_rule_confidence", None)
                if callable(get_rule_confidence):
                    seen_service_types = {t["service_type"] for t in pnl.get("transactions", [])}
                    for st_type in seen_service_types:
                        try:
                            rc = get_rule_confidence(pos_provider, pos_level, st_type)
                            if rc.get("level") in ("provisional", "unverified"):
                                st.warning(
                                    f"⚠️ **{st_type}: {rc.get('label', 'Rule confidence is low.')}** "
                                    f"(source: {rc.get('source', 'unknown')})"
                                )
                        except Exception:
                            pass

            except ValueError as e:
                st.error(f"❌ Couldn't compute this day: {e}")

    st.stop()

# ─── Load Data ───────────────────────────────────────────────────────────────
SAMPLE_DATA_PATH = Path(__file__).parent / "data" / "sample_data.xlsx"

@st.cache_data
def get_data(source_id: str, file_bytes: bytes | None = None):
    source = BytesIO(file_bytes) if file_bytes is not None else source_id
    df = load_data(source)
    if df is not None:
        df = clean_data(df)
    return df


def load_pos_history_from_db(merchant_id: int) -> pd.DataFrame:
    """Loads the merchant's full ledger history from DailyFinancial rows
    and converts it into the Date/Description/Category/Type/Amount schema
    that FinanceAnalytics expects — so the existing analytics, charts,
    copilot, forecasting, and report pipeline work on persisted data with
    zero changes downstream. Routes through load_data/clean_data so
    Month/MonthLabel columns are added exactly as for any other data source."""
    db = get_session()
    try:
        rows = get_ledger_for_merchant(db, merchant_id)
        if not rows:
            return None
        records = []
        for row in rows:
            dt = pd.Timestamp(row.date)
            records.append({"Date": dt, "Description": "Revenue", "Category": "POS Income",
                             "Type": "Revenue", "Amount": row.revenue})
            if row.provider_fees > 0:
                records.append({"Date": dt, "Description": "Provider Fees", "Category": "Provider Charges",
                                 "Type": "Expense", "Amount": row.provider_fees})
            if row.emtl_total > 0:
                records.append({"Date": dt, "Description": "Stamp Duty", "Category": "Government Levy",
                                 "Type": "Expense", "Amount": row.emtl_total})
            opex = row.opex_breakdown or {}
            for category, amount in opex.items():
                if amount and amount > 0:
                    records.append({"Date": dt, "Description": category.title(),
                                     "Category": category.title(), "Type": "Expense", "Amount": amount})
        raw_df = pd.DataFrame(records)
        buf = BytesIO()
        raw_df.to_excel(buf, index=False)
        buf.seek(0)
        df = load_data(buf)
        if df is not None:
            df = clean_data(df)
        return df
    finally:
        db.close()

if business_type == "POS Agent":
    merchant_id = st.session_state.get("pos_merchant_id")
    if merchant_id:
        df = load_pos_history_from_db(merchant_id)
        # If the database has history, optionally blend in today's
        # unsaved session-state rows so the dashboard shows the
        # current day's work even before it's been saved.
        if df is None or df.empty:
            # Nothing in DB yet — fall back to session state only
            if st.session_state.pos_all_rows:
                raw_df = pd.DataFrame(st.session_state.pos_all_rows)
                buf = BytesIO()
                raw_df.to_excel(buf, index=False)
                buf.seek(0)
                df = load_data(buf)
                if df is not None:
                    df = clean_data(df)
            else:
                df = None
    else:
        df = None
elif uploaded_file:
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
    if business_type == "POS Agent":
        merchant_id = st.session_state.get("pos_merchant_id")
        if merchant_id:
            st.warning("⚠️ No days saved yet for this merchant. Go to **🧾 POS Daily Entry** and save your first day.")
        else:
            st.warning("⚠️ Enter your Business Name in the sidebar to get started.")
    else:
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

    if forecast_df.empty:
        st.markdown(insight_box(
            'info',
            "📅 Not enough history to forecast yet — at least 2 complete months of data are needed. "
            "Keep recording days/months and the forecast will appear once there's enough history.",
        ), unsafe_allow_html=True)
    else:
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