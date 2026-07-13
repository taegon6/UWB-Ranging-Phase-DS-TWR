#!/usr/bin/env python3
"""Recover a reproducible, baseline-only SES build in a disposable SDK worktree.

The command is intentionally build-only: no J-Link, erase, reset, UART, RF, or
logic-analyzer operation is implemented here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from ._common import ROOT
    from .prepare_phase6_sdk_sandbox import canonical_sha256
except ImportError:  # pragma: no cover - direct CLI invocation
    from _common import ROOT
    from prepare_phase6_sdk_sandbox import canonical_sha256


PROJECT_RELATIVE = Path("API/nRF52840-DK/dw3000_api.emProject")
SELECTION_RELATIVE = Path("API/Src/example_selection.h")
MISSING_SOURCES = {
    "../Src/urop_2/custom_ds_twr_initiator.c": "CUSTOM_DS_TWR_INITIATOR",
    "../Src/urop_2/custom_ds_twr_responder.c": "CUSTOM_DS_TWR_RESPONDER",
    "../Src/custom_code/switching.c": "UNRESOLVED_NO_SELECTION_MACRO",
    "../Src/custom_code/localization_ds_twr_initiatior.c": "LOCALIZATION_DS_TWR_INIT",
    "../Src/custom_code/localization_ds_twr_responder.c": "LOCALIZATION_DS_TWR_RESP",
}
EMBUILD_DEFAULT = Path(r"C:\Program Files\SEGGER\SEGGER Embedded Studio 8.28\bin\emBuild.exe")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, text=True, capture_output=True).stdout.strip()


def inventory(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        {"path": str(item.resolve()), "size": item.stat().st_size, "mtime_utc": datetime.fromtimestamp(item.stat().st_mtime, timezone.utc).isoformat(), "sha256": sha256(item)}
        for item in sorted(path.rglob("*")) if item.is_file()
    ]


def resolved_path(path: Path) -> dict[str, Any]:
    return {"path": str(path), "resolved_path": str(path.resolve()), "exists": path.exists(), "is_symlink": path.is_symlink()}


def build_command(embuild: Path, project: Path) -> list[str]:
    """Build the project directly; -batch is wrong unless it is marked batch-build."""
    return [str(embuild), "-rebuild", "-echo", "-verbose", "-config", "Debug", str(project)]


def active_defines(selection: Path) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"^\s*#define\s+([A-Z0-9_]+)\b", selection.read_text(encoding="utf-8"), re.MULTILINE)
    }


def remove_missing_project_entries(project: Path, selection: Path) -> list[dict[str, str]]:
    """Remove only proven-absent, inactive optional sources from a sandbox project."""
    text = project.read_text(encoding="utf-8")
    active = active_defines(selection)
    removed: list[dict[str, str]] = []
    for reference, macro in MISSING_SOURCES.items():
        if reference not in text:
            continue
        if macro != "UNRESOLVED_NO_SELECTION_MACRO" and macro in active:
            raise ValueError(f"cannot remove active optional source {reference}; {macro} is enabled")
        line = re.compile(rf"^\s*<file file_name=\"{re.escape(reference)}\"\s*/>\s*\r?\n", re.MULTILINE)
        updated, count = line.subn("", text)
        if count != 1:
            raise ValueError(f"expected exactly one project reference for {reference}, found {count}")
        text = updated
        removed.append({"reference": reference, "selection_macro": macro})
    project.write_text(text, encoding="utf-8", newline="\n")
    return removed


def project_dependency_manifest(project: Path, sdk_root: Path) -> dict[str, Any]:
    text = project.read_text(encoding="utf-8")
    references = re.findall(r'<file file_name="([^"]+)"', text)
    resolved = []
    for reference in references:
        if "$" in reference:
            state = "MACRO_RESOLVED_BY_SES"
            absolute = None
        else:
            absolute_path = (project.parent / reference).resolve()
            state = "PRESENT" if absolute_path.exists() else "MISSING"
            absolute = str(absolute_path)
        resolved.append({"reference": reference, "resolved_path": absolute, "state": state})
    attrs = {key: value for key, value in re.findall(r'([A-Za-z0-9_]+)="([^"]*)"', text.split("</project>", 1)[0])}
    return {
        "project": str(project), "sdk_root": str(sdk_root), "configurations": sorted(set(re.findall(r'<configuration\s+Name="([^"]+)"', text))),
        "target_device": attrs.get("arm_target_device_name"), "linker_script": attrs.get("link_linker_script_file"),
        "linker_output_format": attrs.get("linker_output_format"), "include_paths": attrs.get("c_user_include_directories", "").split(";"),
        "preprocessor_defines": attrs.get("c_preprocessor_definitions", "").split(";"), "files": resolved,
        "pre_build_command": attrs.get("build_pre_build_command"), "post_build_command": attrs.get("build_post_build_command"),
    }


def validate_fresh_build(*, before: list[dict[str, Any]], after: list[dict[str, Any]], log: str, start: datetime, end: datetime, marker: str) -> list[str]:
    errors: list[str] = []
    if before:
        errors.append("output directory was not empty before build")
    paths = {Path(row["path"]).suffix.lower(): row for row in after}
    for suffix in (".hex", ".elf"):
        if suffix not in paths:
            errors.append(f"missing required artifact {suffix}")
    if not re.search(r"(?:cc1|gcc|arm-none-eabi|linker|ld\.exe)", log, re.IGNORECASE):
        errors.append("build log contains no compile/link command")
    for row in after:
        timestamp = datetime.fromisoformat(row["mtime_utc"])
        if timestamp < start or timestamp > end:
            errors.append(f"artifact timestamp outside build interval: {row['path']}")
    elf = paths.get(".elf")
    if elf and marker.encode("utf-8") not in Path(elf["path"]).read_bytes():
        errors.append("baseline marker is absent from ELF")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--embuild", type=Path, default=EMBUILD_DEFAULT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sdk_root, output = args.sdk_root.resolve(), args.output_dir.resolve()
    if output.exists():
        raise SystemExit(f"[FAIL] refusing to overwrite recovery output: {output}")
    if not args.embuild.is_file():
        raise SystemExit(f"[FAIL] emBuild not found: {args.embuild}")
    project, selection = sdk_root / PROJECT_RELATIVE, sdk_root / SELECTION_RELATIVE
    if run_git(sdk_root, "status", "--porcelain=v1"):
        raise SystemExit("[FAIL] SDK worktree must be clean before recovery preparation")
    output.mkdir(parents=True)
    subprocess.run([sys.executable, str(ROOT / "tools" / "set_uwb_example.py"), "ds-initiator", "--path", str(selection)], check=True, capture_output=True, text=True)
    removed = remove_missing_project_entries(project, selection)
    dependency = project_dependency_manifest(project, sdk_root)
    missing = [row for row in dependency["files"] if row["state"] == "MISSING"]
    (output / "project_dependency_manifest.json").write_text(json.dumps(dependency, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "missing_sources_report.json").write_text(json.dumps({"removed_optional_references": removed, "remaining_missing_references": missing}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_root = project.parent / "Output" / "Debug"
    (output / "resolved_paths.json").write_text(json.dumps({"sdk_root": resolved_path(sdk_root), "project": resolved_path(project), "output_root": resolved_path(output_root)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    before = inventory(output_root)
    started = datetime.now(timezone.utc)
    command = build_command(args.embuild, project)
    completed = subprocess.run(command, cwd=project.parent, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    ended = datetime.now(timezone.utc)
    log = (completed.stdout or "") + (completed.stderr or "")
    (output / "build_logs").mkdir()
    (output / "build_logs" / "baseline_initiator.log").write_text(log, encoding="utf-8")
    after = inventory(output_root)
    errors = validate_fresh_build(before=before, after=after, log=log, start=started, end=ended, marker="ds_twr_initiator_final")
    if completed.returncode != 0:
        errors.append(f"emBuild exit code {completed.returncode}")
    manifest: dict[str, Any] = {
        "source_type": "CODE_INSPECTION_AND_BUILD", "hardware_verified": False, "flash_executed": False,
        "status": "BASELINE_FRESH_BUILD_READY" if not errors else "BASELINE_FRESH_BUILD_NOT_READY",
        "sdk_commit": run_git(sdk_root, "rev-parse", "HEAD"), "project": str(project), "target_device": dependency["target_device"],
        "configuration": "Debug", "command": command, "exit_code": completed.returncode,
        "started_utc": started.isoformat(), "ended_utc": ended.isoformat(), "output_before": before, "output_after": after,
        "stdout_bytes": len((completed.stdout or "").encode("utf-8")), "stderr_bytes": len((completed.stderr or "").encode("utf-8")), "build_log": str(output / "build_logs" / "baseline_initiator.log"),
        "removed_optional_references": removed, "errors": errors,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    (output / "build_attempt_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
