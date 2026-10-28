import json
from pathlib import Path

def _chart(rows):
    # Small dependency-free SVG: actual vs forecast median and P10/P90 when supplied.
    width,height=720,260; maximum=max([1]+[max(float(r["actual_booking_reporting"]),float(r.get("scenario_forecast",0))) for r in rows]); step=width/max(1,len(rows))
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="100%" height="100%" fill="white"/>']
    for i,r in enumerate(rows):
        x=20+i*step; scale=(height-40)/maximum; actual=height-20-float(r["actual_booking_reporting"])*scale; median=height-20-float(r.get("scenario_forecast",0))*scale
        parts.append(f'<line x1="{x}" y1="{actual}" x2="{x+step*.35}" y2="{actual}" stroke="#111" stroke-width="5"/><line x1="{x}" y1="{median}" x2="{x+step*.35}" y2="{median}" stroke="#2563eb" stroke-width="5"/>')
    return ''.join(parts)+"</svg>"

def write_evaluation_report(result, rows, output: Path):
    output.mkdir(parents=True,exist_ok=True); (output/"evaluation.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    lines=["# Forecast evaluation","",f"Data context: `{result['data_context']}`",""]
    for method,value in result["methods"].items():
        overall=value["overall"]; lines.extend([f"## {method}","",f"- MAE: {overall.get('mae')}",f"- WAPE: {overall.get('wape')} (null means actual total was zero/negligible)",f"- Bias: {overall.get('forecast_bias')}",f"- Brier: {overall.get('brier_score')}",f"- Interval coverage: {overall.get('interval_coverage')}",""])
    (output/"evaluation.md").write_text('\n'.join(lines),encoding="utf-8"); (output/"actual_vs_forecast.svg").write_text(_chart(rows),encoding="utf-8")
