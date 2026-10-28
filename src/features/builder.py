"""Append-only, as-of feature construction. No future row is read into a feature."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from .contracts import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, FeatureConfig

TERMINAL = {"CLOSED_WON", "CLOSED_LOST"}


def _dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _date(value) -> date:
    return _dt(value).date() if "T" in str(value) or isinstance(value, datetime) else date.fromisoformat(str(value)[:10])


def _as_of(rows, key: str, cutoff: datetime):
    """Return only rows known at cutoff; equal times use stable input order."""
    return [row for row in rows if _dt(row[key]) <= cutoff]


def _effective(rows, cutoff_day: date, start="effective_from", end="effective_to"):
    return [r for r in rows if _date(r[start]) <= cutoff_day and (not r.get(end) or _date(r[end]) >= cutoff_day)]


def _reporting_amount(amount, currency, reporting_currency, rates, cutoff: datetime) -> Decimal:
    amount = Decimal(str(amount))
    if currency == reporting_currency:
        return amount
    valid = [r for r in rates if r["from_currency"] == currency and r["to_currency"] == reporting_currency and _date(r["rate_date"]) <= cutoff.date()]
    if not valid:
        raise ValueError(f"No {currency}->{reporting_currency} rate known at {cutoff.date()}")
    return amount * Decimal(str(max(valid, key=lambda r: _date(r["rate_date"]))["rate"]))


def _close_state(events):
    return events[-1]["to_stage"] if events else None


def _historical_metrics(opportunities, histories, assignments, accounts, bookings, rates, reporting_currency, cutoff):
    """Performance uses only terminal events and recognized bookings known by cutoff."""
    terminal_rows = []
    for opp in opportunities.values():
        rows = sorted(_as_of(histories.get(opp["opportunity_id"], []), "occurred_at", cutoff), key=lambda r: ( _dt(r["occurred_at"]), int(r["event_sequence"])))
        if rows and rows[-1]["to_stage"] in TERMINAL:
            terminal_rows.append((opp, rows[-1]))
    total = len(terminal_rows)
    global_rate = sum(event["to_stage"] == "CLOSED_WON" for _, event in terminal_rows) / total if total else 0.0
    reps = defaultdict(lambda: [0, 0, Decimal("0")])
    territories = defaultdict(lambda: [0, 0, Decimal("0")])
    account_map = accounts
    for opp, event in terminal_rows:
        rep = opp["owner_rep_id"]
        territory = next((x["territory_id"] for x in _effective(assignments.get(rep, []), _dt(event["occurred_at"]).date())), account_map[opp["account_id"]]["territory_id"])
        for bucket, name in ((reps, rep), (territories, territory)):
            bucket[name][0] += 1
            bucket[name][1] += event["to_stage"] == "CLOSED_WON"
    for booking in _as_of(bookings, "recognized_at", cutoff):
        opp = opportunities[booking["opportunity_id"]]
        rep = opp["owner_rep_id"]
        territory = next((x["territory_id"] for x in _effective(assignments.get(rep, []), _dt(booking["recognized_at"]).date())), account_map[opp["account_id"]]["territory_id"])
        converted = _reporting_amount(booking["booking_amount"], booking["currency"], reporting_currency, rates, cutoff)
        reps[rep][2] += converted; territories[territory][2] += converted
    return global_rate, reps, territories


def build_feature_dataset(dataset: dict[str, list[dict]], config: FeatureConfig = FeatureConfig()) -> list[dict]:
    """Create one feature row per eligible opportunity/snapshot, excluding targets."""
    forbidden = {"ground_truth", "ground_truth_outcomes", "ground_truth_anomalies"}
    # Their presence is allowed in the input package but none may flow through the projection below.
    opportunities = {r["opportunity_id"]: r for r in dataset.get("opportunities", [])}
    accounts = {r["account_id"]: r for r in dataset.get("accounts", [])}
    reps = {r["sales_rep_id"]: r for r in dataset.get("sales_reps", [])}
    territories = {r["territory_id"]: r for r in dataset.get("territories", [])}
    histories = defaultdict(list); activities = defaultdict(list); changes = defaultdict(list); assignments = defaultdict(list)
    for r in dataset.get("stage_history", []): histories[r["opportunity_id"]].append(r)
    for r in dataset.get("activities", []): activities[r["opportunity_id"]].append(r)
    for r in dataset.get("opportunity_change_events", []): changes[r["opportunity_id"]].append(r)
    for r in dataset.get("rep_territory_assignments", []): assignments[r["sales_rep_id"]].append(r)
    rows = []
    for snapshot in sorted(dataset.get("forecast_snapshots", []), key=lambda r: _dt(r["snapshot_at"])):
        cutoff = _dt(snapshot["snapshot_at"]); cutoff_day = cutoff.date(); reporting = snapshot["reporting_currency"]
        global_rate, rep_metrics, territory_metrics = _historical_metrics(opportunities, histories, assignments, accounts, dataset.get("historical_bookings", []), dataset.get("exchange_rates", []), reporting, cutoff)
        for opp in opportunities.values():
            if _dt(opp["created_at"]) > cutoff:
                continue
            events = sorted(_as_of(histories[opp["opportunity_id"]], "occurred_at", cutoff), key=lambda r: (_dt(r["occurred_at"]), int(r["event_sequence"])))
            if not events:
                continue
            stage = _close_state(events)
            if stage in TERMINAL and not config.include_closed_opportunities:
                continue
            effective_probs = _effective([r for r in dataset.get("stage_probability_versions", []) if r["stage_code"] == stage and r["scenario"] == config.scenario], cutoff_day)
            if len(effective_probs) != 1:
                raise ValueError(f"Expected exactly one effective probability for {stage}/{config.scenario} at {cutoff_day}")
            known_changes = sorted(_as_of(changes[opp["opportunity_id"]], "occurred_at", cutoff), key=lambda r: _dt(r["occurred_at"]))
            close = _date(opp["original_expected_close_date"])
            amount, currency = opp["initial_amount"], opp["transaction_currency"]
            for change in known_changes:
                value = change.get("new_value", {})
                if isinstance(value, str):
                    import json; value = json.loads(value)
                if change["change_type"] == "EXPECTED_CLOSE_DATE": close = _date(value["date"])
                elif change["change_type"] == "AMOUNT": amount = value["amount"]
                elif change["change_type"] == "CURRENCY": currency = value["currency"]
            rep_id = opp["owner_rep_id"]
            rep_assignment = _effective(assignments[rep_id], cutoff_day)
            territory_id = rep_assignment[0]["territory_id"] if len(rep_assignment) == 1 else accounts[opp["account_id"]]["territory_id"]
            account, territory = accounts[opp["account_id"]], territories[territory_id]
            known_activities = [a for a in _as_of(activities[opp["opportunity_id"]], "occurred_at", cutoff) if a.get("outcome") == "COMPLETED"]
            feature = {"feature_schema_version": FEATURE_SCHEMA_VERSION, "forecast_snapshot_id": snapshot["forecast_snapshot_id"], "feature_cutoff_at": cutoff.isoformat(), "label_horizon_start": config.horizon(snapshot, cutoff)[0].isoformat(), "label_horizon_end": config.horizon(snapshot, cutoff)[1].isoformat(), "opportunity_id": opp["opportunity_id"], "owner_rep_id": rep_id, "amount_reporting_currency": str(_reporting_amount(amount, currency, reporting, dataset.get("exchange_rates", []), cutoff).quantize(Decimal(".01"))), "reporting_currency": reporting, "stage_at_snapshot": stage, "effective_stage_probability": str(effective_probs[0]["probability"]), "expected_close_date": close.isoformat(), "opportunity_age_days": (cutoff_day - _dt(opp["created_at"]).date()).days, "days_until_expected_close": (close - cutoff_day).days, "current_stage_duration_days": (cutoff_day - _dt(events[-1]["occurred_at"]).date()).days, "historical_conversion_rate": global_rate, "rep_historical_win_rate": rep_metrics[rep_id][1] / rep_metrics[rep_id][0] if rep_metrics[rep_id][0] else 0.0, "rep_historical_bookings_reporting": str(rep_metrics[rep_id][2]), "territory_historical_win_rate": territory_metrics[territory_id][1] / territory_metrics[territory_id][0] if territory_metrics[territory_id][0] else 0.0, "territory_historical_bookings_reporting": str(territory_metrics[territory_id][2]), "product_type": opp["product_type"], "account_segment": "ENTERPRISE" if int(account["employee_count"]) >= 5000 else "MID_MARKET" if int(account["employee_count"]) >= 500 else "SMB", "account_industry": account["industry"], "territory_id": territory_id, "territory_region": territory["region"], "rep_role": reps[rep_id]["role"], "prior_close_date_change_count": sum(c["change_type"] == "EXPECTED_CLOSE_DATE" for c in known_changes), "observed_slippage_days": (close - _date(opp["original_expected_close_date"])).days}
            for days in config.activity_windows:
                floor = cutoff_day.fromordinal(cutoff_day.toordinal() - days)
                window = [a for a in known_activities if _dt(a["occurred_at"]).date() > floor]
                for kind, name in (("CALL", "calls"), ("EMAIL", "emails"), ("MEETING", "meetings"), ("DEMO", "demos")):
                    feature[f"{name}_{days}d"] = sum(a["activity_type"] == kind for a in window)
            feature["days_since_last_qualifying_activity"] = (cutoff_day - max((_dt(a["occurred_at"]).date() for a in known_activities), default=_dt(opp["created_at"]).date())).days
            rows.append({key: feature[key] for key in FEATURE_COLUMNS})
    return rows


def build_labels(dataset: dict[str, list[dict]], feature_rows: list[dict]) -> list[dict]:
    """Build targets separately; booking events are used only inside each row's label horizon."""
    snapshots = {r["forecast_snapshot_id"]: r for r in dataset.get("forecast_snapshots", [])}
    opportunities = {r["opportunity_id"]: r for r in dataset.get("opportunities", [])}
    labels = []
    for row in feature_rows:
        cutoff = _dt(row["feature_cutoff_at"]); start, end = _date(row["label_horizon_start"]), _date(row["label_horizon_end"])
        if start <= cutoff.date():
            raise ValueError("Label horizon must begin strictly after the feature cutoff")
        total = Decimal("0")
        for booking in dataset.get("historical_bookings", []):
            if booking["opportunity_id"] == row["opportunity_id"] and start <= _dt(booking["recognized_at"]).date() <= end:
                total += _reporting_amount(booking["booking_amount"], booking["currency"], row["reporting_currency"], dataset.get("exchange_rates", []), cutoff)
        labels.append({"feature_schema_version": FEATURE_SCHEMA_VERSION, "forecast_snapshot_id": row["forecast_snapshot_id"], "opportunity_id": row["opportunity_id"], "label_horizon_start": start.isoformat(), "label_horizon_end": end.isoformat(), "realized_booking_reporting": str(total.quantize(Decimal(".01"))), "booked_in_horizon": total > 0})
    return labels
