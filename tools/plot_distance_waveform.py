#!/usr/bin/env python3
"""Plot anchor distance waveforms from a two-anchor position CSV."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", help="Path to *.position.csv")
    parser.add_argument("--out", help="Output PNG path. Defaults to <csv>.distance_wave.png")
    parser.add_argument("--title", default="UWB Distance Waveform")
    parser.add_argument("--target-a-cm", type=float, help="Optional A1 reference line in cm")
    parser.add_argument("--target-b-cm", type=float, help="Optional B2 reference line in cm")
    parser.add_argument("--single", choices=["A1", "B2"], help="Plot only one anchor")
    return parser.parse_args()


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else math.nan


def read_distances(path: Path) -> tuple[list[float], list[float]]:
    a_cm: list[float] = []
    b_cm: list[float] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                a_cm.append(float(row["d_anchor_a_m"]) * 100.0)
                b_cm.append(float(row["d_anchor_b_m"]) * 100.0)
            except (KeyError, ValueError):
                continue
    return a_cm, b_cm


def cm_formatter():
    from matplotlib.ticker import FuncFormatter

    return FuncFormatter(lambda y, _: f"{y:.0f} cm")


def set_y_limits(ax, values: list[float]) -> None:
    center = mean(values)
    spread = max(2.0, max(abs(v - center) for v in values) + 1.0)
    ax.set_ylim(center - spread, center + spread)


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv_path)
    out_path = Path(args.out) if args.out else csv_path.with_suffix(".distance_wave.png")
    a_cm, b_cm = read_distances(csv_path)
    if not a_cm or not b_cm:
        raise SystemExit(f"No distance rows found in {csv_path}")

    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit("matplotlib is required. Run: python -m pip install matplotlib") from exc

    series = []
    if args.single in (None, "A1"):
        series.append(("A1 distance", a_cm, args.target_a_cm if args.target_a_cm is not None else mean(a_cm), "#58a9f6"))
    if args.single in (None, "B2"):
        series.append(("B2 distance", b_cm, args.target_b_cm if args.target_b_cm is not None else mean(b_cm), "#42b883"))

    fig, axes_obj = plt.subplots(len(series), 1, figsize=(11, 3.2 * len(series)), sharex=True)
    axes = axes_obj if isinstance(axes_obj, list) else getattr(axes_obj, "flat", [axes_obj])
    for ax, (label, values, target, color) in zip(axes, series):
        xs = list(range(len(values)))
        ax.plot(xs, values, color=color, linewidth=1.3)
        ax.axhline(target, color="red", linestyle=(0, (4, 4)), linewidth=1.4, alpha=0.85)
        ax.set_ylabel(label)
        ax.yaxis.set_major_formatter(cm_formatter())
        set_y_limits(ax, values)
        ax.grid(True, alpha=0.22)

    axes[0].set_title(args.title)
    axes[-1].set_xlabel("index")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
