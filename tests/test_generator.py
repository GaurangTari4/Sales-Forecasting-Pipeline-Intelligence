from datetime import date
import unittest
from src.generator import GeneratorConfig, SalesDataGenerator
from src.generator.validation import validate
from src.generator.anomalies import detect_anomalies, detection_metrics, inject_controlled_anomalies
from src.generator.features import build_model_feature_matrix


class GeneratorTests(unittest.TestCase):
    def config(self):
        return GeneratorConfig(reps=8, accounts=12, opportunities=60, history_start=date(2025, 1, 1), history_end=date(2026, 12, 31), seed=20261022)

    def test_baseline_is_internally_consistent(self):
        data = SalesDataGenerator(self.config()).generate()
        validate(data)
        self.assertEqual(len(data["sales_reps"]), 8)
        self.assertEqual(len(data["accounts"]), 12)
        self.assertEqual(len(data["opportunities"]), 60)
        self.assertFalse(data["ground_truth_anomalies"])
        booked = {b["opportunity_id"] for b in data["historical_bookings"]}
        terminal = {}
        for row in data["stage_history"]:
            terminal[row["opportunity_id"]] = row["to_stage"]
        self.assertTrue(all(terminal[opportunity_id] == "CLOSED_WON" for opportunity_id in booked))

    def test_same_seed_produces_identical_records(self):
        first = SalesDataGenerator(self.config()).generate()
        second = SalesDataGenerator(self.config()).generate()
        self.assertEqual(first, second)

    def test_snapshots_are_point_in_time_views(self):
        data = SalesDataGenerator(self.config()).generate()
        headers = {row["forecast_snapshot_id"]: row for row in data["forecast_snapshots"]}
        for row in data["snapshot_opportunities"]:
            cutoff = headers[row["forecast_snapshot_id"]]["snapshot_at"]
            events = [event for event in data["stage_history"] if event["opportunity_id"] == row["opportunity_id"] and event["occurred_at"] <= cutoff]
            self.assertTrue(events)
            self.assertEqual(row["stage_at_snapshot"], events[-1]["to_stage"])
        self.assertEqual(len(headers), 8)

    def test_controlled_anomalies_have_perfect_detection_and_actions(self):
        anomalous = inject_controlled_anomalies(SalesDataGenerator(self.config()).generate())
        findings = detect_anomalies(anomalous)
        metrics = detection_metrics(findings, anomalous["ground_truth"])
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 1.0)
        expected_actions = {row["issue_type"]: row["expected_action"] for row in anomalous["ground_truth"]}
        self.assertEqual({row["issue_type"]: row["expected_action"] for row in findings}, expected_actions)

    def test_clean_baseline_has_no_controlled_anomaly_findings(self):
        self.assertEqual(detect_anomalies(SalesDataGenerator(self.config()).generate()), [])

    def test_ground_truth_never_enters_feature_matrix(self):
        anomalous = inject_controlled_anomalies(SalesDataGenerator(self.config()).generate())
        matrix = build_model_feature_matrix(anomalous)
        self.assertTrue(matrix)
        forbidden = {"issue_id", "issue_type", "expected_action", "latent_quality", "final_outcome"}
        self.assertFalse(forbidden & set(matrix[0]))
