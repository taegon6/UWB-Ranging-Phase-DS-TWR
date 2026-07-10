"""Logic edge loading, pulse pairing, segmentation, and derived timing tables."""

from __future__ import annotations

import csv
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from analysis.timing_statistics import percentile, summarize_timing


@dataclass(frozen=True)
class Edge:
    timestamp_us: float
    channel: str
    value: int
    frame_id: int | None = None


@dataclass(frozen=True)
class Pulse:
    channel: str
    frame_id: int | None
    start_us: float
    end_us: float
    duration_us: float


PULSE_METRICS = {
    "ISR_ACTIVE": "isr_duration",
    "SPI_STATUS": "spi_status_duration",
    "SPI_FRAME": "spi_frame_duration",
    "SPI_CIR": "spi_cir_duration",
    "UART_ENQUEUE": "uart_enqueue_duration",
    "UART_TX": "uart_physical_tx_duration",
    "CIR_READ": "cir_read_duration",
    "PHASE_PROCESS": "phase_processing_duration",
    "FILTER_ACTIVE": "filter_duration",
    "FRAME_ACTIVE": "frame_duration",
}


def load_edges(path: Path | str, channel_map: dict[str, str] | None = None) -> list[Edge]:
    """Load canonical long-form CSV while preserving every raw edge."""

    path = Path(path)
    mapping = channel_map or {}
    edges: list[Edge] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp_us", "channel", "value"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"logic CSV must contain {sorted(required)}")
        for row_number, row in enumerate(reader, start=2):
            try:
                channel = mapping.get(row["channel"], row["channel"]).strip()
                frame_text = (row.get("frame_id") or "").strip()
                edges.append(
                    Edge(
                        timestamp_us=float(row["timestamp_us"]),
                        channel=channel,
                        value=int(row["value"]),
                        frame_id=int(frame_text) if frame_text else None,
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid logic edge at row {row_number}: {exc}") from exc
    return segment_frames(sorted(edges, key=lambda item: (item.timestamp_us, item.channel)))


def segment_frames(edges: list[Edge]) -> list[Edge]:
    """Assign frame IDs from FRAME_START/FRAME_ACTIVE markers when CSV rows lack them."""

    if not edges or all(edge.frame_id is not None for edge in edges):
        return edges
    marker_channel = "FRAME_START" if any(edge.channel == "FRAME_START" for edge in edges) else "FRAME_ACTIVE"
    current_frame: int | None = None
    next_frame = 0
    segmented: list[Edge] = []
    for edge in edges:
        if edge.channel == marker_channel and edge.value == 1:
            if edge.frame_id is not None:
                current_frame = edge.frame_id
                next_frame = max(next_frame, current_frame)
            else:
                next_frame += 1
                current_frame = next_frame
        segmented.append(
            edge
            if edge.frame_id is not None
            else Edge(edge.timestamp_us, edge.channel, edge.value, current_frame)
        )
    return segmented


def pair_pulses(edges: list[Edge], channel: str) -> tuple[list[Pulse], list[dict[str, Any]]]:
    """Pair 0->1/1->0 transitions and report overlaps or missing edges."""

    selected = [edge for edge in edges if edge.channel == channel]
    active: Edge | None = None
    pulses: list[Pulse] = []
    errors: list[dict[str, Any]] = []
    for edge in selected:
        if edge.value == 1:
            if active is not None:
                errors.append(
                    {
                        "channel": channel,
                        "error": "MISSING_FALL",
                        "timestamp_us": active.timestamp_us,
                        "frame_id": active.frame_id,
                    }
                )
                errors.append(
                    {
                        "channel": channel,
                        "error": "OVERLAPPING_RISE",
                        "timestamp_us": edge.timestamp_us,
                        "frame_id": edge.frame_id,
                    }
                )
            active = edge
        elif edge.value == 0:
            if active is None:
                errors.append(
                    {
                        "channel": channel,
                        "error": "FALL_WITHOUT_RISE",
                        "timestamp_us": edge.timestamp_us,
                        "frame_id": edge.frame_id,
                    }
                )
                continue
            if edge.timestamp_us < active.timestamp_us:
                errors.append(
                    {
                        "channel": channel,
                        "error": "NEGATIVE_DURATION",
                        "timestamp_us": edge.timestamp_us,
                        "frame_id": edge.frame_id,
                    }
                )
            else:
                pulses.append(
                    Pulse(
                        channel=channel,
                        frame_id=active.frame_id if active.frame_id is not None else edge.frame_id,
                        start_us=active.timestamp_us,
                        end_us=edge.timestamp_us,
                        duration_us=edge.timestamp_us - active.timestamp_us,
                    )
                )
            active = None
        else:
            errors.append(
                {
                    "channel": channel,
                    "error": "NON_BINARY_VALUE",
                    "timestamp_us": edge.timestamp_us,
                    "frame_id": edge.frame_id,
                }
            )
    if active is not None:
        errors.append(
            {
                "channel": channel,
                "error": "MISSING_FALL",
                "timestamp_us": active.timestamp_us,
                "frame_id": active.frame_id,
            }
        )
    return pulses, errors


def _first_rises_by_frame(edges: list[Edge], channel: str) -> dict[int, float]:
    result: dict[int, float] = {}
    for edge in edges:
        if edge.channel == channel and edge.value == 1 and edge.frame_id is not None:
            result.setdefault(edge.frame_id, edge.timestamp_us)
    return result


def _irq_latencies(
    edges: list[Edge],
) -> tuple[list[float], int, list[dict[str, Any]], list[tuple[float, int, float]]]:
    irq = _first_rises_by_frame(edges, "IRQ_PIN")
    isr = _first_rises_by_frame(edges, "ISR_ACTIVE")
    values: list[float] = []
    errors: list[dict[str, Any]] = []
    samples: list[tuple[float, int, float]] = []
    missing = 0
    for frame_id in sorted(set(irq) | set(isr)):
        if frame_id not in irq or frame_id not in isr:
            missing += 1
            errors.append({"channel": "IRQ_PIN->ISR_ACTIVE", "error": "MISSING_ENDPOINT", "frame_id": frame_id})
            continue
        duration = isr[frame_id] - irq[frame_id]
        if duration < 0:
            errors.append({"channel": "IRQ_PIN->ISR_ACTIVE", "error": "NEGATIVE_LATENCY", "frame_id": frame_id})
        else:
            values.append(duration)
            samples.append((duration, frame_id, irq[frame_id]))
    return values, missing, errors, samples


def _statistical_outliers(
    metric: str,
    channel: str,
    samples: list[tuple[float, int | None, float]],
) -> list[dict[str, Any]]:
    """Return a conservative Tukey-style outlier list for diagnostic reporting."""

    if len(samples) < 4:
        return []
    values = [sample[0] for sample in samples]
    q1 = percentile(values, 25)
    q3 = percentile(values, 75)
    spread = q3 - q1
    median = statistics.median(values)
    if spread <= 1e-12:
        tolerance = max(abs(median) * 0.05, 1e-6)
        low, high = median - tolerance, median + tolerance
    else:
        low, high = q1 - 3.0 * spread, q3 + 3.0 * spread
    return [
        {
            "channel": channel,
            "metric": metric,
            "error": "STATISTICAL_OUTLIER",
            "timestamp_us": timestamp,
            "frame_id": frame_id,
            "value_us": value,
            "outlier_low_us": low,
            "outlier_high_us": high,
        }
        for value, frame_id, timestamp in samples
        if value < low or value > high
    ]


def derive_timing(
    edges: list[Edge],
    *,
    source_type: str = "SYNTHETIC",
    hardware_verified: bool = False,
) -> tuple[list[Pulse], list[dict[str, Any]], list[dict[str, object]]]:
    """Create pulse pairs, error rows and all defined timing summaries."""

    all_pulses: list[Pulse] = []
    errors: list[dict[str, Any]] = []
    summaries: list[dict[str, object]] = []
    channels = sorted({edge.channel for edge in edges})
    for channel in channels:
        if channel not in PULSE_METRICS:
            continue
        pulses, channel_errors = pair_pulses(edges, channel)
        all_pulses.extend(pulses)
        errors.extend(channel_errors)
        errors.extend(
            _statistical_outliers(
                PULSE_METRICS[channel],
                channel,
                [(pulse.duration_us, pulse.frame_id, pulse.start_us) for pulse in pulses],
            )
        )
        missing = sum(error["error"] == "MISSING_FALL" for error in channel_errors)
        invalid = len(channel_errors) - missing
        summaries.append(
            summarize_timing(
                PULSE_METRICS[channel],
                [pulse.duration_us for pulse in pulses],
                missing_pulse_count=missing,
                invalid_pair_count=invalid,
                source_type=source_type,
                hardware_verified=hardware_verified,
            )
        )

    irq_values, irq_missing, irq_errors, irq_samples = _irq_latencies(edges)
    errors.extend(irq_errors)
    errors.extend(_statistical_outliers("irq_latency", "IRQ_PIN->ISR_ACTIVE", irq_samples))
    summaries.append(
        summarize_timing(
            "irq_latency",
            irq_values,
            missing_pulse_count=irq_missing,
            source_type=source_type,
            hardware_verified=hardware_verified,
        )
    )

    frame_starts = sorted(edge.timestamp_us for edge in edges if edge.channel == "FRAME_START" and edge.value == 1)
    frame_periods = [later - earlier for earlier, later in zip(frame_starts, frame_starts[1:])]
    summaries.append(
        summarize_timing(
            "frame_period",
            frame_periods,
            source_type=source_type,
            hardware_verified=hardware_verified,
        )
    )
    return all_pulses, errors, summaries


def _write_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(
            {
                key: ("true" if value else "false") if isinstance(value, bool) else value
                for key, value in row.items()
            }
            for row in rows
        )


def analyze_logic_capture(
    input_csv: Path | str,
    *,
    edge_pairs_csv: Path | str,
    summary_csv: Path | str,
    errors_csv: Path | str,
    channel_map: dict[str, str] | None = None,
    source_type: str = "SYNTHETIC",
    hardware_verified: bool = False,
    warmup_frames: int = 0,
) -> dict[str, object]:
    """Analyze one canonical logic capture and write derived, never raw, tables."""

    edges = load_edges(input_csv, channel_map)
    frame_ids = sorted({edge.frame_id for edge in edges if edge.frame_id is not None})
    warmup_ids = set(frame_ids[: max(0, int(warmup_frames))])
    if warmup_ids:
        edges = [edge for edge in edges if edge.frame_id not in warmup_ids]
    if source_type == "SYNTHETIC" and hardware_verified:
        raise ValueError("synthetic captures cannot be hardware verified")
    pulses, errors, summaries = derive_timing(
        edges,
        source_type=source_type,
        hardware_verified=hardware_verified,
    )
    pair_rows = [
        {**asdict(pulse), "source_type": source_type, "hardware_verified": hardware_verified}
        for pulse in pulses
    ]
    error_rows = [
        {**error, "source_type": source_type, "hardware_verified": hardware_verified}
        for error in errors
    ]
    _write_rows(
        Path(edge_pairs_csv),
        pair_rows,
        ["channel", "frame_id", "start_us", "end_us", "duration_us", "source_type", "hardware_verified"],
    )
    summary_fields = [
        "metric",
        "count",
        "mean_us",
        "median_us",
        "std_us",
        "p90_us",
        "p95_us",
        "p99_us",
        "max_us",
        "missing_pulse_count",
        "invalid_pair_count",
        "source_type",
        "hardware_verified",
    ]
    _write_rows(Path(summary_csv), summaries, summary_fields)
    _write_rows(
        Path(errors_csv),
        error_rows,
        [
            "channel",
            "metric",
            "error",
            "timestamp_us",
            "frame_id",
            "value_us",
            "outlier_low_us",
            "outlier_high_us",
            "source_type",
            "hardware_verified",
        ],
    )
    return {
        "raw_edge_count": len(edges),
        "paired_pulse_count": len(pulses),
        "error_count": len(errors),
        "outlier_count": sum(error.get("error") == "STATISTICAL_OUTLIER" for error in errors),
        "metric_count": len(summaries),
        "warmup_frames_requested": int(warmup_frames),
        "warmup_frames_excluded": len(warmup_ids),
        "source_type": source_type,
        "hardware_verified": hardware_verified,
    }
