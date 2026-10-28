# BUSS pre-upgrade business-brief gap analysis

Audit baseline: 2026-10-28. This report records the repository state before this brief's corrective changes. Evidence is from source inspection and the commands recorded below; previous reports were not treated as current execution evidence.

## Summary

| Status | Count |
|---|---:|
| PASS | 7 |
| PARTIAL | 7 |
| FAIL | 2 |
| NOT VERIFIED | 2 |

## Requirements traceability

| ID | Acceptance requirement | Status | Existing implementation / evidence | Remaining gap and required correction |
|---|---|---|---|---|
| BR-01 | Forecast opportunity and aggregate bookings from stages, age, conversion and rep activity | PASS | `src/features/builder.py`, `src/forecasting/baseline.py`, `api/main.py`; feature projection contains stage, age, activity, historical rates and slippage. | None found in static review; live API reconciliation remains to be re-run. |
| BR-02 | Preserve point-in-time correctness and lifecycle history | PASS | As-of filters in `src/features/builder.py`; append-only event design in `schemas/schema.sql`; leakage/anomaly tests. | Re-run leakage suite and document feature availability. |
| BR-03 | Required entities and effective-dated relationships | PASS | SQL tables for all ten required entities plus `rep_territory_assignments` and `snapshot_opportunities`; `docs/relationships.md`. | Required filenames `docs/schema.md` and `docs/entity_relationships.md` do not yet exist. |
| BR-04 | Complete field-level data dictionary | PARTIAL | `docs/data_dictionary.md` documents core entities and support-table narrative. | It does not enumerate every supporting-table field with all requested attributes; add complete dictionary and requested path aliases. |
| BR-05 | STARTER/FULL deterministic generator and IDs | PASS | `configs/generator_starter.json`, `configs/generator_full.json`, `src/generator/simulation.py`; fixed seed `20261022`; full config is 2,000/2,000/20,000. | Execute two independent full-scale generations in this audit. |
| BR-06 | Generate outcomes from rules and reconcile bookings | PASS | Rule-dependent lifecycle simulation and bookings in `src/generator/simulation.py`; `src/generator/validation.py`. | Re-run validation at full scale. |
| BR-07 | Five isolated labelled negative cases and ground truth | PARTIAL | `src/generator/anomalies.py` implements all five and tests assert precision/recall 1.0. | Required `data/ground_truth/ground_truth.csv` and `reports/anomaly_validation.json` are absent. Generate them. |
| BR-08 | Forecast formula and reconciled opportunity/rep/territory/portfolio outputs | PASS | Weighted-pipeline formula, contribution rows and grouped aggregates in `src/forecasting/baseline.py`, `api/main.py`. | Validate against a live isolated run. |
| BR-09 | Scenario engine supports BASE, CONSERVATIVE, OPTIMISTIC, and CUSTOM | FAIL | `src/forecasting/uncertainty.py` implements three presets and parameter overrides. `ScenarioRequest.name` permits only those three. | Add auditable `CUSTOM` scenario API/dashboard handling and tests. |
| BR-10 | Monte-Carlo quantiles, quota-risk and deterministic replay | PARTIAL | `simulate_bookings` returns portfolio P10/P50/P90 and fixed seed; stored run metadata/replay exist. | API response does not expose explicit probability of missing quota; add it and test it. |
| BR-11 | Rolling-origin evaluation with requested metrics and breakdowns | PARTIAL | `src/evaluation/historical.py` and tests provide historical evaluation/intervals. | Need current executed evidence plus a report containing the requested breakdown/exclusions. |
| BR-12 | Meaningful exceptions, decisions, and audit trail | PASS | `src/exceptions/engine.py`, anomaly actions, API audit/reproducibility endpoints, PostgreSQL forecast tables. | Verify persistence only in disposable integration database. |
| BR-13 | Six-page API/dashboard acceptance | PARTIAL | Six named pages are implemented under `dashboard/`; typed FastAPI routes in `api/main.py`. | Live dashboard/API integration has not been executed in this audit. |
| BR-14 | Full source suite is reproducibly runnable | FAIL | `pytest -q` executed with bundled Python on 2026-10-28. | Collection failed with 19 import-mismatch errors because ignored `github-upload/tests` duplicates the root test module names. Configure discovery to root `tests/` with isolated imports. |
| BR-15 | Two independent full-scale runs match exactly | NOT VERIFIED | Generator uses seed and canonical CSV serialization. Existing output folders are not evidence of a fresh full-scale comparison. | Run two fresh FULL outputs and compare counts, hashes and logical records. |
| BR-16 | Docker/database bootstrap is reproducible without damaging demo state | NOT VERIFIED | `docker-compose.yml` and `docker-compose.isolated.yml` provide health-gated bootstrap and separately named opt-in volumes. | Start and verify the isolated stack; do not use default volumes or destructive commands. |
| BR-17 | Actor coverage: customer, sales/marketing ops, support, analyst, administrator | PARTIAL | Analyst/admin workflows are documented; dashboard supports sales operations analysis. | Add a traceability matrix that explicitly documents out-of-scope interactive access for customer and support actors rather than implying authentication. |
| BR-18 | Publication documentation and source exports | PARTIAL | README, source CSV/JSON export writer, schema, and documentation exist. | Add brief-specific commands, validation summary links, provenance and the final compliance matrix.

## Baseline commands and actual results

- `rg --files -g '!**/.git/**'`: source, Docker, schema, generator, API, dashboard, tests, outputs and an ignored duplicate staging package were present.
- `git rev-parse --is-inside-work-tree`: failed; this workspace is not a Git repository.
- The pre-correction `pytest -q` run **collection failed** with 19 import-mismatch errors because duplicate staged test module names were discoverable. The subsequent fix constrains discovery to the root `tests/` directory and uses importlib import mode.

No main BUSS database or Docker volume was modified while preparing this baseline.
