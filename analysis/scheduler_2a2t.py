"""Direct-2A2T half-duplex scheduling with hard overlap/collision failures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

from analysis.twr_timeline_model import LinkTimeline, PacketEvent, RxWindow


class ScheduleConflictError(RuntimeError):
    """Raised for any invalid node occupancy or receiver collision."""

    def __init__(self, kind: str, detail: str) -> None:
        self.kind = kind
        self.detail = detail
        super().__init__(f"{kind}: {detail}")


@dataclass(frozen=True)
class NodeActivity:
    node: str
    mode: str
    link: str
    packet_name: str
    peer: str
    start_us: float
    end_us: float


@dataclass(frozen=True)
class ScheduleResult:
    links_completed: list[str]
    packet_events: tuple[PacketEvent, ...]
    node_activities: tuple[NodeActivity, ...]
    superframe_duration_us: float
    complete_superframe: bool
    node_overlap_count: int
    receiver_collision_count: int
    node_duty_cycles: dict[str, float]
    source_type: str = "SYNTHETIC"
    hardware_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return start_a < end_b - 1e-9 and start_b < end_a - 1e-9


def _receiver_collision(events: Sequence[PacketEvent]) -> None:
    for index, first in enumerate(events):
        for second in events[index + 1 :]:
            if first.link == second.link:
                continue
            if (
                first.receiver == second.receiver
                and first.receiver.startswith("A")
                and first.sender != second.sender
                and _overlap(first.start_us, first.end_us, second.start_us, second.end_us)
            ):
                raise ScheduleConflictError(
                    "RECEIVER_COLLISION",
                    (
                        f"{first.receiver} receives {first.link}/{first.packet_name} and "
                        f"{second.link}/{second.packet_name} simultaneously"
                    ),
                )


def _activities(
    events: Iterable[PacketEvent], rx_windows: Iterable[RxWindow]
) -> tuple[NodeActivity, ...]:
    events = tuple(events)
    rx_windows = tuple(rx_windows)
    window_keys = {
        (window.link, window.packet_name, window.receiver) for window in rx_windows
    }
    event_by_key = {
        (event.link, event.packet_name, event.receiver): event for event in events
    }
    rows: list[NodeActivity] = []
    for event in events:
        rows.append(
            NodeActivity(
                node=event.sender,
                mode="TX",
                link=event.link,
                packet_name=event.packet_name,
                peer=event.receiver,
                start_us=event.start_us,
                end_us=event.end_us,
            )
        )
        key = (event.link, event.packet_name, event.receiver)
        if key not in window_keys:
            rows.append(
                NodeActivity(
                    node=event.receiver,
                    mode="RX",
                    link=event.link,
                    packet_name=event.packet_name,
                    peer=event.sender,
                    start_us=event.start_us,
                    end_us=event.end_us,
                )
            )
    for window in rx_windows:
        key = (window.link, window.packet_name, window.receiver)
        event = event_by_key.get(key)
        rows.append(
            NodeActivity(
                node=window.receiver,
                mode="RX",
                link=window.link,
                packet_name=window.packet_name,
                peer=event.sender if event is not None else "UNKNOWN",
                start_us=window.start_us,
                # The successful synthetic path exits RX when the expected
                # packet completes; timeout-end occupancy belongs to a future
                # packet-loss/retry model, which Phase 4 does not implement.
                end_us=window.expected_packet_end_us,
            )
        )
    return tuple(sorted(rows, key=lambda item: (item.start_us, item.node, item.mode)))


def _node_overlap(activities: Sequence[NodeActivity]) -> None:
    by_node: dict[str, list[NodeActivity]] = {}
    for activity in activities:
        by_node.setdefault(activity.node, []).append(activity)
    for node, rows in by_node.items():
        ordered = sorted(rows, key=lambda item: (item.start_us, item.end_us))
        for index, first in enumerate(ordered):
            for second in ordered[index + 1 :]:
                if second.start_us >= first.end_us - 1e-9:
                    break
                if first.link == second.link and first.packet_name == second.packet_name:
                    continue
                if _overlap(first.start_us, first.end_us, second.start_us, second.end_us):
                    raise ScheduleConflictError(
                        "NODE_TX_RX_OVERLAP",
                        (
                            f"{node} has {first.mode} {first.link}/{first.packet_name} and "
                            f"{second.mode} {second.link}/{second.packet_name} simultaneously"
                        ),
                    )


def _finalize(
    events: Sequence[PacketEvent], links: list[str], rx_windows: Sequence[RxWindow]
) -> ScheduleResult:
    ordered = tuple(sorted(events, key=lambda item: (item.start_us, item.end_us, item.link)))
    _receiver_collision(ordered)
    activities = _activities(ordered, rx_windows)
    _node_overlap(activities)
    start = min((event.start_us for event in ordered), default=0.0)
    end = max((event.end_us for event in ordered), default=0.0)
    duration = max(0.0, end - start)
    occupied: dict[str, float] = {}
    for activity in activities:
        occupied[activity.node] = occupied.get(activity.node, 0.0) + (
            activity.end_us - activity.start_us
        )
    duty = {
        node: (value / duration if duration > 0 else 0.0)
        for node, value in sorted(occupied.items())
    }
    unique_links = list(dict.fromkeys(links))
    return ScheduleResult(
        links_completed=unique_links,
        packet_events=ordered,
        node_activities=activities,
        superframe_duration_us=duration,
        complete_superframe=set(unique_links) == {"A1-T1", "A2-T1", "A1-T2", "A2-T2"},
        node_overlap_count=0,
        receiver_collision_count=0,
        node_duty_cycles=duty,
    )


def merge_timelines_at_offsets(
    timelines: Sequence[tuple[LinkTimeline, float]],
) -> ScheduleResult:
    """Merge explicit offsets and fail on the first collision/overlap."""

    events: list[PacketEvent] = []
    windows: list[RxWindow] = []
    links: list[str] = []
    for timeline, raw_offset in timelines:
        offset = float(raw_offset)
        if offset < 0:
            raise ValueError("timeline offsets must be non-negative")
        shifted = timeline.shifted(offset)
        events.extend(shifted.packet_events)
        windows.extend(shifted.rx_windows)
        links.append(timeline.link)
    return _finalize(events, links, windows)


def schedule_sequential_2a2t(
    timelines: Sequence[LinkTimeline],
    *,
    slot_guard_us: float,
) -> ScheduleResult:
    """Place all four direct-2A2T links in collision-free time slots."""

    guard = float(slot_guard_us)
    if guard < 0:
        raise ValueError("slot_guard_us must be non-negative")
    if len(timelines) != 4 or len({timeline.link for timeline in timelines}) != 4:
        raise ValueError("direct 2A2T requires exactly four unique link timelines")
    offset = 0.0
    shifted: list[tuple[LinkTimeline, float]] = []
    for timeline in timelines:
        shifted.append((timeline, offset))
        offset += timeline.duration_us + guard
    result = merge_timelines_at_offsets(shifted)
    if not result.complete_superframe:
        raise ScheduleConflictError(
            "INCOMPLETE_SUPERFRAME",
            f"completed links: {result.links_completed}",
        )
    return result


__all__ = [
    "NodeActivity",
    "ScheduleConflictError",
    "ScheduleResult",
    "merge_timelines_at_offsets",
    "schedule_sequential_2a2t",
]
