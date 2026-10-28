# Interview demonstration script

## Opening — 30 seconds

“This is a sales forecasting and pipeline-intelligence system designed around a practical executive question: what will book in the forecast horizon, what assumptions drive the answer, and what should the sales organization investigate next? It is an auditable local demonstration using deterministic synthetic CRM data, not a production forecast claim.”

## Walkthrough — 4 to 6 minutes

1. **Executive Overview** — Run the BASE forecast for `FCST-2025-03-31-001`. Explain that forecast mean, quota, and opportunity contributions share the same snapshot, horizon, eligible-representative population, and reporting currency. Point out that P10/P50/P90 are aggregate portfolio simulation quantiles, not sums of opportunity quantiles.
2. **Pipeline Explorer** — Select an opportunity. Show readable amount, stage probability, expected close date, expected booking contribution, and P10–P90 interval. Expand technical details only when discussing lineage. Explain that the displayed contributions reconcile to the executive forecast total.
3. **Risk and Exceptions** — Filter a quota-gap exception by severity or representative. Explain that the rule supplies evidence, business impact, severity, rule version, and recommended investigation. A quota gap is not automatically CRITICAL: severity considers gap, attainment, and whether forecast is zero.
4. **Scenario Planner** — Select CONSERVATIVE, then compare. Show its recorded conversion, slippage, and booking-fraction assumptions. Explain that scenarios change model inputs and recompute simulations; they are not arbitrary output multipliers. Mention that zero-base percentage changes appear as `N/A`, not an invented infinity.
5. **Model Evaluation** — Run the explicit historical backtest. Explain the rolling-origin control: each historical snapshot is evaluated only using features available at its cutoff and training labels from horizons completed strictly before that cutoff. The latest synthetic result evaluates 3 snapshots and 40 opportunities, so it is exploratory. The conversion model has lower MAE than the weighted-pipeline benchmark on that sample; it is not a claim of production superiority.
6. **Audit and Traceability** — Open a persisted forecast’s audit page and run reproducibility verification. Show snapshot cutoff versus execution timestamp, model and feature versions, seed, assumptions, hashes, and opportunity count. Emphasize that replay is in memory and does not overwrite or append historical forecast records.

## Key technical decisions

- **Point-in-time feature construction:** events and effective-dated reference values are selected as of each snapshot; labels are a separate workflow to prevent future-outcome leakage.
- **Schema-aware ingestion:** absent optional dates, numerics, booleans, and foreign keys become SQL `NULL`, while valid empty text remains text and required fields remain validated.
- **Immutable forecast lineage:** PostgreSQL stores run metadata and opportunity intervals; persistent runtime artifacts support retrieval across API restarts.
- **Explicit scenarios and exceptions:** scenario assumptions and rule evidence are recorded, so users can challenge the drivers instead of accepting unexplained output.
- **Rolling-origin evaluation:** it exposes early snapshots that cannot be evaluated because strictly prior data lacks both outcome classes, rather than silently using future data.

## Engineering challenges worth discussing

- Correctly aligning forecast, quota, currency, reps, territories, and horizon scope.
- Computing portfolio uncertainty from aggregate simulations instead of summing per-opportunity percentiles.
- Preserving transaction atomicity and idempotent seed behavior in Docker bootstrap.
- Preventing Streamlit state/rerun issues while retaining a clear API/dashboard contract.
- Supporting reproducibility without mutating historical forecast records.

## Close — 20 seconds

“The portfolio value is not just a forecast number. It demonstrates data-engineering safeguards, ML evaluation discipline, API/database lineage, and an executive-facing workflow. The documented boundary is equally important: synthetic data, a small exploratory backtest, and local-only security posture mean this needs real-data validation and deployment hardening before production use.”
