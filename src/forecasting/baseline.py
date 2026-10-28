"""Transparent weighted-pipeline benchmark for point-in-time feature rows."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

MONEY = Decimal("0.01")
TERMINAL = {"CLOSED_WON", "CLOSED_LOST"}
VALID_GROUPS = {"quarter", "territory_id", "owner_rep_id", "stage_at_snapshot", "product_type"}


class ForecastInputError(ValueError):
    pass


@dataclass(frozen=True)
class BaselineConfig:
    """Timing probabilities are P(booking is recognized in horizon | eventual win).

    Stage probability is P(eventual win | stage at cutoff), so it appears exactly once.
    """
    timing_if_close_before_horizon: Decimal = Decimal("0.95")
    timing_if_close_in_horizon: Decimal = Decimal("0.80")
    timing_if_close_after_horizon: Decimal = Decimal("0.10")
    slippage_penalty_per_prior_change: Decimal = Decimal("0.10")
    minimum_timing_probability: Decimal = Decimal("0.05")
    expected_booking_fraction: Decimal = Decimal("1.00")
    exchange_rates: tuple[dict, ...] = ()


def _date(value) -> date:
    if isinstance(value, datetime): return value.date()
    return date.fromisoformat(str(value)[:10])


def _money(value) -> Decimal:
    try:
        amount = Decimal(str(value))
    except Exception as exc:
        raise ForecastInputError(f"Invalid monetary value: {value!r}") from exc
    if amount < 0: raise ForecastInputError("Forecast amount cannot be negative")
    return amount


def _reporting_amount(row: dict, config: BaselineConfig) -> Decimal:
    """Accept persisted reporting amount or convert a raw amount with an as-of rate."""
    reporting = row["reporting_currency"]
    if row.get("amount_reporting_currency") not in (None, ""):
        return _money(row["amount_reporting_currency"])
    amount = _money(row.get("amount_transaction_currency"))
    currency = row.get("transaction_currency")
    if currency == reporting: return amount
    cutoff = _date(row["feature_cutoff_at"])
    rates = [r for r in config.exchange_rates if r.get("from_currency") == currency and r.get("to_currency") == reporting and _date(r["rate_date"]) <= cutoff and Decimal(str(r.get("rate", 0))) > 0]
    if not rates:
        raise ForecastInputError(f"Missing valid as-of conversion rate for {currency}->{reporting}")
    return amount * Decimal(str(max(rates, key=lambda r: _date(r["rate_date"]))["rate"]))


def _timing_probability(row: dict, config: BaselineConfig) -> Decimal:
    close = _date(row["expected_close_date"]) if row.get("expected_close_date") else _date(row["label_horizon_end"])
    start, end = _date(row["label_horizon_start"]), _date(row["label_horizon_end"])
    base = config.timing_if_close_before_horizon if close < start else config.timing_if_close_in_horizon if close <= end else config.timing_if_close_after_horizon
    penalty = config.slippage_penalty_per_prior_change * int(row.get("prior_close_date_change_count", 0))
    return max(config.minimum_timing_probability, base - penalty)


def _quarter(day: date) -> str:
    return f"{day.year}Q{(day.month - 1) // 3 + 1}"


def _aggregate(contributions: list[dict], group_by: tuple[str, ...]) -> list[dict]:
    invalid = set(group_by) - VALID_GROUPS
    if invalid: raise ForecastInputError(f"Unsupported aggregation dimensions: {sorted(invalid)}")
    groups = defaultdict(lambda: {"open_pipeline_reporting": Decimal("0"), "weighted_expected_bookings_reporting": Decimal("0"), "closed_won_bookings_as_of_reporting": Decimal("0"), "forecast_bookings_future_horizon_reporting": Decimal("0"), "opportunity_count": 0})
    for row in contributions:
        key_values = {"quarter": _quarter(_date(row["label_horizon_start"])), **row}
        key = tuple(key_values[name] for name in group_by)
        output = groups[key]; output["opportunity_count"] += 1
        for field in ("open_pipeline_reporting", "weighted_expected_bookings_reporting", "closed_won_bookings_as_of_reporting", "forecast_bookings_future_horizon_reporting"):
            output[field] += Decimal(row[field])
    result = []
    for key, values in sorted(groups.items()):
        result.append({**dict(zip(group_by, key)), **{name: str(value.quantize(MONEY, ROUND_HALF_UP)) if isinstance(value, Decimal) else value for name, value in values.items()}})
    return result


def forecast_weighted_pipeline(feature_rows: list[dict], config: BaselineConfig = BaselineConfig(), group_by: tuple[str, ...] = ("quarter", "territory_id", "owner_rep_id", "stage_at_snapshot", "product_type")) -> dict:
    """Return deduplicated opportunity contributions and reconciled aggregate totals.

    For an open opportunity, ``future forecast = amount × stage_probability ×
    timing_probability × expected_booking_fraction``. Timing is conditional on an
    eventual win, preventing multiplication of the same win probability twice.
    Closed-won amounts recognized by cutoff are reported separately and contribute
    zero to the future horizon. Lost deals contribute zero everywhere.
    """
    seen = set(); contributions = []
    for row in feature_rows:
        key = (row.get("forecast_snapshot_id"), row.get("opportunity_id"))
        if key in seen: raise ForecastInputError(f"Duplicate opportunity contribution: {key}")
        seen.add(key)
        amount = _reporting_amount(row, config); stage = row["stage_at_snapshot"]
        base = {"forecast_snapshot_id": row["forecast_snapshot_id"], "opportunity_id": row["opportunity_id"], "label_horizon_start": row["label_horizon_start"], "reporting_currency": row["reporting_currency"], "territory_id": row.get("territory_id"), "owner_rep_id": row.get("owner_rep_id"), "stage_at_snapshot": stage, "product_type": row.get("product_type"), "open_pipeline_reporting": "0", "weighted_expected_bookings_reporting": "0", "closed_won_bookings_as_of_reporting": "0", "forecast_bookings_future_horizon_reporting": "0"}
        if stage == "CLOSED_WON":
            base["closed_won_bookings_as_of_reporting"] = str(_money(row.get("recognized_booking_reporting", amount)).quantize(MONEY))
            base["contribution_status"] = "ALREADY_RECOGNIZED"
        elif stage == "CLOSED_LOST":
            base["contribution_status"] = "LOST"
        else:
            stage_probability = Decimal(str(row["effective_stage_probability"]))
            if not Decimal("0") <= stage_probability <= Decimal("1"): raise ForecastInputError("Stage probability must be in [0, 1]")
            timing = _timing_probability(row, config)
            expected = amount * stage_probability * timing * config.expected_booking_fraction
            base.update({"open_pipeline_reporting": str(amount.quantize(MONEY)), "weighted_expected_bookings_reporting": str(expected.quantize(MONEY, ROUND_HALF_UP)), "forecast_bookings_future_horizon_reporting": str(expected.quantize(MONEY, ROUND_HALF_UP)), "stage_probability": str(stage_probability), "conditional_booking_in_horizon_probability": str(timing), "expected_booking_fraction": str(config.expected_booking_fraction), "contribution_status": "OPEN"})
        contributions.append(base)
    aggregates = _aggregate(contributions, group_by)
    # Exact reconciliation is evaluated in cents, before values become display strings.
    totals = {field: str(sum(Decimal(r[field]) for r in contributions).quantize(MONEY)) for field in ("open_pipeline_reporting", "weighted_expected_bookings_reporting", "closed_won_bookings_as_of_reporting", "forecast_bookings_future_horizon_reporting")}
    return {"method": "weighted-pipeline-v1", "formula": "open future forecast = amount_reporting × P(eventual win | stage) × P(recognized in horizon | eventual win, expected close date, slippage) × expected_booking_fraction", "contributions": contributions, "aggregates": aggregates, "totals": totals}
