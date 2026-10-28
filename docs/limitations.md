# Known limitations

- The project uses synthetic data. Forecast accuracy, calibration, and uncertainty coverage do not establish performance on a real sales process.
- The latest rolling-origin evaluation contains 3 snapshots and 40 opportunities. The observed P10–P90 coverage is descriptive, not a statistically reliable calibration claim.
- The generator currently does not exercise multi-lifecycle reopened opportunities. The validator must be extended to validate each `lifecycle_number` independently before reopen behavior is enabled in generation.
- Docker Compose bootstrap, PostgreSQL ingestion, API persistence, FastAPI integration, dashboard behavior, and service health checks were verified on 2026-10-27. The dashboard is still a local demonstration, not a production user-acceptance test.
- The dashboard deliberately shows actuals/evaluation as unavailable for a live future forecast when the API has no realized-outcome report. It does not manufacture metrics.
- API run artifacts are persisted to both PostgreSQL and the runtime artifact store. Retrieval currently uses the artifact store; database-based retrieval and evaluation-report endpoints should be added before production use.
- The API currently returns some monetary fields as binary floats, which can expose insignificant precision artifacts. Currency values should be serialized as quantized decimal values or strings before production use.
- The PostgreSQL integration suite ran successfully against an isolated disposable `*_test` database. CI should still run the same workflow on clean hosts and dependency versions.
- Exchange-rate logic has unit coverage, but the starter configuration is USD-only and therefore does not exercise a live multi-currency ingestion path.
- The local API has no authentication or authorization, and Compose publishes PostgreSQL on a host port for development convenience. Neither is appropriate for an untrusted or shared production network.
- Dependency ranges are bounded but not lockfile-pinned, and automated vulnerability scanning/CI release controls are not configured in this repository.
