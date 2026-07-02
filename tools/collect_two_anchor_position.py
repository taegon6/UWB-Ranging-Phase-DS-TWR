#!/usr/bin/env python3
"""Collect two-anchor UWB distances and estimate 2D tag position.

Anchor geometry:

    anchor A = (0, 0)
    anchor B = (baseline, 0)

For distances dA and dB, the two-circle solution is:

    x = (dA^2 - dB^2 + baseline^2) / (2 * baseline)
    y = +/-sqrt(dA^2 - x^2)

This script keeps only the positive-y solution.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DIST_RE = re.compile(r"DIST:\s*([-+]?\d+(?:\.\d+)?)\s*m", re.IGNORECASE)


@dataclass
class AnchorSample:
    distance_m: float
    timestamp: str
    monotonic_s: float
    raw_line: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port-a", required=True, help="Serial port for anchor A, for example COM3")
    parser.add_argument("--port-b", required=True, help="Serial port for anchor B, for example COM4")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--baseline-m", type=float, default=2.5, help="Anchor spacing in meters")
    parser.add_argument("--ranging-mode", choices=["ss-twr", "ds-twr"], default="ds-twr")
    parser.add_argument("--duration", type=float, default=60.0, help="Capture duration in seconds")
    parser.add_argument("--max-age-s", type=float, default=0.75, help="Max age gap between A/B samples")
    parser.add_argument("--position-median-window", type=int, default=30, help="Median filter window for x/y positions")
    parser.add_argument("--tag", default="two_anchor", help="Optional run label")
    parser.add_argument("--out-dir", default="logs", help="Output directory")
    parser.add_argument("--no-plot", action="store_true", help="Skip PNG map generation")
    return parser.parse_args()


def safe_token(value: str) -> str:
    value = value.strip().replace("\\", "_").replace("/", "_").replace(":", "")
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value) or "run"


def make_paths(args: argparse.Namespace) -> dict[str, Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    baseline = f"B{args.baseline_m:.2f}m".replace(".", "p")
    stem = "_".join(
        [stamp, "2anchor", safe_token(args.ranging_mode), baseline, safe_token(args.port_a), safe_token(args.port_b), safe_token(args.tag)]
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "raw_a": out_dir / f"{stem}.anchorA.raw.txt",
        "raw_b": out_dir / f"{stem}.anchorB.raw.txt",
        "position_csv": out_dir / f"{stem}.position.csv",
        "meta": out_dir / f"{stem}.meta.json",
        "map_png": out_dir / f"{stem}.map.png",
    }


def open_serial(port: str, baud: int):
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("pyserial is required. Run: python -m pip install pyserial") from exc

    return serial.Serial(port=port, baudrate=baud, timeout=0.05)


def parse_distance(line: str) -> float | None:
    match = DIST_RE.search(line)
    if not match:
        return None
    return float(match.group(1))


def solve_positive_y(d_a: float, d_b: float, baseline: float) -> tuple[float, float, str]:
    if baseline <= 0:
        return math.nan, math.nan, "bad_baseline"
    if d_a < 0 or d_b < 0:
        return math.nan, math.nan, "negative_distance"

    x = (d_a * d_a - d_b * d_b + baseline * baseline) / (2.0 * baseline)
    y_sq = d_a * d_a - x * x
    if y_sq < -1e-6:
        return x, math.nan, "no_intersection"
    y = math.sqrt(max(0.0, y_sq))
    return x, y, "ok"


def read_anchor_line(ser, raw_file, anchor_name: str, start: float) -> AnchorSample | None:
    data = ser.readline()
    if not data:
        return None
    line = data.decode("utf-8", errors="replace").strip()
    now = datetime.now().isoformat(timespec="milliseconds")
    elapsed = time.monotonic() - start
    raw_file.write(f"{now},{elapsed:.3f},{anchor_name},{line}\n")
    raw_file.flush()
    print(f"{anchor_name}: {line}")

    distance = parse_distance(line)
    if distance is None:
        return None
    return AnchorSample(distance_m=distance, timestamp=now, monotonic_s=time.monotonic(), raw_line=line)


def median(values: deque[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return math.nan
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def write_map_png(path: Path, rows: list[dict[str, float]], baseline: float) -> None:
    if not rows:
        return
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is not installed; skipping map PNG. Run: python -m pip install matplotlib")
        return

    xs = [row.get("x_filtered_m", row["x_m"]) for row in rows if row["status"] == "ok"]
    ys = [row.get("y_filtered_m", row["y_m"]) for row in rows if row["status"] == "ok"]
    if not xs:
        return

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter([0, baseline], [0, 0], marker="^", s=140, color="#d62728", label="anchors")
    ax.text(0, -0.08, "A (0,0)", ha="center", va="top")
    ax.text(baseline, -0.08, f"B ({baseline:.2f},0)", ha="center", va="top")
    ax.plot(xs, ys, color="#1f77b4", linewidth=1, alpha=0.55)
    ax.scatter(xs, ys, s=18, color="#1f77b4", label="tag estimates")
    ax.scatter([xs[-1]], [ys[-1]], s=80, color="#2ca02c", label="latest")
    ax.set_title("Two-anchor UWB tag position, positive-y solution")
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


def main() -> int:
    args = parse_args()
    paths = make_paths(args)
    positions: list[dict[str, float | str]] = []

    latest_a: AnchorSample | None = None
    latest_b: AnchorSample | None = None
    last_pair: tuple[str, str] | None = None
    x_window: deque[float] = deque(maxlen=max(1, args.position_median_window))
    y_window: deque[float] = deque(maxlen=max(1, args.position_median_window))
    start = time.monotonic()

    print(f"Anchor A: {args.port_a} -> (0, 0)")
    print(f"Anchor B: {args.port_b} -> ({args.baseline_m}, 0)")
    print(f"Ranging mode label: {args.ranging_mode}")
    print(f"Position median filter window: {args.position_median_window}")
    print("Only positive-y position estimates are written.")
    print(f"Position CSV: {paths['position_csv']}")

    with open_serial(args.port_a, args.baud) as ser_a, open_serial(args.port_b, args.baud) as ser_b, paths["raw_a"].open(
        "w", encoding="utf-8", newline=""
    ) as raw_a, paths["raw_b"].open("w", encoding="utf-8", newline="") as raw_b, paths["position_csv"].open(
        "w", encoding="utf-8", newline=""
    ) as pos_file:
        writer = csv.writer(pos_file)
        writer.writerow(
            [
                "elapsed_s",
                "timestamp",
                "baseline_m",
                "ranging_mode",
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

        try:
            while (time.monotonic() - start) < args.duration:
                got_new_sample = False
                sample_a = read_anchor_line(ser_a, raw_a, "A", start)
                if sample_a:
                    latest_a = sample_a
                    got_new_sample = True

                sample_b = read_anchor_line(ser_b, raw_b, "B", start)
                if sample_b:
                    latest_b = sample_b
                    got_new_sample = True

                if latest_a is None or latest_b is None:
                    continue
                if not got_new_sample:
                    continue

                now_mono = time.monotonic()
                if (now_mono - latest_a.monotonic_s) > args.max_age_s or (now_mono - latest_b.monotonic_s) > args.max_age_s:
                    continue

                age_gap = abs(latest_a.monotonic_s - latest_b.monotonic_s)
                if age_gap > args.max_age_s:
                    continue
                pair = (latest_a.timestamp, latest_b.timestamp)
                if pair == last_pair:
                    continue
                last_pair = pair

                x, y, status = solve_positive_y(latest_a.distance_m, latest_b.distance_m, args.baseline_m)
                if status == "ok":
                    x_window.append(x)
                    y_window.append(y)
                    x_filtered = median(x_window)
                    y_filtered = median(y_window)
                else:
                    x_filtered = math.nan
                    y_filtered = math.nan
                elapsed = time.monotonic() - start
                timestamp = datetime.now().isoformat(timespec="milliseconds")
                writer.writerow(
                    [
                        f"{elapsed:.3f}",
                        timestamp,
                        f"{args.baseline_m:.6f}",
                        args.ranging_mode,
                        f"{latest_a.distance_m:.6f}",
                        f"{latest_b.distance_m:.6f}",
                        "" if math.isnan(x) else f"{x:.6f}",
                        "" if math.isnan(y) else f"{y:.6f}",
                        "" if math.isnan(x_filtered) else f"{x_filtered:.6f}",
                        "" if math.isnan(y_filtered) else f"{y_filtered:.6f}",
                        status,
                        f"{age_gap:.3f}",
                        latest_a.raw_line,
                        latest_b.raw_line,
                    ]
                )
                pos_file.flush()
                positions.append(
                    {
                        "x_m": x,
                        "y_m": y,
                        "x_filtered_m": x_filtered,
                        "y_filtered_m": y_filtered,
                        "status": status,
                    }
                )
                if status == "ok":
                    print(
                        f"TAG: x={x:.3f} m, y={y:.3f} m, "
                        f"filtered=({x_filtered:.3f}, {y_filtered:.3f})  "
                        f"(dA={latest_a.distance_m:.3f}, dB={latest_b.distance_m:.3f})"
                    )
                else:
                    print(f"TAG: invalid geometry ({status})  dA={latest_a.distance_m:.3f}, dB={latest_b.distance_m:.3f}")
        except KeyboardInterrupt:
            print("\nStopped by user.")

    ok_count = sum(1 for row in positions if row["status"] == "ok")
    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "port_a": args.port_a,
        "port_b": args.port_b,
        "baud": args.baud,
        "baseline_m": args.baseline_m,
        "ranging_mode": args.ranging_mode,
        "duration_s": args.duration,
        "max_age_s": args.max_age_s,
        "position_median_window": args.position_median_window,
        "tag": args.tag,
        "position_samples": len(positions),
        "valid_positive_y_samples": ok_count,
        "raw_anchor_a": str(paths["raw_a"]),
        "raw_anchor_b": str(paths["raw_b"]),
        "position_csv": str(paths["position_csv"]),
        "map_png": str(paths["map_png"]),
    }
    paths["meta"].write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if not args.no_plot:
        write_map_png(paths["map_png"], positions, args.baseline_m)

    print(f"Valid positive-y samples: {ok_count}/{len(positions)}")
    print(f"Metadata: {paths['meta']}")
    if not args.no_plot:
        print(f"Map PNG: {paths['map_png']}")
    return 0 if ok_count else 2


if __name__ == "__main__":
    sys.exit(main())
