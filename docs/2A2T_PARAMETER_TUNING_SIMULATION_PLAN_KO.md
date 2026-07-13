# 논문 기반 2A2T 파라미터 조정 시뮬레이션 구현계획

## 1. 목적과 결론

목표는 IEEE 802.15.4z/DW3000의 PHY와 packet 길이로부터 **각 packet airtime, reply delay, RX start/timeout, 4-link superframe 시간**을 계산하고, 실제 보드에 넣을 후보를 시뮬레이션으로 먼저 줄이는 것이다.

핵심 원칙은 다음과 같다.

1. 논문 수치를 firmware 상수에 바로 복사하지 않는다.
2. 논문 모델은 Python unit/golden test로만 재현하고 실제 보드 실험 단계로 두지 않는다.
3. 현재 5-packet phase DS-TWR 흐름으로 모델을 확장한다.
4. A1-T1, A2-T1, A1-T2, A2-T2를 half-duplex discrete-event scheduler로 배치한다.
5. simulation에서는 후보만 선정한다. 실제 processing time과 최종 timing은 logic analyzer/UART 측정으로 확정한다.
6. 실제 보드 실험은 처음부터 A1/A2/T1/T2 네 node와 네 link를 사용하는 2A2T로 시작한다.
7. 첫 2A2T는 충돌을 피한 4-slot sequential superframe으로 시작하고, 안정화 후에만 interleaving을 비교한다. 여기서 sequential은 2A2T 내부 slot 방식이며 1A1T/2A1T 선행 실험을 뜻하지 않는다.

Simulation output에는 항상 다음을 기록한다.

```text
source_type = SYNTHETIC
hardware_verified = false
model_basis = PAPER_GROUNDED
```

## 2. 논문 근거

### 2.1 Source locator

- 논문: 장윤석, 한수민, 장병준, “IEEE 802.15.4z UWB의 거리측정 정확도와 측정시간 최적화,” 한국전자파학회논문지, vol. 36, no. 3, pp. 274-282, 2025.
- DOI: <https://doi.org/10.5515/KJKIEES.2025.36.3.274>
- 원본 경로: `C:/Users/User/Documents/카카오톡 받은 파일/jkiees-36-3-274.pdf`
- SHA-256: `63FC732A71DDD911D8737C5384483310406305EED9CAE351CD98DB24AD3C9F75`
- 원본 PDF는 이동하거나 repository에 복사하지 않고 위 경로와 hash로 참조한다.

### 2.2 논문의 핵심 모델

논문 식 (4)-(6)은 PHY parameter와 symbol 수로 packet 구간을 계산한다.

```text
T_SHR  = SHR symbol count  x T_PSYM
T_PHR  = PHR symbol count  x T_PHRSYM
T_PSDU = PSDU symbol count x T_PSDUSYM
T_packet = T_SHR + T_PHR + T_PSDU
```

구현에서는 SHR을 preamble과 SFD로 분리하고, 향후 STS가 활성화되면 별도 `T_STS` 항을 추가한다. 논문 계산은 STS를 제외하며 현재 firmware baseline도 STS off다.

논문 278-279쪽의 timing model은 다음 경계를 사용한다.

```text
T_reply = T_P_TX + outgoing packet time
RX_START = received/sent Rmarker + T_P_RX
RX_TIMEOUT = expected incoming packet time + timeout margin
```

논문 simulation은 계산 편의를 위해 `T_P_TX = T_P_RX`로 두고, timeout margin은 100 us를 사용했다. 이 100 us는 논문 재현값이지 실제 2A2T 최종 margin이 아니다.

### 2.3 논문 golden values

표 2의 DS-TWR, preamble length 128 결과:

| Packet | T_SHR (us) | T_PHR (us) | T_PSDU (us) | Packet time (us) |
|---|---:|---:|---:|---:|
| Poll | 138.4 | 21.5 | 20.5 | 180.4 (약 181) |
| Response | 138.4 | 21.5 | 23.6 | 183.5 (약 184) |
| Final | 138.4 | 21.5 | 34.9 | 194.8 (약 195) |

