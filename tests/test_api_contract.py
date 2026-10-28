import unittest
class ApiContractTests(unittest.TestCase):
 def test_fastapi_contract_is_opt_in_dependency(self):
  try:
   from api.main import RunRequest
  except ModuleNotFoundError as e:
   self.assertEqual(e.name,'fastapi'); return
  self.assertEqual(RunRequest(snapshot_id='FCST-2025-03-31-001').scenario,'BASE')
