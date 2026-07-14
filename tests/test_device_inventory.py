import copy
from pathlib import Path

import pytest

from hardware.device_inventory import (
    ConfigError,
    build_inventory,
    find_placeholders,
    load_yaml,
    validate_config,
)


ROOT = Path(__file__).resolve().parents[1]


def test_load_and_validate_mock_configuration() -> None:
    config = load_yaml(ROOT / "configs" / "mock_hardware.yaml")
    assert validate_config(config) == []


def test_placeholder_detection_is_recursive_and_deterministic() -> None:
    config = load_yaml(ROOT / "configs" / "local_hardware.example.yaml")
    paths = find_placeholders(config)
    assert paths == sorted(paths)
    assert "boards.A1.jlink_serial" in paths
    assert "logic_analyzer.sample_rate_hz" in paths
    assert "serial.baud_rate" in paths


def test_placeholders_are_allowed_only_when_explicitly_requested() -> None:
    config = load_yaml(ROOT / "configs" / "local_hardware.example.yaml")
    with pytest.raises(ConfigError, match="dry-run"):
        validate_config(config)
    allowed = validate_config(config, allow_placeholders=True)
    assert allowed == find_placeholders(config)


def test_build_inventory_maps_each_role_and_target() -> None:
    config = load_yaml(ROOT / "configs" / "mock_hardware.yaml")
    inventory = build_inventory(config)
    assert [item["node_id"] for item in inventory] == ["A1", "A2", "T1", "T2"]
    assert [item["role"] for item in inventory] == ["ANCHOR", "ANCHOR", "TAG", "TAG"]
    assert inventory[0]["firmware_target"] == "anchor_a1"
    assert inventory[3]["firmware_target"] == "tag_t2"


def test_duplicate_physical_mapping_is_rejected() -> None:
    config = load_yaml(ROOT / "configs" / "mock_hardware.yaml")
    duplicate = copy.deepcopy(config)
    duplicate["boards"]["A2"]["serial_port"] = duplicate["boards"]["A1"]["serial_port"]
    with pytest.raises(ConfigError, match="duplicates"):
        validate_config(duplicate)
    with pytest.raises(ConfigError, match="duplicates"):
        build_inventory(duplicate)


def test_load_yaml_rejects_non_mapping(tmp_path: Path) -> None:
    source = tmp_path / "bad.yaml"
    source.write_text("- one\n- two\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="root must be a mapping"):
        load_yaml(source)
