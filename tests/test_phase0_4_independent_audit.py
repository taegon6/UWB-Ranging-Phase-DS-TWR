from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest

from analysis.pareto_selection import pareto_front
from analysis.parameter_sweep import run_parameter_sweep
from analysis.phy_airtime_model import AirtimeModelError, calculate_profile_airtimes
from analysis.scheduler_2a2t import ScheduleConflictError, merge_timelines_at_offsets
from analysis.twr_timeline_model import LinkTimeline, PacketEvent, RxWindow, build_link_timeline
from hardware.device_inventory import load_yaml


ROOT = Path(__file__).resolve().parents[1]


def _baseline() -> dict:
    return load_yaml(ROOT / "configs" / "simulation_2a2t_paper_baseline.yaml")


def _event_timeline(
    *,
    link: str,
    sender: str,
    receiver: str,
    start_us: float,
    end_us: float,
    packet_name: str = "AuditPacket",
    rx_windows: tuple[RxWindow, ...] = (),
) -> LinkTimeline:
    anchor, tag = link.split("-")
    event = PacketEvent(
        link=link,
        packet_name=packet_name,
        sender=sender,
        receiver=receiver,
        start_us=start_us,
        rmarker_us=start_us,
        end_us=end_us,
        airtime_us=end_us - start_us,
    )
    return LinkTimeline(
        link=link,
        anchor=anchor,
        tag=tag,
        sequence=(packet_name,),
        packet_events=(event,),
        rx_windows=rx_windows,
        reply_headrooms_us=(),
        timeout_headrooms_us=(),
        duration_us=end_us - start_us,
    )


def test_airtime_model_rejects_dimensionally_wrong_units() -> None:
    profile = copy.deepcopy(_baseline()["paper_profiles"]["paper_plen128"])
    profile["phy"]["preamble_symbol_time_us"]["unit"] = "ms/symbol"

    with pytest.raises(AirtimeModelError, match="unit"):
        calculate_profile_airtimes(profile)


def test_golden_airtime_is_computed_from_components_not_packet_name_constants() -> None:
    profile = copy.deepcopy(_baseline()["paper_profiles"]["paper_plen128"])
    original = calculate_profile_airtimes(profile)["Poll"]
    profile["phy"]["sfd_symbols"]["value"] += 1
    profile["phy"]["phr_time_us"]["value"] += 2.0
    profile["packets"]["Poll"]["psdu_octets"]["value"] += 1
    changed = calculate_profile_airtimes(profile)["Poll"]

    symbol_time = profile["phy"]["preamble_symbol_time_us"]["value"]
    bit_time = profile["phy"]["coded_bit_time_us"]["value"]
    assert changed.total_us - original.total_us == pytest.approx(
        symbol_time + 2.0 + 8 * bit_time
    )


def test_paper_three_packet_and_code_five_packet_models_are_separate() -> None:
    baseline = _baseline()
    paper = baseline["paper_profiles"]["paper_plen128"]
    code = baseline["code_baseline_profiles"]["code_baseline_plen128"]
    paper_timeline = build_link_timeline(
        paper,
        link="A1-T1",
        sequence=["Poll", "Response", "Final"],
        reply_delays_us={"Poll->Response": 706, "Response->Final": 717},
        processing_time_us=522,
        timeout_margin_us=100,
    )
    code_timeline = build_link_timeline(
        code,
        link="A1-T1",
        sequence=["Poll", "Response", "Final", "PostFinal", "Report"],
        reply_delays_us={
            "Poll->Response": 702,
            "Response->Final": 723,
            "Final->PostFinal": 701,
            "PostFinal->Report": 705,
        },
        processing_time_us=522,
        timeout_margin_us=200,
    )

    assert paper_timeline.sequence == ("Poll", "Response", "Final")
    assert code_timeline.sequence == ("Poll", "Response", "Final", "PostFinal", "Report")
    assert {event.packet_name for event in paper_timeline.packet_events} != {
        event.packet_name for event in code_timeline.packet_events
    }


def test_rmarker_packet_and_rx_window_reference_boundaries() -> None:
    profile = _baseline()["paper_profiles"]["paper_plen128"]
    airtimes = calculate_profile_airtimes(profile)
    timeline = build_link_timeline(
        profile,
        link="A1-T1",
        sequence=["Poll", "Response", "Final"],
        reply_delays_us={"Poll->Response": 706, "Response->Final": 717},
        processing_time_us=522,
        timeout_margin_us=100,
    )

    assert timeline.packet_events[0].rmarker_us == pytest.approx(
        airtimes["Poll"].shr_us + airtimes["Poll"].sts_us
    )
    for previous, event, window in zip(
        timeline.packet_events, timeline.packet_events[1:], timeline.rx_windows
    ):
        packet = airtimes[event.packet_name]
        expected_reply = 706 if event.packet_name == "Response" else 717
        assert event.rmarker_us - previous.rmarker_us == pytest.approx(expected_reply)
        assert event.start_us == pytest.approx(
            event.rmarker_us - packet.shr_us - packet.sts_us
        )
        assert event.end_us - event.start_us == pytest.approx(packet.total_us)
        assert window.start_us == pytest.approx(
            max(previous.rmarker_us + 522, event.start_us - 50)
        )
        assert window.end_us - window.start_us == pytest.approx(
            math.ceil(packet.total_us) + 100
        )


