"""Safe J-Link command construction with an explicit execution opt-in."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .device_inventory import build_inventory
from .interfaces import (
    HardwareOperationError,
    HardwareUnavailableError,
    planned_metadata,
)


_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:+-]+$")


def _safe_token(value: Any, label: str) -> str:
    token = str(value)
    if not token or not _SAFE_TOKEN.fullmatch(token):
        raise ValueError(f"Unsafe {label}: {token!r}")
    return token


def _safe_script_path(path: Path) -> str:
    value = str(Path(path).resolve())
    if any(character in value for character in ('"', "\r", "\n")):
        raise ValueError(f"Unsafe path for J-Link command script: {value!r}")
    return value


class JLinkFlashBackend:
    """Build and optionally execute J-Link Commander operations.

    ``flash`` and ``reset`` return plans by default.  Execution requires both an
    explicit ``execute=True`` argument and ``jlink.allow_execute: true`` in the
    loaded configuration, preventing accidental probe access.
    """

    def __init__(self, config: Mapping[str, Any], output_root: Path | None = None) -> None:
        self.config = dict(config)
        jlink = self.config.get("jlink", {})
        self.jlink_config = dict(jlink) if isinstance(jlink, Mapping) else {}
        self.output_root = Path(output_root) if output_root else None

    @property
    def executable(self) -> str:
        configured = self.jlink_config.get("executable")
        if configured:
            return str(configured)
        return shutil.which("JLinkExe") or shutil.which("JLink.exe") or "JLinkExe"

    def dependency_status(self) -> dict[str, Any]:
        found = shutil.which(self.executable) if Path(self.executable).name == self.executable else Path(self.executable).is_file()
        return planned_metadata(
            backend="jlink", executable=self.executable, available=bool(found)
        )

    def list_devices(self) -> Sequence[dict[str, Any]]:
        try:
            inventory = build_inventory(self.config)
        except Exception:
            return []
        return [
            planned_metadata(
                backend="jlink",
                node_id=item["node_id"],
                identifier=item.get("jlink_serial"),
                role=item.get("role"),
                configured=True,
                discovered=False,
            )
            for item in inventory
        ]

    def build_script(
        self, device: Mapping[str, Any], image: Path | None = None, *, reset_only: bool = False
    ) -> list[str]:
        if not reset_only and image is None:
            raise ValueError("image is required for a flash script")
        commands = ["r"]
        if not reset_only:
            image_path = Path(image)  # type: ignore[arg-type]
            suffix = image_path.suffix.lower()
            if suffix not in {".hex", ".elf", ".axf", ".bin"}:
                raise ValueError(f"Unsupported firmware image type: {suffix or '<none>'}")
            safe_image = _safe_script_path(image_path)
            if suffix == ".bin":
                address = device.get("load_address", self.jlink_config.get("load_address"))
                if address is None:
                    raise ValueError("A load_address is required for a .bin image")
                address_token = _safe_token(address, "load address")
                commands.append(f'loadfile "{safe_image}" {address_token}')
                commands.append(f'verifybin "{safe_image}" {address_token}')
            else:
                # J-Link Commander LoadFile performs verification for supported
                # object formats; there is no valid argument-free "verify" command.
                commands.append(f'loadfile "{safe_image}"')
            commands.append("r")
        commands.extend(["g", "exit"])
        return commands

    def build_command(
        self, device: Mapping[str, Any], command_file: Path
    ) -> list[str]:
        device_name = _safe_token(
            device.get("device") or self.jlink_config.get("device", "nRF52840_xxAA"),
            "J-Link device",
        )
        interface = _safe_token(
            device.get("interface") or self.jlink_config.get("interface", "SWD"),
            "J-Link interface",
        )
        speed = _safe_token(
            device.get("speed_khz") or self.jlink_config.get("speed_khz", 4000),
            "J-Link speed",
        )
        command = [
            self.executable,
            "-NoGui",
            "1",
            "-ExitOnError",
            "1",
            "-device",
            device_name,
            "-if",
            interface,
            "-speed",
            speed,
        ]
        serial = device.get("jlink_serial") or device.get("identifier")
        if serial and not str(serial).upper().startswith("TODO"):
            command.extend(["-SelectEmuBySN", _safe_token(serial, "J-Link serial")])
        command.extend(["-CommandFile", str(Path(command_file).resolve())])
        return command

    build_flash_command = build_command

    def _run_script(
        self, device: Mapping[str, Any], lines: list[str], timeout_s: float
    ) -> dict[str, Any]:
        if self.jlink_config.get("allow_execute") is not True:
            raise HardwareOperationError(
                "J-Link execution is disabled; set jlink.allow_execute=true and pass execute=True"
            )
        executable_path = shutil.which(self.executable)
        if executable_path is None and not Path(self.executable).is_file():
            raise HardwareUnavailableError(f"J-Link executable not found: {self.executable}")
        with tempfile.TemporaryDirectory(prefix="uwb_jlink_") as temporary:
            script = Path(temporary) / "commands.jlink"
            script.write_text("\n".join(lines) + "\n", encoding="ascii")
            command = self.build_command(device, script)
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                shell=False,
            )
        if completed.returncode != 0:
            raise HardwareOperationError(
                f"J-Link exited with {completed.returncode}: {completed.stderr.strip()}"
            )
        return {
            "source_type": "DEVICE_OPERATION",
            "hardware_verified": False,
            "verification_status": "PROGRAMMER_COMMAND_COMPLETED_RF_UNVERIFIED",
            "backend": "jlink",
            "success": True,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    def flash(
        self,
        device: Mapping[str, Any],
        image: Path,
        *,
        execute: bool = False,
        timeout_s: float = 120.0,
    ) -> dict[str, Any]:
        lines = self.build_script(device, Path(image))
        plan = planned_metadata(
            backend="jlink",
            operation="flash",
            node_id=device.get("node_id"),
            image=str(Path(image)),
            script=lines,
            execute_requested=execute,
            success=None,
            status="PLANNED",
        )
        if not execute:
            return plan
        if not Path(image).is_file():
            raise HardwareUnavailableError(f"Firmware image does not exist: {image}")
        return self._run_script(device, lines, timeout_s)

    def reset(
        self,
        device: Mapping[str, Any],
        *,
        execute: bool = False,
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        lines = self.build_script(device, reset_only=True)
        if not execute:
            return planned_metadata(
                backend="jlink",
                operation="reset",
                node_id=device.get("node_id"),
                script=lines,
                execute_requested=False,
                success=None,
                status="PLANNED",
            )
        return self._run_script(device, lines, timeout_s)


JLinkBackend = JLinkFlashBackend

__all__ = ["JLinkBackend", "JLinkFlashBackend"]
