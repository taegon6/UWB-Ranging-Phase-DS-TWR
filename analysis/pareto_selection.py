"""Deterministic Pareto selection for synthetic direct-2A2T candidates."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


_MAXIMIZE = ("superframe_rate_hz", "min_reply_headroom_us", "min_timeout_headroom_us")
_MINIMIZE = ("max_node_duty_cycle",)


def _dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    no_worse = all(float(left[k]) >= float(right[k]) for k in _MAXIMIZE) and all(
        float(left[k]) <= float(right[k]) for k in _MINIMIZE
    )
    better = any(float(left[k]) > float(right[k]) for k in _MAXIMIZE) or any(
        float(left[k]) < float(right[k]) for k in _MINIMIZE
    )
    return no_worse and better


def pareto_front(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Keep valid candidates not dominated on rate, margins, and duty cycle."""

    eligible = [
        row
        for row in rows
        if row.get("complete_superframe") is True
        and row.get("node_overlap_count") == 0
        and row.get("receiver_collision_count") == 0
        and row.get("source_type") == "SYNTHETIC"
        and row.get("hardware_verified") is False
    ]
    front = [row for row in eligible if not any(_dominates(other, row) for other in eligible if other is not row)]
    return [dict(row) for row in sorted(front, key=lambda row: str(row["candidate_id"]))]


__all__ = ["pareto_front"]