def test_delayed_rx_window_is_a_half_duplex_resource() -> None:
    window = RxWindow(
        link="A1-T1",
        packet_name="ExpectedResponse",
        receiver="T1",
        start_us=1.0,
        end_us=10.0,
        expected_packet_start_us=8.0,
        expected_packet_end_us=9.0,
        timeout_duration_us=9.0,
        timeout_headroom_us=1.0,
    )
    waiting = _event_timeline(
        link="A1-T1", sender="T1", receiver="A1", start_us=0.0, end_us=1.0,
        rx_windows=(window,),
    )
    transmitting = _event_timeline(
        link="A2-T1", sender="T1", receiver="A2", start_us=5.0, end_us=6.0,
    )

    with pytest.raises(ScheduleConflictError, match="NODE_TX_RX_OVERLAP"):
        merge_timelines_at_offsets([(waiting, 0.0), (transmitting, 0.0)])


def test_same_node_double_tx_is_rejected() -> None:
    first = _event_timeline(link="A1-T1", sender="T1", receiver="A1", start_us=0, end_us=10)
    second = _event_timeline(link="A2-T1", sender="T1", receiver="A2", start_us=5, end_us=15)
    with pytest.raises(ScheduleConflictError, match=r"NODE_TX_RX_OVERLAP: T1 has TX .* and TX"):
        merge_timelines_at_offsets([(first, 0), (second, 0)])


def test_same_node_double_rx_is_rejected() -> None:
    first = _event_timeline(link="A1-T1", sender="A1", receiver="T1", start_us=0, end_us=10)
    second = _event_timeline(link="A2-T1", sender="A2", receiver="T1", start_us=5, end_us=15)
    with pytest.raises(ScheduleConflictError, match=r"NODE_TX_RX_OVERLAP: T1 has RX .* and RX"):
        merge_timelines_at_offsets([(first, 0), (second, 0)])


def test_same_anchor_receiver_collision_is_rejected() -> None:
    first = _event_timeline(link="A1-T1", sender="T1", receiver="A1", start_us=0, end_us=10)
    second = _event_timeline(link="A1-T2", sender="T2", receiver="A1", start_us=5, end_us=15)
    with pytest.raises(ScheduleConflictError, match="RECEIVER_COLLISION"):
        merge_timelines_at_offsets([(first, 0), (second, 0)])


def test_exactly_touching_slot_boundaries_do_not_overlap() -> None:
    first = _event_timeline(link="A1-T1", sender="T1", receiver="A1", start_us=0, end_us=10)
    second = _event_timeline(link="A2-T1", sender="T1", receiver="A2", start_us=10, end_us=20)
    result = merge_timelines_at_offsets([(first, 0), (second, 0)])
    assert result.node_overlap_count == 0


def test_sub_microsecond_slot_overlap_is_rejected() -> None:
    first = _event_timeline(link="A1-T1", sender="T1", receiver="A1", start_us=0, end_us=10)
    second = _event_timeline(link="A2-T1", sender="T1", receiver="A2", start_us=9.5, end_us=20)
    with pytest.raises(ScheduleConflictError, match="NODE_TX_RX_OVERLAP"):
        merge_timelines_at_offsets([(first, 0), (second, 0)])


def test_pareto_dominance_matches_hand_checked_dataset() -> None:
    common = {
        "complete_superframe": True,
        "node_overlap_count": 0,
        "receiver_collision_count": 0,
        "source_type": "SYNTHETIC",
        "hardware_verified": False,
        "min_timeout_headroom_us": 10,
    }
    rows = [
        dict(common, candidate_id="dominated", superframe_rate_hz=10, min_reply_headroom_us=5, max_node_duty_cycle=0.5),
        dict(common, candidate_id="balanced", superframe_rate_hz=11, min_reply_headroom_us=5, max_node_duty_cycle=0.4),
        dict(common, candidate_id="headroom", superframe_rate_hz=9, min_reply_headroom_us=20, max_node_duty_cycle=0.3),
        dict(common, candidate_id="invalid", complete_superframe=False, superframe_rate_hz=99, min_reply_headroom_us=99, max_node_duty_cycle=0.01),
    ]

    assert [row["candidate_id"] for row in pareto_front(rows)] == ["balanced", "headroom"]


def test_sweep_cardinality_and_c0003_independent_arithmetic() -> None:
    baseline = _baseline()
    sweep = load_yaml(ROOT / "configs" / "simulation_2a2t_parameter_sweep.yaml")
    rows = run_parameter_sweep(baseline, sweep)
    dimensions = sweep["sweep"]
    expected_count = math.prod(
        len(dimensions[name])
        for name in (
            "profile_names",
            "processing_time_us",
            "reply_guard_us",
            "timeout_margin_us",
            "slot_guard_us",
        )
    )
    assert expected_count == 1 * 2 * 5 * 2 * 2 == 40
    assert len(rows) == expected_count

    candidate = next(row for row in rows if row["candidate_id"] == "C0003")
    assert (
        candidate["processing_time_us"],
        candidate["reply_guard_us"],
        candidate["timeout_margin_us"],
        candidate["slot_guard_us"],
    ) == (522.0, 0.0, 200.0, 100.0)
    report_airtime = calculate_profile_airtimes(
        baseline["code_baseline_profiles"]["code_baseline_plen128"]
    )["Report"].total_us
    link_duration = sum(candidate["reply_delays_us"].values()) + report_airtime
    expected_superframe = 4 * link_duration + 3 * candidate["slot_guard_us"]
    assert expected_superframe == pytest.approx(12353.85641025641)
    assert candidate["superframe_duration_us"] == pytest.approx(expected_superframe)
    assert candidate["superframe_rate_hz"] == pytest.approx(1_000_000 / expected_superframe)
