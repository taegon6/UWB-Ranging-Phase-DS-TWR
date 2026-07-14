from __future__ import annotations

from pathlib import Path

import pytest

from analysis.phy_airtime_model import (
    calculate_profile_airtimes,
    minimum_reply_us,
    timeout_duration_us,
)
from analysis.twr_timeline_model import TimingConstraintError, build_link_timeline
from hardware.device_inventory import load_yaml, validate_config


ROOT = Path(__file__).resolve().parents[1]


def baseline_config() -> dict:
    config = load_yaml(ROOT / "configs" / "simulation_2a2t_paper_baseline.yaml")
    assert validate_config(config) == []
    return config


def test_paper_plen128_packet_airtimes_reproduce_table_2() -> None:
    profile = baseline_config()["paper_profiles"]["paper_plen128"]
    packets = calculate_profile_airtimes(profile)

    assert packets["Poll"].shr_us == pytest.approx(138.4, abs=0.01)
    assert packets["Poll"].psdu_us == pytest.approx(20.5, abs=0.06)
    assert packets["Response"].psdu_us == pytest.approx(23.6, abs=0.06)
    assert packets["Final"].psdu_us == pytest.approx(34.9, abs=0.06)
    assert packets["Poll"].total_us == pytest.approx(180.4, abs=0.06)
    assert packets["Response"].total_us == pytest.approx(183.5, abs=0.06)
    assert packets["Final"].total_us == pytest.approx(194.8, abs=0.06)
    assert all(packet.source_type == "SYNTHETIC" for packet in packets.values())
    assert all(packet.hardware_verified is False for packet in packets.values())


def test_paper_reply_and_timeout_values_reproduce_figure_4() -> None:
    profile = baseline_config()["paper_profiles"]["paper_plen128"]
    packets = calculate_profile_airtimes(profile)
    processing = profile["timing"]["processing_time_us"]["value"]
    timeout_margin = profile["timing"]["timeout_margin_us"]["value"]

    assert round(minimum_reply_us(processing, packets["Response"])) == 706
    assert round(minimum_reply_us(processing, packets["Final"])) == 717
    assert round(timeout_duration_us(packets["Response"], timeout_margin)) == 284
    assert round(timeout_duration_us(packets["Final"], timeout_margin)) == 295


def test_paper_plen1024_minimum_reply_reproduces_table_3() -> None:
    profile = baseline_config()["paper_profiles"]["paper_plen1024"]
    packets = calculate_profile_airtimes(profile)
    processing = profile["timing"]["processing_time_us"]["value"]

    assert round(minimum_reply_us(processing, packets["Response"])) == 1618
    assert round(minimum_reply_us(processing, packets["Final"])) == 1629


def test_paper_three_packet_timeline_is_schedulable_at_golden_values() -> None:
    profile = baseline_config()["paper_profiles"]["paper_plen128"]
    timing = profile["timing"]
    timeline = build_link_timeline(
        profile,
        link="A1-T1",
        sequence=["Poll", "Response", "Final"],
        reply_delays_us={
            "Poll->Response": timing["reply1_us"]["value"],
            "Response->Final": timing["reply2_us"]["value"],
        },
        processing_time_us=timing["processing_time_us"]["value"],
        timeout_margin_us=timing["timeout_margin_us"]["value"],
    )

    assert timeline.link == "A1-T1"
    assert len(timeline.packet_events) == 3
    assert timeline.constraint_failures == []


def test_too_short_reply_is_a_hard_failure() -> None:
    profile = baseline_config()["paper_profiles"]["paper_plen128"]
    with pytest.raises(TimingConstraintError, match="reply delay"):
        build_link_timeline(
            profile,
            link="A1-T1",
            sequence=["Poll", "Response", "Final"],
            reply_delays_us={"Poll->Response": 600, "Response->Final": 600},
            processing_time_us=522,
            timeout_margin_us=100,
        )
