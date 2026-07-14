"""CLI bootstrapping helpers for direct ``python tools/<name>.py`` use."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def root_relative(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path
