import copy
import unittest
from datetime import date

from src.generator.anomalies import inject_controlled_anomalies
from src.generator.config import GeneratorConfig
from src.generator.simulation import SalesDataGenerator
from src.validation.engine import validate_dataset


class EffectiveProbabilityValidationTests(unittest.TestCase):
    def test_probability_uses_the_version_effective_at_snapshot(self):
        baseline = SalesDataGenerator(GeneratorConfig(reps=20, accounts=20, opportunities=200)).generate()
        dataset = copy.deepcopy(inject_controlled_anomalies(baseline))
        input_row = next(row for row in dataset["anomalous_forecast_inputs"] if row["input_id"] == "AFI-003")
        stage = next(
            row["stage_at_snapshot"]
            for row in dataset["snapshot_opportunities"]
            if row["forecast_snapshot_id"] == input_row["forecast_snapshot_id"]
            and row["opportunity_id"] == input_row["opportunity_id"]
        )
        # A later non-overlapping version must not replace the configuration
        # effective at AFI-003's snapshot.
        for row in dataset["stage_probability_versions"]:
            if row["stage_code"] == stage:
                row["effective_to"] = date(2025, 6, 30)
        dataset["stage_probability_versions"].append({
            "stage_probability_version_id": "99", "version_name": "synthetic-v2",
            "stage_code": stage, "scenario": "BASE", "probability": "0.99",
            "effective_from": date(2025, 7, 1), "effective_to": None, "created_at": "2025-07-01T00:00:00+00:00",
        })
        findings = validate_dataset(dataset).to_dict()["results"]
        mismatch = next(item for item in findings if item["affected_record_id"] == "AFI-003")
        self.assertEqual(mismatch["issue_type"], "STAGE_PROBABILITY_MISMATCH")
