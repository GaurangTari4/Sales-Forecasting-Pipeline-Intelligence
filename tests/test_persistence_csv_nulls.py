import unittest

from src.persistence.database import COLUMN_SPECS, Database, coerce_row_for_insert, ingest_generated_dataset


class CsvNullCoercionTests(unittest.TestCase):
    def test_blank_nullable_territory_date_becomes_none(self):
        row = coerce_row_for_insert(
            "territories",
            {"territory_id": "TER-001", "active_from": "2025-01-01", "active_to": ""},
        )
        self.assertEqual(row["active_from"], "2025-01-01")
        self.assertIsNone(row["active_to"])

    def test_non_empty_nullable_date_is_preserved(self):
        row = coerce_row_for_insert("territories", {"active_to": "2025-12-31"})
        self.assertEqual(row["active_to"], "2025-12-31")

    def test_blank_nullable_typed_and_foreign_key_values_become_none(self):
        self.assertIsNone(coerce_row_for_insert("sales_reps", {"active_to": ""})["active_to"])
        self.assertIsNone(
            coerce_row_for_insert("rep_territory_assignments", {"effective_to": ""})["effective_to"]
        )
        self.assertIsNone(coerce_row_for_insert("stage_history", {"from_stage": ""})["from_stage"])
        self.assertIsNone(coerce_row_for_insert("opportunity_change_events", {"old_value": ""})["old_value"])
        self.assertIsNone(
            coerce_row_for_insert("business_exceptions", {"expected_business_impact_reporting": ""})[
                "expected_business_impact_reporting"
            ]
        )
        self.assertIn("numeric", {spec.kind for spec in COLUMN_SPECS["business_exceptions"].values()})

    def test_blank_required_field_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "territories.active_from is required"):
            coerce_row_for_insert("territories", {"active_from": ""})

    def test_nullable_text_blank_is_preserved(self):
        row = coerce_row_for_insert("exception_resolution_history", {"resolved_by": ""})
        self.assertEqual(row["resolved_by"], "")

    def test_generated_identity_column_is_not_inserted(self):
        cursor = _RecordingCursor()
        Database().bulk_insert(
            cursor,
            "stage_probability_versions",
            [{"stage_probability_version_id": "1", "version_name": "synthetic-v1", "effective_to": ""}],
        )
        self.assertNotIn("stage_probability_version_id", cursor.sql)
        self.assertEqual(cursor.values, [("synthetic-v1", None)])

    def test_rows_with_different_csv_columns_are_rejected(self):
        cursor = _RecordingCursor()
        with self.assertRaisesRegex(ValueError, "does not match CSV columns"):
            Database().bulk_insert(
                cursor,
                "territories",
                [
                    {"territory_id": "TER-001", "active_to": ""},
                    {"territory_id": "TER-002"},
                ],
            )


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _RecordingCursor(_Cursor):
    def executemany(self, sql, values):
        self.sql = sql
        self.values = values


class _Connection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return _Cursor()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _Database:
    def __init__(self, failing_table=None):
        self.connection = _Connection()
        self.failing_table = failing_table
        self.tables = []

    def connect(self):
        return self.connection

    def bulk_insert(self, cursor, table, rows):
        self.tables.append(table)
        if table == self.failing_table:
            raise RuntimeError("simulated insert failure")


class TransactionHandlingTests(unittest.TestCase):
    def test_failed_seed_rolls_back_the_entire_transaction(self):
        database = _Database(failing_table="stages")
        with self.assertRaisesRegex(RuntimeError, "simulated insert failure"):
            ingest_generated_dataset(database, {"territories": [{"territory_id": "TER-001"}], "stages": [{"stage_code": "PROSPECTING"}]})
        self.assertEqual(database.connection.commits, 0)
        self.assertEqual(database.connection.rollbacks, 1)

    def test_successful_seed_commits_once(self):
        database = _Database()
        ingest_generated_dataset(database, {"territories": [{"territory_id": "TER-001"}]})
        self.assertEqual(database.connection.commits, 1)
        self.assertEqual(database.connection.rollbacks, 0)
