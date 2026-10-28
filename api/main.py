"""Local FastAPI service; production should replace FileRunStore with PostgreSQL."""
from __future__ import annotations
import hashlib, json, os, uuid
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
from src.exceptions import detect_exceptions
from src.evaluation import run_historical_backtest
from src.features import build_feature_dataset
from src.forecasting.baseline import forecast_weighted_pipeline
from src.forecasting.uncertainty import SCENARIOS, ScenarioConfig, simulate_bookings
from src.validation.io import load_csv_dataset
from src.persistence.database import Database, store_forecast_run

VALID_DIMENSIONS={"quarter","territory_id","owner_rep_id","product_type"}
class RunRequest(BaseModel):
 snapshot_id:str=Field(pattern=r"^FCST-\d{4}-\d{2}-\d{2}-\d{3}$")
 scenario:Literal['CONSERVATIVE','BASE','OPTIMISTIC']='BASE'
 dimensions:list[str]=Field(default_factory=lambda:['quarter','territory_id'])
 seed:int=20261022
 reporting_currency:str='USD'
 @field_validator('reporting_currency')
 @classmethod
 def currency(cls,v):
  if len(v)!=3 or not v.isupper(): raise ValueError('reporting_currency must be uppercase ISO-like code')
  return v
 @field_validator('dimensions')
 @classmethod
 def dimensions_valid(cls,v):
  if not v or len(v)!=len(set(v)) or set(v)-VALID_DIMENSIONS: raise ValueError(f'dimensions must be unique from {sorted(VALID_DIMENSIONS)}')
  return v
class ScenarioRequest(BaseModel):
 name:Literal['CONSERVATIVE','BASE','OPTIMISTIC','CUSTOM']
 conversion_log_odds_shift:float|None=Field(None,ge=-2,le=2)
 slippage_days_shift:int|None=Field(None,ge=-90,le=180)
 booking_fraction:float|None=Field(None,gt=0,le=1)
 activity_effectiveness_log_odds:float|None=Field(None,ge=-1,le=1)
class RunResponse(BaseModel):
 forecast_id:str; snapshot_id:str; scenario:str; totals:dict; uncertainty:dict; quota_attainment:float|None; model_metadata:dict; exception_count:int; scenario_assumptions:dict|None=None
 # These fields are optional so artifacts written by earlier releases remain
 # retrievable.  New runs always populate them from the immutable run manifest.
 snapshot_date:str|None=None; forecast_executed_at:str|None=None
 model_version:str|None=None; feature_version:str|None=None; seed:int|None=None
 data_hash:str|None=None; output_hash:str|None=None; audit_metadata:dict|None=None
class ErrorResponse(BaseModel): detail:str

class FileRunStore:
 def __init__(self): self.path=Path(os.environ.get('API_RUNS_DIR','output/api-runs')); self.path.mkdir(parents=True,exist_ok=True)
 def save(self,run): (self.path/f"{run['forecast_id']}.json").write_text(json.dumps(run,default=str),encoding='utf8')
 def get(self,forecast_id):
  p=self.path/f'{forecast_id}.json'
  return json.loads(p.read_text(encoding='utf8')) if p.exists() else None
store=FileRunStore(); app=FastAPI(title='Sales Forecasting & Pipeline Intelligence API',version='1.0')
def _dataset(): return load_csv_dataset(Path(os.environ.get('FORECAST_DATASET_DIR','output/starter')))
def _resolve_scenario(request: ScenarioRequest) -> ScenarioConfig:
 """Apply a named preset first; explicitly supplied fields are auditable overrides."""
 if request.name == 'CUSTOM' and all(getattr(request, field) is None for field in ('conversion_log_odds_shift','slippage_days_shift','booking_fraction','activity_effectiveness_log_odds')):
  raise HTTPException(422, 'CUSTOM requires at least one explicit scenario assumption')
 values=asdict(SCENARIOS.get(request.name, ScenarioConfig('CUSTOM')))
 values.update(request.model_dump(exclude_none=True))
 return ScenarioConfig(**values)
def _stable_hash(value) -> str:
 """Hash serializable lineage inputs without relying on dictionary insertion order."""
 return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()