그림 4의 `T_P_RX/T_P_TX = 522 us`를 적용하면:

| Parameter | 계산 | 논문 최소 후보 |
|---|---|---:|
| `T_reply1` | 522 + Response 184 | 706 us |
| `T_reply2` | 522 + Final 195 | 717 us |
| Response timeout | 184 + 100 | 284 us |
| Final timeout | 195 + 100 | 295 us |

표 3의 sweep 값:

| Preamble | T_reply1 (us) | T_reply2 (us) |
|---|---|---|
| 128 | 706, 906, 1,106, 1,306, 1,506 | 717, 917, 1,117, 1,317, 1,517 |
| 1,024 | 1,618, 1,818, 2,018, 2,218, 2,418 | 1,629, 1,829, 2,029, 2,229, 2,429 |

논문은 2 m LOS에서 처리시간을 200 us씩 증가시키며 SS-TWR variance를 비교하고, DS-TWR은 10초 동안의 ranging count를 계산값과 측정값으로 비교했다. 따라서 초기 HIL도 2 m/10초 조건을 paper-reproduction baseline으로 사용한다.

### 2.4 논문을 2A2T에 그대로 적용할 수 없는 이유

- 논문은 한 initiator와 한 responder의 2/3-packet SS/DS-TWR 모델이다.
- A1/A2/T1/T2 4-link slot 충돌, half-duplex resource contention, retry는 다루지 않는다.
- 현재 firmware는 Poll/Response/Final 뒤에 Post-Final과 Report가 있는 5-packet 흐름이다.
- 논문 packet 길이와 현재 firmware PSDU/FCS 길이가 다르다.
- 논문은 CIR read, phase processing, UART backhaul 시간을 포함하지 않는다.
- antenna delay, NLOS, phase ambiguity와 실제 packet loss 분포는 이 timing simulation으로 확정할 수 없다.

## 3. 현재 코드 baseline과 차이

현재 값은 code inspection 결과이며 실측 또는 최적값이 아니다.

| 분류 | 현재 baseline | 계획에서의 처리 |
|---|---|---|
| PHY | CH9, PLEN128, PAC8, code 9/9, 6.8 Mbps, STS off | `CODE_BASELINE` profile |
| Initiator timing | 1500, 1650, 281, 1650, 50000 UUS | paper 후보와 별도 보존 |
| Responder timing | 1650, 1500, 298, 1500, 279 UUS | paper 후보와 별도 보존 |
| Antenna delay | TX/RX 16385 | simulation 고정값이 아니라 measured calibration 대상 |
| CIR | dummy 포함 7 bytes, complex sample 1개 | processing budget에 별도 항목 |
| Phase | `phi0 + phi1 - phi2 + phi3` | timing 이후 별도 accuracy model |
| Filter | median window 20 | sweep 가능, timing/accuracy trade-off 구분 |
| Topology | TG 1개와 A1/B2 교대 | T2/4-link scheduler 신규 필요 |

현재 `hardware/mock_backend.py`의 range와 timing은 software branch test용 synthetic fixture다. 위치, packet airtime, clock drift, antenna delay 또는 collision을 계산하지 않으므로 실제 파라미터 선정 근거로 사용하지 않는다.

## 4. 구현 범위

### 4.1 신규 Python model

기존 project 구조를 유지하여 `analysis/` 아래에 구현한다.

| 신규 파일 | 책임 |
|---|---|
| `analysis/phy_airtime_model.py` | SHR/SFD/STS/PHR/PSDU airtime 계산 |
| `analysis/twr_timeline_model.py` | Rmarker, processing, delayed TX, RX window event 계산 |
| `analysis/scheduler_2a2t.py` | 4-link half-duplex superframe와 collision 검사 |
| `analysis/parameter_sweep.py` | reply/timeout/guard/slot order sweep |
| `analysis/pareto_selection.py` | update rate, latency, headroom, duty cycle Pareto selection |
| `tools/run_2a2t_parameter_simulation.py` | config validation, simulation, archive CLI |
| `tools/compare_2a2t_candidates.py` | 후보 비교 report/plot 생성 |
| `tools/export_firmware_candidate.py` | firmware를 수정하지 않고 candidate manifest/diff만 생성 |

