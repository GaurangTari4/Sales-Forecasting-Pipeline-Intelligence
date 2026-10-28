import unittest

from api.main import RunResponse, ScenarioRequest, _resolve_scenario
from src.forecasting.uncertainty import SCENARIOS


class ScenarioApiTests(unittest.TestCase):
    def test_named_preset_is_applied_when_no_override_is_submitted(self):
        self.assertEqual(_resolve_scenario(ScenarioRequest(name="CONSERVATIVE")), SCENARIOS["CONSERVATIVE"])
        self.assertEqual(_resolve_scenario(ScenarioRequest(name="BASE")), SCENARIOS["BASE"])

    def test_explicit_override_changes_only_the_requested_preset_field(self):
        result = _resolve_scenario(ScenarioRequest(name="CONSERVATIVE", booking_fraction=1.0))
        self.assertEqual(result.conversion_log_odds_shift, SCENARIOS["CONSERVATIVE"].conversion_log_odds_shift)
        self.assertEqual(result.slippage_days_shift, SCENARIOS["CONSERVATIVE"].slippage_days_shift)
        self.assertEqual(result.booking_fraction, 1.0)

    def test_custom_requires_an_explicit_assumption_and_records_activity_effect(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            _resolve_scenario(ScenarioRequest(name="CUSTOM"))
        result = _resolve_scenario(ScenarioRequest(name="CUSTOM", activity_effectiveness_log_odds=.2))
        self.assertEqual(result.name, "CUSTOM")
        self.assertEqual(result.activity_effectiveness_log_odds, .2)

    def test_custom_scenario_uses_a_safe_base_run_request(self):
        from api.main import RunRequest
        request = RunRequest(snapshot_id="FCST-2025-03-31-001", scenario="BASE")
        self.assertEqual(request.scenario, "BASE")

    def test_response_contract_exposes_applied_assumptions(self):
        response = RunResponse(forecast_id="run", snapshot_id="FCST-2025-03-31-001", scenario="BASE", totals={}, uncertainty={}, quota_attainment=None, model_metadata={}, exception_count=0, scenario_assumptions={"name":"BASE","booking_fraction":1.0})
        self.assertEqual(response.model_dump()["scenario_assumptions"]["booking_fraction"], 1.0)
