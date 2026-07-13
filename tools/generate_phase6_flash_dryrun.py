#!/usr/bin/env python3
"""Generate a non-executable, hash-bound Phase 6 J-Link flash plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

try:  # Supports both direct CLI invocation and pytest imports.
    from ._common import ROOT
    from .prepare_phase6_sdk_sandbox import canonical_sha256
except ImportError:  # pragma: no cover - direct CLI invocation
    from _common import ROOT
    from prepare_phase6_sdk_sandbox import canonical_sha256


ORDER = ("A1", "A2", "T2", "T1")
EXPECTED = {"A1": "anchor_a1", "A2": "anchor_a2", "T1": "tag_t1", "T2": "tag_t2"}


def unresolved(value: object) -> bool:
    return not isinstance(value, str) or not value or value.upper() in {"UNRESOLVED", "TODO_USER_INPUT", "TODO_CODE_OR_HW_VERIFY"}


def validate_inventory(config: Mapping[str, Any]) -> None:
    if config.get("jlink", {}).get("allow_execute") is not False:
        raise ValueError("Phase 6 dry-run requires jlink.allow_execute=false")
    boards = config.get("boards")
    if not isinstance(boards, Mapping):
        raise ValueError("boards must be a mapping")
    serials: list[str] = []
    ports: list[str] = []
    for node, image_id in EXPECTED.items():
        board = boards.get(node)
        if not isinstance(board, Mapping):
            raise ValueError(f"missing board {node}")
        if board.get("image_id") != image_id or board.get("firmware_target") != image_id:
            raise ValueError(f"{node} image mapping must be {image_id}")
        if board.get("device") != "nRF52840_xxAA":
            raise ValueError(f"{node} must target nRF52840_xxAA")
        if not unresolved(board.get("jlink_serial")):
            serials.append(str(board["jlink_serial"]))
        port = board.get("uart_port", board.get("serial_port"))
        if not unresolved(port):
            ports.append(str(port))
    if len(serials) != len(set(serials)):
        raise ValueError("duplicate concrete J-Link serial")
    if len(ports) != len(set(ports)):
        raise ValueError("duplicate concrete UART port")


def build_flash_plan(config: Mapping[str, Any], image_manifest: Mapping[str, Any]) -> dict[str, Any]:
    validate_inventory(config)
    rows = image_manifest.get("matrix", image_manifest.get("images", []))
    if not isinstance(rows, list):
        raise ValueError("image manifest image list must be a list")
    by_node = {str(row.get("node_id", row.get("node"))): row for row in rows if isinstance(row, Mapping)}
    failure = set(by_node) != set(EXPECTED) or any(
        by_node[node].get("build_status", by_node[node].get("status")) != "BUILT_UNVERIFIED_HW" for node in EXPECTED if node in by_node
    )
    operations: list[dict[str, Any]] = []
    for node in ORDER:
        board = dict(config["boards"][node])
        row = by_node.get(node, {})
        image = row.get("hex_path", row.get("image"))
        image_sha = row.get("image_sha256", row.get("sha256"))
        inventory_unresolved = unresolved(board.get("jlink_serial"))
        operations.append({
            "node": node,
            "image_id": EXPECTED[node],
            "image_sha256": image_sha,
            "hex_path": image,
            "jlink_serial": board.get("jlink_serial"),
            "device": board["device"],
            "interface": config["jlink"].get("interface", "SWD"),
            "speed_khz": config["jlink"].get("speed_khz", 4000),
            "verify_required": True,
            "reset_policy": "reset_after_verify_only",
            "execution_allowed": False,
            "command": "# UNRESOLVED inventory: no executable J-Link command" if inventory_unresolved else "# dry-run only: execution disabled",
        })
    status = "FLASH_PLAN_BLOCKED_BUILD_FAILURE" if failure else "FLASH_PLAN_HARDWARE_MAPPING_REQUIRED"
    plan: dict[str, Any] = {
        "schema_version": 1,
        "source_type": "CODE_INSPECTION_AND_BUILD",
        "hardware_verified": False,
        "flash_executed": False,
        "execution_allowed": False,
        "status": status,
        "operations": operations,
        "reset_order": list(ORDER),
        "failure_policy": "stop_on_first_failure",
    }
    plan["plan_sha256"] = canonical_sha256(plan)
    return plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "local_hardware.phase6.template.yaml")
    parser.add_argument("--image-manifest", type=Path, default=ROOT / "artifacts" / "phase6_build" / "image_manifest.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "phase6_flash" / "flash_plan.json")
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.exists():
        raise SystemExit(f"[FAIL] refusing to overwrite existing flash plan: {args.output}")
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    images = json.loads(args.image_manifest.read_text(encoding="utf-8"))
    plan = build_flash_plan(config, images)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    command_path = args.output.with_name("resolved_jlink_commands.txt")
    command_path.write_text("\n".join(str(row["command"]) for row in plan["operations"]) + "\n", encoding="utf-8")
    review = [
        "# Phase 6 Flash Plan Review (dry-run)",
        "",
        "source_type = CODE_INSPECTION_AND_BUILD",
        "hardware_verified = false",
        "flash_executed = false",
        "execution_allowed = false",
        "",
        f"- Status: `{plan['status']}`",
        "- Planned order: `A1 -> A2 -> T2 -> T1` (T1 coordinator last).",
        "- Stop policy: stop on first failure; no automatic rollback.",
        "- No J-Link command is executable until build artifacts and hardware inventory are resolved.",
    ]
    args.output.with_name("flash_plan_review.md").write_text("\n".join(review) + "\n", encoding="utf-8")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