### 4.2 Config와 schema

```text
configs/simulation_2a2t_paper_baseline.yaml
configs/simulation_2a2t_parameter_sweep.yaml
schemas/simulation_2a2t.schema.json
```

모든 parameter는 값만 저장하지 않고 provenance를 같이 기록한다.

```yaml
reply_delay_us:
  value: 706
  unit: us
  evidence_class: PAPER
  source: jkiees-36-3-274
  page: 279
  equation_or_table: Figure 4 / Table 3
  hardware_verified: false
```

허용할 `evidence_class`:

- `PAPER`: 논문 식/표/그림에서 직접 추출
- `CODE_BASELINE`: 현재 firmware static value
- `ASSUMED`: simulation을 위해 둔 가정
- `SWEEP`: 탐색 후보
- `MEASURED`: 실제 raw capture에서 계산된 값

### 4.3 Test

```text
tests/test_phy_airtime_model.py
tests/test_twr_timeline_model.py
tests/test_scheduler_2a2t.py
tests/test_parameter_sweep.py
tests/test_paper_golden_values.py
```

필수 golden test:

1. PLEN128 Poll/Response/Final이 180.4/183.5/194.8 us와 허용오차 내 일치한다.
2. `T_P_TX=522 us`에서 reply1/reply2가 706/717 us로 계산된다.
3. timeout margin 100 us에서 284/295 us가 계산된다.
4. 표 3의 PLEN128/1024 sweep과 simulated cycle count가 재현된다.
5. 같은 node의 TX/RX overlap 또는 두 송신의 동일 receiver 충돌을 반드시 FAIL 처리한다.

## 5. 2A2T timing model

### 5.1 Link와 node resource

첫 구현의 link는 다음 네 개로 고정한다.

```text
A1-T1
A2-T1
A1-T2
A2-T2
```

각 node는 half-duplex resource로 모델링한다. 한 node에서 같은 시간에 두 TX/RX event가 겹치면 invalid schedule이다. 동일 채널에서 한 receiver의 RX window에 둘 이상의 TX가 겹쳐도 collision으로 판정한다.

### 5.2 Packet sequence

두 sequence를 분리한다.

1. `PAPER_DS_3_PACKET`: Poll -> Response -> Final
2. `CURRENT_PHASE_DS_5_PACKET`: Poll -> Response -> Final -> Post-Final -> Report

논문 재현은 3-packet으로 수행하고, 실제 후보 생성은 현재 packet byte/FCS convention을 반영한 5-packet model로 수행한다.

### 5.3 Hard constraints

```text
reply_delay >= measured_or_assumed_p99_processing + outgoing_airtime_component + guard
rx_timeout >= incoming_packet_airtime + clock_margin + detection_margin
superframe_period >= sum(slot_occupancy) + inter_slot_guards
UART_required_bps <= measured_sustainable_UART_bps
node_TX_RX_overlap = 0
receiver_collision = 0
```

실제 측정 전 `p99_processing`은 `ASSUMED`이므로 최종 timing으로 승격하지 않는다.

### 5.4 Sweep parameter

우선순위 1 - scheduling/time:

- PLEN: 128, 1,024 paper reproduction; 이후 256/512 추가
- `reply1`, `reply2`
- Post-Final/Report delay
- RX-after-TX delay와 RX timeout
- inter-slot guard, inter-link guard, superframe period
- 4-link slot order
- retry/backoff policy

우선순위 2 - processing/logging:

- CIR read on/off
- phase processing on/off
- UART binary record 크기와 flush policy
- median window

우선순위 3 - 실제 측정 후 추가:

