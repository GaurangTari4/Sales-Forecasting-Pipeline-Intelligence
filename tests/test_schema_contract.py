from datetime import date, datetime, timezone
from pathlib import Path
import re
import unittest
from pydantic import ValidationError
from schemas.models import Opportunity, ForecastSnapshot, StageHistory
from schemas.enums import OpportunityStage, ProductType, SnapshotStatus

ROOT = Path(__file__).parents[1]


class SchemaContractTests(unittest.TestCase):
    def test_required_id_patterns_accept_canonical_values(self):
        row = Opportunity(opportunity_id="OPP-2026-000001", account_id="ACC-000001", owner_rep_id="REP-000001",
            product_name="Analytics Cloud", product_type=ProductType.SUBSCRIPTION,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), original_expected_close_date=date(2026, 3, 31),
            transaction_currency="USD", initial_amount="100.00")
        self.assertEqual(row.opportunity_id, "OPP-2026-000001")
        self.assertEqual(StageHistory(stage_event_id="STG-OPP-2026-000001-001", opportunity_id=row.opportunity_id,
            lifecycle_number=1, event_sequence=1, to_stage=OpportunityStage.PROSPECTING,
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc), reason_code="CREATED").event_sequence, 1)

    def test_invalid_identifiers_currency_and_dates_are_rejected(self):
        with self.assertRaises(ValidationError):
            Opportunity(opportunity_id="OPP-26-1", account_id="ACC-000001", owner_rep_id="REP-000001", product_name="x",
                product_type="SUBSCRIPTION", created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                original_expected_close_date=date(2026, 1, 1), transaction_currency="usd", initial_amount="1")

    def test_snapshot_semantics_validate_horizon(self):
        with self.assertRaises(ValidationError):
            ForecastSnapshot(forecast_snapshot_id="FCST-2026-01-31-001", snapshot_at=datetime.now(timezone.utc),
                horizon_start=date(2026, 4, 1), horizon_end=date(2026, 3, 31), reporting_currency="USD", status=SnapshotStatus.DRAFT)

    def test_schema_has_core_fk_and_event_constraints(self):
        sql = (ROOT / "schemas" / "schema.sql").read_text(encoding="utf-8")
        for table in ("territories", "sales_reps", "accounts", "opportunities", "stages", "stage_history", "activities", "quotas", "historical_bookings", "forecast_snapshots"):
            self.assertRegex(sql, rf"CREATE TABLE {table} ")
        self.assertIn("EXCLUDE USING gist (sales_rep_id WITH =, effective_period WITH &&)", sql)
        self.assertNotIn("UNIQUE (forecast_snapshot_id, opportunity_id)", sql)
        self.assertIn("PRIMARY KEY (forecast_snapshot_id, opportunity_id)", sql)
