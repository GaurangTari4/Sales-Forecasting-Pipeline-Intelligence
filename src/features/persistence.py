"""Deterministic CSV and manifest persistence for reproducible feature datasets."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path

from .contracts import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION


def persist_feature_dataset(feature_rows: list[dict], labels: list[dict], output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    files = {"features.csv": (feature_rows, FEATURE_COLUMNS), "labels.csv": (labels, tuple(labels[0]) if labels else ())}
    checksums = {}
    for name, (rows, fields) in files.items():
        path = output / name
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
        checksums[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"feature_schema_version": FEATURE_SCHEMA_VERSION, "feature_rows": len(feature_rows), "label_rows": len(labels), "sha256": checksums}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest
