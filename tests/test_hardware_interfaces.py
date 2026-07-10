from pathlib import Path

import pytest

from hardware import (
    FlashBackend,
    HardwareBackendBundle,
    LogicBackend,
    OutputExistsError,
    SerialBackend,
    create_backend,
    load_yaml,
)
from hardware.device_inventory import ConfigError
from hardware.jlink_backend import JLinkFlashBackend
from hardware.saleae_backend import SaleaeLogicBackend
from hardware.serial_backend import PySerialBackend
from hardware.sigrok_backend import SigrokLogicBackend


ROOT = Path(__file__).resolve().parents[1]


def test_mock_factory_satisfies_all_hal_protocols() -> None:
    config = load_yaml(ROOT / "configs" / "mock_hardware.yaml")
    backend = create_backend("mock", config)

    assert isinstance(backend, FlashBackend)
    assert isinstance(backend, SerialBackend)
    assert isinstance(backend, LogicBackend)
    assert backend.metadata()["source_type"] == "SYNTHETIC"
    assert backend.metadata()["hardware_verified"] is False


@pytest.mark.parametrize(
    ("name", "expected_type"),
    [
        ("jlink", JLinkFlashBackend),
        ("pyserial", PySerialBackend),
        ("saleae", SaleaeLogicBackend),
        ("sigrok", SigrokLogicBackend),
    ],
)
def test_factory_selects_optional_backend_without_touching_hardware(
    name: str, expected_type: type
) -> None:
    config = load_yaml(ROOT / "configs" / "local_hardware.example.yaml")
    assert isinstance(create_backend(name, config), expected_type)


def test_factory_rejects_unknown_backend() -> None:
    with pytest.raises(ConfigError, match="Unknown backend"):
        create_backend("mystery", {})


def test_factory_builds_configured_bundle_without_discovery() -> None:
    config = load_yaml(ROOT / "configs" / "local_hardware.example.yaml")
    bundle = create_backend("real", config)
    assert isinstance(bundle, HardwareBackendBundle)
    assert isinstance(bundle.flash_backend, JLinkFlashBackend)
    assert isinstance(bundle.serial_backend, PySerialBackend)
    assert isinstance(bundle.logic_backend, SigrokLogicBackend)
    assert bundle.metadata()["hardware_verified"] is False


def test_jlink_builds_argv_and_script_but_does_not_execute(tmp_path: Path) -> None:
    config = load_yaml(ROOT / "configs" / "local_hardware.example.yaml")
    backend = JLinkFlashBackend(config)
    device = {
        "node_id": "A1",
        "jlink_serial": "123456789",
        "device": "STM32F429ZI",
        "interface": "SWD",
    }
    image = tmp_path / "anchor_a1.hex"
    command_file = tmp_path / "flash.jlink"

    script = backend.build_script(device, image)
    command = backend.build_command(device, command_file)
    result = backend.flash(device, image)

    assert any("loadfile" in line for line in script)
    assert isinstance(command, list)
    assert "-SelectEmuBySN" in command
    assert "-CommandFile" in command
    assert "-ExitOnError" in command
    assert result["status"] == "PLANNED"
    assert result["hardware_verified"] is False
    assert not command_file.exists()


def test_jlink_rejects_command_token_injection(tmp_path: Path) -> None:
    backend = JLinkFlashBackend({"jlink": {}})
    with pytest.raises(ValueError, match="Unsafe J-Link device"):
        backend.build_command(
            {"device": "STM32\nexit"}, tmp_path / "commands.jlink"
        )


def test_pyserial_capture_requires_explicit_execute_and_protects_output(
    tmp_path: Path,
) -> None:
    backend = PySerialBackend({"serial": {"baud_rate": 115200, "timeout_s": 0.1}})
    output = tmp_path / "uart.bin"
    plan = backend.capture("COM_TEST", output, 0.01)
    assert plan["status"] == "PLANNED"
    assert not output.exists()

    output.write_bytes(b"preserve")
    with pytest.raises(OutputExistsError):
        backend.capture("COM_TEST", output, 0.01)
    assert output.read_bytes() == b"preserve"


def test_sigrok_builder_returns_shell_free_argument_list(tmp_path: Path) -> None:
    backend = SigrokLogicBackend({"sigrok": {"driver": "fx2lafw"}})
    command = backend.build_capture_command(
        {"sample_rate_hz": 24_000_000, "connection": "usb/1-2.3", "channels": {"IRQ_PIN": "D0"}},
        tmp_path / "capture.csv",
        1.0,
    )
    assert isinstance(command, list)
    assert "--output-file" in command
    assert "D0=IRQ_PIN" in command
    assert "fx2lafw:conn=usb/1-2.3" in command
    assert command[command.index("--time") + 1] == "1.000000s"
    assert "--serial-comm" not in command


def test_saleae_dependency_check_is_non_executing() -> None:
    status = SaleaeLogicBackend.dependency_status()
    assert status["source_type"] == "PLANNED"
    assert status["hardware_verified"] is False
    assert isinstance(status["available"], bool)
