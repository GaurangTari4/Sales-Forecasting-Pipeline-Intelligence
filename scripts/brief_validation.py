"""Produce evidence reports for the BUSS business-brief audit.

The command compares already-generated, isolated FULL datasets and evaluates the
five controlled anomaly fixtures from the deterministic generator.  It never
connects to PostgreSQL or modifies a demo dataset.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from src.generator import GeneratorConfig, SalesDataGenerator
from src.generator.anomalies import detection_metrics, detect_anomalies, inject_controlled_anomalies


def _logical_checksum(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = [json.dumps(row, sort_keys=True, separators=(",", ":")) for row in csv.DictReader(stream)]
    return hashlib.sha256("\n".join(sorted(rows)).encode("utf-8")).hexdigest()


def _manifest(directory: Path) -> dict:
    return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))


def full_scale_report(first: Path, second: Path) -> dict:
    first_manifest, second_manifest = _manifest(first), _manifest(second)
    names = sorted(first_manifest["row_counts"])
    logical = {
        name: {
            "first": _logical_checksum(first / f"{name}.csv"),
            "second": _logical_checksum(second / f"{name}.csv"),
        }
        for name in names
    }
    for value in logical.values():
        value["match"] = value["first"] == value["second"]
    rows_match = first_manifest["row_counts"] == second_manifest["row_counts"]
    csv_match = first_manifest["sha256"] == second_manifest["sha256"]
    logical_match = all(value["match"] for value in logical.values())
    return {
        "seed": first_manifest["seed"],
        "first_output": str(first),
        "second_output": str(second),
        "row_counts": first_manifest["row_counts"],
        "csv_sha256": first_manifest["sha256"],
        "logical_record_sha256": logical,
        "row_counts_match": rows_match,
        "csv_checksums_match": csv_match,
        "logical_checksums_match": logical_match,
        "reproducible": rows_match and csv_match and logical_match,
        "runtime_note": "Generation timing is reported by the invoking command, not synthesized by this comparison utility.",
    }


def anomaly_report() -> dict:
    baseline = SalesDataGenerator(GeneratorConfig(reps=20, accounts=20, opportunities=200)).generate()
    anomalous = inject_controlled_anomalies(baseline)
    found, truth = detect_anomalies(anomalous), anomalous["ground_truth"]
    overall = detection_metrics(found, truth)
    by_type = {}
    for issue_type in sorted(row["issue_type"] for row in truth):
        expected = [row for row in truth if row["issue_type"] == issue_type]
        actual = [row for row in found if row["issue_type"] == issue_type]
        by_type[issue_type] = detection_metrics(actual, expected)
    return {
        "simulation_seed": 20261022,
        "ground_truth_path": "data/ground_truth/ground_truth.csv",
        "overall": overall,
        "by_anomaly_type": by_type,
        "detected_actions": {row["issue_type"]: row["expected_action"] for row in found},
        "status": "PASS" if overall["false_positives"] == 0 and overall["false_negatives"] == 0 else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-a", type=Path, required=True)
    parser.add_argument("--full-b", type=Path, required=True)
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    args = parser.parse_args()
    reproducibility = full_scale_report(args.full_a, args.full_b)
    anomalies = anomaly_report()
    args.reports.mkdir(parents=True, exist_ok=True)
    (args.reports / "reproducibility_report.json").write_text(json.dumps(reproducibility, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.reports / "anomaly_validation.json").write_text(json.dumps(anomalies, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# FULL-scale validation",
        "",
        f"- Fixed seed: `{reproducibility['seed']}`",
        f"- First isolated output: `{reproducibility['first_output']}`",
        f"- Second isolated output: `{reproducibility['second_output']}`",
        f"- CSV checksums match: **{reproducibility['csv_checksums_match']}**",
        f"- Sorted logical-record checksums match: **{reproducibility['logical_checksums_match']}**",
        f"- Reproducible: **{reproducibility['reproducible']}**",
        "",
        "## Row counts",
        "",
        "| Table | Rows |",
        "|---|---:|",
        *[f"| {name} | {count} |" for name, count in sorted(reproducibility["row_counts"].items())],
        "",
        "The report compares serialized CSV SHA-256 values and canonical sorted logical-record SHA-256 values. It does not claim database-load timing or resource usage that was not collected by this command.",
    ]
    (args.reports / "full_scale_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"reproducible": reproducibility["reproducible"], "anomaly_status": anomalies["status"]}, sort_keys=True))
    return 0 if reproducibility["reproducible"] and anomalies["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
