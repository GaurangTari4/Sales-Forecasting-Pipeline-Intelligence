CREATE TABLE IF NOT EXISTS schema_migrations (version varchar(100) PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS validation_issues (
  issue_id uuid PRIMARY KEY, rule_id varchar(120) NOT NULL, severity varchar(16) NOT NULL,
  affected_entity varchar(80) NOT NULL, affected_record_id varchar(100) NOT NULL,
  issue_type varchar(120) NOT NULL, explanation text NOT NULL, recommended_action varchar(40) NOT NULL,
  detected_at timestamptz NOT NULL DEFAULT now(), UNIQUE(rule_id, affected_entity, affected_record_id, issue_type)
);
CREATE TABLE IF NOT EXISTS business_exceptions (
  exception_id varchar(80) PRIMARY KEY, entity_id varchar(100) NOT NULL, exception_type varchar(100) NOT NULL,
  severity varchar(16) NOT NULL, evidence jsonb NOT NULL, detection_rule_or_model_version varchar(120) NOT NULL,
  expected_business_impact_reporting numeric(18,2), recommended_next_action text NOT NULL,
  created_at timestamptz NOT NULL, resolution_status varchar(32) NOT NULL, UNIQUE(exception_id)
);
CREATE TABLE IF NOT EXISTS exception_resolution_history (
  resolution_id uuid PRIMARY KEY, exception_id varchar(80) NOT NULL REFERENCES business_exceptions ON DELETE RESTRICT,
  status varchar(32) NOT NULL, note text NOT NULL, resolved_by varchar(100), occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_forecast_runs_snapshot ON forecast_runs(forecast_snapshot_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_owner_created ON opportunities(owner_rep_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_accounts_territory ON accounts(territory_id);
CREATE INDEX IF NOT EXISTS idx_exceptions_status_severity ON business_exceptions(resolution_status, severity, created_at DESC);
CREATE OR REPLACE FUNCTION reject_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'append-only table % cannot be %', TG_TABLE_NAME, TG_OP; END; $$;
DROP TRIGGER IF EXISTS no_stage_history_mutation ON stage_history;
CREATE TRIGGER no_stage_history_mutation BEFORE UPDATE OR DELETE ON stage_history FOR EACH ROW EXECUTE FUNCTION reject_event_mutation();
DROP TRIGGER IF EXISTS no_booking_mutation ON historical_bookings;
CREATE TRIGGER no_booking_mutation BEFORE UPDATE OR DELETE ON historical_bookings FOR EACH ROW EXECUTE FUNCTION reject_event_mutation();
DROP TRIGGER IF EXISTS no_snapshot_mutation ON forecast_snapshots;
CREATE TRIGGER no_snapshot_mutation BEFORE UPDATE OR DELETE ON forecast_snapshots FOR EACH ROW EXECUTE FUNCTION reject_event_mutation();