def _audit_metadata(run: dict) -> dict:
 """Describe only the fields recorded in this run artifact; never infer legacy data."""
 metadata=run.get('model_metadata') or {}
 fields={
  'snapshot_at':run.get('snapshot_date'), 'forecast_executed_at':run.get('forecast_executed_at'),
  'model_version':run.get('model_version'), 'feature_version':run.get('feature_version'),
  'seed':run.get('seed'), 'scenario_assumptions':run.get('scenario_assumptions'),
  'input_hash':run.get('data_hash'), 'output_hash':run.get('output_hash'),
  'opportunity_count':metadata.get('opportunity_count'),
 }
 required=('snapshot_at','model_version','feature_version','seed','scenario_assumptions','input_hash','output_hash','opportunity_count')
 missing=[name for name in required if fields[name] is None]
 return {**fields, 'status':'complete' if not missing else 'legacy_metadata_incomplete',
         'missing_fields':missing,
         'sources':{
          'snapshot_at':'forecast run manifest (snapshot cutoff)',
          'forecast_executed_at':'forecast run manifest (execution time)',
          'model_version':'forecast run manifest and PostgreSQL forecast_runs',
          'feature_version':'forecast run manifest and PostgreSQL forecast_runs',
          'seed':'forecast run manifest and PostgreSQL forecast_runs.assumptions',
          'scenario_assumptions':'forecast run manifest and PostgreSQL forecast_runs.assumptions',
          'input_hash':'forecast run manifest and PostgreSQL forecast_runs.data_hash',
          'output_hash':'forecast run manifest and PostgreSQL forecast_runs.assumptions',
          'opportunity_count':'forecast run manifest model metadata and PostgreSQL forecast_runs.assumptions',
         }}
def _with_audit_metadata(run: dict) -> dict:
 """Attach a status for legacy artifacts without manufacturing missing values."""
 enriched=dict(run)
 enriched['audit_metadata']=_audit_metadata(enriched)
 return enriched
def _scoped_quota_rows(data, header, feature_rows):
 quarter=f"{header['horizon_end'][:4]}Q{(int(header['horizon_end'][5:7])-1)//3+1}"
 reps={row['owner_rep_id'] for row in feature_rows}
 return [row for row in data.get('quotas',[]) if row.get('fiscal_quarter') == quarter and row.get('sales_rep_id') in reps]
def _scoped_quota_total(data, header, feature_rows):
 """Return quota for the same horizon, eligible reps, and currency as a run."""
 quarter=f"{header['horizon_end'][:4]}Q{(int(header['horizon_end'][5:7])-1)//3+1}"
 reps=sorted({row['owner_rep_id'] for row in feature_rows}); territories=sorted({row['territory_id'] for row in feature_rows})
 quota_rows=_scoped_quota_rows(data, header, feature_rows)
 invalid=sorted({row.get('currency') for row in quota_rows if row.get('currency') != header['reporting_currency']})
 if invalid: raise HTTPException(422, f"Quota currencies {invalid} do not match reporting currency {header['reporting_currency']}")
 return sum(float(row['quota_amount']) for row in quota_rows), {'fiscal_quarter':quarter,'eligible_reps':reps,'eligible_territories':territories,'quota_currency':header['reporting_currency']}
def _persist_forecast_run(run,data):
 """Persist immutable run lineage and opportunity intervals before exposing a run."""
 snapshot_day=run['snapshot_date'][:10]
 versions=[row['version_name'] for row in data.get('stage_probability_versions',[])
           if row.get('scenario') == 'BASE' and row['effective_from'] <= snapshot_day
           and (not row.get('effective_to') or row['effective_to'] >= snapshot_day)]
 metadata={'model_version':run['model_version'],'feature_version':run['feature_version'],
           'scenario':run['scenario'],'stage_probability_version_name':sorted(set(versions))[0] if versions else 'unknown',
           'data_hash':run['data_hash'],
           'assumptions':{'scenario_assumptions':run['scenario_assumptions'], 'seed':run['seed'],
                          'snapshot_at':run['snapshot_date'], 'forecast_executed_at':run['forecast_executed_at'],
                          'opportunity_count':run['model_metadata']['opportunity_count'],
                          'output_hash':run['output_hash'],
                          'aggregation_dimensions':run['model_metadata']['aggregation_dimensions']}}
 forecasts=[]
 for row in run['opportunities']:
  expected=float(row['expected_booking_reporting']); low=float(row['P10_booking_reporting']); high=float(row['P90_booking_reporting'])
  forecasts.append({'forecast_run_id':run['forecast_id'],'opportunity_id':row['opportunity_id'],
                    'expected_booking_reporting':expected,'lower_booking_reporting':min(low,expected),
                    'upper_booking_reporting':max(high,expected),'win_probability':row['joint_booking_within_horizon_probability']})
 store_forecast_run(Database(),run['forecast_id'],run['snapshot_id'],metadata,forecasts)
