"""Guard that documented field inventory does not drift from SQL/CSV contracts."""
import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_schema_and_starter_export_columns_are_named_in_data_dictionary():
    documentation = (ROOT / "docs" / "data_dictionary.md").read_text(encoding="utf-8")
    assert "## Complete schema and export field catalogue" in documentation
    schema = (ROOT / "schemas" / "schema.sql").read_text(encoding="utf-8")
    schema_fields = re.findall(r"^\s{2}([a-z_]+)\s+(?:varchar|char|numeric|integer|smallint|bigint|boolean|date|timestamptz|jsonb|[a-z_]+_code)\b", schema, re.MULTILINE)
    missing_schema = sorted({field for field in schema_fields if field not in documentation})
    assert not missing_schema, missing_schema
    for export in (ROOT / "output" / "starter").glob("*.csv"):
        with export.open(encoding="utf-8", newline="") as handle:
            fields = next(csv.reader(handle), [])
        missing_export = [field for field in fields if field and field not in documentation]
        assert not missing_export, f"{export.name}: {missing_export}"
