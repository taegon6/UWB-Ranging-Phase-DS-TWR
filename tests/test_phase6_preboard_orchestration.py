from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from jsonschema import validate

from tools.generate_phase6_flash_dryrun import build_flash_plan, validate_inventory
from tools.run_phase6_four_image_build import PROJECT, _contains_fwid, _error_count, build_one, write_manifests


def _config() -> dict:
    return {
        "jlink": {"allow_execute": False, "interface": "SWD", "speed_khz": 4000},
        "boards": {
            "A1": {"jlink_serial": "UNRESOLVED", "uart_port": "UNRESOLVED", "image_id": "anchor_a1", "firmware_target": "anchor_a1", "device": "nRF52840_xxAA"},
            "A2": {"jlink_serial": "UNRESOLVED", "uart_port": "UNRESOLVED", "image_id": "anchor_a2", "firmware_target": "anchor_a2", "device": "nRF52840_xxAA"},
            "T1": {"jlink_serial": "UNRESOLVED", "uart_port": "UNRESOLVED", "image_id": "tag_t1", "firmware_target": "tag_t1", "device": "nRF52840_xxAA"},
            "T2": {"jlink_serial": "UNRESOLVED", "uart_port": "UNRESOLVED", "image_id": "tag_t2", "firmware_target": "tag_t2", "device": "nRF52840_xxAA"},
        },
    }


def _rows(status: str = "BUILT_UNVERIFIED_HW") -> list[dict]:
    return [{"node_id": node, "build_status": status, "hex_path": f"{node}.hex", "image_sha256": hashlib.sha256(node.encode()).hexdigest()} for node in ("A1", "A2", "T1", "T2")]


def test_flash_plan_is_dry_run_only_and_t1_is_last() -> None:
    plan = build_flash_plan(_config(), {"images": _rows()})
    assert plan["execution_allowed"] is False
    assert [row["node"] for row in plan["operations"]] == ["A1", "A2", "T2", "T1"]
    assert plan["status"] == "FLASH_PLAN_HARDWARE_MAPPING_REQUIRED"
    assert plan["plan_sha256"] == hashlib.sha256(json.dumps({k: v for k, v in plan.items() if k != "plan_sha256"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_flash_plan_blocks_build_failures_and_does_not_emit_jlink_command() -> None:
    plan = build_flash_plan(_config(), {"images": _rows("BUILD_FAILED")})
    assert plan["status"] == "FLASH_PLAN_BLOCKED_BUILD_FAILURE"
    assert all("J-Link command" in row["command"] for row in plan["operations"])


@pytest.mark.parametrize("field,value", [("device", "STM32F103"), ("image_id", "wrong")])
def test_inventory_rejects_wrong_target_or_image(field: str, value: str) -> None:
    config = _config()
    config["boards"]["A1"][field] = value
    with pytest.raises(ValueError):
        validate_inventory(config)


def test_inventory_rejects_duplicate_concrete_serial_and_execute() -> None:
    config = _config()
    config["boards"]["A1"]["jlink_serial"] = "123"
    config["boards"]["A2"]["jlink_serial"] = "123"
    with pytest.raises(ValueError, match="duplicate"):
        validate_inventory(config)
    config = _config()
    config["jlink"]["allow_execute"] = True
    with pytest.raises(ValueError, match="allow_execute=false"):
        validate_inventory(config)


def test_inventory_rejects_duplicate_concrete_uart_port() -> None:
    config = _config()
    config["boards"]["A1"]["uart_port"] = "COM9"
    config["boards"]["A2"]["uart_port"] = "COM9"
    with pytest.raises(ValueError, match="UART"):
        validate_inventory(config)


def test_fwid_check_and_error_detection_are_strict(tmp_path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"prefix FWID|node=A1|role=ANCHOR suffix")
    assert _contains_fwid(elf, "FWID|node=A1|role=ANCHOR")
    assert not _contains_fwid(elf, "FWID|node=T1|role=TAG_COORDINATOR")
    assert _error_count("Build failed\nfile does not exist\nwarning: x") == 2


def test_build_manifest_is_four_image_schema_shaped(tmp_path) -> None:
    rows = [{"image_id": role, "build_status": "BUILD_FAILED"} for role in ("anchor_a1", "anchor_a2", "tag_t1", "tag_t2")]
    manifest = write_manifests(tmp_path, rows, ["build"] * 4)
    assert manifest["status"] == "BUILD_FAILED"
    saved = json.loads((tmp_path / "build_manifest.json").read_text(encoding="utf-8"))
    assert saved["source_type"] == "CODE_INSPECTION_AND_BUILD"
    assert saved["hardware_verified"] is False
    schema = json.loads((Path("schemas") / "phase6_build_manifest.schema.json").read_text(encoding="utf-8"))
    validate(saved, schema)
    plan_schema = json.loads((Path("schemas") / "phase6_flash_plan.schema.json").read_text(encoding="utf-8"))
    validate(build_flash_plan(_config(), {"images": _rows()}), plan_schema)


def test_build_rejects_stale_sdk_output_before_invoking_toolchain(tmp_path) -> None:
    sandbox = tmp_path / "sdk"
    project = sandbox / "anchor_a1" / PROJECT
    project.parent.mkdir(parents=True)
    project.write_text("project", encoding="utf-8")
    stale = project.parent / "Output" / "Debug" / "old.hex"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"old")
    overlays = tmp_path / "overlay_manifests"
    overlays.mkdir()
    payload = {"role": "anchor_a1", "node_id": "A1", "role_name": "ANCHOR", "fwid": "FWID|node=A1|role=ANCHOR", "source_commit": "x", "overlay_sha256": "a", "config_sha256": "b"}
    (overlays / "anchor_a1.json").write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "out"
    (output / "build_logs").mkdir(parents=True)
    row = build_one("anchor_a1", sandbox, output, overlays, Path(sys.executable))
    assert row["build_status"] == "BUILD_FAILED"
    assert "stale" in row["reason"]
