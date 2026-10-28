import json
import unittest
from io import BytesIO
from unittest.mock import patch

from dashboard.client import ForecastApiClient, ForecastApiError
from dashboard.components import render_labeled_value
from dashboard.formatting import display_date, display_datetime, exception_evidence_summary, filter_exceptions, filter_opportunities, humanize_identifier, money, opportunity_display_row, percent, scenario_comparison_rows, scenario_percent_change, signed_number


class _Response:
    def __init__(self, payload): self.payload = payload
    def read(self): return json.dumps(self.payload).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self, *args): return False


class DashboardTests(unittest.TestCase):
    def test_money_and_percent_do_not_fabricate_missing_values(self):
        self.assertEqual(money("1200.5", "USD"), "$1,200.50")
        self.assertEqual(money(None), "Not available")
        self.assertEqual(percent(.875), "87.5%")
        self.assertEqual(percent(None), "Not available")

    def test_business_display_helpers_preserve_missing_values_and_format_dates(self):
        self.assertEqual(display_date("2026-03-31"), "31 Mar 2026")
        self.assertEqual(display_datetime("2026-03-31T14:30:00+00:00"), "31 Mar 2026, 14:30 UTC")
        self.assertEqual(display_date(None), "Not available")
        self.assertEqual(humanize_identifier("MATERIAL_DATA_QUALITY"), "Material Data Quality")
        self.assertEqual(signed_number(-3, " days"), "-3.00 days")
        self.assertEqual(signed_number(None), "Not available")

    def test_display_filters_do_not_calculate_forecasts(self):
        rows = [{"quarter": "2026Q1", "territory_id": "TER-001", "owner_rep_id": "REP-000001", "stage_at_snapshot": "PROPOSAL", "product_type": "SUBSCRIPTION"}, {"quarter": "2026Q2", "territory_id": "TER-002", "owner_rep_id": "REP-000002", "stage_at_snapshot": "DISCOVERY", "product_type": "SERVICES"}]
        self.assertEqual(filter_opportunities(rows, quarters=["2026Q1"]), rows[:1])

    def test_exception_filters_and_evidence_rendering(self):
        rows = [{"exception_type":"FORECAST_GAP_TO_QUOTA","severity":"HIGH","owner_rep_id":"REP-1","territory_id":"TER-1","forecast_run_id":"run-1","evidence":{"quota":"100.00","forecast":25,"gap":75,"attainment":.25}}]
        self.assertEqual(filter_exceptions(rows, types=["FORECAST_GAP_TO_QUOTA"], severities=["HIGH"], reps=["REP-1"], territories=["TER-1"], forecast_runs=["run-1"]), rows)
        self.assertIn("Quota $100.00", exception_evidence_summary(rows[0]))
        self.assertIn("gap $75.00", exception_evidence_summary(rows[0]))

    def test_scenario_comparison_rows_show_base_adjusted_and_percent_change(self):
        rows = scenario_comparison_rows({"totals":{"expected_booking_reporting":100},"uncertainty":{"p10":10,"p50":50,"p90":90}}, {"totals":{"expected_booking_reporting":80},"uncertainty":{"p10":0,"p50":40,"p90":100}})
        self.assertEqual(rows[0], {"Metric":"Expected revenue","Base":100.0,"Adjusted":80.0,"Change %":-.2})
        self.assertEqual(rows[-1]["Metric"], "P90")

    def test_zero_baseline_change_is_unavailable_not_nan_or_infinite(self):
        rows = scenario_comparison_rows({"totals":{"expected_booking_reporting":0},"uncertainty":{"p10":0,"p50":0,"p90":0}}, {"totals":{"expected_booking_reporting":1},"uncertainty":{"p10":0,"p50":1,"p90":2}})
        self.assertTrue(all(row["Change %"] is None for row in rows))
        self.assertTrue(all(scenario_percent_change(row["Change %"]) == "N/A" for row in rows))

    def test_opportunity_display_uses_business_formats_without_changing_source_values(self):
        row = {"amount_reporting_currency": 1000, "expected_booking_reporting": 250, "P10_booking_reporting": 0, "P50_booking_reporting": 100, "P90_booking_reporting": 500, "effective_stage_probability": .25, "expected_close_date": "2026-06-30", "feature_cutoff_at": "2026-03-31T00:00:00+00:00"}
        rendered = opportunity_display_row(row)
        self.assertEqual(rendered["amount_reporting_currency"], "$1,000.00")
        self.assertEqual(rendered["effective_stage_probability"], "25.0%")
        self.assertEqual(rendered["feature_cutoff_at"], "2026-03-31")
        self.assertEqual(row["amount_reporting_currency"], 1000)

    def test_exception_card_label_value_renderer_uses_one_write_value(self):
        class FakeContainer:
            def __init__(self): self.markdowns=[]; self.writes=[]
            def markdown(self, value): self.markdowns.append(value)
            def write(self, value): self.writes.append(value)
        container = FakeContainer()
        render_labeled_value(container, "Affected entity", "SALES_REP")
        self.assertEqual(container.markdowns, ["**Affected entity**"])
        self.assertEqual(container.writes, ["SALES_REP"])

    @patch("dashboard.client.urlopen")
    def test_client_sends_forecast_request_to_api(self, mocked_open):
        mocked_open.return_value = _Response({"forecast_id": "run-1"})
        result = ForecastApiClient("http://api.test").run_forecast({"snapshot_id": "FCST-2025-03-31-001"})
        self.assertEqual(result["forecast_id"], "run-1")
        request = mocked_open.call_args.args[0]
        self.assertEqual(request.full_url, "http://api.test/forecasts/run")
        self.assertEqual(request.get_method(), "POST")
