"""Rmarker-based single-link DS-TWR timeline model for paper and 5-packet flows."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Mapping, Sequence

from analysis.phy_airtime_model import (
    PacketAirtime,
    calculate_profile_airtimes,
    minimum_reply_us,
    timeout_duration_us,
)


class TimingConstraintError(ValueError):
    """Raised when delayed-TX or RX-window constraints cannot be satisfied."""


@dataclass(frozen=True)
class PacketEvent:
    link: str
    packet_name: str
    sender: str
    receiver: str
    start_us: float
    rmarker_us: float
    end_us: float
    airtime_us: float
    source_type: str = "SYNTHETIC"
    hardware_verified: bool = False

    def shifted(self, offset_us: float) -> "PacketEvent":
        return replace(
            self,
            start_us=self.start_us + offset_us,
            rmarker_us=self.rmarker_us + offset_us,
            end_us=self.end_us + offset_us,
        )


@dataclass(frozen=True)
class RxWindow:
    link: str
    packet_name: str
    receiver: str
    start_us: float
    end_us: float
    expected_packet_start_us: float
    expected_packet_end_us: float
    timeout_duration_us: float
    timeout_headroom_us: float
    source_type: str = "SYNTHETIC"
    hardware_verified: bool = False

    def shifted(self, offset_us: float) -> "RxWindow":
        return replace(
            self,
            start_us=self.start_us + offset_us,
            end_us=self.end_us + offset_us,
            expected_packet_start_us=self.expected_packet_start_us + offset_us,
            expected_packet_end_us=self.expected_packet_end_us + offset_us,
        )


@dataclass(frozen=True)
class LinkTimeline:
    link: str
    anchor: str
    tag: str
    sequence: tuple[str, ...]
    packet_events: tuple[PacketEvent, ...]
    rx_windows: tuple[RxWindow, ...]
    reply_headrooms_us: tuple[float, ...]
    timeout_headrooms_us: tuple[float, ...]
    duration_us: float
    constraint_failures: list[str] = field(default_factory=list)
    source_type: str = "SYNTHETIC"
    hardware_verified: bool = False

    def shifted(self, offset_us: float) -> "LinkTimeline":
        if offset_us < 0:
            raise TimingConstraintError("timeline offset must be non-negative")
        return replace(
            self,
            packet_events=tuple(event.shifted(offset_us) for event in self.packet_events),
            rx_windows=tuple(window.shifted(offset_us) for window in self.rx_windows),
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["complete"] = not self.constraint_failures
        return result


_DIRECTION_BY_PACKET = {
    "Poll": ("TAG", "ANCHOR"),
    "Response": ("ANCHOR", "TAG"),
    "Final": ("TAG", "ANCHOR"),
    "PostFinal": ("TAG", "ANCHOR"),
    "Report": ("ANCHOR", "TAG"),
}


def parse_link(link: str) -> tuple[str, str]:
    try:
        anchor, tag = str(link).split("-", 1)
    except ValueError as exc:
        raise TimingConstraintError(f"invalid link identifier: {link!r}") from exc
    if anchor not in {"A1", "A2"} or tag not in {"T1", "T2"}:
        raise TimingConstraintError(f"invalid 2A2T link identifier: {link!r}")
    return anchor, tag


def _nodes_for_packet(packet_name: str, anchor: str, tag: str) -> tuple[str, str]:
    direction = _DIRECTION_BY_PACKET.get(packet_name)
    if direction is None:
        raise TimingConstraintError(f"packet direction is not defined: {packet_name}")
    sender_role, receiver_role = direction
    sender = anchor if sender_role == "ANCHOR" else tag
    receiver = anchor if receiver_role == "ANCHOR" else tag
    return sender, receiver


def build_link_timeline(
    profile: Mapping[str, Any],
    *,
    link: str,
    sequence: Sequence[str],
    reply_delays_us: Mapping[str, float],
    processing_time_us: float,
    timeout_margin_us: float,
) -> LinkTimeline:
    """Build one link and fail immediately on late-TX or RX-window violations."""

    anchor, tag = parse_link(link)
    names = tuple(str(name) for name in sequence)
    if len(names) < 2 or len(set(names)) != len(names):
        raise TimingConstraintError("sequence must contain at least two unique packet names")
    airtimes = calculate_profile_airtimes(profile)
    missing = [name for name in names if name not in airtimes]
    if missing:
        raise TimingConstraintError(f"profile is missing packet airtimes: {missing}")
    processing = float(processing_time_us)
    timeout_margin = float(timeout_margin_us)
    if processing < 0 or timeout_margin < 0:
        raise TimingConstraintError("processing and timeout margin must be non-negative")

    events: list[PacketEvent] = []
    windows: list[RxWindow] = []
    reply_headrooms: list[float] = []
    timeout_headrooms: list[float] = []

    first_airtime = airtimes[names[0]]
    first_sender, first_receiver = _nodes_for_packet(names[0], anchor, tag)
    first_rmarker = first_airtime.shr_us + first_airtime.sts_us
    events.append(
        PacketEvent(
            link=link,
            packet_name=names[0],
            sender=first_sender,
            receiver=first_receiver,
            start_us=0.0,
            rmarker_us=first_rmarker,
            end_us=first_airtime.total_us,
            airtime_us=first_airtime.total_us,
        )
    )

    for previous_name, packet_name in zip(names, names[1:]):
        transition = f"{previous_name}->{packet_name}"
        if transition not in reply_delays_us:
            raise TimingConstraintError(f"missing reply delay for {transition}")
        reply_delay = float(reply_delays_us[transition])
        packet_airtime: PacketAirtime = airtimes[packet_name]
        minimum = minimum_reply_us(processing, packet_airtime)
        headroom = reply_delay - minimum
        if headroom < -1e-9:
            raise TimingConstraintError(
                f"reply delay for {transition} is {reply_delay:.6f} us but minimum is {minimum:.6f} us"
            )
        previous_event = events[-1]
        rmarker = previous_event.rmarker_us + reply_delay
        rmarker_offset = packet_airtime.shr_us + packet_airtime.sts_us
        packet_start = rmarker - rmarker_offset
        packet_end = packet_start + packet_airtime.total_us
        sender, receiver = _nodes_for_packet(packet_name, anchor, tag)
        event = PacketEvent(
            link=link,
            packet_name=packet_name,
            sender=sender,
            receiver=receiver,
            start_us=packet_start,
            rmarker_us=rmarker,
            end_us=packet_end,
            airtime_us=packet_airtime.total_us,
        )
        # The receiver may defer RX enable when the reply delay intentionally
        # exceeds the minimum.  Model a conservative synthetic acquisition lead
        # of half the timeout margin, while never enabling RX before the node is
        # ready after processing the previous packet.
        receiver_ready = previous_event.rmarker_us + processing
        acquisition_lead = timeout_margin / 2.0
        rx_start = max(receiver_ready, packet_start - acquisition_lead)
        rx_duration = timeout_duration_us(packet_airtime, timeout_margin)
        rx_end = rx_start + rx_duration
        if packet_start < rx_start - 1e-9:
            raise TimingConstraintError(
                f"RX starts too late for {transition}: packet={packet_start:.6f}, rx={rx_start:.6f}"
            )
        if packet_end > rx_end + 1e-9:
            raise TimingConstraintError(
                f"RX timeout does not cover {transition}: packet_end={packet_end:.6f}, rx_end={rx_end:.6f}"
            )
        timeout_headroom = rx_end - packet_end
        events.append(event)
        windows.append(
            RxWindow(
                link=link,
                packet_name=packet_name,
                receiver=receiver,
                start_us=rx_start,
                end_us=rx_end,
                expected_packet_start_us=packet_start,
                expected_packet_end_us=packet_end,
                timeout_duration_us=rx_duration,
                timeout_headroom_us=timeout_headroom,
            )
        )
        reply_headrooms.append(headroom)
        timeout_headrooms.append(timeout_headroom)

    duration = events[-1].end_us - events[0].start_us
    return LinkTimeline(
        link=link,
        anchor=anchor,
        tag=tag,
        sequence=names,
        packet_events=tuple(events),
        rx_windows=tuple(windows),
        reply_headrooms_us=tuple(reply_headrooms),
        timeout_headrooms_us=tuple(timeout_headrooms),
        duration_us=duration,
    )


__all__ = [
    "LinkTimeline",
    "PacketEvent",
    "RxWindow",
    "TimingConstraintError",
    "build_link_timeline",
    "parse_link",
]
