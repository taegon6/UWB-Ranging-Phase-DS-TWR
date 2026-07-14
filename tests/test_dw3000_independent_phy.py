from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path

import pytest

from analysis.dw3000_phy_model import (
    PhyModelError,
    TimeUnitError,
    calculate_dw3000_airtimes,
    canonical_ps,
)
from analysis.twr_timeline_model import (
    TimingConstraintError,
    resolve_current_five_packet_delays,
)
from hardware.device_inventory import ConfigError, load_yaml, validate_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "dw3000_current_phy.yaml"


def current_config() -> dict:
    config = load_yaml(CONFIG)
    assert validate_config(config) == []
    return config


def test_unsupported_time_unit_is_rejected_by_schema_and_runtime() -> None:
    config = current_config()
    broken = copy.deepcopy(config)
    broken["timing_constants"]["shr_symbol_time"]["unit"] = "fortnight"
    with pytest.raises(ConfigError, match="fortnight"):
        validate_config(broken)
    with pytest.raises(TimeUnitError, match="unsupported"):
        canonical_ps("1", "fortnight")


def test_current_packet_fcs_conventions_match_driver_calls() -> None:
    packets = current_config()["packets"]
    expected = {
        "Poll": (10, 10, False, 12, 12),
        "Response": (13, 11, True, 13, 13),
        "Final": (32, 32, False, 34, 34),
        "PostFinal": (10, 10, False, 12, 12),
        "Report": (14, 14, False, 16, 16),
    }
    for name, (
        buffer_octets,
        meaningful_octets,
        includes_fcs_placeholders,
        tx_frame_control_octets,
        on_air_psdu_octets,
    ) in expected.items():
        packet = packets[name]
        assert packet["driver_buffer_octets"] == buffer_octets
        assert packet["meaningful_buffer_octets"] == meaningful_octets
        assert packet["buffer_includes_fcs_placeholders"] is includes_fcs_placeholders
        assert packet["driver_tx_frame_control_octets"] == tx_frame_control_octets
        assert packet["fcs_octets"] == 2
        assert packet["on_air_psdu_octets"] == on_air_psdu_octets
        assert packet["mac_header_octets"] == 9
        assert packet["function_code_octets"] == 1
        assert (
            packet["mac_header_octets"]
            + packet["function_code_octets"]
            + packet["body_octets"]
            + packet["fcs_octets"]
            == on_air_psdu_octets
        )


def test_sts_off_and_on_packet_structures_are_explicit() -> None:
    off = current_config()
    off_airtime = calculate_dw3000_airtimes(off)["Poll"]
    assert off_airtime.t_sts_ps == Decimal(0)
    assert off_airtime.structure == ("PREAMBLE", "SFD", "PHR", "PSDU")

    unresolved = copy.deepcopy(off)
    unresolved["phy"]["sts_mode"] = "DWT_STS_MODE_1"
    with pytest.raises(PhyModelError, match="STS.*UNRESOLVED"):
        calculate_dw3000_airtimes(unresolved)

    assumed = copy.deepcopy(unresolved)
    assumed["timing_constants"]["sts_duration"] = {
        "value": "64",
        "unit": "us",
        "evidence_class": "ASSUMED",
        "source": "test-only explicit STS duration",
        "locator": "not a production DW3000 claim",
        "status": "ASSUMED",
        "hardware_verified": False,
    }
    assumed_airtime = calculate_dw3000_airtimes(assumed)["Poll"]
    assert assumed_airtime.t_sts_ps == Decimal("64000000")
    assert assumed_airtime.structure == ("PREAMBLE", "SFD", "STS", "PHR", "PSDU")

    assumed["phy"]["sts_mode"] = "DWT_STS_MODE_2"
    mode2 = calculate_dw3000_airtimes(assumed)["Poll"]
    assert mode2.structure == ("PREAMBLE", "SFD", "PHR", "PSDU", "STS")


def test_independent_plen128_airtime_uses_dw3000_symbol_table() -> None:
    packets = calculate_dw3000_airtimes(current_config())
    poll = packets["Poll"]
    assert poll.t_preamble_ps == Decimal("130256640")
    assert poll.t_sfd_ps == Decimal("8141040")
    assert poll.t_phr_ps == Decimal("21538440")
    assert poll.t_psdu_ps == Decimal("18462240")
    assert poll.total_ps == Decimal("178398360")
    assert poll.total_us == Decimal("178.39836")


def test_independent_plen1024_changes_only_preamble_component() -> None:
    plen128 = current_config()
    plen1024 = copy.deepcopy(plen128)
    plen1024["phy"]["preamble_symbols"] = 1024
    short = calculate_dw3000_airtimes(plen128)["Poll"]
    long = calculate_dw3000_airtimes(plen1024)["Poll"]
    assert long.t_preamble_ps == Decimal("1042053120")
    assert long.t_sfd_ps == short.t_sfd_ps
    assert long.t_phr_ps == short.t_phr_ps
    assert long.t_psdu_ps == short.t_psdu_ps
    assert long.total_ps - short.total_ps == Decimal(896) * Decimal("1017630")


