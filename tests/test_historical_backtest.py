import unittest

from src.evaluation import completed_snapshots, run_historical_backtest
from src.generator.config import GeneratorConfig
from src.generator.simulation import SalesDataGenerator


class HistoricalBacktestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = SalesDataGenerator(GeneratorConfig(reps=20, accounts=20, opportunities=200)).generate()

    def test_completed_snapshots_do_not_extend_beyond_observed_history(self):
        snapshots, observed_through = completed_snapshots(self.dataset)
        self.assertTrue(snapshots)
        self.assertTrue(all(str(snapshot["horizon_end"])[:10] <= observed_through.isoformat() for snapshot in snapshots))

    def test_backtest_is_held_out_and_compares_both_methods(self):
        result = run_historical_backtest(self.dataset)
        self.assertEqual(result["status"], "complete")
        self.assertIn("weighted_pipeline", result["methods"])
        self.assertIn("conversion_model", result["methods"])
        self.assertTrue(result["evaluated_snapshot_ids"])
        self.assertTrue(result["periods"])
        self.assertIn("interval_coverage", result["methods"]["weighted_pipeline"]["overall"])
        self.assertGreater(result["model_metadata"]["held_out_opportunity_ids_excluded_from_training"], 0)
        self.assertEqual(result["evaluated_snapshots"], len(result["periods"]))
        self.assertTrue(any(item["reason"] == "horizon_not_complete_by_observed_through" for item in result["evaluation_eligibility"]))
        self.assertTrue(all(item["snapshot_id"] not in item.get("training_snapshot_ids", []) for item in result["evaluation_eligibility"] if item["status"] == "evaluated"))
