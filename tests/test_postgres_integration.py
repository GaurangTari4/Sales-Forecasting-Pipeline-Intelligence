"""Real PostgreSQL integration coverage; guarded against non-disposable targets."""
from __future__ import annotations

import copy
import importlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from urllib.parse import urlparse
from unittest.mock import patch


URL = os.environ.get("SALES_FORECAST_TEST_DATABASE_URL")
DEPENDENCIES_READY = all(importlib.util.find_spec(name) is not None for name in ("psycopg", "fastapi", "httpx"))
SKIP_REASON = "set SALES_FORECAST_TEST_DATABASE_URL to a disposable *_test PostgreSQL database and install psycopg, fastapi, and httpx"


@unittest.skipUnless(URL and DEPENDENCIES_READY, SKIP_REASON)
class PostgresIntegrationTests(unittest.TestCase):
    """These tests erase only a database explicitly named with the *_test suffix."""

    @classmethod
    def setUpClass(cls):
        parsed = urlparse(URL)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.path.lstrip("/").endswith("_test"):
            raise RuntimeError("SALES_FORECAST_TEST_DATABASE_URL must target a disposable database whose name ends in _test")
        from src.generator.config import GeneratorConfig
        from src.generator.export import write_exports
        from src.generator.simulation import SalesDataGenerator
        from src.persistence.database import Database, ingest_generated_dataset

        cls.database = Database(URL)
        with cls.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        cls.database.migrate()
        generator = SalesDataGenerator(GeneratorConfig(reps=8, accounts=8, opportunities=48))
        cls.dataset = generator.generate()
        cls.temp = tempfile.TemporaryDirectory()
        cls.dataset_dir = Path(cls.temp.name) / "dataset"
        write_exports(cls.dataset, cls.dataset_dir, generator.manifest())
        ingest_generated_dataset(cls.database, cls.dataset)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def _scalar(self, sql, parameters=()):
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, parameters)
                return cursor.fetchone()[0]

    def test_schema_foreign_keys_and_repeatable_ingestion(self):
        from src.persistence.database import ingest_generated_dataset
        self.assertEqual(self._scalar("SELECT count(*) FROM opportunities"), len(self.dataset["opportunities"]))
        self.assertEqual(self._scalar("SELECT count(*) FROM opportunities o LEFT JOIN accounts a ON a.account_id=o.account_id WHERE a.account_id IS NULL"), 0)
        ingest_generated_dataset(self.database, self.dataset)
        self.assertEqual(self._scalar("SELECT count(*) FROM opportunities"), len(self.dataset["opportunities"]))

    def test_failed_ingestion_rolls_back(self):
        from src.persistence.database import ingest_generated_dataset
        bad = {"opportunities": [copy.deepcopy(self.dataset["opportunities"][0])]}
        bad["opportunities"][0]["opportunity_id"] = "OPP-2025-999999"
        bad["opportunities"][0]["account_id"] = "ACC-999999"
        with self.assertRaises(Exception):
            ingest_generated_dataset(self.database, bad)
        self.assertEqual(self._scalar("SELECT count(*) FROM opportunities WHERE opportunity_id='OPP-2025-999999'"), 0)

    def test_finalized_snapshot_is_immutable(self):
        snapshot = self.dataset["forecast_snapshots"][0]["forecast_snapshot_id"]
        original_status = self._scalar("SELECT status FROM forecast_snapshots WHERE forecast_snapshot_id=%s", (snapshot,))
        with self.assertRaises(Exception):
            with self.database.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE forecast_snapshots SET status='DRAFT' WHERE forecast_snapshot_id=%s", (snapshot,))
        self.assertEqual(self._scalar("SELECT status FROM forecast_snapshots WHERE forecast_snapshot_id=%s", (snapshot,)), original_status)

    def test_forecast_history_persistence_and_intervals(self):
        from src.persistence.database import store_forecast_run
        snapshot = self.dataset["forecast_snapshots"][0]["forecast_snapshot_id"]
        opportunity = self.dataset["opportunities"][0]["opportunity_id"]
        metadata = {"model_version": "integration-model-v1", "feature_version": "integration-features-v1", "scenario": "BASE", "stage_probability_version_name": "synthetic-v1", "data_hash": "a" * 64, "assumptions": {"seed": 20261022}}
        rows = lambda run_id: [{"forecast_run_id": run_id, "opportunity_id": opportunity, "expected_booking_reporting": 50, "lower_booking_reporting": 0, "upper_booking_reporting": 100, "win_probability": .5}]
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        store_forecast_run(self.database, first, snapshot, metadata, rows(first))
        store_forecast_run(self.database, second, snapshot, metadata, rows(second))
        self.assertEqual(self._scalar("SELECT count(*) FROM forecast_runs WHERE model_version='integration-model-v1'"), 2)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT forecast_snapshot_id, model_version, feature_version, assumptions->>'seed' FROM forecast_runs WHERE forecast_run_id=%s", (first,))
                self.assertEqual(cursor.fetchone(), (snapshot, "integration-model-v1", "integration-features-v1", "20261022"))
                cursor.execute("SELECT expected_booking_reporting, lower_booking_reporting, upper_booking_reporting FROM opportunity_forecasts WHERE forecast_run_id=%s", (first,))
                self.assertEqual(tuple(float(value) for value in cursor.fetchone()), (50.0, 0.0, 100.0))

    def test_api_run_persists_and_survives_file_store_restart(self):
        from fastapi.testclient import TestClient
        environment = {"DATABASE_URL": URL, "FORECAST_DATASET_DIR": str(self.dataset_dir), "API_RUNS_DIR": str(Path(self.temp.name) / "runs")}
        with patch.dict(os.environ, environment, clear=False):
            api = importlib.import_module("api.main")
            api.store = api.FileRunStore()
            client = TestClient(api.app)
            self.assertEqual(client.get("/health").status_code, 200)
            created = client.post("/forecasts/run", json={"snapshot_id": self.dataset["forecast_snapshots"][0]["forecast_snapshot_id"], "scenario": "BASE", "reporting_currency": "USD", "dimensions": ["quarter", "territory_id"]})
            self.assertEqual(created.status_code, 201, created.text)
            run = created.json()
            self.assertEqual(self._scalar("SELECT count(*) FROM forecast_runs WHERE forecast_run_id=%s", (run["forecast_id"],)), 1)
            self.assertGreater(self._scalar("SELECT count(*) FROM opportunity_forecasts WHERE forecast_run_id=%s", (run["forecast_id"],)), 0)
            self.assertEqual(run["model_version"], "weighted-pipeline-v1")
            self.assertEqual(run["feature_version"], "pit-sales-features-v1")
            self.assertIsNotNone(run["seed"])
            self.assertEqual(run["audit_metadata"]["status"], "complete")
            self.assertGreaterEqual(run["uncertainty"]["probability_of_missing_quota"], 0)
            self.assertLessEqual(run["uncertainty"]["probability_of_missing_quota"], 1)
            custom = client.post(
                f"/forecasts/{run['forecast_id']}/scenarios",
                json={"name": "CUSTOM", "conversion_log_odds_shift": -.2, "slippage_days_shift": 21,
                      "booking_fraction": .9, "activity_effectiveness_log_odds": -.1},
            )
            self.assertEqual(custom.status_code, 201, custom.text)
            self.assertEqual(custom.json()["scenario"], "CUSTOM")
            self.assertEqual(custom.json()["scenario_assumptions"]["activity_effectiveness_log_odds"], -.1)
            with self.database.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT data_hash, assumptions->>'seed', assumptions->>'output_hash', assumptions->>'opportunity_count' FROM forecast_runs WHERE forecast_run_id=%s", (run["forecast_id"],))
                    data_hash, seed, output_hash, opportunity_count = cursor.fetchone()
            self.assertEqual(data_hash, run["data_hash"])
            self.assertEqual(seed, str(run["seed"]))
            self.assertEqual(output_hash, run["output_hash"])
            self.assertEqual(opportunity_count, str(run["model_metadata"]["opportunity_count"]))
            api.store = api.FileRunStore()  # Simulate API-process restart against persistent artifact storage.
            retrieved = client.get(f"/forecasts/{run['forecast_id']}")
            self.assertEqual(retrieved.status_code, 200)
            self.assertEqual(retrieved.json()["snapshot_id"], run["snapshot_id"])
            self.assertEqual(retrieved.json()["audit_metadata"]["output_hash"], run["output_hash"])

    def test_api_rejects_invalid_snapshot_and_reports_database_error(self):
        from fastapi.testclient import TestClient
        environment = {"DATABASE_URL": URL, "FORECAST_DATASET_DIR": str(self.dataset_dir), "API_RUNS_DIR": str(Path(self.temp.name) / "runs")}
        with patch.dict(os.environ, environment, clear=False):
            api = importlib.import_module("api.main")
            api.store = api.FileRunStore()
            client = TestClient(api.app)
            self.assertEqual(client.post("/forecasts/run", json={"snapshot_id": "FCST-2020-01-31-001"}).status_code, 404)
            with patch.object(api.Database, "connect", side_effect=RuntimeError("test database unavailable")):
                self.assertEqual(client.get("/health").status_code, 503)
