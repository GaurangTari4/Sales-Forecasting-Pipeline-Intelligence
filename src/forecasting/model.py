"""Leak-safe, interpretable logistic opportunity-conversion model (NumPy only)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import pickle
import platform
import sys

import numpy as np

from src.features.contracts import FEATURE_SCHEMA_VERSION
from .baseline import forecast_weighted_pipeline

MODEL_VERSION = "conversion-logistic-v1"
NUMERIC = ("amount_reporting_currency", "effective_stage_probability", "opportunity_age_days", "days_until_expected_close", "current_stage_duration_days", "calls_30d", "emails_30d", "meetings_30d", "demos_30d", "calls_90d", "emails_90d", "meetings_90d", "demos_90d", "days_since_last_qualifying_activity", "historical_conversion_rate", "rep_historical_win_rate", "territory_historical_win_rate", "prior_close_date_change_count", "observed_slippage_days")
CATEGORICAL = ("stage_at_snapshot", "product_type", "account_segment", "account_industry", "territory_region", "rep_role")
PROHIBITED = {"ground_truth", "ground_truth_outcomes", "ground_truth_anomalies", "issue_id", "issue_type", "final_outcome", "latent_quality", "realized_booking_reporting", "booked_in_horizon"}


class ModelInputError(ValueError): pass


@dataclass(frozen=True)
class ModelConfig:
    seed: int = 20261022
    learning_rate: float = 0.15
    iterations: int = 800
    l2: float = 0.01
    calibration_iterations: int = 250


def _date(value): return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def build_conversion_labels(dataset: dict[str, list[dict]], feature_rows: list[dict]) -> list[dict]:
    """Target = a CLOSED_WON event occurring in the row's future label horizon."""
    events = defaultdict(list)
    for event in dataset.get("stage_history", []): events[event["opportunity_id"]].append(event)
    labels = []
    for row in feature_rows:
        start, end = _date(row["label_horizon_start"]), _date(row["label_horizon_end"])
        won = any(e["to_stage"] == "CLOSED_WON" and start <= _date(e["occurred_at"]) <= end for e in events[row["opportunity_id"]])
        labels.append({"forecast_snapshot_id": row["forecast_snapshot_id"], "opportunity_id": row["opportunity_id"], "conversion_within_horizon": int(won), "label_horizon_start": row["label_horizon_start"], "label_horizon_end": row["label_horizon_end"]})
    return labels


def _one_snapshot_per_opportunity(rows, labels):
    """Keep earliest snapshot per opportunity, eliminating repeated-snapshot group leakage."""
    target = {(x["forecast_snapshot_id"], x["opportunity_id"]): x["conversion_within_horizon"] for x in labels}
    selected = {}
    for row in sorted(rows, key=lambda r: (r["opportunity_id"], r["feature_cutoff_at"])):
        if row["opportunity_id"] not in selected: selected[row["opportunity_id"]] = row
    return [(r, target[(r["forecast_snapshot_id"], r["opportunity_id"])]) for r in selected.values()]


def chronological_group_split(rows, labels):
    """70/15/15 chronological split of opportunity groups; no ID occurs in two splits."""
    examples = _one_snapshot_per_opportunity(rows, labels)
    dates = sorted({r["feature_cutoff_at"] for r, _ in examples})
    if len(dates) < 3: raise ModelInputError("At least three snapshot dates are required for chronological train/validation/test")
    train_end = dates[max(0, int(len(dates) * .70) - 1)]
    validation_end = dates[max(int(len(dates) * .70), int(len(dates) * .85) - 1)]
    splits = {"train": [], "validation": [], "test": []}
    for value in examples:
        cutoff = value[0]["feature_cutoff_at"]
        splits["train" if cutoff <= train_end else "validation" if cutoff <= validation_end else "test"].append(value)
    if not all(splits.values()): raise ModelInputError("Chronological split produced an empty partition; generate a longer history")
    return splits


class Encoder:
    def fit(self, rows):
        self.categories = {name: sorted({str(r.get(name, "<MISSING>")) for r in rows}) for name in CATEGORICAL}
        numeric = np.array([[float(r.get(name, 0) or 0) for name in NUMERIC] for r in rows], dtype=float)
        self.mean = numeric.mean(axis=0); self.scale = numeric.std(axis=0); self.scale[self.scale == 0] = 1
        self.feature_names = list(NUMERIC) + [f"{name}={value}" for name in CATEGORICAL for value in self.categories[name]]
        return self
    def transform(self, rows):
        numeric = np.array([[float(r.get(name, 0) or 0) for name in NUMERIC] for r in rows], dtype=float)
        values = [(numeric - self.mean) / self.scale]
        for name in CATEGORICAL:
            values.append(np.array([[float(str(r.get(name, "<MISSING>")) == value) for value in self.categories[name]] for r in rows]))
        return np.hstack(values)


def _sigmoid(x): return 1 / (1 + np.exp(-np.clip(x, -30, 30)))


