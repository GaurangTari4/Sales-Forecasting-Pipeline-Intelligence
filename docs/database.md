# PostgreSQL setup and recovery

Set `DATABASE_URL` in your environment (for example `postgresql://user:password@localhost:5545/buss_publication`); do not commit it. Install PostgreSQL 16+ and `psycopg[binary]`, then initialize the approved base schema with `psql "$DATABASE_URL" -f schemas/schema.sql`. Apply persistence migration and seed repeatably with `python -m src.persistence migrate` and `python -m src.persistence seed --input output/starter`.

The loader inserts parents before dependents, uses one transaction, parameterized `executemany`, FK constraints, and `ON CONFLICT DO NOTHING` for idempotent natural keys. A failure rolls back the transaction. Migration 002 adds database triggers preventing UPDATE/DELETE on stage history, bookings, and snapshots. Those guarantees apply only after that migration is applied by a role permitted to create triggers; application permissions still need to be restricted separately for production.

Recovery: restore a tested `pg_dump` backup, re-run migrations (tracked in `schema_migrations`), then re-run seed safely. Do not repair append-only records in place; use correction events or a new forecast run.
