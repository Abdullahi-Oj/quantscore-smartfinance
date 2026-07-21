"""
OPay Provider Configuration (Phase 6 / Level 3 — pure data, no logic)
=======================================================================
This file contains ONLY configuration data. The universal rule that
evaluates it lives in pos_engine/rules.py and has no knowledge that this
data even belongs to OPay.

VERIFIED (see project history): this bracket table does NOT reduce to a
clean percentage formula. Tested both upper- and lower-bound percentage
calculations against every bracket value below — neither matches. This is
a genuine flat-fee-per-bracket schedule transcribed from a provider rate
card, not something safe to approximate with min(amount*rate, cap).

STILL NEEDS VERIFICATION before production use:
- These exact figures should be checked against a real OPay settlement
  statement, not just trusted from the original transcription.
- How OPay Rewards Levels cashback (Rising/Super/Mega Star, a SEPARATE
  weekly-volume-based program) combines with these Merchant Level fees is
  not resolved here — see the docstring in financial_engine.py.
"""

VALID_LEVELS = ("Platinum", "Gold", "Regular")

# Withdrawal / Purchase / POS Transfer Number / POS QR Code all share this
# same fee schedule per level, per the original rate card.
_WITHDRAWAL_SCHEDULES = {
    "Platinum": [
        {"min": 1, "max": 3000, "type": "percentage", "rate": 0.0043, "cap": 85.00},
        {"min": 3001, "max": 4000, "type": "flat", "value": 17.00},
        {"min": 4001, "max": 5000, "type": "flat", "value": 21.25},
        {"min": 5001, "max": 6000, "type": "flat", "value": 25.55},
        {"min": 6001, "max": 7000, "type": "flat", "value": 29.75},
        {"min": 7001, "max": 8000, "type": "flat", "value": 34.00},
        {"min": 8001, "max": 9000, "type": "flat", "value": 38.25},
        {"min": 9001, "max": 10000, "type": "flat", "value": 42.25},
        {"min": 10001, "max": 11000, "type": "flat", "value": 46.75},
        {"min": 11001, "max": 12000, "type": "flat", "value": 51.00},
        {"min": 12001, "max": 13000, "type": "flat", "value": 55.25},
        {"min": 13001, "max": 14000, "type": "flat", "value": 59.50},
        {"min": 14001, "max": 15000, "type": "flat", "value": 63.75},
        {"min": 15001, "max": 16000, "type": "flat", "value": 68.00},
        {"min": 16001, "max": 17000, "type": "flat", "value": 72.25},
        {"min": 17001, "max": 18000, "type": "flat", "value": 76.50},
        {"min": 18001, "max": 19000, "type": "flat", "value": 80.75},
        {"min": 19001, "max": None, "type": "flat", "value": 85.00},  # open-ended cap
    ],
    "Gold": [
        {"min": 1, "max": 3000, "type": "percentage", "rate": 0.0045, "cap": 90.00},
        {"min": 3001, "max": 4000, "type": "flat", "value": 18.00},
        {"min": 4001, "max": 5000, "type": "flat", "value": 22.50},
        {"min": 5001, "max": 6000, "type": "flat", "value": 27.00},
        {"min": 6001, "max": 7000, "type": "flat", "value": 31.50},
        {"min": 7001, "max": 8000, "type": "flat", "value": 36.00},
        {"min": 8001, "max": 9000, "type": "flat", "value": 40.50},
        {"min": 9001, "max": 10000, "type": "flat", "value": 45.00},
        {"min": 10001, "max": 11000, "type": "flat", "value": 49.50},
        {"min": 11001, "max": 12000, "type": "flat", "value": 54.00},
        {"min": 12001, "max": 13000, "type": "flat", "value": 58.50},
        {"min": 13001, "max": 14000, "type": "flat", "value": 63.00},
        {"min": 14001, "max": 15000, "type": "flat", "value": 67.50},
        {"min": 15001, "max": 16000, "type": "flat", "value": 72.00},
        {"min": 16001, "max": 17000, "type": "flat", "value": 76.50},
        {"min": 17001, "max": 18000, "type": "flat", "value": 81.00},
        {"min": 18001, "max": 19000, "type": "flat", "value": 85.50},
        {"min": 19001, "max": None, "type": "flat", "value": 90.00},
    ],
    "Regular": [
        {"min": 1, "max": 3000, "type": "percentage", "rate": 0.005, "cap": 100.00},
        {"min": 3001, "max": 4000, "type": "flat", "value": 20.00},
        {"min": 4001, "max": 5000, "type": "flat", "value": 25.00},
        {"min": 5001, "max": 6000, "type": "flat", "value": 30.00},
        {"min": 6001, "max": 7000, "type": "flat", "value": 35.00},
        {"min": 7001, "max": 8000, "type": "flat", "value": 40.00},
        {"min": 8001, "max": 9000, "type": "flat", "value": 45.00},
        {"min": 9001, "max": 10000, "type": "flat", "value": 50.00},
        {"min": 10001, "max": 11000, "type": "flat", "value": 55.00},
        {"min": 11001, "max": 12000, "type": "flat", "value": 60.00},
        {"min": 12001, "max": 13000, "type": "flat", "value": 65.00},
        {"min": 13001, "max": 14000, "type": "flat", "value": 70.00},
        {"min": 14001, "max": 15000, "type": "flat", "value": 75.00},
        {"min": 15001, "max": 16000, "type": "flat", "value": 80.00},
        {"min": 16001, "max": 17000, "type": "flat", "value": 85.00},
        {"min": 17001, "max": 18000, "type": "flat", "value": 90.00},
        {"min": 18001, "max": 19000, "type": "flat", "value": 95.00},
        {"min": 19001, "max": None, "type": "flat", "value": 100.00},
    ],
}

# Transfer to Bank — flat fee regardless of amount. Expressed as a
# single open-ended bracket so it goes through the exact same generic
# rule as everything else, rather than needing a special case.
_TRANSFER_TO_BANK_SCHEDULES = {
    "Platinum": [{"min": 1, "max": None, "type": "flat", "value": 14.00}],
    "Gold": [{"min": 1, "max": None, "type": "flat", "value": 18.00}],
    "Regular": [{"min": 1, "max": None, "type": "flat", "value": 20.00}],
}

_SERVICE_SCHEDULES = {
    "withdrawal": _WITHDRAWAL_SCHEDULES,
    "purchase": _WITHDRAWAL_SCHEDULES,
    "pos_transfer": _WITHDRAWAL_SCHEDULES,
    "pos_qr": _WITHDRAWAL_SCHEDULES,
    "transfer_to_bank": _TRANSFER_TO_BANK_SCHEDULES,
}


def get_fee_schedule(level: str, service_type: str) -> list:
    """The only function in this file — a pure lookup, no calculation.
    Returns the bracket list for rules.calculate_provider_fee() to evaluate."""
    if level not in VALID_LEVELS:
        raise ValueError(f"Unknown OPay merchant level '{level}'. Must be one of {VALID_LEVELS}.")
    if service_type not in _SERVICE_SCHEDULES:
        raise ValueError(
            f"OPay has no configured schedule for service_type '{service_type}'. "
            f"Known service types: {list(_SERVICE_SCHEDULES.keys())}."
        )
    return _SERVICE_SCHEDULES[service_type][level]
