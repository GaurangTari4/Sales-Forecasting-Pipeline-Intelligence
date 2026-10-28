"""Run with: streamlit run dashboard/app.py"""
from __future__ import annotations

import os
import pandas as pd
import streamlit as st

from dashboard.client import ForecastApiClient, ForecastApiError
from dashboard.components import render_labeled_value
from dashboard.formatting import (
    display_date, display_datetime, exception_evidence_summary, filter_exceptions,
    filter_opportunities, humanize_identifier, money, opportunity_display_row,
    percent, scenario_comparison_rows, scenario_percent_change, signed_number,
)

st.set_page_config(page_title="BUSS | Sales Forecasting & Pipeline Intelligence", page_icon="📈", layout="wide", initial_sidebar_state="expanded")


def apply_page_style() -> None:
    """Keep presentation styling local to the dashboard; no forecast values are changed."""
    st.markdown("""
    <style>
      .block-container {max-width: 1500px; padding-top: 2rem; padding-bottom: 3rem;}
      h1 {letter-spacing: -0.025em; margin-bottom: 0.15rem;}
      h2, h3 {padding-top: 0.65rem;}
      [data-testid="stMetric"] {background: rgba(28, 39, 57, 0.72); border: 1px solid rgba(148, 163, 184, 0.22); border-radius: 0.65rem; padding: 0.85rem;}
      [data-testid="stMetricLabel"] {font-size: 0.82rem;}
      [data-testid="stDataFrame"] {border: 1px solid rgba(148, 163, 184, 0.18); border-radius: 0.5rem;}
      [data-testid="stExpander"] {border-color: rgba(148, 163, 184, 0.25);}
      .business-note {color: #b7c3d2; font-size: 0.9rem;}
    </style>
    """, unsafe_allow_html=True)


def readable_method_name(name: str) -> str:
    return {"weighted_pipeline": "Weighted pipeline baseline", "conversion_model": "Conversion model"}.get(name, humanize_identifier(name))


def readable_scenario_assumptions(assumptions: dict) -> pd.DataFrame:
    """Map recorded scenario fields to business labels without mutating recorded values."""
    rows = (
        ("Scenario", assumptions.get("name", "Not available")),
        ("Conversion adjustment", signed_number(assumptions.get("conversion_log_odds_shift"), " log-odds")),
        ("Expected close-date shift", signed_number(assumptions.get("slippage_days_shift"), " days")),
        ("Expected booking fraction", percent(assumptions.get("booking_fraction"))),
        ("Activity effectiveness adjustment", signed_number(assumptions.get("activity_effectiveness_log_odds"), " log-odds")),
    )
    return pd.DataFrame(rows, columns=["Business assumption", "Applied value"])


def client() -> ForecastApiClient:
    return ForecastApiClient(st.session_state.get("api_url", os.getenv("FORECAST_API_URL", "http://127.0.0.1:8000")))


def require_run():
    run = st.session_state.get("forecast_run")
    if not run:
        st.info("Run a forecast from Executive Overview to populate this page.")
        return None
    return run


def load_details(run):
    try:
        return client().opportunities(run["forecast_id"]), client().exceptions(run["forecast_id"]), client().evaluation(run["forecast_id"])
    except ForecastApiError as error:
        st.error(str(error)); return [], [], {"status": "unavailable"}


