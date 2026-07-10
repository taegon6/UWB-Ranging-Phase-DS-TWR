"""Synthetic antenna-delay search and identifiable offline fitting helpers."""

from __future__ import annotations

import csv
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def inclusive_range(start: int, stop: int, step: int) -> list[int]:
    if step <= 0:
        raise ValueError("step must be positive")
    if stop < start:
        raise ValueError("stop must be greater than or equal to start")
    return list(range(int(start), int(stop) + 1, int(step)))


def coarse_candidates(search: dict[str, Any]) -> list[int]:
    return inclusive_range(search["initial_min"], search["initial_max"], search["coarse_step"])


def fine_candidates(search: dict[str, Any], coarse_best: int) -> list[int]:
    lower = max(int(search["initial_min"]), int(coarse_best) - int(search["coarse_step"]))
    upper = min(int(search["initial_max"]), int(coarse_best) + int(search["coarse_step"]))
    return inclusive_range(lower, upper, int(search["fine_step"]))


def _weighted_objective(
    rows: list[dict[str, float]],
    *,
    squared_bias: bool,
    include_repeatability_penalty: bool,
    repeatability_weight: float,
) -> float:
    if not rows:
        raise ValueError("objective requires at least one row")
    if repeatability_weight < 0:
        raise ValueError("repeatability_weight must be non-negative")
    by_reference: dict[float, list[float]] = defaultdict(list)
    weights: dict[float, float] = {}
    for row in rows:
        reference = float(row["reference_distance_m"])
        measured = float(row["measured_distance_m"])
        by_reference[reference].append(measured)
        weights[reference] = float(row.get("weight", 1.0))
    weighted_bias = 0.0
    weighted_repeatability = 0.0
    total_weight = 0.0
    for reference, values in by_reference.items():
        weight = weights[reference]
        bias = statistics.fmean(values) - reference
        spread = statistics.pstdev(values) if len(values) > 1 else 0.0
        total_weight += weight
        weighted_bias += weight * (bias * bias if squared_bias else abs(bias))
        if include_repeatability_penalty:
            weighted_repeatability += weight * (spread * spread if squared_bias else spread)
    return (weighted_bias + repeatability_weight * weighted_repeatability) / total_weight


def weighted_absolute_bias(
    rows: list[dict[str, float]],
    repeatability_weight: float = 0.25,
    *,
    include_repeatability_penalty: bool = True,
) -> float:
    """Score point-wise biases and optionally penalize repeated-sample spread."""

    return _weighted_objective(
        rows,
        squared_bias=False,
        include_repeatability_penalty=include_repeatability_penalty,
        repeatability_weight=repeatability_weight,
    )


def weighted_squared_bias(
    rows: list[dict[str, float]],
    repeatability_weight: float = 0.25,
    *,
    include_repeatability_penalty: bool = True,
) -> float:
    return _weighted_objective(
        rows,
        squared_bias=True,
        include_repeatability_penalty=include_repeatability_penalty,
        repeatability_weight=repeatability_weight,
    )


def _synthetic_rows(
    candidate: int,
    references: list[float],
    truth: int,
    repeats: int = 8,
    *,
    warmup_samples: int = 0,
    noise_std_m: float = 0.001,
    random_seed: int = 0,
) -> list[dict[str, float]]:
    """Generate deterministic fixture values; this is not a DW3000 model."""

    rows: list[dict[str, float]] = []
    delay_error_m = (candidate - truth) * 0.00012
    for point_index, reference in enumerate(references):
        rng = random.Random(int(random_seed) + point_index * 1_000_003)
        for sample in range(warmup_samples + repeats):
            deterministic_noise = rng.gauss(0.0, float(noise_std_m))
            if sample < warmup_samples:
                continue
            rows.append(
                {
                    "reference_distance_m": float(reference),
                    "measured_distance_m": float(reference) + delay_error_m + deterministic_noise,
                    "weight": 1.0,
                }
            )
    return rows


