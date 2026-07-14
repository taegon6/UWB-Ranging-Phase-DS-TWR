"""Timing-characterization analysis glue shared by the unified runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from analysis.edge_detection import analyze_logic_capture


def analyze_logic(
    capture: Path,
    run_dir: Path,
    *,
    source_type: str,
    hardware_verified: bool = False,
    warmup_frames: int = 0,
) -> dict[str, Any]:
    return analyze_logic_capture(
        capture,
        edge_pairs_csv=run_dir / "intermediate" / "edge_pairs.csv",
        summary_csv=run_dir / "analysis" / "timing_summary.csv",
        errors_csv=run_dir / "analysis" / "errors.csv",
        source_type=source_type,
        hardware_verified=hardware_verified,
        warmup_frames=warmup_frames,
    )


def analyze_synthetic_logic(capture: Path, run_dir: Path) -> dict[str, Any]:
    return analyze_logic(capture, run_dir, source_type="SYNTHETIC", hardware_verified=False)
