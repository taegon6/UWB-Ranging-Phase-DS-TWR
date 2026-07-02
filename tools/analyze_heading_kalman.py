#!/usr/bin/env python3
"""Estimate UWB trajectory heading with a 2D Kalman filter and sliding PCA.

Input is a two-anchor position CSV produced by collect_tag_two_anchor_position.py.
The output CSV keeps the original rows and adds:

    x_kalman_m,y_kalman_m,vx_mps,vy_mps,speed_mps,
    heading_velocity_deg,heading_pca_deg,heading_pca_axis_deg,is_moving

The Kalman model is constant velocity [x, y, vx, vy].  PCA heading is computed
from recent Kalman positions and its 180-degree ambiguity is aligned to the
Kalman velocity direction when the tag is moving.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import deque
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", help="Input *.position.csv")
    parser.add_argument("--out-csv", help="Output CSV path. Defaults beside input.")
    parser.add_argument("--plot", help="Output PNG path. Defaults beside output CSV.")
    parser.add_argument("--measurement-std-x", type=float, default=0.10, help="UWB x measurement noise in meters")
    parser.add_argument("--measurement-std-y", type=float, default=0.08, help="UWB y measurement noise in meters")
    parser.add_argument("--accel-std", type=float, default=0.4, help="Process acceleration noise in m/s^2")
    parser.add_argument("--pca-window-s", type=float, default=1.0, help="Recent Kalman trajectory window for PCA heading")
    parser.add_argument("--moving-speed-threshold", type=float, default=0.15, help="Speed below this keeps heading stable")
    parser.add_argument("--min-pca-points", type=int, default=6)
    parser.add_argument("--measurement-source", choices=["raw", "median"], default="raw")
    return parser.parse_args()


def angle_deg(vx: float, vy: float) -> float:
    return (math.degrees(math.atan2(vy, vx)) + 360.0) % 360.0


def angle_diff_deg(a: float, b: float) -> float:
    return ((a - b + 180.0) % 360.0) - 180.0


def fmt(value: float) -> str:
    return "" if not math.isfinite(value) else f"{value:.6f}"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def parse_float(row: dict[str, str], key: str) -> float:
    text = row.get(key, "")
    if text == "":
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def process_rows(args: argparse.Namespace, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    x_key = "x_m" if args.measurement_source == "raw" else "x_filtered_m"
    y_key = "y_m" if args.measurement_source == "raw" else "y_filtered_m"
    r = np.diag([args.measurement_std_x**2, args.measurement_std_y**2])
    h = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    eye = np.eye(4)

    state: np.ndarray | None = None
    cov: np.ndarray | None = None
    last_t: float | None = None
    last_heading = math.nan
    pca_points: deque[tuple[float, float, float]] = deque()
    out: list[dict[str, str]] = []

    for row in rows:
        new_row = row.copy()
        t = parse_float(row, "elapsed_s")
        z_x = parse_float(row, x_key)
        z_y = parse_float(row, y_key)
        valid = row.get("status") == "ok" and math.isfinite(t) and math.isfinite(z_x) and math.isfinite(z_y)

        if state is None:
            if valid:
                state = np.array([z_x, z_y, 0.0, 0.0], dtype=float)
                cov = np.diag([0.1, 0.1, 1.0, 1.0])
                last_t = t
            else:
                for key in extra_fields():
                    new_row[key] = ""
                out.append(new_row)
                continue

        assert state is not None and cov is not None and last_t is not None
        dt = max(1e-3, min(1.0, t - last_t)) if math.isfinite(t) else 1e-3
        last_t = t if math.isfinite(t) else last_t

        f = np.array(
            [
                [1.0, 0.0, dt, 0.0],
                [0.0, 1.0, 0.0, dt],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        q_scale = args.accel_std**2
        q = q_scale * np.array(
            [
                [dt**4 / 4.0, 0.0, dt**3 / 2.0, 0.0],
                [0.0, dt**4 / 4.0, 0.0, dt**3 / 2.0],
                [dt**3 / 2.0, 0.0, dt**2, 0.0],
                [0.0, dt**3 / 2.0, 0.0, dt**2],
            ]
        )

        state = f @ state
        cov = f @ cov @ f.T + q

        if valid:
            z = np.array([z_x, z_y])
            innovation = z - h @ state
            s = h @ cov @ h.T + r
            k = cov @ h.T @ np.linalg.inv(s)
            state = state + k @ innovation
            cov = (eye - k @ h) @ cov

        x_k, y_k, vx, vy = [float(v) for v in state]
        speed = math.hypot(vx, vy)
        moving = speed >= args.moving_speed_threshold
        velocity_heading = angle_deg(vx, vy) if moving else last_heading
        if moving:
            last_heading = velocity_heading

        pca_points.append((t, x_k, y_k))
        while pca_points and (t - pca_points[0][0]) > args.pca_window_s:
            pca_points.popleft()

        pca_axis = math.nan
        pca_heading = math.nan
        if len(pca_points) >= args.min_pca_points:
            pts = np.array([(x, y) for _, x, y in pca_points], dtype=float)
            centered = pts - pts.mean(axis=0)
            _, _, vh = np.linalg.svd(centered, full_matrices=False)
            axis_vec = vh[0]
            pca_axis = angle_deg(float(axis_vec[0]), float(axis_vec[1])) % 180.0
            pca_heading = pca_axis
            if math.isfinite(velocity_heading):
                opposite = (pca_axis + 180.0) % 360.0
                if abs(angle_diff_deg(opposite, velocity_heading)) < abs(angle_diff_deg(pca_axis, velocity_heading)):
                    pca_heading = opposite
            elif math.isfinite(last_heading):
                opposite = (pca_axis + 180.0) % 360.0
                if abs(angle_diff_deg(opposite, last_heading)) < abs(angle_diff_deg(pca_axis, last_heading)):
                    pca_heading = opposite

        new_row.update(
            {
                "x_kalman_m": fmt(x_k),
                "y_kalman_m": fmt(y_k),
                "vx_mps": fmt(vx),
                "vy_mps": fmt(vy),
                "speed_mps": fmt(speed),
                "heading_velocity_deg": fmt(velocity_heading),
                "heading_pca_deg": fmt(pca_heading),
                "heading_pca_axis_deg": fmt(pca_axis),
                "is_moving": "1" if moving else "0",
            }
        )
        out.append(new_row)

    return out


def extra_fields() -> list[str]:
    return [
        "x_kalman_m",
        "y_kalman_m",
        "vx_mps",
        "vy_mps",
        "speed_mps",
        "heading_velocity_deg",
        "heading_pca_deg",
        "heading_pca_axis_deg",
        "is_moving",
    ]


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    for key in extra_fields():
        if key not in fields:
            fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_plot(path: Path, rows: list[dict[str, str]]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is not installed; skipping plot.")
        return

    def col(name: str) -> np.ndarray:
        values = []
        for row in rows:
            try:
                values.append(float(row.get(name, "")))
            except ValueError:
                values.append(math.nan)
        return np.array(values, dtype=float)

    t = col("elapsed_s")
    x_raw = col("x_m")
    y_raw = col("y_m")
    x_k = col("x_kalman_m")
    y_k = col("y_kalman_m")
    speed = col("speed_mps")
    heading_v = col("heading_velocity_deg")
    heading_pca = col("heading_pca_deg")

    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    axes[0, 0].scatter(x_raw, y_raw, s=8, alpha=0.25, label="raw position")
    axes[0, 0].plot(x_k, y_k, linewidth=1.8, label="Kalman trajectory")
    axes[0, 0].scatter([0, 2.5], [0, 0], marker="^", s=80, label="anchors")
    axes[0, 0].axis("equal")
    axes[0, 0].set_title("Trajectory")
    axes[0, 0].set_xlabel("x [m]")
    axes[0, 0].set_ylabel("y [m]")
    axes[0, 0].grid(True, alpha=0.3)
    axes[0, 0].legend()

    axes[0, 1].plot(t, x_raw, alpha=0.25, label="x raw")
    axes[0, 1].plot(t, y_raw, alpha=0.25, label="y raw")
    axes[0, 1].plot(t, x_k, label="x Kalman")
    axes[0, 1].plot(t, y_k, label="y Kalman")
    axes[0, 1].set_title("Position over time")
    axes[0, 1].set_xlabel("elapsed [s]")
    axes[0, 1].set_ylabel("m")
    axes[0, 1].grid(True, alpha=0.3)
    axes[0, 1].legend(ncol=2)

    axes[1, 0].plot(t, speed)
    axes[1, 0].set_title("Kalman speed")
    axes[1, 0].set_xlabel("elapsed [s]")
    axes[1, 0].set_ylabel("m/s")
    axes[1, 0].grid(True, alpha=0.3)

    axes[1, 1].plot(t, heading_v, label="velocity heading")
    axes[1, 1].plot(t, heading_pca, label="PCA heading", alpha=0.8)
    axes[1, 1].set_title("Heading")
    axes[1, 1].set_xlabel("elapsed [s]")
    axes[1, 1].set_ylabel("deg")
    axes[1, 1].set_ylim(-5, 365)
    axes[1, 1].grid(True, alpha=0.3)
    axes[1, 1].legend()

    fig.savefig(path, dpi=160)
    plt.close(fig)


def print_summary(rows: list[dict[str, str]]) -> None:
    valid = [row for row in rows if row.get("status") == "ok" and row.get("x_kalman_m")]
    moving = [row for row in valid if row.get("is_moving") == "1"]
    if not valid:
        print("No valid Kalman rows.")
        return

    def arr(name: str, source: list[dict[str, str]] = valid) -> np.ndarray:
        return np.array([float(row[name]) for row in source if row.get(name)], dtype=float)

    t = arr("elapsed_s")
    print(f"Valid rows: {len(valid)}")
    if len(t) > 1:
        print(f"Duration: {float(np.nanmax(t) - np.nanmin(t)):.3f} s")
        print(f"Position rate: {len(valid) / float(np.nanmax(t) - np.nanmin(t)):.2f} Hz")
    print(f"Moving rows: {len(moving)}")
    print(f"Mean Kalman position: x={float(np.nanmean(arr('x_kalman_m'))):.3f} m, y={float(np.nanmean(arr('y_kalman_m'))):.3f} m")
    print(f"Kalman std: x={float(np.nanstd(arr('x_kalman_m'), ddof=1))*100:.2f} cm, y={float(np.nanstd(arr('y_kalman_m'), ddof=1))*100:.2f} cm")
    if moving:
        print(f"Moving mean speed: {float(np.nanmean(arr('speed_mps', moving))):.3f} m/s")
        print(f"Latest velocity heading: {float(arr('heading_velocity_deg', moving)[-1]):.1f} deg")
        pca = arr("heading_pca_deg", moving)
        if len(pca):
            print(f"Latest PCA heading: {float(pca[-1]):.1f} deg")


def main() -> int:
    args = parse_args()
    in_path = Path(args.csv)
    out_csv = Path(args.out_csv) if args.out_csv else in_path.with_suffix(".kalman_heading.csv")
    plot_path = Path(args.plot) if args.plot else out_csv.with_suffix(".png")

    rows = read_rows(in_path)
    processed = process_rows(args, rows)
    write_rows(out_csv, processed)
    write_plot(plot_path, processed)
    print_summary(processed)
    print(f"Wrote {out_csv}")
    print(f"Wrote {plot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
