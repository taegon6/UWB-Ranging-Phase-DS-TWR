"""Report, plot, and Phase 6 manifest output for synthetic Phase 5 runs."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


def _plots(run_dir: Path, rows: Sequence[Mapping[str, Any]], front: Sequence[Mapping[str, Any]], selected: Sequence[Mapping[str, Any]]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = run_dir / "results" / "graphs"; out.mkdir(parents=True, exist_ok=True)
    def save(name: str) -> None:
        plt.figtext(0.01, 0.01, "source_type=SYNTHETIC | hardware_verified=false | assumed/code-inspection", fontsize=7)
        plt.tight_layout(rect=(0, .04, 1, 1)); plt.savefig(out / f"{name}.svg"); plt.savefig(out / f"{name}.png", dpi=150); plt.close()
    current = selected[0]["packet_airtime_us"]
    plt.figure(); plt.bar(["Paper Poll", "Paper Resp", "Paper Final", "Current Poll", "Current Resp", "Current Final", "PostFinal", "Report"], [1323,1323,1493]+[float(current[k]) for k in ("Poll","Response","Final","PostFinal","Report")]); plt.xticks(rotation=35, ha="right"); plt.ylabel("airtime (us)"); save("paper_vs_current_packet_airtime")
    subset = sorted(rows, key=lambda r: Decimal(r["transition_delay_ps"]["PostFinal->Report"]))
    plt.figure(); plt.scatter([float(Decimal(r["transition_delay_ps"]["PostFinal->Report"])/Decimal(1e6)) for r in subset], [float(r["complete_superframe_rate_hz"]) for r in subset], s=5); plt.xlabel("PostFinal→Report Rmarker delay (us)"); plt.ylabel("complete-superframe rate (Hz)"); save("superframe_rate_vs_report_transition_delay")
    plt.figure(); plt.scatter([float(Decimal(r["inter_slot_headroom_ps"])/Decimal(1e6)) for r in rows], [float(r["complete_superframe_rate_hz"]) for r in rows], s=5); plt.xlabel("inter-slot guard (us)"); plt.ylabel("complete-superframe rate (Hz)"); save("superframe_rate_vs_inter_slot_guard")
    plt.figure(); plt.scatter([float(r["latency_mean_us"]) for r in rows], [float(Decimal(r["processing_headroom_ps"])/Decimal(1e6)) for r in rows], s=4, alpha=.3, label="valid synthetic"); plt.scatter([float(r["latency_mean_us"]) for r in selected], [float(Decimal(r["processing_headroom_ps"])/Decimal(1e6)) for r in selected], marker="*", s=90, label="HIL candidates"); plt.xlabel("mean synthetic latency (us)"); plt.ylabel("processing headroom (us)"); plt.legend(); save("latency_vs_processing_headroom_pareto")
    labels=[r["hil_label"] for r in selected]; nodes=("A1","A2","T1","T2"); x=range(len(labels)); width=.08
    plt.figure();
    series=[(n,"TX","node_tx_duty_cycle") for n in nodes]+[(n,"RX","node_rx_duty_cycle") for n in nodes]
    for i,(n,mode,key) in enumerate(series): plt.bar([v+(i-3.5)*width for v in x], [float(r[key][n]) for r in selected], width, label=f"{n} {mode}")
    plt.xticks(list(x), labels, rotation=25); plt.ylabel("node duty cycle"); plt.legend(ncol=4, fontsize=6); save("candidate_node_duty_cycle")
    plt.figure(); plt.bar(labels,[float(r["uart_sustainable_bps"]) for r in selected],label="assumed sustainable"); plt.bar(labels,[float(r["uart_required_bps"]) for r in selected],label="required synthetic"); plt.xticks(rotation=25); plt.ylabel("bit/s"); plt.legend(); save("candidate_uart_headroom")
    best=selected[0]; plt.figure(); plt.bar(["legacy C0003",best["hil_label"]],[12353.856,float(best["superframe_period_us"])]); plt.ylabel("superframe period (us)"); save("legacy_vs_corrected_result")
    balanced=next((r for r in selected if r["hil_label"]=="balanced"), selected[0]); plt.figure(figsize=(10,3)); colors={"A1-T1":"C0","A2-T1":"C1","A1-T2":"C2","A2-T2":"C3"};
    for event in balanced["events"]: plt.barh(event["sender"], float((Decimal(event["end_ps"])-Decimal(event["start_ps"]))/Decimal(1e6)), left=float(Decimal(event["start_ps"])/Decimal(1e6)), color=colors[event["link"]], alpha=.8)
    plt.xlabel("synthetic timeline (us)"); save("sequential_superframe_timeline")
    scenarios=sorted(set(r["scenario"] for r in rows)); plt.figure(); plt.boxplot([[float(r["complete_superframe_rate_hz"]) for r in rows if r["scenario"]==s] for s in scenarios], tick_labels=scenarios); plt.ylabel("complete-superframe rate (Hz)"); plt.xticks(rotation=20); save("scenario_sensitivity")


def _manifest(row: Mapping[str, Any], summary: Mapping[str, Any]) -> dict[str, Any]:
    p=row["parameters"]
    return {"schema_version":1,"candidate_id":row["candidate_id"],"label":row["hil_label"],"source_commit":"2b2b6ed73b3fd0dd49023208904449a6725784b4","config_hash":summary["sweep_config_hash"],"source_type":"SYNTHETIC","hardware_verified":False,"phy_profile":{"preamble_symbols":row["preamble_symbols"],"sts_mode":"DWT_STS_MODE_OFF"},"packet_definitions":row["packet_airtime_us"],"node_timing_parameters":{"all_links":"sequential identical timing"},"reply_delay":{"Poll->Response_ps":row["transition_delay_ps"]["Poll->Response"],"Response->Final_ps":row["transition_delay_ps"]["Response->Final"]},"rx_after_tx_delay":{"status":"UNRESOLVED","hardware_verified":False},"rx_timeout_margin_us":p["timeout_margin_us"],"final_postfinal_delay_uus":p["final_postfinal_delay_uus"],"postfinal_report_assumed_delay_ps":row["transition_delay_ps"]["PostFinal->Report"],"inter_slot_guard_us":p["inter_slot_guard_us"],"superframe_period_us":row["superframe_period_us"],"expected_synthetic_rate_hz":row["complete_superframe_rate_hz"],"assumptions_and_provenance":row["parameter_provenance"],"unresolved":["measured PostFinal-to-Report processing","RX enable/startup timing","UART sustainable throughput","Response FCS on-air confirmation"],"firmware_application_targets":["dwt_setdelayedtrxtime","dwt_setrxaftertxdelay","dwt_setrxtimeout","FINAL_TX_TO_POST_FINAL_TX_DLY_UUS"],"pre_apply_checks":["confirm units UUS vs dtu","confirm Rmarker reference","confirm 4 board role mapping","capture baseline constants"],"rollback_values":{"action":"restore recorded pre-apply constants; no automatic patch is provided"}}


def _report(selected: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    rows="\n".join(f"| {r['hil_label']} | {r['candidate_id']} | {r['preamble_symbols']} | {Decimal(r['superframe_period_us']):.3f} | {Decimal(r['complete_superframe_rate_hz']):.3f} | {r['unresolved_assumption_count']} |" for r in selected)
    return f"""# 2A2T Phase 5 Synthetic Simulation Results

