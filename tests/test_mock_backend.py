import copy
import csv
import json
from pathlib import Path

import pytest

from hardware import create_backend, load_yaml
from hardware.interfaces import HardwareOperationError, HardwareUnavailableError, OutputExistsError
from hardware.mock_backend import MockBackend


ROOT = Path(__file__).resolve().parents[1]


def config() -> dict:
    return load_yaml(ROOT / "configs" / "mock_hardware.yaml")


def assert_synthetic(result: dict) -> None:
    assert result["source_type"] == "SYNTHETIC"
    assert result["hardware_verified"] is False


def test_mock_success_and_device_metadata() -> None:
    backend = MockBackend(config())
    devices = backend.list_devices()
    ports = backend.list_ports()
    result = backend.flash(devices[0], Path("not-built-yet.hex"))

    assert len(devices) == 4
    assert len(ports) == 4
    assert all(item["source_type"] == "SYNTHETIC" for item in devices + ports)
    assert result["success"] is True
    assert_synthetic(result)


def test_mock_flash_failure_is_reported_without_hardware() -> None:
    cfg = config()
    cfg["mock"]["faults"]["flash_fail_nodes"] = ["A2"]
    backend = create_backend("mock", cfg)
    device = next(item for item in backend.list_devices() if item["node_id"] == "A2")
    result = backend.flash(device, Path("anchor_a2.hex"))
    assert result["success"] is False
    assert result["error"] == "SIMULATED_FLASH_FAILURE"
    assert_synthetic(result)


def test_mock_accepts_compact_mock_only_configuration() -> None:
    backend = MockBackend(
        {"random_seed": 7, "faults": {"flash_failure_probability": 1.0}}
    )
    result = backend.flash({"node_id": "A1"}, Path("unused.hex"))
    assert result["success"] is False
    assert backend.metadata()["random_seed"] == 7
    assert_synthetic(result)


def test_mock_missing_com_port_raises() -> None:
    cfg = config()
    cfg["mock"]["faults"]["missing_com_nodes"] = ["T2"]
    backend = MockBackend(cfg)
    assert "MOCK_T2" not in {item["device"] for item in backend.list_ports()}
    with pytest.raises(HardwareUnavailableError, match="missing"):
        backend.capture_serial("MOCK_T2", Path("unused.bin"), 0.1)


def test_uart_corruption_overflow_timeout_retry_and_missing_link(
    tmp_path: Path,
) -> None:
    cfg = config()
    faults = cfg["mock"]["faults"]
    faults.update(
        {
            "uart_corruption_probability": 0.5,
            "uart_buffer_overflow": True,
            "packet_timeout_probability": 1.0,
            "retry_probability": 1.0,
            "missing_link_probability": 1.0,
        }
    )
    backend = MockBackend(cfg)
    output = tmp_path / "uart.bin"
    result = backend.capture_serial(
        "MOCK_A1", output, 1.0, record_count=32
    )

    assert result["corrupted_record_count"] > 0
    assert result["uart_buffer_overflow"] is True
    assert result["packet_timeout_count"] > 0
    assert result["retry_count"] > 0
    assert result["missing_link_count"] > 0
    assert b"CORRUPTED_UART_RECORD" in output.read_bytes()
    sidecar = json.loads(Path(result["metadata_file"]).read_text(encoding="utf-8"))
    assert_synthetic(sidecar)
    assert_synthetic(result)


def test_mock_uart_fixture_is_deterministic(tmp_path: Path) -> None:
    first = MockBackend(config())
    second = MockBackend(config())
    first_path = tmp_path / "first.bin"
    second_path = tmp_path / "second.bin"
    first.capture_serial("MOCK_T1", first_path, 0.2, record_count=16)
    second.capture_serial("MOCK_T1", second_path, 0.2, record_count=16)
    assert first_path.read_bytes() == second_path.read_bytes()


def test_logic_fixture_contains_mandatory_provenance_and_fault_timing(
    tmp_path: Path,
) -> None:
    cfg = config()
    faults = cfg["mock"]["faults"]
    faults.update(
        {
            "missing_logic_channels": ["PHASE_PROCESS"],
            "irq_outlier_probability": 1.0,
            "increased_spi_duration_us": 100.0,
            "increased_cir_duration_us": 200.0,
            "missing_link_probability": 0.0,
        }
    )
    backend = MockBackend(cfg)
    output = tmp_path / "logic.csv"
    result = backend.capture_logic(
        cfg["logic_analyzer"], output, frame_count=4
    )
    assert result["missing_channels"] == ["PHASE_PROCESS"]
    assert result["irq_outlier_count"] == 4
    assert result["timing_profile_us"]["spi_frame_duration"] == pytest.approx(138.0)
    assert result["timing_profile_us"]["cir_read_duration"] == pytest.approx(605.0)
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows
    assert {row["source_type"] for row in rows} == {"SYNTHETIC"}
    assert {row["hardware_verified"] for row in rows} == {"false"}
    assert "PHASE_PROCESS" not in {row["channel"] for row in rows}
    assert_synthetic(result)


def test_missing_logic_device_and_capture_file_faults(tmp_path: Path) -> None:
    missing_device = config()
    missing_device["mock"]["faults"]["missing_logic_device"] = True
    with pytest.raises(HardwareUnavailableError):
        MockBackend(missing_device).capture_logic(
            missing_device["logic_analyzer"], tmp_path / "no-device.csv"
        )

    missing_file = config()
    missing_file["mock"]["faults"]["missing_logic_capture_file"] = True
    with pytest.raises(HardwareOperationError, match="missing"):
        MockBackend(missing_file).capture_logic(
            missing_file["logic_analyzer"], tmp_path / "no-file.csv"
        )
    assert not (tmp_path / "no-file.csv").exists()


def test_logic_fixture_and_edge_export_are_deterministic(tmp_path: Path) -> None:
    cfg = config()
    cfg["mock"]["faults"]["missing_link_probability"] = 0.0
    backend = MockBackend(cfg)
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    edges = tmp_path / "edges.csv"
    backend.capture_logic(cfg["logic_analyzer"], first, frame_count=3)
    MockBackend(copy.deepcopy(cfg)).capture_logic(
        cfg["logic_analyzer"], second, frame_count=3
    )
    result = backend.export_edges(first, edges)
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert result["edge_count"] > 0
    assert_synthetic(result)


@pytest.mark.parametrize("kind", ["uart", "logic"])
def test_orphan_metadata_sidecar_is_never_overwritten(tmp_path: Path, kind: str) -> None:
    cfg = config()
    backend = MockBackend(cfg)
    output = tmp_path / ("capture.bin" if kind == "uart" else "capture.csv")
    sidecar = output.with_suffix(output.suffix + ".metadata.json")
    sidecar.write_text("preserve me", encoding="utf-8")
    with pytest.raises(OutputExistsError, match="metadata"):
        if kind == "uart":
            backend.capture_serial("MOCK_A1", output, 0.1)
        else:
            backend.capture_logic(cfg["logic_analyzer"], output, frame_count=2)
    assert sidecar.read_text(encoding="utf-8") == "preserve me"
    assert not output.exists()
