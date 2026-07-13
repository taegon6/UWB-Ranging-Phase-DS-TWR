"""Phase-4 direct-2A2T parameter sweep over immutable baseline profiles."""

from __future__ import annotations

from itertools import product
from typing import Any, Mapping

from analysis.phy_airtime_model import calculate_profile_airtimes, minimum_reply_us, parameter_value
from analysis.scheduler_2a2t import schedule_sequential_2a2t
from analysis.twr_timeline_model import build_link_timeline


def _provenance(parameter: Mapping[str, Any]) -> dict[str, Any]:
    parameter_value(parameter, "sweep parameter")
    return dict(parameter)


def run_parameter_sweep(
    baseline: Mapping[str, Any], sweep_config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Return only collision-free, complete four-link candidates.

    PAPER and CODE_BASELINE objects are read-only inputs. Candidate values and
    their complete provenance are copied into every output row.
    """

    if sweep_config.get("phase_gate") != {
        "implemented_through": 4,
        "phase_5_enabled": False,
        "phase_6_enabled": False,
    }:
        raise ValueError("Phase 5/6 must remain disabled during the Phase 0-4 sweep")
    protocol = sweep_config["protocol"]
    links = list(protocol["slot_order"])
    if set(links) != {"A1-T1", "A2-T1", "A1-T2", "A2-T2"}:
        raise ValueError("direct 2A2T sweep requires all four links")
    sequence = list(protocol["sequence"])
    transitions = [f"{a}->{b}" for a, b in zip(sequence, sequence[1:])]
    profiles = baseline["code_baseline_profiles"]
    dimensions = sweep_config["sweep"]
    rows: list[dict[str, Any]] = []

    for profile_name, processing_p, guard_p, timeout_p, slot_p in product(
        dimensions["profile_names"],
        dimensions["processing_time_us"],
        dimensions["reply_guard_us"],
        dimensions["timeout_margin_us"],
        dimensions["slot_guard_us"],
    ):
        if profile_name not in profiles:
            raise ValueError(f"unknown CODE_BASELINE profile: {profile_name}")
        profile = profiles[profile_name]
        airtimes = calculate_profile_airtimes(profile)
        processing = parameter_value(processing_p, "processing_time_us")
        guard = parameter_value(guard_p, "reply_guard_us")
        timeout = parameter_value(timeout_p, "timeout_margin_us")
        slot_guard = parameter_value(slot_p, "slot_guard_us")
        reply_delays = {
            transition: minimum_reply_us(processing, airtimes[outgoing]) + guard
            for transition, outgoing in zip(transitions, sequence[1:])
        }
        reply_delay_provenance = {
            transition: {
                "value": value,
                "unit": "us",
                "evidence_class": "PAPER_DERIVED",
                "source": "paper airtime/processing model plus explicit sweep guard",
                "locator": f"minimum_reply_us + reply_guard_us ({transition})",
                "hardware_verified": False,
            }
            for transition, value in reply_delays.items()
        }
        timelines = [
            build_link_timeline(
                profile,
                link=link,
                sequence=sequence,
                reply_delays_us=reply_delays,
                processing_time_us=processing,
                timeout_margin_us=timeout,
            )
            for link in links
        ]
        schedule = schedule_sequential_2a2t(timelines, slot_guard_us=slot_guard)
        duration = schedule.superframe_duration_us
        provenance = {
            "profile": {
                "value": profile_name,
                "evidence_class": "CODE_BASELINE",
                "source": baseline.get("sources", {}).get("firmware", {}),
                "hardware_verified": False,
            },
            "processing_time_us": _provenance(processing_p),
            "reply_guard_us": _provenance(guard_p),
            "timeout_margin_us": _provenance(timeout_p),
            "slot_guard_us": _provenance(slot_p),
        }
        rows.append(
            {
                "candidate_id": f"C{len(rows) + 1:04d}",
                "profile_name": profile_name,
                "processing_time_us": processing,
                "reply_guard_us": guard,
                "timeout_margin_us": timeout,
                "slot_guard_us": slot_guard,
                "reply_delays_us": reply_delays,
                "reply_delay_provenance": reply_delay_provenance,
                "rx_acquisition_lead_us": timeout / 2.0,
                "rx_acquisition_lead_provenance": {
                    "value": timeout / 2.0,
                    "unit": "us",
                    "evidence_class": "ASSUMED",
                    "source": "synthetic timeline model",
                    "locator": "timeout_margin_us / 2",
                    "hardware_verified": False,
                },
                "links_completed": len(schedule.links_completed),
                "complete_superframe": schedule.complete_superframe,
                "superframe_duration_us": duration,
                "superframe_rate_hz": 1_000_000.0 / duration,
                "min_reply_headroom_us": min(
                    value for timeline in timelines for value in timeline.reply_headrooms_us
                ),
                "min_timeout_headroom_us": min(
                    value for timeline in timelines for value in timeline.timeout_headrooms_us
                ),
                "max_node_duty_cycle": max(schedule.node_duty_cycles.values()),
                "node_overlap_count": schedule.node_overlap_count,
                "receiver_collision_count": schedule.receiver_collision_count,
                "provenance": provenance,
                "source_type": "SYNTHETIC",
                "hardware_verified": False,
            }
        )
    return rows


__all__ = ["run_parameter_sweep"]
