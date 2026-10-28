# Sales Forecasting & Pipeline Intelligence data dictionary

This is the canonical PostgreSQL contract in `schemas/schema.sql`. IDs are immutable business keys. `required` means `NOT NULL`. Timestamps are UTC `timestamptz`; dates are ISO-8601 calendar dates; money is `numeric(18,2)` in the stated ISO-4217 currency. Event records are append-only. Cross-row lifecycle rules are enforced in the ingest validator because a SQL `CHECK` cannot inspect other rows.

## Core entities

### Territory
| Field | Type | Required | Key/constraints and rules |
|---|---|---:|---|
| territory_id | varchar(7) | Yes | PK, `TER-999`; immutable |
| territory_name | varchar(100) | Yes | Unique, nonblank |
| region | region_code | Yes | `NA`, `EMEA`, `APAC` |
| active_from, active_to | date | Yes/No | Inclusive effective interval; end >= start |

### SalesRep
| Field | Type | Required | Key/constraints and rules |
|---|---|---:|---|
| sales_rep_id | varchar(10) | Yes | PK, `REP-000001`; immutable |
| rep_name | varchar(100) | Yes | Nonblank |
| hire_date | date | Yes | On or before `active_from` |
| role | rep_role | Yes | `ACCOUNT_EXECUTIVE`, `SALES_MANAGER` |
| active_from, active_to | date | Yes/No | Inclusive employment interval |

### Account
| Field | Type | Required | Key/constraints and rules |
|---|---|---:|---|
| account_id | varchar(10) | Yes | PK, `ACC-000001` |
| account_name | varchar(200) | Yes | Unique, nonblank source-system normalized name |
| territory_id | varchar(7) | Yes | FK to Territory; current account territory |
| industry | industry_code | Yes | Six controlled values in SQL enum |
| employee_count | integer | Yes | Count, > 0 |
| active_from, active_to | date | Yes/No | Inclusive account availability interval |

### Opportunity
| Field | Type | Required | Key/constraints and rules |
|---|---|---:|---|
| opportunity_id | varchar(15) | Yes | PK, `OPP-2026-000001` (any four-digit creation year) |
| account_id | varchar(10) | Yes | FK to Account, restrict deletion |
| owner_rep_id | varchar(10) | Yes | FK to SalesRep; original owner; later ownership changes are events |
| product_name | varchar(100) | Yes | Nonblank |
| product_type | product_type_code | Yes | `SUBSCRIPTION`, `SERVICES` |
| created_at | timestamptz | Yes | UTC creation event time |
| original_expected_close_date | date | Yes | >= creation date; never overwritten |
| transaction_currency | char(3) | Yes | Uppercase ISO-4217 code |
| initial_amount | numeric(18,2) | Yes | >= 0, in transaction currency; never overwritten |

Current stage, amount, owner, and expected close date are derived as-of a timestamp from `stage_history` and `opportunity_change_events`; they are not mutable columns.

### Stage
| Field | Type | Required | Key/constraints and rules |
|---|---|---:|---|
| stage_code | stage_code | Yes | PK: Prospecting through Negotiation plus `CLOSED_WON`, `CLOSED_LOST` |
| display_name | varchar(50) | Yes | Unique label |
| stage_rank | smallint | Yes | >= 1; used for normal forward transitions |
| is_terminal | boolean | Yes | True exactly for closed stages |

### StageHistory
| Field | Type | Required | Key/constraints and rules |
|---|---|---:|---|
| stage_event_id | varchar(25) | Yes | PK, `STG-OPP-2026-000001-001` |
| opportunity_id | varchar(15) | Yes | FK to Opportunity |
| lifecycle_number | integer | Yes | Starts at 1; increments on an allowed reopen |
| event_sequence | integer | Yes | Starts at 1 per lifecycle; unique with opportunity/lifecycle |
| from_stage | stage_code | No | Null only for first event in lifecycle |
| to_stage | stage_code | Yes | FK to Stage |
| occurred_at | timestamptz | Yes | UTC, >= opportunity creation |
| reason_code | varchar(50) | Yes | Nonblank controlled ingest code |

