"""
Moniepoint Excel Statement Parser
===================================
VALIDATED against a real Moniepoint export (Jun 2026): the file failed to
open with openpyxl/pandas at all, raising:
    ValueError: Value must be one of {'bottom', 'top', 'justify', 'center', 'distributed'}
Root cause confirmed by inspecting the raw XML inside the .xlsx (it's a
zip archive): Moniepoint's export tool writes `vertical="Top"` (capital T)
in xl/styles.xml, but the OOXML spec only permits lowercase values.
openpyxl's strict validator rejects the entire workbook over this single
attribute. This is a real bug in Moniepoint's export tool, not anything
on our side — the fix below patches just that one attribute's casing
in-memory before handing the file to pandas, and changes nothing else
about the data.

Moniepoint's real export format (confirmed from actual data) has an
explicit `Charge (NGN)` column showing the REAL fee for every transaction
— this is a fundamentally more transparent format than OPay's (which
shows no separate fee line for POS credits at all). Per project decision,
this engine still recomputes fees via the rate-table model rather than
using this observed Charge column directly — be aware the two will not
match, and the observed Charge column is available in raw_data for
anyone who wants to compare or override later.
"""
import re
import io
import zipfile
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime


class MoniepointExcelParser:
    """Parses a real Moniepoint POS/wallet account statement Excel export."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def extract(self) -> Dict:
        try:
            fixed_bytes = self._repair_xlsx()
        except Exception as e:
            return self._failure([f"Could not read or repair the Excel file: {e}"])

        try:
            df = pd.read_excel(io.BytesIO(fixed_bytes), header=None)
        except Exception as e:
            return self._failure([f"File was repaired but pandas still could not parse it: {e}"])

        header_row_idx = self._find_header_row(df)
        if header_row_idx is None:
            return self._failure([
                "Could not locate the transaction table header row (looking for 'Date' and "
                "'Transaction Type' columns). This may not be a Moniepoint statement export, "
                "or the format has changed.",
            ])

        df = pd.read_excel(io.BytesIO(fixed_bytes), header=header_row_idx)
        df.columns = [str(c).strip() for c in df.columns]

        transactions = []
        skipped = 0
        for _, row in df.iterrows():
            txn = self._parse_row(row)
            if txn is None:
                if row.notna().any():
                    skipped += 1
                continue
            transactions.append(txn)

        confidence = len(transactions) / (len(transactions) + skipped) if (transactions or skipped) else 0.0

        errors = []
        if skipped:
            errors.append(f"{skipped} row(s) could not be parsed and were skipped.")

        return {
            "success": len(transactions) > 0,
            "transaction_count": len(transactions),
            "transactions": transactions,
            "confidence_score": round(confidence, 2),
            "errors": errors,
            "provider": "Moniepoint",
            "source_format": "excel",
        }

    def _repair_xlsx(self) -> bytes:
        """Lowercase any capitalized `vertical="..."` style attribute inside
        xl/styles.xml, leaving every other byte of the file untouched."""
        with open(self.file_path, 'rb') as f:
            original = f.read()

        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original), 'r') as zin:
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename == 'xl/styles.xml':
                        text = data.decode('utf-8')
                        text = re.sub(
                            r'vertical="(Top|Bottom|Center|Justify|Distributed)"',
                            lambda m: f'vertical="{m.group(1).lower()}"',
                            text,
                        )
                        data = text.encode('utf-8')
                    zout.writestr(item, data)
        return buf.getvalue()

    def _find_header_row(self, df: pd.DataFrame) -> Optional[int]:
        for idx, row in df.iterrows():
            row_str = ' '.join(str(v) for v in row.values if pd.notna(v))
            if 'Date' in row_str and 'Transaction Type' in row_str:
                return idx
        return None

    def _parse_row(self, row) -> Optional[Dict]:
        date_val = row.get('Date')
        if pd.isna(date_val):
            return None
        date = self._parse_date(date_val)
        if not date:
            return None

        amount = row.get('Transaction Amount (NGN)')
        if pd.isna(amount):
            return None

        settlement_debit = self._to_float(row.get('Settlement Debit (NGN)'))
        settlement_credit = self._to_float(row.get('Settlement Credit (NGN)'))
        charge = self._to_float(row.get('Charge (NGN)'))
        txn_type = str(row.get('Transaction Type', '')).strip()
        narration = str(row.get('Narration', ''))

        direction = 'in' if settlement_credit > 0 else 'out'

        svc_type = self._infer_service_type(txn_type, direction)
        return {
            "date": date,
            "amount": float(amount),
            "direction": direction,
            "description": narration if narration and narration != 'nan' else txn_type,
            "service_type": svc_type,
            "is_emtl_qualifying": svc_type == "transfer_to_bank",
            "is_levy_line": txn_type.upper() == 'VAT' or 'STAMP DUTY' in txn_type.upper(),
            "channel": "POS",
            "raw_debit": settlement_debit,
            "raw_credit": settlement_credit,
            "raw_observed_charge": charge,  # the REAL fee Moniepoint actually deducted —
                                             # available here even though not used by default,
                                             # per the project decision logged above.
            "balance_after": self._to_float(row.get('Balance After (NGN)')),
        }

    def _to_float(self, val) -> float:
        if pd.isna(val):
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    def _parse_date(self, val) -> Optional[str]:
        if isinstance(val, datetime):
            return val.strftime("%Y-%m-%d")
        if isinstance(val, pd.Timestamp):
            return val.strftime("%Y-%m-%d")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(str(val), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _infer_service_type(self, txn_type: str, direction: str) -> str:
        t = txn_type.upper()
        if t == 'PURCHASE':
            return 'withdrawal' if direction == 'in' else 'deposit'
        if t in ('TRANSFER', 'TRF'):
            return 'transfer_to_bank' if direction == 'out' else 'pos_transfer'
        if t == 'VAT':
            return 'levy'
        return 'withdrawal' if direction == 'in' else 'transfer_to_bank'

    def _failure(self, errors: List[str]) -> Dict:
        return {
            "success": False,
            "transaction_count": 0,
            "transactions": [],
            "confidence_score": 0.0,
            "errors": errors,
            "provider": "Moniepoint",
            "source_format": "excel",
        }
