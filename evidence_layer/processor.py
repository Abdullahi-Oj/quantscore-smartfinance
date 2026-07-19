"""
Evidence Processor
====================
Orchestrates extraction -> validation -> conversion to Transaction
objects, ready for pos_engine.financial_engine.daily_pnl().

IMPORTANT: per project decision, this engine recomputes provider fees
and EMTL/Stamp Duty from the rate-table model rather than using observed
values from evidence. Observed levy lines (is_levy_line=True) are
therefore EXCLUDED here when building Transaction objects — including
them would double-count the levy (once as its own line, once again via
rules.calculate_emtl on whichever transaction is later marked
is_emtl_qualifying). The real per-transaction `amount` from evidence
becomes the Transaction's amount, which the rate table then re-prices —
this is the explicit tradeoff already discussed: real revenue volume,
recomputed fee.
"""
from typing import List, Dict
from .extractor import EvidenceExtractor
from .validators import EvidenceValidator
from pos_engine.financial_engine import Transaction


class EvidenceProcessor:
    def __init__(self, provider: str = "OPay"):
        self.provider = provider
        self.validator = EvidenceValidator(provider)

    def process_file(self, file_path: str) -> Dict:
        extractor = EvidenceExtractor(file_path, provider=self.provider)
        raw_extraction = extractor.extract()

        if not raw_extraction.get("success"):
            return {
                "success": False,
                "transactions": [],
                "validation_result": None,
                "raw_extraction": raw_extraction,
            }

        validation_result = self.validator.validate(raw_extraction)
        print("=" * 60)
        print("Validation Result:")
        for key, value in validation_result.items():
            print(f"  {key}: {value}")
        print("=" * 60)

        if not validation_result["is_valid"]:
            return {
                "success": False,
                "transactions": [],
                "validation_result": validation_result,
                "raw_extraction": raw_extraction,
            }

        transactions = self._convert_to_transactions(validation_result["transactions"])

        return {
            "success": True,
            "transactions": transactions,
            "validation_result": validation_result,
            "raw_extraction": raw_extraction,
        }

    def _convert_to_transactions(self, validated_data: List[Dict]) -> List[Transaction]:
        transactions = []
        for txn_data in validated_data:
            if txn_data.get("is_levy_line"):
                continue  # see module docstring — avoid double-counting the levy
            txn = Transaction(
                amount=txn_data["amount"],
                service_type=txn_data["service_type"],
                provider=self.provider,
                is_emtl_qualifying=txn_data.get("is_emtl_qualifying", False),
            )
            if txn_data.get("raw_observed_charge") is not None:
                setattr(txn, "observed_provider_fee", txn_data["raw_observed_charge"])
            transactions.append(txn)
        return transactions
