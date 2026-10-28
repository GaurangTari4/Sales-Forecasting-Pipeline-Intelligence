from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
import hashlib

OPEN={"PROSPECTING","QUALIFICATION","DISCOVERY","PROPOSAL","NEGOTIATION"}

def _id(kind, entity, context=None): return "EXC-"+kind+"-"+hashlib.sha1(f"{kind}:{entity}:{context or ''}".encode()).hexdigest()[:10].upper()
def _severity(impact, urgent=False): return "CRITICAL" if impact>=100000 else "HIGH" if impact>=50000 or urgent else "MEDIUM" if impact>=10000 else "LOW"
def _quota_gap_severity(quota, forecast):
 """Escalate material low-coverage gaps; a positive gap alone is not critical."""
 quota, forecast=float(quota), float(forecast); gap=max(0,quota-forecast); attainment=forecast/quota if quota else 1
 if gap>=100000 and forecast<=0: return "CRITICAL"
 if gap>=100000 and attainment<=.10: return "HIGH"
 if gap>=50000 and attainment<=.40: return "HIGH"
 if gap>=10000 and attainment<=.75: return "MEDIUM"
 return "LOW"
def _new(kind, entity, evidence, impact, action, rule, now, context=None, severity=None, category="BUSINESS_PERFORMANCE", affected_entity="OPPORTUNITY", owner_rep_id=None, territory_id=None):
 return {"exception_id":_id(kind,entity,context),"entity_id":entity,"affected_entity":affected_entity,"exception_type":kind,"exception_category":category,"severity":severity or _severity(float(impact), evidence.get("urgent",False)),"evidence":evidence,"detection_rule_or_model_version":rule,"expected_business_impact_reporting":str(Decimal(str(impact)).quantize(Decimal('.01'))),"recommended_next_action":action,"created_at":now,"resolution_status":"OPEN","resolution_history":[],"forecast_run_id":context.get("forecast_run_id") if context else None,"forecast_snapshot_id":context.get("forecast_snapshot_id") if context else None,"owner_rep_id":owner_rep_id,"territory_id":territory_id}

