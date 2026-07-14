import copy
from pathlib import Path

import pytest

from hardware.device_inventory import ConfigError, find_placeholders, load_yaml, validate_config


ROOT = Path(__file__).resolve().parents[1]


def test_standalone_timing_experiment_matches_schema() -> None:
    config = load_yaml(ROOT / "configs" / "experiment_timing.example.yaml")
    assert validate_config(config) == []


def test_embedded_mock_timing_experiment_matches_hardware_schema() -> None:
    config = load_yaml(ROOT / "configs" / "mock_hardware.yaml")
    assert "timing_characterization" in config["experiments"]
    assert validate_config(config) == []


def test_invalid_experiment_enum_and_repetition_are_rejected() -> None:
    config = load_yaml(ROOT / "configs" / "experiment_timing.example.yaml")
    invalid = copy.deepcopy(config)
    invalid["protocol_mode"] = "NOT_A_PROTOCOL"
    invalid["repetitions"] = 0
    with pytest.raises(ConfigError) as error:
        validate_config(invalid)
    assert len(error.value.errors) >= 2


def test_calibration_separates_hardware_todos_from_numeric_mock_search() -> None:
    config = load_yaml(ROOT / "configs" / "antenna_calibration.example.yaml")
    placeholders = validate_config(config, allow_placeholders=True)
    search = config["calibration"]["search"]
    assert placeholders == find_placeholders(config)
    assert all(
        str(value).startswith("TODO") for value in search["hardware"].values()
    )
    assert all(
        isinstance(value, int) for value in search["synthetic_mock"].values()
    )
    with pytest.raises(ConfigError, match="dry-run"):
        validate_config(config)


def test_calibration_mock_search_rejects_non_numeric_value() -> None:
    config = load_yaml(ROOT / "configs" / "antenna_calibration.example.yaml")
    config["calibration"]["search"]["synthetic_mock"]["fine_step"] = "TODO_HW_VERIFY"
    with pytest.raises(ConfigError):
        validate_config(config, allow_placeholders=True)


def test_jlink_execute_opt_in_must_be_yaml_boolean() -> None:
    config = load_yaml(ROOT / "configs" / "mock_hardware.yaml")
    config["jlink"] = {"allow_execute": "false"}
    with pytest.raises(ConfigError, match="boolean"):
        validate_config(config)
