"""
Universal Business Rules Engine (Phase 6 / Level 1)
=====================================================
These functions know NOTHING about OPay, Moniepoint, or PalmPay. They only
know how to evaluate a fee schedule and apply government rules. All
provider-specific variability lives in pos_engine/providers/ as pure data,
not here — adding a new provider should never require touching this file.

Fee schedule format (the "configuration" the reviewer's design calls for):
    A fee schedule is a list of bracket dicts, each one of:
      {"min": <amt>, "max": <amt or None>, "type": "flat", "value": <ngn>}
      {"min": <amt>, "max": <amt or None>, "type": "percentage",
       "rate": <decimal>, "cap": <ngn or None>}
    `max: None` means "open-ended" (no upper bound on this bracket).

This format is deliberately more expressive than a single rate+cap pair,
because that simpler shape literally cannot represent OPay's real fee
table (verified: it does not reduce to a clean percentage formula — see
providers/opay.py for the evidence). A provider whose real schedule *is*
a clean min(amount*rate, cap) can still be expressed here, as a single
open-ended percentage bracket — the format doesn't force complexity where
it doesn't exist, but it doesn't paper over discontinuous real-world
schedules with a formula that would just be wrong.
"""


def calculate_provider_fee(amount: float, fee_schedule: list) -> float:
    """The ONE place that evaluates a fee schedule. Provider-agnostic —
    it has no idea which provider's schedule it was handed.

    Deliberately does NOT special-case amount <= 0 to "just return 0" —
    that convenience guard previously caused a real bug: a flat fee that
    doesn't depend on amount at all (e.g. Transfer to Bank) got silently
    zeroed out whenever a caller passed a placeholder amount of 0. A
    genuinely invalid amount should fail loudly via "no bracket covers
    this", not silently return a fee of zero.
    """
    for bracket in fee_schedule:
        low = bracket["min"]
        high = bracket["max"]
        if high is not None and not (low <= amount <= high):
            continue
        if high is None and amount < low:
            continue

        if bracket["type"] == "flat":
            return round(bracket["value"], 2)
        elif bracket["type"] == "percentage":
            fee = amount * bracket["rate"]
            cap = bracket.get("cap")
            if cap is not None:
                fee = min(fee, cap)
            return round(fee, 2)
        else:
            raise ValueError(f"Unknown bracket type '{bracket['type']}'.")

    raise ValueError(
        f"No bracket in the fee schedule covers amount {amount}. "
        f"The schedule may be missing coverage for this range."
    )


def calculate_emtl(amount: float, is_qualifying: bool, threshold: float, levy_amount: float) -> float:
    """Government Rule (Level 2) — independent of any provider.

    CONFIRMED by operator (Jun 2026): the ₦50 levy (now "Stamp Duty" under
    the Nigeria Tax Act 2025, effective 1 Jan 2026) is charged from the
    POS agent's own account — it is a real merchant cost, not passed
    through to the customer. This resolves what was previously an open
    question about the post-2026 sender/receiver reform; the merchant-
    borne treatment in this engine is correct as implemented.
    """
    if is_qualifying and amount >= threshold:
        return round(levy_amount, 2)
    return 0.0


def calculate_transaction_profit(customer_charge: float, provider_fee: float, emtl: float) -> float:
    """The universal profit rule — applies identically regardless of
    provider, service type, or merchant level, since by this point all
    the variability has already been resolved into these three numbers."""
    return round(customer_charge - provider_fee - emtl, 2)
