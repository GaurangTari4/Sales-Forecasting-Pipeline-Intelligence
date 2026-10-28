import importlib.util, os, unittest

@unittest.skipUnless(
    importlib.util.find_spec('fastapi') and os.environ.get('SALES_FORECAST_TEST_DATABASE_URL'),
    'set SALES_FORECAST_TEST_DATABASE_URL to a disposable *_test PostgreSQL database to execute API integration tests',
)
class ApiIntegrationTests(unittest.TestCase):
 def test_health_and_invalid_snapshot(self):
  from fastapi.testclient import TestClient
  from api.main import app
  client=TestClient(app); self.assertEqual(client.get('/health').status_code,200)
  self.assertEqual(client.post('/forecasts/run',json={'snapshot_id':'FCST-2020-01-31-001'}).status_code,404)
