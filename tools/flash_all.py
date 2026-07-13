#!/usr/bin/env python3
"""Create and execute an approval-bound A1/A2/T2/T1 J-Link flash plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

try:  # Supports both ``python tools/flash_all.py`` and test imports.
    from ._common import root_relative
except ImportError:  # pragma: no cover - direct CLI invocation
    from _common import root_relative

from hardware.jlink_backend import JLinkFlashBackend


NODE_ORDER = ("A1", "A2", "T2", "T1")
EXPECTED_TARGETS = {"A1": "anchor_a1", "A2": "anchor_a2", "T1": "tag_t1", "T2": "tag_t2"}


def load_config(path: Path) -> dict[str, Any]:
    import yaml

    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("flash configuration must be a mapping")
    return loaded


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_board(config: Mapping[str, Any], node: str) -> Mapping[str, Any]:
    boards = config.get("boards")
    if not isinstance(boards, Mapping) or not isinstance(boards.get(node), Mapping):
        raise ValueError(f"missing board mapping for {node}")
    board = boards[node]
    if board.get("firmware_target") != EXPECTED_TARGETS[node]:
        raise ValueError(f"{node} firmware_target must be {EXPECTED_TARGETS[node]}")
    return board


def _build_rows(image_manifest: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not image_manifest:
        return {}
    rows = image_manifest.get("matrix", [])
    if not isinstance(rows, list):
        raise ValueError("build manifest matrix must be a list")
    mapped = {str(row.get("node")): row for row in rows if isinstance(row, Mapping)}
    if set(mapped) != set(EXPECTED_TARGETS):
        raise ValueError("build manifest must map exactly A1/A2/T1/T2")
    return mapped


def _is_dry_run_manifest(image_manifest: Mapping[str, Any] | None) -> bool:
    return not image_manifest or str(image_manifest.get("mode", "")).upper() == "DRY_RUN"


def _validated_image(row: Mapping[str, Any], node: str) -> tuple[Path, str]:
    if row.get("status") != "BUILT_UNVERIFIED_HW":
        raise ValueError(f"{node} build row is not an executable unverified image")
    raw_image = row.get("image")
    expected_sha = row.get("sha256")
    if not isinstance(raw_image, str) or not raw_image or not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValueError(f"{node} build row lacks image or SHA-256")
    image = Path(raw_image)
    if not image.is_file():
        raise FileNotFoundError(f"{node} image does not exist: {image}")
    actual_sha = hashlib.sha256(image.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        raise ValueError(f"{node} image SHA-256 mismatch; build artifact changed after manifest creation")
    return image, actual_sha


def plan_flash(config: dict[str, Any], image_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve a deterministic plan without touching a J-Link probe."""

    rows = _build_rows(image_manifest)
    dry_run = _is_dry_run_manifest(image_manifest)
    backend = JLinkFlashBackend(config)
    operations: list[dict[str, Any]] = []
    for node in NODE_ORDER:
        board = _require_board(config, node)
        if dry_run:
            image = Path(f"DRY_RUN_IMAGE_FOR_{node}.hex")
            image_sha = None
            status = "DRY_RUN_PLANNED"
            source_type = "SYNTHETIC"
        else:
            image, image_sha = _validated_image(rows[node], node)
            status = "APPROVAL_REQUIRED"
            source_type = "BUILD_ARTIFACT"
        device = {"node_id": node, **dict(board)}
        flash_plan = backend.flash(device, image, execute=False)
        operations.append(
            {
                "node": node,
                "firmware_target": board["firmware_target"],
                "image": str(image),
                "image_sha256": image_sha,
                "jlink_serial": board.get("jlink_serial"),
                "device": device.get("device") or config.get("jlink", {}).get("device"),
                "interface": device.get("interface") or config.get("jlink", {}).get("interface", "SWD"),
                "speed_khz": device.get("speed_khz") or config.get("jlink", {}).get("speed_khz", 4000),
                "script": flash_plan["script"],
                "command": backend.build_command(device, Path(f"flash_{node}.jlink")),
                "status": status,
                "source_type": source_type,
                "hardware_verified": False,
            }
        )
    plan: dict[str, Any] = {
        "operations": operations,
        "reset_order": list(NODE_ORDER),
        "failure_policy": "stop_on_first_failure; do not roll back already flashed boards automatically",
        "approval_required": not dry_run,
        "source_type": "SYNTHETIC" if dry_run else "BUILD_ARTIFACT",
        "hardware_verified": False,
    }
    plan["plan_sha256"] = _canonical_hash(plan)
    return plan


def validate_flash_plan_approval(plan: Mapping[str, Any], approval_hash: str | None) -> None:
    """Bind the user approval to every node/image/SHA/J-Link command field."""

    if plan.get("approval_required") is not True:
        raise ValueError("dry-run flash plans cannot be executed")
    if not isinstance(approval_hash, str) or not approval_hash:
        raise ValueError("an explicit flash plan approval hash is required")
    expected = plan.get("plan_sha256")
    payload = {key: value for key, value in plan.items() if key != "plan_sha256"}
    actual = _canonical_hash(payload)
    if expected != actual:
        raise ValueError("flash plan content does not match its plan_sha256")
    if approval_hash != expected:
        raise ValueError("flash plan approval hash does not match the resolved plan")


def execute_flash_plan(
    config: dict[str, Any], plan: Mapping[str, Any], *, approval_hash: str | None
) -> list[dict[str, Any]]:
    """Flash serially only after hash-bound approval; this function has real side effects."""

    validate_flash_plan_approval(plan, approval_hash)
    if config.get("jlink", {}).get("allow_execute") is not True:
        raise ValueError("J-Link execution is disabled; set jlink.allow_execute=true only after review")
    backend = JLinkFlashBackend(config)
    results: list[dict[str, Any]] = []
    for operation in plan.get("operations", []):
        image = Path(str(operation["image"]))
        expected_sha = str(operation["image_sha256"])
        actual_sha = hashlib.sha256(image.read_bytes()).hexdigest()
        if actual_sha != expected_sha:
            raise ValueError(f"{operation['node']} image SHA-256 changed after plan approval")
        device = dict(config["boards"][str(operation["node"])])
        device["node_id"] = operation["node"]
        result = backend.flash(device, image, execute=True)
        result.update(
            {
                "node": operation["node"],
                "image": str(image),
                "image_sha256": actual_sha,
                "source_type": "DEVICE_OPERATION",
                "hardware_verified": False,
            }
        )
        results.append(result)
        if not result.get("success"):
            raise RuntimeError(f"flash failed for {operation['node']}")
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--build-manifest")
    parser.add_argument("--output", default="artifacts/pre_hardware/flash_plan.json")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--approve-plan-sha256")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = load_config(root_relative(args.config))
        manifest = None
        if args.build_manifest:
            manifest = json.loads(root_relative(args.build_manifest).read_text(encoding="utf-8"))
        plan = plan_flash(config, manifest)
        output = root_relative(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise ValueError(f"refusing to overwrite existing flash plan: {output}")
        output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.execute:
            results = execute_flash_plan(config, plan, approval_hash=args.approve_plan_sha256)
            output.with_name("flash_execution_manifest.json").write_text(
                json.dumps({**plan, "results": results}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
