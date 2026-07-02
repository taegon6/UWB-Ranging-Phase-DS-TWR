#!/usr/bin/env python3
"""Analyze parsed DW3000 DS-TWR distance CSV files."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", default="logs", help="Directory containing *.dist.csv files")
    parser.add_argument("--out-dir", default="analysis", help="Directory for summary outputs")
    parser.add_argument("--outlier-m", type=float, default=0.50, help="Count samples with abs(error) above this value")
    return parser.parse_args()


def load_rows(log_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(log_dir.glob("*.dist.csv")):
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                true_m = float(row["distance_m_true"])
                measured_m = float(row["distance_m_measured"])
                rows.append(
                    {
                        "file": path.name,
                        "mode": row["mode"],
                        "true_m": true_m,
                        "measured_m": measured_m,
                        "error_m": measured_m - true_m,
                    }
                )
    return rows


def pct(values: list[float], percentile: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    pos = (len(ordered) - 1) * percentile / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[int(pos)]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def summarize(rows: list[dict[str, object]], outlier_m: float) -> list[dict[str, object]]:
    groups: dict[tuple[str, float], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["mode"]), float(row["true_m"]))].append(row)

    summary: list[dict[str, object]] = []
    for (mode, true_m), group in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0])):
        measured = [float(row["measured_m"]) for row in group]
        errors = [float(row["error_m"]) for row in group]
        abs_errors = [abs(v) for v in errors]
        n = len(group)
        mean_measured = statistics.fmean(measured)
        mean_error = statistics.fmean(errors)
        std_measured = statistics.stdev(measured) if n > 1 else 0.0
        rmse = math.sqrt(statistics.fmean([v * v for v in errors]))
        outliers = sum(1 for v in abs_errors if v > outlier_m)
        files = sorted({str(row["file"]) for row in group})
        summary.append(
            {
                "mode": mode,
                "true_m": true_m,
                "samples": n,
                "mean_measured_m": mean_measured,
                "mean_error_m": mean_error,
                "std_measured_m": std_measured,
                "rmse_m": rmse,
                "median_abs_error_m": pct(abs_errors, 50),
                "p95_abs_error_m": pct(abs_errors, 95),
                "min_measured_m": min(measured),
                "max_measured_m": max(measured),
                "outliers": outliers,
                "files": ";".join(files),
            }
        )
    return summary


def write_summary_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "mode",
        "true_m",
        "samples",
        "mean_measured_m",
        "mean_error_m",
        "std_measured_m",
        "rmse_m",
        "median_abs_error_m",
        "p95_abs_error_m",
        "min_measured_m",
        "max_measured_m",
        "outliers",
        "files",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            formatted = row.copy()
            for key, value in list(formatted.items()):
                if isinstance(value, float):
                    formatted[key] = f"{value:.6f}"
            writer.writerow(formatted)


def write_markdown(path: Path, rows: list[dict[str, object]], outlier_m: float) -> None:
    lines = [
        "# UWB DS-TWR Distance Analysis",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Outlier threshold: abs(error) > {outlier_m:.3f} m",
        "",
    ]

    if not rows:
        lines.append("No parsed distance samples found.")
    else:
        lines.extend(
            [
                "| mode | true m | samples | mean measured m | mean error m | std m | rmse m | p95 abs error m | outliers |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in rows:
            lines.append(
                "| {mode} | {true_m:.2f} | {samples} | {mean_measured_m:.3f} | {mean_error_m:.3f} | "
                "{std_measured_m:.3f} | {rmse_m:.3f} | {p95_abs_error_m:.3f} | {outliers} |".format(**row)
            )

        by_distance: dict[float, list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            by_distance[float(row["true_m"])].append(row)

        lines.extend(["", "## Quick Comparison", ""])
        for true_m, group in sorted(by_distance.items()):
            best = min(group, key=lambda row: (float(row["rmse_m"]), float(row["std_measured_m"])))
            lines.append(
                f"- {true_m:.2f} m: best current run is `{best['mode']}` "
                f"(RMSE {float(best['rmse_m']):.3f} m, std {float(best['std_measured_m']):.3f} m)."
            )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    log_dir = Path(args.log_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(log_dir)
    summary = summarize(rows, args.outlier_m)

    csv_path = out_dir / "distance_summary.csv"
    md_path = out_dir / "distance_summary.md"
    write_summary_csv(csv_path, summary)
    write_markdown(md_path, summary, args.outlier_m)

    print(f"Loaded {len(rows)} samples from {log_dir}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
