"""
Evidence Validation Layer
============================
Validates extracted transactions before they reach the Financial Engine.
Updated to handle real parser output: screenshot-derived transactions can
have a None date (confirmed missing from real Moniepoint screenshots) and
carry needs_amount_confirmation / needs_date_confirmation flags that force
manual review rather than silent auto-acceptance.
"""
from typing import List, Dict, Tuple
from datetime import datetime


class EvidenceValidator:
    MIN_CONFIDENCE_SCORE = 0.7  # below this, require manual review
    MAX_REASONABLE_AMOUNT = 1_000_000
    MIN_REASONABLE_AMOUNT = 10
    MAX_DAYS_AGO = 365

    def __init__(self, provider: str = "OPay"):
        self.provider = provider

    def validate(self, extraction_result: Dict) -> Dict:
        if not extraction_result.get("success"):
            return {
                "is_valid": False,
                "confidence_score": 0.0,
                "transactions": [],
                "warnings": [],
                "errors": extraction_result.get("errors", ["Extraction failed"]),
                "requires_manual_review": True,
            }

        transactions = extraction_result.get("transactions", [])
        extraction_confidence = extraction_result.get("confidence_score", 0.0)

        validated_transactions = []
        warnings = list(extraction_result.get("errors", []))  # carry forward parser-level
                                                                  # caveats (e.g. the OCR
                                                                  # amount-corruption warning)
        errors = []

        for i, txn in enumerate(transactions, 1):
            is_valid, txn_warnings, txn_errors = self._validate_transaction(txn, i)
            if is_valid:
                validated_transactions.append(txn)
            else:
                errors.extend(txn_errors)
            warnings.extend(txn_warnings)

        validation_confidence = len(validated_transactions) / len(transactions) if transactions else 0.0
        overall_confidence = (extraction_confidence + validation_confidence) / 2

        needs_manual_data = any(
            t.get("needs_date_confirmation") or t.get("needs_amount_confirmation")
            for t in validated_transactions
        )
        requires_review = (
            overall_confidence < self.MIN_CONFIDENCE_SCORE
            or len(errors) > 0
            or needs_manual_data
        )

        return {
            "is_valid": len(validated_transactions) > 0,
            "confidence_score": round(overall_confidence, 2),
            "transactions": validated_transactions,
            "warnings": warnings,
            "errors": errors,
            "requires_manual_review": requires_review,
            "summary": {
                "total_extracted": len(transactions),
                "valid": len(validated_transactions),
                "invalid": len(transactions) - len(validated_transactions),
            },
        }

    def _validate_transaction(self, txn: Dict, index: int) -> Tuple[bool, List[str], List[str]]:
        warnings = []
        errors = []

        if txn.get("date") is None:
            if txn.get("needs_date_confirmation"):
                warnings.append(f"Transaction #{index}: date needs manual confirmation (not visible in source).")
            else:
                errors.append(f"Transaction #{index}: missing date")
                return False, warnings, errors

        if not txn.get("amount"):
            errors.append(f"Transaction #{index}: missing amount")
            return False, warnings, errors

        if not txn.get("service_type"):
            errors.append(f"Transaction #{index}: missing service type")
            return False, warnings, errors

        amount = txn["amount"]
        if amount < self.MIN_REASONABLE_AMOUNT:
            warnings.append(f"Transaction #{index}: unusually small amount (₦{amount:,.0f})")
        if amount > self.MAX_REASONABLE_AMOUNT:
            warnings.append(f"Transaction #{index}: unusually large amount (₦{amount:,.0f}) — please verify")

        if txn.get("date") is not None:
            date_str = txn["date"]
            try:
                # Dates may be full (YYYY-MM-DD) or month-day-only (MM-DD,
                # from screenshots missing a year) — only range-check full dates.
                if len(date_str) == 10:
                    txn_date = datetime.strptime(date_str, "%Y-%m-%d")
                    days_ago = (datetime.now() - txn_date).days
                    if days_ago > self.MAX_DAYS_AGO:
                        warnings.append(f"Transaction #{index}: date is more than {self.MAX_DAYS_AGO} days old")
                    if days_ago < 0:
                        errors.append(f"Transaction #{index}: date is in the future")
                        return False, warnings, errors
            except ValueError:
                errors.append(f"Transaction #{index}: invalid date format")
                return False, warnings, errors

        valid_service_types = {
            "withdrawal", "deposit", "transfer_to_bank", "pos_transfer",
            "pos_qr", "airtime", "data", "bills_payment", "purchase", "levy",
        }
        if txn["service_type"] not in valid_service_types:
            warnings.append(f"Transaction #{index}: unknown service type '{txn['service_type']}' — defaulting to 'withdrawal'")
            txn["service_type"] = "withdrawal"

        return True, warnings, errors
