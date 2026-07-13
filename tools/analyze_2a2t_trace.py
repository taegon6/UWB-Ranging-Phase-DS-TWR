#!/usr/bin/env python3
"""Assemble four-node Phase 6 UART trace records without fabricating HIL results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import ROOT  # noqa: F401 - imports the repository path bootstrap.
from analysis.phase6_trace_records import assemble_superframes, decode_trace_stream


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True, help="One or more raw 64-byte UART trace streams")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-type", choices=["SYNTHETIC", "UNVERIFIED_HW", "MEASURED"], default="UNVERIFIED_HW")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = []
    errors = []
    for path in args.input:
        decoded, stream_errors = decode_trace_stream(path.read_bytes())
        records.extend({**record, "input_file": str(path)} for record in decoded)
        errors.extend({**error, "input_file": str(path)} for error in stream_errors)
    summary = assemble_superframes(records)
    summary["source_type"] = args.source_type
    summary["hardware_verified"] = False
    summary["decoded_record_count"] = len(records)
    summary["parse_errors"] = errors
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing analysis output: {args.output}")
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"complete_superframes={summary['complete_superframe_count']}")
    print("hardware_verified = false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
