import csv
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path


def _value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


def write_exports(dataset: dict[str, list[dict]], output: Path, manifest: dict) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    checksums, counts = {}, {}
    for name, rows in dataset.items():
        path = output / f"{name}.csv"
        fields = list(rows[0]) if rows else manifest["empty_table_columns"].get(name, [])
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows([{key: _value(value) for key, value in row.items()} for row in rows])
        counts[name] = len(rows)
        checksums[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest.update({"row_counts": counts, "sha256": checksums})
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return counts
