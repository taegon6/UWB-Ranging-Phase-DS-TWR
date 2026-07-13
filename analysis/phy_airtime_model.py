"""Paper-grounded IEEE 802.15.4z HRP packet-airtime calculations."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping


class AirtimeModelError(ValueError):
    """Raised when an airtime profile is incomplete or physically invalid."""


@dataclass(frozen=True)
class PacketAirtime:
    packet_name: str
    preamble_symbols: int
    sfd_symbols: int
    sts_symbols: int
    psdu_octets: int
    shr_us: float
    sts_us: float
    phr_us: float
    psdu_us: float
    total_us: float
    profile_type: str
    provenance: dict[str, Any]
    source_type: str = "SYNTHETIC"
    hardware_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parameter_value(
    parameter: Mapping[str, Any], name: str, *, expected_unit: str | None = None
) -> float:
    """Read one numeric parameter while enforcing provenance and HW status."""

    required = {"value", "unit", "evidence_class", "source", "locator", "hardware_verified"}
    missing = sorted(required - set(parameter))
    if missing:
        raise AirtimeModelError(f"{name} is missing provenance fields: {missing}")
    if parameter.get("hardware_verified") is not False:
        raise AirtimeModelError(f"{name}.hardware_verified must remain false for simulation input")
    if expected_unit is not None and parameter.get("unit") != expected_unit:
        raise AirtimeModelError(
            f"{name}.unit must be {expected_unit!r}, got {parameter.get('unit')!r}"
        )
    value = parameter.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise AirtimeModelError(f"{name}.value must be numeric")
    return float(value)


def _integer_parameter(
    parameter: Mapping[str, Any], name: str, *, expected_unit: str
) -> int:
    value = parameter_value(parameter, name, expected_unit=expected_unit)
    if value < 0 or not value.is_integer():
        raise AirtimeModelError(f"{name} must be a non-negative integer")
    return int(value)


def calculate_packet_airtime(
    phy: Mapping[str, Any],
    packet_name: str,
    packet: Mapping[str, Any],
    *,
    profile_type: str,
) -> PacketAirtime:
    """Calculate SHR/STS/PHR/PSDU time without mutating source profiles."""

    preamble_symbols = _integer_parameter(
        phy["preamble_symbols"], "phy.preamble_symbols", expected_unit="symbol"
    )
    sfd_symbols = _integer_parameter(
        phy["sfd_symbols"], "phy.sfd_symbols", expected_unit="symbol"
    )
    sts_symbols = _integer_parameter(
        phy["sts_symbols"], "phy.sts_symbols", expected_unit="symbol"
    )
    psdu_octets = _integer_parameter(
        packet["psdu_octets"],
        f"packets.{packet_name}.psdu_octets",
        expected_unit="octet",
    )
    preamble_symbol_time_us = parameter_value(
        phy["preamble_symbol_time_us"],
        "phy.preamble_symbol_time_us",
        expected_unit="us/symbol",
    )
    phr_time_us = parameter_value(
        phy["phr_time_us"], "phy.phr_time_us", expected_unit="us"
    )
    coded_bit_time_us = parameter_value(
        phy["coded_bit_time_us"], "phy.coded_bit_time_us", expected_unit="us/bit"
    )
    rs_parity_bits = _integer_parameter(
        phy["rs_parity_bits"], "phy.rs_parity_bits", expected_unit="bit"
    )
    if min(preamble_symbol_time_us, phr_time_us, coded_bit_time_us) < 0:
        raise AirtimeModelError("PHY time parameters must be non-negative")

    shr_us = (preamble_symbols + sfd_symbols) * preamble_symbol_time_us
    sts_us = sts_symbols * preamble_symbol_time_us
    psdu_us = (psdu_octets * 8 + rs_parity_bits) * coded_bit_time_us
    total_us = shr_us + sts_us + phr_time_us + psdu_us
    provenance = {
        "profile_type": profile_type,
        "preamble_symbols": dict(phy["preamble_symbols"]),
        "sfd_symbols": dict(phy["sfd_symbols"]),
        "sts_symbols": dict(phy["sts_symbols"]),
        "preamble_symbol_time_us": dict(phy["preamble_symbol_time_us"]),
        "phr_time_us": dict(phy["phr_time_us"]),
        "coded_bit_time_us": dict(phy["coded_bit_time_us"]),
        "rs_parity_bits": dict(phy["rs_parity_bits"]),
        "psdu_octets": dict(packet["psdu_octets"]),
    }
    return PacketAirtime(
        packet_name=packet_name,
        preamble_symbols=preamble_symbols,
        sfd_symbols=sfd_symbols,
        sts_symbols=sts_symbols,
        psdu_octets=psdu_octets,
        shr_us=shr_us,
        sts_us=sts_us,
        phr_us=phr_time_us,
        psdu_us=psdu_us,
        total_us=total_us,
        profile_type=profile_type,
        provenance=provenance,
    )


def calculate_profile_airtimes(profile: Mapping[str, Any]) -> dict[str, PacketAirtime]:
    """Calculate all packet types in one immutable PAPER or CODE_BASELINE profile."""

    phy = profile.get("phy")
    packets = profile.get("packets")
    profile_type = str(profile.get("profile_type", ""))
    if not isinstance(phy, Mapping) or not isinstance(packets, Mapping):
        raise AirtimeModelError("profile must contain phy and packets mappings")
    if profile_type not in {"PAPER", "CODE_BASELINE"}:
        raise AirtimeModelError(f"unsupported profile_type: {profile_type!r}")
    return {
        str(name): calculate_packet_airtime(
            phy,
            str(name),
            packet,
            profile_type=profile_type,
        )
        for name, packet in packets.items()
        if isinstance(packet, Mapping)
    }


def minimum_reply_us(processing_time_us: float, outgoing_packet: PacketAirtime) -> float:
    """Paper model: reply Rmarker delay = processing + outgoing packet airtime."""

    processing = float(processing_time_us)
    if processing < 0:
        raise AirtimeModelError("processing_time_us must be non-negative")
    return processing + math.ceil(outgoing_packet.total_us)


def timeout_duration_us(incoming_packet: PacketAirtime, margin_us: float) -> float:
    """Paper model: RX timeout duration = incoming packet airtime + margin."""

    margin = float(margin_us)
    if margin < 0:
        raise AirtimeModelError("timeout margin must be non-negative")
    return math.ceil(incoming_packet.total_us) + margin


__all__ = [
    "AirtimeModelError",
    "PacketAirtime",
    "calculate_packet_airtime",
    "calculate_profile_airtimes",
    "minimum_reply_us",
    "parameter_value",
    "timeout_duration_us",
]
