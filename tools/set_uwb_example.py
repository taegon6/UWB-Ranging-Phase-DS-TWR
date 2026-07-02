#!/usr/bin/env python3
"""Select one UWB firmware example in API/Src/example_selection.h."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


EXAMPLES = {
    "ss-initiator": "TEST_SS_TWR_INITIATOR",
    "ss-responder": "TEST_SS_TWR_RESPONDER",
    "ds-initiator": "DS_TWR_INITIATOR_FINAL",
    "ds-responder": "DS_TWR_RESPONDER_FINAL",
    "ds-anchor-a": "DS_TWR_RESPONDER_FINAL",
    "ds-anchor-b": "DS_TWR_RESPONDER_FINAL",
}

EXTRA_DEFINES = {
    "ds-anchor-a": ["UWB_ANCHOR_A"],
    "ds-anchor-b": ["UWB_ANCHOR_B"],
}

KNOWN_DEFINES = [
    "TEST_SS_TWR_INITIATOR",
    "TEST_SS_TWR_RESPONDER",
    "TEST_SS_TWR_INITIATOR_STS",
    "TEST_SS_TWR_RESPONDER_STS",
    "TEST_DS_TWR_INITIATOR",
    "TEST_DS_TWR_RESPONDER",
    "TEST_DS_TWR_INITIATOR_STS",
    "TEST_DS_TWR_RESPONDER_STS",
    "DS_TWR_INITIATOR_FINAL",
    "DS_TWR_RESPONDER_FINAL",
    "DS_TWR_INITIATOR_ORIGIN",
    "DS_TWR_RESPONDER_ORIGIN",
    "DS_TWR_INITIATOR_PACKET_SIMULATION",
    "DS_TWR_RESPONDER_PACKET_SIMULATION",
    "DW3000_CIR_SERIAL_RX",
    "UWB_ANCHOR_A",
    "UWB_ANCHOR_B",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("example", choices=sorted(EXAMPLES), help="Firmware example to enable")
    parser.add_argument("--path", default="API/Src/example_selection.h", help="Path to example_selection.h")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.path)
    selected = EXAMPLES[args.example]
    text = path.read_text(encoding="utf-8")

    for define in KNOWN_DEFINES:
        text = re.sub(rf"^[ \t]*(?://[ \t]*)?#define[ \t]+{re.escape(define)}\b.*$", f"//#define {define}", text, flags=re.MULTILINE)

    text = re.sub(rf"^//[ \t]*#define[ \t]+{re.escape(selected)}\b.*$", f"#define {selected}", text, flags=re.MULTILINE)
    for define in EXTRA_DEFINES.get(args.example, []):
        if re.search(rf"^[ \t]*(?://[ \t]*)?#define[ \t]+{re.escape(define)}\b", text, flags=re.MULTILINE):
            text = re.sub(rf"^//[ \t]*#define[ \t]+{re.escape(define)}\b.*$", f"#define {define}", text, flags=re.MULTILINE)
        else:
            text = text.replace("#define " + selected, "#define " + selected + "\n#define " + define, 1)
    path.write_text(text, encoding="utf-8")
    print(f"Enabled {selected} for {args.example} in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
