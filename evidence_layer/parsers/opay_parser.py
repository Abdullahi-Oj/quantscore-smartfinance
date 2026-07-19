import pandas as pd
import re
from typing import List, Dict, Optional
from datetime import datetime


class OPayParser:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.is_csv = file_path.lower().endswith('.csv')
        self.is_excel = file_path.lower().endswith(('.xlsx', '.xls'))
        
    def extract(self) -> Dict:
        try:
            if self.is_csv:
                transactions = self._parse_csv()
            elif self.is_excel:
                transactions = self._parse_excel()
            else:
                return {
                    "success": False,
                    "transaction_count": 0,
                    "transactions": [],
                    "confidence_score": 0.0,
                    "errors": ["Unsupported file format. OPay parser supports CSV and Excel only."],
                }
            
            return {
                "success": True,
                "transaction_count": len(transactions),
                "transactions": transactions,
                "confidence_score": 0.95 if transactions else 0.0,
                "errors": [],
            }
        except Exception as e:
            return {
                "success": False,
                "transaction_count": 0,
                "transactions": [],
                "confidence_score": 0.0,
                "errors": [f"OPay parsing error: {str(e)}"],
            }
    
    def _parse_csv(self) -> List[Dict]:
        # First, read the file to find where the headers are
        with open(self.file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find the header row (should contain "Trans. Date" or "Description")
        header_row_idx = None
        for i, line in enumerate(lines):
            if 'Trans. Date' in line or ('Description' in line and 'Debit' in line):
                header_row_idx = i
                break
        
        if header_row_idx is None:
            raise ValueError("Could not find transaction header row containing 'Trans. Date'")
        
        # Now read the CSV starting from the header row
        df = pd.read_csv(self.file_path, skiprows=header_row_idx, encoding='utf-8')
        
        # Normalize column names
        column_map = {}
        for col in df.columns:
            col_str = str(col).strip()
            if 'Trans. Date' in col_str:
                column_map[col] = 'date'
            elif 'Value Date' in col_str:
                column_map[col] = 'value_date'
            elif 'Description' in col_str:
                column_map[col] = 'description'
            elif 'Debit' in col_str and '₦' in col_str:
                column_map[col] = 'debit'
            elif 'Credit' in col_str and '₦' in col_str:
                column_map[col] = 'credit'
            elif 'Balance After' in col_str:
                column_map[col] = 'balance'
            elif 'Channel' in col_str:
                column_map[col] = 'channel'
            elif 'Transaction Reference' in col_str or 'Reference' in col_str:
                column_map[col] = 'reference'
        
        df = df.rename(columns=column_map)
        
        # Check if required columns exist
        if 'date' not in df.columns or 'description' not in df.columns:
            raise ValueError(f"Required columns not found. Available: {list(df.columns)}")
        
        transactions = []
        for _, row in df.iterrows():
            try:
                txn = self._parse_row(row)
                if txn:
                    transactions.append(txn)
            except Exception:
                continue
        
        return transactions

    def _parse_excel(self) -> List[Dict]:
        # For Excel, use the same logic
        df = pd.read_excel(self.file_path, engine='openpyxl', skiprows=0)
        
        # Find header row
        header_row_idx = None
        for idx, row in df.iterrows():
            row_str = ' '.join([str(v) for v in row.values if pd.notna(v)])
            if 'Trans. Date' in row_str or ('Description' in row_str and 'Debit' in row_str):
                header_row_idx = idx
                break
        
        if header_row_idx is not None:
            df = pd.read_excel(self.file_path, engine='openpyxl', skiprows=header_row_idx)
        
        # Normalize columns
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
            elif 'Reference' in col_str:
                column_map[col] = 'reference'
        
        df = df.rename(columns=column_map)
        
        transactions = []
        for _, row in df.iterrows():
            try:
                txn = self._parse_row(row)
                if txn:
                    transactions.append(txn)
            except Exception:
                continue
        
        return transactions

    def _parse_row(self, row) -> Optional[Dict]:
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
        
        # Extract amounts (handle '--' as empty and ₦ symbol)
        debit_val = row.get('debit', '--')
        credit_val = row.get('credit', '--')
        
        debit = self._parse_amount(str(debit_val))
        credit = self._parse_amount(str(credit_val))
        
        # Determine transaction type and amount
        if debit and debit > 0:
            amount = debit
            transaction_direction = 'out'
        elif credit and credit > 0:
            amount = credit
            transaction_direction = 'in'
        else:
            return None
        
        # Infer service type from description
        service_type = self._infer_service_type(description, transaction_direction)
        
        # Skip EMTL/levy entries (government charges, not business transactions)
        if 'Electronic Money Transfer Levy' in description or 'Stamp Duty' in description:
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
            "raw_data": {
                "debit": debit,
                "credit": credit,
                "direction": transaction_direction,
            },
        }

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse OPay date format: '29 Oct 2025 08:27:01' or '29 Oct 2025'"""
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

    def _parse_amount(self, amount_str: str) -> Optional[float]:
        """Parse amount, handling '--' as empty and removing currency symbols."""
        if not amount_str or amount_str == '--' or amount_str == 'nan':
            return None
        
        # Remove currency symbols (₦, $), commas, whitespace, NGN
        cleaned = re.sub(r'[₦$,\s]|NGN|ngn', '', str(amount_str))
        
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _infer_service_type(self, description: str, direction: str) -> str:
        """
        Map OPay description to our service types.
        POS transactions: 'POS | 2101Y3MT | 510295616825 | Suleja,Suleja,Niger'
        """
        desc_lower = description.lower()
        
        # POS terminal transactions (the main business)
        if desc_lower.startswith('pos |') or desc_lower.startswith('pos|') or 'pos |' in desc_lower:
            if direction == 'out':
                return 'withdrawal'  # Customer withdrew cash (credit to merchant)
            else:
                return 'deposit'  # Customer deposited cash (debit to merchant)
        
        # Airtime purchases
        elif 'airtime' in desc_lower:
            return 'airtime'
        
        # Data purchases
        elif 'data' in desc_lower and ('bundle' in desc_lower or 'internet' in desc_lower):
            return 'data'
        
        # Bills payment
        elif any(word in desc_lower for word in ['dstv', 'gotv', 'wec', 'phcn', 'bill']):
            return 'bills_payment'
        
        # Transfers
        elif 'transfer from' in desc_lower:
            # Customer transferred money to merchant (Cash In)
            return 'pos_transfer'
        
        elif 'transfer to' in desc_lower:
            # Merchant transferred money out (Cash Out)
            return 'transfer_to_bank'
        
        # Default based on direction
        else:
            if direction == 'out':
                return 'withdrawal'
            else:
                return 'deposit'