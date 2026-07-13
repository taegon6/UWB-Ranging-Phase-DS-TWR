"""Pure-Python contract for the Phase 6 four-node firmware protocol.

This is deliberately a protocol oracle, not a radio simulator.  The firmware
and host-side parsers use the same fixed slot order and frame conventions, so
golden tests can reject stale packets before any physical DW3000 is connected.
"""

from __future__ import annotations

from dataclasses import dataclass


FCS_LENGTH = 2
FINAL_EXTENSION_LENGTH = 6
VALID_NODES = frozenset({"A1", "A2", "T1", "T2"})
TAG_NODES = frozenset({"T1", "T2"})
ANCHOR_NODES = frozenset({"A1", "A2"})


class Phase6ProtocolError(ValueError):
    """A frame or scheduler transition violates the fail-closed contract."""


@dataclass(frozen=True)
class FrameLayout:
    """Driver data and complete on-air PSDU byte lengths.

    The DW3000 driver data buffer excludes the hardware-appended two-byte FCS;
    ``on_air_psdu_length`` is the programmed length including that FCS.
    """

    driver_data_length: int
    on_air_psdu_length: int

    def __post_init__(self) -> None:
        if self.on_air_psdu_length != self.driver_data_length + FCS_LENGTH:
            raise Phase6ProtocolError("frame layout must include exactly one FCS")


FRAME_LAYOUTS = {
    "POLL": FrameLayout(driver_data_length=10, on_air_psdu_length=12),
    "RESPONSE": FrameLayout(driver_data_length=11, on_air_psdu_length=13),
    "FINAL": FrameLayout(driver_data_length=32, on_air_psdu_length=34),
    "POST_FINAL": FrameLayout(driver_data_length=10, on_air_psdu_length=12),
    "REPORT": FrameLayout(driver_data_length=14, on_air_psdu_length=16),
}


@dataclass(frozen=True)
class LinkDefinition:
    slot_id: int
    anchor: str
    tag: str
    wire_sequence: int
    superframe_mod64: int

    @property
    def link_id(self) -> str:
        return f"{self.anchor}-{self.tag}"


_SLOT_NODES = (
    ("A1", "T1"),
    ("A2", "T1"),
    ("A1", "T2"),
    ("A2", "T2"),
)


def link_for_sequence(sequence: int) -> LinkDefinition:
    """Map an arbitrary monotonic sequence counter to one 8-bit RF exchange."""

    if not isinstance(sequence, int) or sequence < 0:
        raise Phase6ProtocolError("sequence must be a non-negative integer")
    wire_sequence = sequence & 0xFF
    slot_id = wire_sequence % 4
    anchor, tag = _SLOT_NODES[slot_id]
    return LinkDefinition(
        slot_id=slot_id,
        anchor=anchor,
        tag=tag,
        wire_sequence=wire_sequence,
        superframe_mod64=wire_sequence // 4,
    )


@dataclass(frozen=True)
class PacketHeader:
    destination: str
    source: str
    function_code: str
    sequence: int

    def __post_init__(self) -> None:
        if self.destination not in VALID_NODES:
            raise Phase6ProtocolError(f"unknown destination: {self.destination}")
        if self.source not in VALID_NODES:
            raise Phase6ProtocolError(f"unknown source: {self.source}")
        if self.function_code not in FRAME_LAYOUTS:
            raise Phase6ProtocolError(f"unknown function: {self.function_code}")
        if not isinstance(self.sequence, int) or not 0 <= self.sequence <= 0xFF:
            raise Phase6ProtocolError("sequence must be an unsigned 8-bit value")


def validate_link_packet(header: PacketHeader, link: LinkDefinition, function_code: str) -> None:
    """Validate complete addressing and correlation before payload processing."""

    if function_code not in FRAME_LAYOUTS:
        raise Phase6ProtocolError(f"unknown expected function: {function_code}")
    if header.function_code != function_code:
        raise Phase6ProtocolError(
            f"function mismatch: expected {function_code}, received {header.function_code}"
        )
    if header.sequence != link.wire_sequence:
        raise Phase6ProtocolError(
            f"sequence mismatch: expected {link.wire_sequence}, received {header.sequence}"
        )
    if function_code in {"POLL", "FINAL", "POST_FINAL"}:
        expected_source, expected_destination = link.tag, link.anchor
    else:
        expected_source, expected_destination = link.anchor, link.tag
    if header.destination != expected_destination:
        raise Phase6ProtocolError(
            f"destination mismatch: expected {expected_destination}, received {header.destination}"
        )
    if header.source != expected_source:
        raise Phase6ProtocolError(
            f"source mismatch: expected {expected_source}, received {header.source}"
        )


