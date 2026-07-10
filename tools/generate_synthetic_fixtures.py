#!/usr/bin/env python3
"""Generate deterministic logic, UART, and range fixtures without hardware."""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from _common import root_relative

from analysis.uart_analysis import encode_record


def _open_text(path: Path, force: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("w" if force else "x", encoding="utf-8", newline="")


def generate_logic(path: Path, seed: int, force: bool) -> None:
    rng = random.Random(seed)
    rows: list[dict[str, object]] = []

    def edge(timestamp: float, channel: str, value: int, frame_id: int) -> None:
        rows.append(
            {
                "timestamp_us": f"{timestamp:.6f}",
                "channel": channel,
                "value": value,
                "frame_id": frame_id,
                "source_type": "SYNTHETIC",
                "hardware_verified": "false",
            }
        )

    for frame in range(1, 61):
        base = (frame - 1) * 10_000.0
        edge(base, "FRAME_START", 1, frame)
        edge(base, "FRAME_ACTIVE", 1, frame)
        irq_at = base + 100.0 + rng.uniform(-1.5, 1.5)
        edge(irq_at, "IRQ_PIN", 1, frame)
        edge(irq_at + 3.0, "IRQ_PIN", 0, frame)
        irq_latency = (28.0 if frame == 17 else 7.0) + rng.uniform(-0.8, 0.8)
        isr_at = irq_at + irq_latency
        edge(isr_at, "ISR_ACTIVE", 1, frame)
        edge(isr_at + 20.0 + rng.uniform(-2.0, 2.0), "ISR_ACTIVE", 0, frame)
        timing = [
            ("SPI_STATUS", 150.0, 12.0),
            ("SPI_FRAME", 190.0, 34.0),
            ("CIR_READ", 260.0, 84.0 if frame != 33 else 150.0),
            ("SPI_CIR", 265.0, 72.0 if frame != 33 else 136.0),
            ("PHASE_PROCESS", 370.0, 26.0),
            ("FILTER_ACTIVE", 405.0, 9.0),
            ("UART_ENQUEUE", 430.0, 6.0),
            ("UART_TX", 450.0, 95.0),
        ]
        for channel, offset, duration in timing:
            start = base + offset + rng.uniform(-1.0, 1.0)
            edge(start, channel, 1, frame)
            if not (frame == 23 and channel == "CIR_READ"):
                edge(start + duration + rng.uniform(-1.0, 1.0), channel, 0, frame)
        edge(base + 600.0, "FRAME_ACTIVE", 0, frame)

    rows.sort(key=lambda row: (float(row["timestamp_us"]), str(row["channel"])))
    with _open_text(path, force) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp_us", "channel", "value", "frame_id", "source_type", "hardware_verified"],
        )
        writer.writeheader()
        writer.writerows(rows)


def generate_uart(path: Path, force: bool) -> None:
    blob = bytearray()
    for frame in range(1, 13):
        for slot, link in enumerate(["A1-T1", "A2-T1", "A1-T2", "A2-T2"]):
            record = encode_record(
                {
                    "boot_id": 1,
                    "superframe_id": frame,
                    "frame_id": frame * 10 + slot,
                    "slot_id": slot,
                    "link_id": link,
                    "range_raw_m": 1.0 + 0.05 * slot,
                    "range_phase_m": None,
                    "success": not (frame == 8 and slot == 3),
                    "retry_count": 1 if frame == 8 and slot == 3 else 0,
                }
            )
            if frame == 5 and slot == 1:
                record = bytearray(record)
                record[len(record) // 2] ^= 0x55
                record = bytes(record)
            blob.extend(record)
    blob.extend(b"CORRUPT_TAIL")
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if force else "xb"
    with path.open(mode) as handle:
        handle.write(blob)


def generate_ranges(path: Path, force: bool) -> None:
    with _open_text(path, force) as handle:
        fields = ["candidate", "reference_distance_m", "measured_distance_m", "link_id", "source_type", "hardware_verified"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for candidate in range(16360, 16411, 10):
            for link_index, link in enumerate(["A1-T1", "A2-T1", "A1-T2", "A2-T2"]):
                for reference in [0.5, 1.0, 2.0, 3.0]:
                    writer.writerow(
                        {
                            "candidate": candidate,
                            "reference_distance_m": reference,
                            "measured_distance_m": reference + (candidate - 16385) * 0.00012 + link_index * 0.0002,
                            "link_id": link,
                            "source_type": "SYNTHETIC",
                            "hardware_verified": "false",
                        }
                    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="tests/fixtures")
    parser.add_argument("--seed", type=int, default=20260710)
    parser.add_argument("--force", action="store_true", help="Explicitly replace generated fixtures")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = root_relative(args.output_dir)
    generate_logic(output / "synthetic_logic_capture.csv", args.seed, args.force)
    generate_uart(output / "synthetic_uart_log.bin", args.force)
    generate_ranges(output / "synthetic_range_calibration.csv", args.force)
    print(f"Generated synthetic fixtures in {output}")
    print("source_type = SYNTHETIC")
    print("hardware_verified = false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
