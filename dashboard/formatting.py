from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def money(value, currency: str = "USD") -> str:
    """Format API monetary values without silently treating missing values as zero."""
    if value is None or value == "": return "Not available"
    try: amount = Decimal(str(value))
    except (InvalidOperation, ValueError): return "Not available"
    symbols = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}
    return f"{symbols.get(currency, currency + ' ')}{amount:,.2f}"


def percent(value) -> str:
    if value is None or value == "": return "Not available"
    try: return f"{float(value):.1%}"
    except (TypeError, ValueError): return "Not available"


def scenario_percent_change(value) -> str:
    """A zero base has no meaningful relative change, even when adjusted is nonzero."""
    return "N/A" if value is None else percent(value)


def display_date(value) -> str:
    """Return a compact, business-readable date without inventing missing values."""
    if value is None or value == "":
        return "Not available"
    try:
        return pd_timestamp(value).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return str(value)[:10]


def display_datetime(value) -> str:
    """Return a readable timestamp while retaining the API value in raw details."""
    if value is None or value == "":
        return "Not available"
    try:
        return pd_timestamp(value).strftime("%d %b %Y, %H:%M UTC")
    except (TypeError, ValueError):
        return str(value)


def pd_timestamp(value):
    """Small dependency-free parser for the ISO-like values returned by the API."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def humanize_identifier(value) -> str:
    """Present enum-like API values as business labels without changing the payload."""
    if value is None or value == "":
        return "Not available"
    return str(value).replace("_", " ").replace("-", " ").title()


def signed_number(value, suffix: str = "") -> str:
    if value is None or value == "":
        return "Not available"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Not available"
    return f"{number:+.2f}{suffix}"


def opportunity_display_row(row: dict, currency: str = "USD") -> dict:
    """Business-first rendering while retaining the original values in the API payload."""
    rendered = dict(row)
    for field in ("amount_reporting_currency", "expected_booking_reporting", "P10_booking_reporting", "P50_booking_reporting", "P90_booking_reporting"):
        rendered[field] = money(row.get(field), currency)
    rendered["effective_stage_probability"] = percent(row.get("effective_stage_probability"))
    for field in ("expected_close_date", "feature_cutoff_at"):
        if row.get(field): rendered[field] = str(row[field])[:10]
    return rendered


def filter_opportunities(rows, quarters=(), territories=(), reps=(), stages=(), products=()):
    """Pure display filtering; all forecast calculations remain in the API."""
    choices = {"quarter": set(quarters), "territory_id": set(territories), "owner_rep_id": set(reps), "stage_at_snapshot": set(stages), "product_type": set(products)}
    return [row for row in rows if all(not allowed or str(row.get(field)) in allowed for field, allowed in choices.items())]


def filter_exceptions(rows, types=(), severities=(), reps=(), territories=(), forecast_runs=()):
    choices = {"exception_type": set(types), "severity": set(severities), "owner_rep_id": set(reps), "territory_id": set(territories), "forecast_run_id": set(forecast_runs)}
    return [row for row in rows if all(not allowed or str(row.get(field)) in allowed for field, allowed in choices.items())]


def exception_evidence_summary(exception: dict, currency: str = "USD") -> str:
    evidence, kind = exception.get("evidence", {}), exception.get("exception_type")
    if kind == "FORECAST_GAP_TO_QUOTA":
        return f"Quota {money(evidence.get('quota'), currency)}; forecast {money(evidence.get('forecast'), currency)}; gap {money(evidence.get('gap'), currency)}; attainment {percent(evidence.get('attainment'))}."
    if kind == "STALE_OPPORTUNITY": return f"{evidence.get('opportunity_age_days')} days old in {evidence.get('stage', 'its current')} stage."
    if kind == "CLOSE_DATE_AT_RISK": return f"Expected close is in {evidence.get('days_until_expected_close')} days with {evidence.get('prior_close_date_changes', 0)} prior close-date changes."
    if kind == "STAGE_DURATION_ANOMALY": return f"{evidence.get('current_stage_duration_days')} days in {evidence.get('stage', 'the current')} stage."
    if kind == "INACTIVE_REP_MATERIAL_PIPELINE": return f"Expected open-pipeline bookings: {money(evidence.get('open_pipeline_expected_booking'), currency)}."
    if kind == "FORECAST_CONCENTRATION": return f"Top three deals represent {percent(evidence.get('top_three_share'))} of {money(evidence.get('total_forecast'), currency)} expected forecast."
    if kind == "MATERIAL_DATA_QUALITY": return f"Validation rule {evidence.get('rule_id', 'not supplied')} reported {evidence.get('issue_type', 'a material issue')}."
    return "No display-specific evidence summary is available; review technical details."


def scenario_comparison_rows(base: dict, adjusted: dict):
    metrics = (
        ("Expected revenue", base.get("totals", {}).get("expected_booking_reporting"), adjusted.get("totals", {}).get("expected_booking_reporting")),
        ("P10", base.get("uncertainty", {}).get("p10"), adjusted.get("uncertainty", {}).get("p10")),
        ("P50", base.get("uncertainty", {}).get("p50"), adjusted.get("uncertainty", {}).get("p50")),
        ("P90", base.get("uncertainty", {}).get("p90"), adjusted.get("uncertainty", {}).get("p90")),
    )
    rows = []
    for label, baseline, scenario in metrics:
        baseline_value, scenario_value = float(baseline), float(scenario)
        rows.append({"Metric": label, "Base": baseline_value, "Adjusted": scenario_value, "Change %": round(scenario_value / baseline_value - 1, 12) if baseline_value else None})
    return rows
