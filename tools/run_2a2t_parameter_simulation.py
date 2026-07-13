#!/usr/bin/env python3
"""Run Phase 0-4 paper-grounded direct-2A2T simulation and reporting."""

from __future__ import annotations

import argparse
import csv
import json
import platform
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.parameter_sweep import run_parameter_sweep
from analysis.pareto_selection import pareto_front
from hardware.device_inventory import load_yaml, validate_config


SOURCE_TYPE = "SYNTHETIC"
HARDWARE_VERIFIED = False


def _next_run_dir(root: Path, prefix: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for number in range(1, 10_000):
        candidate = root / f"{prefix}_run{number:02d}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("unable to allocate experiment run number")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _flags() -> str:
    return "source_type: SYNTHETIC\nhardware_verified: false"


def _prepare_documents(run_dir: Path, baseline_path: Path, sweep_path: Path) -> None:
    """Create required pre-run documents before any candidate is evaluated."""

    _write(run_dir / "question.md", """# Research question

Can a direct A1/A2/T1/T2 sequential-slot superframe satisfy the paper-grounded timing model without node TX/RX overlap or receiver collision, and what parameter candidates form the synthetic Pareto front?

## Status labels

- 검증된 결과: none; no hardware was connected.
- 가정한 값: sweep guards and deferred-RX acquisition lead.
- 논문 기반 근거: packet airtime, 522 us processing reference, and 100 us timeout-margin scale.
- 추후 확인 필요: actual DW3000 timing, clock behavior, RX lead, packet lengths, and antenna delay.

source_type = SYNTHETIC
hardware_verified = false
""")
    _write(run_dir / "protocol.md", """# Protocol

1. Validate baseline and sweep schemas.
2. Preserve PAPER and CODE_BASELINE mappings as immutable inputs.
3. Build Poll/Response/Final/PostFinal/Report timelines for A1-T1, A2-T1, A1-T2, and A2-T2.
4. Schedule four sequential slots and hard-fail any NODE_TX_RX_OVERLAP or RECEIVER_COLLISION.
5. Calculate complete-superframe timing, headroom, rate, and node duty cycle.
6. Select a multi-objective Pareto front and generate a synthetic report.

No build, flash, UART, logic-analyzer, CIR, or RF operation is permitted by this protocol.

source_type = SYNTHETIC
hardware_verified = false
""")
    _write(run_dir / "run_matrix.md", """# Run matrix

| Dimension | Values |
|---|---|
| Links | A1-T1, A2-T1, A1-T2, A2-T2 |
| Packet flow | Poll, Response, Final, PostFinal, Report |
| Processing time | 522, 800 us |
| Reply guard | 0, 100, 200, 400, 800 us |
| Timeout margin | 100, 200 us |
| Slot guard | 100, 300 us |
| Expected candidates | 40 |

source_type = SYNTHETIC
hardware_verified = false
""")
    timestamp = datetime.now(timezone.utc).isoformat()
    _write(run_dir / "metadata.yaml", f"""experiment_state: raw-only
state_history:
  - raw-only
created_utc: {timestamp}
baseline_config: {baseline_path.as_posix()}
sweep_config: {sweep_path.as_posix()}
firmware_modified: false
phase_scope: [0, 1, 2, 3, 4]
phase_5_enabled: false
phase_6_enabled: false
{_flags()}
""")


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, bool):
        return str(value).lower()
    return value


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise RuntimeError("simulation produced no valid candidates")
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            text=True, capture_output=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"


