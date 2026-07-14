#!/usr/bin/env python3
from __future__ import annotations
import argparse, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from analysis.phase5_simulation import run_phase5_pipeline

def main()->int:
    p=argparse.ArgumentParser(description="Run independent-PHY Phase 5 synthetic simulation and export Phase 6 candidates")
    p.add_argument("--phy",type=Path,default=ROOT/"configs"/"dw3000_current_phy.yaml")
    p.add_argument("--sweep",type=Path,default=ROOT/"configs"/"phase5_2a2t_sweep.yaml")
    p.add_argument("--results-root",type=Path,default=ROOT/"results")
    a=p.parse_args(); out=run_phase5_pipeline(a.phy.resolve(),a.sweep.resolve(),a.results_root.resolve())
    print(f"Phase 5 synthetic simulation: PASS\nresults: {out}\nsource_type = SYNTHETIC\nhardware_verified = false")
    return 0
if __name__=="__main__": raise SystemExit(main())

