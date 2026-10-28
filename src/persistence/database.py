"""PostgreSQL persistence with schema-aware CSV coercion.

CSV has no native NULL representation: :mod:`csv` reads both an absent optional
value and an intentionally blank value as ``""``.  The schema map below is the
single place where the ingestion boundary decides which blank cells mean SQL
NULL.  In particular, it never turns arbitrary text fields into NULL.
"""
from __future__ import annotations
from dataclasses import dataclass
import json, os, uuid
from pathlib import Path

TABLES=("territories","stages","sales_reps","rep_territory_assignments","accounts","opportunities","stage_history","opportunity_change_events","activities","quotas","exchange_rates","historical_bookings","forecast_snapshots","snapshot_opportunities","stage_probability_versions")


@dataclass(frozen=True)
class ColumnSpec:
 """Nullability and logical type for a persisted column.

 ``text`` intentionally preserves an empty string.  Every other nullable type
 treats a blank CSV cell as an absent value.  A blank required field is rejected
 before PostgreSQL receives a malformed typed value.
 """
 nullable: bool = False
 kind: str = "text"


# This mirrors every nullable column in schemas/schema.sql and the applied
# persistence migrations that can be passed to ``bulk_insert``.  A column that
# is absent from this mapping is required at the CSV ingestion boundary.  That
# deliberately makes newly added nullable database columns an explicit review
# item rather than silently changing their import semantics.
COLUMN_SPECS: dict[str, dict[str, ColumnSpec]] = {
 "territories": {"active_to": ColumnSpec(True, "date")},
 "sales_reps": {"active_to": ColumnSpec(True, "date")},
 "rep_territory_assignments": {"effective_to": ColumnSpec(True, "date")},
 "accounts": {"active_to": ColumnSpec(True, "date")},
 "stage_history": {"from_stage": ColumnSpec(True, "foreign_key")},
 "opportunity_change_events": {"old_value": ColumnSpec(True, "json")},
 "stage_probability_versions": {"effective_to": ColumnSpec(True, "date")},
 "data_quality_anomalies": {"detected_at": ColumnSpec(True, "timestamp")},
 "business_exceptions": {"expected_business_impact_reporting": ColumnSpec(True, "numeric")},
 "exception_resolution_history": {"resolved_by": ColumnSpec(True, "text")},
}

# The generator exports deterministic IDs for traceability, while PostgreSQL
# owns identity values declared GENERATED ALWAYS.  Do not send those columns to
# INSERT; the source row remains otherwise intact for manifests and CSV audits.
INSERT_COLUMN_EXCLUSIONS: dict[str, set[str]] = {
 "stage_probability_versions": {"stage_probability_version_id"},
}


def coerce_row_for_insert(table: str, row: dict, columns: list[str] | None = None) -> dict:
 """Return one row ready for psycopg without erasing valid text content."""
 columns = columns or list(row)
 specs = COLUMN_SPECS.get(table, {})
 converted = {}
 for column in columns:
  value = row.get(column)
  spec = specs.get(column, ColumnSpec())
  if value in (None, ""):
   if spec.nullable and spec.kind != "text":
    converted[column] = None
   elif value is None and spec.nullable:
    converted[column] = None
   elif value == "" and spec.nullable:
    # Empty text is a valid value for the few nullable free-text columns.
    converted[column] = value
   elif value in (None, ""):
    raise ValueError(f"{table}.{column} is required and cannot be blank")
  else:
   converted[column] = value
 return converted

class Database:
 def __init__(self,url=None): self.url=url or os.environ.get("DATABASE_URL");
 def connect(self):
  if not self.url: raise RuntimeError("DATABASE_URL is required; credentials are never embedded in code")
  try:
   import psycopg
  except ImportError as e: raise RuntimeError("Install psycopg[binary] to use PostgreSQL persistence") from e
  return psycopg.connect(self.url)
 def migrate(self,root=Path("migrations")):
  with self.connect() as conn:
   with conn.cursor() as cur:
    cur.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version varchar(100) PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    for path in sorted(root.glob("*.sql")):
     cur.execute("SELECT 1 FROM schema_migrations WHERE version=%s",(path.name,))
     if cur.fetchone(): continue
     # Migration 001 is a psql wrapper (it uses \ir). Execute its approved schema
     # directly so the Python CLI and the container bootstrap follow the same path.
     source = root.parent / "schemas" / "schema.sql" if path.name.startswith("001_") else path
     cur.execute(source.read_text(encoding="utf-8")); cur.execute("INSERT INTO schema_migrations(version) VALUES(%s)",(path.name,))
 def bulk_insert(self,cur,table,rows):
  if not rows:return
  if table not in TABLES and table not in COLUMN_SPECS and table not in {"validation_issues", "opportunity_forecasts"}:
   raise ValueError(f"Unsupported ingestion table: {table}")
  columns=[column for column in rows[0] if column not in INSERT_COLUMN_EXCLUSIONS.get(table, set())]
  expected_columns=set(columns)
  for index, row in enumerate(rows, start=1):
   row_columns={column for column in row if column not in INSERT_COLUMN_EXCLUSIONS.get(table, set())}
   if row_columns != expected_columns:
    missing=sorted(expected_columns-row_columns); extra=sorted(row_columns-expected_columns)
    raise ValueError(f"{table} row {index} does not match CSV columns; missing={missing}, extra={extra}")
  normalized = [coerce_row_for_insert(table, row, columns) for row in rows]
  values=[tuple(json.dumps(row[column]) if isinstance(row[column],(dict,list)) else row[column] for column in columns) for row in normalized]
  sql=f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(['%s']*len(columns))}) ON CONFLICT DO NOTHING"
  cur.executemany(sql,values)

def ingest_generated_dataset(db:Database,dataset):
 """Single transaction, dependency order, repeatable with natural-key conflict handling."""
 with db.connect() as conn:
  try:
   with conn.cursor() as cur:
    for table in TABLES: db.bulk_insert(cur,table,dataset.get(table,[]))
   conn.commit()
  except Exception:
   conn.rollback()
   raise
 return {table:len(dataset.get(table,[])) for table in TABLES}

def store_forecast_run(db,run_id,snapshot_id,metadata,opportunity_forecasts):
 with db.connect() as conn:
  with conn.cursor() as cur:
   cur.execute("INSERT INTO forecast_runs(forecast_run_id,forecast_snapshot_id,model_version,feature_version,scenario,stage_probability_version_name,data_hash,assumptions) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",(run_id,snapshot_id,metadata['model_version'],metadata['feature_version'],metadata['scenario'],metadata['stage_probability_version_name'],metadata['data_hash'],json.dumps(metadata['assumptions'])))
   db.bulk_insert(cur,"opportunity_forecasts",opportunity_forecasts)
def store_validation_issues(db,issues):
 rows=[{"issue_id":str(uuid.uuid4()),"rule_id":x["rule_id"],"severity":str(x["severity"]),"affected_entity":x["affected_entity"],"affected_record_id":x["affected_record_id"],"issue_type":x["issue_type"],"explanation":x["explanation"],"recommended_action":str(x["recommended_action"])} for x in issues]
 with db.connect() as conn:
  with conn.cursor() as cur: db.bulk_insert(cur,"validation_issues",rows)
