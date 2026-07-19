"""
Migration: fix historically-corrupted evidence_type values
=============================================================
Root cause: evidence_type was written as a raw short code ("pdf",
"excel") instead of a proper EvidenceType enum name ("PDF_STATEMENT",
"EXCEL_EXPORT") on every upload since at least 2026-07-06. SQLite never
enforces the enum constraint on write, so this was silently accepted -
it only surfaces as a crash when something reads an affected row back
through SQLAlchemy (e.g. find_duplicate_evidence(), or any other query
that loads a full EvidenceRecord), which is why this appeared now and
not earlier: it's the first code path that actually reads existing
evidence rows back as ORM objects during a normal upload flow.

This migration does NOT touch status or transaction_type - checked both,
already clean.

Run this ONCE against your real smartfinance.db before your next upload:
    python migrate_evidence_type_values.py
"""
import shutil
import sqlite3
from datetime import datetime

DB_PATH = "smartfinance.db"  # adjust if your DB lives elsewhere

# Same mapping evidence_repository.py's _normalize_evidence_type() uses -
# kept in sync manually since this is a one-off migration, not shared code.
SHORT_CODE_TO_ENUM_NAME = {
    "pdf": "PDF_STATEMENT",
    "excel": "EXCEL_EXPORT",
    "csv": "CSV_EXPORT",
    "screenshot": "SCREENSHOT",
    "manual": "MANUAL_ENTRY",
}

VALID_ENUM_NAMES = set(SHORT_CODE_TO_ENUM_NAME.values())


def main():
    backup_path = f"{DB_PATH}.bak_before_evidence_type_migration_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy(DB_PATH, backup_path)
    print(f"Backed up {DB_PATH} -> {backup_path}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT id, evidence_type FROM evidence")
    rows = cur.fetchall()

    fixed = 0
    unrecognized = []
    for row_id, raw_value in rows:
        if raw_value in VALID_ENUM_NAMES:
            continue  # already correct, leave untouched
        correct = SHORT_CODE_TO_ENUM_NAME.get(raw_value)
        if correct is None:
            # Don't silently guess on something we don't recognize -
            # surface it for a human to look at instead.
            unrecognized.append((row_id, raw_value))
            continue
        cur.execute("UPDATE evidence SET evidence_type = ? WHERE id = ?", (correct, row_id))
        print(f"  id={row_id}: {raw_value!r} -> {correct!r}")
        fixed += 1

    conn.commit()
    print(f"\n{fixed} row(s) fixed.")

    if unrecognized:
        print(f"\n⚠️  {len(unrecognized)} row(s) had an evidence_type value that "
              f"isn't a known short code OR a valid enum name - NOT auto-fixed, "
              f"needs manual review:")
        for row_id, raw_value in unrecognized:
            print(f"  id={row_id}: {raw_value!r}")

    cur.execute("SELECT DISTINCT evidence_type FROM evidence")
    print(f"\nDistinct evidence_type values now: {[r[0] for r in cur.fetchall()]}")

    conn.close()
    print(f"\nIf anything looks wrong, restore from: {backup_path}")


if __name__ == "__main__":
    main()
