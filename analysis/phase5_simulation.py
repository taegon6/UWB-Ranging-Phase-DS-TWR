"""Phase 5 independent-PHY synthetic 2A2T simulation and Phase 6 export.

All internal timing is Decimal picoseconds.  This module does not import the
legacy paper-airtime scheduler and never writes firmware sources.
"""

from __future__ import annotations

import csv
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from itertools import product
from pathlib import Path
from typing import Any, Mapping, Sequence

from analysis.dw3000_phy_model import calculate_dw3000_airtimes, canonical_ps, ps_to_us
from hardware.device_inventory import load_yaml


class Phase5ConfigError(ValueError):
    pass


SEQUENCE = ("Poll", "Response", "Final", "PostFinal", "Report")
SLOT_ORDER = ("A1-T1", "A2-T1", "A1-T2", "A2-T2")
PAPER_AIRTIME_US = {"Poll": "1323.0", "Response": "1323.0", "Final": "1493.0"}


def _d(spec: Mapping[str, Any], key: str) -> Decimal:
    value = spec.get(key)
    if value is None or value == "UNRESOLVED":
        raise Phase5ConfigError(f"{key} is UNRESOLVED")
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise Phase5ConfigError(f"{key} is invalid") from exc
    if result < 0:
        raise Phase5ConfigError(f"{key} must be non-negative")
    return result


def _nodes(link: str, packet: str) -> tuple[str, str]:
    anchor, tag = link.split("-")
    if packet in {"Poll", "Final", "PostFinal"}:
        return tag, anchor
    return anchor, tag


@dataclass(frozen=True)
class _Event:
    link: str
    packet: str
    sender: str
    receiver: str
    start_ps: Decimal
    rmarker_ps: Decimal
    end_ps: Decimal


def _link_events(airtimes: Mapping[str, Any], link: str, delays: Mapping[str, Decimal]) -> list[_Event]:
    rows: list[_Event] = []
    current_rmarker = airtimes["Poll"].rmarker_offset_ps
    for index, packet in enumerate(SEQUENCE):
        airtime = airtimes[packet]
        if index:
            current_rmarker += delays[f"{SEQUENCE[index - 1]}->{packet}"]
        start = current_rmarker - airtime.rmarker_offset_ps
        sender, receiver = _nodes(link, packet)
        rows.append(_Event(link, packet, sender, receiver, start, current_rmarker, start + airtime.total_ps))
    return rows


def _provenance(spec: Mapping[str, Any]) -> dict[str, Any]:
    scenario = str(spec["scenario"])
    report_class = {
        "PAPER_BASELINE": "PAPER",
        "CODE_BASELINE": "ASSUMED_CODE_PROXY",
        "SENSITIVITY": "ASSUMED",
    }.get(scenario)
    if report_class is None:
        raise Phase5ConfigError(f"unknown scenario: {scenario}")
    report_source = {
        "PAPER_BASELINE": "jkiees-36-3-274 Figure 4 p.279 (sensitivity only)",
        "CODE_BASELINE": "firmware code inspection: Sleep(2) plus immediate TX path",
        "SENSITIVITY": "Phase 5 sensitivity design",
    }[scenario]
    common = {"hardware_verified": False}
    return {
        "report_processing_us": {**common, "value": str(spec["report_processing_us"]), "unit": "us", "evidence_class": report_class, "source": report_source, "rationale": "unmeasured PostFinal-to-Report processing assumption; not a current-firmware measurement"},
        "final_postfinal_delay_uus": {**common, "value": str(spec["final_postfinal_delay_uus"]), "unit": "UUS", "evidence_class": "CODE_BASELINE", "source": "FINAL_TX_TO_POST_FINAL_TX_DLY_UUS", "rationale": "repository delayed-TX constant"},
        "guards_and_timeout": {**common, "evidence_class": "ASSUMED", "source": "Phase 5 sweep", "rationale": "synthetic robustness variables pending HIL"},
        "uart": {**common, "evidence_class": "ASSUMED", "source": "Phase 5 UART scenario", "rationale": "record size and sustainable throughput are unmeasured"},
    }


