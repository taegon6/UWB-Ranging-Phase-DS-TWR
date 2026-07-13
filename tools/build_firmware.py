#!/usr/bin/env python3
"""Plan or explicitly execute a configured multi-role firmware build matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # Supports both ``python tools/build_firmware.py`` and test imports.
    from ._common import ROOT, root_relative
except ImportError:  # pragma: no cover - exercised by direct CLI invocation
    from _common import ROOT, root_relative

from experiments.definitions import git_snapshot, write_json


EXPECTED_TARGETS = {
    "A1": "anchor_a1",
    "A2": "anchor_a2",
    "T1": "tag_t1",
    "T2": "tag_t2",
}


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
    for row in rows:
        expected_target = EXPECTED_TARGETS[row["node"]]
        if row["firmware_target"] != expected_target:
            raise ValueError(
                f"{row['node']} firmware_target must be {expected_target}, got {row['firmware_target']}"
            )
    return rows


def _has_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith("TODO_")
    if isinstance(value, dict):
        return any(_has_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_placeholder(item) for item in value)
    return False


def _resolve_from_working_directory(value: str | Path, working_directory: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else working_directory / path


def _require_empty_execute_output(output_dir: Path) -> None:
    """Never delete stale outputs: execution requires a fresh directory."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(
            f"execute build requires an empty output directory; refusing stale output: {output_dir}"
        )


def build_firmware(
    config: dict[str, Any],
    output_dir: Path,
    *,
    dry_run: bool,
    execute: bool,
    clean: bool = False,
) -> dict[str, Any]:
    if execute and dry_run:
        raise ValueError("execute and dry_run cannot both be true")
    if execute:
        _require_empty_execute_output(output_dir)
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
    role_markers = firmware.get("role_markers")
    working_directory = root_relative(firmware.get("working_directory", "."))
    if not working_directory.is_dir():
        raise FileNotFoundError(f"firmware working_directory does not exist: {working_directory}")
    images_dir = output_dir / "images"
    logs_dir = output_dir / "build_logs"
    images_dir.mkdir()
    logs_dir.mkdir()
    for row in matrix:
        node = row["node"]
        command = commands.get(node)
        if not isinstance(command, list) or not command:
            raise ValueError(f"missing list command for {node}")
        completed = subprocess.run(
            [str(part) for part in command],
            cwd=working_directory,
            check=False,
            capture_output=True,
            text=True,
        )
        (logs_dir / f"{node}.log").write_text(
            "# source_type = BUILD_ARTIFACT\n"
            "# hardware_verified = false\n"
            f"# command = {json.dumps([str(part) for part in command])}\n"
            f"# returncode = {completed.returncode}\n\n"
            "[stdout]\n"
            + completed.stdout
            + "\n[stderr]\n"
            + completed.stderr,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise RuntimeError(f"build failed for {node} with exit code {completed.returncode}")
        if not isinstance(role_markers, dict) or set(role_markers) != set(EXPECTED_TARGETS):
            raise ValueError("firmware.role_markers must map exactly A1/A2/T1/T2 before --execute")
        source_image = _resolve_from_working_directory(
            config["boards"][node]["firmware_image"], working_directory
        )
        if not source_image.is_file():
            raise FileNotFoundError(f"configured image not produced for {node}: {source_image}")
        marker = role_markers[node]
        if not isinstance(marker, str) or not marker:
            raise ValueError(f"firmware.role_markers.{node} must be a non-empty string")
        if marker.encode("utf-8") not in source_image.read_bytes():
            raise ValueError(f"role marker is absent from {node} image: {marker}")
        image = images_dir / f"{node}{source_image.suffix.lower()}"
        shutil.copy2(source_image, image)
        row.update(
            status="BUILT_UNVERIFIED_HW",
            image=str(image),
            sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
            source_type="BUILD_ARTIFACT",
            source_image=str(source_image),
            role_marker=marker,
            role_marker_verified=True,
            build_log=str(logs_dir / f"{node}.log"),
            built_at=datetime.now(timezone.utc).isoformat(),
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