`source_type = SYNTHETIC`  
`hardware_verified = false`

## 1. 연구 목적
Independent Qorvo DW3000 PHY airtime을 current Poll/Response/Final/PostFinal/Report와 직접 연결하고, sequential A1-T1/A2-T1/A1-T2/A2-T2 후보를 HIL 전달용으로 좁혔다. 실제 DW3000 성능 측정 결과가 아니다.

## 2. 논문 모델 재현 결과
Paper 3-packet 값은 regression comparison 전용이며 current 계산 입력으로 사용하지 않았다. Legacy C0003의 12,353.856 us 및 80.946 Hz도 목표값으로 사용하지 않았다.

## 3. Independent PHY 모델
PLEN128 current airtime은 Poll 178.39836, Response 179.42404, Final 200.96332, PostFinal 178.39836, Report 182.50108 us이다. STS는 OFF다.

| 구분 | Poll | Response | Final | PostFinal | Report |
|---|---:|---:|---:|---:|---:|
| paper regression (us) | 1323 | 1323 | 1493 | N/A | N/A |
| current independent PLEN128 (us) | 178.39836 | 179.42404 | 200.96332 | 178.39836 | 182.50108 |

## 4. Current 5-packet 확장 및 FCS convention
| Packet | meaningful buffer | driver buffer | FCS | on-air PSDU |
|---|---:|---:|---:|---:|
| Poll | 10 | 10 | driver appends 2 | 12 |
| Response | 11 | 13 | 2 placeholders; on-air confirmation unresolved | 13 |
| Final | 32 | 32 | driver appends 2 | 34 |
| PostFinal | 10 | 10 | driver appends 2 | 12 |
| Report | 14 | 14 | driver appends 2 | 16 |

| Transition | sender→receiver | Rmarker delay policy |
|---|---|---|
| Poll→Response | anchor→tag response | remote processing + Response airtime + guard |
| Response→Final | tag→anchor final | remote processing + Final airtime + guard |
| Final→PostFinal | same tag delayed TX | CODE_BASELINE 1650 UUS |
| PostFinal→Report | anchor→tag report | assumed processing + Report airtime + guard |

## 5. Sequential scheduler와 hard constraint
네 link를 고정 순서로 배치했다. TX/RX overlap, double TX, double RX, receiver collision 및 incomplete superframe은 허용하지 않는다. 모든 계산은 Decimal picosecond다.

