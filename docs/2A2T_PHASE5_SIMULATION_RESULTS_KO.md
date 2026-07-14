# 2A2T Phase 5 Synthetic Simulation Results

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
총 2560개 synthetic 조합 중 182개가 non-dominated이고 4개를 실질 중복 제거 후 export했다. 목적은 period/duty/unresolved 최소화와 processing/UART/guard headroom 최대화다. 병합 signature는 period, processing headroom, UART headroom, robustness, PLEN의 완전 일치다. Balanced가 다른 성격과 같은 signature이면 별도 manifest를 만들지 않는다.

| 성격 | ID | PLEN | superframe us | complete-superframe Hz | unresolved count |
|---|---|---:|---:|---:|---:|
| fast | P5-00001 | 128 | 16014.789 | 62.442 | 1 |
| processing_robust | P5-00033 | 128 | 16814.789 | 59.471 | 1 |
| uart_safe | P5-02557 | 1024 | 43715.533 | 22.875 | 1 |
| conservative | P5-00029 | 128 | 16814.789 | 59.471 | 1 |

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
