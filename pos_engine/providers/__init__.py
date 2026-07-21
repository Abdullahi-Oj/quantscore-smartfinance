"""
Provider Registry — Database-Backed (Phase 6 / DB Migration)

This is the ONLY place that maps a provider name to its fee schedule.
The rest of the engine (rules.py, financial_engine.py) has no idea
whether the schedule came from a database, a module, or a file.

Flow:
    Transaction
        ↓
    Financial Engine calls providers.get_fee_schedule(provider, level, service_type)
        ↓
    This module queries the database
        ↓
    Returns bracket list in the format rules.py expects
        ↓
    rules.calculate_provider_fee() evaluates it

Caching:
    Fee schedules are cached in memory (keyed by provider+level+service_type)
    to avoid hitting the database on every transaction. The cache is
    invalidated when admin updates a rule (via admin_app.py).
"""
from typing import Optional
from functools import lru_cache

# Lazy imports to avoid circular dependencies and allow the engine
# to be imported even if the database isn't initialized yet.
_db_session_factory = None
_cache = {}


def _get_db():
    """Get a database session. Lazy-loaded to avoid import-time failures."""
    global _db_session_factory
    if _db_session_factory is None:
        try:
            from database.session import SessionLocal
            _db_session_factory = SessionLocal
        except ImportError:
            raise RuntimeError(
                "Database module not found. Run 'python bootstrap.py' to initialize the database."
            )
    return _db_session_factory()


def _fetch_fee_schedule_from_db(provider: str, level: str, service_type: str) -> list:
    """
    Query the database for fee schedule brackets.
    Returns a list of bracket dicts matching rules.py format:
    [
        {"min": 1, "max": 3000, "type": "percentage", "rate": 0.0043, "cap": 85.00},
        {"min": 3001, "max": 4000, "type": "flat", "value": 17.00},
        ...
    ]
    """
    from database.repositories import ProviderRepository

    db = _get_db()
    try:
        repo = ProviderRepository(db)
        return repo.get_fee_schedule(provider, level, service_type)
    finally:
        db.close()


def get_fee_schedule(provider: str, level: str, service_type: str) -> list:
    """
    Get fee schedule for a provider/level/service combination.
    
    This is the drop-in replacement for the old module-based registry.
    The financial engine calls this function with the same signature,
    so no changes are needed in financial_engine.py or rules.py.
    
    Args:
        provider: Provider name (e.g., "OPay", "Moniepoint")
        level: Merchant level (e.g., "Platinum", "Gold", "Regular")
        service_type: Service type (e.g., "withdrawal", "transfer_to_bank")
    
    Returns:
        List of bracket dicts matching rules.py format.
    
    Raises:
        ValueError: If provider, level, or service_type is unknown,
                    or if no pricing rules exist in the database.
        RuntimeError: If the database is not initialized.
    """
    # Check cache first
    cache_key = (provider, level, service_type)
    if cache_key in _cache:
        return _cache[cache_key]
    
    # Fetch from database
    try:
        brackets = _fetch_fee_schedule_from_db(provider, level, service_type)
    except ValueError as e:
        # Re-raise with context
        raise ValueError(
            f"Failed to get fee schedule for {provider}/{level}/{service_type}: {e}\n"
            f"Make sure the database is initialized and populated. "
            f"Run 'python bootstrap.py' to set up the database."
        ) from e
    
    # Cache the result
    _cache[cache_key] = brackets
    
    return brackets


_CONFIDENCE_LABELS = {
    "verified": "Verified against a real rate card",
    "provisional": "Provisional — inferred from limited observed data",
    "unverified": "Unverified — no documented source",
    "high": "High",  # legacy default from the migration, before per-provider backfill
}


