"""
Database Bootstrap Script — Updated with Moniepoint and PalmPay
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.session import init_db, SessionLocal
from database.models import Provider, ProviderLevel, ProviderPricingRule, FeeType


def check_if_migration_needed() -> bool:
    db = SessionLocal()
    try:
        count = db.query(Provider).count()
        return count == 0
    finally:
        db.close()


def create_provider(db, name: str, code: str, description: str) -> Provider:
    provider = Provider(name=name, code=code, description=description)
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


def create_level(db, provider_id: int, name: str, code: str) -> ProviderLevel:
    level = ProviderLevel(provider_id=provider_id, name=name, code=code)
    db.add(level)
    db.commit()
    db.refresh(level)
    return level


def add_pricing_rule(db, level_id: int, service_type: str, min_amt: float, max_amt, 
                     fee_type: str, flat_value=None, percentage_rate=None, percentage_cap=None):
    rule = ProviderPricingRule(
        level_id=level_id,
        service_type=service_type,
        min_amount=min_amt,
        max_amount=max_amt,
        fee_type=fee_type,
        flat_value=flat_value,
        percentage_rate=percentage_rate,
        percentage_cap=percentage_cap,
    )
    db.add(rule)


def migrate_opay_data(db):
    """Migrate OPay fee schedules to database."""
    print("📦 Migrating OPay data...")
    opay = create_provider(db, "OPay", "OPAY", "OPay POS service provider")
    
    levels = {}
    for level_name in ["Platinum", "Gold", "Regular"]:
        level = create_level(db, opay.id, level_name, level_name.upper())
        levels[level_name] = level
    
    # OPay withdrawal/purchase/pos_transfer/pos_qr schedules (same for all)
    opay_withdrawal_schedules = {
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
            {"min": 19001, "max": None, "type": "flat", "value": 85.00},
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
    
    # OPay transfer_to_bank schedules
    opay_transfer_schedules = {
        "Platinum": [{"min": 1, "max": None, "type": "flat", "value": 14.00}],
        "Gold": [{"min": 1, "max": None, "type": "flat", "value": 18.00}],
        "Regular": [{"min": 1, "max": None, "type": "flat", "value": 20.00}],
    }
    
    for service_type in ["withdrawal", "purchase", "pos_transfer", "pos_qr"]:
        for level_name, brackets in opay_withdrawal_schedules.items():
            level = levels[level_name]
            for bracket in brackets:
                if bracket["type"] == "flat":
                    add_pricing_rule(db, level.id, service_type, bracket["min"], bracket["max"],
                                   "flat", flat_value=bracket["value"])
                else:
                    add_pricing_rule(db, level.id, service_type, bracket["min"], bracket["max"],
                                   "percentage", percentage_rate=bracket["rate"], 
                                   percentage_cap=bracket.get("cap"))
    
    for level_name, brackets in opay_transfer_schedules.items():
        level = levels[level_name]
        for bracket in brackets:
            add_pricing_rule(db, level.id, "transfer_to_bank", bracket["min"], bracket["max"],
                           "flat", flat_value=bracket["value"])
    
    print(f"  ✅ OPay migrated with {len(levels)} levels")


def migrate_moniepoint_data(db):
    """Migrate Moniepoint fee schedules to database."""
    print("📦 Migrating Moniepoint data...")
    moniepoint = create_provider(db, "Moniepoint", "MONIEPOINT", "Moniepoint POS service provider")
    
    levels = {}
    for level_name in ["Premium", "Standard", "Basic"]:
        level = create_level(db, moniepoint.id, level_name, level_name.upper())
        levels[level_name] = level
    
    # Moniepoint withdrawal/purchase/pos_transfer/pos_qr schedules
    # IMPORTANT: "Standard" level uses REAL OBSERVED FEES from pos_engine/providers/moniepoint.py
    # (derived from a single real merchant statement, NOT an official rate card)
    moniepoint_withdrawal_schedules = {
        "Premium": [
            {"min": 1, "max": 5000, "type": "flat", "value": 10.00},
            {"min": 5001, "max": 10000, "type": "flat", "value": 20.00},
            {"min": 10001, "max": 20000, "type": "flat", "value": 30.00},
            {"min": 20001, "max": 30000, "type": "flat", "value": 40.00},
            {"min": 30001, "max": 50000, "type": "flat", "value": 50.00},
            {"min": 50001, "max": 100000, "type": "flat", "value": 75.00},
            {"min": 100001, "max": None, "type": "flat", "value": 100.00},
        ],
        "Standard": [
            # Observed from real Moniepoint export: bracket boundaries inferred from observed amounts
            {"min": 1, "max": 2550, "type": "flat", "value": 10.00},       # observed: 2,000 -> 10
            {"min": 2551, "max": 3550, "type": "flat", "value": 20.00},    # observed: 3,100 -> 20
            {"min": 3551, "max": 4500, "type": "flat", "value": 20.00},    # observed: 4,000 -> 20
            {"min": 4501, "max": 5050, "type": "flat", "value": 25.00},    # observed: 5,000 -> 25
            {"min": 5051, "max": 5550, "type": "flat", "value": 30.00},    # observed: 5,100 -> 30
            {"min": 5551, "max": 8100, "type": "flat", "value": 30.00},    # observed: 6,000 -> 30
            {"min": 8101, "max": 12600, "type": "flat", "value": 55.00},   # observed: 10,200 -> 55
            {"min": 12601, "max": 15100, "type": "flat", "value": 75.00},  # observed: 15,000 -> 75
            {"min": 15101, "max": 17750, "type": "flat", "value": 80.00},  # observed: 15,200 -> 80
            {"min": 17751, "max": None, "type": "flat", "value": 100.00},  # observed: 20,300+ -> 100
        ],
        "Basic": [
            {"min": 1, "max": 5000, "type": "flat", "value": 20.00},
            {"min": 5001, "max": 10000, "type": "flat", "value": 30.00},
            {"min": 10001, "max": 20000, "type": "flat", "value": 40.00},
            {"min": 20001, "max": 30000, "type": "flat", "value": 50.00},
            {"min": 30001, "max": 50000, "type": "flat", "value": 70.00},
            {"min": 50001, "max": 100000, "type": "flat", "value": 95.00},
            {"min": 100001, "max": None, "type": "flat", "value": 120.00},
        ],
    }
    
    # Moniepoint transfer_to_bank schedules
    # IMPORTANT: "Standard" level uses REAL OBSERVED FEES from pos_engine/providers/moniepoint.py
    moniepoint_transfer_schedules = {
        "Premium": [{"min": 1, "max": None, "type": "flat", "value": 10.00}],
        "Standard": [{"min": 1, "max": None, "type": "flat", "value": 20.00}],  # observed: 100,000 -> 20
        "Basic": [{"min": 1, "max": None, "type": "flat", "value": 20.00}],
    }
    
    for service_type in ["withdrawal", "purchase", "pos_transfer", "pos_qr"]:
        for level_name, brackets in moniepoint_withdrawal_schedules.items():
            level = levels[level_name]
            for bracket in brackets:
                add_pricing_rule(db, level.id, service_type, bracket["min"], bracket["max"],
                               "flat", flat_value=bracket["value"])
    
    for level_name, brackets in moniepoint_transfer_schedules.items():
        level = levels[level_name]
        for bracket in brackets:
            add_pricing_rule(db, level.id, "transfer_to_bank", bracket["min"], bracket["max"],
                           "flat", flat_value=bracket["value"])
    
    print(f"  ✅ Moniepoint migrated with {len(levels)} levels")


def migrate_palmpay_data(db):
    """Migrate PalmPay fee schedules to database."""
    print("📦 Migrating PalmPay data...")
    palmpay = create_provider(db, "PalmPay", "PALMPAY", "PalmPay POS service provider")
    
    levels = {}
    for level_name in ["Diamond", "Gold", "Silver"]:
        level = create_level(db, palmpay.id, level_name, level_name.upper())
        levels[level_name] = level
    
    # PalmPay withdrawal/purchase/pos_transfer/pos_qr schedules
    palmpay_withdrawal_schedules = {
        "Diamond": [
            {"min": 1, "max": 5000, "type": "flat", "value": 12.00},
            {"min": 5001, "max": 10000, "type": "flat", "value": 22.00},
            {"min": 10001, "max": 20000, "type": "flat", "value": 32.00},
            {"min": 20001, "max": 30000, "type": "flat", "value": 42.00},
            {"min": 30001, "max": 50000, "type": "flat", "value": 55.00},
            {"min": 50001, "max": 100000, "type": "flat", "value": 80.00},
            {"min": 100001, "max": None, "type": "flat", "value": 105.00},
        ],
        "Gold": [
            {"min": 1, "max": 5000, "type": "flat", "value": 18.00},
            {"min": 5001, "max": 10000, "type": "flat", "value": 28.00},
            {"min": 10001, "max": 20000, "type": "flat", "value": 38.00},
            {"min": 20001, "max": 30000, "type": "flat", "value": 48.00},
            {"min": 30001, "max": 50000, "type": "flat", "value": 65.00},
            {"min": 50001, "max": 100000, "type": "flat", "value": 90.00},
            {"min": 100001, "max": None, "type": "flat", "value": 115.00},
        ],
        "Silver": [
            {"min": 1, "max": 5000, "type": "flat", "value": 25.00},
            {"min": 5001, "max": 10000, "type": "flat", "value": 35.00},
            {"min": 10001, "max": 20000, "type": "flat", "value": 45.00},
            {"min": 20001, "max": 30000, "type": "flat", "value": 55.00},
            {"min": 30001, "max": 50000, "type": "flat", "value": 75.00},
            {"min": 50001, "max": 100000, "type": "flat", "value": 100.00},
            {"min": 100001, "max": None, "type": "flat", "value": 125.00},
        ],
    }
    
    # PalmPay transfer_to_bank schedules
    palmpay_transfer_schedules = {
        "Diamond": [{"min": 1, "max": None, "type": "flat", "value": 12.00}],
        "Gold": [{"min": 1, "max": None, "type": "flat", "value": 18.00}],
        "Silver": [{"min": 1, "max": None, "type": "flat", "value": 25.00}],
    }
    
    for service_type in ["withdrawal", "purchase", "pos_transfer", "pos_qr"]:
        for level_name, brackets in palmpay_withdrawal_schedules.items():
            level = levels[level_name]
            for bracket in brackets:
                add_pricing_rule(db, level.id, service_type, bracket["min"], bracket["max"],
                               "flat", flat_value=bracket["value"])
    
    for level_name, brackets in palmpay_transfer_schedules.items():
        level = levels[level_name]
        for bracket in brackets:
            add_pricing_rule(db, level.id, "transfer_to_bank", bracket["min"], bracket["max"],
                           "flat", flat_value=bracket["value"])
    
    print(f"  ✅ PalmPay migrated with {len(levels)} levels")


def verify_migration():
    print("\n🔍 Verifying migration...")
    from pos_engine.providers import get_fee_schedule, get_supported_providers
    
    providers = get_supported_providers()
    print(f"  ✅ Found {len(providers)} providers: {', '.join(providers)}")
    
    test_cases = [
        ("OPay", "Platinum", "withdrawal"),
        ("Moniepoint", "Premium", "withdrawal"),
        ("PalmPay", "Diamond", "withdrawal"),
    ]
    
    for provider, level, service_type in test_cases:
        try:
            schedule = get_fee_schedule(provider, level, service_type)
            print(f"  ✅ {provider}/{level}/{service_type}: {len(schedule)} brackets loaded")
        except Exception as e:
            print(f"  ❌ {provider}/{level}/{service_type}: {e}")
            return False
    
    print("\n✅ All verifications passed!")
    return True


def main():
    print("=" * 60)
    print("SmartFinance Database Bootstrap")
    print("=" * 60)
    
    print("\n📁 Initializing database...")
    init_db()
    print("  ✅ Database tables created")
    
    if check_if_migration_needed():
        print("\n📊 Database is empty. Running migration...")
        db = SessionLocal()
        try:
            migrate_opay_data(db)
            migrate_moniepoint_data(db)
            migrate_palmpay_data(db)
            db.commit()
            print("\n✅ Migration complete!")
        except Exception as e:
            db.rollback()
            print(f"\n❌ Migration failed: {e}")
            raise
        finally:
            db.close()
    else:
        print("\n📊 Database already has data. Skipping migration.")
        print("   (To re-run migration, delete smartfinance.db and run this script again)")
    
    if verify_migration():
        print("\n" + "=" * 60)
        print("✅ Bootstrap complete! You can now run the app:")
        print("   streamlit run app.py")
        print("=" * 60)
    else:
        print("\n❌ Migration verification failed. Check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()