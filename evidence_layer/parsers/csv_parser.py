"""
CSV Statement Parser
Extracts transactions from CSV exports (OPay, Moniepoint, PalmPay).
"""
import pandas as pd
import re
from typing import List, Dict, Optional
from datetime import datetime


class CSVParser:
    """
    Parses POS provider CSV exports into structured transaction data.
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.df = None
        
    def extract(self) -> Dict:
        """Main extraction method."""
        try:
            self._load_csv()
            transactions = self._parse_transactions()
            
            return {
                "success": True,
                "transaction_count": len(transactions),
                "transactions": transactions,
                "confidence_score": self._calculate_confidence(transactions),
                "errors": [],
            }
        except Exception as e:
            return {
                "success": False,
                "transaction_count": 0,
                "transactions": [],
                "confidence_score": 0.0,
                "errors": [str(e)],
            }
    
    def _load_csv(self):
        """Load CSV file into DataFrame."""
        # Try common encodings
        for encoding in ['utf-8', 'latin1', 'cp1252']:
            try:
                self.df = pd.read_csv(self.file_path, encoding=encoding)
                return
            except UnicodeDecodeError:
                continue
        
        raise ValueError("Could not decode CSV file with common encodings")
    
    def _parse_transactions(self) -> List[Dict]:
        """Parse transactions from DataFrame."""
        transactions = []
        
        # Normalize column names
        self.df.columns = [self._normalize_column(col) for col in self.df.columns]
        
        for _, row in self.df.iterrows():
            try:
                txn = self._parse_row(row.to_dict())
                if txn:
                    transactions.append(txn)
            except Exception:
                continue
        
        return transactions
    
    def _parse_row(self, row_dict: Dict) -> Optional[Dict]:
        """Parse a single row into a transaction dict."""
        date = self._extract_date(row_dict)
        amount = self._extract_amount(row_dict)
        service_type = self._extract_service_type(row_dict)
        
        if not date or not amount:
            return None
        
        return {
            "date": date,
            "amount": amount,
            "service_type": service_type,
            "description": row_dict.get("description", row_dict.get("narration", "")),
            "reference": row_dict.get("reference", row_dict.get("rrn", "")),
            "status": row_dict.get("status", "completed"),
            "raw_data": row_dict,
        }
    
    def _extract_date(self, row_dict: Dict) -> Optional[str]:
        """Extract and normalize date."""
        date_fields = ["date", "transaction_date", "trans_date", "value_date"]
        
        for field in date_fields:
            if field in row_dict and pd.notna(row_dict[field]):
                date_val = row_dict[field]
                
                # Handle pandas Timestamp
                if isinstance(date_val, pd.Timestamp):
                    return date_val.strftime("%Y-%m-%d")
                
                # Parse string
                parsed = self._parse_date(str(date_val))
                if parsed:
                    return parsed
        
        return None
    
    def _extract_amount(self, row_dict: Dict) -> Optional[float]:
        """Extract and normalize amount."""
        amount_fields = ["amount", "value", "debit", "credit", "transaction_amount"]
        
        for field in amount_fields:
            if field in row_dict and pd.notna(row_dict[field]):
                amount_val = row_dict[field]
                parsed = self._parse_amount(str(amount_val))
                if parsed:
                    return parsed
        
        return None
    
    def _extract_service_type(self, row_dict: Dict) -> str:
        """Infer service type from description."""
        desc_fields = ["description", "narration", "particulars", "details", "type"]
        
        description = ""
        for field in desc_fields:
            if field in row_dict and pd.notna(row_dict[field]):
                description = str(row_dict[field])
                break
        
        return self._infer_service_type(description)
    
    def _infer_service_type(self, description: str) -> str:
        """Map description to service type."""
        desc_lower = description.lower()
        
        if any(word in desc_lower for word in ["withdrawal", "cash out"]):
            return "withdrawal"
        elif any(word in desc_lower for word in ["deposit", "cash in"]):
            return "deposit"
        elif any(word in desc_lower for word in ["transfer", "bank transfer"]):
            return "transfer_to_bank"
        elif any(word in desc_lower for word in ["airtime", "recharge"]):
            return "airtime"
        elif any(word in desc_lower for word in ["data", "internet"]):
            return "data"
        elif any(word in desc_lower for word in ["bill", "utility"]):
            return "bills_payment"
        elif any(word in desc_lower for word in ["pos transfer"]):
            return "pos_transfer"
        elif any(word in desc_lower for word in ["qr"]):
            return "pos_qr"
        elif any(word in desc_lower for word in ["purchase", "payment"]):
            return "purchase"
        else:
            return "withdrawal"
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date string to ISO format."""
        formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%m/%d/%Y",
            "%d %b %Y",
            "%d %B %Y",
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        return None
    
    def _parse_amount(self, amount_str: str) -> Optional[float]:
        """Parse amount string."""
        cleaned = re.sub(r'[₦$,\s]|NGN|ngn', '', amount_str)
        
        try:
            return float(cleaned)
        except ValueError:
            return None
    
    def _normalize_column(self, col: str) -> str:
        """Normalize column name."""
        col_lower = col.lower().strip()
        
        mappings = {
            "transaction date": "date",
            "trans date": "date",
            "date": "date",
            "amount": "amount",
            "value": "amount",
            "description": "description",
            "narration": "description",
            "reference": "reference",
            "rrn": "reference",
            "status": "status",
        }
        
        return mappings.get(col_lower, col_lower.replace(" ", "_"))
    
    def _calculate_confidence(self, transactions: List[Dict]) -> float:
        """Calculate extraction confidence."""
        if not transactions:
            return 0.0
        
        valid_count = sum(1 for txn in transactions 
                         if txn.get("date") and txn.get("amount"))
        
        return valid_count / len(transactions)