from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path


@dataclass(frozen=True)
class GeneratorConfig:
    reps: int = 2_000
    accounts: int = 2_000
    opportunities: int = 20_000
    history_start: date = date(2025, 1, 1)
    history_end: date = date(2026, 12, 31)
    snapshot_frequency: str = "QUARTERLY"
    seed: int = 20261022
    anomaly_injection_rate: float = 0.0
    reporting_currency: str = "USD"

    def __post_init__(self):
        if min(self.reps, self.accounts, self.opportunities) < 1:
            raise ValueError("entity counts must be positive")
        if self.history_end <= self.history_start:
            raise ValueError("history_end must be after history_start")
        if self.snapshot_frequency not in {"MONTHLY", "QUARTERLY"}:
            raise ValueError("snapshot_frequency must be MONTHLY or QUARTERLY")
        if not 0 <= self.anomaly_injection_rate <= 1:
            raise ValueError("anomaly_injection_rate must be between 0 and 1")
        if len(self.reporting_currency) != 3 or not self.reporting_currency.isupper():
            raise ValueError("reporting_currency must be an uppercase ISO-4217 code")

    @classmethod
    def from_json(cls, path: Path) -> "GeneratorConfig":
        values = json.loads(path.read_text(encoding="utf-8"))
        values["history_start"] = date.fromisoformat(values["history_start"])
        values["history_end"] = date.fromisoformat(values["history_end"])
        return cls(**values)