def executive():
    st.title("Executive Overview")
    st.caption("Forecast calculations are performed by the FastAPI service. Actuals appear only when the service provides realized outcomes.")
    with st.sidebar:
        st.subheader("Connection")
        st.session_state.api_url = st.text_input("FastAPI URL", st.session_state.get("api_url", os.getenv("FORECAST_API_URL", "http://127.0.0.1:8000")))
        snapshot = st.text_input("Snapshot ID", value=st.session_state.get("snapshot_id", "FCST-2025-03-31-001"))
        scenario = st.selectbox("Scenario", ["BASE", "CONSERVATIVE", "OPTIMISTIC"])
        if st.button("Check API"):
            try: st.success(f"API is {client().health()['status']}")
            except ForecastApiError as error: st.error(str(error))
        if st.button("Run forecast", type="primary"):
            try:
                st.session_state.forecast_run = client().run_forecast({"snapshot_id": snapshot, "scenario": scenario, "reporting_currency": "USD", "dimensions": ["quarter", "territory_id"]})
                st.session_state.snapshot_id = snapshot
                st.success("Forecast run created.")
            except ForecastApiError as error: st.error(str(error))
    run = require_run()
    if not run: return
    currency = "USD"
    metadata = run.get("model_metadata", {})
    quota_scope = metadata.get("quota_scope", {})
    horizon_start, horizon_end = metadata.get("horizon_start"), metadata.get("horizon_end")
    st.caption(
        f"Snapshot as of **{metadata.get('snapshot_at', run.get('snapshot_date', 'Not available'))}** · "
        f"Forecast horizon **{horizon_start or 'Not available'} to {horizon_end or 'Not available'}** · "
        f"Reporting currency **{metadata.get('reporting_currency', currency)}**"
    )
    st.caption(
        f"Scope: {metadata.get('opportunity_count', 'Not available')} eligible open opportunities, "
        f"{len(quota_scope.get('eligible_reps', []))} reps, and {len(quota_scope.get('eligible_territories', []))} territories."
    )
    uncertainty = run["uncertainty"]
    cols = st.columns(5)
    cols[0].metric("Expected bookings", money(run["totals"].get("expected_booking_reporting"), currency), help="Probability-weighted expected bookings within the displayed forecast horizon.")
    cols[1].metric("Scoped quota", money(run["totals"].get("quota_reporting"), currency), help="Quarterly quota for the reps with eligible open pipeline in this snapshot.")
    cols[2].metric("Quota attainment", percent(run.get("quota_attainment")), help="Expected bookings divided by scoped quota.")
    cols[3].metric("Forecast range (P10–P90)", f"{money(uncertainty.get('p10'), currency)} – {money(uncertainty.get('p90'), currency)}", help="10th to 90th percentile of total simulated portfolio bookings.")
    cols[4].metric("Quota-miss probability", percent(uncertainty.get("probability_of_missing_quota")), help="Share of the same 500 aggregate portfolio simulations below scoped quota.")
    st.subheader("Forecast versus scoped quota")
    attainment = run.get("quota_attainment")
    if attainment is None:
        st.info("Scoped quota is not available for this run, so quota attainment is not calculated.")
    else:
        try:
            attainment_value = float(attainment)
            st.progress(min(max(attainment_value, 0.0), 1.0), text=f"Expected bookings cover {percent(attainment_value)} of scoped quota")
            if attainment_value > 1:
                st.caption(f"Expected bookings exceed scoped quota by {percent(attainment_value - 1)}. The indicator is capped visually at 100% but the KPI above preserves the exact attainment value.")
            else:
                st.caption("This attainment indicator avoids comparing unequal bars; all monetary values remain available in the KPIs above.")
        except (TypeError, ValueError):
            st.warning("Quota attainment was returned in an unreadable format; no visual indicator is shown.")
    st.subheader("Forecast uncertainty")
    p10, p50, p90 = st.columns(3)
    p10.metric("P10", money(uncertainty.get("p10"), currency), help="10th percentile of total bookings across 500 portfolio simulations.")
    p50.metric("P50", money(uncertainty.get("p50"), currency), help="Median total bookings across 500 portfolio simulations.")
    p90.metric("P90", money(uncertainty.get("p90"), currency), help="90th percentile of total bookings across 500 portfolio simulations.")
    st.caption("These are quantiles of aggregate simulated portfolio totals; they are not sums of opportunity or territory quantiles.")
    st.subheader("Scenario")
    st.write(f"Current scenario: **{run['scenario']}**. Use Scenario Planner to compare conservative, base, and optimistic assumptions.")
    _, _, evaluation = load_details(run)
    st.subheader("Historical forecast accuracy")
    if evaluation.get("status") == "not_available_for_live_run": st.info(evaluation.get("reason", "No evaluation is available for this run."))
    else: st.json(evaluation)