def get_rule_confidence(provider: str, level: str, service_type: str) -> dict:
    """
    How much to trust the fee schedule used for a given provider/level/
    service_type. Confidence is tracked per-rule (per bracket row in
    ProviderPricingRule). If matching brackets disagree, returns the
    *lowest* confidence found rather than picking one arbitrarily, so
    callers never over-report trust.

    Returns:
        {
            "level": "verified" | "provisional" | "unverified" | None,
            "label": human-readable description,
            "source": free-text provenance note (may be None),
            "bracket_count": how many brackets were checked,
        }

    Raises:
        ValueError: if provider/level/service_type has no pricing rules at all.
        RuntimeError: if the database is not initialized.
    """
    from database.models import Provider, ProviderLevel, ProviderPricingRule

    db = _get_db()
    try:
        provider_obj = db.query(Provider).filter(
            Provider.name == provider,
            Provider.is_active == True,
        ).first()
        if not provider_obj:
            raise ValueError(f"Unknown provider '{provider}'")

        level_obj = db.query(ProviderLevel).filter(
            ProviderLevel.provider_id == provider_obj.id,
            ProviderLevel.name == level,
        ).first()
        if not level_obj:
            raise ValueError(f"Unknown level '{level}' for provider '{provider}'")

        rules = db.query(ProviderPricingRule).filter(
            ProviderPricingRule.level_id == level_obj.id,
            ProviderPricingRule.service_type == service_type,
            ProviderPricingRule.is_active == True,
        ).all()
        if not rules:
            raise ValueError(
                f"No pricing rules found for {provider}/{level}/{service_type}."
            )

        rank = {"unverified": 0, "provisional": 1, "high": 2, "verified": 3}
        worst = min(rules, key=lambda r: rank.get(r.confidence_level, -1))

        return {
            "level": worst.confidence_level,
            "label": _CONFIDENCE_LABELS.get(worst.confidence_level, worst.confidence_level or "Unknown"),
            "source": worst.confidence_source,
            "bracket_count": len(rules),
        }
    finally:
        db.close()


def clear_cache():
    """
    Clear the fee schedule cache.
    Call this after updating provider rules via the admin interface.
    """
    global _cache
    _cache = {}


def get_supported_providers() -> list:
    """
    Get list of providers configured in the database.
    Useful for UI dropdowns (e.g., Streamlit selectbox).
    """
    from database.repositories import ProviderRepository
    
    db = _get_db()
    try:
        repo = ProviderRepository(db)
        # Query all active providers
        from database.models import Provider
        providers = db.query(Provider).filter(Provider.is_active == True).all()
        return [p.name for p in providers]
    finally:
        db.close()


def get_supported_levels(provider: str) -> list:
    """
    Get list of merchant levels for a provider.
    Useful for UI dropdowns.
    """
    from database.repositories import ProviderRepository
    from database.models import Provider, ProviderLevel
    
    db = _get_db()
    try:
        provider_obj = db.query(Provider).filter(
            Provider.name == provider,
            Provider.is_active == True
        ).first()
        
        if not provider_obj:
            raise ValueError(f"Unknown provider '{provider}'")
        
        levels = db.query(ProviderLevel).filter(
            ProviderLevel.provider_id == provider_obj.id
        ).all()
        
        return [level.name for level in levels]
    finally:
        db.close()


def get_supported_service_types(provider: str) -> list:
    """
    Get list of service types configured for a provider.
    Useful for UI dropdowns.
    """
    from database.models import Provider, ProviderLevel, ProviderPricingRule
    
    db = _get_db()
    try:
        provider_obj = db.query(Provider).filter(
            Provider.name == provider,
            Provider.is_active == True
        ).first()
        
        if not provider_obj:
            raise ValueError(f"Unknown provider '{provider}'")
        
        # Get all distinct service types across all levels
        service_types = db.query(ProviderPricingRule.service_type).filter(
            ProviderPricingRule.level_id.in_(
                db.query(ProviderLevel.id).filter(
                    ProviderLevel.provider_id == provider_obj.id
                )
            )
        ).distinct().all()
        
        return [st[0] for st in service_types]
    finally:
        db.close()