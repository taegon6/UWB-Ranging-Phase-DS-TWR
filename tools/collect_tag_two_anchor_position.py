#!/usr/bin/env python3
"""Collect two-anchor position estimates from one tag UART.

Expected tag UART lines:

    ANCHOR:A1 DIST: 0.630 m
    ANCHOR:B2 DIST: 1.040 m

Anchor A1 is treated as (0, 0), anchor B2 as (baseline, 0), and only the
positive-y two-circle solution is written.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LINE_RE = re.compile(r"ANCHOR:(A1|B2)\s+DIST:\s*([-+]?\d+(?:\.\d+)?)\s*m", re.IGNORECASE)


@dataclass
class Sample:
    anchor: str
    distance_m: float
    timestamp: str
    monotonic_s: float
    raw_line: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag-port", required=True, help="Tag serial port, for example COM8")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--baseline-m", type=float, default=2.5)
    parser.add_argument("--max-age-s", type=float, default=1.0)
    parser.add_argument("--position-median-window", type=int, default=30)
    parser.add_argument("--tag", default="tag_two_anchor")
    parser.add_argument("--out-dir", default="logs/tag_two_anchor")
    parser.add_argument("--no-plot", action="store_true")
    return parser.parse_args()


def safe_token(value: str) -> str:
    value = value.strip().replace("\\", "_").replace("/", "_").replace(":", "")
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value) or "run"


def make_paths(args: argparse.Namespace) -> dict[str, Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    baseline = f"B{args.baseline_m:.2f}m".replace(".", "p")
    stem = "_".join([stamp, "tag_2anchor", baseline, safe_token(args.tag_port), safe_token(args.tag)])
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "raw": out_dir / f"{stem}.raw.txt",
        "position_csv": out_dir / f"{stem}.position.csv",
        "meta": out_dir / f"{stem}.meta.json",
        "map_png": out_dir / f"{stem}.map.png",
        "distance_wave_png": out_dir / f"{stem}.distance_wave.png",
    }


def open_serial(port: str, baud: int):
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("pyserial is required. Run: python -m pip install pyserial") from exc
    return serial.Serial(port=port, baudrate=baud, timeout=0.05)


def parse_line(line: str) -> tuple[str, float] | None:
    match = LINE_RE.search(line)
    if not match:
        return None
    return match.group(1).upper(), float(match.group(2))


def solve_positive_y(d_a: float, d_b: float, baseline: float) -> tuple[float, float, str]:
    if baseline <= 0:
        return math.nan, math.nan, "bad_baseline"
    if d_a < 0 or d_b < 0:
        return math.nan, math.nan, "negative_distance"
    x = (d_a * d_a - d_b * d_b + baseline * baseline) / (2.0 * baseline)
    y_sq = d_a * d_a - x * x
    if y_sq < -1e-6:
        return x, math.nan, "no_intersection"
    return x, math.sqrt(max(0.0, y_sq)), "ok"


def median(values: deque[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def write_map_png(path: Path, rows: list[dict[str, float | str]], baseline: float) -> None:
    ok_rows = [row for row in rows if row["status"] == "ok"]
    if not ok_rows:
        return
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is not installed; skipping map PNG.")
        return

    xs = [float(row["x_filtered_m"]) for row in ok_rows]
    ys = [float(row["y_filtered_m"]) for row in ok_rows]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter([0, baseline], [0, 0], marker="^", s=140, color="#d62728", label="anchors")
    ax.text(0, -0.08, "A1 (0,0)", ha="center", va="top")
    ax.text(baseline, -0.08, f"B2 ({baseline:.2f},0)", ha="center", va="top")
    ax.plot(xs, ys, color="#1f77b4", linewidth=1, alpha=0.55)
    ax.scatter(xs, ys, s=18, color="#1f77b4", label="tag")
    ax.scatter([xs[-1]], [ys[-1]], s=80, color="#2ca02c", label="latest")
    ax.set_title("Tag-side two-anchor UWB position")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_xlim(min(-0.5, min(xs) - 0.3), max(baseline + 0.5, max(xs) + 0.3))
    ax.set_ylim(0, max(1.0, max(ys) + 0.3))
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _finite_column(rows: list[dict[str, float | str]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        number = float(value)
        if math.isfinite(number):
            values.append(number)
    return values


def write_distance_wave_png(path: Path, rows: list[dict[str, float | str]], title: str) -> None:
    if not rows:
        return
    try:
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter
    except ImportError:
        print("matplotlib is not installed; skipping distance wave PNG.")
        return

    a_cm = [float(row["d_anchor_a_m"]) * 100.0 for row in rows]
    b_cm = [float(row["d_anchor_b_m"]) * 100.0 for row in rows]
    xs = list(range(len(rows)))
    target_a = statistics_mean(a_cm)
    target_b = statistics_mean(b_cm)
    all_values = a_cm + b_cm
    center = statistics_mean(all_values)
    spread = max(2.0, max(abs(v - center) for v in all_values) + 1.0)

    fig, axes = plt.subplots(2, 1, figsize=(11, 5.8), sharex=True)
    for ax, values, target, label, color in [
        (axes[0], a_cm, target_a, "A1 distance", "#58a9f6"),
        (axes[1], b_cm, target_b, "B2 distance", "#42b883"),
    ]:
        ax.plot(xs, values, color=color, linewidth=1.3)
        ax.axhline(target, color="red", linestyle=(0, (4, 4)), linewidth=1.4, alpha=0.8)
        ax.set_ylabel(label)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.0f} cm"))
        local_center = statistics_mean(values)
        local_spread = max(spread * 0.4, max(abs(v - local_center) for v in values) + 1.0)
        ax.set_ylim(local_center - local_spread, local_center + local_spread)
        ax.grid(True, alpha=0.22)

    axes[0].set_title(title)
    axes[1].set_xlabel("index")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def statistics_mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else math.nan


def main() -> int:
    args = parse_args()
    paths = make_paths(args)
    start = time.monotonic()
    latest: dict[str, Sample] = {}
    last_pair: tuple[str, str] | None = None
    x_window: deque[float] = deque(maxlen=max(1, args.position_median_window))
    y_window: deque[float] = deque(maxlen=max(1, args.position_median_window))
    rows: list[dict[str, float | str]] = []

    print(f"Tag UART: {args.tag_port} @ {args.baud}")
    print("Anchor A1 -> (0, 0)")
    print(f"Anchor B2 -> ({args.baseline_m}, 0)")
    print(f"Position CSV: {paths['position_csv']}")

    with open_serial(args.tag_port, args.baud) as ser, paths["raw"].open("w", encoding="utf-8", newline="") as raw_file, paths[
        "position_csv"
    ].open("w", encoding="utf-8", newline="") as pos_file:
        writer = csv.writer(pos_file)
        writer.writerow(
            [
                "elapsed_s",
                "timestamp",
                "baseline_m",
                "d_anchor_a_m",
                "d_anchor_b_m",
                "x_m",
                "y_m",
                "x_filtered_m",
                "y_filtered_m",
                "status",
                "age_gap_s",
                "raw_anchor_a",
                "raw_anchor_b",
            ]
        )

        while (time.monotonic() - start) < args.duration:
            data = ser.readline()
            if not data:
                continue
            line = data.decode("utf-8", errors="replace").strip()
            now_iso = datetime.now().isoformat(timespec="milliseconds")
            elapsed = time.monotonic() - start
            raw_file.write(f"{now_iso},{elapsed:.3f},{line}\n")
            raw_file.flush()
            print(line)

            parsed = parse_line(line)
            if not parsed:
                continue
            anchor, distance = parsed
            latest[anchor] = Sample(anchor, distance, now_iso, time.monotonic(), line)

            if "A1" not in latest or "B2" not in latest:
                continue
            a = latest["A1"]
            b = latest["B2"]
            age_gap = abs(a.monotonic_s - b.monotonic_s)
            if age_gap > args.max_age_s:
                continue
            pair = (a.timestamp, b.timestamp)
            if pair == last_pair:
                continue
            last_pair = pair

            x, y, status = solve_positive_y(a.distance_m, b.distance_m, args.baseline_m)
            if status == "ok":
                x_window.append(x)
                y_window.append(y)
                x_filtered = median(x_window)
                y_filtered = median(y_window)
            else:
                x_filtered = math.nan
                y_filtered = math.nan

            row = {
                "elapsed_s": elapsed,
                "timestamp": now_iso,
                "baseline_m": args.baseline_m,
                "d_anchor_a_m": a.distance_m,
                "d_anchor_b_m": b.distance_m,
                "x_m": x,
                "y_m": y,
                "x_filtered_m": x_filtered,
                "y_filtered_m": y_filtered,
                "status": status,
                "age_gap_s": age_gap,
                "raw_anchor_a": a.raw_line,
                "raw_anchor_b": b.raw_line,
            }
            rows.append(row)
            writer.writerow(
                [
                    f"{elapsed:.3f}",
                    now_iso,
                    f"{args.baseline_m:.3f}",
                    f"{a.distance_m:.3f}",
                    f"{b.distance_m:.3f}",
                    f"{x:.3f}" if math.isfinite(x) else "",
                    f"{y:.3f}" if math.isfinite(y) else "",
                    f"{x_filtered:.3f}" if math.isfinite(x_filtered) else "",
                    f"{y_filtered:.3f}" if math.isfinite(y_filtered) else "",
                    status,
                    f"{age_gap:.3f}",
                    a.raw_line,
                    b.raw_line,
                ]
            )
            pos_file.flush()

    valid = sum(1 for row in rows if row["status"] == "ok")
    meta = {
        "tag_port": args.tag_port,
        "baud": args.baud,
        "baseline_m": args.baseline_m,
        "duration_s": args.duration,
        "samples_total": len(rows),
        "samples_valid": valid,
        "outputs": {key: str(value) for key, value in paths.items()},
    }
    paths["meta"].write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if not args.no_plot:
        write_map_png(paths["map_png"], rows, args.baseline_m)
        write_distance_wave_png(paths["distance_wave_png"], rows, "UWB Distance Waveform")
    print(f"Valid positive-y samples: {valid}/{len(rows)}")
    print(f"Metadata: {paths['meta']}")
    print(f"Map PNG: {paths['map_png']}")
    print(f"Distance wave PNG: {paths['distance_wave_png']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
