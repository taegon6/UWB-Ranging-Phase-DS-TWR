#!/usr/bin/env python3
"""Capture four UART streams through an injected backend with retry metadata."""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from _common import root_relative

from hardware import HardwareError, create_backend, load_yaml, validate_config


def capture_many(
    config: dict[str, Any],
    output_dir: Path,
    *,
    backend_name: str,
    duration_s: float,
    execute: bool,
    reconnect_attempts: int = 2,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    backend = create_backend(backend_name, config, output_dir)
    serial_backend = backend.serial_backend if backend_name == "mock" else backend
    port_by_node = {node: str(board["serial_port"]) for node, board in config["boards"].items()}
    available = {str(item["device"]) for item in serial_backend.list_ports()}
    missing = {node: port for node, port in port_by_node.items() if port not in available}
    if missing:
        raise HardwareError(f"missing configured UART ports: {missing}")

    started = time.monotonic()

    def one(node: str, port: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(reconnect_attempts + 1):
            try:
                result = serial_backend.capture(
                    port,
                    output_dir / f"{node}.bin",
                    duration_s,
                    execute=execute,
                )
                return {**result, "node_id": node, "attempt": attempt + 1}
            except HardwareError as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    results = []
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="uwb-uart") as executor:
        futures = {executor.submit(one, node, port): node for node, port in port_by_node.items()}
        for future in as_completed(futures):
            results.append(future.result())
    manifest = {
        "status": "PASS",
        "backend": backend_name,
        "host_monotonic_start_s": started,
        "host_monotonic_end_s": time.monotonic(),
        "captures": sorted(results, key=lambda row: row["node_id"]),
        "source_type": "SYNTHETIC" if backend_name == "mock" else "MEASURED",
        "hardware_verified": False,
        "verification_status": (
            "SYNTHETIC_FIXTURE" if backend_name == "mock" else "RAW_CAPTURED_NOT_QUALITY_VALIDATED"
        ),
    }
    (output_dir / "capture_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--backend", choices=["mock", "pyserial"], required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duration", type=float, default=1.0)
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
        raise SystemExit("real UART capture requires --execute")
    configured_backend = config.get("backend")
    if args.backend == "mock" and configured_backend != "mock":
        raise SystemExit("mock capture requires config backend: mock")
    if args.backend != "mock":
        if not isinstance(configured_backend, dict) or configured_backend.get("serial") not in {"pyserial", "serial"}:
            raise SystemExit("real UART capture requires config backend.serial: pyserial")
    result = capture_many(
        config,
        root_relative(args.output_dir),
        backend_name=args.backend,
        duration_s=args.duration,
        execute=args.execute,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
