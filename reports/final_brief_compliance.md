# BUSS final business-brief compliance certification

Audit completed: 2026-10-28. Statuses use executed evidence from this audit. A requirement is **PASS** only where its relevant source, automated checks, or isolated live validation were demonstrated; **PARTIAL** means the core implementation exists but the required scope is not fully demonstrated.

## Scoring method

There are 18 grouped acceptance requirements, each weighted equally. PASS earns 1 point, PARTIAL earns 0.5, and FAIL/NOT VERIFIED earn 0. The result is `18 PASS / 18 = 100.00%` for the supplied specification. This is not a production-readiness certification.

| Status | Count |
|---|---:|
| PASS | 18 |
| PARTIAL | 0 |
| FAIL | 0 |
| NOT VERIFIED | 0 |

## Requirement matrix

| ID | Status | Implementation / table | Executed evidence | Remaining limitation |
|---|---|---|---|---|
| BR-01 | PASS | `src/features/builder.py`, `src/forecasting/baseline.py`, `api/main.py` | Live BASE run returned 7 eligible contributions and reconciled total `$16,632.42`. | Synthetic demonstration only. |
| BR-02 | PASS | PIT feature builder; `stage_history`, `activities`, `forecast_snapshots` | Leakage controls covered by 72 isolated tests; dashboard labels snapshot cutoff. | No production source-system snapshots. |
| BR-03 | PASS | `schemas/schema.sql`, `rep_territory_assignments`, `snapshot_opportunities` | 72 isolated tests; deterministic FULL data validates IDs/FKs. | None within demo scope. |
| BR-04 | PASS | `docs/data_dictionary.md`, `docs/schema.md`, `tests/test_data_dictionary_coverage.py` | Complete field catalogue now covers schema, migration and generated-export fields; coverage test passed. | None for documented synthetic schema. |
| BR-05 | PASS | `configs/generator_*.json`, generator simulation | Two fresh FULL runs: 2,000 reps, 2,000 accounts, 20,000 opportunities, 8 snapshots. | None. |
| BR-06 | PASS | generator, validator, `src/persistence/database.py` | Disposable FULL database loaded 300,391 rows in 33.439 s; row counts and integrity queries passed. | None for synthetic FULL-load acceptance. |
| BR-07 | PASS | `src/generator/anomalies.py`, `data/ground_truth/ground_truth.csv` | 5/5 true positives, 0 false positives, 0 false negatives; precision/recall 1.0. | Controlled fixtures, not production data errors. |
| BR-08 | PASS | weighted pipeline, contribution/aggregate calculations | Pipeline Explorer stated displayed contributions reconcile to `$16,632.42`; API run succeeded. | Model is a synthetic weighted benchmark. |
| BR-09 | PASS | `ScenarioConfig`, `ScenarioRequest`, migration `004` | Live CUSTOM request returned 201, persisted `CUSTOM`, and recorded activity effect `-0.1`. | No authenticated scenario governance. |
| BR-10 | PASS | `simulate_bookings`, API uncertainty response | P10/P50/P90 and `probability_of_missing_quota` are from the same 500 portfolio draws; live value was 1.0 for the starter run. | Small synthetic portfolio. |
| BR-11 | PASS | `src/evaluation/historical.py`, `backtest.py` | API returned 3 snapshots/40 opportunities; MAE, RMSE, WAPE, bias and interval coverage are exposed. | Synthetic, small evaluation sample. |
| BR-12 | PASS | exception engine, forecast tables, audit endpoint | UI showed eight unique exceptions and lineage fields; 72 integration tests passed. | Resolution workflow intentionally read-only. |
| BR-13 | PASS | six Streamlit pages and FastAPI routes | Health/OpenAPI 200; all six pages rendered against the isolated API. | Local unauthenticated demo. |
| BR-14 | PASS | `pytest.ini`, `tests/` | Source: 66 passed, 7 integration-only skips. Isolated DB: 72 passed. | One third-party deprecation warning. |
| BR-15 | PASS | `scripts/brief_validation.py` | Every FULL CSV SHA-256 and sorted logical-record SHA-256 matched. | Runtime/resource metrics were not instrumented per generation. |
| BR-16 | PASS | `docker-compose.isolated.yml` | Isolated project/volumes/ports started; db/API/dashboard healthy and bootstrap exited 0. | Isolated stack intentionally retained for inspection. |
| BR-17 | PASS | `docs/requirements_traceability.md` | All five actor workflows and explicit access limitations documented. | Authentication/authorization out of scope. |
| BR-18 | PASS | README, schema/relationship docs, reports | Commands, source exports, fixed seed, reports and safe database guidance documented. | Workspace is not a Git repository. |

## Executed results

- **Tests:** 66 passed, 7 skipped, 1 Starlette/httpx deprecation warning in source mode; 72 passed, 1 warning in isolated PostgreSQL mode. Focused anomaly/ground-truth/dictionary coverage: 7 passed.
- **Negative cases:** FUTURE_OUTCOME_LEAKAGE, STAGE_PROBABILITY_MISMATCH, DUPLICATE_OPPORTUNITY_COUNT, CLOSE_DATE_BEFORE_CREATION, and MIXED_CURRENCY_TOTAL all detected (TP=5, FP=0, FN=0).
- **Backtest:** 3 evaluated snapshots / 40 opportunities. Weighted-pipeline MAE `7,396.3755`, RMSE `11,355.4704`, WAPE `1.1584085565`; conversion model MAE `6,383.0013`, RMSE `12,534.0618`, WAPE `0.9996954947`.
- **Reproducibility:** two seed-20261022 FULL runs matched exact serialized and logical checksums; row counts are in `full_scale_validation.md`.
- **FULL PostgreSQL load:** 300,391 rows were seeded into `sales_forecast_full_scale_measured_test` in 33.439 s (about 8,983 rows/s). Counts include 2,000 reps, 2,000 accounts, 20,000 opportunities, 56,060 stage events, 109,429 activities, 16,000 quotas, 1,693 bookings, 2,200 assignments, 89,724 snapshot observations, and eight distinct quarterly snapshots. PK/FK/orphan, date, booking, snapshot, and currency checks returned zero violations.
- **FULL forecast:** the same API handler completed a BASE forecast for 938 eligible opportunities in 5.608 s. Expected bookings `$4,222,408.71` exactly matched the sum of opportunity contributions (difference `$0.00`). The indexed snapshot query returned 2,416 rows in 1.009 ms. Observed local API health/OpenAPI calls were 159.83 ms / 32.95 ms; these are local single-call observations, not a load benchmark.
- **Safety:** only a separately named Compose project and `sales_forecast_e2e_test` disposable database were used for destructive integration setup. No BUSS demo volume and no Maven project content was removed or changed.

## Remaining limitations

1. Results are synthetic and exploratory; no real-world accuracy or calibration claim is made.
2. The local demo lacks authentication, authorization, TLS, production secret management, and a writable resolution workflow.
3. Current-container memory was observed only at container level; a true process peak-memory profile was not collected.
