"""Deterministic, hardware-free backend for the 2A2T experiment pipeline."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Mapping, Sequence

from .device_inventory import EXPECTED_NODES, build_inventory
from .interfaces import (
    HardwareOperationError,
    HardwareUnavailableError,
    OutputExistsError,
    synthetic_metadata,
)


DEFAULT_TIMING_US: dict[str, float] = {
    "irq_latency": 7.2,
    "isr_duration": 18.0,
    "spi_status_duration": 6.0,
    "spi_frame_duration": 38.0,
    "cir_read_duration": 405.0,
    "phase_processing_duration": 52.0,
    "uart_enqueue_duration": 5.0,
    "uart_physical_tx_duration": 310.0,
    "frame_period": 10_000.0,
}

DEFAULT_CHANNELS: dict[str, int] = {
    "IRQ_PIN": 0,
    "ISR_ACTIVE": 1,
    "SPI_ACTIVE": 2,
    "SPI_STATUS": 2,
    "SPI_FRAME": 3,
    "UART_ENQUEUE": 4,
    "UART_TX": 5,
    "CIR_READ": 6,
    "PHASE_PROCESS": 7,
}


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _new_output(path: Path, overwrite: bool, *, companions: tuple[Path, ...] = ()) -> Path:
    resolved = Path(path)
    existing = [candidate for candidate in (resolved, *companions) if candidate.exists()]
    if existing and not overwrite:
        raise OutputExistsError(
            "Refusing to overwrite raw output or metadata: "
            + ", ".join(str(candidate) for candidate in existing)
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


class MockBackend:
    """Unified deterministic backend with Flash, Serial, and Logic adapters.

    Faults may be placed directly below ``mock`` or below ``mock.faults``.
    Every returned result and generated fixture contains
    ``source_type=SYNTHETIC`` and ``hardware_verified=false``.
    """

    def __init__(
        self, config: dict[str, Any], output_root: Path | None = None
    ) -> None:
        self.config = dict(config)
        # Accept either the complete hardware YAML or a mock-only mapping. This
        # keeps unit tests and small fixture generators lightweight.
        raw_mock = self.config.get("mock", self.config)
        self.mock_config = dict(raw_mock) if isinstance(raw_mock, Mapping) else {}
        raw_faults = self.mock_config.get("faults", {})
        self.faults = dict(raw_faults) if isinstance(raw_faults, Mapping) else {}
        self.output_root = Path(output_root) if output_root is not None else None
        self.seed = int(self.mock_config.get("random_seed", 20260710))
        self.history: list[dict[str, Any]] = []
        self.flash_backend = MockFlashBackend(self)
        self.serial_backend = MockSerialBackend(self)
        self.logic_backend = MockLogicBackend(self)

    def metadata(self) -> dict[str, Any]:
        return synthetic_metadata(backend="mock", random_seed=self.seed)

    def _fault(self, key: str, default: Any = None) -> Any:
        if key in self.faults:
            return self.faults[key]
        return self.mock_config.get(key, default)

    def _fault_any(self, *keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in self.faults or key in self.mock_config:
                return self._fault(key)
        return default

    def _rng(self, context: str) -> random.Random:
        digest = hashlib.sha256(f"{self.seed}:{context}".encode("utf-8")).digest()
        return random.Random(int.from_bytes(digest[:8], "big"))

    def _probability(self, key: str, context: str) -> bool:
        probability = float(self._fault(key, 0.0) or 0.0)
        return self._rng(f"probability:{key}:{context}").random() < probability

    def _record(self, operation: str, **fields: Any) -> dict[str, Any]:
        result = synthetic_metadata(operation=operation, **fields)
        self.history.append(dict(result))
        return result

    def _inventory(self) -> list[dict[str, Any]]:
        try:
            return build_inventory(self.config)
        except Exception:
            return [
                {
                    "node_id": node,
                    "role": "ANCHOR" if node.startswith("A") else "TAG",
                    "jlink_serial": f"MOCK-JLINK-{node}",
                    "serial_port": f"MOCK_{node}",
                    "firmware_target": (
                        f"anchor_{node.lower()}" if node.startswith("A") else f"tag_{node.lower()}"
                    ),
                }
                for node in EXPECTED_NODES
            ]

    # Convenience methods keep the unified object usable by simple runners.
    def list_devices(self, kind: str = "flash") -> Sequence[dict[str, Any]]:
        if kind.lower() in {"logic", "logic_analyzer", "analyzer"}:
            return self.logic_backend.list_devices()
        return self.flash_backend.list_devices()

    def list_ports(self) -> Sequence[dict[str, Any]]:
        return self.serial_backend.list_ports()

    def flash(self, device: Mapping[str, Any], image: Path, **kwargs: Any) -> dict[str, Any]:
        return self.flash_backend.flash(device, image, **kwargs)

    def reset(self, device: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
        return self.flash_backend.reset(device, **kwargs)

    def capture_serial(
        self, port: str, output: Path, duration_s: float, **kwargs: Any
    ) -> dict[str, Any]:
        return self.serial_backend.capture(port, output, duration_s, **kwargs)

    def capture_logic(
        self, config: Mapping[str, Any], output: Path, **kwargs: Any
    ) -> dict[str, Any]:
        return self.logic_backend.capture(config, output, **kwargs)

    def capture(self, source: Any, output: Path, duration_s: float | None = None, **kwargs: Any) -> dict[str, Any]:
        """Dispatch Protocol-style ``capture`` calls by first-argument type."""

        if isinstance(source, str):
            if duration_s is None:
                raise ValueError("duration_s is required for serial capture")
            return self.capture_serial(source, output, duration_s, **kwargs)
        return self.capture_logic(source, output, duration_s=duration_s, **kwargs)

    def export_edges(self, capture: Path, output_csv: Path, **kwargs: Any) -> dict[str, Any]:
        return self.logic_backend.export_edges(capture, output_csv, **kwargs)


class MockFlashBackend:
    def __init__(self, owner: MockBackend) -> None:
        self.owner = owner

    def list_devices(self) -> Sequence[dict[str, Any]]:
        missing = {str(item) for item in self.owner._fault("missing_jlink_nodes", []) or []}
        devices: list[dict[str, Any]] = []
        for board in self.owner._inventory():
            node = str(board.get("node_id"))
            if node in missing:
                continue
            devices.append(
                synthetic_metadata(
                    node_id=node,
                    identifier=board.get("jlink_serial", f"MOCK-JLINK-{node}"),
                    role=board.get("role"),
                    backend="mock",
                )
            )
        return devices

    def flash(
        self,
        device: Mapping[str, Any],
        image: Path,
        *,
        execute: bool = False,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        node = str(device.get("node_id") or device.get("name") or device.get("identifier"))
        explicit_failures = {
            str(item)
            for item in self.owner._fault_any(
                "flash_fail_nodes", "flash_failure_nodes", default=[]
            )
            or []
        }
        failed = node in explicit_failures or self.owner._probability(
            "flash_failure_probability", node
        )
        return self.owner._record(
            "flash",
            node_id=node,
            image=str(Path(image)),
            image_exists=Path(image).is_file(),
            execute_requested=bool(execute),
            success=not failed,
            status="FAIL" if failed else "PASS",
            error="SIMULATED_FLASH_FAILURE" if failed else None,
        )

    def reset(
        self, device: Mapping[str, Any], *, execute: bool = False, **_kwargs: Any
    ) -> dict[str, Any]:
        node = str(device.get("node_id") or device.get("name") or device.get("identifier"))
        return self.owner._record(
            "reset", node_id=node, execute_requested=bool(execute), success=True, status="PASS"
        )


class MockSerialBackend:
    def __init__(self, owner: MockBackend) -> None:
        self.owner = owner

    def list_ports(self) -> Sequence[dict[str, Any]]:
        missing_nodes = {
            str(item) for item in self.owner._fault("missing_com_nodes", []) or []
        }
        missing_ports = {
            str(item) for item in self.owner._fault("missing_com_ports", []) or []
        }
        missing_com_port = self.owner._fault("missing_com_port")
        if isinstance(missing_com_port, str):
            missing_ports.add(missing_com_port)
        elif missing_com_port is True:
            missing_ports.update(
                str(board.get("serial_port") or f"MOCK_{board.get('node_id')}")
                for board in self.owner._inventory()
            )
        ports: list[dict[str, Any]] = []
        for board in self.owner._inventory():
            node = str(board.get("node_id"))
            port = str(board.get("serial_port") or f"MOCK_{node}")
            if node in missing_nodes or port in missing_ports:
                continue
            ports.append(
                synthetic_metadata(
                    node_id=node,
                    device=port,
                    description=f"Synthetic UART for {node}",
                    backend="mock",
                )
            )
        return ports

    def capture(
        self,
        port: str,
        output: Path,
        duration_s: float,
        *,
        execute: bool = False,
        overwrite: bool = False,
        record_count: int | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        available = {str(item["device"]): item for item in self.list_ports()}
        if port not in available:
            raise HardwareUnavailableError(f"Synthetic COM port is missing: {port}")
        if duration_s <= 0:
            raise ValueError("duration_s must be greater than zero")
        raw_target = Path(output)
        sidecar = raw_target.with_suffix(raw_target.suffix + ".metadata.json")
        target = _new_output(raw_target, overwrite, companions=(sidecar,))
        count = int(record_count or max(8, round(duration_s * 20)))
        rng = self.owner._rng(f"uart:{port}:{duration_s}:{count}")
        corruption_probability = float(
            self.owner._fault("uart_corruption_probability", 0.0) or 0.0
        )
        overflow = bool(
            self.owner._fault_any(
                "uart_buffer_overflow", "uart_overflow", default=False
            )
        ) or self.owner._probability(
            "uart_overflow_probability", port
        )
        timeout_probability = float(
            self.owner._fault_any(
                "packet_timeout_probability", "timeout_probability", default=0.0
            )
            or 0.0
        )
        retry_probability = float(
            self.owner._fault("retry_probability", timeout_probability) or 0.0
        )
        missing_link_probability = float(
            self.owner._fault("missing_link_probability", 0.0) or 0.0
        )
        node = str(available[port].get("node_id", "UNKNOWN"))
        corrupted = 0
        timeout_count = 0
        retry_count = 0
        missing_link_count = 0
        header = synthetic_metadata(
            record_type="CAPTURE_HEADER",
            backend="mock",
            port=port,
            node_id=node,
            duration_s=float(duration_s),
        )
        with target.open("wb") as stream:
            stream.write((json.dumps(header, sort_keys=True) + "\n").encode("utf-8"))
            for index in range(count):
                if rng.random() < corruption_probability:
                    stream.write(b"\xff\x00CORRUPTED_UART_RECORD\n")
                    corrupted += 1
                    continue
                timed_out = rng.random() < timeout_probability
                retried = timed_out or rng.random() < retry_probability
                missing_link = rng.random() < missing_link_probability
                timeout_count += int(timed_out)
                retry_count += int(retried)
                missing_link_count += int(missing_link)
                record = synthetic_metadata(
                    record_type="RANGE",
                    sequence=index,
                    node_id=node,
                    superframe_id=index // 4,
                    link=("A1T1", "A2T1", "A1T2", "A2T2")[index % 4],
                    range_m=round(1.25 + rng.gauss(0.0, 0.015), 6),
                    packet_timeout=timed_out,
                    retry_count=1 if retried else 0,
                    link_present=not missing_link,
                )
                stream.write((json.dumps(record, sort_keys=True) + "\n").encode("utf-8"))
            if overflow:
                marker = synthetic_metadata(
                    record_type="UART_OVERFLOW", dropped_bytes=128, port=port
                )
                stream.write((json.dumps(marker, sort_keys=True) + "\n").encode("utf-8"))
        sidecar_payload = synthetic_metadata(
            backend="mock",
            port=port,
            node_id=node,
            raw_file=str(target),
            bytes_written=target.stat().st_size,
            records_requested=count,
            corrupted_record_count=corrupted,
            uart_buffer_overflow=overflow,
            packet_timeout_count=timeout_count,
            retry_count=retry_count,
            missing_link_count=missing_link_count,
        )
        sidecar.write_text(json.dumps(sidecar_payload, indent=2) + "\n", encoding="utf-8")
        return self.owner._record(
            "serial_capture",
            success=True,
            status="PASS",
            execute_requested=bool(execute),
            port=port,
            output=str(target),
            metadata_file=str(sidecar),
            bytes_written=target.stat().st_size,
            records_requested=count,
            corrupted_record_count=corrupted,
            uart_buffer_overflow=overflow,
            packet_timeout_count=timeout_count,
            retry_count=retry_count,
            missing_link_count=missing_link_count,
        )


class MockLogicBackend:
    def __init__(self, owner: MockBackend) -> None:
        self.owner = owner

    def list_devices(self) -> Sequence[dict[str, Any]]:
        if bool(
            self.owner._fault_any(
                "missing_logic_device", "missing_logic", default=False
            )
        ):
            return []
        logic = self.owner.config.get("logic_analyzer", {})
        device_id = logic.get("device_id", "MOCK-LOGIC-001") if isinstance(logic, Mapping) else "MOCK-LOGIC-001"
        return [
            synthetic_metadata(
                device_id=device_id,
                description="Synthetic 8-channel logic analyzer",
                backend="mock",
            )
        ]

    def _timing_profile(self) -> dict[str, float]:
        profile: dict[str, Any] = {}
        raw = self.owner.mock_config.get("timing_profile", {})
        if isinstance(raw, Mapping):
            profile.update(raw)
        elif isinstance(raw, str):
            source = Path(raw)
            if not source.is_absolute():
                source = Path.cwd() / source
            if source.is_file():
                try:
                    import yaml

                    loaded = yaml.safe_load(source.read_text(encoding="utf-8"))
                    if isinstance(loaded, Mapping):
                        profile.update(loaded)
                except Exception as exc:  # deterministic test adapter: surface bad fixture
                    raise HardwareOperationError(
                        f"Unable to read mock timing profile {source}: {exc}"
                    ) from exc
        result = dict(DEFAULT_TIMING_US)
        for key, value in profile.items():
            normalized = str(key).removesuffix("_us")
            if normalized in result and isinstance(value, (int, float)):
                result[normalized] = float(value)
        spi_scale = float(self.owner._fault("spi_duration_scale", 1.0) or 1.0)
        cir_scale = float(self.owner._fault("cir_duration_scale", 1.0) or 1.0)
        for key in ("spi_status_duration", "spi_frame_duration"):
            result[key] *= spi_scale
        result["cir_read_duration"] *= cir_scale
        result["spi_frame_duration"] += float(
            self.owner._fault_any(
                "increased_spi_duration_us", "spi_duration_increase_us", default=0.0
            )
            or 0.0
        )
        result["cir_read_duration"] += float(
            self.owner._fault_any(
                "increased_cir_duration_us", "cir_duration_increase_us", default=0.0
            )
            or 0.0
        )
        return result

    def _channels(self, capture_config: Mapping[str, Any]) -> dict[str, Any]:
        raw = capture_config.get("channels")
        if not isinstance(raw, Mapping):
            logic = self.owner.config.get("logic_analyzer", {})
            raw = logic.get("channels", {}) if isinstance(logic, Mapping) else {}
        channels = dict(DEFAULT_CHANNELS)
        if isinstance(raw, Mapping):
            channels.update(raw)
        missing = {
            str(value) for value in self.owner._fault("missing_logic_channels", []) or []
        }
        singular = self.owner._fault("missing_logic_channel")
        if singular:
            missing.add(str(singular))
        return {
            key: value
            for key, value in channels.items()
            if str(key) not in missing and str(value) not in missing
        }

    @staticmethod
    def _add_pulse(
        rows: list[dict[str, Any]], channel: str, frame: int, start_us: float, duration_us: float
    ) -> None:
        for edge, value, timestamp in (
            ("rising", 1, start_us),
            ("falling", 0, start_us + max(duration_us, 0.001)),
        ):
            rows.append(
                {
                    "timestamp_s": f"{timestamp / 1_000_000.0:.9f}",
                    "timestamp_us": f"{timestamp:.6f}",
                    "channel": channel,
                    "edge": edge,
                    "value": value,
                    "frame_id": frame,
                    "source_type": "SYNTHETIC",
                    "hardware_verified": "false",
                }
            )

    def capture(
        self,
        config: Mapping[str, Any],
        output: Path,
        *,
        duration_s: float | None = None,
        execute: bool = False,
        overwrite: bool = False,
        frame_count: int | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not self.list_devices():
            raise HardwareUnavailableError("Synthetic logic analyzer is missing")
        if bool(
            self.owner._fault_any(
                "missing_logic_capture_file", "missing_logic_file", default=False
            )
        ):
            raise HardwareOperationError("Simulated logic capture file is missing")
        raw_target = Path(output)
        sidecar = raw_target.with_suffix(raw_target.suffix + ".metadata.json")
        target = _new_output(raw_target, overwrite, companions=(sidecar,))
        profile = self._timing_profile()
        count = int(frame_count or config.get("frame_count", 64))
        if duration_s is not None:
            count = max(1, min(count, int(float(duration_s) * 1_000_000 / profile["frame_period"])))
        channels = self._channels(config)
        required = {
            "IRQ_PIN",
            "ISR_ACTIVE",
            "SPI_ACTIVE",
            "SPI_STATUS",
            "SPI_FRAME",
            "CIR_READ",
            "PHASE_PROCESS",
            "UART_ENQUEUE",
            "UART_TX",
        }
        missing_channels = sorted(required - set(channels))
        jitter_us = float(self.owner._fault("pulse_jitter_us", 0.25) or 0.0)
        irq_outlier_probability = float(
            self.owner._fault("irq_outlier_probability", 0.0) or 0.0
        )
        irq_outlier_us = float(self.owner._fault("irq_outlier_us", 25.0) or 25.0)
        missing_link_probability = float(
            self.owner._fault("missing_link_probability", 0.0) or 0.0
        )
        rows: list[dict[str, Any]] = []
        outlier_count = 0
        omitted_frames = 0
        rng = self.owner._rng(f"logic:{count}:{sorted(channels)}")
        for frame in range(count):
            if rng.random() < missing_link_probability:
                omitted_frames += 1
                continue
            base = frame * profile["frame_period"]

            # Virtual marker used by the software timing analyzer. It is not a
            # claim that an additional physical GPIO has been assigned.
            rows.append(
                {
                    "timestamp_s": f"{base / 1_000_000.0:.9f}",
                    "timestamp_us": f"{base:.6f}",
                    "channel": "FRAME_START",
                    "edge": "rising",
                    "value": 1,
                    "frame_id": frame,
                    "source_type": "SYNTHETIC",
                    "hardware_verified": "false",
                }
            )

            def jitter(value: float) -> float:
                return max(0.001, value + rng.gauss(0.0, jitter_us))

            irq_latency = jitter(profile["irq_latency"])
            if rng.random() < irq_outlier_probability:
                irq_latency += irq_outlier_us
                outlier_count += 1
            isr_start = base + irq_latency
            if "IRQ_PIN" in channels:
                self._add_pulse(rows, "IRQ_PIN", frame, base, jitter(700.0))
            if "ISR_ACTIVE" in channels:
                self._add_pulse(
                    rows, "ISR_ACTIVE", frame, isr_start, jitter(profile["isr_duration"])
                )
            cursor = isr_start + 2.0
            if "SPI_ACTIVE" in channels:
                self._add_pulse(
                    rows,
                    "SPI_ACTIVE",
                    frame,
                    cursor,
                    jitter(profile["spi_status_duration"]),
                )
            sequence = (
                ("SPI_STATUS", "spi_status_duration", 3.0),
                ("SPI_FRAME", "spi_frame_duration", 3.0),
                ("CIR_READ", "cir_read_duration", 4.0),
                ("PHASE_PROCESS", "phase_processing_duration", 3.0),
                ("UART_ENQUEUE", "uart_enqueue_duration", 2.0),
                ("UART_TX", "uart_physical_tx_duration", 0.0),
            )
            for channel, metric, gap in sequence:
                duration = jitter(profile[metric])
                if channel in channels:
                    self._add_pulse(rows, channel, frame, cursor, duration)
                cursor += duration + gap
        rows.sort(key=lambda row: (float(row["timestamp_us"]), str(row["channel"])))
        fields = [
            "timestamp_s",
            "timestamp_us",
            "channel",
            "edge",
            "value",
            "frame_id",
            "source_type",
            "hardware_verified",
        ]
        with target.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        sidecar_payload = synthetic_metadata(
            backend="mock",
            capture_file=str(target),
            frame_count_requested=count,
            frame_count_omitted=omitted_frames,
            edge_count=len(rows),
            missing_channels=missing_channels,
            irq_outlier_count=outlier_count,
            timing_profile_us=profile,
        )
        sidecar.write_text(json.dumps(sidecar_payload, indent=2) + "\n", encoding="utf-8")
        return self.owner._record(
            "logic_capture",
            success=True,
            status="PASS" if not missing_channels else "PASS_WITH_MISSING_CHANNELS",
            execute_requested=bool(execute),
            output=str(target),
            metadata_file=str(sidecar),
            edge_count=len(rows),
            frame_count_requested=count,
            frame_count_omitted=omitted_frames,
            missing_channels=missing_channels,
            irq_outlier_count=outlier_count,
            timing_profile_us=profile,
        )

    def export_edges(
        self,
        capture: Path,
        output_csv: Path,
        *,
        overwrite: bool = False,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        source = Path(capture)
        if not source.is_file():
            raise HardwareUnavailableError(f"Logic capture does not exist: {source}")
        target = _new_output(Path(output_csv), overwrite)
        if source.resolve() == target.resolve():
            raise OutputExistsError("Capture and edge-output paths must differ")
        row_count = 0
        with source.open("r", encoding="utf-8", newline="") as input_stream:
            reader = csv.DictReader(input_stream)
            fieldnames = list(reader.fieldnames or [])
            required = {"channel", "edge"}
            if not required.issubset(fieldnames):
                raise HardwareOperationError(
                    f"Capture is not a normalized edge CSV; fields={fieldnames}"
                )
            output_fields = list(fieldnames)
            for name in ("source_type", "hardware_verified"):
                if name not in output_fields:
                    output_fields.append(name)
            with target.open("w", encoding="utf-8", newline="") as output_stream:
                writer = csv.DictWriter(output_stream, fieldnames=output_fields)
                writer.writeheader()
                for row in reader:
                    row["source_type"] = "SYNTHETIC"
                    row["hardware_verified"] = "false"
                    writer.writerow(row)
                    row_count += 1
        return self.owner._record(
            "logic_export_edges",
            success=True,
            status="PASS",
            capture=str(source),
            output=str(target),
            edge_count=row_count,
        )

    generate_fixture = capture


MockHardwareBackend = MockBackend

__all__ = [
    "DEFAULT_CHANNELS",
    "DEFAULT_TIMING_US",
    "MockBackend",
    "MockHardwareBackend",
    "MockFlashBackend",
    "MockLogicBackend",
    "MockSerialBackend",
]
