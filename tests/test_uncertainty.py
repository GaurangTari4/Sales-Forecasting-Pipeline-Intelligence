import unittest

from src.forecasting.uncertainty import SCENARIOS, ScenarioConfig, evaluate_intervals, opportunity_scenario_contributions, simulate_bookings


def rows():
    return [{"forecast_snapshot_id":"FCST-2026-01-31-001","opportunity_id":"OPP-1","label_horizon_start":"2026-02-01","label_horizon_end":"2026-03-31","expected_close_date":"2026-02-15","prior_close_date_change_count":0,"calls_30d":1,"meetings_30d":1,"demos_30d":0,"amount_reporting_currency":"100.00","reporting_currency":"USD","territory_id":"TER-001","owner_rep_id":"REP-000001","product_type":"SUBSCRIPTION"}]
def predictions(): return [{"forecast_snapshot_id":"FCST-2026-01-31-001","opportunity_id":"OPP-1","conversion_probability":.5}]

class UncertaintyTests(unittest.TestCase):
    def test_probability_bounds_and_scenario_monotonicity(self):
        conservative = opportunity_scenario_contributions(rows(), predictions(), SCENARIOS["CONSERVATIVE"])[0]
        base = opportunity_scenario_contributions(rows(), predictions(), SCENARIOS["BASE"])[0]
        optimistic = opportunity_scenario_contributions(rows(), predictions(), SCENARIOS["OPTIMISTIC"])[0]
        self.assertTrue(0 <= conservative["joint_booking_within_horizon_probability"] <= 1)
        self.assertLess(conservative["expected_booking_reporting"], base["expected_booking_reporting"])
        self.assertLess(base["expected_booking_reporting"], optimistic["expected_booking_reporting"])

    def test_reproducibility_and_reconciliation(self):
        first = simulate_bookings(rows(), predictions(), simulations=200, seed=9)
        second = simulate_bookings(rows(), predictions(), simulations=200, seed=9)
        self.assertEqual(first, second)
        aggregate = first["aggregates"][0]
        self.assertEqual(aggregate["mean_booking_reporting"], first["contributions"][0]["mean_simulated_booking_reporting"])
        metrics = evaluate_intervals(first, [{"forecast_snapshot_id":"FCST-2026-01-31-001","opportunity_id":"OPP-1","realized_booking_reporting":"100.00"}])
        self.assertEqual(metrics["records"], 1)

    def test_multi_opportunity_aggregate_reconciles_to_contributions(self):
        second = dict(rows()[0]); second["opportunity_id"] = "OPP-2"; second["amount_reporting_currency"] = "50.00"
        prediction = dict(predictions()[0]); prediction["opportunity_id"] = "OPP-2"
        result = simulate_bookings(rows() + [second], predictions() + [prediction], simulations=300, seed=11, group_by=("quarter", "territory_id"))
        aggregate = result["aggregates"][0]
        self.assertAlmostEqual(aggregate["mean_booking_reporting"], sum(r["mean_simulated_booking_reporting"] for r in result["contributions"]))
        self.assertLessEqual(aggregate["P10_booking_reporting"], aggregate["P50_booking_reporting"])
        self.assertLessEqual(aggregate["P50_booking_reporting"], aggregate["P90_booking_reporting"])

    def test_portfolio_quantiles_come_from_portfolio_simulations(self):
        second = dict(rows()[0]); second.update({"opportunity_id": "OPP-2", "territory_id": "TER-002"})
        prediction = dict(predictions()[0]); prediction["opportunity_id"] = "OPP-2"
        grouped = simulate_bookings(rows() + [second], predictions() + [prediction], simulations=300, seed=17, group_by=("quarter", "territory_id"))
        portfolio = simulate_bookings(rows() + [second], predictions() + [prediction], simulations=300, seed=17, group_by=())["aggregates"][0]
        for field in ("P10_booking_reporting", "P50_booking_reporting", "P90_booking_reporting", "mean_booking_reporting"):
            self.assertEqual(grouped["portfolio"][field], portfolio[field])

    def test_directional_scenario_changes_and_neutral_base(self):
        base = opportunity_scenario_contributions(rows(), predictions(), SCENARIOS["BASE"])[0]["expected_booking_reporting"]
        neutral = opportunity_scenario_contributions(rows(), predictions(), ScenarioConfig("BASE"))[0]["expected_booking_reporting"]
        lower_conversion = opportunity_scenario_contributions(rows(), predictions(), ScenarioConfig("CUSTOM", conversion_log_odds_shift=-.4))[0]["expected_booking_reporting"]
        more_slippage = opportunity_scenario_contributions(rows(), predictions(), ScenarioConfig("CUSTOM", slippage_days_shift=30))[0]["expected_booking_reporting"]
        lower_fraction = opportunity_scenario_contributions(rows(), predictions(), ScenarioConfig("CUSTOM", booking_fraction=.8))[0]["expected_booking_reporting"]
        self.assertEqual(base, neutral)
        self.assertLess(lower_conversion, base)
        self.assertLess(more_slippage, base)
        self.assertLess(lower_fraction, base)