def _fit_logistic(x, y, config, weights=None):
    weights = np.ones(len(y)) if weights is None else weights
    coef = np.zeros(x.shape[1]); intercept = 0.0
    for _ in range(config.iterations):
        p = _sigmoid(x @ coef + intercept); error = (p - y) * weights / weights.sum()
        coef -= config.learning_rate * (x.T @ error + config.l2 * coef)
        intercept -= config.learning_rate * error.sum()
    return coef, intercept


def _metrics(y, p):
    eps = 1e-12; p = np.clip(p, eps, 1-eps)
    brier = float(np.mean((p-y)**2)); log_loss = float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p)))
    thresholds = np.linspace(.05, .95, 19); best = max(((2 * ((p >= t) & (y == 1)).sum() / max(1, 2*((p >= t) & (y == 1)).sum() + ((p >= t) & (y == 0)).sum() + ((p < t) & (y == 1)).sum()), float(t)) for t in thresholds), key=lambda z:z[0])
    calibration = [{"lower": i/5, "upper": (i+1)/5, "count": int(((p >= i/5) & (p < (i+1)/5 if i < 4 else p <= 1)).sum()), "mean_probability": float(p[(p >= i/5) & (p < (i+1)/5 if i < 4 else p <= 1)].mean()) if ((p >= i/5) & (p < (i+1)/5 if i < 4 else p <= 1)).any() else None, "observed_rate": float(y[(p >= i/5) & (p < (i+1)/5 if i < 4 else p <= 1)].mean()) if ((p >= i/5) & (p < (i+1)/5 if i < 4 else p <= 1)).any() else None} for i in range(5)]
    return {"brier_score": brier, "log_loss": log_loss, "best_f1": best[0], "threshold": best[1], "positive_rate": float(y.mean()), "calibration": calibration}


def _check_schema(rows):
    if not rows: raise ModelInputError("No feature rows")
    for row in rows:
        if row.get("feature_schema_version") != FEATURE_SCHEMA_VERSION: raise ModelInputError("Incompatible feature schema version")
        unsafe = PROHIBITED & set(row)
        if unsafe: raise ModelInputError(f"Prohibited future/ground-truth fields in features: {sorted(unsafe)}")
        missing = set(NUMERIC + CATEGORICAL) - set(row)
        if missing: raise ModelInputError(f"Missing model features: {sorted(missing)}")


def _booking_error(rows, y, probabilities):
    """MAE of snapshot-level expected bookings against realized conversion × amount."""
    predicted = defaultdict(float); actual = defaultdict(float)
    for row, target, probability in zip(rows, y, probabilities):
        snapshot = row["forecast_snapshot_id"]; amount = float(row["amount_reporting_currency"])
        predicted[snapshot] += amount * float(probability); actual[snapshot] += amount * float(target)
    return float(np.mean([abs(predicted[key] - actual[key]) for key in actual]))


def train_conversion_model(feature_rows, conversion_labels, config: ModelConfig = ModelConfig()):
    """Fit logistic regression; calibration and threshold use validation only."""
    _check_schema(feature_rows); splits = chronological_group_split(feature_rows, conversion_labels)
    train_rows, train_y = zip(*splits["train"]); val_rows, val_y = zip(*splits["validation"]); test_rows, test_y = zip(*splits["test"])
    encoder = Encoder().fit(train_rows); x_train = encoder.transform(train_rows); y_train = np.array(train_y, dtype=float)
    positives, negatives = y_train.sum(), len(y_train)-y_train.sum()
    if positives == 0 or negatives == 0: raise ModelInputError("Training partition needs both conversion classes")
    weights = np.where(y_train == 1, len(y_train)/(2*positives), len(y_train)/(2*negatives))
    coef, intercept = _fit_logistic(x_train, y_train, config, weights)
    raw_val = _sigmoid(encoder.transform(val_rows) @ coef + intercept)
    # Platt scaling uses validation only. A small logistic fit on logits avoids leakage from test.
    logits = np.log(np.clip(raw_val, 1e-6, 1-1e-6) / np.clip(1-raw_val, 1e-6, 1))[:, None]
    calibrator_config = ModelConfig(seed=config.seed, learning_rate=.1, iterations=config.calibration_iterations, l2=.01)
    cal_coef, cal_intercept = _fit_logistic(logits, np.array(val_y, dtype=float), calibrator_config)
    calibrate = lambda raw: _sigmoid(np.log(np.clip(raw,1e-6,1-1e-6)/np.clip(1-raw,1e-6,1)) * cal_coef[0] + cal_intercept)
    validation = _metrics(np.array(val_y, dtype=float), calibrate(raw_val)); test_p = calibrate(_sigmoid(encoder.transform(test_rows) @ coef + intercept)); test = _metrics(np.array(test_y, dtype=float), test_p)
    baseline = forecast_weighted_pipeline(list(test_rows), group_by=("quarter",))
    baseline_by_id = {r["opportunity_id"]: float(r["forecast_bookings_future_horizon_reporting"]) / max(float(next(x for x in test_rows if x["opportunity_id"] == r["opportunity_id"])["amount_reporting_currency"]), 1e-12) for r in baseline["contributions"]}
    model = {"model_version": MODEL_VERSION, "feature_schema_version": FEATURE_SCHEMA_VERSION, "encoder": encoder, "coef": coef, "intercept": intercept, "calibrator": (float(cal_coef[0]), float(cal_intercept)), "threshold": validation["threshold"], "config": asdict(config)}
    return model, {"validation": validation, "test": {**test, "forecast_level_booking_mae": _booking_error(test_rows, test_y, test_p)}, "baseline_test": {"forecast_level_booking_mae": _booking_error(test_rows, test_y, [baseline_by_id[r["opportunity_id"]] for r in test_rows]), "total_future_forecast_reporting": baseline["totals"]["forecast_bookings_future_horizon_reporting"]}, "split_counts": {k: len(v) for k,v in splits.items()}, "split_opportunity_ids": {k: [r["opportunity_id"] for r,_ in v] for k,v in splits.items()}, "training_window": [min(r["feature_cutoff_at"] for r in train_rows), max(r["feature_cutoff_at"] for r in train_rows)], "label_horizon": sorted({(r["label_horizon_start"], r["label_horizon_end"]) for r in feature_rows})}


