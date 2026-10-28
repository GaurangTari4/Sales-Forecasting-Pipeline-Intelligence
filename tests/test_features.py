from datetime import date, datetime, timezone
import unittest

from src.features import FeatureLeakageError, assert_temporal_integrity, build_feature_dataset, build_labels
from src.generator import GeneratorConfig, SalesDataGenerator


UTC = timezone.utc


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def point_in_time_fixture():
    """A future call, close-date update, outcome and booking must not change Jan-31 features."""
    return {
        "territories": [{"territory_id": "TER-001", "region": "NA"}],
        "sales_reps": [{"sales_rep_id": "REP-000001", "role": "ACCOUNT_EXECUTIVE"}],
        "rep_territory_assignments": [{"sales_rep_id": "REP-000001", "territory_id": "TER-001", "effective_from": "2025-01-01", "effective_to": None}],
        "accounts": [{"account_id": "ACC-000001", "territory_id": "TER-001", "industry": "TECHNOLOGY", "employee_count": 1000}],
        "opportunities": [
            {"opportunity_id": "OPP-2026-000001", "account_id": "ACC-000001", "owner_rep_id": "REP-000001", "created_at": stamp("2026-01-01T09:00:00"), "original_expected_close_date": "2026-02-15", "transaction_currency": "USD", "initial_amount": "100.00", "product_type": "SUBSCRIPTION"},
            {"opportunity_id": "OPP-2026-000002", "account_id": "ACC-000001", "owner_rep_id": "REP-000001", "created_at": stamp("2026-02-01T09:00:00"), "original_expected_close_date": "2026-03-15", "transaction_currency": "USD", "initial_amount": "99.00", "product_type": "SERVICES"},
        ],
        "stage_history": [
            {"stage_event_id": "STG-OPP-2026-000001-001", "opportunity_id": "OPP-2026-000001", "event_sequence": 1, "to_stage": "PROSPECTING", "occurred_at": stamp("2026-01-01T09:00:00")},
            {"stage_event_id": "STG-OPP-2026-000001-002", "opportunity_id": "OPP-2026-000001", "event_sequence": 2, "to_stage": "CLOSED_WON", "occurred_at": stamp("2026-02-15T09:00:00")},
        ],
        "activities": [
            {"opportunity_id": "OPP-2026-000001", "activity_type": "CALL", "outcome": "COMPLETED", "occurred_at": stamp("2026-01-20T09:00:00")},
            {"opportunity_id": "OPP-2026-000001", "activity_type": "DEMO", "outcome": "COMPLETED", "occurred_at": stamp("2026-02-02T09:00:00")},
        ],
        "opportunity_change_events": [{"opportunity_id": "OPP-2026-000001", "change_type": "EXPECTED_CLOSE_DATE", "occurred_at": stamp("2026-02-02T09:00:00"), "new_value": {"date": "2026-04-01"}}],
        "stage_probability_versions": [
            {"stage_code": "PROSPECTING", "scenario": "BASE", "probability": "0.10", "effective_from": "2025-01-01", "effective_to": None},
            {"stage_code": "CLOSED_WON", "scenario": "BASE", "probability": "1.00", "effective_from": "2025-01-01", "effective_to": None},
        ],
        "historical_bookings": [{"opportunity_id": "OPP-2026-000001", "booking_amount": "100.00", "currency": "USD", "recognized_at": stamp("2026-02-16T09:00:00")}],
        "forecast_snapshots": [{"forecast_snapshot_id": "FCST-2026-01-31-001", "snapshot_at": stamp("2026-01-31T23:00:00"), "horizon_start": "2026-02-01", "horizon_end": "2026-03-31", "reporting_currency": "USD"}],
        "exchange_rates": [],
        "ground_truth": [{"issue_type": "not-a-feature"}],
        "ground_truth_outcomes": [{"final_outcome": "CLOSED_WON"}],
    }


class PointInTimeFeatureTests(unittest.TestCase):
    def test_future_events_do_not_modify_historical_features(self):
        rows = build_feature_dataset(point_in_time_fixture())
        self.assertEqual(len(rows), 1, "post-snapshot opportunity and pre-horizon closed state are excluded")
        row = rows[0]
        self.assertEqual(row["stage_at_snapshot"], "PROSPECTING")
        self.assertEqual(row["calls_30d"], 1)
        self.assertEqual(row["demos_30d"], 0)
        self.assertEqual(row["days_until_expected_close"], 15)
        self.assertEqual(row["prior_close_date_change_count"], 0)
        self.assertEqual(row["historical_conversion_rate"], 0.0)
        self.assertNotIn("final_outcome", row)
        self.assertNotIn("issue_type", row)

    def test_labels_are_separate_and_may_use_future_horizon_booking(self):
        rows = build_feature_dataset(point_in_time_fixture())
        labels = build_labels(point_in_time_fixture(), rows)
        self.assertEqual(labels[0]["realized_booking_reporting"], "100.00")
        self.assertTrue(labels[0]["booked_in_horizon"])
        self.assertNotIn("realized_booking_reporting", rows[0])

    def test_temporal_audit_detects_future_derived_feature_and_truth_column(self):
        data = point_in_time_fixture()
        rows = build_feature_dataset(data)
        assert_temporal_integrity(data, rows)
        rows[0]["calls_30d"] = 2  # would reflect the future Feb-2 demo if incorrectly derived
        with self.assertRaises(FeatureLeakageError):
            assert_temporal_integrity(data, rows)
        rows = build_feature_dataset(data)
        rows[0]["issue_type"] = "FUTURE_OUTCOME_LEAKAGE"
        with self.assertRaises(FeatureLeakageError):
            assert_temporal_integrity(data, rows)

    def test_generated_dataset_builds_deterministically(self):
        config = GeneratorConfig(reps=8, accounts=12, opportunities=60, history_start=date(2025, 1, 1), history_end=date(2026, 12, 31), seed=20261022)
        data = SalesDataGenerator(config).generate()
        first = build_feature_dataset(data); second = build_feature_dataset(data)
        self.assertEqual(first, second)
        self.assertTrue(first)
        for row in first:
            self.assertNotIn("ground_truth", row)
            self.assertGreaterEqual(row["opportunity_age_days"], 0)
