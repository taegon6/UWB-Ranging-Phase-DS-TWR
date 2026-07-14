from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

from analysis.antenna_delay_fit import (
    coarse_candidates,
    fine_candidates,
    fit_four_link_combined_delays,
    run_mock_calibration,
    solve_least_squares,
    weighted_absolute_bias,
    weighted_squared_bias,
)

ROOT = Path(__file__).resolve().parents[1]


def test_coarse_to_fine_candidate_generation() -> None:
    search = {"initial_min": 100, "initial_max": 140, "coarse_step": 10, "fine_step": 2}
    assert coarse_candidates(search) == [100, 110, 120, 130, 140]
    assert fine_candidates(search, 120) == [110, 112, 114, 116, 118, 120, 122, 124, 126, 128, 130]


def test_weighted_objective_penalizes_bias() -> None:
    unbiased = [
        {"reference_distance_m": 1.0, "measured_distance_m": 0.99},
        {"reference_distance_m": 1.0, "measured_distance_m": 1.01},
    ]
    biased = [
        {"reference_distance_m": 1.0, "measured_distance_m": 1.1},
        {"reference_distance_m": 1.0, "measured_distance_m": 1.12},
    ]
    assert weighted_absolute_bias(unbiased) < weighted_absolute_bias(biased)


def test_four_link_synthetic_recovery() -> None:
    result = fit_four_link_combined_delays(
        {"A1-T1": 0.1, "A1-T2": 0.3, "A2-T1": 0.3, "A2-T2": 0.5}
    )
    assert result["identifiable"] is True
    assert result["solution"] == pytest.approx([0.2, 0.1, 0.3])
    assert result["hardware_verified"] is False


def test_rank_deficiency_is_reported() -> None:
    result = solve_least_squares([[1.0, 1.0], [2.0, 2.0]], [2.0, 4.0])
    assert result["identifiable"] is False
    assert result["rank"] == 1


def test_configured_samples_warmup_and_squared_objective_are_consumed(tmp_path: Path) -> None:
    config = yaml.safe_load((ROOT / "configs" / "antenna_calibration.example.yaml").read_text(encoding="utf-8"))
    calibration = config["calibration"]
    calibration["samples_per_point"] = 7
    calibration["warmup_samples"] = 3
    calibration["objective"].update(
        metric="weighted_squared_bias",
        include_repeatability_penalty=False,
        repeatability_weight=0.75,
    )
    result = run_mock_calibration(config, tmp_path / "calibration")
    assert result["samples_per_point"] == 7
    assert result["warmup_samples_discarded_per_point"] == 3
    assert result["objective_metric"] == "weighted_squared_bias"
    assert result["include_repeatability_penalty"] is False
    with (tmp_path / "calibration" / "calibration_candidates.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows and {int(row["sample_count"]) for row in rows} == {28}
    assert (tmp_path / "calibration" / "mock_bias_table.csv").is_file()


@pytest.mark.parametrize("mode", ["REFERENCE_NODE_SEQUENTIAL", "OFFLINE_2A2T_LEAST_SQUARES"])
def test_declared_calibration_modes_execute_synthetic_branches(tmp_path: Path, mode: str) -> None:
    config = yaml.safe_load((ROOT / "configs" / "antenna_calibration.example.yaml").read_text(encoding="utf-8"))
    calibration = config["calibration"]
    calibration["mode"] = mode
    calibration["reference_node"] = "A1"
    calibration["samples_per_point"] = 3
    calibration["warmup_samples"] = 1
    result = run_mock_calibration(config, tmp_path / mode)
    assert result["mode_details"]["mode"] == mode
    if mode == "REFERENCE_NODE_SEQUENTIAL":
        assert set(result["mode_details"]["target_nodes"]) == {"A2", "T1", "T2"}
    else:
        assert result["mode_details"]["offline_fit"]["identifiable"] is True


def test_squared_objective_penalizes_large_bias() -> None:
    near = [{"reference_distance_m": 1.0, "measured_distance_m": 1.01}]
    far = [{"reference_distance_m": 1.0, "measured_distance_m": 1.2}]
    assert weighted_squared_bias(near) < weighted_squared_bias(far)
