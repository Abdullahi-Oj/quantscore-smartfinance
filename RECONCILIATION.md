# Reconciliation Summary — cla.zip merged with prior fixes

## Key finding
`cla.zip` diverged from my earlier fix package *before* those fixes were
ever incorporated — none of the 5 fixes I sent previously were present
here. In exchange, this codebase had its own independent progress I
didn't have: the `evidence_type` short-code normalizer, a `file_hash`
column (migration already run), `copilot.py`, `test_moniepoint_pdf.py`.
This was a genuine two-way merge, not a one-directional update.

## NEW — Evidence Enum bug (your Phase 1 #1)

**Half of it was already fixed here.** `evidence_repository.py` already had
a `_normalize_evidence_type()` helper correctly mapping short codes
(`"pdf"`) → the real enum members (`EvidenceType.PDF_STATEMENT`), and
`save_evidence()` was already calling it for the `evidence_type` field.

**The other half wasn't.** Two lines below, `status=` was still being set
to the plain strings `"processed"` / `"failed"` — but `status` is also
enum-bound (`SQLEnum(EvidenceStatus)`), and `EvidenceStatus` has no
`"failed"` member at all (only `PENDING`, `EXTRACTED`, `VALIDATED`,
`REJECTED`, `PROCESSED`). Any extraction that actually failed would hit
the identical error class again: `'failed' is not among the defined enum
values`.

**Fixed** — `database/evidence_repository.py`: now sets
`status=EvidenceStatus.PROCESSED` / `EvidenceStatus.REJECTED` using the
real enum members instead of ad hoc strings. Added `EvidenceStatus` to
the import. I also swept the rest of the codebase for the same pattern
(`transaction_type=`, `fee_type=`, other enum-bound columns) — no other
instance found. `TransactionType`'s values already match the canonical
service_type vocabulary, so no issue there.

**Not yet wired up (flagging, not fixed):** `file_hash` exists as a column
on `Evidence`/`EvidenceRecord` and the DB migration for it has run, but
`save_evidence()` never actually computes or checks it — nothing hashes
the uploaded file or looks up existing evidence by hash before inserting.
Your Phase 1 #3 ("test duplicate detection") will fail as-is until this
is wired up. Happy to do this next if you want.

## RE-APPLIED — the 5 fixes from the earlier package

None of these were present in `cla.zip`, so I re-applied all of them here,
adapting to this version's exact code (mostly identical to before, with
minor structural differences in `pos_engine/providers/__init__.py`'s
`_get_db()` pattern).

1. **`evidence_layer/parsers/moniepoint_pdf_parser.py`** — vocabulary
   drift (`cash_withdrawal`/`bank_transfer` → `withdrawal`/`transfer_to_bank`)
   and EMTL over-application to `pos_transfer`. Re-verified against the
   real Moniepoint PDF: 21 withdrawal / 6 transfer_to_bank / 2 levy / 1
   pos_transfer, exactly 1 EMTL-qualifying.

2. **`evidence_layer/parsers/opay_pdf_parser.py`** — the `txn_type`
   `NameError` (referenced a variable that was never defined). Fixed
   identically to before.

3. **`pos_engine/financial_engine.py`** — missing `"purchase"` case in
   `transaction_profit()`'s customer-charge lookup. Fixed identically.

4. **`database/models.py`** — added the missing `MerchantPricingRecord`
   alias (completing the disambiguation pattern that already existed for
   `TransactionRecord`/`EvidenceRecord`), and added the 5 columns
   (`rule_version`, `effective_from`, `effective_to`, `confidence_level`,
   `confidence_source`) to `ProviderPricingRule` that the DB migration
   had already applied to the raw SQLite file but the ORM never declared.

5. **`database/repositories.py`** — aligned imports to the `*Record`
   convention.

6. **`pos_engine/providers/__init__.py`** — added `get_rule_confidence()`,
   adapted to this file's `_get_db()` pattern.

7. **`smartfinance.db`** — backfilled real per-provider confidence data
   (was still the migration's blanket `'high'` default here too):
   OPay → `verified`, Moniepoint → `provisional`, PalmPay → `unverified`.
   Pre-backfill copy saved as `smartfinance.db.bak_before_confidence_backfill`.

## File placement
`models.py`, `repositories.py`, `evidence_repository.py` were flat at the
root of `cla.zip`, but per your `project_tree.txt` they belong in
`database/`. I've placed them there in this package. `evidence_layer/`
and `pos_engine/` keep their existing structure.

## Still not seen / not reconciled
`copilot.py`, `test_moniepoint_pdf.py`, `database/session.py`,
`database/ledger_repository.py`, `database/__init__.py`, `app.py`, and
the `docs_stabilization/` folder were not in `cla.zip`. If
`docs_stabilization/MASTER_ISSUES.md` still exists, that's worth sending
next — it likely already tracks some of what's above and may have context
I'm missing.
