"""sigrok-cli argument builder and portable CSV-to-edge parser."""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from .interfaces import (
    HardwareOperationError,
    HardwareUnavailableError,
    OutputExistsError,
    planned_metadata,
)


_SAFE_SIGROK_TOKEN = re.compile(r"^[A-Za-z0-9_.:+/=-]+$")


def _safe(value: Any, label: str) -> str:
    token = str(value)
    if not token or not _SAFE_SIGROK_TOKEN.fullmatch(token):
        raise ValueError(f"Unsafe sigrok {label}: {token!r}")
    return token


class SigrokLogicBackend:
    def __init__(self, config: Mapping[str, Any], output_root: Path | None = None) -> None:
        self.config = dict(config)
        raw = self.config.get("sigrok", {})
        self.sigrok_config = dict(raw) if isinstance(raw, Mapping) else {}
        self.output_root = Path(output_root) if output_root else None

    @property
    def executable(self) -> str:
        return str(self.sigrok_config.get("executable", "sigrok-cli"))

    def dependency_status(self) -> dict[str, Any]:
        executable = self.executable
        available = bool(shutil.which(executable) or Path(executable).is_file())
        return planned_metadata(
            backend="sigrok", executable=executable, available=available
        )

    def list_devices(self) -> Sequence[dict[str, Any]]:
        # Avoid touching a USB analyzer during configuration or environment checks.
        return []

    def build_capture_command(
        self, config: Mapping[str, Any], output: Path, duration_s: float
    ) -> list[str]:
        if duration_s <= 0:
            raise ValueError("duration_s must be greater than zero")
        driver = _safe(
            config.get("driver") or self.sigrok_config.get("driver", "fx2lafw"),
            "driver",
        )
        connection = config.get("connection") or self.sigrok_config.get("connection")
        if connection and not str(connection).upper().startswith("TODO"):
            driver = f"{driver}:conn={_safe(connection, 'connection')}"
        sample_rate = _safe(
            config.get("sample_rate_hz")
            or self.sigrok_config.get("sample_rate_hz", 24_000_000),
            "sample rate",
        )
        command = [
            self.executable,
            "--driver",
            driver,
            "--config",
            f"samplerate={sample_rate}",
        ]
        channels = config.get("channels", {})
        if isinstance(channels, Mapping) and channels:
            channel_tokens = []
            for logical_name, physical_name in channels.items():
                if str(physical_name).upper().startswith("TODO"):
                    continue
                channel_tokens.append(
                    f"{_safe(physical_name, 'physical channel')}={_safe(logical_name, 'logical channel')}"
                )
            if channel_tokens:
                command.extend(["--channels", ",".join(channel_tokens)])
        command.extend(
            [
                "--time",
                f"{float(duration_s):.6f}s",
                "--output-format",
                "csv",
                "--output-file",
                str(Path(output).resolve()),
            ]
        )
        return command

    build_command = build_capture_command

    def capture(
        self,
        config: Mapping[str, Any],
        output: Path,
        *,
        duration_s: float | None = None,
        execute: bool = False,
        overwrite: bool = False,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        target = Path(output)
        if target.exists() and not overwrite:
            raise OutputExistsError(f"Refusing to overwrite sigrok capture: {target}")
        selected_duration = float(duration_s or config.get("capture_duration_s", 1.0))
        command = self.build_capture_command(config, target, selected_duration)
        plan = planned_metadata(
            backend="sigrok",
            operation="logic_capture",
            command=command,
            output=str(target),
            duration_s=selected_duration,
            execute_requested=execute,
            status="PLANNED",
        )
        if not execute:
            return plan
        if not self.dependency_status()["available"]:
            raise HardwareUnavailableError(f"sigrok-cli not found: {self.executable}")
        target.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout_s or selected_duration + 30.0,
        )
        if completed.returncode != 0:
            raise HardwareOperationError(
                f"sigrok-cli exited with {completed.returncode}: {completed.stderr.strip()}"
            )
        if not target.is_file():
            raise HardwareOperationError("sigrok-cli reported success but produced no capture")
        return {
            "source_type": "MEASURED",
            "hardware_verified": False,
            "verification_status": "RAW_CAPTURED_NOT_QUALITY_VALIDATED",
            "backend": "sigrok",
            "operation": "logic_capture",
            "success": True,
            "status": "PASS",
            "command": command,
            "output": str(target),
            "bytes_written": target.stat().st_size,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    @staticmethod
    def parse_csv(capture: Path) -> list[dict[str, Any]]:
        """Parse normalized edge CSV or sampled sigrok CSV into edge rows."""

        source = Path(capture)
        if not source.is_file():
            raise HardwareUnavailableError(f"sigrok CSV does not exist: {source}")
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(
                line for line in stream if line.strip() and not line.lstrip().startswith(";")
            )
            fields = list(reader.fieldnames or [])
            rows = list(reader)
        if not fields:
            raise HardwareOperationError(f"sigrok CSV has no header: {source}")
        lower = {field.lower().strip(): field for field in fields}
        time_field = next(
            (
                lower[key]
                for key in ("timestamp_s", "time_s", "time", "seconds")
                if key in lower
            ),
            fields[0],
        )
        if "channel" in lower and "edge" in lower:
            channel_field = lower["channel"]
            edge_field = lower["edge"]
            normalized: list[dict[str, Any]] = []
            for row in rows:
                timestamp_s = float(row[time_field])
                edge = str(row[edge_field]).strip().lower()
                normalized.append(
                    {
                        "timestamp_s": timestamp_s,
                        "timestamp_us": timestamp_s * 1_000_000.0,
                        "channel": row[channel_field],
                        "edge": edge,
                        "value": 1 if edge in {"rising", "rise", "1"} else 0,
                    }
                )
            return normalized
        channel_fields = [field for field in fields if field != time_field]
        previous: dict[str, int] = {}
        edges: list[dict[str, Any]] = []
        for row in rows:
            try:
                timestamp_s = float(row[time_field])
            except (TypeError, ValueError) as exc:
                raise HardwareOperationError(
                    f"Invalid timestamp {row.get(time_field)!r} in {source}"
                ) from exc
            for channel in channel_fields:
                raw = str(row.get(channel, "")).strip().lower()
                if raw in {"1", "high", "true"}:
                    value = 1
                elif raw in {"0", "low", "false"}:
                    value = 0
                else:
                    continue
                old = previous.get(channel)
                previous[channel] = value
                if old is None or old == value:
                    continue
                edges.append(
                    {
                        "timestamp_s": timestamp_s,
                        "timestamp_us": timestamp_s * 1_000_000.0,
                        "channel": channel,
                        "edge": "rising" if value else "falling",
                        "value": value,
                    }
                )
        return edges

    def export_edges(
        self,
        capture: Path,
        output_csv: Path,
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        target = Path(output_csv)
        if target.exists() and not overwrite:
            raise OutputExistsError(f"Refusing to overwrite edge CSV: {target}")
        edges = self.parse_csv(Path(capture))
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as stream:
            fields = ["timestamp_s", "timestamp_us", "channel", "edge", "value"]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(edges)
        return {
            "source_type": "MEASURED",
            "hardware_verified": False,
            "verification_status": "EDGES_EXPORTED_NOT_QUALITY_VALIDATED",
            "backend": "sigrok",
            "operation": "export_edges",
            "success": True,
            "status": "PASS",
            "capture": str(capture),
            "output": str(target),
            "edge_count": len(edges),
        }


SigrokBackend = SigrokLogicBackend

__all__ = ["SigrokBackend", "SigrokLogicBackend"]
