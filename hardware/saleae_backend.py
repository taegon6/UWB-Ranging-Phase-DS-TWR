"""Saleae Logic 2 automation adapter skeleton.

No Saleae session is opened unless a future adapter implements an explicit
``execute=True`` path.  The current class is intentionally useful for
environment checks and dry-run planning only.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Mapping, Sequence

from .interfaces import HardwareUnavailableError, OutputExistsError, planned_metadata


class SaleaeLogicBackend:
    def __init__(self, config: Mapping[str, Any], output_root: Path | None = None) -> None:
        self.config = dict(config)
        self.output_root = Path(output_root) if output_root else None

    @staticmethod
    def dependency_status() -> dict[str, Any]:
        available = importlib.util.find_spec("saleae") is not None
        automation = importlib.util.find_spec("saleae.automation") is not None if available else False
        return planned_metadata(
            backend="saleae",
            package="saleae",
            available=available,
            automation_available=automation,
        )

    def list_devices(self) -> Sequence[dict[str, Any]]:
        # Discovery would open a Logic 2 automation connection; dry-run does not.
        return []

    def capture(
        self,
        config: Mapping[str, Any],
        output: Path,
        *,
        execute: bool = False,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        target = Path(output)
        if target.exists() and not overwrite:
            raise OutputExistsError(f"Refusing to overwrite Saleae capture: {target}")
        plan = planned_metadata(
            backend="saleae",
            operation="logic_capture",
            output=str(target),
            config=dict(config),
            execute_requested=execute,
            status="PLANNED",
        )
        if execute:
            status = self.dependency_status()
            if not status["automation_available"]:
                raise HardwareUnavailableError(
                    "Saleae automation package is unavailable; install optional hardware dependencies"
                )
            raise NotImplementedError(
                "Saleae execution requires device-specific Logic 2 validation; use sigrok or mock until configured"
            )
        return plan

    def export_edges(self, capture: Path, output_csv: Path) -> dict[str, Any]:
        raise NotImplementedError(
            "Export Saleae digital CSV in Logic 2, then analyze it with the shared edge parser"
        )


SaleaeBackend = SaleaeLogicBackend

__all__ = ["SaleaeBackend", "SaleaeLogicBackend"]
