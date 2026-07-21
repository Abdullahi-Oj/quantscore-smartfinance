"""
Database Migration — add missing additive columns to the real smartfinance.db
===============================================================================
SQLAlchemy's create_all() creates missing TABLES but NOT missing COLUMNS on
existing tables. These columns were defined in models.py as additive
(described as "new, additive") but won't exist in smartfinance.db if the DB
was created before those columns were added.

This script is safe to run multiple times — it skips columns that already
exist. It never drops or modifies existing columns or rows.

Run once against your real smartfinance.db before using the new features:
    python database/migrate.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "smartfinance.db"


def get_existing_columns(cur, table: str) -> set:
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def add_column_if_missing(cur, table: str, column: str, definition: str):
    existing = get_existing_columns(cur, table)
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        print(f"  + {table}.{column} added")
    else:
        print(f"  ✓ {table}.{column} already exists")


def run_migration(db_path: Path):
    if not db_path.exists():
        print(f"Database not found at {db_path}. Nothing to migrate.")
        return

    print(f"Migrating: {db_path}")
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    print("\n--- transactions ---")
    add_column_if_missing(cur, "transactions", "observed_provider_fee", "FLOAT")
    add_column_if_missing(cur, "transactions", "calculated_provider_fee", "FLOAT")
    add_column_if_missing(cur, "transactions", "pricing_difference", "FLOAT")
    add_column_if_missing(cur, "transactions", "pricing_alert", "BOOLEAN DEFAULT 0")
    add_column_if_missing(cur, "transactions", "rule_version", "VARCHAR(20)")
    add_column_if_missing(cur, "transactions", "rule_confidence_level", "VARCHAR(10)")

    print("\n--- provider_pricing_rules ---")
    add_column_if_missing(cur, "provider_pricing_rules", "rule_version", "VARCHAR(20) DEFAULT 'v1'")
    add_column_if_missing(cur, "provider_pricing_rules", "effective_from", "DATE")
    add_column_if_missing(cur, "provider_pricing_rules", "effective_to", "DATE")
    add_column_if_missing(cur, "provider_pricing_rules", "confidence_level",
                          "VARCHAR(10) DEFAULT 'high'")
    add_column_if_missing(cur, "provider_pricing_rules", "confidence_source", "VARCHAR(255)")

    print("\n--- engine_logs (new table if missing) ---")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS engine_logs (
            id INTEGER NOT NULL PRIMARY KEY,
            transaction_id INTEGER NOT NULL REFERENCES transactions(id),
            provider VARCHAR(100) NOT NULL,
            rule_version VARCHAR(20),
            customer_charge FLOAT NOT NULL,
            calculated_provider_fee FLOAT NOT NULL,
            observed_provider_fee FLOAT,
            emtl FLOAT NOT NULL,
            net_profit FLOAT NOT NULL,
            rule_confidence_level VARCHAR(10),
            calculation_timestamp DATETIME NOT NULL
        )
    """)
    print("  ✓ engine_logs table ensured")

    conn.commit()
    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    run_migration(path)