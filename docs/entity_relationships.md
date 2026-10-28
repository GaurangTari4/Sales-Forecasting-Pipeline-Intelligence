# Entity relationships

This brief-specific entry point supplements the canonical [relationships](relationships.md) document.

- Territory → Account is 1:N; Account → Opportunity is 1:N.
- SalesRep ↔ Territory is N:M over time through `rep_territory_assignments`; each rep's effective periods cannot overlap.
- Opportunity → StageHistory, Activity, opportunity-change event, and HistoricalBooking is 1:N.
- ForecastSnapshot ↔ Opportunity is N:M through `snapshot_opportunities`, uniquely keyed by snapshot and opportunity.
- ForecastSnapshot → ForecastRun → OpportunityForecast preserves immutable run lineage and contribution detail.

Optional end dates represent ongoing effective relationships. Event time and effective time are distinct: as-of features use event timestamps and select assignments/probabilities effective at the snapshot date.
