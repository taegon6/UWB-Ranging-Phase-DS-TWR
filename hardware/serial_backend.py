"""Optional pyserial adapter with explicit execution and raw-file protection."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from .interfaces import HardwareOperationError, HardwareUnavailableError, OutputExistsError, planned_metadata


class PySerialBackend:
    def __init__(self, config: Mapping[str, Any], output_root: Path | None = None) -> None:
        self.config = dict(config)
        serial_config = self.config.get("serial", {})
        self.serial_config = (
            dict(serial_config) if isinstance(serial_config, Mapping) else {}
        )
        self.output_root = Path(output_root) if output_root else None

    @staticmethod
    def dependency_status() -> dict[str, Any]:
        try:
            import serial

            version = getattr(serial, "__version__", "unknown")
            return planned_metadata(
                backend="pyserial", package="pyserial", available=True, version=version
            )
        except ImportError:
            return planned_metadata(
                backend="pyserial", package="pyserial", available=False, version=None
            )

    def list_ports(self) -> Sequence[dict[str, Any]]:
        try:
            from serial.tools import list_ports
        except ImportError:
            return []
        return [
            planned_metadata(
                backend="pyserial",
                device=item.device,
                description=item.description,
                hwid=item.hwid,
                vid=item.vid,
                pid=item.pid,
                serial_number=item.serial_number,
                discovered=True,
            )
            for item in list_ports.comports()
        ]

    def capture(
        self,
        port: str,
        output: Path,
        duration_s: float,
        *,
        execute: bool = False,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        target = Path(output)
        if target.exists() and not overwrite:
            raise OutputExistsError(f"Refusing to overwrite raw UART file: {target}")
        sidecar = target.with_suffix(target.suffix + ".metadata.json")
        if sidecar.exists() and not overwrite:
            raise OutputExistsError(f"Refusing to overwrite UART metadata: {sidecar}")
        if duration_s <= 0:
            raise ValueError("duration_s must be greater than zero")
        baud_rate = self.serial_config.get("baud_rate")
        if baud_rate is None or str(baud_rate).upper().startswith("TODO"):
            if execute:
                raise HardwareOperationError(
                    "serial.baud_rate must be resolved before UART capture"
                )
        plan = planned_metadata(
            backend="pyserial",
            operation="serial_capture",
            port=port,
            output=str(target),
            duration_s=float(duration_s),
            baud_rate=baud_rate,
            execute_requested=execute,
            status="PLANNED",
        )
        if not execute:
            return plan
        try:
            import serial
        except ImportError as exc:
            raise HardwareUnavailableError("pyserial is not installed") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        byte_count = 0
        chunks = 0
        try:
            with serial.Serial(
                port=port,
                baudrate=int(baud_rate),
                timeout=float(self.serial_config.get("timeout_s", 0.1)),
            ) as connection, target.open("xb" if not overwrite else "wb") as stream:
                while time.monotonic() - start < duration_s:
                    available = max(1, int(getattr(connection, "in_waiting", 0)))
                    payload = connection.read(available)
                    if payload:
                        stream.write(payload)
                        byte_count += len(payload)
                        chunks += 1
        except (OSError, serial.SerialException) as exc:
            raise HardwareOperationError(f"UART capture failed for {port}: {exc}") from exc
        end = time.monotonic()
        metadata = {
            "source_type": "MEASURED",
            "hardware_verified": False,
            "verification_status": "RAW_CAPTURED_NOT_QUALITY_VALIDATED",
            "backend": "pyserial",
            "port": port,
            "baud_rate": int(baud_rate),
            "duration_s": end - start,
            "host_monotonic_start_s": start,
            "host_monotonic_end_s": end,
            "bytes_written": byte_count,
            "chunks_written": chunks,
            "raw_file": str(target),
        }
        sidecar.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        return {**metadata, "operation": "serial_capture", "success": True, "status": "PASS"}


SerialBackend = PySerialBackend
SerialCaptureBackend = PySerialBackend

__all__ = ["PySerialBackend", "SerialBackend", "SerialCaptureBackend"]
