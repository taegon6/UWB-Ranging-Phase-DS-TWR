#!/usr/bin/env python3
"""Collect DW3000 DS-TWR distance logs from a serial port.

The firmware prints lines such as:

    DIST: 1.23 m

This script stores both the raw serial stream and a parsed CSV so the same
capture can be inspected manually and analyzed automatically.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

DIST_RE = re.compile(r"DIST:\s*([-+]?\d+(?:\.\d+)?)\s*m", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Serial port, for example COM3")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baudrate")
    parser.add_argument("--duration", type=float, default=60.0, help="Capture duration in seconds")
    parser.add_argument("--mode", choices=["origin", "final", "baseline", "custom"], required=True)
    parser.add_argument("--distance-m", type=float, required=True, help="Measured ground-truth distance in meters")
    parser.add_argument("--role", default="responder", help="Board role printed by this port")
    parser.add_argument("--tag", default="", help="Optional run label, for example desk_los")
    parser.add_argument("--out-dir", default="logs", help="Output directory")
    return parser.parse_args()


def safe_token(value: str) -> str:
    value = value.strip().replace("\\", "_").replace("/", "_").replace(":", "")
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value) or "run"


def make_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    distance = f"{args.distance_m:.2f}m".replace(".", "p")
    parts = [stamp, args.mode, distance, safe_token(args.port)]
    if args.tag:
        parts.append(safe_token(args.tag))
    stem = "_".join(parts)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{stem}.raw.txt", out_dir / f"{stem}.dist.csv", out_dir / f"{stem}.meta.json"


def open_serial(port: str, baud: int):
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("pyserial is required. Run: python -m pip install pyserial") from exc

    return serial.Serial(port=port, baudrate=baud, timeout=1)


def main() -> int:
    args = parse_args()
    raw_path, csv_path, meta_path = make_paths(args)

    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "port": args.port,
        "baud": args.baud,
        "duration_s": args.duration,
        "mode": args.mode,
        "role": args.role,
        "distance_m": args.distance_m,
        "tag": args.tag,
        "raw_log": str(raw_path),
        "distance_csv": str(csv_path),
    }

    print(f"Opening {args.port} at {args.baud} baud")
    print(f"Saving raw log: {raw_path}")
    print(f"Saving parsed distances: {csv_path}")
    print("Press Ctrl+C to stop early.")

    sample_count = 0
    start = time.monotonic()

    try:
        with open_serial(args.port, args.baud) as ser, raw_path.open("w", encoding="utf-8", newline="") as raw_file, csv_path.open(
            "w", encoding="utf-8", newline=""
        ) as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["elapsed_s", "timestamp", "mode", "distance_m_true", "distance_m_measured", "raw_line"])

            while (time.monotonic() - start) < args.duration:
                data = ser.readline()
                if not data:
                    continue

                line = data.decode("utf-8", errors="replace").strip()
                now = datetime.now().isoformat(timespec="milliseconds")
                elapsed = time.monotonic() - start
                raw_file.write(f"{now},{elapsed:.3f},{line}\n")
                raw_file.flush()

                print(line)
                match = DIST_RE.search(line)
                if not match:
                    continue

                measured = float(match.group(1))
                writer.writerow([f"{elapsed:.3f}", now, args.mode, f"{args.distance_m:.6f}", f"{measured:.6f}", line])
                csv_file.flush()
                sample_count += 1
    except KeyboardInterrupt:
        print("\nStopped by user.")

    meta["samples"] = sample_count
    meta["elapsed_s_actual"] = round(time.monotonic() - start, 3)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Captured {sample_count} DIST samples")
    print(f"Metadata: {meta_path}")
    return 0 if sample_count else 2


if __name__ == "__main__":
    sys.exit(main())
