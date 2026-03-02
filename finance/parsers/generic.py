from datetime import date, datetime
from typing import Dict, Optional

from .base import BaseStatementParser

# Formats to try in order
_DATE_FORMATS = [
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
]


class GenericParser(BaseStatementParser):
    bank_name = "Generic"
    bank_code = "GENERIC"

    def _get_column_mapping(self) -> Dict[str, str]:
        return {
            "date": "date",
            "description": "description",
            "reference": "reference",
            "credit": "credit",
            "debit": "debit",
        }

    def _parse_date(self, value) -> Optional[date]:
        if value is None:
            return None
        text = str(value).strip()[:10]
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date()
            except (ValueError, TypeError):
                continue
        return None
