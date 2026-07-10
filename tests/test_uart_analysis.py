from __future__ import annotations

from pathlib import Path

from analysis.uart_analysis import decode_stream, decode_uart_file, encode_record

FIXTURES = Path(__file__).parent / "fixtures"


def test_binary_record_round_trip() -> None:
    encoded = encode_record({"frame_id": 4, "range_raw_m": 1.2})
    records, errors = decode_stream(encoded)
    assert not errors
    assert records[0]["frame_id"] == 4
    assert records[0]["source_type"] == "SYNTHETIC"
    assert records[0]["hardware_verified"] is False


def test_corrupt_uart_record_recovery() -> None:
    data = (FIXTURES / "synthetic_uart_log.bin").read_bytes()
    records, errors = decode_stream(data)
    assert len(records) >= 40
    assert any(error["error"] == "CRC_MISMATCH" for error in errors)
    assert any(record["superframe_id"] > 5 for record in records)


def test_uart_decoder_writes_records_and_errors(tmp_path: Path) -> None:
    result = decode_uart_file(
        FIXTURES / "synthetic_uart_log.bin",
        tmp_path / "records.csv",
        tmp_path / "errors.csv",
    )
    assert result["decoded_record_count"] > 0
    assert result["parse_error_count"] > 0
    assert "hardware_verified" in (tmp_path / "records.csv").read_text(encoding="utf-8")
