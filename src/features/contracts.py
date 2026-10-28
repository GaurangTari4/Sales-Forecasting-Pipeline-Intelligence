"""Stable contracts for point-in-time feature datasets."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

FEATURE_SCHEMA_VERSION = "pit-sales-features-v1"

# The fields deliberately exclude outcomes, bookings, and all ground-truth exports.
FEATURE_COLUMNS = (
    "feature_schema_version", "forecast_snapshot_id", "feature_cutoff_at", "label_horizon_start",
    "label_horizon_end", "opportunity_id", "owner_rep_id", "amount_reporting_currency", "reporting_currency",
    "stage_at_snapshot", "effective_stage_probability", "expected_close_date", "opportunity_age_days",
    "days_until_expected_close", "current_stage_duration_days", "calls_30d", "emails_30d",
    "meetings_30d", "demos_30d", "calls_90d", "emails_90d", "meetings_90d", "demos_90d",
    "days_since_last_qualifying_activity", "historical_conversion_rate", "rep_historical_win_rate",
    "rep_historical_bookings_reporting", "territory_historical_win_rate",
    "territory_historical_bookings_reporting", "product_type", "account_segment", "account_industry",
    "territory_id", "territory_region", "rep_role", "prior_close_date_change_count",
    "observed_slippage_days",
)


@dataclass(frozen=True)
class FeatureConfig:
    """Feature cutoff is snapshot_at; labels are strictly after that cutoff."""
    scenario: str = "BASE"
    activity_windows: tuple[int, ...] = (30, 90)
    label_horizon_days: int | None = None
    include_closed_opportunities: bool = False

    def horizon(self, snapshot: dict, cutoff):
        start = _date(snapshot.get("horizon_start"))
        end = _date(snapshot.get("horizon_end"))
        if self.label_horizon_days is not None:
            end = start + timedelta(days=self.label_horizon_days - 1)
        return start, end


def _date(value):
    from datetime import date, datetime
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])
