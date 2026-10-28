import unittest
from src.exceptions import detect_exceptions
class ExceptionTests(unittest.TestCase):
 def test_priority_action_and_traceability(self):
  rows=[{'forecast_snapshot_id':'S','opportunity_id':'O1','owner_rep_id':'R1','territory_id':'T','stage_at_snapshot':'PROPOSAL','opportunity_age_days':200,'current_stage_duration_days':100,'days_until_expected_close':3,'prior_close_date_change_count':2,'rep_active':False}]
  fc=[{'forecast_snapshot_id':'S','opportunity_id':'O1','owner_rep_id':'R1','territory_id':'T','expected_booking_reporting':'120000'}]
  result=detect_exceptions(rows,fc,now='2026-01-31T00:00:00Z'); types={x['exception_type']:x for x in result}
  self.assertIn('STALE_OPPORTUNITY',types); self.assertIn('CLOSE_DATE_AT_RISK',types); self.assertEqual(types['STALE_OPPORTUNITY']['severity'],'CRITICAL'); self.assertTrue(types['STALE_OPPORTUNITY']['exception_id'].startswith('EXC-')); self.assertEqual(types['STALE_OPPORTUNITY']['resolution_status'],'OPEN'); self.assertIn('recommended_next_action',types['STALE_OPPORTUNITY'])

 def test_quota_gap_uses_only_supplied_scoped_quotas_and_calibrated_severity(self):
  rows=[{'forecast_snapshot_id':'S','opportunity_id':'O1','owner_rep_id':'R1','territory_id':'T1','stage_at_snapshot':'PROPOSAL'}]
  fc=[{'forecast_snapshot_id':'S','opportunity_id':'O1','owner_rep_id':'R1','territory_id':'T1','expected_booking_reporting':'50000'}]
  scoped=[{'sales_rep_id':'R1','quota_amount':'200000','currency':'USD','fiscal_quarter':'2025Q2'}]
  result=detect_exceptions(rows,fc,scoped,context={'forecast_run_id':'run-1','forecast_snapshot_id':'S'})
  gap=next(item for item in result if item['exception_type']=='FORECAST_GAP_TO_QUOTA')
  self.assertEqual(gap['severity'],'HIGH')
  self.assertEqual(gap['owner_rep_id'],'R1')
  self.assertEqual(gap['territory_id'],'T1')
  self.assertEqual(gap['evidence']['gap'],150000)

 def test_exception_ids_are_unique_per_forecast_run_context(self):
  rows=[{'forecast_snapshot_id':'S','opportunity_id':'O1','owner_rep_id':'R1','territory_id':'T1','stage_at_snapshot':'PROPOSAL'}]
  fc=[{'forecast_snapshot_id':'S','opportunity_id':'O1','owner_rep_id':'R1','territory_id':'T1','expected_booking_reporting':'0'}]
  quota=[{'sales_rep_id':'R1','quota_amount':'100000','currency':'USD','fiscal_quarter':'2025Q2'}]
  first=next(item for item in detect_exceptions(rows,fc,quota,context={'forecast_run_id':'run-1'}) if item['exception_type']=='FORECAST_GAP_TO_QUOTA')
  second=next(item for item in detect_exceptions(rows,fc,quota,context={'forecast_run_id':'run-2'}) if item['exception_type']=='FORECAST_GAP_TO_QUOTA')
  self.assertNotEqual(first['exception_id'],second['exception_id'])
  self.assertEqual(first['severity'],'CRITICAL')
