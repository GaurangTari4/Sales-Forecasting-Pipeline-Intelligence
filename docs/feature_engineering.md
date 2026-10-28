# Point-in-time feature engineering

`src.features` creates one versioned (`pit-sales-features-v1`) feature row for an opportunity and forecast snapshot. The feature cutoff is exactly `forecast_snapshots.snapshot_at`; every stage-history row, activity, change event, booking used in historical performance, assignment, exchange rate, and stage-probability version is filtered to information available at or before that timestamp.

The label horizon is explicitly copied from the snapshot header (`horizon_start` through `horizon_end`). Labels are written separately in `labels.csv`, and use booking recognition events only inside that horizon. Thus, a January 31 feature row never uses a February call, stage movement, close-date change, booking, final outcome, or conversion result; a February/March booking can be used only as that January row's target.

Open opportunities created on or before a cutoff are eligible. Opportunities created after the cutoff are absent. By default, opportunities already closed at the cutoff are also absent because they are no longer forecastable; set `FeatureConfig(include_closed_opportunities=True)` for retrospective analysis. Ground-truth exports and anomaly labels are never projected into features.

Run the pipeline with:

```powershell
& <python> -m src.features --input output/starter --output output/features
```

The output contains `features.csv`, `labels.csv`, and a checksum manifest. Call `assert_temporal_integrity(dataset, features)` before training or after loading a persisted feature dataset.
