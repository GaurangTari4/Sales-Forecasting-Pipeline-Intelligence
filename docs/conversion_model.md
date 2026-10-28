# Opportunity conversion model

The first learned model is `conversion-logistic-v1`, an interpretable, L2-regularized logistic regression implemented with NumPy because scikit-learn is not installed in this runtime. The target is `conversion_within_horizon`: `1` only when a `CLOSED_WON` stage-history event occurs after the snapshot cutoff and within that row's explicit label horizon. It is not a final-outcome label and it does not use a booking recognized before the snapshot.

Use the reproducible command:

```powershell
& <python> -m src.forecasting.model --input output/starter --output output/model
```

The model uses only the versioned point-in-time feature schema. IDs, cutoff/horizon fields, targets, ground truth, final outcomes, and other protected future fields are excluded. Schema validation rejects protected fields before training or inference.

To prevent leakage from repeat observations of the same opportunity, the workflow keeps its earliest eligible snapshot only, then assigns whole opportunity groups chronologically to 70% training, 15% validation, and 15% test partitions. A group cannot occur in multiple partitions. Class weights are inverse-frequency weights computed on training data only. Platt calibration and the F1 decision threshold are fitted/selected on validation data only; the test partition is never used for them.

Artifacts are `model.pkl` and `manifest.json`; the manifest records the feature schema and encoded feature names, seed/configuration, train window, label horizons, split IDs/counts, metrics, and runtime versions. It reports Brier score, log loss, calibration bins, F1/threshold, positive rate, and snapshot-level booking MAE. The weighted-pipeline benchmark is evaluated on the identical held-out rows. No superiority claim is made by code or documentation: interpret the comparison only after inspecting the held-out values in that manifest.

Gradient boosting is deliberately deferred: the dependency is absent and this first implementation needs a meaningful held-out advantage over the transparent baseline before that added complexity is justified.
