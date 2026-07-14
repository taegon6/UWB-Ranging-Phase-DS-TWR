"""Versioned binary UART framing and corrupt-record resynchronization."""

from __future__ import annotations

import binascii
import csv
import json
import re
import struct
from pathlib import Path
from typing import Any

MAGIC = b"U2AT"
VERSION = 1
HEADER = struct.Struct("<4sBH")
CRC = struct.Struct("<I")
ANCHOR_LINE = re.compile(rb"ANCHOR:(A1|A2|B2)\s+DIST:\s*([-+]?\d+(?:\.\d+)?)\s*m")


def encode_record(record: dict[str, Any]) -> bytes:
    payload_record = dict(record)
    payload_record["source_type"] = "SYNTHETIC"
    payload_record["hardware_verified"] = False
    payload = json.dumps(payload_record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    header = HEADER.pack(MAGIC, VERSION, len(payload))
    checksum = binascii.crc32(header + payload) & 0xFFFFFFFF
    return header + payload + CRC.pack(checksum)


def decode_stream(
    data: bytes,
    *,
    source_type: str = "SYNTHETIC",
    hardware_verified: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Decode records and scan forward to MAGIC after malformed bytes."""

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    offset = 0
    while offset < len(data):
        magic_at = data.find(MAGIC, offset)
        if magic_at < 0:
            if offset < len(data):
                errors.append({"offset": offset, "error": "TRAILING_UNFRAMED_BYTES", "byte_count": len(data) - offset})
            break
        if magic_at > offset:
            errors.append({"offset": offset, "error": "UNFRAMED_BYTES", "byte_count": magic_at - offset})
        offset = magic_at
        if offset + HEADER.size > len(data):
            errors.append({"offset": offset, "error": "TRUNCATED_HEADER", "byte_count": len(data) - offset})
            break
        magic, version, payload_len = HEADER.unpack_from(data, offset)
        end = offset + HEADER.size + payload_len + CRC.size
        if magic != MAGIC or version != VERSION:
            errors.append({"offset": offset, "error": "BAD_HEADER", "version": version})
            offset += 1
            continue
        if end > len(data):
            errors.append({"offset": offset, "error": "TRUNCATED_RECORD", "expected_end": end})
            break
        payload = data[offset + HEADER.size : offset + HEADER.size + payload_len]
        expected_crc = CRC.unpack_from(data, end - CRC.size)[0]
        actual_crc = binascii.crc32(data[offset : end - CRC.size]) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            errors.append({"offset": offset, "error": "CRC_MISMATCH"})
            offset += 1
            continue
        try:
            record = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append({"offset": offset, "error": "PAYLOAD_DECODE", "detail": str(exc)})
            offset = end
            continue
        if source_type == "SYNTHETIC" and hardware_verified:
            raise ValueError("synthetic UART records cannot be hardware verified")
        record["source_type"] = source_type
        record["hardware_verified"] = hardware_verified
        records.append(record)
        offset = end
    return records, errors


def decode_uart_file(
    input_path: Path | str,
    records_csv: Path | str,
    errors_csv: Path | str,
    *,
    source_type: str = "SYNTHETIC",
    hardware_verified: bool = False,
) -> dict[str, object]:
    if source_type == "SYNTHETIC" and hardware_verified:
        raise ValueError("synthetic UART records cannot be hardware verified")
    data = Path(input_path).read_bytes()
    if MAGIC in data:
        records, errors = decode_stream(
            data,
            source_type=source_type,
            hardware_verified=hardware_verified,
        )
    else:
        records = []
        errors = []
        for index, line in enumerate(data.splitlines(), start=1):
            try:
                decoded_line = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                decoded_line = None
            if isinstance(decoded_line, dict):
                decoded_line["line_number"] = index
                decoded_line["source_type"] = source_type
                decoded_line["hardware_verified"] = hardware_verified
                records.append(decoded_line)
                continue
            match = ANCHOR_LINE.search(line)
            if match:
                records.append(
                    {
                        "line_number": index,
                        "anchor_id": match.group(1).decode("ascii"),
                        "range_raw_m": float(match.group(2)),
                        "source_type": source_type,
                        "hardware_verified": hardware_verified,
                    }
                )
            elif line.strip():
                errors.append({"offset": index, "error": "UNPARSED_LINE", "detail": line.decode("utf-8", "replace")})

    record_fields = sorted({key for record in records for key in record}) or ["source_type", "hardware_verified"]
    with Path(records_csv).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=record_fields)
        writer.writeheader()
        writer.writerows(
            {
                key: ("true" if value else "false") if isinstance(value, bool) else value
                for key, value in record.items()
            }
            for record in records
        )
    with Path(errors_csv).open("w", encoding="utf-8", newline="") as handle:
        fields = ["offset", "error", "byte_count", "expected_end", "version", "detail", "source_type", "hardware_verified"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for error in errors:
            writer.writerow(
                {
                    **error,
                    "source_type": source_type,
                    "hardware_verified": "true" if hardware_verified else "false",
                }
            )
    return {
        "decoded_record_count": len(records),
        "parse_error_count": len(errors),
        "source_type": source_type,
        "hardware_verified": hardware_verified,
    }
