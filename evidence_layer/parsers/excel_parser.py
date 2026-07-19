"""
Excel Statement Parser
Extracts transactions from Excel exports (similar to CSV but with .xlsx support).
"""
import pandas as pd
from typing import List, Dict, Optional
from .csv_parser import CSVParser  # Reuse CSV logic


class ExcelParser(CSVParser):
    """
    Parses POS provider Excel exports.
    Inherits from CSVParser since the logic is nearly identical.
    """
    
    def _load_csv(self):
        """Load Excel file instead of CSV."""
        try:
            self.df = pd.read_excel(self.file_path, engine='openpyxl')
        except Exception as e:
            raise ValueError(f"Could not read Excel file: {e}")