def pipeline():
    st.title("Pipeline Explorer")
    run = require_run()
    if not run: return
    rows, _, _ = load_details(run)
    if not rows: st.warning("No opportunity-level contributions were returned by the API."); return
    options = lambda name: sorted({str(row.get(name)) for row in rows if row.get(name) is not None})
    filters = st.columns(5)
    selected = [filters[i].multiselect(label, options(field)) for i, (label, field) in enumerate((("Quarter", "quarter"), ("Territory", "territory_id"), ("Rep", "owner_rep_id"), ("Stage", "stage_at_snapshot"), ("Product", "product_type")))]
    filtered = filter_opportunities(rows, *selected)
    contribution_total = sum(float(row.get("expected_booking_reporting", 0) or 0) for row in rows)
    forecast_total = float(run.get("totals", {}).get("expected_booking_reporting", 0) or 0)
    if abs(contribution_total - forecast_total) <= 1e-9:
        st.caption(f"All displayed opportunity contributions reconcile to the Executive Overview forecast: {money(forecast_total, run.get('model_metadata', {}).get('reporting_currency', 'USD'))}.")
    else:
        st.error("Opportunity contributions do not reconcile to the Executive Overview forecast; investigate the API payload before using this view.")
    currency = run.get("model_metadata", {}).get("reporting_currency", "USD")
    display = pd.DataFrame([opportunity_display_row(row, currency) for row in filtered])
    columns = ["opportunity_id", "stage_at_snapshot", "amount_reporting_currency", "expected_booking_reporting", "effective_stage_probability", "expected_close_date", "territory_id", "owner_rep_id", "product_type", "P10_booking_reporting", "P50_booking_reporting", "P90_booking_reporting"]
    opportunity_table = display.reindex(columns=columns).rename(columns={
        "opportunity_id": "Opportunity", "stage_at_snapshot": "Stage", "amount_reporting_currency": "Pipeline amount",
        "expected_booking_reporting": "Expected bookings", "effective_stage_probability": "Stage probability",
        "expected_close_date": "Expected close", "territory_id": "Territory", "owner_rep_id": "Sales representative",
        "product_type": "Product", "P10_booking_reporting": "P10", "P50_booking_reporting": "P50", "P90_booking_reporting": "P90",
    })
    st.dataframe(opportunity_table, width="stretch", hide_index=True, column_config={
        "Opportunity": st.column_config.TextColumn(width="medium"), "Stage": st.column_config.TextColumn(width="small"),
        "Pipeline amount": st.column_config.TextColumn(width="medium"), "Expected bookings": st.column_config.TextColumn(width="medium"),
        "Stage probability": st.column_config.TextColumn(width="small"), "Expected close": st.column_config.TextColumn(width="medium"),
        "Sales representative": st.column_config.TextColumn(width="medium"), "Product": st.column_config.TextColumn(width="medium"),
    })
    if filtered:
        selected_id = st.selectbox("Opportunity drill-down", [row["opportunity_id"] for row in filtered])
        detail = next(row for row in filtered if row["opportunity_id"] == selected_id)
        st.subheader("Opportunity summary")
        summary_left, summary_right = st.columns(2)
        for container, label, value in (
            (summary_left, "Stage at snapshot", detail.get("stage_at_snapshot")),
            (summary_left, "Expected close date", display_date(detail.get("expected_close_date"))),
            (summary_left, "Territory / representative", f"{detail.get('territory_id', 'Not available')} / {detail.get('owner_rep_id', 'Not available')}"),
            (summary_right, "Pipeline amount", money(detail.get("amount_reporting_currency"), currency)),
            (summary_right, "Stage probability", percent(detail.get("effective_stage_probability"))),
            (summary_right, "Expected contribution", money(detail.get("expected_booking_reporting"), currency)),
            (summary_right, "P10–P90 contribution", f"{money(detail.get('P10_booking_reporting'), currency)} – {money(detail.get('P90_booking_reporting'), currency)}"),
        ):
            render_labeled_value(container, label, value)
        try:
            history = client().opportunity_detail(run["forecast_id"], selected_id)
            left, right = st.columns(2)
            with left:
                st.subheader("Stage history as of snapshot")
                stage_history = pd.DataFrame(history["stage_history"])
                if stage_history.empty:
                    st.info("No stage history was available before this snapshot cutoff.")
                else:
                    stage_history["occurred_at"] = stage_history["occurred_at"].map(display_datetime)
                    stage_history = stage_history.reindex(columns=["occurred_at", "from_stage", "to_stage", "reason_code", "event_sequence"]).rename(columns={"occurred_at": "Occurred", "from_stage": "Previous stage", "to_stage": "New stage", "reason_code": "Reason", "event_sequence": "Sequence"})
                    st.dataframe(stage_history, width="stretch", hide_index=True, column_config={"Occurred": st.column_config.TextColumn(width="medium"), "Previous stage": st.column_config.TextColumn(width="medium"), "New stage": st.column_config.TextColumn(width="medium"), "Reason": st.column_config.TextColumn(width="medium")})
            with right:
                st.subheader("Sales activities as of snapshot")
                activities = pd.DataFrame(history["activities"])
                if activities.empty:
                    st.info("No sales activities were available before this snapshot cutoff.")
                else:
                    activities["occurred_at"] = activities["occurred_at"].map(display_datetime)
                    activities = activities.reindex(columns=["occurred_at", "activity_type", "outcome", "duration_minutes", "sales_rep_id"]).rename(columns={"occurred_at": "Occurred", "activity_type": "Activity", "outcome": "Outcome", "duration_minutes": "Duration (minutes)", "sales_rep_id": "Sales representative"})
                    st.dataframe(activities, width="stretch", hide_index=True, column_config={"Occurred": st.column_config.TextColumn(width="medium"), "Activity": st.column_config.TextColumn(width="medium"), "Outcome": st.column_config.TextColumn(width="large"), "Duration (minutes)": st.column_config.NumberColumn(format="%d", width="small")})
        except ForecastApiError as error: st.error(str(error))
        with st.expander("Technical opportunity details"):
            st.json(detail)


