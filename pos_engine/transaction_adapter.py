"""
POS-to-SME Schema Adapter
===========================
Converts a pos_engine.financial_engine.daily_pnl() result into rows matching
the existing SME dashboard's schema (Date, Description, Category, Type,
Amount). This is the integration point that lets the entire existing
analytics/charts/copilot/forecasting/reports pipeline work on POS data
without modification — exactly the "shared analytics framework across
industry engines" from the original architecture vision.

One day's P&L becomes:
- One Revenue row per transaction (the customer charge — NOT the
  transaction's face value, since that's not the merchant's income)
- One Expense row per transaction's provider fee, where non-zero
- One Expense row per transaction's EMTL, where non-zero
- One Expense row per opex category, where non-zero

This is intentionally granular (multiple rows per transaction) rather than
collapsed into daily totals, because the existing analytics layer expects
transaction-level rows and several of its features (category breakdowns,
revenue concentration) depend on having more than one row to analyze.
"""

import pandas as pd

_SERVICE_CATEGORY_LABELS = {
    "withdrawal": "Withdrawal Fees",
    "purchase": "Purchase Fees",
    "pos_transfer": "Transfer Fees",
    "pos_qr": "QR Payment Fees",
    "transfer_to_bank": "Bank Transfer Fees",
}


def _service_category(service_type: str) -> str:
    return _SERVICE_CATEGORY_LABELS.get(service_type, service_type.replace("_", " ").title())


def daily_pnl_to_transactions(pnl_result: dict, date) -> list:
    """Returns a list of dicts, one per row, ready to build a DataFrame
    matching data_loader's REQUIRED_COLUMNS schema."""
    date = pd.Timestamp(date)
    rows = []

    for i, txn in enumerate(pnl_result["transactions"], start=1):
        service_label = txn["service_type"].replace("_", " ").title()

        rows.append({
            "Date": date,
            "Description": f"{service_label} #{i}",
            "Category": _service_category(txn["service_type"]),
            "Type": "Revenue",
            "Amount": txn["customer_charge"],
        })

        if txn["provider_fee"] > 0:
            rows.append({
                "Date": date,
                "Description": f"{txn['provider']} fee — {service_label} #{i}",
                "Category": "Provider Charges",
                "Type": "Expense",
                "Amount": txn["provider_fee"],
            })

        if txn["emtl"] > 0:
            rows.append({
                "Date": date,
                "Description": f"EMTL — {service_label} #{i}",
                "Category": "Government Levy",
                "Type": "Expense",
                "Amount": txn["emtl"],
            })

    for opex_category, amount in pnl_result.get("opex_breakdown", {}).items():
        if amount > 0:
            rows.append({
                "Date": date,
                "Description": opex_category.replace("_", " ").title(),
                "Category": opex_category.replace("_", " ").title(),
                "Type": "Expense",
                "Amount": amount,
            })

    return rows
