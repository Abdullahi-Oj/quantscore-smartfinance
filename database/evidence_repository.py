"""
Evidence Repository
====================
Stores raw evidence records in the database BEFORE they are processed by
the Financial Engine. This is what makes the audit trail complete:

    Raw File
        ↓
    EvidenceRecord (stored here, immutable after creation)
        ↓
    Financial Engine
        ↓
    TransactionRecord.evidence_id → points back to the raw source

The raw file content is stored as a base64-encoded string (JSON-compatible
with our current SQLite/JSON column setup). The extraction result is
JSON-sanitized before storage (removing non-serializable types like bytes
or NumPy floats). Neither is ever overwritten after creation.
"""
import json
import base64
import hashlib
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from .models import EvidenceRecord, EvidenceType, EvidenceStatus

# Some parts of the codebase (extractor.py's CONFIDENCE_LEVELS, the
# "source_format" fields written by the *_pdf_parser.py modules) use a
# short-code vocabulary ("pdf", "excel", "screenshot", "manual")
# that does not match the EvidenceType enum's member names or values.
# This maps the short codes to the correct enum member.
_SHORT_CODE_TO_EVIDENCE_TYPE = {
    "pdf": EvidenceType.PDF_STATEMENT,
    "excel": EvidenceType.EXCEL_EXPORT,
    "screenshot": EvidenceType.SCREENSHOT,
    "manual": EvidenceType.MANUAL_ENTRY,
}


def _normalize_evidence_type(evidence_type) -> EvidenceType:
    """Accepts an EvidenceType member, an enum .value string
    ("pdf_statement"), an enum .name string ("PDF_STATEMENT"), or a
    legacy short code ("pdf"), and returns a valid EvidenceType member.
    Raises ValueError with a clear message if nothing matches, instead
    of letting SQLAlchemy raise an opaque LookupError at flush time."""
    if isinstance(evidence_type, EvidenceType):
        return evidence_type

    if isinstance(evidence_type, str):
        # Try short code first (e.g. "pdf")
        if evidence_type in _SHORT_CODE_TO_EVIDENCE_TYPE:
            return _SHORT_CODE_TO_EVIDENCE_TYPE[evidence_type]
        # Try enum .value (e.g. "pdf_statement")
        try:
            return EvidenceType(evidence_type)
        except ValueError:
            pass
        # Try enum .name (e.g. "PDF_STATEMENT")
        if evidence_type in EvidenceType.__members__:
            return EvidenceType[evidence_type]

    raise ValueError(
        f"Unrecognized evidence_type {evidence_type!r}. Expected one of "
        f"{list(_SHORT_CODE_TO_EVIDENCE_TYPE)} (short codes), "
        f"{[e.value for e in EvidenceType]} (enum values), or "
        f"{[e.name for e in EvidenceType]} (enum names)."
    )


def _sanitize_for_json(obj):
    """Recursively convert non-JSON-serializable types (bytes, NumPy
    scalars, etc.) to JSON-safe equivalents, so extraction results can
    be stored without crashing the DB write."""
    if isinstance(obj, bytes):
        return base64.b64encode(obj).decode('ascii')
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    # Handle NumPy scalars without importing numpy (avoids a hard dependency here)
    if hasattr(obj, 'item'):
        return obj.item()
    if hasattr(obj, '__float__'):
        try:
            return float(obj)
        except (TypeError, ValueError):
            return str(obj)
    return obj


def _compute_file_hash(file_bytes: Optional[bytes]) -> Optional[str]:
    """SHA-256 of the raw file bytes, used for duplicate-upload detection.
    Returns None if there's no file (e.g. a manual-entry evidence record,
    which has nothing to hash and can never collide on this basis)."""
    if not file_bytes:
        return None
    return hashlib.sha256(file_bytes).hexdigest()


