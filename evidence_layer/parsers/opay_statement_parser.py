"""
OPay-Specific Statement Parser
Handles the exact format of OPay wallet account statement exports.

OPay exports have:
- 6 rows of metadata before the transaction table
- Column headers: Trans. Date, Value Date, Description, Debit(N), Credit(N), Balance After(N), Channel, Transaction Reference
- "--" for empty values
- Dates like "29 Oct 2025 08:27:01"
- Structured descriptions like "Airtime | 8101268622 | MTN" or "POS | 2101Y3MT | ..."
- EMTL entries with "Electronic Money Transfer Levy" in description
"""
import pandas as pd
import re
from typing import List, Dict, Optional
from datetime import datetime


class OPayStatementParser:
    """
    Dedicated parser for OPay wallet statement exports.
    Normalizes OPay's format into the common Transaction schema.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.metadata = {}
        self.transactions = []

    def parse(self) -> Dict:
        """
        Main parsing method. Returns structured data ready for the Financial Engine.
        """
        try:
            # Step 1: Read raw lines to find the transaction table
            raw_lines = self._read_file()

            # Step 2: Extract metadata (account info, period, balances)
            self.metadata = self._extract_metadata(raw_lines)

            # Step 3: Find where the transaction table starts
            header_row_idx = self._find_header_row(raw_lines)

            if header_row_idx is None:
                return {
                    "success": False,
                    "metadata": self.metadata,
                    "transactions": [],
                    "transaction_count": 0,
                    "confidence_score": 0.0,
                    "errors": ["Could not locate transaction table header (looking for 'Trans. Date')"],
                }

            # Step 4: Parse the transaction table
            df = self._parse_transaction_table(header_row_idx)

            # Step 5: Normalize and extract transactions
            self.transactions = self._normalize_transactions(df)

            return {
                "success": True,
                "metadata": self.metadata,
                "transactions": self.transactions,
                "transaction_count": len(self.transactions),
                "confidence_score": 0.95 if self.transactions else 0.0,
                "errors": [],
            }

        except Exception as e:
            return {
                "success": False,
                "metadata": self.metadata,
                "transactions": [],
                "transaction_count": 0,
                "confidence_score": 0.0,
                "errors": [f"OPay parsing error: {str(e)}"],
            }

    def _read_file(self) -> List[str]:
        """Read file with multiple encoding attempts."""
        encodings = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252']

        for encoding in encodings:
            try:
                with open(self.file_path, 'r', encoding=encoding) as f:
                    lines = f.readlines()

                # Check if we got readable content
                sample = ''.join(lines[:10])
                if any(ord(c) > 127 and c not in '₦' for c in sample):
                    continue

                return lines
            except UnicodeDecodeError:
                continue
            except Exception as e:
                raise ValueError(f"Could not read file: {e}")

        raise ValueError("Could not decode file with any supported encoding")

    def _extract_metadata(self, lines: List[str]) -> Dict:
        """Extract account metadata from the header rows."""
        metadata = {}

        for line in lines[:10]:
            line = line.strip()

            if 'Account Name' in line:
                parts = line.split(',')
                if len(parts) >= 2:
                    metadata['account_name'] = parts[1].strip()

            elif 'Account Number' in line:
                parts = line.split(',')
                if len(parts) >= 4:
                    metadata['account_number'] = parts[3].strip()

            elif 'Period' in line:
                parts = line.split(',')
                if len(parts) >= 4:
                    metadata['period'] = parts[3].strip()

            elif 'Opening Balance' in line:
                parts = line.split(',')
                if len(parts) >= 2:
                    metadata['opening_balance'] = self._clean_amount(parts[1])

            elif 'Closing Balance' in line:
                parts = line.split(',')
                if len(parts) >= 2:
                    metadata['closing_balance'] = self._clean_amount(parts[1])

        return metadata

    def _find_header_row(self, lines: List[str]) -> Optional[int]:
        """Find the row containing 'Trans. Date' header."""
        for i, line in enumerate(lines):
            if 'Trans. Date' in line and 'Description' in line:
                return i
        return None

    def _parse_transaction_table(self, header_row_idx: int) -> pd.DataFrame:
        """Parse the transaction table starting from the header row."""
        df = pd.read_csv(
            self.file_path,
            skiprows=header_row_idx,
            encoding='utf-8',
            on_bad_lines='skip'
        )
        return df

    def _normalize_transactions(self, df: pd.DataFrame) -> List[Dict]:
        """Convert DataFrame rows into normalized Transaction dicts."""
        transactions = []

        # Normalize column names
        column_map = {}
        for col in df.columns:
            col_str = str(col).strip()
            if 'Trans. Date' in col_str:
                column_map[col] = 'date'
            elif 'Description' in col_str:
                column_map[col] = 'description'
            elif 'Debit' in col_str:
                column_map[col] = 'debit'
            elif 'Credit' in col_str:
                column_map[col] = 'credit'
            elif 'Transaction Reference' in col_str or 'Reference' in col_str:
                column_map[col] = 'reference'

        df = df.rename(columns=column_map)

        # Process each row
        for _, row in df.iterrows():
            try:
                txn = self._process_transaction_row(row)
                if txn:
                    transactions.append(txn)
            except Exception:
                continue

        return transactions

    def _process_transaction_row(self, row) -> Optional[Dict]:
        """Process a single transaction row into normalized format."""
        # Extract date
        date_str = str(row.get('date', ''))
        if not date_str or date_str == 'nan':
            return None

        date = self._parse_date(date_str)
        if not date:
            return None

        # Extract description
        description = str(row.get('description', ''))
        if not description or description == 'nan':
            return None

        # Extract amounts (handle "--" as 0)
        debit = self._clean_amount(str(row.get('debit', '--')))
        credit = self._clean_amount(str(row.get('credit', '--')))

        # Determine transaction direction and amount
        if debit and debit > 0:
            amount = debit
            direction = 'out'
        elif credit and credit > 0:
            amount = credit
            direction = 'in'
        else:
            return None

        # Auto-detect service type from description
        service_type = self._detect_service_type(description)

        # Auto-detect EMTL
        is_emtl = 'Electronic Money Transfer Levy' in description or 'Stamp Duty' in description

        # Skip EMTL entries (these are government charges, not business transactions)
        if is_emtl:
            return None

        # Extract reference
        reference = str(row.get('reference', ''))
        if reference == 'nan':
            reference = ''

        return {
            "date": date,
            "amount": amount,
            "service_type": service_type,
            "description": description,
            "reference": reference,
            "status": "completed",
            "is_emtl_qualifying": service_type == "transfer_to_bank",  # Stamp Duty on bank transfers >= ₦10k
            "raw_data": {
                "debit": debit,
                "credit": credit,
                "direction": direction,
            },
        }

    def _detect_service_type(self, description: str) -> str:
        """
        Auto-detect service type from OPay's structured descriptions.
        """
        desc_lower = description.lower()

        # Airtime purchases
        if desc_lower.startswith('airtime'):
            return 'airtime'

        # Data purchases
        elif 'data' in desc_lower and ('bundle' in desc_lower or 'internet' in desc_lower):
            return 'data'

        # POS transactions (customer used the terminal)
        elif desc_lower.startswith('pos |') or desc_lower.startswith('pos|'):
            return 'withdrawal'

        # Transfers FROM someone (money coming in)
        elif 'transfer from' in desc_lower:
            return 'deposit'

        # Transfers TO someone (money going out)
        elif 'transfer to' in desc_lower:
            return 'transfer_to_bank'

        # Bills payment
        elif any(word in desc_lower for word in ['dstv', 'gotv', 'wec', 'phcn', 'bill']):
            return 'bills_payment'

        # Default
        else:
            return 'withdrawal'

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse OPay date format."""
        date_str = str(date_str).strip()

        formats = [
            "%d %b %Y %H:%M:%S",
            "%d %b %Y",
            "%d %B %Y %H:%M:%S",
            "%d %B %Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return None

    def _clean_amount(self, amount_str: str) -> Optional[float]:
        """Clean amount string."""
        if not amount_str or amount_str == '--' or amount_str == 'nan':
            return 0.0

        cleaned = re.sub(r'[₦$,\s]|NGN|ngn', '', str(amount_str))

        try:
            return float(cleaned)
        except ValueError:
            return 0.0