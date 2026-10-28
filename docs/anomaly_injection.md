# Controlled anomaly injection

Baseline generation remains clean. Running the generator with `--inject-anomalies` writes a separate anomalous dataset and its `ground_truth.csv`. The rate is recorded for configuration lineage; this initial controlled suite always injects exactly one deterministic case for each of the five required scenarios.

| Issue type | Test path | Detection rule | Expected action |
|---|---|---|---|
| FUTURE_OUTCOME_LEAKAGE | `anomalous_forecast_inputs` | `LEAKAGE.FEATURE_AS_OF` | Quarantine feature set |
| STAGE_PROBABILITY_MISMATCH | `anomalous_forecast_inputs` | `FORECAST.STAGE_PROBABILITY_EFFECTIVE_DATE` | Recompute forecast input |
| DUPLICATE_OPPORTUNITY_COUNT | `anomalous_aggregation_inputs` | `AGGREGATION.UNIQUE_SNAPSHOT_OPPORTUNITY` | Deduplicate input |
| CLOSE_DATE_BEFORE_CREATION | anomalous opportunity change event | `OPPORTUNITY.EXPECTED_CLOSE_AFTER_CREATION` | Quarantine event |
| MIXED_CURRENCY_TOTAL | `anomalous_aggregation_inputs` | `AGGREGATION.COMMON_REPORTING_CURRENCY` | Convert or reject total |

The leakage fixture contains two rows intentionally: `final_outcome` is improperly declared as a feature and is detected because its source event follows the snapshot. `final_outcome_label` uses the same later outcome as an evaluation label and is not flagged, because labels are permitted after the forecast horizon. Ground truth is excluded from the feature projection in `src/generator/features.py`.
