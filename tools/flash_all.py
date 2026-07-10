#!/usr/bin/env python3
"""Plan A1/A2/T1/T2 J-Link flashing; execute only with explicit authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from _common import root_relative


def load_config(path: Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def plan_flash(config: dict[str, Any], image_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    image_by_node = {
        row["node"]: row.get("image")
        for row in (image_manifest or {}).get("matrix", [])
    }
    operations = []
    for node in ["A1", "A2", "T1", "T2"]:
        board = config.get("boards", {}).get(node)
        if board is None:
            raise ValueError(f"missing board mapping for {node}")
        serial = board.get("jlink_serial", "TODO_USER_INPUT")
        image = image_by_node.get(node) or board.get("firmware_image") or f"DRY_RUN_IMAGE_FOR_{node}"
        operations.append(
            {
                "node": node,
                "firmware_target": board.get("firmware_target"),
                "image": image,
                "jlink_serial": serial,
                "command": [
                    board.get("jlink_executable", "JLink.exe"),
                    "-SelectEmuBySN",
                    str(serial),
                    "-CommandFile",
                    board.get("jlink_command_file", "TODO_USER_INPUT"),
                ],
                "status": "DRY_RUN_PLANNED",
                "source_type": "SYNTHETIC",
                "hardware_verified": False,
            }
        )
    return {
        "operations": operations,
        "reset_order": ["A1", "A2", "T1", "T2"],
        "failure_policy": "stop_on_first_failure; do not roll back already flashed boards automatically",
        "source_type": "SYNTHETIC",
        "hardware_verified": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--build-manifest")
    parser.add_argument("--output", default="artifacts/pre_hardware/flash_plan.json")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(root_relative(args.config))
    manifest = None
    if args.build_manifest:
        manifest = json.loads(root_relative(args.build_manifest).read_text(encoding="utf-8"))
    plan = plan_flash(config, manifest)
    if args.execute:
        unresolved = [
            operation["node"]
            for operation in plan["operations"]
            if any(str(value).startswith("TODO_") for value in operation["command"])
            or str(operation["image"]).startswith("DRY_RUN_")
        ]
        if unresolved:
            raise SystemExit(f"Refusing flash; unresolved mappings for: {', '.join(unresolved)}")
        raise SystemExit("Use the configured FlashBackend through run_hardware_experiment.py for real flashing.")
    output = root_relative(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
