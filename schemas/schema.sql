-- PostgreSQL 15+ schema. Execute with: psql "$DATABASE_URL" -f schemas/schema.sql
-- Business identifiers are immutable. Events are append-only: application roles must
-- not receive UPDATE/DELETE rights on *_events, stage_history, or bookings.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TYPE region_code AS ENUM ('NA','EMEA','APAC');
CREATE TYPE rep_role AS ENUM ('ACCOUNT_EXECUTIVE','SALES_MANAGER');
CREATE TYPE industry_code AS ENUM ('TECHNOLOGY','FINANCIAL_SERVICES','HEALTHCARE','MANUFACTURING','RETAIL','PROFESSIONAL_SERVICES');
CREATE TYPE product_type_code AS ENUM ('SUBSCRIPTION','SERVICES');
CREATE TYPE stage_code AS ENUM ('PROSPECTING','QUALIFICATION','DISCOVERY','PROPOSAL','NEGOTIATION','CLOSED_WON','CLOSED_LOST');
CREATE TYPE activity_type_code AS ENUM ('CALL','EMAIL','MEETING','DEMO','TASK');
CREATE TYPE activity_outcome_code AS ENUM ('COMPLETED','NO_SHOW','BOUNCED','CANCELLED');
CREATE TYPE snapshot_status_code AS ENUM ('DRAFT','FINALIZED','SUPERSEDED');
CREATE TYPE scenario_code AS ENUM ('CONSERVATIVE','BASE','OPTIMISTIC','CUSTOM');

