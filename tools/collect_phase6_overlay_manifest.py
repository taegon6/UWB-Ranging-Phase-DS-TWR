#!/usr/bin/env python3
"""Aggregate per-role Phase 6 overlay provenance without modifying an SDK."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .prepare_phase6_sdk_sandbox import ROLE_SPECS, canonical_sha256
except ImportError:  # pragma: no cover
    from prepare_phase6_sdk_sandbox import ROLE_SPECS, canonical_sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"[FAIL] refusing to overwrite: {args.output}")
    rows = []
    for role in ROLE_SPECS:
        path = args.input_dir / f"{role}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.append(payload)
    result = {"schema_version": 1, "source_type": "CODE_INSPECTION_AND_BUILD", "hardware_verified": False, "flash_executed": False, "roles": rows}
    result["manifest_sha256"] = canonical_sha256(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
