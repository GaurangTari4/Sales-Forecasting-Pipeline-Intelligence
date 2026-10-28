# Scenario assumptions

Scenario runs always use the source forecast's snapshot, eligible opportunities, reporting currency, and forecast horizon. A named preset supplies the defaults below; explicitly submitted fields override only that field and are returned as `scenario_assumptions` with the saved run.

| Preset | Conversion log-odds shift | Slippage-day shift | Booking fraction | Activity-effectiveness log-odds |
|---|---:|---:|---:|---:|
| CONSERVATIVE | -0.35 | +14 | 0.95 | -0.05 |
| BASE | 0.00 | 0 | 1.00 | 0.00 |
| OPTIMISTIC | +0.25 | -7 | 1.00 | +0.05 |

The conversion and activity shifts alter the odds of a booking within the fixed horizon. Positive slippage moves expected booking timing later and weakens in-horizon probability. Booking fraction scales the portion of a won deal expected to be recognized in the horizon. These are explicit assumptions, not arbitrary output multipliers.

The API exposes the presets at `GET /scenario-presets`. The Scenario Planner fetches them from that endpoint, marks custom overrides clearly, and displays the exact effective configuration returned by its scenario run.
