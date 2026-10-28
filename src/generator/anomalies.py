"""Controlled anomaly fixtures and detectors. They are never added to baseline data."""
from __future__ import annotations
from copy import deepcopy
from datetime import timedelta


ISSUES = {
    "FUTURE_OUTCOME_LEAKAGE": ("LEAKAGE.FEATURE_AS_OF", "ERROR", "QUARANTINE_FEATURE_SET"),
    "STAGE_PROBABILITY_MISMATCH": ("FORECAST.STAGE_PROBABILITY_EFFECTIVE_DATE", "ERROR", "RECOMPUTE_FORECAST_INPUT"),
    "DUPLICATE_OPPORTUNITY_COUNT": ("AGGREGATION.UNIQUE_SNAPSHOT_OPPORTUNITY", "ERROR", "DEDUPLICATE_AGGREGATION_INPUT"),
    "CLOSE_DATE_BEFORE_CREATION": ("OPPORTUNITY.EXPECTED_CLOSE_AFTER_CREATION", "ERROR", "QUARANTINE_EVENT"),
    "MIXED_CURRENCY_TOTAL": ("AGGREGATION.COMMON_REPORTING_CURRENCY", "ERROR", "CONVERT_OR_REJECT_TOTAL"),
}


def _truth(issue_type, entity, record_id, explanation):
    rule, severity, action = ISSUES[issue_type]
    return {"issue_id": f"ISS-{issue_type}-{record_id}", "issue_type": issue_type, "affected_entity": entity,
            "affected_record_id": record_id, "detection_rule_id": rule, "expected_severity": severity,
            "expected_action": action, "explanation": explanation}