def risks():
    st.title("Risk and Exceptions")
    run = require_run()
    if not run: return
    _, exceptions, _ = load_details(run)
    if not exceptions: st.info("No exceptions returned for this forecast run."); return
    identifiers = [row.get("exception_id") for row in exceptions]
    if len(identifiers) == len(set(identifiers)):
        st.caption(f"All {len(identifiers)} returned exceptions have unique IDs.")
    else:
        st.error("Duplicate exception IDs were returned; do not treat these as independent findings.")
    values = lambda name: sorted({str(row.get(name)) for row in exceptions if row.get(name) is not None})
    filters = st.columns(5)
    selected = [
        filters[0].multiselect("Exception type", values("exception_type")),
        filters[1].multiselect("Severity", values("severity")),
        filters[2].multiselect("Representative", values("owner_rep_id")),
        filters[3].multiselect("Territory", values("territory_id")),
        filters[4].multiselect("Forecast run", values("forecast_run_id")),
    ]
    filtered = filter_exceptions(exceptions, *selected)
    st.caption(f"Showing {len(filtered)} of {len(exceptions)} exceptions. Business performance, opportunity risk, and data-quality findings are labelled separately.")
    currency = run.get("model_metadata", {}).get("reporting_currency", "USD")
    summary = pd.DataFrame([{
        "Category": humanize_identifier(item.get("exception_category")),
        "Severity": humanize_identifier(item.get("severity")),
        "Affected entity": item.get("affected_entity", "Not supplied"),
        "Record": item.get("entity_id", "Not supplied"),
        "Business impact": money(item.get("expected_business_impact_reporting"), currency),
        "Rule ID": item.get("detection_rule_or_model_version", "Not supplied"),
        "Suggested investigation": item.get("recommended_next_action", "Not supplied"),
    } for item in filtered])
    if not summary.empty:
        st.dataframe(summary, width="stretch", hide_index=True, column_config={
            "Category": st.column_config.TextColumn(width="medium"), "Severity": st.column_config.TextColumn(width="small"),
            "Affected entity": st.column_config.TextColumn(width="medium"), "Record": st.column_config.TextColumn(width="medium"),
            "Business impact": st.column_config.TextColumn(width="medium"), "Rule ID": st.column_config.TextColumn(width="medium"),
            "Suggested investigation": st.column_config.TextColumn(width="large"),
        })
    st.subheader("Exception evidence")
    for item in filtered:
        label = f"{item['severity']} · {item['exception_type']} · {item['entity_id']}"
        with st.expander(label):
            first, second, third = st.columns(3)
            render_labeled_value(first, "Affected entity", item.get("affected_entity", "Not supplied"))
            render_labeled_value(first, "Category", item.get("exception_category", "Not supplied"))
            render_labeled_value(second, "Business impact", money(item.get("expected_business_impact_reporting"), currency))
            render_labeled_value(second, "Status", item.get("resolution_status", "Not supplied"))
            render_labeled_value(third, "Rule / model", item.get("detection_rule_or_model_version", "Not supplied"))
            render_labeled_value(third, "Run", item.get("forecast_run_id", "Not supplied"))
            render_labeled_value(st, "Evidence", exception_evidence_summary(item, currency))
            render_labeled_value(st, "Suggested investigation", item.get("recommended_next_action", "Not supplied"))
            with st.expander("Technical details (JSON)"):
                st.json({key: item.get(key) for key in ("exception_id", "forecast_snapshot_id", "owner_rep_id", "territory_id", "created_at", "evidence", "resolution_history")})
    st.info("Resolution is read-only. A future status-update endpoint must require authentication, authorization, and an append-only resolution-history record; none is exposed by this service.")


