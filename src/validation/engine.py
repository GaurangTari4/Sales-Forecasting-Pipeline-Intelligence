"""Dataset-level integrity checks. All functions are read-only."""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
from .contracts import Action, Severity, ValidationReport

ENUMS = {"territories": {"region": {"NA", "EMEA", "APAC"}}, "opportunities": {"product_type": {"SUBSCRIPTION", "SERVICES"}}, "stage_history": {"to_stage": {"PROSPECTING", "QUALIFICATION", "DISCOVERY", "PROPOSAL", "NEGOTIATION", "CLOSED_WON", "CLOSED_LOST"}}, "activities": {"activity_type": {"CALL", "EMAIL", "MEETING", "DEMO", "TASK"}, "outcome": {"COMPLETED", "NO_SHOW", "BOUNCED", "CANCELLED"}}}
PKS = {"territories": "territory_id", "sales_reps": "sales_rep_id", "accounts": "account_id", "opportunities": "opportunity_id", "stages": "stage_code", "stage_history": "stage_event_id", "activities": "activity_id", "quotas": "quota_id", "historical_bookings": "booking_id", "forecast_snapshots": "forecast_snapshot_id"}
REQUIRED = {"opportunities": ("opportunity_id", "account_id", "owner_rep_id", "created_at", "original_expected_close_date", "transaction_currency", "initial_amount"), "stage_history": ("stage_event_id", "opportunity_id", "to_stage", "occurred_at"), "forecast_snapshots": ("forecast_snapshot_id", "snapshot_at", "horizon_start", "horizon_end", "reporting_currency")}


