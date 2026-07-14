"""Shared run layout, manifest, and provenance utilities."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

RUN_STAGES = [
    "VALIDATE_CONFIG",
    "CHECK_ENVIRONMENT",
    "DISCOVER_DEVICES",
    "BUILD",
    "FLASH",
    "RESET_AND_SYNC",
    "START_LOGIC_CAPTURE",
    "START_UART_CAPTURE",
    "RUN_EXPERIMENT",
    "STOP_CAPTURE",
    "VALIDATE_RAW_DATA",
    "ANALYZE",
    "GENERATE_REPORT",
    "ARCHIVE",
]


@dataclass
class StageRecord:
    name: str
    status: str
    duration_s: float
    reason: str = ""


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(config).encode("utf-8")).hexdigest()


def git_snapshot(root: Path) -> dict[str, Any]:
    def command(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return completed.stdout.strip()

    try:
        status = command("status", "--porcelain=v1", "--untracked-files=normal")
        return {
            "git_commit": command("rev-parse", "HEAD"),
            "git_branch": command("branch", "--show-current"),
            "working_tree_dirty": bool(status),
            "tracked_diff": command("diff", "--stat"),
            "untracked_files": command("ls-files", "--others", "--exclude-standard").splitlines(),
        }
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {
            "git_commit": "UNAVAILABLE",
            "git_branch": "UNAVAILABLE",
            "working_tree_dirty": True,
            "tracked_diff": "UNAVAILABLE",
            "untracked_files": [],
        }


def create_run_directory(
    results_root: Path,
    experiment_id: str,
    *,
    backend: str = "mock",
    now: datetime | None = None,
) -> tuple[str, Path]:
    now = now or datetime.now().astimezone()
    date_prefix = now.strftime("%Y-%m-%d")
    run_class = "mock_pre-hardware" if backend == "mock" else "real_unverified-hardware"
    base = f"{date_prefix}_{experiment_id}_{run_class}"
    results_root.mkdir(parents=True, exist_ok=True)
    existing = sorted(results_root.glob(f"{base}_run*"))
    run_number = len(existing) + 1
    run_id = f"{base}_run{run_number:02d}_{uuid.uuid4().hex[:8]}"
    run_dir = results_root / run_id
    run_dir.mkdir()
    for relative in [
        "config_snapshot",
        "source_snapshot",
        "firmware",
        "raw/uart",
        "raw/logic",
        "intermediate",
        "analysis",
        "figures",
    ]:
        (run_dir / relative).mkdir(parents=True)
    return run_id, run_dir


_SNAPSHOT_EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "results",
}


def _snapshot_source_files(repository_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in repository_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(repository_root)
        if any(part in _SNAPSHOT_EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(repository_root).as_posix())


def _git_text(repository_root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=repository_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError:
        return "git executable unavailable\n"
    output = completed.stdout
    if completed.stderr:
        output += ("\n" if output else "") + completed.stderr
    return output


def write_source_snapshot(
    repository_root: Path,
    output_dir: Path,
    *,
    extra_sources: list[Path] | None = None,
) -> dict[str, Any]:
    """Record tracked diffs plus hashes for tracked and untracked source files."""

    output_dir.mkdir(parents=True, exist_ok=False)
    flags = "source_type = SYNTHETIC\nhardware_verified = false\n"
    (output_dir / "git_status.txt").write_text(
        flags + _git_text(repository_root, "status", "--porcelain=v1", "--untracked-files=all"),
        encoding="utf-8",
    )
    (output_dir / "git_diff.patch").write_text(
        flags + _git_text(repository_root, "diff", "--binary", "HEAD", "--"),
        encoding="utf-8",
    )
    untracked = _git_text(repository_root, "ls-files", "--others", "--exclude-standard")
    (output_dir / "untracked_files.txt").write_text(flags + untracked, encoding="utf-8")

    inventory: list[dict[str, Any]] = []
    hash_lines = ["# source_type = SYNTHETIC", "# hardware_verified = false"]
    for path in _snapshot_source_files(repository_root):
        relative = path.relative_to(repository_root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        inventory.append({"path": relative, "sha256": digest, "size_bytes": path.stat().st_size})
        hash_lines.append(f"{digest}  {relative}")
    (output_dir / "source_hashes.txt").write_text("\n".join(hash_lines) + "\n", encoding="utf-8")
    write_json(
        output_dir / "source_inventory.json",
        {
            "source_type": "SYNTHETIC",
            "hardware_verified": False,
            "snapshot_type": "SOURCE_CODE",
            "file_count": len(inventory),
            "files": inventory,
        },
    )
    for source in extra_sources or []:
        if source.exists():
            shutil.copy2(source, output_dir / source.name)
    return {"file_count": len(inventory), "source_type": "SYNTHETIC", "hardware_verified": False}


def exclusive_write_bytes(path: Path, data: bytes) -> None:
    """Create a raw file exactly once."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def base_manifest(
    *,
    run_id: str,
    backend: str,
    config: dict[str, Any],
    repository_root: Path,
    start_time: str,
) -> dict[str, Any]:
    git = git_snapshot(repository_root)
    return {
        "run_id": run_id,
        "source_type": "SYNTHETIC" if backend == "mock" else "UNVERIFIED_HW",
        "hardware_verified": False,
        "backend": backend,
        "git_commit": git["git_commit"],
        "git_branch": git["git_branch"],
        "working_tree_dirty": git["working_tree_dirty"],
        "tracked_diff": git["tracked_diff"],
        "untracked_files": git["untracked_files"],
        "config_hash": config_hash(config),
        "firmware_hashes": {},
        "start_time": start_time,
        "end_time": None,
        "status": "RUNNING",
        "stages": [],
    }


def append_stage(manifest: dict[str, Any], stage: StageRecord) -> None:
    manifest.setdefault("stages", []).append(asdict(stage))


def validate_stage_order(stages: list[dict[str, Any]]) -> bool:
    indexes = [RUN_STAGES.index(stage["name"]) for stage in stages]
    return indexes == sorted(indexes) and len(indexes) == len(set(indexes))