def planner():
    st.title("Scenario Planner")
    run = require_run()
    if not run: return
    try: presets = client().scenario_presets()
    except ForecastApiError as error: st.error(str(error)); return
    presets = {**presets, "CUSTOM": {"name": "CUSTOM", "conversion_log_odds_shift": 0.0, "slippage_days_shift": 0, "booking_fraction": 1.0, "activity_effectiveness_log_odds": 0.0}}
    def apply_preset():
        selected = presets[st.session_state["planner_name"]]
        st.session_state["planner_conversion"] = selected["conversion_log_odds_shift"]
        st.session_state["planner_slippage"] = selected["slippage_days_shift"]
        st.session_state["planner_fraction"] = selected["booking_fraction"]
        st.session_state["planner_activity"] = selected["activity_effectiveness_log_odds"]
    if "planner_name" not in st.session_state:
        st.session_state["planner_name"] = "BASE"
    if any(key not in st.session_state for key in ("planner_conversion", "planner_slippage", "planner_fraction", "planner_activity")):
        apply_preset()
    name = st.selectbox("Scenario preset", list(presets), key="planner_name", on_change=apply_preset)
    if st.button("Reset values to selected preset"): apply_preset()
    a, b, c, d = st.columns(4)
    conversion = a.slider("Conversion adjustment (log-odds)", -2.0, 2.0, key="planner_conversion", step=.05, help="A recorded scenario assumption; it is not a percentage-point change in win rate.")
    slippage = b.slider("Expected close-date shift (days)", -90, 180, key="planner_slippage", help="Negative values bring expected close dates forward; positive values add delay.")
    fraction = c.slider("Expected booking fraction", .05, 1.0, key="planner_fraction", step=.05, help="Share of expected won value recognized as bookings in the selected horizon.")
    activity = d.slider("Activity effectiveness adjustment (log-odds)", -1.0, 1.0, key="planner_activity", step=.05, help="A recorded scenario assumption; it does not alter historical activities.")
    effective = {"name": name, "conversion_log_odds_shift": conversion, "slippage_days_shift": slippage, "booking_fraction": fraction, "activity_effectiveness_log_odds": activity}
    st.caption("Using the selected preset." if all(effective[key] == presets[name][key] for key in effective if key != "name") else "Using custom overrides of the selected preset. The applied values are recorded with the forecast run.")
    if st.button("Compare with current forecast", type="primary"):
        try:
            st.session_state.scenario_run = client().scenario(run["forecast_id"], effective)
            st.session_state.scenario_run_base_id = run["forecast_id"]
            st.session_state.scenario_run_controls = effective.copy()
        except ForecastApiError as error: st.error(str(error))
    comparison = st.session_state.get("scenario_run")
    stale = comparison is not None and (st.session_state.get("scenario_run_base_id") != run["forecast_id"] or st.session_state.get("scenario_run_controls") != effective)
    if stale: st.warning("Controls changed after this comparison was calculated. Click Compare with current forecast to refresh it.")
    currency = run.get("model_metadata", {}).get("reporting_currency", "USD")
    render_labeled_value(st, "Base forecast", money(run["totals"].get("expected_booking_reporting"), currency))
    if comparison and not stale:
        assumptions = comparison.get("scenario_assumptions")
        if assumptions is None:
            st.error("This API response does not include applied scenario assumptions; no assumptions are displayed.")
            return
        st.subheader("Base forecast versus adjusted scenario")
        raw_table = pd.DataFrame(scenario_comparison_rows(run, comparison))
        table = raw_table.copy()
        table["Base"] = table["Base"].map(lambda value: money(value, currency))
        table["Adjusted"] = table["Adjusted"].map(lambda value: money(value, currency))
        table["Change %"] = table["Change %"].map(scenario_percent_change)
        table = table.rename(columns={"Base": "Base value", "Adjusted": "Adjusted value", "Change %": "Relative change"})
        st.dataframe(table, width="stretch", hide_index=True)
        adjusted_expected = comparison.get("totals", {}).get("expected_booking_reporting")
        st.metric("Adjusted expected bookings", money(adjusted_expected, currency), delta=scenario_percent_change(raw_table.iloc[0]["Change %"]) if not raw_table.empty else "Not available")
        chart = raw_table.set_index("Metric")[["Base", "Adjusted"]]
        st.bar_chart(chart, width="stretch")
        st.subheader("Applied assumptions")
        st.dataframe(readable_scenario_assumptions(assumptions), width="stretch", hide_index=True)
        st.caption(f"Snapshot {comparison['snapshot_id']} · horizon {comparison.get('model_metadata',{}).get('horizon_start', 'Not available')} to {comparison.get('model_metadata',{}).get('horizon_end', 'Not available')} · {comparison.get('model_metadata',{}).get('reporting_currency', 'Not available')}")


