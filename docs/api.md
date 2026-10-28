# API

Set `FORECAST_DATASET_DIR` and optional `API_RUNS_DIR`; secrets remain in environment variables. Run with `uvicorn api.main:app --reload` after installing FastAPI/Uvicorn.

```json
POST /forecasts/run
{"snapshot_id":"FCST-2025-03-31-001","scenario":"BASE","dimensions":["quarter","territory_id"],"seed":20261022,"reporting_currency":"USD"}
```

Returns `201` with a unique `forecast_id`, totals, P10/P50/P90, the probability of missing the scoped quota (from the same portfolio draws), quota attainment, model/feature metadata, scenario assumptions, and audit fields. Unknown snapshots/runs return 404; invalid schemas/currency/dimensions return 422.

## Endpoint summary

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Database-backed service readiness check. |
| `POST` | `/forecasts/run` | Create and persist an immutable base forecast run. |
| `GET` | `/forecasts/{forecast_id}` | Retrieve the stored run projection. |
| `GET` | `/forecasts/{forecast_id}/opportunities` | Opportunity contributions and intervals. |
| `GET` | `/forecasts/{forecast_id}/opportunities/{opportunity_id}` | Stage/activity history visible at the snapshot cutoff only. |
| `GET` | `/forecasts/{forecast_id}/exceptions` | Rule-based exception evidence for the run. |
| `POST` | `/forecasts/{forecast_id}/scenarios` | Create an immutable BASE/CONSERVATIVE/OPTIMISTIC/CUSTOM scenario comparison run using bounded explicit assumptions. `CUSTOM` requires at least one explicit override. |
| `GET` | `/scenario-presets` | Return BASE, CONSERVATIVE, and OPTIMISTIC preset assumptions. |
| `POST` | `/evaluations/backtest` | Run the explicit, non-persisting rolling-origin historical evaluation. |
| `GET` | `/forecasts/{forecast_id}/audit` | Retrieve the artifact lineage summary, including explicit legacy gaps. |
| `POST` | `/forecasts/{forecast_id}/reproducibility` | Replay in memory only; it never writes a forecast record. |

`GET /forecasts/{forecast_id}/evaluation` returns the live-run evaluation status. A live forecast is not assigned fabricated future outcomes; use `/evaluations/backtest` for historical results.

## Security boundary

The local demonstration API has no authentication or authorization. Do not expose it to an untrusted network. A shared deployment requires authenticated TLS ingress, role-based authorization, request identity in the audit trail, rate limits, and an approved secret-management mechanism before enabling any write endpoint.

The local file store is durable across API restarts but is intended for development. For requests that exceed typical HTTP limits, enqueue the same immutable run payload in a worker (Celery/RQ/managed queue), return 202 plus a job ID, and persist the final run through PostgreSQL.
