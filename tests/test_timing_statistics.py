from __future__ import annotations

import pytest

from analysis.timing_statistics import percentile, summarize_timing


def test_percentile_linear_interpolation() -> None:
    values = list(range(1, 101))
    assert percentile(values, 95) == pytest.approx(95.05)
    assert percentile(values, 99) == pytest.approx(99.01)


def test_synthetic_cannot_be_hardware_verified() -> None:
    with pytest.raises(ValueError):
        summarize_timing("irq_latency", [1.0], hardware_verified=True)


def test_summary_includes_provenance_and_errors() -> None:
    row = summarize_timing("cir_read_duration", [10.0, 12.0, 14.0], missing_pulse_count=1, invalid_pair_count=2)
    assert row["count"] == 3
    assert row["source_type"] == "SYNTHETIC"
    assert row["hardware_verified"] is False
    assert row["missing_pulse_count"] == 1
    assert row["invalid_pair_count"] == 2