def evaluation():
    st.title("Model Evaluation")
    run = require_run()
    if not run: return
    st.info("Live forecasts are not scored with future outcomes. Run the explicit historical backtest below to evaluate completed horizons only.")
    if st.button("Run historical backtest", type="primary"):
        try: st.session_state.historical_backtest = client().historical_backtest()
        except ForecastApiError as error: st.error(str(error))
    result = st.session_state.get("historical_backtest")
    if not result: return
    st.caption(f"Evaluated {result['evaluated_snapshots']} snapshots and {result['evaluated_opportunities']} opportunities through {display_date(result['observed_through'])}. Metrics aggregate at opportunity level across the evaluated periods.")
    if result.get("exploratory"): st.warning(result.get("note", "Results are exploratory."))
    summary = []
    for name, value in result["methods"].items():
        overall = value["overall"]
        summary.append({"Method": readable_method_name(name), "MAE": money(overall.get("mae")), "RMSE": money(overall.get("rmse")), "WAPE": percent(overall.get("wape")), "Bias": money(overall.get("forecast_bias")), "Interval coverage": percent(overall.get("interval_coverage"))})
    st.dataframe(pd.DataFrame(summary), width="stretch", hide_index=True, column_config={"Method": st.column_config.TextColumn(width="large"), "MAE": st.column_config.TextColumn(width="medium"), "RMSE": st.column_config.TextColumn(width="medium"), "WAPE": st.column_config.TextColumn(width="small"), "Bias": st.column_config.TextColumn(width="medium"), "Interval coverage": st.column_config.TextColumn(width="medium")})
    weighted = result["methods"].get("weighted_pipeline", {}).get("overall", {})
    conversion = result["methods"].get("conversion_model", {}).get("overall", {})
    if weighted.get("mae") is not None and conversion.get("mae") is not None:
        better = "weighted-pipeline baseline" if weighted["mae"] < conversion["mae"] else "conversion model" if conversion["mae"] < weighted["mae"] else "neither method (equal MAE)"
        st.info(f"By overall opportunity-level MAE, the {better} performs better. Bias is forecast minus actual: positive means over-forecasting; negative means under-forecasting.")
    periods = pd.DataFrame(result["periods"])
    st.subheader("Predicted versus actual revenue by completed period")
    if periods.empty:
        st.info("No completed historical periods were returned for charting.")
    else:
        chart_rows = periods.copy()
        chart_rows["Completed period"] = chart_rows["horizon_end"].map(display_date)
        chart_rows = chart_rows.set_index("Completed period")[["actual_booking_reporting", "weighted_pipeline_forecast", "conversion_model_forecast"]].rename(columns={"actual_booking_reporting": "Actual bookings", "weighted_pipeline_forecast": "Weighted pipeline baseline", "conversion_model_forecast": "Conversion model"})
        if len(chart_rows) == 1:
            st.bar_chart(chart_rows.T, width="stretch")
            st.caption("One eligible completed period is available; this comparison does not imply a time trend.")
        else:
            st.line_chart(chart_rows, width="stretch")
    with st.expander("Backtest technical details"):
        st.json({key: result.get(key) for key in ("data_context", "completed_snapshot_ids", "evaluation_eligibility", "evaluated_snapshot_ids", "training_snapshot_ids", "metric_definitions", "model_metadata")})


