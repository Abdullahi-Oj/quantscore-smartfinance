"""
POS Daily Financial Engine
Calculates profit for POS transactions.
"""
from dataclasses import dataclass
from typing import Optional
from . import rules
from . import providers

DEFAULT_EMTL_AMOUNT = 50.00
DEFAULT_EMTL_THRESHOLD = 10_000.00

# Service types mapped to cash flow direction
CASH_OUT_SERVICES = {"withdrawal"}
CASH_IN_SERVICES = {"deposit", "transfer_to_bank", "pos_transfer", "pos_qr", "airtime", "data", "bills_payment"}


@dataclass
class MerchantPricing:
    """What the merchant charges customers. Separate pricing for different service types."""
    cash_out_brackets: list  # list of (low, high, charge) for withdrawals
    transfer_to_bank_brackets: list  # list of (low, high, charge) for bank transfers
    airtime_data_bills_bracket: tuple  # (charge) flat fee for airtime/data/bills_payment
    pos_transfers_qr_bracket: tuple  # (charge) flat fee for POS transfers/QR

    def charge_for_cash_out(self, amount: float) -> float:
        return self._find_bracket(self.cash_out_brackets, amount)

    def charge_for_transfer_to_bank(self, amount: float) -> float:
        return self._find_bracket(self.transfer_to_bank_brackets, amount)
    
    def charge_for_airtime_data_bills(self) -> float:
        """Flat fee for airtime/data/bills_payment."""
        return self.airtime_data_bills_bracket[0] if self.airtime_data_bills_bracket else 0.0
    
    def charge_for_pos_transfers_qr(self) -> float:
        """Flat fee for POS transfers/QR."""
        return self.pos_transfers_qr_bracket[0] if self.pos_transfers_qr_bracket else 0.0

    def _find_bracket(self, brackets: list, amount: float) -> float:
        for low, high, charge in brackets:
            if low <= amount <= high:
                return charge
        raise ValueError(f"No pricing for amount {amount}. Check your pricing setup.")


@dataclass
class Transaction:
    amount: float
    service_type: str
    provider: str = "OPay"
    is_emtl_qualifying: bool = False
    observed_provider_fee: Optional[float] = None
    calculated_provider_fee: Optional[float] = None
    customer_charge: Optional[float] = None  # Override bracket pricing if set (for manual entries)


def transaction_profit(txn: Transaction, pricing: MerchantPricing, level: str,
                       emtl_amount: float = DEFAULT_EMTL_AMOUNT,
                       emtl_threshold: float = DEFAULT_EMTL_THRESHOLD) -> dict:
    """Calculate profit for a single transaction."""
    # 1. Customer charge: use override if provided, otherwise lookup by service type
    if txn.customer_charge is not None:
        customer_charge = txn.customer_charge
    elif txn.service_type in ("withdrawal", "purchase"):
        # "purchase" is priced identically to "withdrawal" here because both
        # providers/opay.py and providers/moniepoint.py already key it to the
        # same fee schedule on the provider_fee side (_WITHDRAWAL_SCHEDULES).
        customer_charge = pricing.charge_for_cash_out(txn.amount)
    elif txn.service_type == "transfer_to_bank":
        customer_charge = pricing.charge_for_transfer_to_bank(txn.amount)
    elif txn.service_type in ("airtime", "data", "bills_payment"):
        customer_charge = pricing.charge_for_airtime_data_bills()
    elif txn.service_type in ("pos_transfer", "pos_qr"):
        customer_charge = pricing.charge_for_pos_transfers_qr()
    else:
        raise ValueError(f"Unknown service type: {txn.service_type}")

    # 2. Provider fee from database. Airtime/data/bills_payment have no
    # provider fee schedule anywhere (providers/opay.py, providers/
    # moniepoint.py, and the seeded database all correctly omit them) -
    # providers don't charge merchants a per-transaction fee for these,
    # unlike withdrawal/transfer/pos_transfer. Looking one up for them
    # was always going to fail; skip the lookup entirely instead.
    if txn.service_type in ("airtime", "data", "bills_payment"):
        provider_fee = 0.0
    else:
        fee_schedule = providers.get_fee_schedule(txn.provider, level, txn.service_type)
        provider_fee = rules.calculate_provider_fee(txn.amount, fee_schedule)

    # 3. EMTL and profit
    emtl = rules.calculate_emtl(txn.amount, txn.is_emtl_qualifying, emtl_threshold, emtl_amount)
    profit = rules.calculate_transaction_profit(customer_charge, provider_fee, emtl)

    return {
        "amount": txn.amount,
        "service_type": txn.service_type,
        "provider": txn.provider,
        "customer_charge": round(customer_charge, 2),
        "provider_fee": round(provider_fee, 2),
        "emtl": round(emtl, 2),
        "profit": profit,
    }


def daily_pnl(transactions: list, pricing: MerchantPricing, level: str,
              opex: Optional[dict] = None,
              emtl_amount: float = DEFAULT_EMTL_AMOUNT,
              emtl_threshold: float = DEFAULT_EMTL_THRESHOLD) -> dict:
    """Calculate full day P&L."""
    opex = opex or {}
    breakdown = [transaction_profit(t, pricing, level, emtl_amount, emtl_threshold) for t in transactions]

    total_revenue = sum(b["customer_charge"] for b in breakdown)
    total_provider_fees = sum(b["provider_fee"] for b in breakdown)
    total_emtl = sum(b["emtl"] for b in breakdown)
    total_opex = sum(opex.values())
    gross_profit = total_revenue - total_provider_fees - total_emtl
    net_profit = gross_profit - total_opex

    return {
        "transaction_count": len(transactions),
        "revenue": round(total_revenue, 2),
        "provider_fees": round(total_provider_fees, 2),
        "emtl": round(total_emtl, 2),
        "gross_profit": round(gross_profit, 2),
        "opex_total": round(total_opex, 2),
        "opex_breakdown": dict(opex),
        "net_profit": round(net_profit, 2),
        "transactions": breakdown,
        "caveats": [
            "Excludes OPay Rewards Levels cashback (not yet modeled).",
        ],
    }