"""
Migrate hardcoded OPay data from providers/opay.py to the database.
Run this once to populate the database with initial provider data.
"""
from database.session import init_db, SessionLocal
from database.models import Provider, ProviderLevel, ProviderPricingRule, FeeType
from database.repositories import ProviderRepository
from pos_engine.providers import opay


def migrate_opay_data():
    """Migrate OPay fee schedules to database."""
    init_db()
    db = SessionLocal()
    
    try:
        # Create OPay provider
        opay_provider = Provider(
            name="OPay",
            code="OPAY",
            description="OPay POS service provider"
        )
        db.add(opay_provider)
        db.commit()
        db.refresh(opay_provider)
        
        print(f"Created provider: {opay_provider.name} (ID: {opay_provider.id})")
        
        # Create merchant levels
        levels = {}
        for level_name in opay.VALID_LEVELS:
            level = ProviderLevel(
                provider_id=opay_provider.id,
                name=level_name,
                code=level_name.upper()
            )
            db.add(level)
            db.commit()
            db.refresh(level)
            levels[level_name] = level
            print(f"Created level: {level_name} (ID: {level.id})")
        
        # Migrate fee schedules
        service_types = {
            "withdrawal": opay._WITHDRAWAL_SCHEDULES,
            "purchase": opay._WITHDRAWAL_SCHEDULES,
            "pos_transfer": opay._WITHDRAWAL_SCHEDULES,
            "pos_qr": opay._WITHDRAWAL_SCHEDULES,
            "transfer_to_bank": opay._TRANSFER_TO_BANK_SCHEDULES,
        }
        
        for service_type, schedules in service_types.items():
            for level_name, brackets in schedules.items():
                level = levels[level_name]
                
                for bracket in brackets:
                    rule = ProviderPricingRule(
                        level_id=level.id,
                        service_type=service_type,
                        min_amount=bracket["min"],
                        max_amount=bracket["max"],
                        fee_type=bracket["type"],
                    )
                    
                    if bracket["type"] == "flat":
                        rule.flat_value = bracket["value"]
                    elif bracket["type"] == "percentage":
                        rule.percentage_rate = bracket["rate"]
                        rule.percentage_cap = bracket.get("cap")
                    
                    db.add(rule)
                
                print(f"Migrated {len(brackets)} brackets for {level_name}/{service_type}")
        
        db.commit()
        print("\n✅ Migration complete!")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate_opay_data()