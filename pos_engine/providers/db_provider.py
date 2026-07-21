"""
Database-backed provider registry.
Replaces the hardcoded module-based registry in providers/__init__.py.
"""
from database.session import get_db
from database.repositories import ProviderRepository


def get_fee_schedule(provider: str, level: str, service_type: str) -> list:
    """
    Get fee schedule from database.
    
    This is the drop-in replacement for the old providers.get_fee_schedule().
    The rest of the engine (rules.py, financial_engine.py) doesn't need to change.
    
    Args:
        provider: Provider code (e.g., "OPay", "Moniepoint")
        level: Merchant level (e.g., "Platinum", "Gold", "Regular")
        service_type: Service type (e.g., "withdrawal", "transfer_to_bank")
    
    Returns:
        List of bracket dicts matching rules.py format:
        [
            {"min": 1, "max": 3000, "type": "percentage", "rate": 0.0043, "cap": 85.00},
            {"min": 3001, "max": 4000, "type": "flat", "value": 17.00},
            ...
        ]
    
    Raises:
        ValueError: If provider, level, or service_type is unknown
    """
    db = next(get_db())
    try:
        repo = ProviderRepository(db)
        return repo.get_fee_schedule(provider, level, service_type)
    finally:
        db.close()