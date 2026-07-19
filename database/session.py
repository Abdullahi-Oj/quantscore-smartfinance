"""
Database Session
==================
Engine and session factory. Defaults to the real smartfinance.db file in
the project root, matching what's already deployed — override via
SMARTFINANCE_DB_URL for tests or a different environment (e.g. Postgres
in production later).
"""
import os
import sqlite3
from pathlib import Path
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker
from .models import Base

DEFAULT_DB_PATH = Path(__file__).parent.parent / "smartfinance.db"
DATABASE_URL = os.environ.get("SMARTFINANCE_DB_URL", f"sqlite:///{DEFAULT_DB_PATH}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _get_sqlite_db_path(database_url: str) -> Optional[Path]:
    if not database_url.startswith("sqlite"):
        return None
    url = make_url(database_url)
    if url.database is None or url.database == ":memory:":
        return None
    return Path(url.database)


def _get_existing_columns(cur, table: str) -> set:
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def _add_column_if_missing(cur, table: str, column: str, definition: str):
    existing = _get_existing_columns(cur, table)
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _run_sqlite_schema_migrations():
    db_path = _get_sqlite_db_path(DATABASE_URL)
    if db_path is None or not db_path.exists():
        return

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    _add_column_if_missing(cur, "transactions", "observed_provider_fee", "FLOAT")
    _add_column_if_missing(cur, "transactions", "calculated_provider_fee", "FLOAT")
    _add_column_if_missing(cur, "transactions", "pricing_difference", "FLOAT")
    _add_column_if_missing(cur, "transactions", "pricing_alert", "BOOLEAN DEFAULT 0")
    _add_column_if_missing(cur, "transactions", "rule_version", "VARCHAR(20)")
    _add_column_if_missing(cur, "transactions", "rule_confidence_level", "VARCHAR(10)")

    _add_column_if_missing(cur, "provider_pricing_rules", "rule_version", "VARCHAR(20) DEFAULT 'v1'")
    _add_column_if_missing(cur, "provider_pricing_rules", "effective_from", "DATE")
    _add_column_if_missing(cur, "provider_pricing_rules", "effective_to", "DATE")
    _add_column_if_missing(cur, "provider_pricing_rules", "confidence_level", "VARCHAR(10) DEFAULT 'high'")
    _add_column_if_missing(cur, "provider_pricing_rules", "confidence_source", "VARCHAR(255)")

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
    conn.commit()
    conn.close()


def init_db():
    """Creates any tables that don't exist yet. Safe to call against the
    real smartfinance.db — SQLAlchemy only CREATEs missing tables, it
    never drops or alters existing ones, so pre-existing data survives."""
    Base.metadata.create_all(bind=engine)
    _run_sqlite_schema_migrations()


def get_session():
    return SessionLocal()
