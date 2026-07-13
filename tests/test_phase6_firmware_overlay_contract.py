from __future__ import annotations

import subprocess
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CUSTOM = ROOT / "firmware_overlay" / "API" / "Src" / "custom_code"


def test_phase6_adds_derived_sources_without_modifying_baseline() -> None:
    for name in (
        "ds_twr_2a2t_tag.c",
        "ds_twr_2a2t_anchor.c",
        "uwb_2a2t_config.h",
        "uwb_2a2t_protocol.h",
        "uwb_2a2t_trace.h",
        "uwb_2a2t_trace.c",
    ):
        assert (CUSTOM / name).is_file(), name
    for baseline in ("ds_twr_initiator_final.c", "ds_twr_responder_final.c"):
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", str((CUSTOM / baseline).relative_to(ROOT))],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, baseline


def test_baseline_manifest_matches_current_untouched_source_hashes() -> None:
    manifest = json.loads((ROOT / "artifacts" / "phase6" / "baseline_firmware_manifest.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["baseline_files"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected


def test_phase6_sources_preserve_five_packet_and_fail_closed_contract() -> None:
    tag = (CUSTOM / "ds_twr_2a2t_tag.c").read_text(encoding="utf-8")
    anchor = (CUSTOM / "ds_twr_2a2t_anchor.c").read_text(encoding="utf-8")
    protocol = (CUSTOM / "uwb_2a2t_protocol.h").read_text(encoding="utf-8")
    for token in ("POLL", "RESPONSE", "FINAL", "POST_FINAL", "REPORT"):
        assert f"UWB_2A2T_{token}_" in protocol
    assert "UWB_2A2T_TRACE_TOKEN_TIMEOUT" in tag
    assert "uwb_2a2t_header_matches" in tag
    assert "uwb_2a2t_header_matches" in anchor
    assert "dwt_starttx(DWT_START_TX_DELAYED)" in tag
    assert "dwt_starttx(DWT_START_TX_DELAYED)" in anchor
    assert "Sleep(" not in tag
    assert "Sleep(" not in anchor
    assert "frame_len <" in tag
    assert "frame_len <" in anchor
