# Weighted pipeline baseline

`src.forecasting.baseline` is a transparent benchmark, not a learned model. For each open opportunity:

`future expected bookings = reporting-currency amount × P(eventual win | snapshot stage) × P(booking is recognized in horizon | eventual win, expected close date, prior slippage) × expected booking fraction`.

The second probability is deliberately conditional on an eventual win. This prevents double-counting: the stage probability already represents chance of an eventual win, while the timing probability represents when that win is recognized. Timing defaults are 95% for a close date before the horizon, 80% inside it, and 10% after it, reduced by 10 percentage points per prior close-date change (floor 5%). The expected booking fraction defaults to 1.0.

Open pipeline value, weighted expected/future bookings, and bookings already recognized by the snapshot are separate measures. Closed-won deals have zero future contribution; their recognized amount appears only in `closed_won_bookings_as_of_reporting`. Lost deals contribute zero.

All opportunity IDs must be unique within a snapshot. The baseline consumes `amount_reporting_currency`; it can convert raw transaction values only with a valid exchange rate on or before the feature cutoff. Aggregations support any combination of quarter, territory, rep, stage, and product.

Limitations: stage priors and timing defaults are hand-tuned; they are not calibrated to observed outcomes, do not quantify uncertainty, and do not model correlations, capacity, partial bookings, or changing market conditions. They should be compared with a chronologically evaluated learned model.
