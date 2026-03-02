from datetime import date, datetime
from typing import Dict, Optional

from .base import BaseStatementParser


class EcobankParser(BaseStatementParser):
    bank_name = "Ecobank"
    bank_code = "ECOBANK"

    def _get_column_mapping(self) -> Dict[str, str]:
        return {
            "date": "value_date",
            "description": "narration",
            "reference": "reference_no",
            "credit": "credit",
            "debit": "debit",
        }

    def _parse_date(self, value) -> Optional[date]:
        if value is None:
            return None
        try:
            return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
