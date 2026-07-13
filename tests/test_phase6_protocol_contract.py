from __future__ import annotations

import pytest

from analysis.phase6_protocol import (
    FINAL_EXTENSION_LENGTH,
    FRAME_LAYOUTS,
    PacketHeader,
    Phase6ProtocolError,
    TagScheduler,
    decode_final_extension,
    encode_final_extension,
    link_for_sequence,
    validate_link_packet,
)


def test_four_slot_sequence_and_wire_sequence_wrap_are_stable() -> None:
    assert [link_for_sequence(sequence).link_id for sequence in range(4)] == [
        "A1-T1",
        "A2-T1",
        "A1-T2",
        "A2-T2",
    ]
    assert link_for_sequence(255).link_id == "A2-T2"
    assert link_for_sequence(255).superframe_mod64 == 63
    assert link_for_sequence(256).link_id == "A1-T1"
    assert link_for_sequence(256).superframe_mod64 == 0


def test_all_five_packets_keep_a_single_exchange_sequence() -> None:
    link = link_for_sequence(2)
    for function_code in ("POLL", "RESPONSE", "FINAL", "POST_FINAL", "REPORT"):
        header = PacketHeader(
            destination=link.anchor if function_code in {"POLL", "FINAL", "POST_FINAL"} else link.tag,
            source=link.tag if function_code in {"POLL", "FINAL", "POST_FINAL"} else link.anchor,
            function_code=function_code,
            sequence=2,
        )
        assert validate_link_packet(header, link, function_code) is None


def test_wrong_address_function_or_sequence_is_rejected() -> None:
    link = link_for_sequence(1)
    with pytest.raises(Phase6ProtocolError, match="sequence"):
        validate_link_packet(PacketHeader("T1", "A2", "REPORT", 0), link, "REPORT")
    with pytest.raises(Phase6ProtocolError, match="destination"):
        validate_link_packet(PacketHeader("T2", "A2", "REPORT", 1), link, "REPORT")
    with pytest.raises(Phase6ProtocolError, match="function"):
        validate_link_packet(PacketHeader("T1", "A2", "POLL", 1), link, "REPORT")


def test_final_extension_preserves_length_and_carries_slot_epoch() -> None:
    payload = encode_final_extension(protocol_version=1, slot_id=3, superframe_id=0x10203040)
    assert len(payload) == FINAL_EXTENSION_LENGTH == 6
    assert decode_final_extension(payload) == {
        "protocol_version": 1,
        "slot_id": 3,
        "superframe_id": 0x10203040,
    }
    with pytest.raises(Phase6ProtocolError, match="slot_id"):
        encode_final_extension(protocol_version=1, slot_id=4, superframe_id=0)


def test_driver_length_and_on_air_fcs_convention_are_explicit() -> None:
    assert FRAME_LAYOUTS["POLL"].driver_data_length == 10
    assert FRAME_LAYOUTS["POLL"].on_air_psdu_length == 12
    assert FRAME_LAYOUTS["RESPONSE"].driver_data_length == 11
    assert FRAME_LAYOUTS["RESPONSE"].on_air_psdu_length == 13
    assert FRAME_LAYOUTS["FINAL"].driver_data_length == 32
    assert FRAME_LAYOUTS["FINAL"].on_air_psdu_length == 34
    assert FRAME_LAYOUTS["POST_FINAL"].on_air_psdu_length == 12
    assert FRAME_LAYOUTS["REPORT"].on_air_psdu_length == 16


def test_t2_remains_silent_until_the_expected_a2_to_t1_report_token() -> None:
    scheduler = TagScheduler("T2")
    assert scheduler.next_link() is None
    assert scheduler.accept_overheard_report(PacketHeader("T1", "A2", "REPORT", 0)) is False
    assert scheduler.next_link() is None
    assert scheduler.accept_overheard_report(PacketHeader("T1", "A2", "REPORT", 1)) is True
    assert scheduler.next_link().link_id == "A1-T2"
    scheduler.complete_local_link(success=True)
    assert scheduler.next_link().link_id == "A2-T2"
    scheduler.complete_local_link(success=True)
    assert scheduler.next_link() is None


def test_t1_waits_for_t2_completion_token_before_next_superframe() -> None:
    scheduler = TagScheduler("T1")
    assert scheduler.next_link().link_id == "A1-T1"
    scheduler.complete_local_link(success=True)
    assert scheduler.next_link().link_id == "A2-T1"
    scheduler.complete_local_link(success=True)
    assert scheduler.next_link() is None
    assert scheduler.accept_overheard_report(PacketHeader("T2", "A2", "REPORT", 3)) is True
    assert scheduler.next_link().link_id == "A1-T1"
    assert scheduler.current_sequence == 4


def test_local_failure_is_fail_closed_and_does_not_schedule_the_next_tx() -> None:
    scheduler = TagScheduler("T1")
    scheduler.complete_local_link(success=False)
    assert scheduler.next_link() is None
    assert scheduler.state == "FAILED"
