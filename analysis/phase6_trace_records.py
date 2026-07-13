"""Decoder and four-slot assembler for the firmware's fixed 64-byte trace record."""

from __future__ import annotations

import binascii
import struct
from collections import defaultdict
from typing import Any, Iterable


MAGIC = 0x3255
VERSION = 1
RECORD = struct.Struct("<HBBBBBBIIBBHiiQ5IIHH")
RECORD_SIZE = RECORD.size

EVENT_BOOT = 0
EVENT_SUPERFRAME_START = 1
EVENT_SLOT_START = 2
EVENT_PACKET_TX_SCHEDULED = 3
EVENT_PACKET_TX_DONE = 4
EVENT_PACKET_RX_RMARKER = 5
EVENT_PROCESS_START = 6
EVENT_PROCESS_END = 7
EVENT_TOKEN_RX = 8
EVENT_TOKEN_TIMEOUT = 9
EVENT_LATE_TX = 10
EVENT_RX_TIMEOUT = 11
EVENT_REPORT_READY = 12
EVENT_SUPERFRAME_DONE = 13
EVENT_UART_DROP = 14


def _crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def encode_trace_record(record: dict[str, Any]) -> bytes:
    """Fixture encoder mirroring the packed C layout; it is not a hardware sample."""

    deltas = list(record.get("event_delta_dtu", [0, 0, 0, 0, 0]))
    if len(deltas) != 5:
        raise ValueError("event_delta_dtu must contain exactly five values")
    packed = RECORD.pack(
        MAGIC,
        int(record.get("version", VERSION)),
        int(record["node_id"]),
        int(record["slot_id"]),
        int(record["event_type"]),
        int(record.get("result_code", 0)),
        int(record.get("flags", 0)),
        int(record.get("boot_id", 0)),
        int(record.get("superframe_id", 0)),
        int(record.get("sequence", 0)) & 0xFF,
        int(record.get("retry_count", 0)),
        int(record.get("reserved", 0)),
        int(record.get("raw_distance_mm", 0)),
        int(record.get("corrected_distance_mm", 0)),
        int(record.get("slot_start_dtu", 0)),
        *(int(value) for value in deltas),
        int(record.get("status_reg", 0)),
        int(record.get("uart_drop_count", 0)),
        0,
    )
    return packed[:-2] + struct.pack("<H", _crc16_ccitt(packed[:-2]))


def _record_from_bytes(chunk: bytes) -> dict[str, Any]:
    values = RECORD.unpack(chunk)
    (
        magic,
        version,
        node_id,
        slot_id,
        event_type,
        result_code,
        flags,
        boot_id,
        superframe_id,
        sequence,
        retry_count,
        reserved,
        raw_distance_mm,
        corrected_distance_mm,
        slot_start_dtu,
        *tail,
    ) = values
    event_delta_dtu = tail[:5]
    status_reg, uart_drop_count, crc16 = tail[5:]
    return {
        "magic": magic,
        "version": version,
        "node_id": node_id,
        "slot_id": slot_id,
        "event_type": event_type,
        "result_code": result_code,
        "flags": flags,
        "boot_id": boot_id,
        "superframe_id": superframe_id,
        "sequence": sequence,
        "retry_count": retry_count,
        "reserved": reserved,
        "raw_distance_mm": raw_distance_mm,
        "corrected_distance_mm": corrected_distance_mm,
        "slot_start_dtu": slot_start_dtu,
        "event_delta_dtu": event_delta_dtu,
        "status_reg": status_reg,
        "uart_drop_count": uart_drop_count,
        "crc16": crc16,
    }


def decode_trace_stream(data: bytes) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Decode a stream and recover after noise or a bad fixed-record CRC."""

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    magic = struct.pack("<H", MAGIC)
    offset = 0
    while offset < len(data):
        found = data.find(magic, offset)
        if found < 0:
            if offset < len(data):
                errors.append({"offset": offset, "error": "TRAILING_UNFRAMED_BYTES", "byte_count": len(data) - offset})
            break
        if found > offset:
            errors.append({"offset": offset, "error": "UNFRAMED_BYTES", "byte_count": found - offset})
        if found + RECORD_SIZE > len(data):
            errors.append({"offset": found, "error": "TRUNCATED_RECORD", "byte_count": len(data) - found})
            break
        chunk = data[found : found + RECORD_SIZE]
        record = _record_from_bytes(chunk)
        if record["version"] != VERSION:
            errors.append({"offset": found, "error": "UNSUPPORTED_VERSION", "version": record["version"]})
            offset = found + 1
            continue
        if _crc16_ccitt(chunk[:-2]) != record["crc16"]:
            errors.append({"offset": found, "error": "CRC16_MISMATCH"})
            offset = found + 1
            continue
        records.append(record)
        offset = found + RECORD_SIZE
    return records, errors


def assemble_superframes(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Group tag slot records without converting them into claimed measurements."""

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    token_timeout_count = 0
    late_tx_count = 0
    uart_drop_count = 0
    for record in records:
        superframe = int(record["superframe_id"])
        grouped[superframe].append(record)
        token_timeout_count += int(record["event_type"] == EVENT_TOKEN_TIMEOUT)
        late_tx_count += int(record["event_type"] == EVENT_LATE_TX)
        uart_drop_count = max(uart_drop_count, int(record.get("uart_drop_count", 0)))
    superframes: list[dict[str, Any]] = []
    for superframe_id, group in sorted(grouped.items()):
        slots = sorted({int(record["slot_id"]) for record in group if int(record["event_type"]) == EVENT_SLOT_START})
        superframes.append(
            {
                "superframe_id": superframe_id,
                "slots": slots,
                "complete": slots == [0, 1, 2, 3],
                "record_count": len(group),
            }
        )
    complete = sum(int(row["complete"]) for row in superframes)
    return {
        "superframes": superframes,
        "complete_superframe_count": complete,
        "incomplete_superframe_count": len(superframes) - complete,
        "token_timeout_count": token_timeout_count,
        "late_tx_count": late_tx_count,
        "uart_drop_count": uart_drop_count,
        "source_type": "UNVERIFIED_HW",
        "hardware_verified": False,
    }


__all__ = [
    "EVENT_SLOT_START",
    "EVENT_TOKEN_TIMEOUT",
    "RECORD_SIZE",
    "assemble_superframes",
    "decode_trace_stream",
    "encode_trace_record",
]
