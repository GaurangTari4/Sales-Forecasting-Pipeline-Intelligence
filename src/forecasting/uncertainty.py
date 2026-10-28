"""Scenario-aware, reproducible booking simulation built on conversion probabilities."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal
import math
import random


@dataclass(frozen=True)
class ScenarioConfig:
    """Explicit, defensible shifts to conversion/timing assumptions (not output multipliers)."""
    name: str
    conversion_log_odds_shift: float = 0.0
    slippage_days_shift: int = 0
    booking_fraction: float = 1.0
    activity_effectiveness_log_odds: float = 0.0


SCENARIOS = {
    "CONSERVATIVE": ScenarioConfig("CONSERVATIVE", conversion_log_odds_shift=-.35, slippage_days_shift=14, booking_fraction=.95, activity_effectiveness_log_odds=-.05),
    "BASE": ScenarioConfig("BASE"),
    "OPTIMISTIC": ScenarioConfig("OPTIMISTIC", conversion_log_odds_shift=.25, slippage_days_shift=-7, booking_fraction=1.0, activity_effectiveness_log_odds=.05),
}


class SimulationInputError(ValueError): pass


def _date(value): return date.fromisoformat(str(value)[:10])
def _sigmoid(x): return 1 / (1 + math.exp(-max(-30, min(30, x))))
def _logit(p):
    p = max(1e-6, min(1-1e-6, float(p))); return math.log(p/(1-p))
def _quarter(day): return f"{day.year}Q{(day.month-1)//3+1}"


def booking_horizon_probability(row: dict, conversion_probability: float, scenario: ScenarioConfig) -> float:
    """Joint P(Closed Won and booked in horizon), adjusted once in log-odds space.

    The conversion model already predicts this joint event. Slippage/activity scenario
    shifts alter its odds; no stage or timing probability is multiplied a second time.
    """
    if not 0 <= float(conversion_probability) <= 1: raise SimulationInputError("Conversion probability must be in [0, 1]")
    activity = min(10, int(row.get("calls_30d", 0)) + int(row.get("meetings_30d", 0)) + int(row.get("demos_30d", 0)))
    shift = scenario.conversion_log_odds_shift + scenario.activity_effectiveness_log_odds * activity
    # More expected slippage weakens probability of landing inside the fixed horizon.
    shift -= max(0, scenario.slippage_days_shift) / 60
    return _sigmoid(_logit(conversion_probability) + shift)


def sample_booking_date(row: dict, rng: random.Random, scenario: ScenarioConfig) -> date:
    """Conditional booking date is always in-horizon after joint booking event sampled."""
    start, end = _date(row["label_horizon_start"]), _date(row["label_horizon_end"])
    expected = _date(row.get("expected_close_date", row["label_horizon_end"])) + timedelta(days=scenario.slippage_days_shift)
    # Gamma is positive, skewed slippage; history shifts its expected delay.
    delay = int(rng.gammavariate(2, 4 + 2 * int(row.get("prior_close_date_change_count", 0))))
    return min(end, max(start, expected + timedelta(days=delay)))


def opportunity_scenario_contributions(feature_rows, predictions, scenario: ScenarioConfig = SCENARIOS["BASE"]):
    """Expected contribution uses joint horizon probability exactly once."""
    probs = {(p["forecast_snapshot_id"], p["opportunity_id"]): p["conversion_probability"] for p in predictions}
    seen = set(); result = []
    for row in feature_rows:
        key = (row["forecast_snapshot_id"], row["opportunity_id"])
        if key in seen: raise SimulationInputError(f"Duplicate opportunity contribution {key}")
        seen.add(key)
        if key not in probs: raise SimulationInputError(f"Missing conversion prediction {key}")
        probability = booking_horizon_probability(row, probs[key], scenario)
        amount = float(row["amount_reporting_currency"]); expected = amount * probability * scenario.booking_fraction
        result.append({"forecast_snapshot_id": key[0], "opportunity_id": key[1], "quarter": _quarter(_date(row["label_horizon_start"])), "territory_id": row.get("territory_id"), "owner_rep_id": row.get("owner_rep_id"), "product_type": row.get("product_type"), "reporting_currency": row["reporting_currency"], "joint_booking_within_horizon_probability": probability, "expected_booking_reporting": expected, "scenario": scenario.name})
    return result


def simulate_bookings(feature_rows, predictions, scenario: ScenarioConfig = SCENARIOS["BASE"], simulations: int = 1000, seed: int = 20261022, group_by=("quarter", "territory_id", "owner_rep_id", "product_type")):
    """Sample each joint deal+timing outcome once per simulation and return P10/P50/P90."""
    if simulations <= 0: raise SimulationInputError("simulations must be positive")
    contributions = opportunity_scenario_contributions(feature_rows, predictions, scenario)
    row_by_key = {(r["forecast_snapshot_id"], r["opportunity_id"]): r for r in feature_rows}
    rng = random.Random(seed); values = defaultdict(list); opportunity_samples = defaultdict(list); portfolio_values = []
    for _ in range(simulations):
        totals = defaultdict(float); portfolio_total = 0.0
        for c in contributions:
            booked = rng.random() < c["joint_booking_within_horizon_probability"]
            realized = c["expected_booking_reporting"] / max(c["joint_booking_within_horizon_probability"], 1e-12) if booked else 0.0
            # booking date simulation is conditional on booked; it does not add another probability.
            if booked: sample_booking_date(row_by_key[(c["forecast_snapshot_id"], c["opportunity_id"])], rng, scenario)
            opportunity_samples[(c["forecast_snapshot_id"], c["opportunity_id"])].append(realized)
            key = tuple(c[name] for name in group_by); totals[key] += realized; portfolio_total += realized
        for key in {tuple(c[name] for name in group_by) for c in contributions}: values[key].append(totals[key])
        portfolio_values.append(portfolio_total)
    percentile = lambda xs, q: sorted(xs)[round((len(xs)-1)*q)]
    aggregates = [{**dict(zip(group_by, key)), "scenario": scenario.name, "P10_booking_reporting": percentile(xs,.10), "P50_booking_reporting": percentile(xs,.50), "P90_booking_reporting": percentile(xs,.90), "mean_booking_reporting": sum(xs)/len(xs)} for key,xs in sorted(values.items())]
    for c in contributions:
        xs = opportunity_samples[(c["forecast_snapshot_id"], c["opportunity_id"])]
        c.update({"P10_booking_reporting": percentile(xs,.10), "P50_booking_reporting": percentile(xs,.50), "P90_booking_reporting": percentile(xs,.90), "mean_simulated_booking_reporting": sum(xs)/len(xs)})
    portfolio = {"P10_booking_reporting": percentile(portfolio_values,.10), "P50_booking_reporting": percentile(portfolio_values,.50), "P90_booking_reporting": percentile(portfolio_values,.90), "mean_booking_reporting": sum(portfolio_values)/len(portfolio_values)}
    return {"scenario": asdict(scenario), "seed": seed, "simulations": simulations, "contributions": contributions, "aggregates": aggregates, "portfolio": portfolio, "portfolio_draws": portfolio_values}


def evaluate_intervals(simulation_result, realized_labels):
    """Chronological-holdout interval coverage/width at opportunity level."""
    actual = {(r["forecast_snapshot_id"], r["opportunity_id"]): float(r.get("realized_booking_reporting", 0)) for r in realized_labels}
    evaluated = [r for r in simulation_result["contributions"] if (r["forecast_snapshot_id"], r["opportunity_id"]) in actual]
    if not evaluated: raise SimulationInputError("No labels align with simulation contributions")
    covered = [r["P10_booking_reporting"] <= actual[(r["forecast_snapshot_id"],r["opportunity_id"])] <= r["P90_booking_reporting"] for r in evaluated]
    return {"interval": "P10-P90", "coverage": sum(covered)/len(covered), "mean_interval_width": sum(r["P90_booking_reporting"]-r["P10_booking_reporting"] for r in evaluated)/len(evaluated), "records": len(evaluated)}
