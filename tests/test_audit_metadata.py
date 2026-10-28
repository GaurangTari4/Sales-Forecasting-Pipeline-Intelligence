import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import main


def complete_run():
    run = {
        "forecast_id": "original-run", "snapshot_id": "FCST-2025-03-31-001", "scenario": "BASE",
        "snapshot_date": "2025-03-31T23:00:00+00:00", "forecast_executed_at": "2026-10-27T12:00:00+00:00",
        "model_version": "weighted-pipeline-v1", "feature_version": "pit-sales-features-v1", "seed": 20261022,
        "scenario_assumptions": {"name": "BASE", "conversion_log_odds_shift": 0.0, "slippage_days_shift": 0, "booking_fraction": 1.0},
        "data_hash": "i" * 64, "output_hash": "o" * 64,
        "model_metadata": {"opportunity_count": 7, "reporting_currency": "USD", "aggregation_dimensions": ["quarter", "territory_id"]},
        "totals": {}, "uncertainty": {}, "quota_attainment": None, "exception_count": 0,
        "opportunities": [], "exceptions": [], "evaluation": {},
    }
    return main._with_audit_metadata(run)


class AuditMetadataTests(unittest.TestCase):
    def test_canonical_metadata_is_complete_and_not_taken_from_duplicate_model_metadata(self):
        run = complete_run()
        audit = main._audit_metadata(run)
        self.assertEqual(audit["status"], "complete")
        self.assertEqual(audit["snapshot_at"], "2025-03-31T23:00:00+00:00")
        self.assertEqual(audit["forecast_executed_at"], "2026-10-27T12:00:00+00:00")
        self.assertEqual(audit["model_version"], "weighted-pipeline-v1")
        self.assertEqual(audit["opportunity_count"], 7)

    def test_legacy_metadata_is_explicitly_incomplete_without_inference(self):
        legacy = {"forecast_id": "legacy", "snapshot_id": "FCST-2025-03-31-001", "model_metadata": {"feature_version": "pit-sales-features-v1", "seed": 20261022, "snapshot_at": "2025-03-31T23:00:00+00:00", "opportunity_count": 7}}
        audit = main._audit_metadata(legacy)
        self.assertEqual(audit["status"], "legacy_metadata_incomplete")
        self.assertIsNone(audit["snapshot_at"])
        self.assertIsNone(audit["feature_version"])
        self.assertIn("input_hash", audit["missing_fields"])

    def test_response_schema_serializes_audit_fields(self):
        run = complete_run()
        response = main.RunResponse(**run).model_dump()
        self.assertEqual(response["snapshot_date"], run["snapshot_date"])
        self.assertEqual(response["seed"], 20261022)
        self.assertEqual(response["audit_metadata"]["input_hash"], "i" * 64)

    def test_reproducibility_replay_does_not_persist_or_store(self):
        original = complete_run()
        replay = complete_run()
        replay["forecast_id"] = "replay-run"
        with patch.object(main, "_get", return_value=original), patch.object(main, "_run", return_value=replay), patch.object(main.store, "save") as save, patch.object(main, "_persist_forecast_run") as persist:
            result = TestClient(main.app).post("/forecasts/original-run/reproducibility")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["status"], "reproducible")
        save.assert_not_called()
        persist.assert_not_called()
