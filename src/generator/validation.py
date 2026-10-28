from collections import Counter, defaultdict
from datetime import datetime


class ValidationError(ValueError):
    pass


def validate(dataset: dict[str, list[dict]]) -> None:
    for table, key in (("territories", "territory_id"), ("sales_reps", "sales_rep_id"), ("accounts", "account_id"), ("opportunities", "opportunity_id"), ("stage_history", "stage_event_id"), ("activities", "activity_id"), ("quotas", "quota_id"), ("historical_bookings", "booking_id"), ("forecast_snapshots", "forecast_snapshot_id")):
        values = [row[key] for row in dataset[table]]
        if len(values) != len(set(values)): raise ValidationError(f"duplicate {key} in {table}")
    ids = {name: {r[key] for r in dataset[name]} for name, key in (("territories","territory_id"),("sales_reps","sales_rep_id"),("accounts","account_id"),("opportunities","opportunity_id"),("forecast_snapshots","forecast_snapshot_id"))}
    if any(r["territory_id"] not in ids["territories"] for r in dataset["accounts"]): raise ValidationError("account territory FK failure")
    if any(r["account_id"] not in ids["accounts"] or r["owner_rep_id"] not in ids["sales_reps"] for r in dataset["opportunities"]): raise ValidationError("opportunity FK failure")
    opportunities = {r["opportunity_id"]: r for r in dataset["opportunities"]}
    histories = defaultdict(list)
    for row in dataset["stage_history"]:
        if row["opportunity_id"] not in opportunities: raise ValidationError("stage history FK failure")
        histories[row["opportunity_id"]].append(row)
    terminal = {}
    for oid, rows in histories.items():
        rows.sort(key=lambda r: r["event_sequence"])
        if rows[0]["from_stage"] is not None or rows[0]["event_sequence"] != 1: raise ValidationError(f"bad initial stage: {oid}")
        if [r["event_sequence"] for r in rows] != list(range(1, len(rows)+1)): raise ValidationError(f"stage sequence gap: {oid}")
        if any(rows[i]["occurred_at"] > rows[i+1]["occurred_at"] for i in range(len(rows)-1)): raise ValidationError(f"nonchronological stage history: {oid}")
        if rows[-1]["to_stage"] in {"CLOSED_WON", "CLOSED_LOST"}: terminal[oid] = rows[-1]["to_stage"]
    for booking in dataset["historical_bookings"]:
        if terminal.get(booking["opportunity_id"]) != "CLOSED_WON": raise ValidationError("booking without closed-won event")
    snapshot_keys = [(r["forecast_snapshot_id"], r["opportunity_id"]) for r in dataset["snapshot_opportunities"]]
    if len(snapshot_keys) != len(set(snapshot_keys)): raise ValidationError("duplicate snapshot opportunity")
    if any(r["forecast_snapshot_id"] not in ids["forecast_snapshots"] or r["opportunity_id"] not in ids["opportunities"] for r in dataset["snapshot_opportunities"]): raise ValidationError("snapshot FK failure")
    if dataset["ground_truth_anomalies"]: raise ValidationError("baseline must not contain injected anomalies")
