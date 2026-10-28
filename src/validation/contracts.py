from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Action(str, Enum):
    PASS = "PASS"
    FLAG_FOR_REVIEW = "FLAG_FOR_REVIEW"
    QUARANTINE = "QUARANTINE"


@dataclass(frozen=True)
class ValidationResult:
    rule_id: str
    severity: Severity
    affected_entity: str
    affected_record_id: str
    issue_type: str
    explanation: str
    recommended_action: Action

    def to_dict(self) -> dict[str, str]:
        return {key: (value.value if isinstance(value, Enum) else value) for key, value in asdict(self).items()}


@dataclass
class ValidationReport:
    records_checked: int
    results: list[ValidationResult] = field(default_factory=list)
    known_anomalies_detected: int = 0

    @property
    def errors(self) -> int: return sum(r.severity == Severity.ERROR for r in self.results)
    @property
    def warnings(self) -> int: return sum(r.severity == Severity.WARNING for r in self.results)
    @property
    def quarantined_records(self) -> int: return len({(r.affected_entity, r.affected_record_id) for r in self.results if r.recommended_action == Action.QUARANTINE})

    def add(self, **kwargs: Any) -> None: self.results.append(ValidationResult(**kwargs))

    def to_dict(self) -> dict[str, Any]:
        return {"records_checked": self.records_checked, "errors": self.errors, "warnings": self.warnings,
                "quarantined_records": self.quarantined_records, "known_anomalies_detected": self.known_anomalies_detected,
                "results": [result.to_dict() for result in self.results]}
