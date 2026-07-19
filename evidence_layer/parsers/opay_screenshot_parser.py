"""
OPay App Screenshot Parser
=============================
VALIDATED against a real OPay app "Transactions" screen screenshot.
Tesseract OCR mangles the ₦ symbol inconsistently — it comes out as
different garbage characters on different lines (§, ¥, %, 8, etc., or
sometimes nothing). This parser therefore does NOT try to match a
currency symbol at all; it anchors on the layout structure that survives
OCR reliably:

    <Label/description>          -<amount>
    <date>, <time> [· <ref>]
    Successful

Each transaction is 3 lines. The amount is found via "a dash followed by
digits/commas/period", which OCR preserves even when the currency symbol
before it is garbled.
"""
import os
import re
import pytesseract
_WINDOWS_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(_WINDOWS_TESSERACT_PATH):
    # Only override on a Windows dev machine that actually has it there.
    # On Linux deployments (Render, Streamlit Cloud, Docker), this path
    # never exists - leaving tesseract_cmd untouched lets pytesseract find
    # the real binary on PATH instead of always failing on a hardcoded
    # path that can never exist outside Windows.
    pytesseract.pytesseract.tesseract_cmd = _WINDOWS_TESSERACT_PATH
from PIL import Image
from typing import Dict, List, Optional
from datetime import datetime

# A dash (the literal minus sign OPay shows for every debit in this view),
# then any amount of currency-symbol garbage, then the actual digits.
_AMOUNT_LINE = re.compile(r'-\s*[^\d\n]{0,3}([\d,]+\.\d{2})')
_DATE_LINE = re.compile(r'([A-Za-z]{3,9} \d{1,2}),?\s+(\d{1,2}:\d{2})')
_STATUS_WORDS = {"successful", "failed", "pending", "reversed"}


class OPayScreenshotParser:
    """Parses an OPay app 'Transactions' screen screenshot via OCR."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def extract(self) -> Dict:
        try:
            image = Image.open(self.file_path)
            text = pytesseract.image_to_string(image)
        except Exception as e:
            return self._failure([f"Could not run OCR on this image: {e}"])

        lines = [l.strip() for l in text.split('\n') if l.strip()]
        transactions = []
        i = 0
        skipped = 0
        while i < len(lines):
            amt_match = _AMOUNT_LINE.search(lines[i])
            if not amt_match:
                i += 1
                continue

            description = lines[i][:amt_match.start()].strip()
            description = re.sub(r'^[^A-Za-z]+', '', description)  # strip OCR noise glyphs
            amount = float(amt_match.group(1).replace(',', ''))

            date = None
            j = i + 1
            while j < len(lines) and j < i + 3:
                date_match = _DATE_LINE.search(lines[j])
                if date_match:
                    date = self._normalize_date(date_match.group(1))
                    break
                j += 1

            if not description or amount <= 0:
                skipped += 1
                i += 1
                continue

            service_type = self._infer_service_type(description)
            transactions.append({
                "date": date,
                "amount": amount,
                "direction": "out",
                "description": description,
                "service_type": service_type,
                "is_emtl_qualifying": service_type == "transfer_to_bank",
                "is_levy_line": "stamp duty" in description.lower() or "vat" in description.lower(),
                "channel": "App Screenshot",
                "needs_date_confirmation": date is None,
                # CONFIRMED on real data: OCR can misread the mangled ₦ glyph as a literal
                # leading digit and fuse it onto the real amount (e.g. real ₦45,000 came
                # back as 845,000 — a corrupted "8" prepended, with no way to detect this
                # from text alone). EVERY screenshot-derived amount must be shown to the
                # merchant for confirmation before it is trusted — there is no reliable
                # automatic fix for this category of OCR error.
                "needs_amount_confirmation": True,
            })
            i = j + 1

        confidence = 0.4 if transactions else 0.0  # deliberately low: OCR-derived amounts
                                                      # have a confirmed failure mode that
                                                      # cannot be auto-corrected, so this
                                                      # should never clear an auto-accept
                                                      # threshold on its own
        errors = []
        if skipped:
            errors.append(f"{skipped} line(s) looked like amounts but couldn't be matched to a transaction.")
        if any(t["needs_date_confirmation"] for t in transactions):
            errors.append(
                "Some transactions are missing a year (screenshots often only show 'Month Day'). "
                "Please confirm the date for each before saving."
            )
        errors.append(
            "⚠️ Screenshot OCR can misread amounts (a corrupted currency symbol can attach an "
            "extra digit to a real number). Please check every extracted amount against the "
            "screenshot before saving — do not trust these numbers automatically."
        )

        return {
            "success": len(transactions) > 0,
            "transaction_count": len(transactions),
            "transactions": transactions,
            "confidence_score": confidence,
            "errors": errors,
            "provider": "OPay",
            "source_format": "screenshot",
        }

    def _normalize_date(self, date_str: str) -> Optional[str]:
        # No year in the screenshot — return month-day only; the caller is
        # responsible for asking the merchant which year this belongs to.
        for fmt in ("%b %d", "%B %d"):
            try:
                dt = datetime.strptime(date_str, fmt)
                return f"{dt.month:02d}-{dt.day:02d}"
            except ValueError:
                continue
        return None

    def _infer_service_type(self, description: str) -> str:
        d = description.lower()
        if 'stamp duty' in d or 'vat' in d:
            return 'levy'
        if 'transfer to bank' in d:
            return 'transfer_to_bank'
        if 'airtime' in d:
            return 'airtime'
        if 'data' in d:
            return 'data'
        return 'transfer_to_bank'

    def _failure(self, errors: List[str]) -> Dict:
        return {
            "success": False,
            "transaction_count": 0,
            "transactions": [],
            "confidence_score": 0.0,
            "errors": errors,
            "provider": "OPay",
            "source_format": "screenshot",
        }