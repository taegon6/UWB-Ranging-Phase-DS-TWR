#!/usr/bin/env python3
"""Run the antenna-delay calibration software path or a guarded real plan."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from _common import ROOT, root_relative

from analysis.antenna_delay_fit import run_mock_calibration
from check_environment import run_checks
from experiments.definitions import (
    base_manifest,
    create_run_directory,
    write_json,
    write_source_snapshot,
)
from hardware.device_inventory import ConfigError, validate_config


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _objective_svg(curve_csv: Path, output: Path) -> None:
    with curve_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    points = [(float(row["candidate"]), float(row["objective"])) for row in rows]
    width, height, margin = 720, 360, 48
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_span = max(xs) - min(xs) or 1.0
    y_span = max(ys) - min(ys) or 1.0
    coords = [
        (
            margin + (x - min(xs)) / x_span * (width - 2 * margin),
            height - margin - (y - min(ys)) / y_span * (height - 2 * margin),
        )
        for x, y in points
    ]
    polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in coords)
    circles = "\n".join(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="#2563eb" />' for x, y in coords)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<!-- source_type = SYNTHETIC -->
<!-- hardware_verified = false -->
<rect width="100%" height="100%" fill="white" />
<text x="{width/2}" y="24" text-anchor="middle" font-family="sans-serif" font-size="16">Synthetic objective curve (not a hardware calibration)</text>
<line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="black" />
<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height-margin}" stroke="black" />
<polyline points="{polyline}" fill="none" stroke="#2563eb" stroke-width="2" />
{circles}
<text x="{width/2}" y="{height-8}" text-anchor="middle" font-family="sans-serif" font-size="12">synthetic candidate token</text>
<text x="12" y="{height/2}" transform="rotate(-90 12 {height/2})" text-anchor="middle" font-family="sans-serif" font-size="12">synthetic objective</text>
<text x="{width-12}" y="{height-8}" text-anchor="end" font-family="sans-serif" font-size="10">source_type=SYNTHETIC; hardware_verified=false</text>
</svg>
"""
    output.write_text(svg, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--hardware-config")
    parser.add_argument("--backend", choices=["mock", "real"], default="mock")
    parser.add_argument("--output-root", default="results")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    return parser.parse_args()


def _run_mock(config: dict[str, Any], output_root: Path) -> Path:
    start = datetime.now().astimezone()
    run_id, run_dir = create_run_directory(
        output_root,
        "antenna_delay_calibration",
        backend="mock",
        now=start,
    )
    write_json(run_dir / "config_snapshot" / "antenna_calibration.json", config)
    write_source_snapshot(
        ROOT,
        run_dir / "source_snapshot" / "attempt01",
        extra_sources=[
            ROOT / "artifacts" / "baseline" / "baseline_manifest.json",
            ROOT / "artifacts" / "current_code_analysis.md",
        ],
    )
    checks = run_checks(ROOT / "configs" / "mock_hardware.yaml")
    write_json(
        run_dir / "environment_report.json",
        {
            "source_type": "SYNTHETIC",
            "hardware_verified": False,
            "checks": [asdict(check) for check in checks],
        },
    )
    write_json(
        run_dir / "firmware" / "build_manifest.json",
        {
            "status": "SKIP",
            "reason": "calibration dry-run evaluates synthetic candidates without compiling images",
            "source_type": "SYNTHETIC",
            "hardware_verified": False,
        },
    )
    (run_dir / "firmware" / "hashes.txt").write_text(
        "# source_type = SYNTHETIC\n"
        "# hardware_verified = false\n"
        "# No firmware images were built by calibration dry-run.\n",
        encoding="utf-8",
    )
    calibration_dir = run_dir / "analysis" / "calibration"
    result = run_mock_calibration(config, calibration_dir)
    _objective_svg(calibration_dir / "objective_curve.csv", run_dir / "figures" / "objective_curve.svg")
    manifest = base_manifest(
        run_id=run_id,
        backend="mock",
        config=config,
        repository_root=ROOT,
        start_time=start.isoformat(),
    )
    manifest.update(
        status="PASS",
        end_time=datetime.now().astimezone().isoformat(),
        calibration=result,
        stages=[
            {"name": "VALIDATE_CONFIG", "status": "PASS", "duration_s": 0.0, "reason": "dry-run placeholders allowed"},
            {"name": "RUN_EXPERIMENT", "status": "PASS", "duration_s": 0.0, "reason": "synthetic candidate evaluation"},
            {"name": "ANALYZE", "status": "PASS", "duration_s": 0.0, "reason": "synthetic objective"},
            {"name": "GENERATE_REPORT", "status": "PASS", "duration_s": 0.0, "reason": "dry-run report"},
        ],
    )
    write_json(run_dir / "run_manifest.json", manifest)
    calibration_report = (calibration_dir / "calibration_report.md").read_text(encoding="utf-8")
    (run_dir / "report.md").write_text(
        "# 2A2T UWB antenna-delay calibration dry-run\n\n"
        + calibration_report.split("\n", 1)[1].lstrip(),
        encoding="utf-8",
    )
    (run_dir / "unresolved_items.md").write_text(
        "# Unresolved items\n\n"
        "- Actual A1/A2/T1/T2 build targets, images, J-Link IDs, and UART identity records.\n"
        "- Reference-node/link geometry, antenna reference points, placement uncertainty, and environment.\n"
        "- Hardware-safe antenna-delay range and coarse/fine steps.\n"
        "- Range-record contract and final-candidate measured validation.\n\n"
        "`source_type = SYNTHETIC`  \n`hardware_verified = false`\n",
        encoding="utf-8",
    )
    return run_dir


def _guard_real(args: argparse.Namespace, config: dict[str, Any]) -> None:
    if not args.hardware_config:
        raise SystemExit("--hardware-config is required with --backend real --execute")
    hardware_config = load_yaml(root_relative(args.hardware_config))
    if config.get("backend") != "real":
        raise SystemExit("Refusing real calibration; set calibration config backend: real after copying the example")
    outputs = config.get("outputs", {})
    if outputs.get("source_type") != "MEASURED" or outputs.get("hardware_verified") is not False:
        raise SystemExit(
            "Refusing real calibration; outputs must start as source_type: MEASURED and hardware_verified: false"
        )
    try:
        from hardware.device_inventory import find_placeholders
    except ImportError as exc:
        raise SystemExit(f"hardware layer unavailable: {exc}") from exc
    placeholders = find_placeholders(hardware_config) + find_placeholders(config)
    hardware_search = config.get("calibration", {}).get("search", {}).get("hardware", {})
    placeholders += [f"calibration.search.hardware.{key}" for key, value in hardware_search.items() if str(value).startswith("TODO_")]
    if placeholders:
        raise SystemExit("Refusing real calibration; unresolved placeholders:\n- " + "\n- ".join(sorted(set(placeholders))))
    raise SystemExit(
        "Real calibration is guarded until the connection smoke test and range-record contract pass. "
        "No build, flash, reset, or measurement was attempted."
    )


def main() -> int:
    args = parse_args()
    config = load_yaml(root_relative(args.config))
    try:
        validate_config(config, allow_placeholders=args.dry_run)
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    if args.backend == "mock":
        if not args.dry_run:
            raise SystemExit("mock backend must be used with --dry-run")
        run_dir = _run_mock(config, root_relative(args.output_root))
        print(f"[PASS] antenna-delay calibration dry-run")
        print("source_type = SYNTHETIC")
        print("hardware_verified = false")
        print(f"RESULT_DIR={run_dir}")
        return 0
    if not args.execute:
        raise SystemExit("real backend requires explicit --execute")
    _guard_real(args, config)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
