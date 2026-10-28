"""Small, dependency-free client for the forecasting API."""
from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ForecastApiError(RuntimeError):
    """An API response that the dashboard can present safely to the user."""


@dataclass
class ForecastApiClient:
    base_url: str = "http://127.0.0.1:8000"
    timeout_seconds: float = 15.0

    def _request(self, method: str, path: str, payload: dict | None = None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url.rstrip('/')}{path}", body, method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8")
            try:
                detail = json.loads(detail).get("detail", detail)
            except json.JSONDecodeError:
                pass
            raise ForecastApiError(f"API returned {error.code}: {detail}") from error
        except (URLError, TimeoutError) as error:
            raise ForecastApiError(f"Unable to reach forecasting API at {self.base_url}: {error.reason if isinstance(error, URLError) else error}") from error

    def health(self): return self._request("GET", "/health")
    def run_forecast(self, payload: dict): return self._request("POST", "/forecasts/run", payload)
    def get_forecast(self, forecast_id: str): return self._request("GET", f"/forecasts/{forecast_id}")
    def opportunities(self, forecast_id: str): return self._request("GET", f"/forecasts/{forecast_id}/opportunities")
    def opportunity_detail(self, forecast_id: str, opportunity_id: str): return self._request("GET", f"/forecasts/{forecast_id}/opportunities/{opportunity_id}")
    def exceptions(self, forecast_id: str): return self._request("GET", f"/forecasts/{forecast_id}/exceptions")
    def evaluation(self, forecast_id: str): return self._request("GET", f"/forecasts/{forecast_id}/evaluation")
    def audit(self, forecast_id: str): return self._request("GET", f"/forecasts/{forecast_id}/audit")
    def reproducibility(self, forecast_id: str): return self._request("POST", f"/forecasts/{forecast_id}/reproducibility", {})
    def scenario_presets(self): return self._request("GET", "/scenario-presets")
    def historical_backtest(self): return self._request("POST", "/evaluations/backtest", {})
    def scenario(self, forecast_id: str, payload: dict): return self._request("POST", f"/forecasts/{forecast_id}/scenarios", payload)
