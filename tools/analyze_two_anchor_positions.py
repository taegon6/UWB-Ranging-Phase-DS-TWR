#!/usr/bin/env python3
"""Summarize two-anchor positive-y position CSV files."""

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
    parser.add_argument("--log-dir", default="logs", help="Directory containing *.position.csv files")
    parser.add_argument("--out-dir", default="analysis", help="Directory for summary outputs")
    return parser.parse_args()


def load_rows(log_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(log_dir.glob("*.position.csv")):
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                status = row.get("status", "")
                x_text = row.get("x_m", "")
                y_text = row.get("y_m", "")
                xf_text = row.get("x_filtered_m", x_text)
                yf_text = row.get("y_filtered_m", y_text)
                rows.append(
                    {
                        "file": path.name,
                        "baseline_m": float(row["baseline_m"]),
                        "ranging_mode": row.get("ranging_mode", "unknown"),
                        "d_anchor_a_m": float(row["d_anchor_a_m"]),
                        "d_anchor_b_m": float(row["d_anchor_b_m"]),
                        "x_m": float(x_text) if x_text else math.nan,
                        "y_m": float(y_text) if y_text else math.nan,
                        "x_filtered_m": float(xf_text) if xf_text else math.nan,
                        "y_filtered_m": float(yf_text) if yf_text else math.nan,
                        "status": status,
                        "age_gap_s": float(row["age_gap_s"]),
                    }
                )
    return rows


def fmean(values: list[float]) -> float:
    return statistics.fmean(values) if values else math.nan


def stdev(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def summarize_by_file(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["file"])].append(row)

    summaries: list[dict[str, object]] = []
    for filename, group in sorted(grouped.items()):
        valid = [row for row in group if row["status"] == "ok" and not math.isnan(float(row["x_m"])) and not math.isnan(float(row["y_m"]))]
        xs = [float(row["x_m"]) for row in valid]
        ys = [float(row["y_m"]) for row in valid]
        xfs = [float(row["x_filtered_m"]) for row in valid if not math.isnan(float(row["x_filtered_m"]))]
        yfs = [float(row["y_filtered_m"]) for row in valid if not math.isnan(float(row["y_filtered_m"]))]
        d_as = [float(row["d_anchor_a_m"]) for row in valid]
        d_bs = [float(row["d_anchor_b_m"]) for row in valid]
        age_gaps = [float(row["age_gap_s"]) for row in valid]
        baseline = float(group[0]["baseline_m"]) if group else math.nan
        invalid = len(group) - len(valid)

        summaries.append(
            {
                "file": filename,
                "baseline_m": baseline,
                "ranging_mode": str(group[0].get("ranging_mode", "unknown")) if group else "unknown",
                "samples_total": len(group),
                "samples_valid": len(valid),
                "samples_invalid": invalid,
                "mean_x_m": fmean(xs),
                "mean_y_m": fmean(ys),
                "std_x_m": stdev(xs),
                "std_y_m": stdev(ys),
                "mean_x_filtered_m": fmean(xfs),
                "mean_y_filtered_m": fmean(yfs),
                "std_x_filtered_m": stdev(xfs),
                "std_y_filtered_m": stdev(yfs),
                "min_x_m": min(xs) if xs else math.nan,
                "max_x_m": max(xs) if xs else math.nan,
                "min_y_m": min(ys) if ys else math.nan,
                "max_y_m": max(ys) if ys else math.nan,
                "mean_d_anchor_a_m": fmean(d_as),
                "mean_d_anchor_b_m": fmean(d_bs),
                "mean_age_gap_s": fmean(age_gaps),
            }
        )
    return summaries


def write_summary_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "file",
        "baseline_m",
        "ranging_mode",
        "samples_total",
        "samples_valid",
        "samples_invalid",
        "mean_x_m",
        "mean_y_m",
        "std_x_m",
        "std_y_m",
        "mean_x_filtered_m",
        "mean_y_filtered_m",
        "std_x_filtered_m",
        "std_y_filtered_m",
        "min_x_m",
        "max_x_m",
        "min_y_m",
        "max_y_m",
        "mean_d_anchor_a_m",
        "mean_d_anchor_b_m",
        "mean_age_gap_s",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            formatted = row.copy()
            for key, value in list(formatted.items()):
                if isinstance(value, float):
                    formatted[key] = "" if math.isnan(value) else f"{value:.6f}"
            writer.writerow(formatted)


def write_markdown(path: Path, rows: list[dict[str, object]]) -> None:
    lines = [
        "# Two-Anchor UWB Position Summary",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
    ]
    if not rows:
        lines.append("No `*.position.csv` files found.")
    else:
        lines.extend(
            [
                "| file | mode | valid/total | filtered x m | filtered y m | filtered std x | filtered std y | raw std x | raw std y | invalid |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in rows:
            def fmt(key: str) -> str:
                value = row[key]
                if isinstance(value, float) and math.isnan(value):
                    return ""
                return f"{float(value):.3f}"

            lines.append(
                f"| {row['file']} | {row['ranging_mode']} | {row['samples_valid']}/{row['samples_total']} | "
                f"{fmt('mean_x_filtered_m')} | {fmt('mean_y_filtered_m')} | "
                f"{fmt('std_x_filtered_m')} | {fmt('std_y_filtered_m')} | "
                f"{fmt('std_x_m')} | {fmt('std_y_m')} | {row['samples_invalid']} |"
            )

        latest = rows[-1]
        if latest["samples_valid"]:
            lines.extend(
                [
                    "",
                    "## Latest Run",
                    "",
                    f"- File: `{latest['file']}`",
                    f"- Mean filtered tag position: x={float(latest['mean_x_filtered_m']):.3f} m, y={float(latest['mean_y_filtered_m']):.3f} m",
                    f"- Filtered position spread: std_x={float(latest['std_x_filtered_m']):.3f} m, std_y={float(latest['std_y_filtered_m']):.3f} m",
                    f"- Raw position spread: std_x={float(latest['std_x_m']):.3f} m, std_y={float(latest['std_y_m']):.3f} m",
                    f"- Valid samples: {latest['samples_valid']} / {latest['samples_total']}",
                ]
            )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    log_dir = Path(args.log_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(log_dir)
    summaries = summarize_by_file(rows)

    csv_path = out_dir / "two_anchor_position_summary.csv"
    md_path = out_dir / "two_anchor_position_summary.md"
    write_summary_csv(csv_path, summaries)
    write_markdown(md_path, summaries)

    print(f"Loaded {len(rows)} position rows from {log_dir}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
