"""Portable hardware-abstraction protocols used by experiment tooling.

The protocols deliberately contain no vendor imports.  Optional packages are
loaded by concrete adapters only when their functionality is explicitly used.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


SOURCE_SYNTHETIC = "SYNTHETIC"


class HardwareError(RuntimeError):
    """Base error for hardware adapter failures."""


class HardwareUnavailableError(HardwareError):
    """A configured device, port, executable, or optional package is absent."""


class HardwareOperationError(HardwareError):
    """A hardware operation was attempted but did not complete successfully."""


class OutputExistsError(HardwareError, FileExistsError):
    """An adapter refused to overwrite an existing raw-data file."""


def synthetic_metadata(**extra: Any) -> dict[str, Any]:
    """Return the mandatory provenance fields for a synthetic result."""

    return {
        "source_type": SOURCE_SYNTHETIC,
        "hardware_verified": False,
        **extra,
    }


def planned_metadata(**extra: Any) -> dict[str, Any]:
    """Return provenance for a real-backend command that was not executed."""

    return {
        "source_type": "PLANNED",
        "hardware_verified": False,
        **extra,
    }


@runtime_checkable
class FlashBackend(Protocol):
    """Programming/debug-probe operations."""

    def list_devices(self) -> Sequence[dict[str, Any]]:
        """List available or configured programming devices."""

    def flash(self, device: Mapping[str, Any], image: Path) -> dict[str, Any]:
        """Program *image* on *device* or return an explicit dry-run plan."""

    def reset(self, device: Mapping[str, Any]) -> None:
        """Reset one device."""


@runtime_checkable
class SerialBackend(Protocol):
    """UART discovery and binary-safe capture operations."""

    def list_ports(self) -> Sequence[dict[str, Any]]:
        """List serial ports."""

    def capture(
        self, port: str, output: Path, duration_s: float
    ) -> dict[str, Any]:
        """Capture bytes from *port* into a new raw output file."""


@runtime_checkable
class LogicBackend(Protocol):
    """Logic-analyzer capture and edge-export operations."""

    def list_devices(self) -> Sequence[dict[str, Any]]:
        """List logic analyzers."""

    def capture(
        self, config: Mapping[str, Any], output: Path
    ) -> dict[str, Any]:
        """Capture digital channels into *output*."""

    def export_edges(self, capture: Path, output_csv: Path) -> dict[str, Any]:
        """Convert a capture/export to a normalized edge CSV."""


__all__ = [
    "FlashBackend",
    "HardwareError",
    "HardwareOperationError",
    "HardwareUnavailableError",
    "LogicBackend",
    "OutputExistsError",
    "SOURCE_SYNTHETIC",
    "SerialBackend",
    "planned_metadata",
    "synthetic_metadata",
]
