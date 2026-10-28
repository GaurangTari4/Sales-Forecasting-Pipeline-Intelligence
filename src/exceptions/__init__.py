"""Auditable rule-based business exceptions and decision support."""
from .engine import detect_exceptions, apply_permitted_corrections
from .reporting import write_exception_report
__all__=["detect_exceptions","apply_permitted_corrections","write_exception_report"]