def evaluate_candidates(
    candidates: list[int],
    references: list[float],
    truth: int,
    *,
    samples_per_point: int = 8,
    warmup_samples: int = 0,
    noise_std_m: float = 0.001,
    random_seed: int = 0,
    metric: str = "weighted_absolute_bias",
    include_repeatability_penalty: bool = True,
    repeatability_weight: float = 0.25,
) -> list[dict[str, Any]]:
    if metric not in {"weighted_absolute_bias", "weighted_squared_bias"}:
        raise ValueError(f"unsupported objective metric: {metric}")
    objective_function = weighted_absolute_bias if metric == "weighted_absolute_bias" else weighted_squared_bias
    evaluations: list[dict[str, Any]] = []
    for candidate in candidates:
        rows = _synthetic_rows(
            candidate,
            references,
            truth,
            samples_per_point,
            warmup_samples=warmup_samples,
            noise_std_m=noise_std_m,
            random_seed=random_seed,
        )
        point_rows = []
        for reference in references:
            values = [
                row["measured_distance_m"]
                for row in rows
                if row["reference_distance_m"] == reference
            ]
            point_rows.append(
                {
                    "candidate": candidate,
                    "reference_distance_m": reference,
                    "mean_measured_distance_m": statistics.fmean(values),
                    "mean_bias_m": statistics.fmean(values) - reference,
                    "repeatability_std_m": statistics.pstdev(values) if len(values) > 1 else 0.0,
                    "sample_count": len(values),
                    "source_type": "SYNTHETIC",
                    "hardware_verified": False,
                }
            )
        evaluations.append(
            {
                "candidate": candidate,
                "objective": objective_function(
                    rows,
                    repeatability_weight,
                    include_repeatability_penalty=include_repeatability_penalty,
                ),
                "mean_bias_m": statistics.fmean(
                    row["measured_distance_m"] - row["reference_distance_m"] for row in rows
                ),
                "sample_count": len(rows),
                "source_type": "SYNTHETIC",
                "hardware_verified": False,
                "point_biases": point_rows,
            }
        )
    return evaluations


def solve_least_squares(matrix: list[list[float]], observations: list[float]) -> dict[str, Any]:
    """Solve a small full-column-rank least-squares system via normal equations."""

    if not matrix or len(matrix) != len(observations):
        raise ValueError("matrix and observations must have equal non-zero row count")
    columns = len(matrix[0])
    if columns == 0 or any(len(row) != columns for row in matrix):
        raise ValueError("matrix rows must have equal non-zero length")
    ata = [[sum(row[i] * row[j] for row in matrix) for j in range(columns)] for i in range(columns)]
    atb = [sum(row[i] * value for row, value in zip(matrix, observations)) for i in range(columns)]
    augmented = [ata[row][:] + [atb[row]] for row in range(columns)]
    rank = 0
    for column in range(columns):
        pivot = max(range(rank, columns), key=lambda row: abs(augmented[row][column]), default=rank)
        if abs(augmented[pivot][column]) < 1e-12:
            continue
        augmented[rank], augmented[pivot] = augmented[pivot], augmented[rank]
        scale = augmented[rank][column]
        augmented[rank] = [value / scale for value in augmented[rank]]
        for row in range(columns):
            if row == rank:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[rank])
            ]
        rank += 1
    if rank < columns:
        return {
            "solution": None,
            "rank": rank,
            "columns": columns,
            "identifiable": False,
            "limitation": "The supplied link equations do not uniquely identify all node delays.",
        }
    solution = [augmented[index][-1] for index in range(columns)]
    residuals = [
        observed - sum(coefficient * value for coefficient, value in zip(row, solution))
        for row, observed in zip(matrix, observations)
    ]
    return {
        "solution": solution,
        "rank": rank,
        "columns": columns,
        "identifiable": True,
        "residual_rms": math.sqrt(statistics.fmean(value * value for value in residuals)),
    }


