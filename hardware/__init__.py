"""Hardware abstraction package and backend factory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .device_inventory import (
    ConfigError,
    build_inventory,
    find_placeholders,
    load_yaml,
    validate_config,
)
from .interfaces import (
    FlashBackend,
    HardwareError,
    HardwareOperationError,
    HardwareUnavailableError,
    LogicBackend,
    OutputExistsError,
    SerialBackend,
)
from .mock_backend import MockBackend


@dataclass(frozen=True)
class HardwareBackendBundle:
    """Configured real-backend adapters without performing discovery or I/O."""

    flash_backend: Any
    serial_backend: Any
    logic_backend: Any

    def metadata(self) -> dict[str, Any]:
        return {
            "source_type": "PLANNED",
            "hardware_verified": False,
            "backend": "configured",
            "flash_backend": type(self.flash_backend).__name__,
            "serial_backend": type(self.serial_backend).__name__,
            "logic_backend": type(self.logic_backend).__name__,
        }


def create_backend(
    name: str,
    config: Mapping[str, Any],
    output_root: Path | None = None,
) -> Any:
    """Create one backend without importing unrelated optional dependencies."""

    normalized = str(name).strip().lower().replace("-", "_")
    if normalized == "mock":
        return MockBackend(dict(config), output_root=output_root)
    if normalized in {"jlink", "j_link"}:
        from .jlink_backend import JLinkFlashBackend

        return JLinkFlashBackend(config, output_root=output_root)
    if normalized in {"serial", "pyserial", "uart"}:
        from .serial_backend import PySerialBackend

        return PySerialBackend(config, output_root=output_root)
    if normalized in {"saleae", "logic2", "saleae_logic2"}:
        from .saleae_backend import SaleaeLogicBackend

        return SaleaeLogicBackend(config, output_root=output_root)
    if normalized in {"sigrok", "sigrok_cli"}:
        from .sigrok_backend import SigrokLogicBackend

        return SigrokLogicBackend(config, output_root=output_root)
    if normalized in {"real", "configured", "hardware"}:
        selection = config.get("backend")
        if not isinstance(selection, Mapping):
            raise ConfigError(
                "A configured real backend requires backend.flash, backend.serial, and backend.logic"
            )
        missing = [key for key in ("flash", "serial", "logic") if key not in selection]
        if missing:
            raise ConfigError(f"Configured backend is missing: {', '.join(missing)}")
        return HardwareBackendBundle(
            flash_backend=create_backend(str(selection["flash"]), config, output_root),
            serial_backend=create_backend(str(selection["serial"]), config, output_root),
            logic_backend=create_backend(str(selection["logic"]), config, output_root),
        )
    raise ConfigError(
        f"Unknown backend {name!r}; expected mock, real, jlink, pyserial, saleae, or sigrok"
    )


__all__ = [
    "ConfigError",
    "FlashBackend",
    "HardwareError",
    "HardwareBackendBundle",
    "HardwareOperationError",
    "HardwareUnavailableError",
    "LogicBackend",
    "MockBackend",
    "OutputExistsError",
    "SerialBackend",
    "build_inventory",
    "create_backend",
    "find_placeholders",
    "load_yaml",
    "validate_config",
]
