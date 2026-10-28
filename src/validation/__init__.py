"""Read-only data-quality and integrity validation."""
from .engine import ValidationReport, validate_dataset

__all__ = ["ValidationReport", "validate_dataset"]