def audit():
    st.title("Audit and Traceability")
    run = require_run()
    if not run: return
    try:
        lineage = client().audit(run["forecast_id"])
    except ForecastApiError as error:
        st.error(f"Could not retrieve audit metadata: {error}")
        return
    st.caption("The snapshot timestamp is the historical data cutoff; the execution timestamp is when this forecast was calculated.")
    if lineage.get("status") != "complete":
        st.warning("This is a legacy forecast artifact with incomplete audit metadata. Missing values are shown explicitly and have not been inferred.")
    left, right = st.columns(2)
    with left:
        render_labeled_value(st, "Forecast run", run.get("forecast_id"))
        render_labeled_value(st, "Source snapshot", run.get("snapshot_id"))
        render_labeled_value(st, "Snapshot as-of", display_datetime(lineage.get("snapshot_at")))
        render_labeled_value(st, "Forecast executed", display_datetime(lineage.get("forecast_executed_at")))
        render_labeled_value(st, "Model version", lineage.get("model_version") or "Unavailable in this artifact")
    with right:
        render_labeled_value(st, "Feature version", lineage.get("feature_version") or "Unavailable in this artifact")
        render_labeled_value(st, "Random seed", lineage.get("seed") if lineage.get("seed") is not None else "Unavailable in this artifact")
        render_labeled_value(st, "Eligible opportunities", lineage.get("opportunity_count") if lineage.get("opportunity_count") is not None else "Unavailable in this artifact")
        render_labeled_value(st, "Input hash", lineage.get("input_hash") or "Unavailable in this artifact")
        render_labeled_value(st, "Output hash", lineage.get("output_hash") or "Unavailable in this artifact")
    st.subheader("Scenario assumptions")
    assumptions = lineage.get("scenario_assumptions")
    if assumptions is None:
        st.info("Scenario assumptions are unavailable in this legacy artifact.")
    else:
        st.dataframe(readable_scenario_assumptions(assumptions), width="stretch", hide_index=True)
    st.subheader("Reproducibility")
    st.caption("A verification replay uses the recorded snapshot, assumptions, model and seed in memory only. It never writes a forecast run or changes forecast history.")
    if st.button("Verify reproducibility", key="verify_reproducibility"):
        try:
            st.session_state.reproducibility = client().reproducibility(run["forecast_id"])
        except ForecastApiError as error:
            st.error(str(error))
    verification = st.session_state.get("reproducibility")
    if verification and verification.get("forecast_id") == run["forecast_id"]:
        if verification.get("status") == "reproducible":
            st.success("Replay matches the recorded inputs and outputs. No new forecast was saved.")
        elif verification.get("status", "").startswith("unsupported"):
            st.warning(verification.get("message", "This artifact cannot be replayed with the metadata available."))
        else:
            st.error("Replay did not match the recorded artifact. See technical details for individual checks.")
        if verification.get("checks"):
            checks = pd.DataFrame([verification["checks"]]).rename(columns={"input_hash": "Input hash matches", "output_hash": "Output hash matches", "scenario_assumptions": "Scenario assumptions match", "model_version": "Model version matches", "feature_version": "Feature version matches", "seed": "Seed matches", "snapshot": "Snapshot matches"})
            st.dataframe(checks, width="stretch", hide_index=True)
    _, exceptions, _ = load_details(run)
    render_labeled_value(st, "Data validation status", "Review required" if any(item.get("exception_type") == "MATERIAL_DATA_QUALITY" for item in exceptions) else "No material data-quality exception returned")
    with st.expander("Technical audit details (JSON)"):
        st.json({"audit": lineage, "run_response": run, "reproducibility": verification if verification and verification.get("forecast_id") == run["forecast_id"] else None})


apply_page_style()
st.sidebar.markdown("## BUSS")
st.sidebar.caption("Sales Forecasting & Pipeline Intelligence")
PAGES = {"Executive Overview": executive, "Pipeline Explorer": pipeline, "Risk and Exceptions": risks, "Scenario Planner": planner, "Model Evaluation": evaluation, "Audit and Traceability": audit}
PAGES[st.sidebar.radio("Page", list(PAGES))]()
