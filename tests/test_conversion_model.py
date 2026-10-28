import unittest

from src.features.contracts import FEATURE_SCHEMA_VERSION
from src.forecasting.model import ModelInputError, build_conversion_labels, chronological_group_split, predict_conversion, train_conversion_model


def feature(opp, cutoff, stage="PROPOSAL", amount="100"):
    row = {"feature_schema_version": FEATURE_SCHEMA_VERSION, "forecast_snapshot_id": f"FCST-{cutoff[:10]}-001", "feature_cutoff_at": cutoff,
           "label_horizon_start": cutoff[:4] + "-" + ("04-01" if cutoff[5:7] == "03" else "07-01" if cutoff[5:7] == "06" else "10-01" if cutoff[5:7] == "09" else "12-31"), "label_horizon_end": "2026-12-31", "opportunity_id": opp, "owner_rep_id": "REP-000001", "amount_reporting_currency": amount, "reporting_currency": "USD", "stage_at_snapshot": stage, "effective_stage_probability": "0.5", "expected_close_date": "2026-12-15", "opportunity_age_days": 30, "days_until_expected_close": 60, "current_stage_duration_days": 10, "historical_conversion_rate": .3, "rep_historical_win_rate": .3, "territory_historical_win_rate": .3, "prior_close_date_change_count": 0, "observed_slippage_days": 0, "product_type": "SUBSCRIPTION", "account_segment": "MID_MARKET", "account_industry": "TECHNOLOGY", "territory_region": "NA", "rep_role": "ACCOUNT_EXECUTIVE", "territory_id": "TER-001"}
    for name in ("calls_30d","emails_30d","meetings_30d","demos_30d","calls_90d","emails_90d","meetings_90d","demos_90d","days_since_last_qualifying_activity"): row[name] = 1
    return row


class ConversionModelTests(unittest.TestCase):
    def test_grouped_chronological_split_and_training(self):
        dates = ["2025-03-31T23:00:00+00:00", "2025-06-30T23:00:00+00:00", "2025-09-30T23:00:00+00:00", "2025-12-31T23:00:00+00:00", "2026-03-31T23:00:00+00:00", "2026-06-30T23:00:00+00:00", "2026-09-30T23:00:00+00:00", "2026-12-31T23:00:00+00:00"]
        rows = [feature(f"OPP-{i:03d}", day, "NEGOTIATION" if i % 2 else "PROPOSAL") for i, day in enumerate(dates * 3)]
        labels = [{"forecast_snapshot_id": r["forecast_snapshot_id"], "opportunity_id": r["opportunity_id"], "conversion_within_horizon": int(i % 2 == 0)} for i,r in enumerate(rows)]
        splits = chronological_group_split(rows, labels)
        ids = [set(r["opportunity_id"] for r,_ in values) for values in splits.values()]
        self.assertFalse(ids[0] & ids[1] or ids[1] & ids[2] or ids[0] & ids[2])
        model, report = train_conversion_model(rows, labels)
        self.assertIn("brier_score", report["test"]); self.assertIn("baseline_test", report)
        self.assertEqual(len(predict_conversion(model, [rows[-1]])), 1)

    def test_schema_and_truth_leakage_are_rejected(self):
        row = feature("OPP-1", "2025-03-31T23:00:00+00:00"); row["final_outcome"] = "CLOSED_WON"
        with self.assertRaises(ModelInputError): train_conversion_model([row], [])