def test_one_on_air_psdu_octet_monotonically_increases_airtime() -> None:
    config = current_config()
    original = calculate_dw3000_airtimes(config)["Poll"]
    longer = copy.deepcopy(config)
    packet = longer["packets"]["Poll"]
    packet["body_octets"] += 1
    packet["meaningful_buffer_octets"] += 1
    packet["driver_buffer_octets"] += 1
    packet["driver_tx_frame_control_octets"] += 1
    packet["on_air_psdu_octets"] += 1
    changed = calculate_dw3000_airtimes(longer)["Poll"]
    assert changed.total_ps > original.total_ps
    assert changed.t_psdu_ps - original.t_psdu_ps == Decimal(8) * Decimal("128210")


def test_paper_and_current_packet_definitions_are_separate() -> None:
    paper = load_yaml(ROOT / "configs" / "simulation_2a2t_paper_baseline.yaml")
    current = current_config()
    assert set(paper["paper_profiles"]["paper_plen128"]["packets"]) == {
        "Poll", "Response", "Final"
    }
    assert set(current["packets"]) == {
        "Poll", "Response", "Final", "PostFinal", "Report"
    }
    assert current["model_role"] == "CURRENT_FIRMWARE_INDEPENDENT_PHY"
    assert current["paper_table_2_role"] == "REGRESSION_COMPARISON_ONLY"


def test_final_to_post_final_does_not_reuse_remote_reply_formula() -> None:
    config = current_config()
    airtimes = calculate_dw3000_airtimes(config)
    config["transition_timing"]["PostFinal->Report"]["delay"] = {
        "value": "2522",
        "unit": "us",
        "evidence_class": "ASSUMED",
        "source": "test-only non-paper transition assumption",
        "locator": "independence test",
        "status": "ASSUMED",
        "hardware_verified": False,
    }
    first = resolve_current_five_packet_delays(
        airtimes,
        config["transition_timing"],
        remote_processing_us=Decimal(522),
        remote_reply_guard_us=Decimal(100),
    )
    second = resolve_current_five_packet_delays(
        airtimes,
        config["transition_timing"],
        remote_processing_us=Decimal(800),
        remote_reply_guard_us=Decimal(400),
    )
    assert first["Poll->Response"] != second["Poll->Response"]
    assert first["Response->Final"] != second["Response->Final"]
    assert first["Final->PostFinal"] == second["Final->PostFinal"]
    assert first["Final->PostFinal"] == canonical_ps("1650", "UUS")


def test_post_final_to_report_requires_explicit_non_paper_timing() -> None:
    config = current_config()
    airtimes = calculate_dw3000_airtimes(config)
    with pytest.raises(TimingConstraintError, match="PostFinal->Report.*UNRESOLVED"):
        resolve_current_five_packet_delays(
            airtimes,
            config["transition_timing"],
            remote_processing_us=Decimal(522),
            remote_reply_guard_us=Decimal(100),
        )

    assumed = copy.deepcopy(config["transition_timing"])
    assumed["PostFinal->Report"]["delay"] = {
        "value": "2522",
        "unit": "us",
        "evidence_class": "ASSUMED",
        "source": "legacy Phase 4 synthetic assumption",
        "locator": "not paper reply timing",
        "status": "ASSUMED",
        "hardware_verified": False,
    }
    first = resolve_current_five_packet_delays(
        airtimes,
        assumed,
        remote_processing_us=Decimal(522),
        remote_reply_guard_us=Decimal(0),
    )
    second = resolve_current_five_packet_delays(
        airtimes,
        assumed,
        remote_processing_us=Decimal(800),
        remote_reply_guard_us=Decimal(800),
    )
    assert first["PostFinal->Report"] == second["PostFinal->Report"]
    assert first["PostFinal->Report"] == canonical_ps("2522", "us")


def test_decimal_canonical_output_is_bitwise_deterministic() -> None:
    first = calculate_dw3000_airtimes(current_config())
    second = calculate_dw3000_airtimes(current_config())
    assert first == second
    assert all(isinstance(packet.total_ps, Decimal) for packet in first.values())
    assert all(str(packet.total_us) == str(second[name].total_us) for name, packet in first.items())


def test_supported_time_unit_conversions_are_explicit() -> None:
    assert canonical_ps("1", "ps") == Decimal(1)
    assert canonical_ps("1", "ns") == Decimal(1000)
    assert canonical_ps("1", "us") == Decimal(1_000_000)
    assert canonical_ps("1", "UUS") == canonical_ps("65536", "dtu")