## 6. Sweep 범위와 provenance
PLEN128/1024, remote reply guard 0/200 us, report processing 522(PAPER sensitivity only), 2000(ASSUMED_CODE_PROXY), 800/1500/3000 us(ASSUMED), report guard 0/200 us, timeout 100/300 us, inter-slot/superframe guard 0/200 us, CIR/phase off/on, UART 64/256 octets를 coarse sweep했다. 범위는 실측치가 아니라 최소·보수 경계 민감도 비교용이다.

## 7. 결과와 Pareto
총 {summary['candidate_count']}개 synthetic 조합 중 {summary['pareto_count']}개가 non-dominated이고 {summary['selected_count']}개를 실질 중복 제거 후 export했다. 목적은 period/duty/unresolved 최소화와 processing/UART/guard headroom 최대화다. 병합 signature는 period, processing headroom, UART headroom, robustness, PLEN의 완전 일치다. Balanced가 다른 성격과 같은 signature이면 별도 manifest를 만들지 않는다.

| 성격 | ID | PLEN | superframe us | complete-superframe Hz | unresolved count |
|---|---|---:|---:|---:|---:|
{rows}

## 8. 그래프
`results/graphs/`에 요구된 9개 그래프의 SVG/PNG가 있다. 모든 그림은 synthetic/assumed/code-inspection 상태를 표시한다.

## 9. Legacy C0003 비교
Legacy 12,353.856 us/80.946 Hz는 paper-grounded hardcoded airtime 경로 결과다. Corrected 모델은 current five-packet independent airtime, 독립 Final→PostFinal 및 PostFinal→Report 정책, superframe guard와 UART/CIR 시나리오를 사용하므로 직접 수치가 달라진다. C0003 ID 자체는 새 Pareto 순위에 유지하지 않았다.

## 10. 가정·unresolved 영향
| 항목 | 상태 | 영향 |
|---|---|---|
| PostFinal→Report processing | ASSUMED/PAPER sensitivity/CODE proxy | rate와 processing headroom |
| Response FCS on-air convention | unresolved confirmation | Response airtime |
| RX-after-TX/startup | UNRESOLVED | timeout feasibility |
| UART sustainable throughput | ASSUMED | UART-safe 판정 |
| CIR/phase processing | unmeasured | processing delay와 UART load |

## 11. 실제 실험 검증 가설과 한계
Conservative 후보가 4/4 link를 완료하고 timeout/late-TX 없이 동작하는지, 예측 period와 측정 period의 오차, UART drop을 검증한다. 전파, oscillator, firmware scheduling jitter, 실제 processing 및 RF collision을 합성 모델은 증명하지 못한다. Antenna delay와 range accuracy는 목적함수에서 제외했다.

## 12. Phase 6 전달 조건과 판정
Firmware 자동 patch 없이 manifest만 제공한다. 실제 processing과 RX timing이 미측정이므로 판정은 **PHASE6_CANDIDATES_CONDITIONAL**이다.
"""


def _plan() -> str:
    return """# 2A2T Phase 6 Hardware Experiment Plan

`source_type = SYNTHETIC`  
`hardware_verified = false`

## 사전 조건
A1/A2/T1/T2 역할·serial/J-Link ID, firmware commit, UART baud/format, logic channel mapping, 공급전압, 위치·방향을 기록한다. Antenna-delay calibration은 별도 accuracy 실험으로 둔다.

## Stage A — Conservative smoke test
가장 보수적인 manifest를 수동 적용한다. 4/4 link complete, node identity, timeout/late-TX/RX error를 확인하고 UART 4개를 동시에 원본 저장한다. 가능하면 logic analyzer도 원본으로 보존한다. 실패 시 즉시 rollback한다.

## Stage B — Candidate comparison
후보당 10초, 최소 3회, 같은 위치/PHY로 수행한다. complete superframe, link success, timeout, late TX, retry, UART drop, measured period를 저장한다. Fake measurement를 만들지 않는다.

## Stage C — Robustness
CIR/phase on/off, UART load, LOS, 보드 방향을 바꾸며 반복한다. 각 변경은 독립 run으로 기록한다.

## 비교 및 승인
예측/측정 superframe period·rate·link update rate, timeout/late-TX rate, UART drop, 반복 변동성, model error percent를 비교한다. HIL 결과 전까지 어떤 후보도 hardware verified가 아니다.
"""


def write_phase5_outputs(run_dir: Path, phy: Mapping[str, Any], sweep: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], front: Sequence[Mapping[str, Any]], selected: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> None:
    docs=run_dir/"docs"; docs.mkdir()
    (docs/"2A2T_PHASE5_SIMULATION_RESULTS_KO.md").write_text(_report(selected,summary),encoding="utf-8")
    (docs/"2A2T_PHASE6_HARDWARE_EXPERIMENT_PLAN_KO.md").write_text(_plan(),encoding="utf-8")
    out=run_dir/"artifacts"/"hil_candidates"; out.mkdir(parents=True)
    for row in selected: (out/f"{row['hil_label']}.yaml").write_text(yaml.safe_dump(_manifest(row,summary),allow_unicode=True,sort_keys=False),encoding="utf-8")
    _plots(run_dir,rows,front,selected)


__all__=["write_phase5_outputs"]