def find_duplicate_evidence(
    db: Session,
    merchant_id: int,
    file_bytes: Optional[bytes],
) -> Optional[EvidenceRecord]:
    """
    Call this BEFORE running extraction/building transactions, not after.
    The point of duplicate detection is to skip re-processing entirely —
    checking after the fact only prevents a second Evidence row, not the
    duplicate Transaction rows the caller would otherwise still create.

    Only matches evidence that was actually PROCESSED successfully.
    A REJECTED record (failed extraction) never produced transactions in
    the first place, so re-uploading the same bytes after a failure is a
    legitimate retry, not a duplicate — it must not be blocked here.

    Returns the existing EvidenceRecord if this exact file (by content,
    not filename) was already successfully processed for this merchant,
    else None. Manual entries (file_bytes=None) never match — there's
    nothing to hash, so duplicate detection doesn't apply to them.
    """
    file_hash = _compute_file_hash(file_bytes)
    if file_hash is None:
        return None

    return (
        db.query(EvidenceRecord)
        .filter(
            EvidenceRecord.merchant_id == merchant_id,
            EvidenceRecord.file_hash == file_hash,
            EvidenceRecord.status == EvidenceStatus.PROCESSED,
        )
        .order_by(EvidenceRecord.uploaded_at.desc())
        .first()
    )


def save_evidence(
    db: Session,
    merchant_id: int,
    evidence_type,                # EvidenceType member, or "pdf"/"excel"/
                                   # "screenshot"/"manual", or "pdf_statement"-style
                                   # enum values, or "PDF_STATEMENT"-style names —
                                   # all normalized via _normalize_evidence_type()
    file_bytes: Optional[bytes],
    file_path: Optional[str],
    extraction_result: dict,
    confidence_score: float,
    is_validated: bool,
    validation_notes: Optional[str] = None,
) -> tuple[EvidenceRecord, bool]:
    """Writes raw evidence to the database before the Financial Engine runs.

    Checks for a duplicate (same merchant, same file content, already
    successfully processed) BEFORE inserting. If found, returns the
    EXISTING record unchanged and is_duplicate=True — no new row is
    written, so the caller can short-circuit before building any
    Transactions from it. Manual entries (file_bytes=None) never match,
    since there's nothing to hash; is_duplicate is always False for them.

    Returns:
        (record, is_duplicate) — record.id can be attached to
        TransactionRecords either way (existing or newly created).
    """
    existing = find_duplicate_evidence(db, merchant_id, file_bytes)
    if existing is not None:
        return existing, True

    # Store file bytes as base64 string — our file_content column is JSON
    # in the current model. A production upgrade to LargeBinary/BLOB would
    # be more efficient for large files, but this is correct and portable.
    encoded_content = (
        base64.b64encode(file_bytes).decode('ascii') if file_bytes else None
    )

    # Sanitize the extraction result — it may contain bytes (file_content
    # embedded in the result dict) or NumPy scalars from pandas parsing
    safe_extraction = _sanitize_for_json(extraction_result)

    record = EvidenceRecord(
        merchant_id=merchant_id,
        evidence_type=_normalize_evidence_type(evidence_type),
        file_path=file_path,
        file_content=encoded_content,  # base64 string, not raw bytes
        file_hash=_compute_file_hash(file_bytes),
        status=EvidenceStatus.PROCESSED if extraction_result.get("success") else EvidenceStatus.REJECTED,
        extracted_data=safe_extraction,
        confidence_score=float(confidence_score),
        is_validated=is_validated,
        validation_notes=validation_notes,
        uploaded_at=datetime.utcnow(),
        processed_at=datetime.utcnow(),
    )
    db.add(record)
    db.flush()  # assigns record.id without committing
    return record, False


def get_evidence_for_merchant(db: Session, merchant_id: int) -> list:
    """Returns all evidence records for a merchant, newest first."""
    return (
        db.query(EvidenceRecord)
        .filter(EvidenceRecord.merchant_id == merchant_id)
        .order_by(EvidenceRecord.uploaded_at.desc())
        .all()
    )