CREATE TABLE territories (
  territory_id varchar(7) PRIMARY KEY CHECK (territory_id ~ '^TER-[0-9]{3}$'),
  territory_name varchar(100) NOT NULL UNIQUE CHECK (btrim(territory_name) <> ''),
  region region_code NOT NULL, active_from date NOT NULL, active_to date,
  CHECK (active_to IS NULL OR active_to >= active_from)
);
CREATE TABLE sales_reps (
  sales_rep_id varchar(10) PRIMARY KEY CHECK (sales_rep_id ~ '^REP-[0-9]{6}$'),
  rep_name varchar(100) NOT NULL CHECK (btrim(rep_name) <> ''), hire_date date NOT NULL,
  role rep_role NOT NULL, active_from date NOT NULL, active_to date,
  CHECK (active_from >= hire_date), CHECK (active_to IS NULL OR active_to >= active_from)
);
-- Purpose: preserves ownership territory at any as-of date; replaces a mutable rep.territory_id.
CREATE TABLE rep_territory_assignments (
  assignment_id varchar(18) PRIMARY KEY CHECK (assignment_id ~ '^RTA-REP-[0-9]{6}-[0-9]{3}$'),
  sales_rep_id varchar(10) NOT NULL REFERENCES sales_reps ON DELETE RESTRICT,
  territory_id varchar(7) NOT NULL REFERENCES territories ON DELETE RESTRICT,
  effective_from date NOT NULL, effective_to date,
  effective_period daterange GENERATED ALWAYS AS (daterange(effective_from, effective_to, '[]')) STORED,
  CHECK (effective_to IS NULL OR effective_to >= effective_from),
  EXCLUDE USING gist (sales_rep_id WITH =, effective_period WITH &&)
);
CREATE TABLE accounts (
  account_id varchar(10) PRIMARY KEY CHECK (account_id ~ '^ACC-[0-9]{6}$'),
  account_name varchar(200) NOT NULL UNIQUE CHECK (btrim(account_name) <> ''),
  territory_id varchar(7) NOT NULL REFERENCES territories ON DELETE RESTRICT,
  industry industry_code NOT NULL, employee_count integer NOT NULL CHECK (employee_count > 0),
  active_from date NOT NULL, active_to date,
  CHECK (active_to IS NULL OR active_to >= active_from)
);
CREATE TABLE opportunities (
  opportunity_id varchar(15) PRIMARY KEY CHECK (opportunity_id ~ '^OPP-[0-9]{4}-[0-9]{6}$'),
  account_id varchar(10) NOT NULL REFERENCES accounts ON DELETE RESTRICT,
  owner_rep_id varchar(10) NOT NULL REFERENCES sales_reps ON DELETE RESTRICT,
  product_name varchar(100) NOT NULL CHECK (btrim(product_name) <> ''),
  product_type product_type_code NOT NULL, created_at timestamptz NOT NULL,
  original_expected_close_date date NOT NULL, transaction_currency char(3) NOT NULL CHECK (transaction_currency ~ '^[A-Z]{3}$'),
  initial_amount numeric(18,2) NOT NULL CHECK (initial_amount >= 0),
  CHECK (original_expected_close_date >= created_at::date)
);
-- Purpose: controlled definition of lifecycle states; stage rank is not an empirical rate.
CREATE TABLE stages (
  stage_code stage_code PRIMARY KEY, display_name varchar(50) NOT NULL UNIQUE,
  stage_rank smallint NOT NULL CHECK (stage_rank >= 1), is_terminal boolean NOT NULL,
  CHECK ((stage_code IN ('CLOSED_WON','CLOSED_LOST')) = is_terminal)
);
CREATE TABLE stage_history (
  stage_event_id varchar(25) PRIMARY KEY CHECK (stage_event_id ~ '^STG-OPP-[0-9]{4}-[0-9]{6}-[0-9]{3}$'),
  opportunity_id varchar(15) NOT NULL REFERENCES opportunities ON DELETE RESTRICT,
  lifecycle_number integer NOT NULL DEFAULT 1 CHECK (lifecycle_number >= 1), event_sequence integer NOT NULL CHECK (event_sequence >= 1),
  from_stage stage_code REFERENCES stages, to_stage stage_code NOT NULL REFERENCES stages,
  occurred_at timestamptz NOT NULL, reason_code varchar(50) NOT NULL CHECK (btrim(reason_code) <> ''),
  UNIQUE (opportunity_id, lifecycle_number, event_sequence),
  CHECK ((from_stage IS NULL AND event_sequence = 1) OR from_stage IS NOT NULL)
);
CREATE TABLE opportunity_change_events (
  change_event_id varchar(29) PRIMARY KEY CHECK (change_event_id ~ '^CHG-OPP-[0-9]{4}-[0-9]{6}-[0-9]{3}$'),
  opportunity_id varchar(15) NOT NULL REFERENCES opportunities ON DELETE RESTRICT,
  occurred_at timestamptz NOT NULL, change_type varchar(30) NOT NULL CHECK (change_type IN ('AMOUNT','EXPECTED_CLOSE_DATE','OWNER','CURRENCY')),
  old_value jsonb, new_value jsonb NOT NULL, reason_code varchar(50) NOT NULL,
  CHECK (old_value IS DISTINCT FROM new_value)
);
CREATE TABLE activities (
  activity_id varchar(25) PRIMARY KEY CHECK (activity_id ~ '^ACT-OPP-[0-9]{4}-[0-9]{6}-[0-9]{3}$'),
  opportunity_id varchar(15) NOT NULL REFERENCES opportunities ON DELETE RESTRICT,
  sales_rep_id varchar(10) NOT NULL REFERENCES sales_reps ON DELETE RESTRICT,
  occurred_at timestamptz NOT NULL, activity_type activity_type_code NOT NULL,
  outcome activity_outcome_code NOT NULL, duration_minutes integer NOT NULL CHECK (duration_minutes BETWEEN 0 AND 1440)
);
CREATE TABLE quotas (
  quota_id varchar(25) PRIMARY KEY CHECK (quota_id ~ '^QUOTA-REP-[0-9]{6}-[0-9]{4}Q[1-4]$'),
  sales_rep_id varchar(10) NOT NULL REFERENCES sales_reps ON DELETE RESTRICT,
  fiscal_quarter char(6) NOT NULL CHECK (fiscal_quarter ~ '^[0-9]{4}Q[1-4]$'),
  quota_amount numeric(18,2) NOT NULL CHECK (quota_amount >= 0), currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  UNIQUE (sales_rep_id, fiscal_quarter)
);
CREATE TABLE exchange_rates (
  rate_date date NOT NULL, from_currency char(3) NOT NULL CHECK (from_currency ~ '^[A-Z]{3}$'),
  to_currency char(3) NOT NULL CHECK (to_currency ~ '^[A-Z]{3}$'),
  rate numeric(20,10) NOT NULL CHECK (rate > 0), source varchar(100) NOT NULL,
  PRIMARY KEY (rate_date, from_currency, to_currency), CHECK (from_currency <> to_currency)
);
CREATE TABLE historical_bookings (
  booking_id varchar(25) PRIMARY KEY CHECK (booking_id ~ '^BKG-OPP-[0-9]{4}-[0-9]{6}-[0-9]{3}$'),
  opportunity_id varchar(15) NOT NULL REFERENCES opportunities ON DELETE RESTRICT,
  recognized_at timestamptz NOT NULL, booking_amount numeric(18,2) NOT NULL CHECK (booking_amount >= 0),
  currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'), booking_type varchar(20) NOT NULL DEFAULT 'INITIAL' CHECK (booking_type IN ('INITIAL','ADJUSTMENT','REVERSAL')),
  UNIQUE (opportunity_id, recognized_at, booking_type)
);
-- Header is the authoritative as-of boundary. Detail holds one observation per opportunity.
CREATE TABLE forecast_snapshots (
  forecast_snapshot_id varchar(20) PRIMARY KEY CHECK (forecast_snapshot_id ~ '^FCST-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{3}$'),
  snapshot_at timestamptz NOT NULL, horizon_start date NOT NULL, horizon_end date NOT NULL,
  reporting_currency char(3) NOT NULL CHECK (reporting_currency ~ '^[A-Z]{3}$'), status snapshot_status_code NOT NULL DEFAULT 'DRAFT',
  created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (snapshot_at, horizon_start, horizon_end), CHECK (horizon_end >= horizon_start)
);
CREATE TABLE snapshot_opportunities (
  forecast_snapshot_id varchar(20) NOT NULL REFERENCES forecast_snapshots ON DELETE RESTRICT,
  opportunity_id varchar(15) NOT NULL REFERENCES opportunities ON DELETE RESTRICT,
  stage_at_snapshot stage_code NOT NULL REFERENCES stages, amount_transaction_currency numeric(18,2) NOT NULL CHECK (amount_transaction_currency >= 0),
  transaction_currency char(3) NOT NULL CHECK (transaction_currency ~ '^[A-Z]{3}$'), expected_close_date date NOT NULL,
  PRIMARY KEY (forecast_snapshot_id, opportunity_id)
);
-- Versioned configuration, distinct from actual observed conversion rates computed from stage_history.
CREATE TABLE stage_probability_versions (
  stage_probability_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  version_name varchar(100) NOT NULL, stage_code stage_code NOT NULL REFERENCES stages ON DELETE RESTRICT,
  scenario scenario_code NOT NULL DEFAULT 'BASE', probability numeric(7,6) NOT NULL CHECK (probability BETWEEN 0 AND 1),
  effective_from date NOT NULL, effective_to date, created_at timestamptz NOT NULL DEFAULT now(),
  effective_period daterange GENERATED ALWAYS AS (daterange(effective_from, effective_to, '[]')) STORED,
  CHECK (effective_to IS NULL OR effective_to >= effective_from),
  UNIQUE (version_name, stage_code, scenario, effective_from),
  EXCLUDE USING gist (stage_code WITH =, scenario WITH =, effective_period WITH &&)
);
CREATE TABLE forecast_runs (
  forecast_run_id uuid PRIMARY KEY, forecast_snapshot_id varchar(20) NOT NULL REFERENCES forecast_snapshots ON DELETE RESTRICT,
  model_version varchar(100) NOT NULL, feature_version varchar(100) NOT NULL,
  scenario scenario_code NOT NULL, stage_probability_version_name varchar(100) NOT NULL,
  data_hash char(64) NOT NULL CHECK (data_hash ~ '^[a-f0-9]{64}$'), assumptions jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
  -- Runs are immutable historical facts. Identical input configuration may be run
  -- more than once, so only the run ID is unique.
);
CREATE TABLE opportunity_forecasts (
  forecast_run_id uuid NOT NULL REFERENCES forecast_runs ON DELETE RESTRICT,
  opportunity_id varchar(15) NOT NULL REFERENCES opportunities ON DELETE RESTRICT,
  expected_booking_reporting numeric(18,2) NOT NULL CHECK (expected_booking_reporting >= 0),
  lower_booking_reporting numeric(18,2) NOT NULL CHECK (lower_booking_reporting >= 0),
  upper_booking_reporting numeric(18,2) NOT NULL CHECK (upper_booking_reporting >= lower_booking_reporting),
  win_probability numeric(7,6) NOT NULL CHECK (win_probability BETWEEN 0 AND 1),
  PRIMARY KEY (forecast_run_id, opportunity_id), CHECK (expected_booking_reporting BETWEEN lower_booking_reporting AND upper_booking_reporting)
);
CREATE TABLE data_quality_anomalies (
  anomaly_id uuid PRIMARY KEY, entity_name varchar(64) NOT NULL, entity_id varchar(64) NOT NULL,
  rule_code varchar(100) NOT NULL, injected boolean NOT NULL DEFAULT false, detected_at timestamptz, severity varchar(10) NOT NULL CHECK (severity IN ('INFO','WARNING','ERROR')),
  UNIQUE (entity_name, entity_id, rule_code)
);

CREATE INDEX idx_stage_history_opp_time ON stage_history(opportunity_id, occurred_at DESC);
CREATE INDEX idx_change_events_opp_time ON opportunity_change_events(opportunity_id, occurred_at DESC);
CREATE INDEX idx_activities_opp_time ON activities(opportunity_id, occurred_at DESC);
CREATE INDEX idx_bookings_recognized ON historical_bookings(recognized_at);
CREATE INDEX idx_snapshot_opportunities_close ON snapshot_opportunities(forecast_snapshot_id, expected_close_date);
