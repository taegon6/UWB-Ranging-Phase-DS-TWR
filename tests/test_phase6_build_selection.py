from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.build_firmware import build_firmware


ROOT = Path(__file__).resolve().parents[1]
SELECTOR = ROOT / "tools" / "set_uwb_example.py"


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        ("ds-2a2t-anchor-a1", ("DS_TWR_2A2T_ANCHOR", "UWB_NODE_A1")),
        ("ds-2a2t-anchor-a2", ("DS_TWR_2A2T_ANCHOR", "UWB_NODE_A2")),
        ("ds-2a2t-tag-t1", ("DS_TWR_2A2T_TAG", "UWB_NODE_T1", "UWB_2A2T_COORDINATOR")),
        ("ds-2a2t-tag-t2", ("DS_TWR_2A2T_TAG", "UWB_NODE_T2", "UWB_2A2T_FOLLOWER")),
    ],
)
def test_selector_emits_exactly_one_phase6_role_set(
    tmp_path: Path, selection: str, expected: tuple[str, ...]
) -> None:
    header = tmp_path / "example_selection.h"
    header.write_text(
        "\n".join(
            f"//#define {name}"
            for name in (
                "DS_TWR_INITIATOR_FINAL",
                "DS_TWR_RESPONDER_FINAL",
                "LOCALIZATION_DS_TWR_INIT",
                "LOCALIZATION_DS_TWR_RESP",
                "CUSTOM_DS_TWR_INITIATOR",
                "CUSTOM_DS_TWR_RESPONDER",
                "DS_TWR_2A2T_TAG",
                "DS_TWR_2A2T_ANCHOR",
                "UWB_NODE_A1",
                "UWB_NODE_A2",
                "UWB_NODE_T1",
                "UWB_NODE_T2",
                "UWB_2A2T_COORDINATOR",
                "UWB_2A2T_FOLLOWER",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(SELECTOR), selection, "--path", str(header)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    active = {
        line.split()[1]
        for line in header.read_text(encoding="utf-8").splitlines()
        if line.startswith("#define ")
    }
    assert set(expected).issubset(active)
    assert "DS_TWR_INITIATOR_FINAL" not in active
    assert "DS_TWR_RESPONDER_FINAL" not in active
    assert not {"LOCALIZATION_DS_TWR_INIT", "LOCALIZATION_DS_TWR_RESP", "CUSTOM_DS_TWR_INITIATOR", "CUSTOM_DS_TWR_RESPONDER"} & active


def test_execute_build_requires_empty_output_and_role_marker(tmp_path: Path) -> None:
    output = tmp_path / "build"
    output.mkdir()
    (output / "stale.hex").write_bytes(b"old")
    config = {
        "boards": {
            node: {
                "role": "ANCHOR" if node.startswith("A") else "TAG",
                "firmware_target": target,
                "firmware_image": f"{node}.hex",
            }
            for node, target in {
                "A1": "anchor_a1",
                "A2": "anchor_a2",
                "T1": "tag_t1",
                "T2": "tag_t2",
            }.items()
        },
        "firmware": {
            "working_directory": str(tmp_path),
            "role_build_commands": {node: [sys.executable, "-c", "pass"] for node in ("A1", "A2", "T1", "T2")},
        },
    }
    with pytest.raises(ValueError, match="empty output directory"):
        build_firmware(config, output, dry_run=False, execute=True)


def test_execute_build_copies_immutable_images_and_records_sha(tmp_path: Path) -> None:
    marker_by_node = {node: f"FWID:{node}" for node in ("A1", "A2", "T1", "T2")}
    for node, marker in marker_by_node.items():
        (tmp_path / f"{node}.hex").write_bytes((marker + "\nimage").encode("ascii"))
    config = {
        "boards": {
            node: {
                "role": "ANCHOR" if node.startswith("A") else "TAG",
                "firmware_target": target,
                "firmware_image": f"{node}.hex",
            }
            for node, target in {
                "A1": "anchor_a1",
                "A2": "anchor_a2",
                "T1": "tag_t1",
                "T2": "tag_t2",
            }.items()
        },
        "firmware": {
            "working_directory": str(tmp_path),
            "role_build_commands": {node: [sys.executable, "-c", "pass"] for node in ("A1", "A2", "T1", "T2")},
            "role_markers": marker_by_node,
        },
    }
    result = build_firmware(config, tmp_path / "build", dry_run=False, execute=True)
    assert result["status"] == "BUILD_PASS_UNVERIFIED_HW"
    for row in result["matrix"]:
        image = Path(row["image"])
        assert image.parent.name == "images"
        assert image.is_file()
        assert row["sha256"]
        assert row["role_marker_verified"] is True
