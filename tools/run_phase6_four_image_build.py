#!/usr/bin/env python3
"""Build or inspect the four isolated Phase 6 SDK images without hardware I/O.

This command intentionally has no J-Link, UART, or RF code path.  A zero return
code from emBuild is *not* treated as a build pass unless a fresh HEX, ELF, and
role-specific FWID are also found.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # Supports both direct CLI invocation and pytest imports.
    from ._common import ROOT
    from .prepare_phase6_sdk_sandbox import ROLE_SPECS, canonical_sha256
except ImportError:  # pragma: no cover - direct CLI invocation
    from _common import ROOT
    from prepare_phase6_sdk_sandbox import ROLE_SPECS, canonical_sha256


PROJECT = Path("API/nRF52840-DK/dw3000_api.emProject")
ROLE_ORDER = ("anchor_a1", "anchor_a2", "tag_t1", "tag_t2")
EMBUILD_DEFAULT = Path(r"C:\Program Files\SEGGER\SEGGER Embedded Studio 8.28\bin\emBuild.exe")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _find_one(root: Path, suffix: str) -> Path | None:
    matches = [path for path in root.rglob(f"*{suffix}") if path.is_file()]
    return matches[0] if len(matches) == 1 else None


def _contains_fwid(path: Path | None, expected: str) -> bool:
    if path is None:
        return False
    return expected.encode("utf-8") in path.read_bytes()


def _warning_count(output: str) -> int:
    return sum("warning:" in line.lower() for line in output.splitlines())


def _error_count(output: str) -> int:
    return sum(
        ("error:" in line.lower() or "build failed" in line.lower() or "does not exist" in line.lower())
        for line in output.splitlines()
    )


def _load_overlay(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {"role", "node_id", "role_name", "fwid", "source_commit", "overlay_sha256", "config_sha256"}
    if not required.issubset(payload):
        raise ValueError(f"overlay manifest is missing required fields: {path}")
    return payload


def build_one(role: str, sandbox_root: Path, output_dir: Path, overlay_dir: Path, embuild: Path) -> dict[str, Any]:
    spec = ROLE_SPECS[role]
    sdk_root = sandbox_root / role
    overlay = _load_overlay(overlay_dir / f"{role}.json")
    if overlay["node_id"] != spec["node"] or overlay["role_name"] != spec["role"]:
        raise ValueError(f"overlay role identity mismatch for {role}")
    project = sdk_root / PROJECT
    if not project.is_file():
        raise FileNotFoundError(f"missing SDK project for {role}: {project}")
    output_root = project.parent / "Output" / "Debug"
    log_path = output_dir / "build_logs" / f"{role}.log"
    # Clean is constrained to this disposable SDK worktree.  It prevents a
    # pre-existing HEX/object tree from ever entering a Phase 6 manifest.
    clean_command = [str(embuild), "-clean", "-config", "Debug", str(project)]
    clean = subprocess.run(clean_command, cwd=project.parent, capture_output=True, text=True, check=False)
    clean_log = clean.stdout + clean.stderr
    if clean.returncode != 0 or (output_root.exists() and any(path.is_file() for path in output_root.rglob("*"))):
        reason = "SDK output was not clean after emBuild -clean; stale artifact rejected"
        log_path.write_text(reason + "\n", encoding="utf-8")
        return {
            "image_id": role, "node_id": spec["node"], "role": spec["role"],
            "build_status": "BUILD_FAILED", "reason": reason, "build_log": str(log_path),
            "source_type": "CODE_INSPECTION_AND_BUILD", "hardware_verified": False, "flash_executed": False,
        }
    command = [str(embuild), "-rebuild", "-echo", "-config", "Debug", str(project)]
    started = datetime.now(timezone.utc).isoformat()
    completed = subprocess.run(command, cwd=project.parent, capture_output=True, text=True, check=False)
    log = clean_log + completed.stdout + completed.stderr
    log_path.write_text(log, encoding="utf-8")
    hex_path = _find_one(output_root, ".hex") if output_root.exists() else None
    elf_path = _find_one(output_root, ".elf") if output_root.exists() else None
    map_path = _find_one(output_root, ".map") if output_root.exists() else None
    fwid_in_elf = _contains_fwid(elf_path, str(overlay["fwid"]))
    errors = _error_count(log)
    success = completed.returncode == 0 and errors == 0 and hex_path is not None and elf_path is not None and fwid_in_elf
    if success:
        image_dir = output_dir / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        copied_hex = image_dir / f"{role}.hex"
        if copied_hex.exists():
            raise ValueError(f"refusing to reuse stale image: {copied_hex}")
        shutil.copy2(hex_path, copied_hex)
        hex_path = copied_hex
    return {
        "image_id": role,
        "node_id": spec["node"],
        "role": spec["role"],
        "hex_path": str(hex_path) if success and hex_path else None,
        "elf_path": str(elf_path) if elf_path else None,
        "map_path": str(map_path) if map_path else None,
        "source_commit": overlay["source_commit"],
        "overlay_sha256": overlay["overlay_sha256"],
        "config_sha256": overlay["config_sha256"],
        "image_sha256": sha256(hex_path) if success and hex_path else None,
        "fwid": overlay["fwid"],
        "fwid_verified_in_elf": fwid_in_elf,
        "build_timestamp": started,
        "toolchain": "SEGGER Embedded Studio 8.28 / emBuild",
        "target_device": "nRF52840_xxAA",
        "build_configuration": "Debug",
        "warning_count": _warning_count(log),
        "error_count": errors,
        "emBuild_exit_code": completed.returncode,
        "build_log": str(log_path),
        "build_status": "BUILT_UNVERIFIED_HW" if success else "BUILD_FAILED",
        "source_type": "CODE_INSPECTION_AND_BUILD",
        "hardware_verified": False,
        "flash_executed": False,
    }


def write_manifests(output_dir: Path, rows: list[dict[str, Any]], commands: list[str]) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "source_type": "CODE_INSPECTION_AND_BUILD",
        "hardware_verified": False,
        "flash_executed": False,
        "mode": "BUILD",
        "status": "BUILD_PASS_UNVERIFIED_HW" if all(row["build_status"] == "BUILT_UNVERIFIED_HW" for row in rows) else "BUILD_FAILED",
        "images": rows,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    (output_dir / "build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    image_manifest = {"schema_version": 1, "source_type": manifest["source_type"], "hardware_verified": False, "flash_executed": False, "matrix": rows}
    image_manifest["manifest_sha256"] = canonical_sha256(image_manifest)
    (output_dir / "image_manifest.json").write_text(json.dumps(image_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "resolved_build_commands.txt").write_text("\n".join(commands) + "\n", encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sandbox-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "phase6_build")
    parser.add_argument("--overlay-dir", type=Path, default=ROOT / "artifacts" / "phase6_build" / "overlay_manifests")
    parser.add_argument("--embuild", type=Path, default=EMBUILD_DEFAULT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    if (output_dir / "build_manifest.json").exists() or (output_dir / "image_manifest.json").exists():
        raise SystemExit("[FAIL] refusing to overwrite a prior build manifest")
    if not args.embuild.is_file():
        raise SystemExit(f"[FAIL] emBuild not found: {args.embuild}")
    (output_dir / "build_logs").mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    commands: list[str] = []
    for role in ROLE_ORDER:
        try:
            rows.append(build_one(role, args.sandbox_root.resolve(), output_dir, args.overlay_dir.resolve(), args.embuild))
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            spec = ROLE_SPECS[role]
            rows.append({"image_id": role, "node_id": spec["node"], "role": spec["role"], "build_status": "BUILD_FAILED", "reason": str(exc), "source_type": "CODE_INSPECTION_AND_BUILD", "hardware_verified": False, "flash_executed": False})
        commands.append(f'"{args.embuild}" -rebuild -echo -config Debug "{args.sandbox_root.resolve() / role / PROJECT}"')
    manifest = write_manifests(output_dir, rows, commands)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest["status"] == "BUILD_PASS_UNVERIFIED_HW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
