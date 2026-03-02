"""
Bank statement parsers — one per supported bank, plus a generic fallback.
"""

from .base import BaseStatementParser, ParsedRow
from .gcb import GCBParser
from .ecobank import EcobankParser
from .stanbic import StanbicParser
from .fidelity import FidelityParser
from .generic import GenericParser


def get_statement_parser(bank_code: str) -> BaseStatementParser:
    """Factory: return the correct parser for a bank code."""
    parsers = {
        "GCB": GCBParser,
        "ECOBANK": EcobankParser,
        "STANBIC": StanbicParser,
        "FIDELITY": FidelityParser,
        "GENERIC": GenericParser,
    }
    parser_class = parsers.get(bank_code)
    if not parser_class:
        raise ValueError(f"Unsupported bank: {bank_code}")
    return parser_class()


__all__ = [
    "BaseStatementParser",
    "ParsedRow",
    "GCBParser",
    "EcobankParser",
    "StanbicParser",
    "FidelityParser",
    "GenericParser",
    "get_statement_parser",
]
