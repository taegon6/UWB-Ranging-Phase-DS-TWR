#!/usr/bin/env python3
"""Evidence-only Phase 6.2 recovery gate for legacy SES and missing SDK sources.

This command never installs software, edits an SDK, builds firmware, or performs
J-Link/flash/reset/RF/UART/logic-analyzer I/O.  It records only reproducible
provenance evidence and blocks a build until the source and toolchain contracts
are both independently resolved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from ._common import ROOT
except ImportError:  # pragma: no cover - direct CLI invocation
    from _common import ROOT


KNOWN_MISSING_REFS = (
    "../Src/urop_2/custom_ds_twr_initiator.c",
    "../Src/urop_2/custom_ds_twr_responder.c",
    "../Src/custom_code/switching.c",
    "../Src/custom_code/localization_ds_twr_initiatior.c",
    "../Src/custom_code/localization_ds_twr_responder.c",
    "../Src/custom_code/AoA_rtls_tx.c",
    "../Src/custom_code/AoA_rtls_rx.c",
    "../Src/custom_code/AoA_rtls_tx_AI.c",
    "../Src/custom_code/AoA_rtls_rx_AI.c",
    "../Src/custom_code/UART_test.c",
    "../Src/custom_code/rx_diagnostics_cp.c",
    "../Src/custom_code/AoA_rtls_tx_txt.c",
    "../Src/custom_code/AoA_rtls_rx_txt.c",
    "../Src/custom_code/AoA_rtls_rx_two.c",
    "../Src/custom_code/AoA_rtls_tx_two.c",
)

SELECTION_MACROS = {
    "custom_ds_twr_initiator.c": "CUSTOM_DS_TWR_INITIATOR",
    "custom_ds_twr_responder.c": "CUSTOM_DS_TWR_RESPONDER",
    "localization_ds_twr_initiatior.c": "LOCALIZATION_DS_TWR_INIT",
    "localization_ds_twr_responder.c": "LOCALIZATION_DS_TWR_RESP",
}

RESPONSIBILITIES = {
    "custom_ds_twr_initiator.c": "custom DS-TWR initiator application",
    "custom_ds_twr_responder.c": "custom DS-TWR responder application",
    "switching.c": "custom switching experiment application",
    "localization_ds_twr_initiatior.c": "custom localization DS-TWR initiator application",
    "localization_ds_twr_responder.c": "custom localization DS-TWR responder application",
    "UART_test.c": "custom UART experiment application",
    "rx_diagnostics_cp.c": "custom RX diagnostics experiment application",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify_toolchain(map_text: str, installed: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify an exact runtime only when its executable is actually present."""
    matches = sorted(set(re.findall(r"SEGGER Embedded Studio(?: for ARM)? ([0-9]+\.[0-9]+)", map_text)))
    map_version = matches[0] if len(matches) == 1 else None
    exact = bool(map_version and any(item.get("version") == map_version and item.get("executable_sha256") for item in installed))
    return {
        "map_reported_versions": matches,
        "map_reported_version": map_version,
        "installed_versions": [item.get("version") for item in installed],
        "classification": "EXACT_TOOLCHAIN_IDENTIFIED" if exact else ("TOOLCHAIN_FAMILY_IDENTIFIED" if map_version else "TOOLCHAIN_UNRESOLVED"),
        "exact_installed": exact,
        "reason": "MAP library path is historical provenance, not an installed executable hash." if not exact else "Matching installed executable is hash-recorded.",
    }


