"""
Moniepoint App Screenshot Parser
====================================
VALIDATED structurally against two real Moniepoint app "Transactions"
screen screenshots. Layout differs from OPay's app:

    <↑/↓ icon> [to/from] <Counterparty>    <sign><amount>
    <service label, e.g. "Transfer" or "Purchase">
    <Debit|Credit>

CONFIRMED real limitation: this screen does NOT show a date per
transaction in the cropped view available — only a "Past" tab header.
Every transaction from this parser is missing a date and MUST be
confirmed by the merchant before being saved, same as the amount-
confirmation requirement on the OPay screenshot parser.
"""
import os
import re
import pytesseract
_WINDOWS_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(_WINDOWS_TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = _WINDOWS_TESSERACT_PATH
from PIL import Image
from typing import Dict, List, Optional

_AMOUNT = re.compile(r'[+\-*]?\s*[^\d\n]{0,3}([\d,]+\.\d{2})')
_DIRECTION_WORDS = {"debit", "credit"}


class MoniepointScreenshotParser:
    """Parses a Moniepoint app 'Transactions' screen screenshot via OCR."""

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
        skipped = 0

        for i, line in enumerate(lines):
            amt_match = _AMOUNT.search(line)
            if not amt_match:
                continue

            direction = None
            for j in range(i + 1, min(i + 3, len(lines))):
                low = lines[j].lower()
                if 'debit' in low:
                    direction = 'out'
                    break
                if 'credit' in low:
                    direction = 'in'
                    break

            if direction is None:
                skipped += 1
                continue

            description = line[:amt_match.start()].strip()
            description = re.sub(r'^[^A-Za-z]+', '', description)
            if not description:
                skipped += 1
                continue

            amount = float(amt_match.group(1).replace(',', ''))
            if amount <= 0:
                skipped += 1
                continue

            transactions.append({
                "date": None,  # CONFIRMED missing from this screen — merchant must supply it
                "amount": amount,
                "direction": direction,
                "description": description,
                "service_type": (svc := "withdrawal" if direction == "in" else "transfer_to_bank"),
                "is_emtl_qualifying": svc == "transfer_to_bank",
                "is_levy_line": "vat" in description.lower() or "stamp duty" in description.lower(),
                "channel": "App Screenshot",
                "needs_date_confirmation": True,
                "needs_amount_confirmation": True,  # same OCR-currency-glyph risk as OPay's parser
            })

        errors = []
        if skipped:
            errors.append(f"{skipped} line(s) looked like transactions but couldn't be fully parsed.")
        errors.append(
            "⚠️ This screen doesn't show a date per transaction and OCR can misread amounts — "
            "please fill in the date and verify every amount before saving."
        )

        return {
            "success": len(transactions) > 0,
            "transaction_count": len(transactions),
            "transactions": transactions,
            "confidence_score": 0.35 if transactions else 0.0,  # lower than OPay's: missing
                                                                    # dates on top of the same
                                                                    # amount-OCR risk
            "errors": errors,
            "provider": "Moniepoint",
            "source_format": "screenshot",
        }

    def _failure(self, errors: List[str]) -> Dict:
        return {
            "success": False,
            "transaction_count": 0,
            "transactions": [],
            "confidence_score": 0.0,
            "errors": errors,
            "provider": "Moniepoint",
            "source_format": "screenshot",
        }