- oscillator offset distribution
- measured packet loss/late-TX probability
- measured IRQ/SPI/CIR/phase/UART duration distribution
- temperature, orientation, LOS/NLOS condition

### 5.5 Objective와 출력 metric

하나의 임의 score로 합치기보다 Pareto 후보를 만든다.

- complete 4-link superframe rate
- link별 update rate
- mean/p95/p99 superframe latency
- minimum/percentile processing headroom
- timeout/retry 예상 횟수
- node별 TX/RX duty cycle
- UART throughput/headroom
- collision/overlap count
- paper baseline 대비 cycle time 감소율

Range bias/RMSE는 timing simulation의 1차 목적함수로 사용하지 않는다. 실제 ground truth와 raw range를 확보한 뒤 measured metric으로 결합한다.

## 6. 구현 단계와 완료조건

### Phase 0 - source/baseline freeze

- PDF path/hash와 논문 표/식 locator 저장
- 현재 firmware timing/PHY/packet length snapshot 저장
- `PAPER`, `CODE_BASELINE`, `ASSUMED`, `SWEEP` 값 분리

완료조건: 논문값과 firmware값이 같은 field에 덮어써지지 않는다.

### Phase 1 - packet airtime calculator

- PHY symbol duration과 coding에 따른 packet time 계산
- paper Table 1/2 golden test
- 현재 Poll/Response/Final/Post-Final/Report byte 길이 입력

완료조건: paper PLEN128 packet time이 허용오차 내 재현된다.

### Phase 2 - single-link timeline reproduction

- Rmarker 기준 event timeline 생성
- `T_P_TX/T_P_RX`, delayed TX, RX start/end, timeout 구현
- Figure 3/4와 Table 3 재현

완료조건: 706/717 us, 284/295 us 및 PLEN1024 table 값 재현.

### Phase 3 - 2A2T scheduler

- A1/A2/T1/T2 half-duplex resource 구현
- sequential 4-link superframe 구현
- collision/overlap/late-TX constraint 구현
- tag-major와 anchor-major slot order 비교

완료조건: 네 link가 누락 없이 완료되고 모든 node overlap이 0인 schedule 생성.

### Phase 4 - sweep/Pareto/report

- 논문 Table 3과 current 1500/1650 UUS 주변 후보 sweep
- complete-superframe rate, latency, headroom, duty 비교
- candidate manifest와 Markdown/CSV/SVG report 생성

완료조건: 실제 HIL로 넘길 후보 3-5개와 탈락 이유가 재현 가능하게 기록됨.

### Phase 5 - current mock runner integration

- 기존 deterministic fault injection과 scheduler output 연결
- config/source/firmware candidate hash snapshot
- `source_type=SYNTHETIC`, `hardware_verified=false` 강제

완료조건: one-command simulation과 report가 hardware 없이 통과.

### Phase 6 - HIL candidate export

- firmware source를 자동 수정하지 않음
- node별 target timing, register/API call, expected delta를 manifest로 출력
- unresolved measured input이 있으면 export 중단

완료조건: 사용자가 review할 수 있는 candidate diff plan만 생성.

## 7. 실제 실험으로 넘기는 순서

### 7.1 새 experiment folder

새 규칙에 맞춰 다음처럼 만든다.

```text
results/2026-07-13_python_2A2T-paper-baseline_parameter-sweep_run01/
results/YYYY-MM-DD_DWS3000_2A2T-conservative_timing-smoke_runNN/
results/YYYY-MM-DD_DWS3000_2A2T-sequential_parameter-sweep_runNN/
results/YYYY-MM-DD_DWS3000_2A2T-sequential_robustness_runNN/
```

각 실험 시작 전에 반드시 준비한다.

```text
question.md
protocol.md
run_matrix.md
metadata.yaml
```

실행 후 다음 순서로 채운다.

```text
run_log.md
qc.md
analysis_environment.md
results/validation.md
closeout.md
```

### 7.2 실제 실험 시작점 - direct 2A2T

실제 실험은 처음부터 네 board를 모두 사용한다.