def fit_four_link_combined_delays(link_biases: dict[str, float], reference_node: str = "A1") -> dict[str, Any]:
    """Fit node contributions with one node fixed to remove the global gauge."""

    expected = {"A1-T1", "A1-T2", "A2-T1", "A2-T2"}
    if set(link_biases) != expected:
        raise ValueError(f"link_biases must contain exactly {sorted(expected)}")
    nodes = [node for node in ["A1", "A2", "T1", "T2"] if node != reference_node]
    matrix: list[list[float]] = []
    observations: list[float] = []
    for link in sorted(link_biases):
        left, right = link.split("-")
        matrix.append([float(node in (left, right)) for node in nodes])
        observations.append(float(link_biases[link]))
    result = solve_least_squares(matrix, observations)
    result["parameter_nodes"] = nodes
    result["reference_node"] = reference_node
    result["identifiability_note"] = (
        "Only aggregate node/link delay contributions are fitted. Separate TX and RX delays are not identifiable from range bias alone."
    )
    result["source_type"] = "SYNTHETIC"
    result["hardware_verified"] = False
    return result


def run_mock_calibration(config: dict[str, Any], output_dir: Path | str) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    calibration = config["calibration"]
    search_groups = calibration["search"]
    search = search_groups.get("synthetic_mock") or search_groups
    references = [float(value) for value in calibration["reference_distances_m"]]
    mode = str(calibration["mode"])
    supported_modes = {
        "COMBINED_SINGLE_LINK",
        "REFERENCE_NODE_SEQUENTIAL",
        "OFFLINE_2A2T_LEAST_SQUARES",
    }
    if mode not in supported_modes:
        raise ValueError(f"unsupported calibration mode: {mode}")
    samples_per_point = int(calibration["samples_per_point"])
    warmup_samples = int(calibration["warmup_samples"])
    objective = calibration["objective"]
    metric = str(objective["metric"])
    include_repeatability = bool(objective["include_repeatability_penalty"])
    repeatability_weight = float(objective.get("repeatability_weight", 0.25))
    synthetic_truth = calibration.get("synthetic_truth", {})
    noise_std_m = float(synthetic_truth.get("noise_std_m", 0.001))
    random_seed = int(synthetic_truth.get("random_seed", 0))
    truth = int(
        search.get(
            "synthetic_truth",
            synthetic_truth.get(
                "combined_delay_dtu",
                (int(search["initial_min"]) + int(search["initial_max"])) // 2,
            ),
        )
    )

    coarse = coarse_candidates(search)
    evaluation_options = {
        "samples_per_point": samples_per_point,
        "warmup_samples": warmup_samples,
        "noise_std_m": noise_std_m,
        "random_seed": random_seed,
        "metric": metric,
        "include_repeatability_penalty": include_repeatability,
        "repeatability_weight": repeatability_weight,
    }
    coarse_eval = evaluate_candidates(coarse, references, truth, **evaluation_options)
    coarse_best = min(coarse_eval, key=lambda row: row["objective"])["candidate"]
    fine = fine_candidates(search, int(coarse_best))
    fine_eval = evaluate_candidates(fine, references, truth, **evaluation_options)
    selected = min(fine_eval, key=lambda row: row["objective"])
    combined = coarse_eval + [row for row in fine_eval if row["candidate"] not in set(coarse)]

    fields = ["candidate", "objective", "mean_bias_m", "sample_count", "source_type", "hardware_verified"]
    for name, rows in (("calibration_candidates.csv", combined), ("objective_curve.csv", fine_eval)):
        with (output_dir / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(
                {**row, "hardware_verified": "false"}
                for row in rows
            )

    bias_fields = [
        "candidate",
        "reference_distance_m",
        "mean_measured_distance_m",
        "mean_bias_m",
        "repeatability_std_m",
        "sample_count",
        "source_type",
        "hardware_verified",
    ]
    with (output_dir / "mock_bias_table.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=bias_fields)
        writer.writeheader()
        for evaluation in combined:
            writer.writerows(
                {**row, "hardware_verified": "false"}
                for row in evaluation["point_biases"]
            )

    mode_details: dict[str, Any]
    if mode == "COMBINED_SINGLE_LINK":
        mode_details = {
            "mode": mode,
            "estimated_quantity": "combined synthetic single-link token",
        }
    elif mode == "REFERENCE_NODE_SEQUENTIAL":
        reference_node = str(calibration.get("reference_node", ""))
        if reference_node not in {"A1", "A2", "T1", "T2"}:
            raise ValueError("REFERENCE_NODE_SEQUENTIAL requires a resolved A1/A2/T1/T2 reference_node")
        targets = [node for node in ["A1", "A2", "T1", "T2"] if node != reference_node]
        mode_details = {
            "mode": mode,
            "reference_node": reference_node,
            "target_nodes": targets,
            "sequential_mock_candidates": {
                node: int(selected["candidate"]) + offset
                for node, offset in zip(targets, (-2, 0, 2))
            },
            "limitation": "Synthetic sequencing branch only; no board was reconfigured or ranged.",
        }
    else:
        mode_details = {
            "mode": mode,
            "offline_fit": fit_four_link_combined_delays(
                {"A1-T1": 0.1, "A1-T2": 0.3, "A2-T1": 0.3, "A2-T2": 0.5},
                reference_node=str(calibration.get("reference_node", "A1")),
            ),
        }

    result = {
        "status": "DRY_RUN_PASS",
        "selected_mock_candidate": selected["candidate"],
        "objective": selected["objective"],
        "candidate_count": len(combined),
        "mode": mode,
        "mode_details": mode_details,
        "measurement_metadata": calibration.get("measurement_metadata", {}),
        "samples_per_point": samples_per_point,
        "warmup_samples_discarded_per_point": warmup_samples,
        "objective_metric": metric,
        "include_repeatability_penalty": include_repeatability,
        "repeatability_weight": repeatability_weight,
        "synthetic_noise_std_m": noise_std_m,
        "random_seed": random_seed,
        "source_type": "SYNTHETIC",
        "hardware_verified": False,
        "calibration_completed": False,
        "interpretation": "Synthetic software-path selection only; not an antenna-delay calibration result.",
    }
    (output_dir / "calibration_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    report = f"""# Antenna-delay calibration dry-run report

`source_type = SYNTHETIC`  
`hardware_verified = false`

## 검증된 결과

- Mode branch: `{mode}`
- Selected mock token: `{selected['candidate']}`
- Synthetic objective: `{selected['objective']:.12g}` using `{metric}`
- Candidates evaluated: `{len(combined)}`
- Samples used per reference/candidate: `{samples_per_point}` after discarding `{warmup_samples}` synthetic warm-up samples

The candidate generator, configured objective calculation, bias table, mode branch, and selection/report path completed using deterministic synthetic fixture values.

## 가정한 값

- Synthetic truth token: `{truth}`
- Synthetic noise standard deviation: `{noise_std_m}` m; random seed: `{random_seed}`
- Repeatability penalty enabled: `{str(include_repeatability).lower()}`; weight: `{repeatability_weight}`

## 논문 기반 근거

- None. No paper-derived numeric antenna-delay value is used by this software fixture.

## 추후 확인 필요

This does **not** establish a DW3000/DWS3000 antenna-delay value. The reported candidate is only a mock-path test token and must not be copied into firmware.

Separate TX and RX delays cannot be identified from range bias alone without additional constraints or measurements.

본 결과는 mock/synthetic data를 이용한 소프트웨어 환경 검증 결과이며,
DW3000/DWS3000의 실제 처리시간 또는 antenna delay 보정 결과를 의미하지 않는다.
"""
    (output_dir / "calibration_report.md").write_text(report, encoding="utf-8")
    return result
