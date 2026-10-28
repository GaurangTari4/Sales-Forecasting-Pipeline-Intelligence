# Schema reference

The executable, canonical PostgreSQL definition is [schemas/schema.sql](../schemas/schema.sql); migrations are applied in lexical order from `migrations/`. The schema models Territory, SalesRep, Account, Opportunity, Stage, StageHistory, Activity, Quota, HistoricalBooking, and ForecastSnapshot, with supporting effective-dated assignment, change-event, snapshot-detail, exchange-rate, probability-version, forecast-run, forecast-detail, and data-quality tables.

Keys are immutable business identifiers. Foreign keys use restrictive delete behavior. `rep_territory_assignments` and `snapshot_opportunities` are bridge tables, while append-only stage/change/activity/booking records preserve historical reconstruction. `004_add_custom_scenario.sql` extends the scenario enum without rewriting historical runs.

See [data dictionary](data_dictionary.md) for field rules and [entity relationships](entity_relationships.md) for cardinalities.