def is_placeholder_source(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    return bool(re.search(r"\b(?:placeholder|stub)\b|TODO\s*:\s*(?:implement|replace)", text, re.IGNORECASE))


def runtime_header_contract(source_text: str, available_headers: set[str]) -> dict[str, Any]:
    required = sorted(set(re.findall(r'#\s*include\s+"([^"]+)"', source_text)))
    missing = [header for header in required if header not in available_headers]
    return {"required_headers": required, "available_headers": sorted(available_headers), "missing_headers": missing, "status": "RUNTIME_HEADER_MISMATCH" if missing else "RUNTIME_HEADER_CONTRACT_SATISFIED"}


def hash_invariant(expected: dict[str, bytes | str], root: Path) -> dict[str, Any]:
    rows = []
    for relative, expected_value in sorted(expected.items()):
        expected_hash = hashlib.sha256(expected_value).hexdigest() if isinstance(expected_value, bytes) else expected_value
        path = root / relative
        observed_hash = sha256(path) if path.is_file() else None
        rows.append({"path": relative, "expected_sha256": expected_hash, "observed_sha256": observed_hash, "unchanged": expected_hash == observed_hash})
    return {"unchanged": all(row["unchanged"] for row in rows), "files": rows}


def evaluate_source_candidates(candidates: Iterable[Path], expected_sha256: str | None = None) -> dict[str, Any]:
    rows = [{"path": str(item), "sha256": sha256(item), "placeholder": is_placeholder_source(item)} for item in candidates]
    if not rows:
        decision = "NO_CANDIDATE"
    elif any(row["placeholder"] for row in rows):
        decision = "REJECTED_PLACEHOLDER"
    elif expected_sha256 and any(row["sha256"] != expected_sha256 for row in rows):
        decision = "REJECTED_HASH_MISMATCH"
    elif len({row["sha256"] for row in rows}) > 1:
        decision = "REJECTED_AMBIGUOUS"
    else:
        decision = "CANDIDATE_PRESENT_PROVENANCE_UNRESOLVED"
    return {"decision": decision, "candidates": rows, "expected_sha256": expected_sha256}


def classify_reference_usage(reference: str, active_defines: set[str]) -> str:
    macro = SELECTION_MACROS.get(Path(reference).name)
    if macro and macro not in active_defines:
        return "INACTIVE_REFERENCE_PROVEN"
    return "ACTIVE_OR_UNRESOLVED_REFERENCE"


def recovery_gate(toolchain_classification: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_blockers = [row["filename"] if "filename" in row else "test-row" for row in rows if row.get("blocking") or row.get("candidate_decision") != "CANDIDATE_PROVEN"]
    ready = toolchain_classification == "EXACT_TOOLCHAIN_IDENTIFIED" and not source_blockers
    source_tree_not_ready = bool(rows) and len(source_blockers) * 2 >= len(rows)
    return {
        "outcome": "LEGACY_BUILD_ENVIRONMENT_READY" if ready else ("LEGACY_BUILD_ENVIRONMENT_NOT_READY" if toolchain_classification == "TOOLCHAIN_UNRESOLVED" or source_tree_not_ready else "LEGACY_BUILD_ENVIRONMENT_CONDITIONAL"),
        "allow_baseline_build": ready,
        "allow_four_image_build": ready,
        "allow_flash_execute": False,
        "allow_execute": False,
        "hardware_verified": False,
        "source_type": "CODE_INSPECTION",
        "blocking_sources": source_blockers,
        "blocked_actions": ["baseline_build", "four_image_build", "flash", "erase", "reset", "RF", "UART", "logic_analyzer"],
    }


def active_defines(project: Path) -> set[str]:
    selection = project.parent.parent / "Src" / "example_selection.h"
    if not selection.is_file():
        return set()
    return set(re.findall(r"^\s*#define\s+([A-Z0-9_]+)\b", selection.read_text(encoding="utf-8", errors="replace"), re.MULTILINE))


def project_references(project: Path) -> set[str]:
    return set(re.findall(r'<file file_name="([^"]+)"', project.read_text(encoding="utf-8", errors="replace")))


def git_history_exists(root: Path, expected_path: Path) -> bool:
    if not (root / ".git").exists():
        return False
    result = subprocess.run(["git", "-C", str(root), "log", "--all", "--format=%H", "--", expected_path.as_posix()], text=True, capture_output=True, check=False)
    return bool(result.stdout.strip())


def index_exact_candidates(filenames: Iterable[str], roots: list[Path]) -> dict[str, list[Path]]:
    """Scan each read-only tree once; stale Output and vendor SDK trees are not sources."""
    wanted = set(filenames)
    candidates: dict[str, list[Path]] = {filename: [] for filename in wanted}
    for root in roots:
        if root.is_dir():
            for directory, children, files in os.walk(root):
                children[:] = [item for item in children if item not in {".git", "Output", "SDK"}]
                for filename in files:
                    if filename in wanted:
                        candidates[filename].append(Path(directory) / filename)
    return {filename: sorted(set(paths)) for filename, paths in candidates.items()}


def archive_matches(filename: str, roots: list[Path]) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for archive in root.glob("*.zip"):
            try:
                with zipfile.ZipFile(archive) as bundle:
                    for member in bundle.namelist():
                        if Path(member).name == filename:
                            matches.append({"archive": str(archive), "member": member})
            except zipfile.BadZipFile:
                continue
    return matches


def installed_ses() -> list[dict[str, Any]]:
    root = Path(r"C:\Program Files\SEGGER")
    result: list[dict[str, Any]] = []
    if not root.is_dir():
        return result
    for directory in sorted(root.glob("SEGGER Embedded Studio*")):
        match = re.search(r"([0-9]+\.[0-9]+)", directory.name)
        executable = directory / "bin" / "emBuild.exe"
        result.append({"path": str(directory), "version": match.group(1) if match else None, "emBuild": str(executable), "executable_exists": executable.is_file(), "executable_sha256": sha256(executable) if executable.is_file() else None})
    return result


def map_object_present(map_text: str, filename: str) -> bool:
    return bool(re.search(rf"(?:^|/)({re.escape(Path(filename).stem)})\.o\b", map_text, re.MULTILINE))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, required=True, help="Phase 6 disposable SDK sandbox containing the five recorded missing references.")
    parser.add_argument("--related-project", type=Path, required=True, help="Sibling AoA project's SES project used for the remaining recorded references.")
    parser.add_argument("--historical-map", type=Path, required=True)
    parser.add_argument("--search-root", type=Path, action="append", required=True, help="Read-only root to search for exact source filenames.")
    parser.add_argument("--archive-root", type=Path, action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true", help="Replace only a prior evidence set generated by this command.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()) and not args.refresh:
        raise SystemExit(f"[FAIL] refusing to overwrite recovery evidence: {output}")
    sdk_root, related_project, historical_map = args.sdk_root.resolve(), args.related_project.resolve(), args.historical_map.resolve()
    primary_project = sdk_root / "API" / "nRF52840-DK" / "dw3000_api.emProject"
    if not primary_project.is_file() or not related_project.is_file() or not historical_map.is_file():
        raise SystemExit("[FAIL] sdk project, related project, and historical MAP must exist")

    output.mkdir(parents=True, exist_ok=args.refresh)
    map_text = historical_map.read_text(encoding="utf-8", errors="replace")
    installed = installed_ses()
    toolchain = classify_toolchain(map_text, installed)
    syscalls = primary_project.parent / "SEGGER" / "SEGGER_RTT_Syscalls_SES.c"
    syscalls_text = syscalls.read_text(encoding="utf-8", errors="replace") if syscalls.is_file() else ""
    requested_headers = set(re.findall(r'#\s*include\s+"([^"]+)"', syscalls_text))
    available_headers = {
        header
        for header in requested_headers
        if (syscalls.parent / header).is_file()
        or any((Path(installation["path"]) / "include" / header).is_file() for installation in installed)
    }
    runtime_contract = runtime_header_contract(syscalls_text, available_headers)
    project_refs = project_references(primary_project) | project_references(related_project)
    active = active_defines(primary_project) | active_defines(related_project)
    source_roots = [item.resolve() for item in args.search_root]
    candidates_by_filename = index_exact_candidates((Path(item).name for item in KNOWN_MISSING_REFS), source_roots)
    matrix: list[dict[str, Any]] = []
    for reference in KNOWN_MISSING_REFS:
        filename = Path(reference).name
        expected = (primary_project.parent / reference).resolve()
        candidates = evaluate_source_candidates(candidates_by_filename[filename])
        archive = archive_matches(filename, [item.resolve() for item in args.archive_root])
        project_reference_state = "PROJECT_REFERENCE_PRESENT" if reference in project_refs else "RECORDED_PREVIOUS_PROJECT_REFERENCE"
        row = {
            "filename": filename, "project_reference": reference, "project_reference_state": project_reference_state,
            "expected_relative_path": reference, "expected_path": str(expected), "expected_path_exists": expected.exists(),
            "referenced_symbols": [Path(filename).stem], "expected_responsibility": RESPONSIBILITIES.get(filename, "custom AoA/RTLS experiment application"),
            "classification": "custom", "reference_usage": classify_reference_usage(reference, active),
            "git_history_exists": git_history_exists(sdk_root, expected.relative_to(sdk_root)) if expected.is_relative_to(sdk_root) else False,
            "sibling_exact_source_exists": bool(candidates["candidates"]), "archive_exact_source_matches": archive,
            "historical_map_object_present": map_object_present(map_text, filename), "candidate_origin": [item["path"] for item in candidates["candidates"]],
            "candidate_sha256": [item["sha256"] for item in candidates["candidates"]], "candidate_decision": candidates["decision"],
            "confidence": "UNRESOLVED", "blocking": True,
        }
        matrix.append(row)

    source_tree = {
        "classification": "MIXED_INCOMPLETE_OVERLAY_OR_SNAPSHOT",
        "alternatives_not_proven": ["missing Git submodule", "generated source", "stale project reference"],
        "evidence": [
            "15 recorded custom source references have no exact provenance-approved source candidate.",
            "Historical MAP/object records may be stale and are not accepted as fresh-build evidence.",
            "No .gitmodules file was found in the inspected SDK sandbox.",
        ],
        "inactive_reference_rule": "Only an absent selection macro proves INACTIVE_REFERENCE_PROVEN; it never authorizes project-reference deletion or source substitution.",
        "source_copy_performed": False,
    }
    historical = {
        "source_type": "HISTORICAL_ARTIFACT_INSPECTION", "hardware_verified": False,
        "map": {"path": str(historical_map), "sha256": sha256(historical_map), "ses_versions": toolchain["map_reported_versions"], "target_device": "nRF52840_xxAA", "configuration": "Debug", "linker_script": "Setup/SEGGER_Flash.icf"},
        "provenance_limit": "MAP library/object paths establish historical clues only; build timestamp, compiler executable hash, complete source hash, and fresh artifact interval are absent.",
        "prior_fresh_build_failure": "SES 8.28 compilation stopped at SEGGER_RTT_Syscalls_SES.c because __vfprintf.h was absent.",
        "baseline_and_2a2t_hash_invariant": hash_invariant(json.loads((ROOT / "artifacts" / "phase6" / "baseline_firmware_manifest.json").read_text(encoding="utf-8"))["baseline_files"], ROOT),
    }
    inventory = {
        "source_type": "CODE_INSPECTION", "hardware_verified": False, "allow_execute": False,
        "inputs": [{"path": str(item), "exists": item.exists(), "sha256": sha256(item) if item.is_file() else None} for item in [primary_project, related_project, historical_map]],
        "installed_ses": installed, "archive_roots": [str(item) for item in args.archive_root],
    }
    plan = recovery_gate(toolchain["classification"], matrix)
    plan.update({
        "route_A": "Acquire/hash-verify SES 5.68 executable plus complete, origin-proven source tree; then perform one isolated baseline fresh build.",
        "route_B": "Only consider a compatible legacy SES after its runtime/header contract is hash-verified against the recovered source tree.",
        "route_C": "Planning only: analyze newer SES syscall/runtime headers and project schema; do not modify vendor or firmware source.",
        "toolchain_installation": "NOT_PERFORMED; required exact installer/version must be obtained separately and installed side-by-side, outside SES 8.28.",
    })
    log = {"performed": ["project/MAP/session provenance inspection", "exact-filename source search", "ZIP member-name search", "installed SES executable inventory"], "not_performed": ["toolchain install", "source copy", "SDK edit", "build", "flash", "erase", "reset", "RF", "UART", "logic analyzer"], "timestamp_utc": datetime.now(timezone.utc).isoformat()}
    for filename, data in {
        "toolchain_evidence.json": {"source_type": "CODE_INSPECTION", "hardware_verified": False, **toolchain, "installed": installed, "runtime_header_contract": runtime_contract, "syscalls_source": str(syscalls)},
        "missing_source_matrix.json": {"source_type": "CODE_INSPECTION", "hardware_verified": False, "missing_source_count": len(matrix), "sources": matrix},
        "historical_build_provenance.json": historical,
        "source_tree_candidates.json": {"source_type": "CODE_INSPECTION", "hardware_verified": False, **source_tree},
        "recovery_plan.json": plan,
        "investigation_log.json": log,
        "artifact_inventory.json": inventory,
    }.items():
        (output / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"outcome": plan["outcome"], "missing_source_count": len(matrix), "output_dir": str(output), "allow_execute": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
