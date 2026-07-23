"""
Evidence Extractor
====================
Routes a file to the correct provider+format-specific parser. Every
parser registered here has been validated against a real statement/
screenshot from that provider — see each parser module's docstring for
exactly what was checked and what limitations were found.
"""
from pathlib import Path
from typing import Dict

from .parsers import (
    OPayPDFParser,
    OPayExcelParser,
    MoniepointPDFParser,
    MoniepointExcelParser,
    OPayScreenshotParser,
    MoniepointScreenshotParser,
)

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

# Evidence confidence classification — tells the rest of the system, and
# the person reviewing, how much to trust a given source WITHOUT having
# to inspect the actual confidence_score float every time.
CONFIDENCE_LEVELS = {
    "csv": {"level": "A", "label": "Structured export", "typical_confidence": 0.999},
    "excel": {"level": "A", "label": "Structured export", "typical_confidence": 0.999},
    "pdf": {"level": "B", "label": "Text-based document", "typical_confidence": 0.95},
    "screenshot": {"level": "C", "label": "OCR (image)", "typical_confidence": 0.5},
    "manual": {"level": "D", "label": "Manual entry", "typical_confidence": None},
}


def get_confidence_level(source_format: str) -> dict:
    return CONFIDENCE_LEVELS.get(source_format, {"level": "?", "label": "Unknown source", "typical_confidence": 0.0})


class EvidenceExtractor:
    """Main entry point for evidence extraction. Picks a parser based on
    (provider, file extension) — there is no generic fallback parser for
    formats that haven't been validated against real data, since an
    unvalidated parser silently producing wrong numbers is worse than a
    clear "not supported yet" message."""

    def __init__(self, file_path: str, provider: str = "OPay"):
        self.file_path = file_path
        self.provider = provider
        self.file_extension = Path(file_path).suffix.lower()

    def extract(self) -> Dict:
        parser = self._select_parser()
        if parser is None:
            return {
                "success": False,
                "transaction_count": 0,
                "transactions": [],
                "confidence_score": 0.0,
                "confidence_level": get_confidence_level("unknown"),
                "errors": [
                    f"No validated parser available for {self.provider} + "
                    f"'{self.file_extension}' files yet. Currently supported: "
                    f"OPay (.pdf statement, .xlsx statement, screenshot), "
                    f"Moniepoint (.pdf statement, .xlsx statement, screenshot)."
                ],
                "provider": self.provider,
            }
        result = parser.extract()
        result["confidence_level"] = get_confidence_level(result.get("source_format", "unknown"))
        return result

    def _select_parser(self):
        ext = self.file_extension
        is_image = ext in _IMAGE_EXTENSIONS

        if self.provider == "OPay":
            if ext == ".pdf":
                return OPayPDFParser(self.file_path)
            if ext in (".xlsx", ".xls"):
                return OPayExcelParser(self.file_path)
            if is_image:
                return OPayScreenshotParser(self.file_path)
        elif self.provider == "Moniepoint":
            if ext == ".pdf":
                return MoniepointPDFParser(self.file_path)
            if ext in (".xlsx", ".xls"):
                return MoniepointExcelParser(self.file_path)
            if is_image:
                return MoniepointScreenshotParser(self.file_path)
        return None