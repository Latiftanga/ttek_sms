from datetime import date, datetime
from typing import Dict, Optional

from .base import BaseStatementParser


class StanbicParser(BaseStatementParser):
    bank_name = "Stanbic Bank"
    bank_code = "STANBIC"

    def _get_column_mapping(self) -> Dict[str, str]:
        return {
            "date": "date",
            "description": "description",
            "reference": "reference",
            "credit": "credits",
            "debit": "debits",
        }

    def _parse_date(self, value) -> Optional[date]:
        if value is None:
            return None
        try:
            return datetime.strptime(str(value).strip(), "%d-%b-%Y").date()
        except (ValueError, TypeError):
            return None
