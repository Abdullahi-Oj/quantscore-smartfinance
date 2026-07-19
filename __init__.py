"""
Provider Registry
==================
The ONLY place that maps a provider name to its configuration module.
Adding Moniepoint or PalmPay later means: write providers/moniepoint.py
with the same get_fee_schedule(level, service_type) interface, register
it below, and the rest of the engine (rules.py, financial_engine.py)
needs zero changes.
"""

from . import opay

_REGISTRY = {
    "OPay": opay,
}


def get_fee_schedule(provider: str, level: str, service_type: str) -> list:
    if provider not in _REGISTRY:
        raise ValueError(
            f"Unknown provider '{provider}'. Configured providers: {list(_REGISTRY.keys())}. "
            f"To add a new one, create providers/<name>.py with a get_fee_schedule() "
            f"function and register it in providers/__init__.py."
        )
    return _REGISTRY[provider].get_fee_schedule(level, service_type)
