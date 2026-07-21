"""
Moniepoint Provider Configuration (Phase 6 / Level 3 — pure data, no logic)
==============================================================================
STATUS: PROVISIONAL — derived from a single real statement's observed
(amount, charge) pairs, NOT an official rate card. Unlike OPay's
providers/opay.py (transcribed from a documented rate card and verified
against every bracket), this schedule is built from only 13 distinct
amounts actually seen in one merchant's real Moniepoint export.

Tried first: a clean percentage formula (amount * rate, capped). It does
NOT fit — observed ratios range from 0.40% to 0.65% with no consistent
cap point, so this is genuinely bracket-based, similar in shape to OPay's
schedule, but the bracket BOUNDARIES here are inferred from sparse data
points, not read off a real published table. Treat any fee calculated
for an amount that wasn't one of the originally-observed values with
real caution — this is filling gaps between known points, not a
confirmed schedule.

DO NOT extend the "known good" confidence of OPay's schedule to this one.
This exists so audit mode is functional rather than silent for
Moniepoint, not because the underlying pricing model has been verified.
Replace this with a real Moniepoint rate card as soon as one is available.
"""

VALID_LEVELS = ("Standard",)  # Moniepoint's tiering isn't documented yet —
                                # everything maps to one tier until that's known.

# Bracket boundaries are the midpoints between consecutive OBSERVED amounts,
# with the OBSERVED charge held flat across that inferred bracket — the
# same flat-fee-per-bracket shape OPay uses, applied to far fewer real
# data points. Anything above the highest observed bracket with a non-flat
# charge (>50,400) reuses the ₦100 cap, consistent with the apparent
# capping behavior already visible in the observed data.
_WITHDRAWAL_SCHEDULE_STANDARD = [
    {"min": 1, "max": 2550, "type": "flat", "value": 10.00},      # observed: 2,000 -> 10
    {"min": 2551, "max": 3550, "type": "flat", "value": 20.00},   # observed: 3,100 -> 20
    {"min": 3551, "max": 4500, "type": "flat", "value": 20.00},   # observed: 4,000 -> 20
    {"min": 4501, "max": 5050, "type": "flat", "value": 25.00},   # observed: 5,000 -> 25
    {"min": 5051, "max": 5550, "type": "flat", "value": 30.00},   # observed: 5,100 -> 30
    {"min": 5551, "max": 8100, "type": "flat", "value": 30.00},   # observed: 6,000 -> 30
    {"min": 8101, "max": 12600, "type": "flat", "value": 55.00},  # observed: 10,200 -> 55
    {"min": 12601, "max": 15100, "type": "flat", "value": 75.00}, # observed: 15,000 -> 75
    {"min": 15101, "max": 17750, "type": "flat", "value": 80.00}, # observed: 15,200 -> 80
    {"min": 17751, "max": None, "type": "flat", "value": 100.00}, # observed: 20,300+ -> 100 (apparent cap)
]

_TRANSFER_TO_BANK_SCHEDULE_STANDARD = [
    {"min": 1, "max": None, "type": "flat", "value": 20.00},  # observed: 100,000 -> 20
]

_SERVICE_SCHEDULES = {
    "withdrawal": {"Standard": _WITHDRAWAL_SCHEDULE_STANDARD},
    "purchase": {"Standard": _WITHDRAWAL_SCHEDULE_STANDARD},
    "pos_transfer": {"Standard": _WITHDRAWAL_SCHEDULE_STANDARD},
    "pos_qr": {"Standard": _WITHDRAWAL_SCHEDULE_STANDARD},
    "transfer_to_bank": {"Standard": _TRANSFER_TO_BANK_SCHEDULE_STANDARD},
}


def get_fee_schedule(level: str, service_type: str) -> list:
    if level not in VALID_LEVELS:
        raise ValueError(
            f"Unknown Moniepoint merchant level '{level}'. Must be one of {VALID_LEVELS} "
            f"(Moniepoint's real tiering structure isn't documented yet)."
        )
    if service_type not in _SERVICE_SCHEDULES:
        raise ValueError(
            f"Moniepoint has no configured schedule for service_type '{service_type}'. "
            f"Known service types: {list(_SERVICE_SCHEDULES.keys())}."
        )
    return _SERVICE_SCHEDULES[service_type][level]
