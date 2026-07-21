"""
Ledger Repository
====================
The write path from pos_engine.financial_engine.daily_pnl() output into
the database, implementing the architecture:

    Evidence Repository → Financial Engine → Transactions → Ledger → Engine Log

One call (save_day_to_ledger) does all three writes in one transaction:
- One TransactionRecord per transaction (with audit-mode and versioning fields)
- One DailyFinancial row (the ledger the dashboard reads from)
- One EngineLog row per transaction (frozen snapshot for dispute resolution)

Rule versions are read from each transaction's own result dict, not
hardcoded here — so if a historical day is re-processed, the version
stored will be the one that was actually active on the transaction's date.
"""
from datetime import date as date_type, datetime as datetime_type
from typing import Optional
from sqlalchemy.orm import Session

from .models import TransactionRecord, DailyFinancial, EngineLog


def _to_date(val, fallback: date_type) -> date_type:
    """Normalise to datetime.date. SQLite's Date column rejects strings
    and datetime objects, so we coerce everything here rather than
    adding checks everywhere upstream."""
    if val is None:
        return fallback
    if isinstance(val, datetime_type):
        return val.date()
    if isinstance(val, date_type):
        return val
    if isinstance(val, str):
        try:
            return date_type.fromisoformat(val[:10])
        except ValueError:
            return fallback
    return fallback


def save_day_to_ledger(
    db: Session,
    merchant_id: int,
    pnl_result: dict,
    merchant_level: str,
    transaction_date: date_type,
    evidence_id: Optional[int] = None,
) -> DailyFinancial:
    """Writes one day's daily_pnl() output to the database atomically.
    Returns the DailyFinancial (ledger) row. Raises on any failure."""

    transaction_date = _to_date(transaction_date, date_type.today())

    try:
        if evidence_id is not None:
            old_records = db.query(TransactionRecord).filter(
                TransactionRecord.evidence_id == evidence_id
            ).all()
            old_ids = [r.id for r in old_records]
            if old_ids:
                db.query(EngineLog).filter(EngineLog.transaction_id.in_(old_ids)).delete(synchronize_session=False)
                db.query(TransactionRecord).filter(TransactionRecord.id.in_(old_ids)).delete(synchronize_session=False)

        saved_transactions = []
        for txn in pnl_result["transactions"]:
            rule_conf = txn.get("rule_confidence") or {}
            is_pending = txn.get("status") == "pending_pricing_rule"
            record = TransactionRecord(
                merchant_id=merchant_id,
                evidence_id=evidence_id,
                transaction_date=_to_date(txn.get("transaction_date"), transaction_date),
                transaction_type=txn["service_type"],
                amount=txn["amount"],
                provider=txn["provider"],
                merchant_level=merchant_level,
                customer_charge=txn["customer_charge"],
                # pending rows: store 0.0 to satisfy NOT NULL, but mark status
                # via rule_confidence_level="pending" so it's never mistaken for
                # a genuinely zero-fee calculated row.
                provider_fee=txn.get("provider_fee") or 0.0,
                emtl=txn.get("emtl") or 0.0,
                profit=txn.get("profit") or 0.0,
                is_emtl_qualifying=bool((txn.get("emtl") or 0) > 0),
                is_reconciled=False,
                observed_provider_fee=txn.get("observed_provider_fee"),
                calculated_provider_fee=txn.get("calculated_provider_fee"),
                pricing_difference=txn.get("pricing_difference"),
                pricing_alert=txn.get("pricing_alert", False),
                rule_version=txn.get("rule_version", "unknown"),
                rule_confidence_level="pending" if is_pending else rule_conf.get("level"),
            )
            db.add(record)
            saved_transactions.append((record, txn))

        db.flush()  # assigns record.id for each row without committing yet

        for record, txn in saved_transactions:
            if txn.get("status") == "pending_pricing_rule":
                continue  # no engine log for unresolved transactions —
                           # there's nothing to explain yet
            rule_conf = txn.get("rule_confidence") or {}
            db.add(EngineLog(
                transaction_id=record.id,
                provider=txn["provider"],
                rule_version=txn.get("rule_version", "unknown"),
                customer_charge=txn["customer_charge"],
                calculated_provider_fee=txn.get("calculated_provider_fee", 0.0),
                observed_provider_fee=txn.get("observed_provider_fee"),
                emtl=txn.get("emtl", 0.0),
                net_profit=txn.get("profit", 0.0),
                rule_confidence_level=rule_conf.get("level"),
            ))

        # Upsert daily_financial: check if a record exists for this merchant+date
        ledger_row = db.query(DailyFinancial).filter(
            DailyFinancial.merchant_id == merchant_id,
            DailyFinancial.date == transaction_date
        ).first()
        
        if ledger_row:
            # Update existing record
            ledger_row.transaction_count = pnl_result["transaction_count"]
            ledger_row.revenue = pnl_result["revenue"]
            ledger_row.provider_fees = pnl_result["provider_fees"]
            ledger_row.emtl_total = pnl_result["emtl"]
            ledger_row.gross_profit = pnl_result["gross_profit"]
            ledger_row.opex_total = pnl_result["opex_total"]
            ledger_row.opex_breakdown = pnl_result["opex_breakdown"]
            ledger_row.net_profit = pnl_result["net_profit"]
            ledger_row.updated_at = datetime_type.utcnow()
        else:
            # Create new record
            ledger_row = DailyFinancial(
                merchant_id=merchant_id,
                date=transaction_date,
                transaction_count=pnl_result["transaction_count"],
                revenue=pnl_result["revenue"],
                provider_fees=pnl_result["provider_fees"],
                emtl_total=pnl_result["emtl"],
                gross_profit=pnl_result["gross_profit"],
                opex_total=pnl_result["opex_total"],
                opex_breakdown=pnl_result["opex_breakdown"],
                net_profit=pnl_result["net_profit"],
            )
            db.add(ledger_row)
        
        db.commit()
        db.refresh(ledger_row)
        return ledger_row

    except Exception:
        db.rollback()
        raise


def get_ledger_for_merchant(db: Session, merchant_id: int,
                             start_date=None, end_date=None):
    """Reads from DailyFinancial (the ledger), not raw transactions.
    This is what the dashboard reads."""
    query = (db.query(DailyFinancial)
               .filter(DailyFinancial.merchant_id == merchant_id))
    if start_date:
        query = query.filter(DailyFinancial.date >= start_date)
    if end_date:
        query = query.filter(DailyFinancial.date <= end_date)
    return query.order_by(DailyFinancial.date).all()