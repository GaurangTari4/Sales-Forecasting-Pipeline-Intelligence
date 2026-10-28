import unittest
from src.evaluation import evaluate_forecasts
from src.evaluation.backtest import evaluate_anomalies

class EvaluationTests(unittest.TestCase):
 def test_hand_calculated_metrics_and_breakdowns(self):
  rows=[{"actual_booking_reporting":100,"actual_win":1,"weighted_pipeline_forecast":80,"weighted_pipeline_probability":.8,"scenario_forecast":90,"scenario_probability":.9,"scenario_p10":70,"scenario_p90":110,"label_horizon_end":"2026-03-31","quarter":"2026Q1","territory_id":"T1","stage_at_snapshot":"PROPOSAL","rep_segment":"NEW","deal_size_band":"SMALL"},{"actual_booking_reporting":0,"actual_win":0,"weighted_pipeline_forecast":20,"weighted_pipeline_probability":.2,"scenario_forecast":10,"scenario_probability":.1,"scenario_p10":0,"scenario_p90":20,"label_horizon_end":"2026-03-31","quarter":"2026Q1","territory_id":"T1","stage_at_snapshot":"PROPOSAL","rep_segment":"NEW","deal_size_band":"SMALL"}]
  out=evaluate_forecasts(rows,methods=("weighted_pipeline","scenario")); m=out["methods"]["weighted_pipeline"]["overall"]
  self.assertEqual(m["mae"],20); self.assertAlmostEqual(m["rmse"],20); self.assertEqual(m["wape"],.4); self.assertEqual(m["forecast_bias"],0); self.assertAlmostEqual(m["brier_score"],.04); self.assertEqual(out["methods"]["scenario"]["overall"]["interval_coverage"],1)
 def test_zero_wape_and_anomaly_f1(self):
  out=evaluate_forecasts([{"actual_booking_reporting":0,"weighted_pipeline_forecast":1}],methods=("weighted_pipeline",)); self.assertIsNone(out["methods"]["weighted_pipeline"]["overall"]["wape"])
  truth=[{"issue_type":"A","affected_record_id":"1","detection_rule_id":"x"}]; found=truth+[{"issue_type":"B","affected_record_id":"2","detection_rule_id":"x"}]
  self.assertAlmostEqual(evaluate_anomalies(found,truth)["f1"],2/3)