def train_conversion_model_on_history(feature_rows, conversion_labels, config: ModelConfig = ModelConfig()):
    """Fit on a strictly prior historical window when a three-way split is class-sparse.

    Callers must keep the training window before the held-out period and exclude
    held-out opportunity IDs. The returned model is intentionally uncalibrated;
    calibration requires a separate prior validation period containing both classes.
    """
    _check_schema(feature_rows)
    targets = {(row["forecast_snapshot_id"], row["opportunity_id"]): row["conversion_within_horizon"] for row in conversion_labels}
    if any((row["forecast_snapshot_id"], row["opportunity_id"]) not in targets for row in feature_rows):
        raise ModelInputError("Missing conversion labels for historical training rows")
    y = np.array([targets[(row["forecast_snapshot_id"], row["opportunity_id"])] for row in feature_rows], dtype=float)
    positives, negatives = y.sum(), len(y) - y.sum()
    if positives == 0 or negatives == 0: raise ModelInputError("Historical training window needs both conversion classes")
    encoder = Encoder().fit(feature_rows); x = encoder.transform(feature_rows)
    weights = np.where(y == 1, len(y)/(2*positives), len(y)/(2*negatives))
    coef, intercept = _fit_logistic(x, y, config, weights)
    model = {"model_version": MODEL_VERSION, "feature_schema_version": FEATURE_SCHEMA_VERSION, "encoder": encoder, "coef": coef, "intercept": intercept, "calibrator": (1.0, 0.0), "threshold": .5, "config": asdict(config)}
    return model, {"training_rows": len(feature_rows), "training_window": [min(row["feature_cutoff_at"] for row in feature_rows), max(row["feature_cutoff_at"] for row in feature_rows)], "calibration": "not_applied_due_to_class_sparse_chronological_validation_window"}


def predict_conversion(model, rows):
    _check_schema(rows)
    if model["feature_schema_version"] != FEATURE_SCHEMA_VERSION: raise ModelInputError("Model and feature schema versions differ")
    raw = _sigmoid(model["encoder"].transform(rows) @ model["coef"] + model["intercept"]); a,b = model["calibrator"]
    calibrated = _sigmoid(np.log(np.clip(raw,1e-6,1-1e-6)/np.clip(1-raw,1e-6,1))*a+b)
    return [{"forecast_snapshot_id": row["forecast_snapshot_id"], "opportunity_id": row["opportunity_id"], "conversion_probability": float(p), "predicted_conversion": bool(p >= model["threshold"]), "expected_booking_reporting": str((float(row["amount_reporting_currency"])*p))} for row,p in zip(rows, calibrated)]


def save_model_artifacts(model, metadata, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "model.pkl").open("wb") as f: pickle.dump(model, f)
    manifest = {"model_version": MODEL_VERSION, "feature_schema_version": FEATURE_SCHEMA_VERSION, "feature_names": model["encoder"].feature_names, "random_seed": model["config"]["seed"], "software_versions": {"python": sys.version, "numpy": np.__version__, "platform": platform.platform()}, **metadata}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main():
    """Reproducible training command: python -m src.forecasting.model --input ..."""
    import argparse
    from src.features import build_feature_dataset
    from src.validation.io import load_csv_dataset
    parser = argparse.ArgumentParser(description="Train the point-in-time conversion logistic model.")
    parser.add_argument("--input", type=Path, required=True, help="Generated dataset CSV directory")
    parser.add_argument("--output", type=Path, required=True, help="Model artifact directory")
    args = parser.parse_args()
    dataset = load_csv_dataset(args.input); features = build_feature_dataset(dataset); labels = build_conversion_labels(dataset, features)
    model, report = train_conversion_model(features, labels); manifest = save_model_artifacts(model, report, args.output)
    print(json.dumps({"model_version": manifest["model_version"], "split_counts": report["split_counts"], "test": report["test"], "baseline_test": report["baseline_test"]}, indent=2))


if __name__ == "__main__": main()
