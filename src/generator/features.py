"""Leakage-safe feature projection; protected ground-truth and anomaly tables are never inputs."""

def build_model_feature_matrix(dataset: dict[str, list[dict]]) -> list[dict]:
    return [{"forecast_snapshot_id": row["forecast_snapshot_id"], "opportunity_id": row["opportunity_id"],
             "stage_at_snapshot": row["stage_at_snapshot"], "amount_transaction_currency": row["amount_transaction_currency"],
             "expected_close_date": row["expected_close_date"]} for row in dataset["snapshot_opportunities"]]
