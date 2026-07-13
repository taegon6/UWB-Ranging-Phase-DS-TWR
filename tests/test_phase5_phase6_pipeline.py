from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest
import jsonschema
import yaml

from analysis.phase5_simulation import (
    Phase5ConfigError,
    build_phase5_candidate,
    pareto_front_phase5,
    run_phase5_pipeline,
)
from hardware.device_inventory import load_yaml


ROOT = Path(__file__).resolve().parents[1]
PHY = ROOT / "configs" / "dw3000_current_phy.yaml"
SWEEP = ROOT / "configs" / "phase5_2a2t_sweep.yaml"


def _tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(item.relative_to(path).as_posix().encode())
        digest.update(item.read_bytes())
    return digest.hexdigest()


def test_phase5_candidate_uses_independent_phy_and_complete_five_packet_timeline() -> None:
    candidate = build_phase5_candidate(load_yaml(PHY), load_yaml(SWEEP)["smoke_candidate"])
    assert candidate["model_role"] == "CURRENT_FIRMWARE_INDEPENDENT_PHY"
    assert candidate["sequence"] == ["Poll", "Response", "Final", "PostFinal", "Report"]
    assert candidate["links_completed"] == 4
    assert candidate["complete_superframe"] is True
    assert candidate["packet_airtime_us"] == {
        "Poll": "178.39836",
        "Response": "179.42404",
        "Final": "200.96332",
        "PostFinal": "178.39836",
        "Report": "182.50108",
    }
    assert candidate["source_type"] == "SYNTHETIC"
    assert candidate["hardware_verified"] is False


def test_unresolved_report_transition_is_not_silently_defaulted() -> None:
    spec = dict(load_yaml(SWEEP)["smoke_candidate"])
    spec["report_processing_us"] = None
    with pytest.raises(Phase5ConfigError, match="report_processing_us.*UNRESOLVED"):
        build_phase5_candidate(load_yaml(PHY), spec)


def test_scenario_provenance_and_decimal_output_are_preserved() -> None:
    first = build_phase5_candidate(load_yaml(PHY), load_yaml(SWEEP)["smoke_candidate"])
    second = build_phase5_candidate(load_yaml(PHY), load_yaml(SWEEP)["smoke_candidate"])
    assert first == second
    assert first["parameter_provenance"]["report_processing_us"]["evidence_class"] == "PAPER"
    assert first["parameter_provenance"]["report_processing_us"]["hardware_verified"] is False
    assert Decimal(first["superframe_period_ps"]) > 0


def test_hard_constraint_violation_is_rejected() -> None:
    spec = dict(load_yaml(SWEEP)["smoke_candidate"])
    spec["inter_slot_guard_us"] = "-1"
    with pytest.raises(Phase5ConfigError, match="inter_slot_guard_us"):
        build_phase5_candidate(load_yaml(PHY), spec)


def test_phase5_pareto_matches_hand_checked_fixture() -> None:
    rows = [
        {"candidate_id": "A", "superframe_period_ps": "10", "processing_headroom_ps": "5", "uart_headroom_bps": "5", "robustness_ps": "5", "max_node_duty_cycle": "0.5", "unresolved_assumption_count": 1},
        {"candidate_id": "B", "superframe_period_ps": "11", "processing_headroom_ps": "4", "uart_headroom_bps": "4", "robustness_ps": "4", "max_node_duty_cycle": "0.6", "unresolved_assumption_count": 2},
        {"candidate_id": "C", "superframe_period_ps": "12", "processing_headroom_ps": "9", "uart_headroom_bps": "9", "robustness_ps": "9", "max_node_duty_cycle": "0.4", "unresolved_assumption_count": 0},
    ]
    assert [row["candidate_id"] for row in pareto_front_phase5(rows)] == ["A", "C"]


def test_pipeline_exports_three_to_five_manifests_reports_and_all_graphs(tmp_path: Path) -> None:
    firmware_before = _tree_hash(ROOT / "firmware_overlay")
    run_dir = run_phase5_pipeline(PHY, SWEEP, tmp_path)
    firmware_after = _tree_hash(ROOT / "firmware_overlay")
    assert firmware_before == firmware_after
    manifests = sorted((run_dir / "artifacts" / "hil_candidates").glob("*.yaml"))
    assert 3 <= len(manifests) <= 5
    schema = json.loads((ROOT / "schemas" / "hil_candidate.schema.json").read_text(encoding="utf-8"))
    for manifest in manifests:
        jsonschema.validate(yaml.safe_load(manifest.read_text(encoding="utf-8")), schema)
    assert (run_dir / "docs" / "2A2T_PHASE5_SIMULATION_RESULTS_KO.md").is_file()
    assert (run_dir / "docs" / "2A2T_PHASE6_HARDWARE_EXPERIMENT_PLAN_KO.md").is_file()
    graph_names = {
        "paper_vs_current_packet_airtime",
        "superframe_rate_vs_report_transition_delay",
        "superframe_rate_vs_inter_slot_guard",
        "latency_vs_processing_headroom_pareto",
        "candidate_node_duty_cycle",
        "candidate_uart_headroom",
        "legacy_vs_corrected_result",
        "sequential_superframe_timeline",
        "scenario_sensitivity",
    }
    for name in graph_names:
        assert (run_dir / "results" / "graphs" / f"{name}.svg").is_file()
        assert (run_dir / "results" / "graphs" / f"{name}.png").is_file()
    summary = json.loads((run_dir / "results" / "summary.json").read_text(encoding="utf-8"))
    assert summary["source_type"] == "SYNTHETIC"
    assert summary["hardware_verified"] is False
    assert summary["legacy_cache_used"] is False
