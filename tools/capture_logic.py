#!/usr/bin/env python3
"""Capture or synthesize a canonical logic-edge CSV through the HAL."""

from __future__ import annotations

import argparse
import json

from _common import root_relative

from hardware import create_backend, load_yaml, validate_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--backend", choices=["mock", "saleae", "sigrok"], required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=float)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_yaml(root_relative(args.config))
    validate_config(config, allow_placeholders=args.dry_run)
    if args.backend == "mock" and not args.dry_run:
        raise SystemExit("mock capture requires --dry-run")
    if args.backend != "mock" and not args.execute:
        raise SystemExit("real logic capture requires --execute")
    configured_backend = config.get("backend")
    if args.backend == "mock" and configured_backend != "mock":
        raise SystemExit("mock capture requires config backend: mock")
    if args.backend != "mock":
        if not isinstance(configured_backend, dict) or configured_backend.get("logic") != args.backend:
            raise SystemExit(f"real logic capture requires config backend.logic: {args.backend}")
    backend = create_backend(args.backend, config)
    selected = backend.logic_backend if args.backend == "mock" else backend
    logic = dict(config.get("logic_analyzer", {}))
    output = root_relative(args.output)
    capture_output = output
    if args.backend == "sigrok":
        capture_output = output.with_name(output.stem + ".raw" + output.suffix)
    result = selected.capture(
        logic,
        capture_output,
        duration_s=args.duration or float(logic.get("capture_duration_s", 1.0)),
        execute=args.execute,
    )
    if args.backend == "sigrok":
        export_result = selected.export_edges(capture_output, output)
        result = {
            "capture": result,
            "edge_export": export_result,
            "source_type": "MEASURED",
            "hardware_verified": False,
        }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
