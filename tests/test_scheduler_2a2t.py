from __future__ import annotations

from pathlib import Path

import pytest

from analysis.scheduler_2a2t import (
    ScheduleConflictError,
    merge_timelines_at_offsets,
    schedule_sequential_2a2t,
)
from analysis.twr_timeline_model import build_link_timeline
from hardware.device_inventory import load_yaml


ROOT = Path(__file__).resolve().parents[1]


def baseline_profile() -> dict:
    config = load_yaml(ROOT / "configs" / "simulation_2a2t_paper_baseline.yaml")
    return config["code_baseline_profiles"]["code_baseline_plen128"]


def make_timeline(link: str):
    profile = baseline_profile()
    return build_link_timeline(
        profile,
        link=link,
        sequence=["Poll", "Response", "Final", "PostFinal", "Report"],
        reply_delays_us={
            "Poll->Response": 1650,
            "Response->Final": 1650,
            "Final->PostFinal": 1650,
            "PostFinal->Report": 2522,
        },
        processing_time_us=522,
        timeout_margin_us=200,
    )


def test_direct_2a2t_sequential_schedule_completes_all_four_links() -> None:
    links = ["A1-T1", "A2-T1", "A1-T2", "A2-T2"]
    schedule = schedule_sequential_2a2t(
        [make_timeline(link) for link in links], slot_guard_us=100
    )

    assert schedule.links_completed == links
    assert schedule.node_overlap_count == 0
    assert schedule.receiver_collision_count == 0
    assert schedule.complete_superframe is True
    assert schedule.source_type == "SYNTHETIC"
    assert schedule.hardware_verified is False


def test_same_tag_overlapping_two_links_is_a_hard_failure() -> None:
    with pytest.raises(ScheduleConflictError, match="NODE_TX_RX_OVERLAP"):
        merge_timelines_at_offsets(
            [(make_timeline("A1-T1"), 0.0), (make_timeline("A2-T1"), 0.0)]
        )


def test_two_tags_transmitting_to_same_anchor_is_receiver_collision() -> None:
    with pytest.raises(ScheduleConflictError, match="RECEIVER_COLLISION"):
        merge_timelines_at_offsets(
            [(make_timeline("A1-T1"), 0.0), (make_timeline("A1-T2"), 0.0)]
        )