### Activity
| Field | Type | Required | Key/constraints and rules |
|---|---|---:|---|
| activity_id | varchar(25) | Yes | PK, `ACT-OPP-2026-000001-001` |
| opportunity_id, sales_rep_id | varchar | Yes | FKs to Opportunity and SalesRep |
| occurred_at | timestamptz | Yes | UTC; >= opportunity creation |
| activity_type | activity_type_code | Yes | Call, email, meeting, demo, task |
| outcome | activity_outcome_code | Yes | Completed, no-show, bounced, cancelled |
| duration_minutes | integer | Yes | Minutes, 0–1,440 |

### Quota
| Field | Type | Required | Key/constraints and rules |
|---|---|---:|---|
| quota_id | varchar(25) | Yes | PK, `QUOTA-REP-000001-2026Q1` |
| sales_rep_id | varchar(10) | Yes | FK to SalesRep |
| fiscal_quarter | char(6) | Yes | `YYYYQ1`–`YYYYQ4`; unique per rep/quarter |
| quota_amount | numeric(18,2) | Yes | >= 0 in `currency` |
| currency | char(3) | Yes | Uppercase ISO-4217 code |

### HistoricalBooking
| Field | Type | Required | Key/constraints and rules |
|---|---|---:|---|
| booking_id | varchar(25) | Yes | PK, `BKG-OPP-2026-000001-001` |
| opportunity_id | varchar(15) | Yes | FK to a Closed Won opportunity |
| recognized_at | timestamptz | Yes | Booking-recognition timestamp, UTC |
| booking_amount | numeric(18,2) | Yes | >= 0 in currency |
| currency | char(3) | Yes | Uppercase ISO-4217 code |
| booking_type | varchar(20) | Yes | Initial, adjustment, reversal |

The recognition date, not expected close date, assigns a booking to a reporting period.

### ForecastSnapshot
| Field | Type | Required | Key/constraints and rules |
|---|---|---:|---|
| forecast_snapshot_id | varchar(20) | Yes | PK, `FCST-2026-01-31-001` |
| snapshot_at | timestamptz | Yes | Strict information cutoff; all input events must be <= it |
| horizon_start, horizon_end | date | Yes | Inclusive forecast period; end >= start |
| reporting_currency | char(3) | Yes | Uppercase ISO-4217 output currency |
| status | snapshot_status_code | Yes | Draft, finalized, superseded |
| created_at | timestamptz | Yes | System audit time |

`snapshot_opportunities` is the required detail table: one immutable as-of view per opportunity and snapshot. It has composite PK `(forecast_snapshot_id, opportunity_id)`.

## Supporting tables and why they exist

- **rep_territory_assignments** is the rep–territory bridge. Its non-overlapping, inclusive effective dates retain historical ownership after reassignment.
- **opportunity_change_events** is the immutable event log for amount, expected close, owner, and currency corrections.
- **exchange_rates** records sourced daily FX rates by directed currency pair.
- **stage_probability_versions** is a configured prior/scenario assumption. It is not a historical conversion rate; empirical rates are computed from dated `stage_history` cohorts and realized bookings.
- **forecast_runs** and **opportunity_forecasts** provide model/scenario/feature/data lineage and forecast uncertainty results, without implementing a model.
- **data_quality_anomalies** stores deliberate injection labels and validator findings.

`stage_probability_versions` contains `version_name` (required configuration label), `stage_code` (FK), `scenario` (conservative/base/optimistic), `probability` (required decimal 0–1), and inclusive `effective_from`/optional `effective_to` dates. Its `(stage, scenario)` periods cannot overlap. Actual historical conversion rate is deliberately not stored here: it is a reproducible aggregate calculated from a specified as-of cohort, stage-entry definition, and future realized booking window.

## Currency, snapshots, duplicates, and lifecycle semantics

Transaction amounts retain their original ISO-4217 code. Reporting conversion uses the rate from `exchange_rates` on the **economic recognition date** for realized bookings, and the rate dated `snapshot_at::date` for pipeline and forecast outputs. If a rate is missing, the record is invalid for reporting conversion rather than silently using a future rate. The reporting currency is recorded on the snapshot/run.

A snapshot is immutable after `FINALIZED`; it includes only records whose event time is at or before `snapshot_at`. Duplicate source events are detected by immutable primary keys and natural unique keys. A source duplicate with a different key is written to the anomaly table and quarantined; it is never merged automatically.

