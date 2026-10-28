# Container deployment

## Prerequisites

Install Docker Desktop (or Docker Engine with Compose v2), then copy `.env.example` to `.env` and replace `POSTGRES_PASSWORD` with a local development secret. The `.env` file is excluded from the image and must not be committed.

## Start

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
docker compose logs bootstrap
```

Compose starts PostgreSQL first and waits for `pg_isready`. The one-shot `bootstrap` service then generates the small configured starter dataset into the `buss_publication_runtime_data` volume, applies migrations, and performs idempotent ingestion. The API waits for successful bootstrap completion; the dashboard waits for the API's database-backed health check.

After all services are healthy, open the dashboard at `http://localhost:8511`, API OpenAPI docs at `http://localhost:8011/docs`, and verify the API with:

```powershell
Invoke-RestMethod http://localhost:8011/health
Invoke-RestMethod -Method Post http://localhost:8011/forecasts/run -ContentType 'application/json' -Body '{"snapshot_id":"FCST-2025-03-31-001","scenario":"BASE","reporting_currency":"USD","dimensions":["quarter","territory_id"]}'
```

The image deliberately excludes generated outputs, CSVs, serialized models, `.env`, and local database files. Generated seed data and API run artifacts are instead stored in the named `buss_publication_runtime_data` volume. PostgreSQL uses the named `buss_publication_postgres_data` volume.

## Migrations and seed commands

The bootstrap command is repeatable: `python -m src.persistence migrate` records migrations in `schema_migrations`; seed inserts use conflict-safe natural keys. To run only that operation again after the stack is up:

```powershell
docker compose run --rm bootstrap
```

## Safe shutdown

Stop containers while preserving all data:

```powershell
docker compose stop
```

The publication stack uses named volumes, not a bind mount of the project directory. For a clean test run, use the isolated override in `docker-compose.isolated.yml` rather than deleting an existing volume.

## Local credential continuity

PostgreSQL reads `POSTGRES_PASSWORD` only when an empty data volume is initialized. Changing that value later in `.env` does not change the password already stored in an existing database volume, so bootstrap will correctly fail authentication rather than bypass validation. Keep the same local `.env` password for a retained volume, or have an authorized local administrator rotate the database role password to the new `.env` value. For a disposable clean test, use a newly suffixed isolated volume; do not reset a preserved demo volume.

## Operational notes

- The API health endpoint returns `503` until PostgreSQL accepts a `SELECT 1`; Compose uses that endpoint for API readiness.
- The database service is intentionally published on a configurable local port for development. Remove the `db.ports` section before deploying to a shared network.
- The current API persists live run artifacts in the persistent runtime volume. The PostgreSQL schema and generated data are initialized and retained independently; moving run persistence fully into PostgreSQL remains a future application-layer change.
- API, dashboard, and database ports are published on all host interfaces by the current Compose file. Restrict them to loopback or an internal network before any shared deployment.
- `POSTGRES_PASSWORD` is supplied from `.env` for local development. Use a managed secret store and injected runtime secret in any deployed environment; do not put a production value in `.env`, Compose files, source, or CI logs.
- The API has no authentication, authorization, request rate limiting, TLS termination, or user identity audit trail. It must remain on a trusted local network until those controls exist.
- Dependency versions are range-bounded in `requirements.txt` but not lockfile-pinned. Build provenance, pinned hashes, vulnerability scanning, and CI image scanning are required before a production release.
- Docker health checks cover PostgreSQL readiness, API database connectivity, and Streamlit availability. They do not test authorization, business correctness, or external ingress.