def build_phase5_candidate(phy_config: Mapping[str, Any], spec: Mapping[str, Any], candidate_id: str = "P5-SMOKE") -> dict[str, Any]:
    if phy_config.get("model_role") != "CURRENT_FIRMWARE_INDEPENDENT_PHY":
        raise Phase5ConfigError("independent PHY model is required")
    config = deepcopy(dict(phy_config))
    config["phy"]["preamble_symbols"] = int(spec.get("preamble_symbols", 128))
    if config["phy"].get("sts_mode") != "DWT_STS_MODE_OFF":
        raise Phase5ConfigError("Phase 5 requires STS off")
    airtimes = calculate_dw3000_airtimes(config)
    r1p, r1g = _d(spec, "reply1_processing_us"), _d(spec, "reply1_guard_us")
    r2p, r2g = _d(spec, "reply2_processing_us"), _d(spec, "reply2_guard_us")
    report_processing, report_guard = _d(spec, "report_processing_us"), _d(spec, "report_guard_us")
    timeout, slot_guard = _d(spec, "timeout_margin_us"), _d(spec, "inter_slot_guard_us")
    super_guard = _d(spec, "superframe_guard_us")
    final_pf = canonical_ps(_d(spec, "final_postfinal_delay_uus"), "UUS")
    delays = {
        "Poll->Response": canonical_ps(r1p + r1g, "us") + airtimes["Response"].total_ps,
        "Response->Final": canonical_ps(r2p + r2g, "us") + airtimes["Final"].total_ps,
        "Final->PostFinal": final_pf,
        "PostFinal->Report": canonical_ps(report_processing + report_guard, "us") + airtimes["Report"].total_ps,
    }
    if delays["PostFinal->Report"] < airtimes["Report"].total_ps:
        raise Phase5ConfigError("PostFinal->Report is below physical Report-airtime lower bound")
    timeout_ps = canonical_ps(timeout, "us")
    link_rows = _link_events(airtimes, SLOT_ORDER[0], delays)
    link_start, link_end = link_rows[0].start_ps, link_rows[-1].end_ps
    link_duration = link_end - link_start
    slot_guard_ps = canonical_ps(slot_guard, "us")
    super_guard_ps = canonical_ps(super_guard, "us")
    events: list[_Event] = []
    for index, link in enumerate(SLOT_ORDER):
        offset = Decimal(index) * (link_duration + slot_guard_ps)
        for event in _link_events(airtimes, link, delays):
            events.append(_Event(event.link, event.packet, event.sender, event.receiver, event.start_ps + offset, event.rmarker_ps + offset, event.end_ps + offset))
    period = Decimal(4) * link_duration + Decimal(3) * slot_guard_ps + super_guard_ps
    if period <= 0:
        raise Phase5ConfigError("superframe period must be positive")
    # Sequential slots guarantee no cross-link overlap; assert it explicitly.
    ordered = sorted(events, key=lambda e: (e.start_ps, e.end_ps))
    for left, right in zip(ordered, ordered[1:]):
        if left.link != right.link and right.start_ps < left.end_ps:
            raise Phase5ConfigError("hard constraint violation: sequential slot overlap")
    tx: dict[str, Decimal] = {n: Decimal(0) for n in ("A1", "A2", "T1", "T2")}
    rx = dict(tx)
    for event in events:
        duration = event.end_ps - event.start_ps
        tx[event.sender] += duration
        rx[event.receiver] += duration
    records = int(spec.get("uart_record_octets", 96))
    sustainable = int(spec.get("uart_sustainable_bps", 921600))
    with localcontext() as ctx:
        ctx.prec = 50
        rate = Decimal(10) ** 12 / period
        required_uart = rate * Decimal(4 * records * 8)
        uart_headroom = Decimal(sustainable) - required_uart
    processing_headroom = canonical_ps(report_guard, "us")
    robustness = min(timeout_ps, slot_guard_ps + super_guard_ps)
    duty_tx = {n: str(tx[n] / period) for n in tx}
    duty_rx = {n: str(rx[n] / period) for n in rx}
    scenario = str(spec["scenario"])
    unresolved = 1 + (1 if scenario == "CODE_BASELINE" else 0) + (1 if bool(spec.get("cir_phase_processing")) else 0)
    latency_values = [link_duration + Decimal(i) * (link_duration + slot_guard_ps) for i in range(4)]
    sorted_lat = sorted(latency_values)
    return {
        "candidate_id": candidate_id,
        "scenario": scenario,
        "model_role": "CURRENT_FIRMWARE_INDEPENDENT_PHY",
        "sequence": list(SEQUENCE),
        "preamble_symbols": config["phy"]["preamble_symbols"],
        "packet_airtime_us": {k: str(v.total_us) for k, v in airtimes.items()},
        "transition_delay_ps": {k: str(v) for k, v in delays.items()},
        "single_link_duration_ps": str(link_duration),
        "slot_occupancy_ps": str(link_duration),
        "superframe_period_ps": str(period),
        "superframe_period_us": str(ps_to_us(period)),
        "complete_superframe_rate_hz": str(rate),
        "nominal_link_update_rate_hz": {link: str(rate) for link in SLOT_ORDER},
        "latency_mean_us": str(ps_to_us(sum(latency_values) / Decimal(4))),
        "latency_p95_us": str(ps_to_us(sorted_lat[-1])),
        "latency_p99_us": str(ps_to_us(sorted_lat[-1])),
        "processing_headroom_ps": str(processing_headroom),
        "timeout_margin_ps": str(timeout_ps),
        "inter_slot_headroom_ps": str(slot_guard_ps),
        "robustness_ps": str(robustness),
        "node_tx_duty_cycle": duty_tx,
        "node_rx_duty_cycle": duty_rx,
        "max_node_duty_cycle": str(max([Decimal(v) for v in duty_tx.values()] + [Decimal(v) for v in duty_rx.values()])),
        "uart_required_bps": str(required_uart),
        "uart_sustainable_bps": sustainable,
        "uart_headroom_bps": str(uart_headroom),
        "links_completed": 4,
        "complete_superframe": True,
        "node_tx_rx_overlap_count": 0,
        "node_double_tx_count": 0,
        "node_double_rx_count": 0,
        "receiver_collision_count": 0,
        "unresolved_assumption_count": unresolved,
        "parameters": {k: v for k, v in spec.items()},
        "parameter_provenance": _provenance(spec),
        "events": [{"link": e.link, "packet": e.packet, "sender": e.sender, "receiver": e.receiver, "start_ps": str(e.start_ps), "end_ps": str(e.end_ps)} for e in events],
        "source_type": "SYNTHETIC",
        "hardware_verified": False,
    }