- A1/A2/T1/T2 고유 address와 role을 firmware에 구현
- A1-T1, A2-T1, A1-T2, A2-T2 네 link를 한 superframe에 포함
- 모든 record에 `boot_id/superframe_id/frame_id/slot_id/link_id/node_id` 포함
- packet stage별 late-TX, timeout, retry, RX error와 이전 값 재사용 여부 기록
- 네 link의 ground-truth distance를 각각 독립 측정하여 metadata에 기록
- raw UART 4개와 logic analyzer capture를 동일 run에 보존

첫 scheduler는 다음과 같은 4-slot 2A2T다.

```text
SUPERFRAME N
  SLOT 0: A1-T1
  SLOT 1: A2-T1
  SLOT 2: A1-T2
  SLOT 3: A2-T2
```

이 방식은 네 link가 모두 활성인 2A2T다. 단지 같은 node의 TX/RX overlap과 receiver collision을 피하기 위해 link를 시간 slot으로 분리한다.

### 7.3 Stage A - direct 2A2T conservative smoke

- PLEN128, current 5-packet sequence 사용
- 실제 5-packet airtime calculator가 만든 값 중 headroom이 가장 큰 후보 사용
- 현재 1500/1650 UUS code baseline도 비교용 profile로 유지
- 4/4 link가 같은 superframe에서 완료되어야 success
- 한 link라도 late TX/timeout/identity mismatch가 발생하면 run은 partial/FAIL로 기록
- 실제 처리시간이 없으면 delay를 줄이지 않고 logic/UART raw를 먼저 수집

완료조건:

```text
complete_4_link_superframe > 0
node_TX_RX_overlap = 0
receiver_collision = 0
identity_mismatch = 0
raw_capture_present = true
```

성공률 threshold는 논문에 제시되지 않았으므로 `protocol.md`에서 별도 승인값으로 정한다.

### 7.4 Stage B - direct 2A2T parameter sweep

논문 Table 3의 값은 3-packet single-link golden seed로만 사용한다. 실제 sweep 값은 current 5-packet airtime과 2A2T measured processing p99를 반영하여 다시 계산한다.

```text
reply_candidate = packet_time_component + measured_processing_p99 + guard
timeout_candidate = incoming_packet_time + measured_clock_margin + detection_margin
```

Sweep 방식:

- 네 link에 같은 timing profile을 적용한 global sweep부터 시작
- 큰 delay/guard에서 작은 값 방향으로 진행
- 설정당 10초 count와 최소 3 repeat run을 기록
- complete 4-link superframe rate, link별 update rate, p95/p99 latency, retry/timeout을 비교
- current 1500/1650 UUS profile을 항상 baseline으로 포함
- 논문 PLEN128과 PLEN1024 profile을 비교하되, 실제 packet length로 재계산된 후보만 firmware에 적용

Paper Table 3의 탐색 순서는 model regression에서 다음과 같이 유지한다.

PLEN128 seed:

```text
(1506,1517) -> (1306,1317) -> (1106,1117) -> (906,917) -> (706,717) us
```

PLEN1024 seed:

```text
(2418,2429) -> (2218,2229) -> (2018,2029) -> (1818,1829) -> (1618,1629) us
```

각 단계에서 late TX, timeout, missing frame 또는 raw corruption이 증가하면 더 작은 delay로 진행하지 않는다.

### 7.5 Stage C - direct 2A2T robustness

- 선택된 Pareto 후보 3-5개만 반복
- 네 link ground truth와 raw/phase-corrected range 동시 기록
- CIR/phase on/off, UART 부하, retry 조건 비교
- anchor/tag 배치와 LOS/NLOS 조건을 바꾸어 변동성 기록
- complete 4-link superframe만 success로 계산
- 한 link의 previous value를 현재 success로 재분류하지 않음

### 7.6 Stage D - optional 2A2T interleaving

