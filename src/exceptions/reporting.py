import json
from pathlib import Path
from .engine import apply_permitted_corrections
def write_exception_report(exceptions, forecasts, output:Path):
 output.mkdir(parents=True,exist_ok=True); correction=apply_permitted_corrections(forecasts,exceptions); payload={"exceptions":exceptions,"forecast_correction_what_if":correction}; (output/'exceptions.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
 lines=['# Business exceptions','',f"Permitted-correction forecast change: {correction['permitted_correction_change_reporting']}",'','| Severity | Type | Entity | Impact | Action |','|---|---|---|---:|---|']
 lines += [f"| {e['severity']} | {e['exception_type']} | {e['entity_id']} | {e['expected_business_impact_reporting']} | {e['recommended_next_action']} |" for e in exceptions]
 (output/'exceptions.md').write_text('\n'.join(lines)+'\n',encoding='utf-8'); return payload
