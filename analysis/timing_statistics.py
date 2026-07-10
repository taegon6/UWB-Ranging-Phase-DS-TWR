"""Deterministic timing statistics with explicit provenance."""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable


def percentile(values: Iterable[float], percent: float) -> float:
    """Return a linearly interpolated percentile using the (n-1) convention."""

    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    if not 0.0 <= percent <= 100.0:
        raise ValueError("percent must be between 0 and 100")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percent / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize_timing(
    metric: str,
    values_us: Iterable[float],
    *,
    missing_pulse_count: int = 0,
    invalid_pair_count: int = 0,
    source_type: str = "SYNTHETIC",
    hardware_verified: bool = False,
) -> dict[str, object]:
    """Summarize one metric without allowing synthetic data to look measured."""

    values = [float(value) for value in values_us]
    if source_type == "SYNTHETIC" and hardware_verified:
        raise ValueError("synthetic results cannot be hardware verified")
    if not values:
        return {
            "metric": metric,
            "count": 0,
            "mean_us": "",
            "median_us": "",
            "std_us": "",
            "p90_us": "",
            "p95_us": "",
            "p99_us": "",
            "max_us": "",
            "missing_pulse_count": int(missing_pulse_count),
            "invalid_pair_count": int(invalid_pair_count),
            "source_type": source_type,
            "hardware_verified": bool(hardware_verified),
        }
    return {
        "metric": metric,
        "count": len(values),
        "mean_us": statistics.fmean(values),
        "median_us": statistics.median(values),
        "std_us": statistics.pstdev(values),
        "p90_us": percentile(values, 90),
        "p95_us": percentile(values, 95),
        "p99_us": percentile(values, 99),
        "max_us": max(values),
        "missing_pulse_count": int(missing_pulse_count),
        "invalid_pair_count": int(invalid_pair_count),
        "source_type": source_type,
        "hardware_verified": bool(hardware_verified),
    }
