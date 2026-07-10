"""Logic-analyzer HAL exports and optional concrete adapters."""

from .interfaces import HardwareOperationError, HardwareUnavailableError, LogicBackend
from .saleae_backend import SaleaeLogicBackend
from .sigrok_backend import SigrokLogicBackend

__all__ = [
    "HardwareOperationError",
    "HardwareUnavailableError",
    "LogicBackend",
    "SaleaeLogicBackend",
    "SigrokLogicBackend",
]
