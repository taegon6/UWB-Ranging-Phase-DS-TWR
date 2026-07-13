from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.phase6_ses_recovery import MISSING_SOURCES, build_command, remove_missing_project_entries, validate_fresh_build


def _project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "dw3000_api.emProject"
    project.write_text("\n".join(f'<file file_name="{item}" />' for item in MISSING_SOURCES) + "\n", encoding="utf-8")
    selection = tmp_path / "example_selection.h"
    selection.write_text("//#define CUSTOM_DS_TWR_RESPONDER\n//#define LOCALIZATION_DS_TWR_INIT\n", encoding="utf-8")
    return project, selection


def test_recovery_removes_only_inactive_proven_missing_project_entries(tmp_path: Path) -> None:
    project, selection = _project(tmp_path)
    removed = remove_missing_project_entries(project, selection)
    assert {row["reference"] for row in removed} == set(MISSING_SOURCES)
    assert not project.read_text(encoding="utf-8").strip()


def test_recovery_refuses_to_remove_an_active_optional_source(tmp_path: Path) -> None:
    project, selection = _project(tmp_path)
    selection.write_text("#define CUSTOM_DS_TWR_RESPONDER\n", encoding="utf-8")
    with pytest.raises(ValueError, match="active optional"):
        remove_missing_project_entries(project, selection)


def test_fresh_build_gate_requires_empty_output_artifacts_log_and_marker(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    elf = tmp_path / "baseline.elf"
    hex_file = tmp_path / "baseline.hex"
    elf.write_bytes(b"xx ds_twr_initiator_final yy")
    hex_file.write_bytes(b"hex")
    rows = [{"path": str(item), "mtime_utc": now.isoformat()} for item in (elf, hex_file)]
    assert not validate_fresh_build(before=[], after=rows, log="cc1.exe file.c\nld.exe", start=now, end=now, marker="ds_twr_initiator_final")
    assert "output directory was not empty before build" in validate_fresh_build(before=rows, after=rows, log="cc1", start=now, end=now, marker="ds_twr_initiator_final")
    assert "build log contains no compile/link command" in validate_fresh_build(before=[], after=rows, log="nothing", start=now, end=now, marker="ds_twr_initiator_final")


def test_direct_ses_build_command_never_uses_batch_mode() -> None:
    command = build_command(Path("emBuild.exe"), Path("dw3000_api.emProject"))
    assert "-batch" not in command
    assert command[:5] == ["emBuild.exe", "-rebuild", "-echo", "-verbose", "-config"]
