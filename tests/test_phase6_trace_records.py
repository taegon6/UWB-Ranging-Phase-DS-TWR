from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from analysis.phase6_trace_records import (
    EVENT_SLOT_START,
    EVENT_TOKEN_TIMEOUT,
    assemble_superframes,
    decode_trace_stream,
    encode_trace_record,
)


def _record(*, node: int, slot: int, superframe: int, event: int = EVENT_SLOT_START) -> dict:
    return {
        "node_id": node,
        "slot_id": slot,
        "event_type": event,
        "result_code": 0,
        "boot_id": 7,
        "superframe_id": superframe,
        "sequence": superframe * 4 + slot,
        "slot_start_dtu": 1000 + slot * 100,
    }


def test_fixed_64_byte_trace_record_round_trip_and_crc_resynchronization() -> None:
    good = encode_trace_record(_record(node=3, slot=0, superframe=2))
    assert len(good) == 64
    records, errors = decode_trace_stream(b"noise" + good)
    assert len(records) == 1
    assert records[0]["slot_id"] == 0
    assert errors[0]["error"] == "UNFRAMED_BYTES"


def test_assembler_requires_all_four_slots_and_keeps_timeout_visible() -> None:
    data = b"".join(
        [
            encode_trace_record(_record(node=3, slot=0, superframe=5)),
            encode_trace_record(_record(node=3, slot=1, superframe=5)),
            encode_trace_record(_record(node=4, slot=2, superframe=5)),
            encode_trace_record(_record(node=4, slot=3, superframe=5)),
            encode_trace_record(_record(node=4, slot=2, superframe=6, event=EVENT_TOKEN_TIMEOUT)),
        ]
    )
    records, errors = decode_trace_stream(data)
    assert not errors
    result = assemble_superframes(records)
    assert result["complete_superframe_count"] == 1
    assert result["incomplete_superframe_count"] == 1
    assert result["token_timeout_count"] == 1
    assert result["superframes"][0]["slots"] == [0, 1, 2, 3]


def test_trace_cli_writes_unverified_summary_without_overwriting(tmp_path: Path) -> None:
    source = tmp_path / "T1.bin"
    source.write_bytes(encode_trace_record(_record(node=3, slot=0, superframe=1)))
    output = tmp_path / "summary.json"
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(root / "tools" / "analyze_2a2t_trace.py"), "--input", str(source), "--output", str(output)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["source_type"] == "UNVERIFIED_HW"
    assert summary["hardware_verified"] is False
