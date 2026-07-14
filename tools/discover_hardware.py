#!/usr/bin/env python3
"""Validate configured device-role mappings and perform guarded discovery."""

from __future__ import annotations

import argparse
import json

from _common import root_relative

from hardware import ConfigError, build_inventory, create_backend, find_placeholders, load_yaml, validate_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_yaml(root_relative(args.config))
    try:
        placeholders = validate_config(config, allow_placeholders=args.dry_run)
    except ConfigError as exc:
        print(f"[FAIL] {exc}")
        return 1
    report = {
        "configured_inventory": build_inventory(config),
        "unresolved_placeholders": placeholders,
        "source_type": "PLANNED" if args.dry_run else "DISCOVERED_UNVERIFIED",
        "hardware_verified": False,
    }
    if args.dry_run:
        report["status"] = "DRY_RUN_ONLY"
        print(json.dumps(report, indent=2))
        return 0
    mapping = config.get("backend")
    if not isinstance(mapping, dict):
        print("[FAIL] real discovery requires backend.flash/backend.serial/backend.logic mapping")
        return 1
    if any(value == "mock" for value in mapping.values()):
        print("[FAIL] real discovery forbids mock adapters")
        return 1
    flash = create_backend(mapping["flash"], config)
    serial = create_backend(mapping["serial"], config)
    logic = create_backend(mapping["logic"], config)
    report.update(
        status="DISCOVERY_COMPLETE_UNVERIFIED",
        flash_devices=list(flash.list_devices()),
        serial_ports=list(serial.list_ports()),
        logic_devices=list(logic.list_devices()),
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
