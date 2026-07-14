"""Independent DW3000 HRP airtime model using canonical Decimal picoseconds.

This module is intentionally separate from ``phy_airtime_model.py``.  The
latter reproduces the paper fixture; this module calculates the current
firmware PPDU from Qorvo DW3000 symbol timings and explicit frame conventions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any, Mapping


class PhyModelError(ValueError):
    """Raised when a PHY setting or frame convention is unresolved/invalid."""


class TimeUnitError(PhyModelError):
    """Raised when time enters the model without an explicit supported unit."""


SUPPORTED_TIME_UNITS = frozenset({"ps", "ns", "us", "dtu", "UUS"})
_PS_PER_NS = Decimal(1_000)
_PS_PER_US = Decimal(1_000_000)
_DW_CLOCK_HZ = Decimal(499_200_000) * Decimal(128)
_UUS_DTU = Decimal(65_536)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TimeUnitError("boolean is not a time value")
    try:
        return Decimal(str(value))
    except Exception as exc:  # pragma: no cover - Decimal has several exception types
        raise TimeUnitError(f"invalid Decimal time value: {value!r}") from exc


def canonical_ps(value: Any, unit: str) -> Decimal:
    """Convert an explicitly typed value to canonical Decimal picoseconds."""

    if unit not in SUPPORTED_TIME_UNITS:
        raise TimeUnitError(f"unsupported time unit: {unit!r}")
    number = _decimal(value)
    with localcontext() as context:
        context.prec = 50
        if unit == "ps":
            return +number
        if unit == "ns":
            return +(number * _PS_PER_NS)
        if unit == "us":
            return +(number * _PS_PER_US)
        dtu_ps = Decimal(1_000_000_000_000) / _DW_CLOCK_HZ
        if unit == "dtu":
            return +(number * dtu_ps)
        return +(number * _UUS_DTU * dtu_ps)


def ps_to_us(value_ps: Decimal) -> Decimal:
    """Convert canonical picoseconds to Decimal microseconds explicitly."""

    return value_ps / _PS_PER_US


@dataclass(frozen=True)
class Dw3000PacketAirtime:
    packet_name: str
    on_air_psdu_octets: int
    encoded_psdu_bits: int
    t_preamble_ps: Decimal
    t_sfd_ps: Decimal
    t_sts_ps: Decimal
    t_phr_ps: Decimal
    t_psdu_ps: Decimal
    total_ps: Decimal
    structure: tuple[str, ...]
    provenance: dict[str, Any]
    source_type: str = "SYNTHETIC"
    hardware_verified: bool = False

    @property
    def total_us(self) -> Decimal:
        return ps_to_us(self.total_ps)

    @property
    def rmarker_offset_ps(self) -> Decimal:
        # Current firmware has STS off; for that format RMARKER is at the end
        # of SHR.  STS-on RMARKER semantics remain outside the ready model.
        return self.t_preamble_ps + self.t_sfd_ps


def _time_parameter(parameter: Mapping[str, Any], name: str) -> Decimal:
    required = {
        "value",
        "unit",
        "evidence_class",
        "source",
        "locator",
        "status",
        "hardware_verified",
    }
    missing = sorted(required - set(parameter))
    if missing:
        raise PhyModelError(f"{name} missing fields: {missing}")
    if parameter["hardware_verified"] is not False:
        raise PhyModelError(f"{name}.hardware_verified must be false")
    if parameter["status"] == "UNRESOLVED" or parameter["value"] is None:
        raise PhyModelError(f"{name} is UNRESOLVED")
    value_ps = canonical_ps(parameter["value"], str(parameter["unit"]))
    if value_ps < 0:
        raise PhyModelError(f"{name} must be non-negative")
    return value_ps


def _validate_phy(config: Mapping[str, Any]) -> None:
    phy = config["phy"]
    supported = {
        "channel": 9,
        "pac_symbols": 8,
        "tx_preamble_code": 9,
        "rx_preamble_code": 9,
        "prf_mhz": 64,
        "sfd_type": "DWT_SFD_DW_8",
        "sfd_symbols": 8,
        "data_rate": "DWT_BR_6M8",
        "phr_mode": "DWT_PHRMODE_STD",
        "phr_rate": "DWT_PHRRATE_STD",
    }
    for name, expected in supported.items():
        if phy.get(name) != expected:
            raise PhyModelError(
                f"unsupported current PHY {name}: {phy.get(name)!r}; expected {expected!r}"
            )
    if phy.get("preamble_symbols") not in {128, 1024}:
        raise PhyModelError("independent regression currently supports PLEN128/PLEN1024")
    if phy.get("sts_mode") not in {
        "DWT_STS_MODE_OFF",
        "DWT_STS_MODE_1",
        "DWT_STS_MODE_2",
    }:
        raise PhyModelError(f"unsupported STS mode: {phy.get('sts_mode')!r}")


def _validate_packet(name: str, packet: Mapping[str, Any]) -> None:
    integers = (
        "driver_buffer_octets",
        "meaningful_buffer_octets",
        "driver_tx_frame_control_octets",
        "mac_header_octets",
        "function_code_octets",
        "body_octets",
        "fcs_octets",
        "on_air_psdu_octets",
    )
    for field in integers:
        value = packet.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise PhyModelError(f"packets.{name}.{field} must be a non-negative integer")
    meaningful = (
        packet["mac_header_octets"]
        + packet["function_code_octets"]
        + packet["body_octets"]
    )
    if packet["meaningful_buffer_octets"] != meaningful:
        raise PhyModelError(f"packets.{name} meaningful byte breakdown is inconsistent")
    expected_buffer = meaningful + (
        packet["fcs_octets"] if packet["buffer_includes_fcs_placeholders"] else 0
    )
    if packet["driver_buffer_octets"] != expected_buffer:
        raise PhyModelError(f"packets.{name} driver buffer/FCS convention is inconsistent")
    on_air = meaningful + packet["fcs_octets"]
    if packet["driver_tx_frame_control_octets"] != on_air:
        raise PhyModelError(f"packets.{name} TX frame-control length must include FCS")
    if packet["on_air_psdu_octets"] != on_air:
        raise PhyModelError(f"packets.{name} on-air PSDU length is inconsistent")


def calculate_dw3000_airtimes(
    config: Mapping[str, Any],
) -> dict[str, Dw3000PacketAirtime]:
    """Calculate current firmware packet airtimes without paper Table 2 inputs."""

    _validate_phy(config)
    phy = config["phy"]
    constants = config["timing_constants"]
    shr_symbol_ps = _time_parameter(constants["shr_symbol_time"], "shr_symbol_time")
    phr_symbol_ps = _time_parameter(constants["phr_symbol_time"], "phr_symbol_time")
    data_symbol_ps = _time_parameter(constants["data_symbol_time"], "data_symbol_time")
    phr_symbols = int(constants["phr_symbols"])
    rs_block_bits = int(constants["rs_data_block_bits"])
    rs_parity_bits = int(constants["rs_parity_bits_per_block"])
    if min(phr_symbols, rs_block_bits, rs_parity_bits) <= 0:
        raise PhyModelError("PHR and Reed-Solomon constants must be positive")

    sts_mode = phy["sts_mode"]
    if sts_mode == "DWT_STS_MODE_OFF":
        sts_ps = Decimal(0)
    else:
        try:
            sts_ps = _time_parameter(constants["sts_duration"], "STS duration")
        except PhyModelError as exc:
            raise PhyModelError("STS timing is UNRESOLVED for an enabled STS mode") from exc

    preamble_ps = Decimal(phy["preamble_symbols"]) * shr_symbol_ps
    sfd_ps = Decimal(phy["sfd_symbols"]) * shr_symbol_ps
    phr_ps = Decimal(phr_symbols) * phr_symbol_ps
    if sts_mode == "DWT_STS_MODE_OFF":
        structure = ("PREAMBLE", "SFD", "PHR", "PSDU")
    elif sts_mode == "DWT_STS_MODE_1":
        structure = ("PREAMBLE", "SFD", "STS", "PHR", "PSDU")
    else:
        structure = ("PREAMBLE", "SFD", "PHR", "PSDU", "STS")

    result: dict[str, Dw3000PacketAirtime] = {}
    for name, packet in config["packets"].items():
        _validate_packet(str(name), packet)
        data_bits = int(packet["on_air_psdu_octets"]) * 8
        rs_blocks = (data_bits + rs_block_bits - 1) // rs_block_bits if data_bits else 0
        encoded_bits = data_bits + rs_blocks * rs_parity_bits
        psdu_ps = Decimal(encoded_bits) * data_symbol_ps
        total = preamble_ps + sfd_ps + sts_ps + phr_ps + psdu_ps
        result[str(name)] = Dw3000PacketAirtime(
            packet_name=str(name),
            on_air_psdu_octets=int(packet["on_air_psdu_octets"]),
            encoded_psdu_bits=encoded_bits,
            t_preamble_ps=preamble_ps,
            t_sfd_ps=sfd_ps,
            t_sts_ps=sts_ps,
            t_phr_ps=phr_ps,
            t_psdu_ps=psdu_ps,
            total_ps=total,
            structure=structure,
            provenance={
                "phy": dict(config["parameter_provenance"]),
                "timing_constants": dict(constants),
                "frame": dict(packet),
            },
        )
    return result


__all__ = [
    "Dw3000PacketAirtime",
    "PhyModelError",
    "SUPPORTED_TIME_UNITS",
    "TimeUnitError",
    "calculate_dw3000_airtimes",
    "canonical_ps",
    "ps_to_us",
]
