import csv
import json
from pathlib import Path


def load_csv_dataset(directory: Path) -> dict[str, list[dict[str, str]]]:
    dataset = {}
    for path in sorted(directory.glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as stream:
            dataset[path.stem] = list(csv.DictReader(stream))
    return dataset


def write_report(report, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    lines = ["# Validation summary", "", f"- Records checked: {report.records_checked}", f"- Errors: {report.errors}", f"- Warnings: {report.warnings}", f"- Quarantined records: {report.quarantined_records}", f"- Detected known anomalies: {report.known_anomalies_detected}", "", "| Rule | Severity | Entity | Record | Action | Explanation |", "|---|---|---|---|---|---|"]
    for result in report.results:
        lines.append(f"| {result.rule_id} | {result.severity.value} | {result.affected_entity} | {result.affected_record_id} | {result.recommended_action.value} | {result.explanation} |")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
