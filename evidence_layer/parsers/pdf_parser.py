"""
PDF Statement Parser - OPay/Moniepoint/PalmPay optimized
"""
import pdfplumber
import pandas as pd
import re
from typing import List, Dict, Optional
from datetime import datetime


class PDFParser:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.raw_text = ""
        self.tables = []
        self.debug_info = []
        
    def extract(self) -> Dict:
        try:
            self._extract_text_and_tables()
            
            if not self.raw_text and not self.tables:
                return {
                    "success": False,
                    "transaction_count": 0,
                    "transactions": [],
                    "confidence_score": 0.0,
                    "errors": ["PDF appears to be empty or contains only images (no extractable text)"],
                    "debug": self.debug_info,
                }
            
            self.debug_info.append(f"Extracted {len(self.raw_text)} characters of text")
            self.debug_info.append(f"Found {len(self.tables)} table(s)")
            
            transactions = self._parse_transactions()
            
            if not transactions:
                return {
                    "success": False,
                    "transaction_count": 0,
                    "transactions": [],
                    "confidence_score": 0.0,
                    "errors": [
                        "No transactions could be extracted from this PDF.",
                        "This may be because:",
                        "• The PDF format is not recognized (try CSV/Excel export instead)",
                        "• The statement contains only summary totals, not individual transactions",
                        "• The PDF is image-based (scanned) rather than text-based",
                    ],
                    "debug": self.debug_info,
                }
            
            return {
                "success": True,
                "transaction_count": len(transactions),
                "transactions": transactions,
                "confidence_score": self._calculate_confidence(transactions),
                "errors": [],
                "debug": self.debug_info,
            }
            
        except Exception as e:
            return {
                "success": False,
                "transaction_count": 0,
                "transactions": [],
                "confidence_score": 0.0,
                "errors": [f"PDF parsing error: {str(e)}"],
                "debug": self.debug_info,
            }
    
    def _extract_text_and_tables(self):
        with pdfplumber.open(self.file_path) as pdf:
            self.debug_info.append(f"PDF has {len(pdf.pages)} page(s)")
            
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    self.raw_text += text + "\n"
                    self.debug_info.append(f"Page {i+1}: extracted {len(text)} chars")
                
                tables = page.extract_tables()
                if tables:
                    self.tables.extend(tables)
                    self.debug_info.append(f"Page {i+1}: found {len(tables)} table(s)")
    
    def _parse_transactions(self) -> List[Dict]:
        transactions = []
        
        # Try table-based extraction first
        if self.tables:
            transactions = self._parse_from_tables()
            if transactions:
                self.debug_info.append(f"Extracted {len(transactions)} transactions from tables")
                return transactions
        
        # Fallback to text-based extraction with OPay-specific patterns
        transactions = self._parse_opay_format()
        if transactions:
            self.debug_info.append(f"Extracted {len(transactions)} transactions using OPay patterns")
            return transactions
        
        # Generic text-based extraction
        transactions = self._parse_from_text()
        if transactions:
            self.debug_info.append(f"Extracted {len(transactions)} transactions using generic patterns")
        
        return transactions
    
    def _parse_opay_format(self) -> List[Dict]:
        """OPay-specific parsing patterns"""
        transactions = []
        
        # OPay statement patterns (common formats)
        patterns = [
            # Pattern 1: Date | Time | Description | Amount | Balance
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(\d{2}:\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})',
            # Pattern 2: Date | Description | Debit | Credit | Balance
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})',
            # Pattern 3: Simple Date | Amount | Description
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+([\d,]+\.\d{2})\s+(.+?)(?=\n|$)',
        ]
        
        for pattern_idx, pattern in enumerate(patterns):
            matches = re.finditer(pattern, self.raw_text, re.MULTILINE)
            for match in matches:
                try:
                    groups = match.groups()
                    date_str = groups[0]
                    
                    # Determine which groups are amount vs description
                    if len(groups) >= 3:
                        # Try to find amount (numeric with decimals)
                        amount_idx = None
                        for i, g in enumerate(groups[1:], 1):
                            if re.match(r'^[\d,]+\.\d{2}$', g.replace(',', '')):
                                amount_idx = i
                                break
                        
                        if amount_idx:
                            amount_str = groups[amount_idx]
                            description = ' '.join([g for i, g in enumerate(groups[1:], 1) if i != amount_idx])
                        else:
                            continue
                        
                        date = self._parse_date(date_str)
                        amount = self._parse_amount(amount_str)
                        
                        if date and amount and amount > 0:
                            transactions.append({
                                "date": date,
                                "amount": amount,
                                "service_type": self._infer_service_type(description),
                                "description": description.strip(),
                                "reference": "",
                                "status": "completed",
                                "raw_data": {"pattern": f"opay_pattern_{pattern_idx}"},
                            })
                except Exception as e:
                    self.debug_info.append(f"Pattern {pattern_idx} match failed: {e}")
                    continue
        
        return transactions
    
    def _parse_from_tables(self) -> List[Dict]:
        transactions = []
        
        for table_idx, table in enumerate(self.tables):
            if not table or len(table) < 2:
                continue
            
            # Find header row
            header_row = None
            for i, row in enumerate(table):
                if row and any(self._is_transaction_header(cell) for cell in row if cell):
                    header_row = i
                    break
            
            if header_row is None:
                self.debug_info.append(f"Table {table_idx}: no header row found")
                continue
            
            headers = [self._normalize_header(h) for h in table[header_row] if h]
            self.debug_info.append(f"Table {table_idx}: headers = {headers}")
            
            for row_idx, row in enumerate(table[header_row + 1:], start=1):
                if not row or all(cell is None or str(cell).strip() == '' for cell in row):
                    continue
                
                try:
                    txn = self._parse_table_row(row, headers)
                    if txn:
                        transactions.append(txn)
                except Exception as e:
                    self.debug_info.append(f"Table {table_idx}, row {row_idx}: parse error - {e}")
                    continue
        
        return transactions
    
    def _parse_table_row(self, row: List, headers: List) -> Optional[Dict]:
        row_dict = {}
        for i, h in enumerate(headers):
            if i < len(row):
                row_dict[h] = row[i]
        
        date = self._extract_date(row_dict)
        amount = self._extract_amount(row_dict)
        service_type = self._extract_service_type(row_dict)
        
        if not date or not amount or amount <= 0:
            return None
        
        return {
            "date": date,
            "amount": amount,
            "service_type": service_type,
            "description": row_dict.get("description", row_dict.get("narration", "")),
            "reference": row_dict.get("reference", row_dict.get("rrn", "")),
            "status": "completed",
            "raw_data": row_dict,
        }
    
    def _parse_from_text(self) -> List[Dict]:
        """Generic text-based extraction"""
        transactions = []
        
        # Look for lines with dates and amounts
        lines = self.raw_text.split('\n')
        for line in lines:
            # Skip header lines
            if any(word in line.lower() for word in ['date', 'description', 'amount', 'balance', 'transaction']):
                continue
            
            # Try to extract date and amount from line
            date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', line)
            amount_match = re.search(r'([\d,]+\.\d{2})', line)
            
            if date_match and amount_match:
                try:
                    date = self._parse_date(date_match.group(1))
                    amount = self._parse_amount(amount_match.group(1))
                    
                    if date and amount and amount > 0:
                        # Remove date and amount from line to get description
                        description = re.sub(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', '', line)
                        description = re.sub(r'[\d,]+\.\d{2}', '', description)
                        description = description.strip()
                        
                        transactions.append({
                            "date": date,
                            "amount": amount,
                            "service_type": self._infer_service_type(description),
                            "description": description,
                            "reference": "",
                            "status": "completed",
                            "raw_data": {},
                        })
                except:
                    continue
        
        return transactions
    
    def _extract_date(self, row_dict: Dict) -> Optional[str]:
        date_fields = ["date", "transaction_date", "trans_date", "value_date", "posting_date"]
        for field in date_fields:
            if field in row_dict and row_dict[field]:
                parsed = self._parse_date(str(row_dict[field]))
                if parsed:
                    return parsed
        return None
    
    def _extract_amount(self, row_dict: Dict) -> Optional[float]:
        amount_fields = ["amount", "value", "debit", "credit", "transaction_amount", "withdrawal", "deposit"]
        for field in amount_fields:
            if field in row_dict and row_dict[field]:
                parsed = self._parse_amount(str(row_dict[field]))
                if parsed:
                    return parsed
        return None
    
    def _extract_service_type(self, row_dict: Dict) -> str:
        desc_fields = ["description", "narration", "particulars", "details", "type", "transaction_type"]
        description = ""
        for field in desc_fields:
            if field in row_dict and row_dict[field]:
                description = str(row_dict[field])
                break
        return self._infer_service_type(description)
    
    def _infer_service_type(self, description: str) -> str:
        desc_lower = description.lower()
        
        if any(word in desc_lower for word in ["withdrawal", "cash out", "cashout", "cash withdrawal"]):
            return "withdrawal"
        elif any(word in desc_lower for word in ["deposit", "cash in", "cashin", "cash deposit"]):
            return "deposit"
        elif any(word in desc_lower for word in ["transfer", "bank transfer", "pos transfer"]):
            return "transfer_to_bank"
        elif any(word in desc_lower for word in ["airtime", "recharge", "mobile"]):
            return "airtime"
        elif any(word in desc_lower for word in ["data", "internet", "bundle"]):
            return "data"
        elif any(word in desc_lower for word in ["bill", "utility", "dstv", "gotv", "wec", "phcn"]):
            return "bills_payment"
        elif any(word in desc_lower for word in ["pos", "qr", "qr code"]):
            return "pos_qr"
        elif any(word in desc_lower for word in ["purchase", "payment", "buy"]):
            return "purchase"
        else:
            return "withdrawal"  # Default for POS businesses
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        date_str = str(date_str).strip()
        formats = [
            "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y",
            "%d %b %Y", "%d %B %Y", "%Y/%m/%d", "%d/%m/%y",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
    
    def _parse_amount(self, amount_str: str) -> Optional[float]:
        if not amount_str:
            return None
        cleaned = re.sub(r'[₦$,\s]|NGN|ngn', '', str(amount_str))
        try:
            return float(cleaned)
        except ValueError:
            return None
    
    def _is_transaction_header(self, cell: str) -> bool:
        if not cell:
            return False
        cell_lower = cell.lower()
        return any(word in cell_lower for word in [
            "date", "trans_date", "value_date", "description", "amount", "narration"
        ])
    
    def _normalize_header(self, header: str) -> str:
        if not header:
            return "unknown"
        header_lower = header.lower().strip()
        mappings = {
            "transaction date": "date", "trans date": "date", "value date": "date",
            "date": "date", "amount": "amount", "value": "amount", "debit": "amount",
            "credit": "amount", "description": "description", "narration": "description",
            "particulars": "description", "details": "description", "reference": "reference",
            "rrn": "reference", "retrieval ref": "reference", "status": "status", "type": "type",
        }
        return mappings.get(header_lower, header_lower.replace(" ", "_"))
    
    def _calculate_confidence(self, transactions: List[Dict]) -> float:
        if not transactions:
            return 0.0
        valid_count = sum(1 for t in transactions if t.get("date") and t.get("amount"))
        return valid_count / len(transactions)