def encode_final_extension(*, protocol_version: int, slot_id: int, superframe_id: int) -> bytes:
    """Encode Final bytes 26..31 without changing the 32-byte data length."""

    if not 0 <= protocol_version <= 0xFF:
        raise Phase6ProtocolError("protocol_version must fit in one byte")
    if not 0 <= slot_id < 4:
        raise Phase6ProtocolError("slot_id must be in [0, 3]")
    if not 0 <= superframe_id <= 0xFFFFFFFF:
        raise Phase6ProtocolError("superframe_id must fit in four bytes")
    return bytes((protocol_version, slot_id)) + superframe_id.to_bytes(4, "little")


def decode_final_extension(payload: bytes) -> dict[str, int]:
    if len(payload) != FINAL_EXTENSION_LENGTH:
        raise Phase6ProtocolError(
            f"Final extension must be {FINAL_EXTENSION_LENGTH} bytes, got {len(payload)}"
        )
    version, slot_id = payload[0], payload[1]
    if slot_id >= 4:
        raise Phase6ProtocolError(f"slot_id must be in [0, 3], got {slot_id}")
    return {
        "protocol_version": version,
        "slot_id": slot_id,
        "superframe_id": int.from_bytes(payload[2:], "little"),
    }


class TagScheduler:
    """Fail-closed T1/T2 report-token state machine.

    T1 begins slot 0.  T2 sends no RF packet until it overhears the A2->T1
    report for slot 1.  After slot 3, T1 similarly waits for A2->T2 before
    starting the next superframe.  A packet loss therefore cannot turn into an
    unscheduled TX.
    """

    def __init__(self, local_tag: str) -> None:
        if local_tag not in TAG_NODES:
            raise Phase6ProtocolError("TagScheduler requires T1 or T2")
        self.local_tag = local_tag
        self.current_sequence = 0 if local_tag == "T1" else 2
        self._expected_token_sequence = 3 if local_tag == "T1" else 1
        self.state = "READY" if local_tag == "T1" else "WAIT_TOKEN"

    def next_link(self) -> LinkDefinition | None:
        if self.state != "READY":
            return None
        link = link_for_sequence(self.current_sequence)
        if link.tag != self.local_tag:
            raise Phase6ProtocolError("scheduler internal tag/slot mismatch")
        return link

    def complete_local_link(self, *, success: bool) -> None:
        """Close exactly one local exchange; failure suppresses all future TX."""

        if self.state != "READY" or self.next_link() is None:
            raise Phase6ProtocolError("no local link is active")
        if not success:
            self.state = "FAILED"
            return
        completed_sequence = self.current_sequence
        completed_slot = completed_sequence % 4
        if completed_slot in {0, 2}:
            self.current_sequence = (completed_sequence + 1) & 0xFF
            self.state = "READY"
            return
        self._expected_token_sequence = (completed_sequence + 2) & 0xFF
        self.state = "WAIT_TOKEN"

    def accept_overheard_report(self, header: PacketHeader) -> bool:
        """Accept only the A2 Report that ends the other tag's second slot."""

        if self.state != "WAIT_TOKEN":
            return False
        expected = link_for_sequence(self._expected_token_sequence)
        if expected.anchor != "A2" or expected.tag == self.local_tag:
            raise Phase6ProtocolError("scheduler token definition is inconsistent")
        try:
            validate_link_packet(header, expected, "REPORT")
        except Phase6ProtocolError:
            return False
        self.current_sequence = (self._expected_token_sequence + 1) & 0xFF
        self.state = "READY"
        return True

    def token_timeout(self) -> None:
        """Record a timeout as a safe stopped state; recovery needs host policy."""

        if self.state == "WAIT_TOKEN":
            self.state = "TOKEN_TIMEOUT"


__all__ = [
    "ANCHOR_NODES",
    "FCS_LENGTH",
    "FINAL_EXTENSION_LENGTH",
    "FRAME_LAYOUTS",
    "FrameLayout",
    "LinkDefinition",
    "PacketHeader",
    "Phase6ProtocolError",
    "TAG_NODES",
    "TagScheduler",
    "decode_final_extension",
    "encode_final_extension",
    "link_for_sequence",
    "validate_link_packet",
]