Close-date slippage is `current_expected_close_date - original_expected_close_date` in days, using the latest expected-close event known as-of the analysis time. A forward move is positive slippage; an earlier move is negative acceleration. Closed Lost may be reopened only via a `REOPENED` stage event that begins `lifecycle_number + 1`; Closed Won cannot be reopened once any booking is recognized. Historical bookings must reconcile to the final won amount plus approved adjustments/reversals.

## Complete schema and export field catalogue

This appendix covers every persisted column in `schemas/schema.sql`, migrations `002`–`004`, and every generated CSV field. **R** means required (`NOT NULL` or generated source value); **O** means optional. All IDs are immutable and unique where marked **PK**. All `*_id` fields shown as **FK** use `RESTRICT` deletion. CSV exports serialize the same fields using ISO dates/timestamps, decimal strings, and canonical JSON for JSON values.

| Entity / field | Type; required | Allowed values, units, validation | Key / relationship / provenance and lifecycle semantics |
|---|---|---|---|
| territories.territory_id | varchar(7); R | `TER-999` pattern | PK; deterministic generator master record |
| territories.territory_name | varchar(100); R | nonblank | Unique; generator territory master |
| territories.region | region_code; R | `NA`, `EMEA`, `APAC` | Territory classification; generator master |
| territories.active_from / active_to | date; R / O | inclusive interval, end >= start | Effective availability; generator configuration |
| sales_reps.sales_rep_id | varchar(10); R | `REP-000001` pattern | PK; deterministic generator master |
| sales_reps.rep_name | varchar(100); R | nonblank | Derived deterministic name; no relationship key |
| sales_reps.hire_date | date; R | <= active_from | Personnel lifecycle source |
| sales_reps.role | rep_role; R | `ACCOUNT_EXECUTIVE`, `SALES_MANAGER` | Generator role / forecast context |
| sales_reps.active_from / active_to | date; R / O | inclusive interval, end >= start | Employment effective dating |
| rep_territory_assignments.assignment_id | varchar(18); R | `RTA-REP-000001-001` pattern | PK; deterministic bridge identifier |
| rep_territory_assignments.sales_rep_id / territory_id | varchar; R / R | valid parent IDs | FK SalesRep / Territory; N:M bridge |
| rep_territory_assignments.effective_from / effective_to | date; R / O | inclusive, non-overlapping per rep | Historical ownership at snapshot |
| rep_territory_assignments.effective_period | daterange; R generated | derived from effective dates | SQL exclusion constraint prevents overlap |
| accounts.account_id | varchar(10); R | `ACC-000001` pattern | PK; deterministic master |
| accounts.account_name | varchar(200); R | nonblank | Unique; synthetic normalized name |
| accounts.territory_id | varchar(7); R | valid territory | FK Territory; account geography |
| accounts.industry | industry_code; R | six SQL enum industries | Synthetic dependent attribute |
| accounts.employee_count | integer; R | positive count | Unit: employees; account segment source |
| accounts.active_from / active_to | date; R / O | inclusive interval | Account lifecycle |
| opportunities.opportunity_id | varchar(15); R | `OPP-YYYY-000001` | PK; deterministic, immutable |
| opportunities.account_id / owner_rep_id | varchar; R / R | valid parent IDs | FK Account / SalesRep; initial ownership |
| opportunities.product_name / product_type | varchar / product_type_code; R / R | nonblank; `SUBSCRIPTION` or `SERVICES` | Product context from generator constants |
| opportunities.created_at | timestamptz; R | UTC | Opportunity lifecycle start |
| opportunities.original_expected_close_date | date; R | >= created date | Immutable original close plan |
| opportunities.transaction_currency | char(3); R | uppercase ISO-4217 | Transaction money currency |
| opportunities.initial_amount | numeric(18,2); R | non-negative transaction money | Source amount; later changes are events |
| stages.stage_code | stage_code; R | seven SQL lifecycle stages | PK; controlled lifecycle vocabulary |
| stages.display_name / stage_rank / is_terminal | varchar / smallint / boolean; R | unique nonblank; rank >=1; terminal only closed stages | Generator stage master; transition validation source |
| stage_history.stage_event_id | varchar(25); R | `STG-OPP-YYYY-000001-001` | PK; append-only event |
| stage_history.opportunity_id | varchar(15); R | valid opportunity | FK; 1:N lifecycle events |
| stage_history.lifecycle_number / event_sequence | integer / integer; R | >=1; unique per opportunity/lifecycle/sequence | Reopen and chronological ordering controls |
| stage_history.from_stage / to_stage | stage_code; O / R | valid Stage values | FK Stage; first event has null from-stage |
| stage_history.occurred_at / reason_code | timestamptz / varchar; R / R | UTC; nonblank code | As-of event time / transition provenance |
| opportunity_change_events.change_event_id | varchar(29); R | `CHG-OPP-YYYY-000001-001` | PK; append-only change event |
| opportunity_change_events.opportunity_id / occurred_at | varchar / timestamptz; R / R | valid FK; UTC | As-of source event |
| opportunity_change_events.change_type | varchar(30); R | `AMOUNT`, `EXPECTED_CLOSE_DATE`, `OWNER`, `CURRENCY` | Determines JSON payload semantics |
| opportunity_change_events.old_value / new_value / reason_code | jsonb / jsonb / varchar; O / R / R | old != new; nonblank reason | Immutable correction provenance |
| activities.activity_id | varchar(25); R | `ACT-OPP-YYYY-000001-001` | PK; deterministic event |
| activities.opportunity_id / sales_rep_id | varchar / varchar; R / R | valid parents | FK Opportunity / SalesRep; rep activity input |
| activities.occurred_at | timestamptz; R | UTC, on/after creation | PIT eligibility boundary |
| activities.activity_type / outcome | enums; R / R | CALL/EMAIL/MEETING/DEMO/TASK; COMPLETED/NO_SHOW/BOUNCED/CANCELLED | Activity semantics |
| activities.duration_minutes | integer; R | 0–1,440 minutes | Activity intensity unit |
| quotas.quota_id | varchar(25); R | `QUOTA-REP-000001-YYYYQ1` | PK; deterministic |
| quotas.sales_rep_id / fiscal_quarter | varchar / char(6); R / R | valid FK; `YYYYQ1`–`YYYYQ4` | Unique per rep-quarter |
| quotas.quota_amount / currency | numeric(18,2) / char(3); R / R | non-negative; ISO-4217 | Quarterly target; must match reporting currency for aggregation |
| exchange_rates.rate_date / from_currency / to_currency | date / char(3) / char(3); R | uppercase ISO-4217, currencies differ | Composite PK; as-of conversion source |
| exchange_rates.rate / source | numeric(20,10) / varchar; R | positive rate; nonblank source | Conversion factor and provenance |
| historical_bookings.booking_id | varchar(25); R | `BKG-OPP-YYYY-000001-001` | PK; append-only booking |
| historical_bookings.opportunity_id / recognized_at | varchar / timestamptz; R / R | valid FK; UTC | Closed-won reconciliation and reporting time |
| historical_bookings.booking_amount / currency | numeric(18,2) / char(3); R / R | non-negative; ISO-4217 | Recognized money, not pipeline amount |
| historical_bookings.booking_type | varchar(20); R | `INITIAL`, `ADJUSTMENT`, `REVERSAL` | Unique per opportunity/time/type |
| forecast_snapshots.forecast_snapshot_id | varchar(20); R | `FCST-YYYY-MM-DD-001` | PK; deterministic as-of identity |
| forecast_snapshots.snapshot_at | timestamptz; R | UTC | Strict PIT cutoff |
| forecast_snapshots.horizon_start / horizon_end | date; R / R | end >= start | Forecast label horizon |
| forecast_snapshots.reporting_currency / status / created_at | char(3) / enum / timestamptz; R / R / R | ISO-4217; DRAFT/FINALIZED/SUPERSEDED; UTC | Immutable when finalized; unique header period |
| snapshot_opportunities.forecast_snapshot_id / opportunity_id | varchar / varchar; R / R | valid FKs | Composite PK; one as-of observation per pair |
| snapshot_opportunities.stage_at_snapshot | stage_code; R | valid Stage FK | Reconstructed snapshot state |
| snapshot_opportunities.amount_transaction_currency / transaction_currency / expected_close_date | numeric(18,2) / char(3) / date; R | non-negative; ISO-4217 | Snapshot value/close-date inputs |
| stage_probability_versions.stage_probability_version_id | bigint; R generated | identity | PK; configuration record |
| stage_probability_versions.version_name / stage_code / scenario | varchar / stage_code / scenario_code; R | valid Stage; BASE/CONSERVATIVE/OPTIMISTIC/CUSTOM | Effective-dated configured prior, not observed conversion |
| stage_probability_versions.probability | numeric(7,6); R | 0–1 | Forecast stage probability |
| stage_probability_versions.effective_from / effective_to / effective_period / created_at | date / date / daterange / timestamptz; R / O / generated / R | inclusive non-overlap by stage+scenario; UTC | As-of configuration selection |
| forecast_runs.forecast_run_id / forecast_snapshot_id | uuid / varchar; R / R | valid Snapshot FK | PK; immutable execution lineage |
| forecast_runs.model_version / feature_version / scenario | varchar / varchar / scenario_code; R | nonblank version identifiers; valid scenario | Calculation provenance |
| forecast_runs.stage_probability_version_name / data_hash / assumptions / created_at | varchar / char(64) / jsonb / timestamptz; R | SHA-256 lowercase; recorded assumptions; UTC | Input hash, seed, output hash and scenario metadata |
| opportunity_forecasts.forecast_run_id / opportunity_id | uuid / varchar; R / R | valid FKs | Composite PK; one contribution per run/opportunity |
| opportunity_forecasts.expected_booking_reporting / lower_booking_reporting / upper_booking_reporting | numeric(18,2); R | non-negative; lower <= expected <= upper | Reporting-currency expected/P10/P90-compatible interval |
| opportunity_forecasts.win_probability | numeric(7,6); R | 0–1 | Scenario joint booking probability |
| data_quality_anomalies.anomaly_id | uuid; R | UUID | PK; controlled/analyzed issue identity |
| data_quality_anomalies.entity_name / entity_id / rule_code | varchar; R | nonblank identifiers | Affected entity and detector rule provenance |
| data_quality_anomalies.injected / detected_at / severity | boolean / timestamptz / varchar; R / O / R | INFO/WARNING/ERROR | Ground-truth/detection lifecycle |
| schema_migrations.version / applied_at | varchar / timestamptz; R / R | unique version; UTC | PK; migration audit history |
| validation_issues.issue_id | uuid; R | UUID | PK; validation result identity |
| validation_issues.rule_id / severity / affected_entity / affected_record_id / issue_type / explanation / recommended_action | varchar/text; R | nonblank rule/result metadata | Unique rule/entity/record/type; audit evidence |
| validation_issues.detected_at | timestamptz; R | UTC | Detection audit time |
| business_exceptions.exception_id | varchar(80); R | unique nonblank ID | PK; decision/exception identity |
| business_exceptions.entity_id / exception_type / severity / evidence | varchar/jsonb; R | nonblank; structured evidence | Affected entity and explanation |
| business_exceptions.detection_rule_or_model_version / expected_business_impact_reporting / recommended_next_action / created_at / resolution_status | varchar/numeric/text/timestamptz/varchar; R/O/R/R/R | reporting-money when present; UTC | Rule/model provenance and read-only workflow state |
| exception_resolution_history.resolution_id / exception_id | uuid / varchar; R | valid exception FK | PK; append-only resolution history |
| exception_resolution_history.status / note / resolved_by / occurred_at | varchar/text/varchar/timestamptz; R/R/O/R | nonblank status/note; UTC | Resolution actor/event provenance |

### Generated-only ground truth and anomaly exports

`ground_truth_outcomes.csv` contains `opportunity_id` (FK-like deterministic opportunity reference), `final_outcome` (terminal stage), `latent_quality`, `buyer_urgency`, `activity_count_at_decision`, `decision_score`, and `random_seed`; it is protected truth and never a model feature. `ground_truth.csv` contains `issue_id`, `issue_type`, `affected_entity`, `affected_record_id`, `detection_rule_id`, `expected_severity`, `expected_action`, and `explanation`; it labels the five isolated negative fixtures. `anomalous_forecast_inputs.csv` and `anomalous_aggregation_inputs.csv` are validation fixtures only and are never loaded into the valid production-shaped schema. `manifest.json` records configuration, seed, row counts and per-CSV SHA-256 values.
