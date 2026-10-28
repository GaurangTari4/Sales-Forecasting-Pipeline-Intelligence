# Reproduction without overwriting existing data

Run all commands from the repository root. Use the configured bundled Python runtime if `python` does not resolve locally.

Use a fresh clone for a clean demonstration. If another BUSS stack already exists on the same Docker host, use the isolated-volume override below: the default Compose file intentionally names its volumes explicitly, so `COMPOSE_PROJECT_NAME` alone does not isolate them. If you are working in an existing local stack, the standard commands preserve the named PostgreSQL and runtime volumes; they do not reset data or forecast history.

```powershell
$env:COMPOSE_VOLUME_SUFFIX = "demo-$env:USERNAME"
docker compose -f docker-compose.yml -f docker-compose.isolated.yml up --build -d
```

Use that same two-file command for `ps`, `logs`, `exec`, `stop`, and `down` during the isolated demonstration. This creates separate named volumes and does not touch `buss_publication_postgres_data` or `buss_publication_runtime_data`.

Before attempting live integration checks, run the read-only prerequisite check:

```powershell
python scripts/preflight.py
```

It returns non-zero until Docker, required Python packages, and a safely named disposable test database (`*_test`) are available.

## In-process audit

```powershell
python -m src.generator --config configs/generator_starter.json --output output/audit-run-a
python -m src.generator --config configs/generator_starter.json --output output/audit-run-b
python -m src.features --input output/audit-run-a --output output/audit-e2e-features
python -m src.forecasting.model --input output/audit-run-a --output output/audit-e2e-model
python -m src.generator --config configs/generator_anomalous.json --output output/audit-anomalous --inject-anomalies
python -m unittest discover -s tests -v
```

Compare `output/audit-run-a/manifest.json` and `output/audit-run-b/manifest.json`: both `row_counts` and `sha256` must be identical. The expected starter dataset has 200 opportunities, 8 snapshots, and 850 snapshot-opportunity rows.

## Container and PostgreSQL verification

The following commands were executed successfully on 2026-10-27 against the local Compose stack. They remain the reproduction procedure for a machine with Docker Compose v2:

```powershell
# Only do this when .env does not already exist; never overwrite another developer's secret file.
Copy-Item .env.example .env
# Edit .env and choose a development-only POSTGRES_PASSWORD.
docker compose up --build -d
docker compose ps
docker compose logs --no-color bootstrap
Invoke-RestMethod http://localhost:8011/health
Invoke-RestMethod -Method Post http://localhost:8011/forecasts/run -ContentType 'application/json' -Body '{"snapshot_id":"FCST-2025-03-31-001","scenario":"BASE","reporting_currency":"USD","dimensions":["quarter","territory_id"]}'
```

The expected Compose state is: `db`, `api`, and `dashboard` healthy; `bootstrap` exited successfully. Record the returned forecast ID, then verify its persisted lineage in PostgreSQL:

```powershell
docker compose exec db psql -U buss_publication -d buss_publication -c "SELECT forecast_run_id, forecast_snapshot_id, model_version, feature_version, scenario, created_at FROM forecast_runs ORDER BY created_at DESC LIMIT 5;"
docker compose exec db psql -U buss_publication -d buss_publication -c "SELECT count(*) AS opportunity_forecasts FROM opportunity_forecasts;"
```

For an isolated PostgreSQL integration run, use a disposable database only. The following Docker command uses `buss_publication_e2e_test`, not the application database:

```powershell
docker compose exec -T api sh -c 'SALES_FORECAST_TEST_DATABASE_URL="${DATABASE_URL%/*}/buss_publication_e2e_test" pytest -q'
```

Do not point that variable at a shared or production database.

The supplied isolated PostgreSQL evidence records **72 passed** with one third-party Starlette/httpx deprecation warning. Re-run this command locally before reporting a fresh result.

To verify persistence across safe restarts without deleting volumes:

```powershell
docker compose restart api db
docker compose ps
Invoke-RestMethod http://localhost:8011/forecasts/<forecast-id>
```

The final audit also ran the reproducibility endpoint for a persisted run. It matched recorded snapshot inputs, assumptions, model/feature versions, seed, and output hash; its in-memory replay created zero `forecast_runs` rows.

## Clean-up and safety

Use `docker compose stop` or `docker compose down` to stop containers while retaining volumes. Do **not** use `docker compose down -v`, `docker volume rm`, or a database reset when preserving an existing demonstration history. To test a clean bootstrap on the same Docker host, use the isolated-volume override above.