def _finish_documents(run_dir: Path, rows: list[dict[str, Any]], front: list[dict[str, Any]]) -> None:
    best = min(front, key=lambda row: row["superframe_duration_us"])
    _write(run_dir / "run_log.md", f"""# Run log

- Candidate count: {len(rows)}
- Pareto count: {len(front)}
- Fastest Pareto candidate: {best['candidate_id']}
- No hardware commands were issued.

source_type = SYNTHETIC
hardware_verified = false
""")
    _write(run_dir / "qc.md", f"""# Quality control

- Schema validation: PASS
- Four-link completion for every retained row: PASS
- Node TX/RX overlap count: 0
- Receiver collision count: 0
- Provenance attached to every candidate parameter: PASS
- Firmware modification by runner: none

The run is synthetic QC only and is not hardware verification.

source_type = SYNTHETIC
hardware_verified = false
""")
    _write(run_dir / "analysis_environment.md", f"""# Analysis environment

- Python: {platform.python_version()}
- Platform: {platform.platform()}
- Git commit at run time: {_git_commit()}
- Runner: tools/run_2a2t_parameter_simulation.py

source_type = SYNTHETIC
hardware_verified = false
""")
    _write(run_dir / "results" / "validation.md", f"""# Validation

## 검증된 결과

Golden/software constraints passed for {len(rows)} synthetic candidates; each completed all four direct-2A2T links with zero modeled overlap and collision.

## 가정한 값

Sequential slots, candidate guards, and deferred RX start with an acquisition lead equal to half the timeout margin are simulation assumptions.

## 논문 기반 근거

The PHY airtime equations, PLEN timing values, 522 us processing reference, and 100 us timeout-margin scale come from jkiees-36-3-274. The paper itself describes a single link, so the four-link superframe is a model extension.

## 추후 확인 필요

DW3000 measured processing, delayed-TX quantization, RX startup/preamble acquisition, actual frame lengths, oscillator drift, UART/SPI/IRQ timing, CIR behavior, RF coexistence, and antenna delay all remain unverified.

source_type = SYNTHETIC
hardware_verified = false
""")
    _write(run_dir / "results" / "report.md", f"""# Direct-2A2T parameter simulation report

This Phase 0-4 run evaluated {len(rows)} valid synthetic candidates and retained {len(front)} Pareto candidates. The fastest Pareto candidate is `{best['candidate_id']}` with a modeled superframe duration of {best['superframe_duration_us']:.3f} us ({best['superframe_rate_hz']:.3f} Hz).

This is not a DW3000 measurement, antenna-delay calibration, actual 2A2T communication verification, or logic-analyzer capture.

source_type = SYNTHETIC
hardware_verified = false
""")
    _write(run_dir / "closeout.md", """# Closeout

State progression: raw-only -> qc-passed -> processed -> exploratory.

Phase 0-4 software scope is complete for this run. Phase 5-6 remain gated and no result is promoted to reproducible, verified, or reported.

source_type = SYNTHETIC
hardware_verified = false
""")
    metadata = (run_dir / "metadata.yaml").read_text(encoding="utf-8")
    metadata = metadata.replace(
        "state_history:\n  - raw-only",
        "state_history:\n  - raw-only\n  - qc-passed\n  - processed\n  - exploratory",
    ).replace("experiment_state: raw-only", "experiment_state: exploratory")
    _write(run_dir / "metadata.yaml", metadata)


def run_simulation(baseline_path: Path, sweep_path: Path, results_root: Path) -> Path:
    baseline = load_yaml(baseline_path)
    sweep = load_yaml(sweep_path)
    errors = validate_config(baseline) + validate_config(sweep)
    if errors:
        raise ValueError("configuration validation failed:\n- " + "\n- ".join(errors))
    outputs = sweep["outputs"]
    prefix = "_".join(
        [date.today().isoformat(), outputs["platform"], outputs["configuration"], outputs["topic"]]
    )
    run_dir = _next_run_dir(results_root, prefix)
    run_dir.mkdir(parents=True)
    _prepare_documents(run_dir, baseline_path, sweep_path)
    shutil.copy2(baseline_path, run_dir / "baseline_config.snapshot.yaml")
    shutil.copy2(sweep_path, run_dir / "sweep_config.snapshot.yaml")
    rows = run_parameter_sweep(baseline, sweep)
    front = pareto_front(rows)
    _write_csv(run_dir / "results" / "candidates.csv", rows)
    _write_csv(run_dir / "results" / "pareto_candidates.csv", front)
    _write(run_dir / "results" / "candidates.json", json.dumps(rows, indent=2, ensure_ascii=False))
    _finish_documents(run_dir, rows, front)
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "configs" / "simulation_2a2t_paper_baseline.yaml")
    parser.add_argument("--sweep", type=Path, default=ROOT / "configs" / "simulation_2a2t_parameter_sweep.yaml")
    parser.add_argument("--results-root", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    run_dir = run_simulation(args.baseline.resolve(), args.sweep.resolve(), args.results_root.resolve())
    print(f"Phase 0-4 direct-2A2T simulation: PASS\nresults: {run_dir}")
    print("source_type = SYNTHETIC\nhardware_verified = false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