def _run(req,scenario=None):
 data=_dataset(); header=next((x for x in data.get('forecast_snapshots',[]) if x['forecast_snapshot_id']==req.snapshot_id),None)
 if not header: raise HTTPException(404,'Unknown forecast snapshot')
 if header['reporting_currency']!=req.reporting_currency: raise HTTPException(422,'Requested reporting currency differs from snapshot currency')
 rows=[r for r in build_feature_dataset(data) if r['forecast_snapshot_id']==req.snapshot_id]
 baseline=forecast_weighted_pipeline(rows,group_by=tuple(req.dimensions)); predictions=[{'forecast_snapshot_id':r['forecast_snapshot_id'],'opportunity_id':r['opportunity_id'],'conversion_probability':float(next(x for x in baseline['contributions'] if x['opportunity_id']==r['opportunity_id'])['forecast_bookings_future_horizon_reporting'])/max(float(r['amount_reporting_currency']),1e-12)} for r in rows]
 simulation=simulate_bookings(rows,predictions,scenario or SCENARIOS[req.scenario],simulations=500,seed=req.seed,group_by=tuple(req.dimensions)); forecast_id=str(uuid.uuid4()); quota_rows=_scoped_quota_rows(data, header, rows); exceptions=detect_exceptions(rows,simulation['contributions'],quota_rows,context={'forecast_run_id':forecast_id,'forecast_snapshot_id':req.snapshot_id,'scenario':(scenario or SCENARIOS[req.scenario]).name})
 # The dashboard consumes this API projection rather than reconstructing features
 # from source CSVs.  It contains only information known at the snapshot cutoff.
 feature_by_key={(r['forecast_snapshot_id'],r['opportunity_id']):r for r in rows}
 opportunity_details=[]
 for contribution in simulation['contributions']:
  feature=feature_by_key[(contribution['forecast_snapshot_id'],contribution['opportunity_id'])]
  opportunity_details.append({**contribution, **{key:feature.get(key) for key in ('stage_at_snapshot','effective_stage_probability','expected_close_date','amount_reporting_currency','product_type','territory_id','owner_rep_id','feature_cutoff_at','prior_close_date_change_count','observed_slippage_days')}})
  expected=sum(row['expected_booking_reporting'] for row in simulation['contributions']); quota, quota_scope=_scoped_quota_total(data, header, rows); portfolio=simulation['portfolio']
  probability_of_missing_quota=(sum(value < quota for value in simulation['portfolio_draws'])/len(simulation['portfolio_draws'])) if quota else None
  result={'forecast_id':forecast_id,'snapshot_id':req.snapshot_id,'scenario':(scenario or SCENARIOS[req.scenario]).name,'snapshot_date':header['snapshot_at'],'forecast_executed_at':datetime.now(timezone.utc).isoformat(),'feature_version':'pit-sales-features-v1','model_version':'weighted-pipeline-v1','seed':req.seed,'scenario_assumptions':asdict(scenario or SCENARIOS[req.scenario]),'totals':{'expected_booking_reporting':expected,'quota_reporting':quota},'uncertainty':{'p10':portfolio['P10_booking_reporting'],'p50':portfolio['P50_booking_reporting'],'p90':portfolio['P90_booking_reporting'],'probability_of_missing_quota':probability_of_missing_quota},'quota_attainment':expected/quota if quota else None,'model_metadata':{'method':'weighted-pipeline-v1','feature_version':'pit-sales-features-v1','seed':req.seed,'snapshot_at':header['snapshot_at'],'horizon_start':header['horizon_start'],'horizon_end':header['horizon_end'],'reporting_currency':header['reporting_currency'],'aggregation_dimensions':req.dimensions,'opportunity_count':len(rows),'quota_scope':quota_scope,'metric_definitions':{'forecast_mean':'Probability-weighted expected bookings within the forecast horizon.','uncertainty':'P10, P50, P90, and probability of missing the scoped quota from the same 500 aggregate portfolio simulations.','quota':'Quarterly quota for reps with eligible open pipeline at this snapshot.'}},'exception_count':len(exceptions),'opportunities':opportunity_details,'exceptions':exceptions,'evaluation':{'status':'not_available_for_live_run','reason':'No realized-outcome evaluation is attached to this live forecast run. Historical backtests must be requested separately.'}}
 result['data_hash']=_stable_hash({'snapshot_id':result['snapshot_id'],'opportunities':result['opportunities']})
 result['output_hash']=_stable_hash({'snapshot_id':result['snapshot_id'],'scenario':result['scenario'],'totals':result['totals'],'uncertainty':result['uncertainty'],'opportunities':result['opportunities']})
 return _with_audit_metadata(result)
@app.get('/health')
def health():
 try:
  with Database().connect() as connection:
   with connection.cursor() as cursor: cursor.execute('SELECT 1'); cursor.fetchone()
 except Exception as error:
  raise HTTPException(503, f'Database is not ready: {error}') from error
 return {'status':'ok','time':datetime.now(timezone.utc).isoformat(),'database':'ready'}
@app.post('/forecasts/run',response_model=RunResponse,status_code=201,responses={404:{'model':ErrorResponse},422:{'model':ErrorResponse}})
def run(req:RunRequest):
 result=_run(req); _persist_forecast_run(result,_dataset()); store.save(result); return {k:result[k] for k in RunResponse.model_fields}