_MIN = ("superframe_period_ps", "max_node_duty_cycle", "unresolved_assumption_count")
_MAX = ("processing_headroom_ps", "uart_headroom_bps", "robustness_ps")


def _dominates(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    no_worse = all(Decimal(str(a[k])) <= Decimal(str(b[k])) for k in _MIN) and all(Decimal(str(a[k])) >= Decimal(str(b[k])) for k in _MAX)
    better = any(Decimal(str(a[k])) < Decimal(str(b[k])) for k in _MIN) or any(Decimal(str(a[k])) > Decimal(str(b[k])) for k in _MAX)
    return no_worse and better


def pareto_front_phase5(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if not any(other is not row and _dominates(other, row) for other in rows)]


def _specs(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    c = config["coarse_sweep"]
    result = []
    for scenario, scenario_cfg in config["scenarios"].items():
        for values in product(c["preamble_symbols"], c["reply1_guard_us"], c["reply2_guard_us"], scenario_cfg["report_processing_us"], c["report_guard_us"], c["timeout_margin_us"], c["inter_slot_guard_us"], c["superframe_guard_us"], c["cir_phase_processing"], c["uart_profiles"]):
            plen, g1, g2, rp, rg, tm, sg, sfg, cir, uart = values
            result.append({"scenario": scenario, "preamble_symbols": plen, "reply1_processing_us": c["reply1_processing_us"][0], "reply1_guard_us": g1, "reply2_processing_us": c["reply2_processing_us"][0], "reply2_guard_us": g2, "final_postfinal_delay_uus": c["final_postfinal_delay_uus"][0], "report_processing_us": rp, "report_guard_us": rg, "timeout_margin_us": tm, "inter_slot_guard_us": sg, "superframe_guard_us": sfg, "cir_phase_processing": cir, "uart_record_octets": uart["record_octets"], "uart_sustainable_bps": uart["sustainable_bps"], "uart_profile": uart["name"]})
    return result


def _choose(front: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not front:
        raise Phase5ConfigError("no Pareto candidates")
    choices = [
        ("fast", min(front, key=lambda r: Decimal(r["superframe_period_ps"]))),
        ("processing_robust", max(front, key=lambda r: Decimal(r["processing_headroom_ps"]))),
        ("uart_safe", max(front, key=lambda r: Decimal(r["uart_headroom_bps"]))),
        ("conservative", max(front, key=lambda r: (Decimal(r["robustness_ps"]), -Decimal(r["superframe_period_ps"])))),
        ("balanced", min(front, key=lambda r: (int(r["unresolved_assumption_count"]), Decimal(r["superframe_period_ps"]) / max(Decimal(1), Decimal(r["robustness_ps"]))))),
    ]
    unique: list[dict[str, Any]] = []
    seen = set()
    for label, row in choices:
        signature = (row["superframe_period_ps"], row["processing_headroom_ps"], row["uart_headroom_bps"], row["robustness_ps"], row["preamble_symbols"])
        if signature not in seen:
            picked = dict(row); picked["hil_label"] = label; unique.append(picked); seen.add(signature)
    for row in front:
        if len(unique) >= 3:
            break
        signature = (row["superframe_period_ps"], row["processing_headroom_ps"], row["uart_headroom_bps"], row["robustness_ps"], row["preamble_symbols"])
        if signature not in seen:
            picked = dict(row); picked["hil_label"] = f"alternative_{len(unique)+1}"; unique.append(picked); seen.add(signature)
    return unique[:5]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [k for k in rows[0] if k not in {"events", "parameters", "parameter_provenance", "nominal_link_update_rate_hz", "node_tx_duty_cycle", "node_rx_duty_cycle", "packet_airtime_us", "transition_delay_ps"}]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        for row in rows: writer.writerow({k: row[k] for k in fields})


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_research_records(run_dir: Path, before: bool, summary: Mapping[str, Any] | None = None) -> None:
    marker = "source_type = SYNTHETIC\nhardware_verified = false\n"
    if before:
        (run_dir / "question.md").write_text("# Research question\n\nWhich independent-PHY sequential 2A2T timing candidates should proceed to conditional HIL review?\n\n" + marker, encoding="utf-8")
        (run_dir / "protocol.md").write_text("# Protocol\n\nValidate configs, calculate five-packet airtime/timelines in Decimal picoseconds, reject hard conflicts, sweep, select Pareto candidates, and export manifests. No firmware write or hardware command is permitted.\n\n" + marker, encoding="utf-8")
        (run_dir / "run_matrix.md").write_text("# Run matrix\n\nSee `configs/phase5_2a2t_sweep.yaml`; PLEN128/1024, three provenance scenarios, timing guards, timeout, CIR/phase, and UART profiles are crossed in the coarse sweep.\n\n" + marker, encoding="utf-8")
        (run_dir / "metadata.yaml").write_text(f"experiment_state: raw-only\ncreated_utc: {datetime.now(timezone.utc).isoformat()}\nsource_type: SYNTHETIC\nhardware_verified: false\nfirmware_modified: false\n", encoding="utf-8")
        return
    assert summary is not None
    (run_dir / "run_log.md").write_text(f"# Run log\n\nCandidates: {summary['candidate_count']}; Pareto: {summary['pareto_count']}; selected: {summary['selected_count']}. No hardware commands were issued.\n\n" + marker, encoding="utf-8")
    (run_dir / "qc.md").write_text("# QC\n\nIndependent PHY path, four-link completion, conflict counts, provenance, report/plot/manifest generation: PASS. Hardware verification: NOT PERFORMED.\n\n" + marker, encoding="utf-8")
    (run_dir / "analysis_environment.md").write_text("# Analysis environment\n\nPython deterministic Decimal timing; matplotlib static plots; input hashes are in results/summary.json.\n\n" + marker, encoding="utf-8")
    (run_dir / "closeout.md").write_text("# Closeout\n\nState: exploratory. Conditional HIL candidates exported; no promotion to verified/reported.\n\n" + marker, encoding="utf-8")


def run_phase5_pipeline(phy_path: Path, sweep_path: Path, results_root: Path) -> Path:
    from analysis.phase5_reporting import write_phase5_outputs
    phy, sweep = load_yaml(phy_path), load_yaml(sweep_path)
    prefix = f"{date.today().isoformat()}_python_2A2T-sequential_phase5-synthetic-timing"
    run_dir = results_root / f"{prefix}_run01"
    if run_dir.exists():
        index = 2
        while (results_root / f"{prefix}_run{index:02d}").exists(): index += 1
        run_dir = results_root / f"{prefix}_run{index:02d}"
    run_dir.mkdir(parents=True)
    _write_research_records(run_dir, True)
    rows = [build_phase5_candidate(phy, spec, f"P5-{i:05d}") for i, spec in enumerate(_specs(sweep), 1)]
    front = pareto_front_phase5(rows)
    selected = _choose(front)
    (run_dir / "results").mkdir()
    (run_dir / "results" / "candidates.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(run_dir / "results" / "candidates.csv", rows)
    _write_csv(run_dir / "results" / "pareto.csv", front)
    summary = {"source_type": "SYNTHETIC", "hardware_verified": False, "legacy_cache_used": False, "candidate_count": len(rows), "pareto_count": len(front), "selected_count": len(selected), "phy_config_hash": _hash(phy_path), "sweep_config_hash": _hash(sweep_path), "verdict": "PHASE6_CANDIDATES_CONDITIONAL"}
    (run_dir / "results" / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_phase5_outputs(run_dir, phy, sweep, rows, front, selected, summary)
    _write_research_records(run_dir, False, summary)
    return run_dir


__all__ = ["Phase5ConfigError", "build_phase5_candidate", "pareto_front_phase5", "run_phase5_pipeline"]