4-slot sequential 2A2T가 반복 run에서 qc-passed 이상일 때만 진행한다. node half-duplex와 동일 receiver collision constraint를 만족하는 경우에만 interleaving 후보를 허용한다. 이 단계도 네 node와 네 link를 유지한다.

## 8. 실제 측정에서 필요한 값

| 값 | 획득 방법 | simulation 사용처 |
|---|---|---|
| node별 `T_P_TX`, `T_P_RX` | GPIO/logic analyzer | reply lower bound |
| IRQ/ISR latency p99 | IRQ pin + ISR trace | processing budget |
| SPI status/frame/CIR p99 | trace GPIO/SPI probe | processing budget |
| phase/filter p99 | trace GPIO/software timestamp | processing budget |
| UART sustainable throughput/drop | 4-port raw capture | superframe/report rate constraint |
| actual packet success/timeout/retry | structured UART record | probability model |
| actual clock offset | DW diagnostic/timestamp analysis | RX window margin |
| ground-truth distance/uncertainty | 독립 측정 | bias/RMSE validation |
| antenna orientation/height/environment | metadata/photo | repeatability/condition grouping |

## 9. 승격 기준

결과 상태는 다음 순서로만 올린다.

```text
raw-only -> qc-passed -> processed -> exploratory -> reproducible -> verified -> reported
```

- Simulation 결과는 최대 `reproducible` 후보이며 hardware `verified`가 아니다.
- 실제 timing candidate의 `verified` 승격에는 반복 run, current baseline, p95/p99 또는 변동성, ground truth 유무와 한계가 필요하다.
- antenna delay는 별도 multi-distance calibration과 validation을 통과해야 한다.
- 최종 firmware 상수는 candidate manifest와 실제 measured report가 모두 연결된 경우에만 변경한다.

## 10. 검증된 결과

- 논문은 PHY/packet length에 따라 packet time과 최소 reply/timeout을 계산해야 한다는 방법을 제시한다.
- 논문 PLEN128 DS-TWR packet time은 Poll/Response/Final 약 181/184/195 us다.
- 논문 그림의 522 us processing assumption에서 reply1/reply2 최소 후보는 706/717 us다.
- 현재 repository의 mock timing/range는 논문 기반 physical/protocol simulator가 아니다.
- 현재 firmware baseline은 실제 2A2T가 아니라 한 tag와 두 anchor를 교대하는 2A1T 계열이다.

## 11. 가정한 값

- 논문 reproduction에서는 논문과 같이 `T_P_TX=T_P_RX=522 us`, timeout margin 100 us를 사용한다.
- 실제 실험의 초기 down-sweep 순서는 안전한 큰 delay에서 작은 delay 방향으로 한다.
- 실제 HIL 후보 개수 3-5개와 repeat 3회는 초기 계획값이며 protocol 승인 시 확정한다.
- 첫 2A2T mode는 collision-free sequential scheduling으로 가정한다.

## 12. 논문 기반 근거

- 식 (3): DS-TWR의 clock offset 완화 ToF 식
- 식 (4)-(6): SHR/PHR/PSDU packet-time 구성
- 표 2: PLEN128 DS-TWR Poll/Response/Final packet time
- 그림 3/4: packet time을 고려한 RX start/timeout/reply timing
- 그림 5: SS-TWR reply 증가에 따른 2 m 거리분산 경향
- 표 3/그림 6: PLEN128/1024 reply sweep과 10초 ranging count

## 13. 추후 확인 필요

- paper packet-time 수식의 coding/detail을 IEEE 802.15.4z와 사용 중인 DW3000 API version에 맞춰 교차검증
- 현재 Response/FCS 길이 convention 불일치 해결
- actual Post-Final/Report packet airtime 계산
- clean full SDK의 target/build command 확보
- A1/A2/T1/T2 addressing, scheduler와 structured identity record 구현
- actual `T_P_TX/T_P_RX`, IRQ/SPI/CIR/phase/UART p99 측정
- final timeout margin, clock drift/detection margin의 실제 근거
- ground truth와 antenna-delay calibration 분리 수행