def _get(fid):
 r=store.get(fid)
 if not r: raise HTTPException(404,'Forecast not found')
 return _with_audit_metadata(r)
@app.get('/forecasts/{forecast_id}',response_model=RunResponse)
def get_run(forecast_id:str): r=_get(forecast_id); return {k:r[k] for k in RunResponse.model_fields}
@app.get('/forecasts/{forecast_id}/audit')
def audit(forecast_id:str):
 """Return the immutable artifact's lineage statement, including legacy gaps."""
 return _get(forecast_id)['audit_metadata']
@app.post('/forecasts/{forecast_id}/reproducibility')
def reproducibility(forecast_id:str):
 """Recalculate in memory only; no run artifact or database history is written."""
 original=_get(forecast_id); audit=_audit_metadata(original)
 required=('snapshot_at','model_version','feature_version','seed','scenario_assumptions','input_hash','output_hash','opportunity_count')
 missing=[field for field in required if audit.get(field) is None]
 if missing:
  return {'status':'unsupported_for_legacy_artifact','forecast_id':forecast_id,'missing_fields':missing,
          'message':'The stored artifact lacks required reproducibility metadata; no values were inferred.'}
 if original['model_version'] != 'weighted-pipeline-v1' or original['feature_version'] != 'pit-sales-features-v1':
  return {'status':'unsupported_model_version','forecast_id':forecast_id,'model_version':original['model_version'],'feature_version':original['feature_version']}
 metadata=original.get('model_metadata') or {}
 request=RunRequest(snapshot_id=original['snapshot_id'],scenario=original['scenario'],seed=original['seed'],
                    reporting_currency=metadata.get('reporting_currency','USD'),dimensions=metadata.get('aggregation_dimensions',['quarter','territory_id']))
 replay=_run(request,ScenarioConfig(**original['scenario_assumptions']))
 checks={name:original.get(name)==replay.get(name) for name in ('snapshot_id','model_version','feature_version','seed','scenario_assumptions','data_hash','output_hash')}
 return {'status':'reproducible' if all(checks.values()) else 'mismatch','forecast_id':forecast_id,
         'replay_forecast_id':replay['forecast_id'],'checks':checks,
         'original':_audit_metadata(original),'replay':_audit_metadata(replay),
         'message':'Replay was computed in memory and was not persisted.'}
@app.get('/forecasts/{forecast_id}/opportunities')
def opportunities(forecast_id:str): return _get(forecast_id)['opportunities']
@app.get('/forecasts/{forecast_id}/opportunities/{opportunity_id}')
def opportunity_detail(forecast_id:str,opportunity_id:str):
 r=_get(forecast_id); cutoff=datetime.fromisoformat(r['snapshot_date'].replace('Z','+00:00'))
 data=_dataset()
 if not any(x['opportunity_id']==opportunity_id for x in r['opportunities']): raise HTTPException(404,'Opportunity is not part of this forecast run')
 # Never disclose events that occurred after the run's snapshot cutoff.
 event_at=lambda value: datetime.fromisoformat(str(value).replace('Z','+00:00'))
 return {'forecast_id':forecast_id,'opportunity_id':opportunity_id,'stage_history':[x for x in data.get('stage_history',[]) if x['opportunity_id']==opportunity_id and event_at(x['occurred_at'])<=cutoff],'activities':[x for x in data.get('activities',[]) if x['opportunity_id']==opportunity_id and event_at(x['occurred_at'])<=cutoff]}
@app.get('/forecasts/{forecast_id}/exceptions')
def exceptions(forecast_id:str): return _get(forecast_id)['exceptions']
@app.get('/scenario-presets')
def scenario_presets(): return {name:asdict(config) for name,config in SCENARIOS.items()}
@app.post('/evaluations/backtest')
def historical_backtest():
 try: return run_historical_backtest(_dataset())
 except Exception as error:
  raise HTTPException(422, f"Historical backtest could not be completed: {error}") from error
@app.post('/forecasts/{forecast_id}/scenarios',response_model=RunResponse,status_code=201)
def scenario(forecast_id:str,req:ScenarioRequest):
 original=_get(forecast_id); dimensions=original.get('model_metadata',{}).get('aggregation_dimensions',['quarter','territory_id']); request=RunRequest(snapshot_id=original['snapshot_id'],scenario=original['scenario'] if original['scenario'] in SCENARIOS else 'BASE',seed=original['seed'],reporting_currency=original.get('model_metadata',{}).get('reporting_currency','USD'),dimensions=dimensions)
 result=_run(request,_resolve_scenario(req)); _persist_forecast_run(result,_dataset()); store.save(result); return {k:result[k] for k in RunResponse.model_fields}
@app.get('/forecasts/{forecast_id}/evaluation')
def evaluation(forecast_id:str): return _get(forecast_id)['evaluation']
