# FULL-scale validation

- Fixed seed: `20261022`
- First isolated output: `output\brief-full-a`
- Second isolated output: `output\brief-full-b`
- CSV checksums match: **True**
- Sorted logical-record checksums match: **True**
- Reproducible: **True**

## Row counts

| Table | Rows |
|---|---:|
| accounts | 2000 |
| activities | 109429 |
| exchange_rates | 0 |
| forecast_snapshots | 8 |
| ground_truth_anomalies | 0 |
| ground_truth_outcomes | 18918 |
| historical_bookings | 1693 |
| opportunities | 20000 |
| opportunity_change_events | 1257 |
| quotas | 16000 |
| rep_territory_assignments | 2200 |
| sales_reps | 2000 |
| snapshot_opportunities | 89724 |
| stage_history | 56060 |
| stage_probability_versions | 7 |
| stages | 7 |
| territories | 6 |

The report compares serialized CSV SHA-256 values and canonical sorted logical-record SHA-256 values.

## Disposable PostgreSQL integration

The same verified FULL export was loaded into the isolated disposable database `sales_forecast_full_scale_measured_test`; no demonstration volume or database was used.

- Transactional migration and seed: **300,391 rows in 33.439 seconds** (about **8,983 rows/s**).
- Core counts: 2,000 sales reps, 2,000 accounts, 20,000 opportunities, 56,060 stage-history rows, 109,429 activities, 16,000 quotas, 1,693 historical bookings, 2,200 effective-dated assignments, 8 snapshots, and 89,724 snapshot-opportunity rows.
- Integrity queries returned zero duplicate opportunity IDs, zero queried FK orphans, zero stage events before creation, zero snapshot records before opportunity creation, zero won/booking mismatches, and zero non-USD money rows. Snapshot headers span **eight distinct quarters**.
- A BASE full-scale forecast completed in **5.608 seconds** for 938 eligible opportunities. Its expected-bookings total `$4,222,408.71` equals the sum of persisted opportunity contributions exactly (difference `$0.00`).
- A representative indexed snapshot query returned 2,416 rows in **1.009 ms**. Local single-call API health/OpenAPI observations were 159.83 ms / 32.95 ms; they are not a concurrency benchmark. Process peak memory was not instrumented.
