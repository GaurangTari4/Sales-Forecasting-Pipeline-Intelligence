import unittest

from api.main import _scoped_quota_total


class ForecastScopeTests(unittest.TestCase):
    def test_quota_uses_only_reps_with_eligible_snapshot_pipeline(self):
        header = {"horizon_end": "2025-06-30", "reporting_currency": "USD"}
        features = [
            {"owner_rep_id": "REP-000001", "territory_id": "TER-001"},
            {"owner_rep_id": "REP-000002", "territory_id": "TER-002"},
        ]
        data = {"quotas": [
            {"sales_rep_id": "REP-000001", "fiscal_quarter": "2025Q2", "quota_amount": "100", "currency": "USD"},
            {"sales_rep_id": "REP-000002", "fiscal_quarter": "2025Q2", "quota_amount": "200", "currency": "USD"},
            {"sales_rep_id": "REP-000003", "fiscal_quarter": "2025Q2", "quota_amount": "999", "currency": "USD"},
        ]}
        total, scope = _scoped_quota_total(data, header, features)
        self.assertEqual(total, 300)
        self.assertEqual(scope["eligible_reps"], ["REP-000001", "REP-000002"])
        self.assertEqual(scope["eligible_territories"], ["TER-001", "TER-002"])
