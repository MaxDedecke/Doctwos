"""Compatibility exports for the former COBOL-local parser registry.

The shared registry now lives in ``core.registry``. These names remain
available for existing parser tests and integrations; new consumers should
import them from the shared module.
"""

from core.registry import ParserEntry, PrepareSourceHook, STRUCTURE_PARSERS, StructureParser
from cobol.prepare import prepare_copybook_index

_prepare_copybook_index = prepare_copybook_index

__all__ = [
    "ParserEntry",
    "PrepareSourceHook",
    "STRUCTURE_PARSERS",
    "StructureParser",
    "_prepare_copybook_index",
]