def _text(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _date(value) -> date:
    return value if isinstance(value, date) and not isinstance(value, datetime) else date.fromisoformat(_text(value)[:10])


def _datetime(value) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(_text(value).replace("Z", "+00:00"))


def _json(value):
    return value if isinstance(value, dict) else json.loads(value)


def _issue(report, rule, entity, record, issue, explanation, severity=Severity.ERROR, action=Action.QUARANTINE):
    report.add(rule_id=rule, severity=severity, affected_entity=entity, affected_record_id=str(record), issue_type=issue, explanation=explanation, recommended_action=action)


def validate_dataset(data: dict[str, list[dict]]) -> ValidationReport:
    report = ValidationReport(records_checked=sum(len(rows) for rows in data.values()))
    _keys_required_enums(report, data); _foreign_keys(report, data); _dates_and_lifecycle(report, data)
    _effective_dates(report, data); _probabilities_and_snapshots(report, data); _bookings_and_money(report, data)
    _controlled_inputs(report, data); _ground_truth_separation(report, data)
    truth = {(r.get("issue_type"), r.get("affected_record_id")) for r in data.get("ground_truth", [])}
    report.known_anomalies_detected = sum((r.issue_type, r.affected_record_id) in truth for r in report.results)
    if not report.results:
        report.add(rule_id="VALIDATION.COMPLETED", severity=Severity.INFO, affected_entity="dataset", affected_record_id="all", issue_type="BASELINE_VALID", explanation="All applicable integrity checks passed.", recommended_action=Action.PASS)
    return report


def _keys_required_enums(report, data):
    for table, key in PKS.items():
        values = [row.get(key) for row in data.get(table, [])]
        for value, count in Counter(values).items():
            if value in (None, "") or count > 1: _issue(report, "KEY.PRIMARY_UNIQUENESS", table, value or "<null>", "PRIMARY_KEY_DUPLICATE_OR_NULL", f"{key} is null or occurs {count} times.")
    for table, fields in REQUIRED.items():
        for row in data.get(table, []):
            for field in fields:
                if row.get(field) in (None, ""): _issue(report, "FIELD.REQUIRED", table, row.get(PKS.get(table), "<unknown>"), "REQUIRED_FIELD_MISSING", f"{field} is required.")
    for table, columns in ENUMS.items():
        for row in data.get(table, []):
            for field, allowed in columns.items():
                if row.get(field) not in allowed: _issue(report, "VALUE.ALLOWED_ENUM", table, row.get(PKS.get(table), "<unknown>"), "INVALID_ENUM", f"{field}={row.get(field)!r} is not allowed.")


def _foreign_keys(report, data):
    sets = {table: {row[key] for row in data.get(table, [])} for table, key in PKS.items()}
    links = [("accounts", "territory_id", "territories"), ("opportunities", "account_id", "accounts"), ("opportunities", "owner_rep_id", "sales_reps"), ("stage_history", "opportunity_id", "opportunities"), ("activities", "opportunity_id", "opportunities"), ("activities", "sales_rep_id", "sales_reps"), ("quotas", "sales_rep_id", "sales_reps"), ("historical_bookings", "opportunity_id", "opportunities"), ("snapshot_opportunities", "forecast_snapshot_id", "forecast_snapshots"), ("snapshot_opportunities", "opportunity_id", "opportunities")]
    for table, field, parent in links:
        for row in data.get(table, []):
            if row.get(field) not in sets[parent]: _issue(report, "FK.INTEGRITY", table, row.get(PKS.get(table), row.get("opportunity_id", "<unknown>")), "FOREIGN_KEY_MISSING", f"{field} does not reference {parent}.")


def _dates_and_lifecycle(report, data):
    opportunities = {r["opportunity_id"]: r for r in data.get("opportunities", [])}
    histories = defaultdict(list)
    for event in data.get("stage_history", []):
        histories[event["opportunity_id"]].append(event)
        if event["opportunity_id"] in opportunities and _datetime(event["occurred_at"]) < _datetime(opportunities[event["opportunity_id"]]["created_at"]): _issue(report, "TIME.EVENT_AFTER_CREATION", "stage_history", event["stage_event_id"], "EVENT_BEFORE_CREATION", "Stage event predates its opportunity.")
    ranks = {"PROSPECTING": 1, "QUALIFICATION": 2, "DISCOVERY": 3, "PROPOSAL": 4, "NEGOTIATION": 5, "CLOSED_WON": 6, "CLOSED_LOST": 6}
    for opp_id, events in histories.items():
        events.sort(key=lambda r: int(r["event_sequence"]))
        if events and (events[0].get("from_stage") not in (None, "") or int(events[0]["event_sequence"]) != 1): _issue(report, "LIFECYCLE.INITIAL_STAGE", "stage_history", opp_id, "INVALID_INITIAL_TRANSITION", "First lifecycle event must start at sequence 1 with no prior stage.")
        for old, new in zip(events, events[1:]):
            if _datetime(new["occurred_at"]) < _datetime(old["occurred_at"]) or int(new["event_sequence"]) != int(old["event_sequence"]) + 1 or (old["to_stage"] not in {"CLOSED_LOST", "CLOSED_WON"} and ranks[new["to_stage"]] < ranks[old["to_stage"]]): _issue(report, "LIFECYCLE.VALID_TRANSITION", "stage_history", new["stage_event_id"], "INVALID_STAGE_TRANSITION", "Stage transition is nonchronological, nonsequential, or regressive.")
    for event in data.get("opportunity_change_events", []):
        if event.get("change_type") == "EXPECTED_CLOSE_DATE":
            close = _json(event["new_value"]).get("date")
            if close and _date(close) < _datetime(opportunities[event["opportunity_id"]]["created_at"]).date(): _issue(report, "OPPORTUNITY.EXPECTED_CLOSE_AFTER_CREATION", "opportunity_change_events", event["opportunity_id"], "CLOSE_DATE_BEFORE_CREATION", "Expected close date predates opportunity creation.")


def _effective_dates(report, data):
    assignments = defaultdict(list)
    for row in data.get("rep_territory_assignments", []): assignments[row["sales_rep_id"]].append(row)
    for rep, rows in assignments.items():
        rows.sort(key=lambda r: _date(r["effective_from"]))
        for first, second in zip(rows, rows[1:]):
            end = first.get("effective_to")
            if not end or _date(end) >= _date(second["effective_from"]): _issue(report, "EFFECTIVE_DATE.REP_TERRITORY_NON_OVERLAP", "rep_territory_assignments", rep, "OVERLAPPING_TERRITORY_ASSIGNMENT", "Rep territory effective periods overlap.")
    versions = defaultdict(list)
    for row in data.get("stage_probability_versions", []): versions[(row["stage_code"], row["scenario"])].append(row)
    for key, rows in versions.items():
        for first, second in zip(sorted(rows, key=lambda r: _date(r["effective_from"])), sorted(rows, key=lambda r: _date(r["effective_from"]))[1:]):
            if not first.get("effective_to") or _date(first["effective_to"]) >= _date(second["effective_from"]): _issue(report, "EFFECTIVE_DATE.STAGE_PROBABILITY_NON_OVERLAP", "stage_probability_versions", ":".join(key), "OVERLAPPING_STAGE_PROBABILITY", "Stage probability versions overlap.")


def _probabilities_and_snapshots(report, data):
    snapshots = {r["forecast_snapshot_id"]: r for r in data.get("forecast_snapshots", [])}; opps = {r["opportunity_id"]: r for r in data.get("opportunities", [])}
    stage_asof = {(r["forecast_snapshot_id"], r["opportunity_id"]): r for r in data.get("snapshot_opportunities", [])}
    for row in data.get("snapshot_opportunities", []):
        snapshot = snapshots.get(row["forecast_snapshot_id"]); opp = opps.get(row["opportunity_id"])
        if snapshot and opp and _datetime(opp["created_at"]) > _datetime(snapshot["snapshot_at"]): _issue(report, "SNAPSHOT.TEMPORAL_INTEGRITY", "snapshot_opportunities", row["opportunity_id"], "OPPORTUNITY_AFTER_SNAPSHOT", "Snapshot contains an opportunity not yet created.")
    for row in data.get("anomalous_forecast_inputs", []):
        snapshot = snapshots[row["forecast_snapshot_id"]]
        if row["feature_role"] == "feature" and "outcome" in row["feature_name"] and _datetime(row["source_event_at"]) > _datetime(snapshot["snapshot_at"]): _issue(report, "LEAKAGE.FEATURE_AS_OF", "anomalous_forecast_inputs", row["input_id"], "FUTURE_OUTCOME_LEAKAGE", "Feature event occurs after snapshot cutoff.")
        if row["feature_name"] == "stage_probability":
            stage = stage_asof[(row["forecast_snapshot_id"], row["opportunity_id"])]["stage_at_snapshot"]
            snapshot_day = _datetime(snapshot["snapshot_at"]).date()
            effective = [version for version in data.get("stage_probability_versions", [])
                         if version["stage_code"] == stage and version["scenario"] == "BASE"
                         and _date(version["effective_from"]) <= snapshot_day
                         and (not version.get("effective_to") or _date(version["effective_to"]) >= snapshot_day)]
            if len(effective) != 1:
                _issue(report, "FORECAST.STAGE_PROBABILITY_EFFECTIVE_DATE", "stage_probability_versions", stage, "EFFECTIVE_STAGE_PROBABILITY_MISSING_OR_AMBIGUOUS", f"Expected exactly one BASE probability for {stage} at {snapshot_day}.")
            elif Decimal(str(row["stage_probability"])) != Decimal(str(effective[0]["probability"])):
                _issue(report, "FORECAST.STAGE_PROBABILITY_EFFECTIVE_DATE", "anomalous_forecast_inputs", row["input_id"], "STAGE_PROBABILITY_MISMATCH", "Forecast probability differs from the configuration effective at the snapshot date.")


def _bookings_and_money(report, data):
    opps = {r["opportunity_id"]: r for r in data.get("opportunities", [])}; terminal = {}
    for event in data.get("stage_history", []): terminal[event["opportunity_id"]] = event["to_stage"]
    sums = defaultdict(Decimal)
    for booking in data.get("historical_bookings", []):
        if terminal.get(booking["opportunity_id"]) != "CLOSED_WON": _issue(report, "BOOKING.CLOSED_WON_REQUIRED", "historical_bookings", booking["booking_id"], "BOOKING_WITHOUT_WON_OUTCOME", "Booking lacks a closed-won outcome.")
        sums[booking["opportunity_id"]] += Decimal(str(booking["booking_amount"]))
    for opp_id, amount in sums.items():
        if amount != Decimal(str(opps[opp_id]["initial_amount"])): _issue(report, "MONEY.BOOKING_RECONCILIATION", "historical_bookings", opp_id, "BOOKING_AMOUNT_MISMATCH", "Bookings do not reconcile to opportunity amount.")
    groups = defaultdict(list)
    for row in data.get("anomalous_aggregation_inputs", []): groups[row["aggregation_id"]].append(row)
    for group, rows in groups.items():
        pairs = [(r["forecast_snapshot_id"], r["opportunity_id"]) for r in rows]
        if len(pairs) != len(set(pairs)): _issue(report, "AGGREGATION.UNIQUE_SNAPSHOT_OPPORTUNITY", "anomalous_aggregation_inputs", group, "DUPLICATE_OPPORTUNITY_COUNT", "Opportunity occurs more than once in aggregation input.")
        if len({r["currency"] for r in rows}) > 1 and not all(str(r["converted_to_reporting"]).lower() == "true" for r in rows): _issue(report, "AGGREGATION.COMMON_REPORTING_CURRENCY", "anomalous_aggregation_inputs", group, "MIXED_CURRENCY_TOTAL", "Multiple currencies are totalled without conversion.")


def _controlled_inputs(report, data):
    # Decimal validation makes malformed money a quarantinable source-quality failure.
    for table, field in (("opportunities", "initial_amount"), ("historical_bookings", "booking_amount"), ("snapshot_opportunities", "amount_transaction_currency")):
        for row in data.get(table, []):
            try:
                if Decimal(str(row[field])) < 0: raise InvalidOperation
            except (InvalidOperation, KeyError): _issue(report, "MONEY.NON_NEGATIVE_DECIMAL", table, row.get(PKS.get(table), row.get("opportunity_id", "<unknown>")), "INVALID_MONETARY_VALUE", f"{field} is invalid or negative.")


def _ground_truth_separation(report, data):
    prohibited = {"ground_truth", "ground_truth_outcomes", "ground_truth_anomalies"}
    # Feature projection has a fixed allowlist; report only if an explicit dataset claims otherwise.
    for table in prohibited:
        for row in data.get("model_feature_matrix", []):
            if any(key in row for key in {"issue_id", "issue_type", "final_outcome", "latent_quality"}): _issue(report, "LEAKAGE.GROUND_TRUTH_SEPARATION", "model_feature_matrix", row.get("opportunity_id", "<unknown>"), "GROUND_TRUTH_IN_FEATURES", "Protected ground-truth field entered feature matrix.")
