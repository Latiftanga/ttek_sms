"""
Base bank statement parser with shared logic for reading CSV/Excel files
and normalising columns into a standard format.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

import logging
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ParsedRow:
    """Standardised representation of one bank-statement row."""

    row_number: int
    transaction_date: Optional[date] = None
    description: str = ""
    reference: str = ""
    credit_amount: Decimal = field(default_factory=lambda: Decimal("0.00"))
    debit_amount: Decimal = field(default_factory=lambda: Decimal("0.00"))


class BaseStatementParser(ABC):
    """Abstract base for all bank-specific statement parsers."""

    @property
    @abstractmethod
    def bank_name(self) -> str:
        """Human-readable bank name."""

    @property
    @abstractmethod
    def bank_code(self) -> str:
        """Short code matching BANK_CHOICES (e.g. 'GCB')."""

    @abstractmethod
    def _get_column_mapping(self) -> Dict[str, str]:
        """
        Return a mapping from standard keys to the bank's column names.
        Required keys: date, description, credit, debit
        Optional key: reference
        """

    @abstractmethod
    def _parse_date(self, value) -> Optional[date]:
        """Parse a date value using the bank's specific format."""

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_amount(value) -> Decimal:
        """Safely convert a value to Decimal, handling commas / blanks."""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return Decimal("0.00")
        text = str(value).strip().replace(",", "")
        if not text or text == "-":
            return Decimal("0.00")
        try:
            return Decimal(text).quantize(Decimal("0.01"))
        except InvalidOperation:
            return Decimal("0.00")

    def _validate_columns(self, df: pd.DataFrame, mapping: Dict[str, str]):
        """Raise ValueError if any required columns are missing."""
        required = {"date", "description", "credit", "debit"}
        missing = []
        for key in required:
            col = mapping.get(key)
            if not col or col not in df.columns:
                missing.append(f"{key} (expected column '{col}')")
        if missing:
            raise ValueError(
                f"Missing required columns for {self.bank_name}: "
                + ", ".join(missing)
                + f". Found columns: {list(df.columns)}"
            )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def parse(self, file, file_ext: str) -> List[ParsedRow]:
        """
        Read a CSV or Excel file and return a list of ParsedRow objects.
        """
        file.seek(0)
        if file_ext in ("xlsx", "xls"):
            df = pd.read_excel(file, engine="openpyxl")
        else:
            df = pd.read_csv(file)

        if df.empty:
            raise ValueError("The uploaded file is empty.")

        # Normalise column names
        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

        mapping = self._get_column_mapping()
        self._validate_columns(df, mapping)

        rows: List[ParsedRow] = []
        for idx, raw in df.iterrows():
            row_num = idx + 2  # 1-based, header is row 1
            try:
                parsed = ParsedRow(
                    row_number=row_num,
                    transaction_date=self._parse_date(
                        raw.get(mapping["date"])
                    ),
                    description=str(
                        raw.get(mapping["description"], "")
                    ).strip(),
                    reference=str(
                        raw.get(mapping.get("reference", ""), "")
                    ).strip()
                    if mapping.get("reference")
                    else "",
                    credit_amount=self._parse_amount(
                        raw.get(mapping["credit"])
                    ),
                    debit_amount=self._parse_amount(
                        raw.get(mapping["debit"])
                    ),
                )
                rows.append(parsed)
            except Exception:
                logger.warning(
                    "Skipping unparseable row %d in %s statement",
                    row_num,
                    self.bank_name,
                    exc_info=True,
                )
        return rows
