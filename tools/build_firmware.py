#!/usr/bin/env python3
"""Plan or explicitly execute a configured multi-role firmware build matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from _common import ROOT, root_relative

from experiments.definitions import git_snapshot, write_json


def load_config(path: Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def plan_build_matrix(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node, board in config.get("boards", {}).items():
        rows.append(
            {
                "node": node,
                "role": board.get("role", "UNKNOWN"),
                "firmware_target": board.get("firmware_target", "TODO_USER_INPUT"),
                "status": "DRY_RUN_PLANNED",
                "image": None,
                "sha256": None,
                "source_type": "SYNTHETIC",
                "hardware_verified": False,
            }
        )
    expected = {"A1", "A2", "T1", "T2"}
    actual = {row["node"] for row in rows}
    if actual != expected:
        raise ValueError(f"build matrix must map exactly {sorted(expected)}, got {sorted(actual)}")
    return rows


def _has_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith("TODO_")
    if isinstance(value, dict):
        return any(_has_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_placeholder(item) for item in value)
    return False


def build_firmware(
    config: dict[str, Any],
    output_dir: Path,
    *,
    dry_run: bool,
    execute: bool,
    clean: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix = plan_build_matrix(config)
    firmware = config.get("firmware", {})
    result: dict[str, Any] = {
        "mode": "DRY_RUN" if dry_run else "EXECUTE",
        "status": "DRY_RUN_PASS" if dry_run else "PENDING",
        "clean_requested": clean,
        "matrix": matrix,
        "repository": git_snapshot(ROOT),
        "source_type": "SYNTHETIC" if dry_run else "UNVERIFIED_HW",
        "hardware_verified": False,
        "limitations": [
            "The baseline repository is overlay-only and has no native A1/A2/T1/T2 build targets.",
            "Dry-run rows are plans, not compiled firmware images.",
        ],
    }
    if dry_run:
        write_json(output_dir / "build_manifest.json", result)
        (output_dir / "hashes.txt").write_text(
            "# source_type = SYNTHETIC\n"
            "# hardware_verified = false\n"
            "# No firmware hashes: dry-run did not build images.\n",
            encoding="utf-8",
        )
        return result
    if not execute:
        raise ValueError("non-dry-run build requires --execute")
    commands = firmware.get("role_build_commands")
    if not isinstance(commands, dict) or _has_placeholder(commands):
        raise ValueError("firmware.role_build_commands must be fully configured before --execute")
    for row in matrix:
        node = row["node"]
        command = commands.get(node)
        if not isinstance(command, list) or not command:
            raise ValueError(f"missing list command for {node}")
        completed = subprocess.run([str(part) for part in command], cwd=root_relative(firmware.get("working_directory", ".")))
        if completed.returncode != 0:
            raise RuntimeError(f"build failed for {node} with exit code {completed.returncode}")
        image = root_relative(config["boards"][node]["firmware_image"])
        if not image.is_file():
            raise FileNotFoundError(f"configured image not produced for {node}: {image}")
        row.update(
            status="BUILT_UNVERIFIED_HW",
            image=str(image),
            sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
            source_type="BUILD_ARTIFACT",
        )
    result["status"] = "BUILD_PASS_UNVERIFIED_HW"
    result["source_type"] = "BUILD_ARTIFACT"
    write_json(output_dir / "build_manifest.json", result)
    (output_dir / "hashes.txt").write_text(
        "# source_type = BUILD_ARTIFACT\n"
        "# hardware_verified = false\n"
        + "".join(f"{row['sha256']}  {row['image']}\n" for row in matrix),
        encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default="artifacts/pre_hardware/build_dry_run")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(root_relative(args.config))
    result = build_firmware(
        config,
        root_relative(args.output),
        dry_run=args.dry_run,
        execute=args.execute,
        clean=args.clean,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
