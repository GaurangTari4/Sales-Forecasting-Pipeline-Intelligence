import unittest

from src.forecasting import BaselineConfig, ForecastInputError, forecast_weighted_pipeline


def row(opportunity_id, stage, amount="100.00", close="2026-02-15", probability="0.80", **extra):
    return {"forecast_snapshot_id": "FCST-2026-01-31-001", "opportunity_id": opportunity_id,
            "feature_cutoff_at": "2026-01-31T23:00:00+00:00", "label_horizon_start": "2026-02-01",
            "label_horizon_end": "2026-03-31", "reporting_currency": "USD",
            "amount_reporting_currency": amount, "stage_at_snapshot": stage,
            "effective_stage_probability": probability, "expected_close_date": close,
            "prior_close_date_change_count": 0, "territory_id": "TER-001",
            "owner_rep_id": "REP-000001", "product_type": "SUBSCRIPTION", **extra}


class WeightedPipelineTests(unittest.TestCase):
    def test_high_probability_deal_in_horizon_uses_each_probability_once(self):
        result = forecast_weighted_pipeline([row("OPP-1", "NEGOTIATION", "1000.00", probability="0.80")])
        contribution = result["contributions"][0]
        # 1000 × P(eventual win=.80) × P(in horizon | win=.80) × fraction 1.0
        self.assertEqual(contribution["forecast_bookings_future_horizon_reporting"], "640.00")
        self.assertEqual(result["totals"]["open_pipeline_reporting"], "1000.00")
        self.assertEqual(result["totals"]["weighted_expected_bookings_reporting"], "640.00")

    def test_slipping_deal_receives_low_timing_probability(self):
        result = forecast_weighted_pipeline([row("OPP-2", "PROPOSAL", "1000.00", close="2026-05-01", probability="0.50")])
        self.assertEqual(result["contributions"][0]["conditional_booking_in_horizon_probability"], "0.10")
        self.assertEqual(result["totals"]["forecast_bookings_future_horizon_reporting"], "50.00")

    def test_recognized_won_and_lost_deals_do_not_become_future_bookings(self):
        result = forecast_weighted_pipeline([row("OPP-3", "CLOSED_WON", "900.00", recognized_booking_reporting="900.00"), row("OPP-4", "CLOSED_LOST", "700.00")])
        self.assertEqual(result["totals"]["closed_won_bookings_as_of_reporting"], "900.00")
        self.assertEqual(result["totals"]["forecast_bookings_future_horizon_reporting"], "0.00")
        self.assertEqual(result["totals"]["open_pipeline_reporting"], "0.00")

    def test_duplicate_snapshot_opportunity_is_rejected(self):
        with self.assertRaises(ForecastInputError): forecast_weighted_pipeline([row("OPP-5", "PROPOSAL"), row("OPP-5", "PROPOSAL")])

    def test_missing_or_invalid_currency_rate_is_rejected(self):
        raw = row("OPP-6", "PROPOSAL", amount=None)
        raw.pop("amount_reporting_currency"); raw.update({"amount_transaction_currency": "100", "transaction_currency": "EUR"})
        with self.assertRaises(ForecastInputError): forecast_weighted_pipeline([raw])
        invalid = BaselineConfig(exchange_rates=({"from_currency": "EUR", "to_currency": "USD", "rate_date": "2026-01-30", "rate": "0"},))
        with self.assertRaises(ForecastInputError): forecast_weighted_pipeline([raw], invalid)

    def test_aggregation_reconciles_selected_dimensions(self):
        result = forecast_weighted_pipeline([row("OPP-7", "PROPOSAL", "100.00", probability="0.50"), row("OPP-8", "PROPOSAL", "100.00", probability="0.50")], group_by=("quarter", "territory_id"))
        self.assertEqual(result["aggregates"][0]["opportunity_count"], 2)
        self.assertEqual(result["aggregates"][0]["forecast_bookings_future_horizon_reporting"], result["totals"]["forecast_bookings_future_horizon_reporting"])
