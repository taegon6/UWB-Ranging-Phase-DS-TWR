#!/usr/bin/env python3
"""Compare real Phase 6 records with predictions; never synthesizes measurements."""
from __future__ import annotations
import argparse,json,statistics
from pathlib import Path
def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("input",type=Path); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    data=json.loads(a.input.read_text(encoding="utf-8")); runs=data.get("measured_runs",[])
    if not runs: raise SystemExit("measured_runs is empty; fake measurements will not be generated")
    pred=data["predicted"]; periods=[float(r["superframe_period_us"]) for r in runs]
    measured=statistics.mean(periods); predicted=float(pred["superframe_period_us"])
    result={"candidate_id":data["candidate_id"],"source_type":"MEASURED","hardware_verified":bool(data.get("hardware_verified",False)),"repeat_count":len(runs),"measured_period_mean_us":measured,"measured_period_stdev_us":statistics.stdev(periods) if len(periods)>1 else 0.0,"model_error_percent":100*(measured-predicted)/predicted,"timeout_count":sum(r["timeout_count"] for r in runs),"late_tx_count":sum(r["late_tx_count"] for r in runs),"uart_drop_count":sum(r["uart_drop_count"] for r in runs)}
    a.output.write_text(json.dumps(result,indent=2),encoding="utf-8"); return 0
if __name__=="__main__": raise SystemExit(main())