def inject_controlled_anomalies(baseline: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Return a deterministic anomalous copy containing exactly one case of each type."""
    data = deepcopy(baseline)
    histories = sorted(data["stage_history"], key=lambda r: (r["opportunity_id"], r["occurred_at"], r["event_sequence"]))
    snapshots = sorted(data["forecast_snapshots"], key=lambda r: r["snapshot_at"])
    # A terminal event after a snapshot is a legitimate label but invalid as a feature at that snapshot.
    terminal = next(event for event in histories if event["to_stage"] in {"CLOSED_WON", "CLOSED_LOST"} and any(s["horizon_end"] < event["occurred_at"].date() for s in snapshots))
    snapshot = next(s for s in snapshots if s["horizon_end"] < terminal["occurred_at"].date())
    stage_row = next(row for row in data["snapshot_opportunities"] if row["forecast_snapshot_id"] == snapshot["forecast_snapshot_id"])
    config = next(row for row in data["stage_probability_versions"] if row["stage_code"] == stage_row["stage_at_snapshot"] and row["scenario"] == "BASE")
    data["anomalous_forecast_inputs"] = [
        {"input_id": "AFI-001", "forecast_snapshot_id": snapshot["forecast_snapshot_id"], "opportunity_id": terminal["opportunity_id"], "feature_name": "final_outcome", "feature_role": "feature", "feature_value": terminal["to_stage"], "source_event_at": terminal["occurred_at"], "stage_probability": None},
        # This is intentionally a label and remains legitimate after horizon; detector must not flag it.
        {"input_id": "AFI-002", "forecast_snapshot_id": snapshot["forecast_snapshot_id"], "opportunity_id": terminal["opportunity_id"], "feature_name": "final_outcome_label", "feature_role": "label", "feature_value": terminal["to_stage"], "source_event_at": terminal["occurred_at"], "stage_probability": None},
        {"input_id": "AFI-003", "forecast_snapshot_id": snapshot["forecast_snapshot_id"], "opportunity_id": stage_row["opportunity_id"], "feature_name": "stage_probability", "feature_role": "feature", "feature_value": None, "source_event_at": snapshot["snapshot_at"], "stage_probability": float(config["probability"]) + .111111},
    ]
    data["anomalous_aggregation_inputs"] = [
        {"input_id": "AAI-001", "aggregation_id": "AGG-DUP-001", "forecast_snapshot_id": snapshot["forecast_snapshot_id"], "opportunity_id": stage_row["opportunity_id"], "amount": "100.00", "currency": "USD", "converted_to_reporting": True},
        {"input_id": "AAI-002", "aggregation_id": "AGG-DUP-001", "forecast_snapshot_id": snapshot["forecast_snapshot_id"], "opportunity_id": stage_row["opportunity_id"], "amount": "100.00", "currency": "USD", "converted_to_reporting": True},
        {"input_id": "AAI-003", "aggregation_id": "AGG-FX-001", "forecast_snapshot_id": snapshot["forecast_snapshot_id"], "opportunity_id": stage_row["opportunity_id"], "amount": "100.00", "currency": "USD", "converted_to_reporting": False},
        {"input_id": "AAI-004", "aggregation_id": "AGG-FX-001", "forecast_snapshot_id": snapshot["forecast_snapshot_id"], "opportunity_id": terminal["opportunity_id"], "amount": "100.00", "currency": "EUR", "converted_to_reporting": False},
    ]
    bad_opp = data["opportunities"][0]
    data["opportunity_change_events"].append({"change_event_id": f"CHG-{bad_opp['opportunity_id']}-999", "opportunity_id": bad_opp["opportunity_id"], "occurred_at": bad_opp["created_at"] + timedelta(hours=1), "change_type": "EXPECTED_CLOSE_DATE", "old_value": {"date": bad_opp["original_expected_close_date"].isoformat()}, "new_value": {"date": (bad_opp["created_at"].date() - timedelta(days=1)).isoformat()}, "reason_code": "CONTROLLED_BAD_DATE"})
    data["ground_truth"] = [
        _truth("FUTURE_OUTCOME_LEAKAGE", "anomalous_forecast_inputs", "AFI-001", "Final outcome event occurs after the snapshot but is marked as a feature; AFI-002 is a valid post-horizon label."),
        _truth("STAGE_PROBABILITY_MISMATCH", "anomalous_forecast_inputs", "AFI-003", "Configured base probability for the snapshot stage was deliberately replaced."),
        _truth("DUPLICATE_OPPORTUNITY_COUNT", "anomalous_aggregation_inputs", "AGG-DUP-001", "Same snapshot/opportunity is present twice in one aggregation input."),
        _truth("CLOSE_DATE_BEFORE_CREATION", "opportunity_change_events", bad_opp["opportunity_id"], "Expected close change predates opportunity creation."),
        _truth("MIXED_CURRENCY_TOTAL", "anomalous_aggregation_inputs", "AGG-FX-001", "USD and EUR values are totalled without conversion."),
    ]
    return data


def detect_anomalies(data: dict[str, list[dict]]) -> list[dict]:
    """Return issue records in the same shape as ground_truth, without copying labels."""
    found = []
    snapshots = {r["forecast_snapshot_id"]: r for r in data.get("forecast_snapshots", [])}
    stage_at_snapshot = {(r["forecast_snapshot_id"], r["opportunity_id"]): r for r in data.get("snapshot_opportunities", [])}
    probabilities = {(r["stage_code"], r["scenario"]): r["probability"] for r in data.get("stage_probability_versions", [])}
    for row in data.get("anomalous_forecast_inputs", []):
        snapshot = snapshots[row["forecast_snapshot_id"]]
        if row["feature_role"] == "feature" and "outcome" in row["feature_name"] and row["source_event_at"] > snapshot["snapshot_at"]:
            found.append(_truth("FUTURE_OUTCOME_LEAKAGE", "anomalous_forecast_inputs", row["input_id"], "Feature source is later than snapshot cutoff."))
        if row["feature_name"] == "stage_probability":
            expected = probabilities[(stage_at_snapshot[(row["forecast_snapshot_id"], row["opportunity_id"])]["stage_at_snapshot"], "BASE")]
            if abs(float(expected) - float(row["stage_probability"])) > 1e-9:
                found.append(_truth("STAGE_PROBABILITY_MISMATCH", "anomalous_forecast_inputs", row["input_id"], "Input probability differs from effective configuration."))
    opportunity_created = {r["opportunity_id"]: r["created_at"].date() for r in data.get("opportunities", [])}
    for event in data.get("opportunity_change_events", []):
        if event["change_type"] == "EXPECTED_CLOSE_DATE" and event["new_value"].get("date", "9999-12-31") < opportunity_created[event["opportunity_id"]].isoformat():
            found.append(_truth("CLOSE_DATE_BEFORE_CREATION", "opportunity_change_events", event["opportunity_id"], "Expected close date predates creation."))
    groups = {}
    for row in data.get("anomalous_aggregation_inputs", []): groups.setdefault(row["aggregation_id"], []).append(row)
    for aggregation_id, rows in groups.items():
        keys = [(r["forecast_snapshot_id"], r["opportunity_id"]) for r in rows]
        if len(keys) != len(set(keys)):
            found.append(_truth("DUPLICATE_OPPORTUNITY_COUNT", "anomalous_aggregation_inputs", aggregation_id, "Aggregation input has duplicate opportunity."))
        if len({r["currency"] for r in rows}) > 1 and not all(r["converted_to_reporting"] for r in rows):
            found.append(_truth("MIXED_CURRENCY_TOTAL", "anomalous_aggregation_inputs", aggregation_id, "Mixed transaction currencies lack reporting conversion."))
    return found


def detection_metrics(found: list[dict], truth: list[dict]) -> dict[str, float | int]:
    key = lambda row: (row["issue_type"], row["affected_record_id"], row["detection_rule_id"])
    detected, expected = {key(row) for row in found}, {key(row) for row in truth}
    tp = len(detected & expected); fp = len(detected - expected); fn = len(expected - detected)
    return {"true_positives": tp, "false_positives": fp, "false_negatives": fn, "precision": tp / (tp + fp) if tp + fp else 0.0, "recall": tp / (tp + fn) if tp + fn else 0.0}
