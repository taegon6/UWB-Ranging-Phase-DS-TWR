from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools.flash_all import plan_flash, validate_flash_plan_approval


def _config() -> dict:
    return {
        "boards": {
            node: {
                "role": "ANCHOR" if node.startswith("A") else "TAG",
                "firmware_target": target,
                "jlink_serial": f"JLINK-{node}",
                "serial_port": f"COM-{node}",
            }
            for node, target in {
                "A1": "anchor_a1",
                "A2": "anchor_a2",
                "T1": "tag_t1",
                "T2": "tag_t2",
            }.items()
        },
        "jlink": {
            "executable": "JLinkExe",
            "device": "nRF52840_xxAA",
            "interface": "SWD",
            "speed_khz": 4000,
            "allow_execute": False,
        },
    }


def _manifest(tmp_path: Path) -> dict:
    rows = []
    for node in ("A1", "A2", "T1", "T2"):
        image = tmp_path / f"{node}.hex"
        image.write_bytes(f"FWID:{node}".encode("ascii"))
        rows.append(
            {
                "node": node,
                "status": "BUILT_UNVERIFIED_HW",
                "image": str(image),
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            }
        )
    return {"mode": "EXECUTE", "status": "BUILD_PASS_UNVERIFIED_HW", "matrix": rows}


def test_four_image_flash_plan_is_hashed_and_uses_safe_reset_order(tmp_path: Path) -> None:
    plan = plan_flash(_config(), _manifest(tmp_path))
    assert [operation["node"] for operation in plan["operations"]] == ["A1", "A2", "T2", "T1"]
    assert plan["reset_order"] == ["A1", "A2", "T2", "T1"]
    assert len(plan["plan_sha256"]) == 64
    assert plan["approval_required"] is True
    assert all(operation["image_sha256"] for operation in plan["operations"])
    assert all("erase" not in "\n".join(operation["script"]).lower() for operation in plan["operations"])
    validate_flash_plan_approval(plan, plan["plan_sha256"])


def test_flash_plan_rejects_stale_or_tampered_image(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    Path(manifest["matrix"][0]["image"]).write_bytes(b"changed-after-build")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        plan_flash(_config(), manifest)


def test_flash_plan_rejects_wrong_approval_hash(tmp_path: Path) -> None:
    plan = plan_flash(_config(), _manifest(tmp_path))
    with pytest.raises(ValueError, match="approval hash"):
        validate_flash_plan_approval(plan, "0" * 64)
