"""Explicit, leakage-safe historical backtesting for the API and dashboard."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from src.features import build_feature_dataset, build_labels
from src.forecasting.baseline import forecast_weighted_pipeline
from src.forecasting.model import ModelInputError, build_conversion_labels, predict_conversion, train_conversion_model_on_history
from src.forecasting.uncertainty import SCENARIOS, simulate_bookings

from .backtest import evaluate_forecasts


def _date(value): return date.fromisoformat(str(value)[:10])


def _observed_through(dataset: dict) -> date:
    timestamps = []
    for table, field in (("stage_history", "occurred_at"), ("activities", "occurred_at"), ("historical_bookings", "recognized_at")):
        timestamps.extend(_date(row[field]) for row in dataset.get(table, []) if row.get(field))
    if not timestamps: raise ModelInputError("No observed event timestamps are available for backtesting")
    return max(timestamps)


def completed_snapshots(dataset: dict) -> tuple[list[dict], date]:
    observed_through = _observed_through(dataset)
    snapshots = sorted(dataset.get("forecast_snapshots", []), key=lambda row: row["snapshot_at"])
    return [row for row in snapshots if _date(row["horizon_end"]) <= observed_through], observed_through


def _period(snapshot_id, features, rows):
    actual = sum(float(row["actual_booking_reporting"]) for row in rows)
    return {"snapshot_id": snapshot_id, "horizon_start": features[0]["label_horizon_start"], "horizon_end": features[0]["label_horizon_end"], "opportunities": len(rows), "actual_booking_reporting": actual, "weighted_pipeline_forecast": sum(float(row["weighted_pipeline_forecast"]) for row in rows), "conversion_model_forecast": sum(float(row["conversion_model_forecast"]) for row in rows)}


def run_historical_backtest(dataset: dict, seed: int = 20261022) -> dict:
    """Rolling-origin scoring; each prediction uses only information known then.

    The temporary backtest models are neither persisted nor used by the serving
    forecast path.  This avoids turning an evaluation display into model tuning.
    """
    completed, observed_through = completed_snapshots(dataset)
    if not completed: raise ModelInputError("No completed historical forecast horizons are available for backtesting")
    all_features = build_feature_dataset(dataset)
    features_by_snapshot = defaultdict(list)
    for row in all_features: features_by_snapshot[row["forecast_snapshot_id"]].append(row)
    booking_labels = {(row["forecast_snapshot_id"], row["opportunity_id"]): row for row in build_labels(dataset, all_features)}
    conversion_labels = build_conversion_labels(dataset, all_features)
    conversion_by_key = {(row["forecast_snapshot_id"], row["opportunity_id"]): row for row in conversion_labels}
    completed_by_id = {row["forecast_snapshot_id"]: row for row in completed}
    eligibility, evaluation_rows, training_by_snapshot = [], [], {}
    for header in sorted(dataset.get("forecast_snapshots", []), key=lambda row: row["snapshot_at"]):
        snapshot_id = header["forecast_snapshot_id"]
        held_out_features = features_by_snapshot.get(snapshot_id, [])
        entry = {"snapshot_id": snapshot_id, "snapshot_at": header["snapshot_at"], "horizon_end": header["horizon_end"], "eligible_opportunities": len(held_out_features)}
        if snapshot_id not in completed_by_id or _date(header["horizon_end"]) > observed_through:
            eligibility.append({**entry, "status": "excluded", "reason": "horizon_not_complete_by_observed_through"}); continue
        if not held_out_features:
            eligibility.append({**entry, "status": "excluded", "reason": "no_eligible_open_opportunities_at_snapshot"}); continue
        if any((snapshot_id, row["opportunity_id"]) not in conversion_by_key for row in held_out_features):
            eligibility.append({**entry, "status": "excluded", "reason": "missing_realized_outcome_label"}); continue
        # An outcome ending on the snapshot date is not yet assumed to be known.
        training_ids = {row["forecast_snapshot_id"] for row in completed if _date(row["horizon_end"]) < _date(header["snapshot_at"])}
        held_out_opportunity_ids = {row["opportunity_id"] for row in held_out_features}
        train_features = [row for row in all_features if row["forecast_snapshot_id"] in training_ids and row["opportunity_id"] not in held_out_opportunity_ids]
        train_labels = [row for row in conversion_labels if row["forecast_snapshot_id"] in training_ids and row["opportunity_id"] not in held_out_opportunity_ids]
        if not train_features:
            eligibility.append({**entry, "status": "excluded", "reason": "no_strictly_prior_completed_training_horizon"}); continue
        try:
            model, model_metadata = train_conversion_model_on_history(train_features, train_labels)
        except ModelInputError as error:
            eligibility.append({**entry, "status": "excluded", "reason": "training_window_ineligible", "detail": str(error)}); continue
        eligibility.append({**entry, "status": "evaluated", "reason": None, "training_snapshot_ids": sorted(training_ids), "training_rows": len(train_features), "held_out_opportunity_ids_excluded_from_training": len(held_out_opportunity_ids)})
        training_by_snapshot[snapshot_id] = model_metadata
        model_predictions = predict_conversion(model, held_out_features)
        baseline = forecast_weighted_pipeline(held_out_features, group_by=("quarter",))
        baseline_contributions = {(row["forecast_snapshot_id"], row["opportunity_id"]): row for row in baseline["contributions"]}
        baseline_predictions = [{"forecast_snapshot_id": row["forecast_snapshot_id"], "opportunity_id": row["opportunity_id"], "conversion_probability": float(baseline_contributions[(row["forecast_snapshot_id"], row["opportunity_id"])]["forecast_bookings_future_horizon_reporting"]) / max(float(row["amount_reporting_currency"]), 1e-12)} for row in held_out_features]
        baseline_simulation = simulate_bookings(held_out_features, baseline_predictions, SCENARIOS["BASE"], simulations=500, seed=seed, group_by=("quarter",))
        model_simulation = simulate_bookings(held_out_features, model_predictions, SCENARIOS["BASE"], simulations=500, seed=seed, group_by=("quarter",))
        baseline_simulated = {(row["forecast_snapshot_id"], row["opportunity_id"]): row for row in baseline_simulation["contributions"]}
        model_simulated = {(row["forecast_snapshot_id"], row["opportunity_id"]): row for row in model_simulation["contributions"]}
        model_probability = {(row["forecast_snapshot_id"], row["opportunity_id"]): row["conversion_probability"] for row in model_predictions}
        baseline_probability = {(row["forecast_snapshot_id"], row["opportunity_id"]): row["conversion_probability"] for row in baseline_predictions}
        for feature in held_out_features:
            key = (feature["forecast_snapshot_id"], feature["opportunity_id"])
            booking, conversion = booking_labels[key], conversion_by_key[key]
            amount = float(feature["amount_reporting_currency"])
            evaluation_rows.append({"held_out": True, "forecast_snapshot_id": key[0], "opportunity_id": key[1], "label_horizon_end": feature["label_horizon_end"], "quarter": f"{feature['label_horizon_end'][:4]}Q{(_date(feature['label_horizon_end']).month-1)//3+1}", "territory_id": feature["territory_id"], "stage_at_snapshot": feature["stage_at_snapshot"], "rep_segment": feature["rep_role"], "deal_size_band": "SMALL" if amount < 10000 else "MEDIUM" if amount < 50000 else "LARGE", "actual_booking_reporting": booking["realized_booking_reporting"], "actual_win": int(conversion["conversion_within_horizon"]), "weighted_pipeline_forecast": baseline_contributions[key]["forecast_bookings_future_horizon_reporting"], "weighted_pipeline_probability": baseline_probability[key], "weighted_pipeline_p10": baseline_simulated[key]["P10_booking_reporting"], "weighted_pipeline_p90": baseline_simulated[key]["P90_booking_reporting"], "conversion_model_forecast": model_simulated[key]["expected_booking_reporting"], "conversion_model_probability": model_probability[key], "conversion_model_p10": model_simulated[key]["P10_booking_reporting"], "conversion_model_p90": model_simulated[key]["P90_booking_reporting"]})
    if not evaluation_rows: raise ModelInputError("No completed snapshots had an eligible strictly-prior training window")
    metrics = evaluate_forecasts(evaluation_rows, methods=("weighted_pipeline", "conversion_model"))
    by_snapshot = defaultdict(list)
    for row in evaluation_rows: by_snapshot[row["forecast_snapshot_id"]].append(row)
    periods = [_period(snapshot_id, features_by_snapshot[snapshot_id], rows) for snapshot_id, rows in sorted(by_snapshot.items())]
    evaluated_ids = sorted(by_snapshot)
    return {"status": "complete", "data_context": "historical rolling-origin held-out outcomes", "observed_through": observed_through.isoformat(), "completed_snapshot_ids": [row["forecast_snapshot_id"] for row in completed], "evaluation_eligibility": eligibility, "evaluated_snapshot_ids": evaluated_ids, "evaluated_snapshots": len(evaluated_ids), "evaluated_opportunities": len(evaluation_rows), "training_snapshot_ids": sorted({item for entry in eligibility for item in entry.get("training_snapshot_ids", [])}), "methods": metrics["methods"], "periods": periods, "metric_definitions": {"mae": "Opportunity-level mean absolute error, aggregated across all evaluated opportunities.", "rmse": "Square root of mean squared opportunity-level forecast error.", "wape": "Sum of absolute opportunity errors divided by sum of absolute actual bookings across all evaluated opportunities.", "forecast_bias": "Mean forecast minus actual per opportunity; positive is over-forecasting and negative is under-forecasting.", "interval_coverage": "Share of opportunity actual bookings within that method's P10–P90 interval."}, "model_metadata": {"model_version": "conversion-logistic-v1", "training_by_snapshot": training_by_snapshot, "held_out_opportunity_ids_excluded_from_training": sum(entry.get("held_out_opportunity_ids_excluded_from_training", 0) for entry in eligibility)}, "exploratory": True, "note": "Synthetic rolling-origin results are exploratory. Each prediction uses only snapshot-available features and labels from horizons completed strictly before that snapshot."}


def _single_holdout_backtest(dataset: dict, seed: int = 20261022) -> dict:
    """Train before the held-out periods and evaluate only outcomes now complete."""
    completed, observed_through = completed_snapshots(dataset)
    if len(completed) < 5: raise ModelInputError("At least five completed snapshots are required for historical backtesting")
    features = build_feature_dataset(dataset)
    booking_labels = {(row["forecast_snapshot_id"], row["opportunity_id"]): row for row in build_labels(dataset, features)}
    conversion_labels = build_conversion_labels(dataset, features)
    conversion_by_key = {(row["forecast_snapshot_id"], row["opportunity_id"]): row for row in conversion_labels}
    held_out_headers = completed[-1:]
    held_out_ids = {row["forecast_snapshot_id"] for row in held_out_headers}
    first_held_out_snapshot = _date(held_out_headers[0]["snapshot_at"])
    # A training label must have completed before the earliest holdout snapshot.
    training_ids = {row["forecast_snapshot_id"] for row in completed if _date(row["horizon_end"]) < first_held_out_snapshot}
    held_out_opportunities = {row["opportunity_id"] for row in features if row["forecast_snapshot_id"] in held_out_ids}
    train_features = [row for row in features if row["forecast_snapshot_id"] in training_ids and row["opportunity_id"] not in held_out_opportunities]
    train_labels = [row for row in conversion_labels if row["forecast_snapshot_id"] in training_ids]
    held_out_features = [row for row in features if row["forecast_snapshot_id"] in held_out_ids]
    if not held_out_features: raise ModelInputError("No eligible opportunities exist in the completed holdout snapshots")
    train_labels = [row for row in train_labels if row["opportunity_id"] not in held_out_opportunities]
    model, model_metadata = train_conversion_model_on_history(train_features, train_labels)
    model_predictions = predict_conversion(model, held_out_features)
    baseline = forecast_weighted_pipeline(held_out_features, group_by=("quarter",))
    baseline_contributions = {(row["forecast_snapshot_id"], row["opportunity_id"]): row for row in baseline["contributions"]}
    baseline_predictions = [{"forecast_snapshot_id": row["forecast_snapshot_id"], "opportunity_id": row["opportunity_id"], "conversion_probability": float(baseline_contributions[(row["forecast_snapshot_id"], row["opportunity_id"])]["forecast_bookings_future_horizon_reporting"]) / max(float(row["amount_reporting_currency"]), 1e-12)} for row in held_out_features]
    baseline_simulation = simulate_bookings(held_out_features, baseline_predictions, SCENARIOS["BASE"], simulations=500, seed=seed, group_by=("quarter",))
    model_simulation = simulate_bookings(held_out_features, model_predictions, SCENARIOS["BASE"], simulations=500, seed=seed, group_by=("quarter",))
    baseline_simulated = {(row["forecast_snapshot_id"], row["opportunity_id"]): row for row in baseline_simulation["contributions"]}
    model_simulated = {(row["forecast_snapshot_id"], row["opportunity_id"]): row for row in model_simulation["contributions"]}
    model_probability = {(row["forecast_snapshot_id"], row["opportunity_id"]): row["conversion_probability"] for row in model_predictions}
    baseline_probability = {(row["forecast_snapshot_id"], row["opportunity_id"]): row["conversion_probability"] for row in baseline_predictions}
    evaluation_rows = []
    for feature in held_out_features:
        key = (feature["forecast_snapshot_id"], feature["opportunity_id"])
        booking, conversion = booking_labels[key], conversion_by_key[key]
        amount = float(feature["amount_reporting_currency"])
        evaluation_rows.append({"held_out": True, "forecast_snapshot_id": key[0], "opportunity_id": key[1], "label_horizon_end": feature["label_horizon_end"], "quarter": f"{feature['label_horizon_end'][:4]}Q{(_date(feature['label_horizon_end']).month-1)//3+1}", "territory_id": feature["territory_id"], "stage_at_snapshot": feature["stage_at_snapshot"], "rep_segment": feature["rep_role"], "deal_size_band": "SMALL" if amount < 10000 else "MEDIUM" if amount < 50000 else "LARGE", "actual_booking_reporting": booking["realized_booking_reporting"], "actual_win": int(conversion["conversion_within_horizon"]), "weighted_pipeline_forecast": baseline_contributions[key]["forecast_bookings_future_horizon_reporting"], "weighted_pipeline_probability": baseline_probability[key], "weighted_pipeline_p10": baseline_simulated[key]["P10_booking_reporting"], "weighted_pipeline_p90": baseline_simulated[key]["P90_booking_reporting"], "conversion_model_forecast": model_simulated[key]["expected_booking_reporting"], "conversion_model_probability": model_probability[key], "conversion_model_p10": model_simulated[key]["P10_booking_reporting"], "conversion_model_p90": model_simulated[key]["P90_booking_reporting"]})
    metrics = evaluate_forecasts(evaluation_rows, methods=("weighted_pipeline", "conversion_model"))
    by_snapshot = defaultdict(list)
    for row in evaluation_rows: by_snapshot[row["forecast_snapshot_id"]].append(row)
    periods = [_period(snapshot_id, [row for row in held_out_features if row["forecast_snapshot_id"] == snapshot_id], rows) for snapshot_id, rows in sorted(by_snapshot.items())]
    return {"status": "complete", "data_context": "historical held-out simulated outcomes", "observed_through": observed_through.isoformat(), "completed_snapshot_ids": [row["forecast_snapshot_id"] for row in completed], "evaluated_snapshot_ids": [row["forecast_snapshot_id"] for row in held_out_headers], "evaluated_snapshots": len(held_out_headers), "evaluated_opportunities": len(evaluation_rows), "training_snapshot_ids": sorted(training_ids), "methods": metrics["methods"], "periods": periods, "model_metadata": {"model_version": model["model_version"], **model_metadata, "held_out_opportunity_ids_excluded_from_training": len(held_out_opportunities)}, "exploratory": True, "note": "Synthetic, small-sample held-out results are exploratory. The conversion model is uncalibrated because its strictly prior validation window was class-sparse."}
