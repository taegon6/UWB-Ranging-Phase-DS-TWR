#!/usr/bin/env python3
"""Analyze canonical logic edges into pulse, error, and timing summary tables."""

from __future__ import annotations

import argparse
import json

from _common import root_relative

from analysis.edge_detection import analyze_logic_capture


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-type", choices=["SYNTHETIC", "MEASURED"], default="SYNTHETIC")
    parser.add_argument("--hardware-verified", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.hardware_verified:
        raise SystemExit(
            "timing analysis alone cannot set hardware_verified=true; keep it false until separate HIL acceptance"
        )
    output = root_relative(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result = analyze_logic_capture(
        root_relative(args.input_csv),
        edge_pairs_csv=output / "edge_pairs.csv",
        summary_csv=output / "timing_summary.csv",
        errors_csv=output / "errors.csv",
        source_type=args.source_type,
        hardware_verified=args.hardware_verified,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
