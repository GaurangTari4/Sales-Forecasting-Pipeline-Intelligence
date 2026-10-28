"""Metrics for forecasts whose predictions were created before their label period."""
from __future__ import annotations
from collections import defaultdict
import math


def _safe_wape(errors, actuals, epsilon=1e-9):
    denominator = sum(abs(x) for x in actuals)
    return None if denominator <= epsilon else sum(abs(x) for x in errors) / denominator


def _bands(probabilities, actuals):
    result=[]
    for i in range(5):
        lo, hi=i/5,(i+1)/5; idx=[j for j,p in enumerate(probabilities) if lo <= p < hi or (i==4 and p==1)]
        result.append({"lower":lo,"upper":hi,"count":len(idx),"mean_probability":sum(probabilities[j] for j in idx)/len(idx) if idx else None,"observed_rate":sum(actuals[j] for j in idx)/len(idx) if idx else None})
    return result


def _metric(rows):
    actual=[float(r["actual_booking_reporting"]) for r in rows]; forecast=[float(r["forecast_booking_reporting"]) for r in rows]
    errors=[f-a for f,a in zip(forecast,actual)]
    out={"records":len(rows),"mae":sum(abs(x) for x in errors)/len(rows) if rows else None,"rmse":math.sqrt(sum(x*x for x in errors)/len(rows)) if rows else None,"wape":_safe_wape(errors,actual),"forecast_bias":sum(errors)/len(rows) if rows else None,"actual_total":sum(actual),"forecast_total":sum(forecast)}
    probabilities=[r.get("win_probability") for r in rows]
    binary=[r.get("actual_win") for r in rows]
    if rows and all(x is not None for x in probabilities) and all(x is not None for x in binary):
        p=[float(x) for x in probabilities]; y=[int(x) for x in binary]; eps=1e-12
        out.update({"brier_score":sum((x-z)**2 for x,z in zip(p,y))/len(y),"log_loss":-sum(z*math.log(max(eps,x))+(1-z)*math.log(max(eps,1-x)) for x,z in zip(p,y))/len(y),"calibration":_bands(p,y)})
    interval=[r.get("p10_booking_reporting") is not None and r.get("p90_booking_reporting") is not None for r in rows]
    if rows and all(interval):
        out.update({"interval_coverage":sum(float(r["p10_booking_reporting"])<=float(r["actual_booking_reporting"])<=float(r["p90_booking_reporting"]) for r in rows)/len(rows),"mean_interval_width":sum(float(r["p90_booking_reporting"])-float(r["p10_booking_reporting"]) for r in rows)/len(rows)})
    return out


def evaluate_forecasts(rows, methods=("weighted_pipeline","conversion_model","timing_adjusted","scenario")):
    """Evaluate precomputed historical forecasts; never fits a model or accesses training data.

    Each input row carries actual booking/win labels and optional method fields:
    ``<method>_forecast``, ``<method>_probability``, and scenario P10/P90 fields.
    """
    output={"data_context":"held_out_simulated_outcomes" if any(r.get("held_out") for r in rows) else "synthetic_test_cases","methods":{}}
    dimensions={"forecast_horizon":"label_horizon_end","quarter":"quarter","territory":"territory_id","sales_stage":"stage_at_snapshot","rep_segment":"rep_segment","deal_size_band":"deal_size_band"}
    for method in methods:
        method_rows=[]
        for r in rows:
            field=f"{method}_forecast"
            if field not in r: continue
            method_rows.append({"actual_booking_reporting":r["actual_booking_reporting"],"forecast_booking_reporting":r[field],"actual_win":r.get("actual_win"),"win_probability":r.get(f"{method}_probability"),"p10_booking_reporting":r.get(f"{method}_p10"),"p90_booking_reporting":r.get(f"{method}_p90"),**r})
        breakdown={}
        for title,column in dimensions.items():
            grouped=defaultdict(list)
            for r in method_rows: grouped[str(r.get(column,"<UNKNOWN>"))].append(r)
            breakdown[title]={key:_metric(value) for key,value in sorted(grouped.items())}
        output["methods"][method]={"overall":_metric(method_rows),"breakdowns":breakdown}
    return output


def evaluate_anomalies(detected, ground_truth):
    key=lambda x:(x["issue_type"],x["affected_record_id"],x.get("detection_rule_id"))
    found={key(x) for x in detected}; truth={key(x) for x in ground_truth}; tp=len(found&truth); fp=len(found-truth); fn=len(truth-found)
    precision=tp/(tp+fp) if tp+fp else 0.; recall=tp/(tp+fn) if tp+fn else 0.
    return {"true_positives":tp,"false_positives":fp,"false_negatives":fn,"precision":precision,"recall":recall,"f1":2*precision*recall/(precision+recall) if precision+recall else 0.}
