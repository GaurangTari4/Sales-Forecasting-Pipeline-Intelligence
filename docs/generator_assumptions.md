# Synthetic sales simulation assumptions

The generator is deterministic: one `random.Random` stream is initialized from the configured seed (`20261022` by default), and generation iterates in stable numeric-ID order. Equal config and seed produce equal records and CSV checksums.

- Deal amount is log-normal, adjusted for a year-end seasonal uplift and early-year slowdown.
- An opportunity starts in Prospecting. At each stage it receives a realistically bounded number of activities, waits a stage-specific dwell time, then progresses or closes lost using a logistic probability driven by latent deal quality, buyer urgency, cumulative activity, deal amount, stage, and industry.
- A Negotiation deal has a separate final win decision using the same simulated state. Thus the final outcome is an effect of the lifecycle; it is not an independent random label.
- Late progression can emit an immutable expected-close-date change event. Slippage is derived from these events relative to the original expected close date.
- Closed Won opportunities emit one booking recognition event 0–7 days after close. Closed Lost and open opportunities never emit bookings.
- Every tenth rep receives a deterministic effective-dated territory transfer. Assignment periods are adjacent, never overlapping.
- Quotas are generated for every rep/quarter with stable territory-linked variation and a bounded random component.
- Snapshot detail is reconstructed from only stage and change events dated at or before each snapshot cutoff. The default range produces eight quarterly snapshots.
- `ground_truth_outcomes.csv` includes latent process variables and outcome decision scores. It is protected simulation truth, not a model feature source. `ground_truth_anomalies.csv` is intentionally empty in this baseline because anomaly injection is not yet implemented.

Run the starter dataset with:

```powershell
& <python> -m src.generator --config configs/generator_starter.json --output output/starter
```

Use `configs/generator_full.json` for the 2,000 rep / 2,000 account / 20,000 opportunity target.