def detect_exceptions(feature_rows, forecast_contributions, quotas=(), validation_results=(), now=None, context=None):
 """Detect from visible business data only; hidden truth is intentionally not accepted."""
 now=now or datetime.now(timezone.utc).isoformat(); forecast={(x["forecast_snapshot_id"],x["opportunity_id"]):x for x in forecast_contributions}; out=[]
 for r in feature_rows:
  key=(r["forecast_snapshot_id"],r["opportunity_id"]); f=forecast.get(key,{}); value=float(f.get("expected_booking_reporting",f.get("forecast_bookings_future_horizon_reporting",0)))
  age=int(r.get("opportunity_age_days",0)); stage_days=int(r.get("current_stage_duration_days",0)); close=int(r.get("days_until_expected_close",999));
  details={"context":context,"owner_rep_id":r.get("owner_rep_id"),"territory_id":r.get("territory_id")}
  if r.get("stage_at_snapshot") in OPEN and age>=180: out.append(_new("STALE_OPPORTUNITY",r["opportunity_id"],{"opportunity_age_days":age,"stage":r.get("stage_at_snapshot")},value,"Review deal qualification and next customer commitment.","RULE.STALE_AGE_V1",now,category="OPPORTUNITY_RISK",**details))
  if r.get("stage_at_snapshot") in OPEN and close<=14: out.append(_new("CLOSE_DATE_AT_RISK",r["opportunity_id"],{"days_until_expected_close":close,"prior_close_date_changes":r.get("prior_close_date_change_count",0),"urgent":close<=0},value,"Confirm close plan and update date only with customer evidence.","RULE.CLOSE_RISK_V1",now,category="OPPORTUNITY_RISK",**details))
  if r.get("stage_at_snapshot") in OPEN and stage_days>=90: out.append(_new("STAGE_DURATION_ANOMALY",r["opportunity_id"],{"current_stage_duration_days":stage_days,"stage":r.get("stage_at_snapshot")},value,"Validate stage criteria and identify the blocking next step.","RULE.STAGE_DURATION_V1",now,category="OPPORTUNITY_RISK",**details))
 reps={}
 for r in feature_rows:
  if r.get("stage_at_snapshot") in OPEN: reps.setdefault(r.get("owner_rep_id"),0); reps[r.get("owner_rep_id")]+=float(forecast.get((r["forecast_snapshot_id"],r["opportunity_id"]),{}).get("expected_booking_reporting",0))
 for rep,value in reps.items():
  sample=next(r for r in feature_rows if r.get("owner_rep_id")==rep)
  if any(r.get("owner_rep_id")==rep and r.get("rep_active") is False for r in feature_rows) and value>=10000: out.append(_new("INACTIVE_REP_MATERIAL_PIPELINE",rep,{"open_pipeline_expected_booking":value},value,"Reassign ownership under the documented coverage policy.","RULE.INACTIVE_REP_V1",now,context,category="BUSINESS_PERFORMANCE",affected_entity="SALES_REP",owner_rep_id=rep,territory_id=sample.get("territory_id")))
 for q in quotas:
  forecast_total=sum(float(x.get("expected_booking_reporting",x.get("forecast_bookings_future_horizon_reporting",0))) for x in forecast_contributions if x.get("owner_rep_id")==q.get("sales_rep_id"))
  gap=max(0,float(q["quota_amount"])-forecast_total)
  if gap>0:
   rep=q["sales_rep_id"]; sample=next((r for r in feature_rows if r.get("owner_rep_id")==rep),{})
   out.append(_new("FORECAST_GAP_TO_QUOTA",rep,{"quota":q["quota_amount"],"forecast":forecast_total,"gap":gap,"attainment":forecast_total/float(q["quota_amount"]) if float(q["quota_amount"]) else None,"fiscal_quarter":q.get("fiscal_quarter"),"currency":q.get("currency")},gap,"Review coverage and pipeline creation; do not alter forecast without evidence.","RULE.QUOTA_GAP_V2",now,context,severity=_quota_gap_severity(q["quota_amount"],forecast_total),category="BUSINESS_PERFORMANCE",affected_entity="SALES_REP",owner_rep_id=rep,territory_id=sample.get("territory_id")))
 by_group={}
 for x in forecast_contributions: by_group.setdefault((x.get("forecast_snapshot_id"),x.get("territory_id")),[]).append(x)
 for group,items in by_group.items():
  total=sum(float(x.get("expected_booking_reporting",0)) for x in items); top=sum(sorted((float(x.get("expected_booking_reporting",0)) for x in items),reverse=True)[:3])
  if total and top/total>=.65: out.append(_new("FORECAST_CONCENTRATION",":".join(str(x) for x in group),{"top_three_share":top/total,"total_forecast":total,"top_three_forecast":top},top,"Review downside plans for the concentrated deals.","RULE.CONCENTRATION_V1",now,context,category="BUSINESS_PERFORMANCE",affected_entity="FORECAST_AGGREGATE",territory_id=group[1]))
 for issue in validation_results:
  if issue.get("severity") in {"ERROR","CRITICAL"}:
   impact=float(issue.get("forecast_impact_reporting",0)); out.append(_new("MATERIAL_DATA_QUALITY",issue.get("affected_record_id","UNKNOWN"),{"rule_id":issue.get("rule_id"),"issue_type":issue.get("issue_type"),"urgent":True},impact,"Quarantine or correct through an auditable transformation before using this forecast.",issue.get("rule_id","VALIDATION"),now,context,category="DATA_QUALITY",affected_entity=issue.get("affected_entity","DATA_QUALITY")))
 return sorted(out,key=lambda x:({"CRITICAL":4,"HIGH":3,"MEDIUM":2,"LOW":1}[x["severity"]],float(x["expected_business_impact_reporting"])),reverse=True)

def apply_permitted_corrections(forecast_contributions, exceptions):
 """What-if only: applies explicit corrected values, never an inferred intervention."""
 before=sum(Decimal(str(x.get("expected_booking_reporting",x.get("forecast_bookings_future_horizon_reporting",0)))) for x in forecast_contributions); delta=Decimal('0'); changes=[]
 for e in exceptions:
  ev=e.get("evidence",{})
  if "current_expected_booking_reporting" in ev and "corrected_expected_booking_reporting" in ev:
   change=Decimal(str(ev["corrected_expected_booking_reporting"]))-Decimal(str(ev["current_expected_booking_reporting"])); delta+=change; changes.append({"exception_id":e["exception_id"],"forecast_change_reporting":str(change)})
 return {"forecast_before_reporting":str(before),"permitted_correction_change_reporting":str(delta),"forecast_after_reporting":str(before+delta),"applied_corrections":changes}
