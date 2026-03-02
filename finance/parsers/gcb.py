from datetime import date, datetime
from typing import Dict, Optional

from .base import BaseStatementParser


class GCBParser(BaseStatementParser):
    bank_name = "GCB Bank"
    bank_code = "GCB"

    def _get_column_mapping(self) -> Dict[str, str]:
        return {
            "date": "transaction_date",
            "description": "description",
            "reference": "reference",
            "credit": "credit",
            "debit": "debit",
        }

    def _parse_date(self, value) -> Optional[date]:
        if value is None:
            return None
        try:
            return datetime.strptime(str(value).strip(), "%d/%m/%Y").date()
        except (ValueError, TypeError):
            return None
