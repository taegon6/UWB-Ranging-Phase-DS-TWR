from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from analysis.parameter_sweep import run_parameter_sweep
from analysis.pareto_selection import pareto_front
from hardware.device_inventory import load_yaml, validate_config


ROOT = Path(__file__).resolve().parents[1]


def test_simulation_configs_validate_and_phase_5_6_are_gated() -> None:
    baseline = load_yaml(ROOT / "configs" / "simulation_2a2t_paper_baseline.yaml")
    sweep = load_yaml(ROOT / "configs" / "simulation_2a2t_parameter_sweep.yaml")
    assert validate_config(baseline) == []
    assert validate_config(sweep) == []
    assert sweep["phase_gate"] == {
        "implemented_through": 4,
        "phase_5_enabled": False,
        "phase_6_enabled": False,
    }


def test_sweep_preserves_profiles_and_emits_only_valid_2a2t_candidates() -> None:
    baseline = load_yaml(ROOT / "configs" / "simulation_2a2t_paper_baseline.yaml")
    sweep = load_yaml(ROOT / "configs" / "simulation_2a2t_parameter_sweep.yaml")
    original = copy.deepcopy(baseline)
    rows = run_parameter_sweep(baseline, sweep)

    assert baseline == original
    assert rows
    assert all(row["complete_superframe"] is True for row in rows)
    assert all(row["links_completed"] == 4 for row in rows)
    assert all(row["node_overlap_count"] == 0 for row in rows)
    assert all(row["receiver_collision_count"] == 0 for row in rows)
    assert all(row["source_type"] == "SYNTHETIC" for row in rows)
    assert all(row["hardware_verified"] is False for row in rows)
    assert all(
        all(value["hardware_verified"] is False for value in row["provenance"].values())
        for row in rows
    )
    assert all(
        all(
            value["evidence_class"] == "PAPER_DERIVED"
            and value["hardware_verified"] is False
            for value in row["reply_delay_provenance"].values()
        )
        for row in rows
    )
    assert all(
        row["rx_acquisition_lead_provenance"]["evidence_class"] == "ASSUMED"
        for row in rows
    )
    assert pareto_front(rows)


def test_firmware_overlay_hashes_remain_equal_to_phase_0_manifest() -> None:
    manifest = load_yaml(ROOT / "artifacts" / "simulation_2a2t_source_manifest.json")
    expected = manifest["firmware_baseline"]["files"]
    for relative, digest in expected.items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert actual == digest
