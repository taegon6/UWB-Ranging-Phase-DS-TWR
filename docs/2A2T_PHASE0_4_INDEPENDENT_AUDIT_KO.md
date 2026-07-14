# 2A2T Phase 0~4 독립 감사 보고서

## 1. 감사 범위와 결론

- 감사 기준 브랜치: `codex/pre-hardware-2a2t-foundation`
- 감사 기준 커밋: `f8e6410b80ee8d5ffeb8224c8b42b0ba6c9a52a7`
- 논문: 장윤석 외, 「IEEE 802.15.4z UWB의 거리측정 정확도와 측정시간 최적화」, 2025
- PDF SHA-256: `63FC732A71DDD911D8737C5384483310406305EED9CAE351CD98DB24AD3C9F75`
- 검토 방법: 계획-코드-설정-테스트 정적 추적, 논문 276~280쪽 식/표/그림 대조, adversarial test, 독립 수기 계산, firmware hash 재검증

최종 Phase 5 판정은 **NO-GO**다. Phase 0~4의 software skeleton과 hard-fail 기본 동작은 존재하지만, PHY golden 검증이 독립적이지 않고, Phase 4 sweep이 계획에 명시된 CODE_BASELINE timing과 주요 파라미터를 포함하지 않으며, Pareto front가 후보를 실질적으로 축소하지 못한다. 두 개의 구현 결함은 실패 테스트를 먼저 추가한 후 최소 수정했지만 나머지 Major 항목은 측정 또는 모델 정의 결정 없이 수정할 수 없어 남겨 두었다.

```text
source_type = CODE_INSPECTION
hardware_verified = false
```

이 보고서는 DW3000 실측, 실제 2A2T 통신, logic analyzer capture 또는 antenna-delay calibration 완료를 의미하지 않는다.

## 2. 요구사항 추적표

| ID | 계획/감사 요구사항 | 근거 파일 | 실제 확인 결과 | 상태 |
|---|---|---|---|---|
| P0-1 | 논문 source와 hash 동결 | `artifacts/simulation_2a2t_source_manifest.json`, baseline config | PDF hash와 원본 경로가 기록됨 | PASS |
| P0-2 | firmware baseline 동결 | source manifest, firmware 4개 파일 | manifest hash, 현재 hash, `b8b911f..f8e6410` diff가 모두 일치/없음 | PASS |
| P0-3 | PAPER와 CODE_BASELINE 분리 | `simulation_2a2t_paper_baseline.yaml` | `paper_profiles`와 `code_baseline_profiles`가 분리되고 sweep도 입력을 변경하지 않음 | PASS |
| P0-4 | parameter provenance | schema, baseline/sweep config, candidate rows | 입력 및 파생 reply/RX lead에 source/locator/evidence/hardware status 존재 | PASS |
| P1-1 | SHR/SFD/STS/PHR/PSDU airtime 계산 | `analysis/phy_airtime_model.py` | 산술 구성은 구현됨. 단, PHR은 직접 시간, PSDU coding/FCS는 역산 fixture에 의존 | PARTIAL |
| P1-2 | PLEN128 Table 2 golden 재현 | `tests/test_paper_golden_values.py` | 수치는 재현하지만 입력도 같은 표에서 역산되어 독립 검증이 아님 | PARTIAL |
| P1-3 | STS-off | baseline line의 `sts_symbols=0`, firmware `DWT_STS_MODE_OFF` | airtime에서 STS 0 us로 처리 | PASS |
| P1-4 | 단위 안전성 | provenance parameter와 계산 코드 | `f8e6410`은 잘못된 단위를 허용함. 실패 테스트 후 exact unit 검사를 추가 | FIXED |
| P2-1 | paper 3-packet 재현 | paper profile + golden timeline test | Poll/Response/Final만 사용하고 706/717 us 재현 | PASS |
| P2-2 | current 5-packet 분리 | sweep protocol + code profile | Poll/Response/Final/PostFinal/Report를 별도 profile/sequence로 사용 | PASS |
| P2-3 | Rmarker/packet boundary | `analysis/twr_timeline_model.py` | Rmarker는 SHR+STS 끝, packet start/end에는 전체 airtime 반영 | PASS |
| P2-4 | delayed TX/RX start/timeout | timeline model | paper minimum 조건은 재현. 긴 reply의 RX start는 `timeout_margin/2` lead라는 ASSUMED 확장 | PARTIAL |
| P3-1 | 네 node half-duplex | scheduler + adversarial tests | actual packet과 성공 경로 RX 대기 구간을 검사하도록 수정 | FIXED |
| P3-2 | receiver collision hard-fail | scheduler tests | 서로 다른 tag가 같은 anchor에 송신하면 `RECEIVER_COLLISION` | PASS |
| P3-3 | TX/RX, TX/TX, RX/RX hard-fail | 기존/추가 tests | 네 경우 모두 `ScheduleConflictError`로 실패 | PASS |
| P3-4 | slot 경계 | 추가 tests | 정확히 맞닿으면 허용, 0.5 us 중첩은 실패 | PASS |
| P3-5 | slot order 비교 | 계획 Phase 3 | 한 가지 순서만 고정되어 비교 없음 | FAIL |
| P4-1 | parameter sweep | `simulation_2a2t_parameter_sweep.yaml` | 1×2×5×2×2=40 조합은 생성되나 계획 파라미터 다수가 고정/누락 | PARTIAL |
| P4-2 | CODE_BASELINE 주변 sweep | plan Phase 4, baseline timing | 1650/2522 UUS와 firmware timeout 값이 sweep에 사용되지 않음 | FAIL |
| P4-3 | Pareto selection | `analysis/pareto_selection.py` | dominance 산술은 맞지만 rate/duty 목적의 구조적 상충으로 축소 기능이 약함 | PARTIAL |
| P4-4 | report와 provenance | Phase 4 runner | synthetic report/CSV/JSON 생성, 실제 성능으로 표시하지 않음 | PASS |
| G-1 | golden test 우선 및 기존 assertion 유지 | Git diff/test history | 기존 test 삭제/완화 없음. 감사 수정도 실패 test 2개를 먼저 확인 | PASS |
| G-2 | Phase 5/6 미구현 | config gate | `implemented_through=4`, Phase 5/6 false | PASS |
| G-3 | firmware source 미수정 | Git diff/hash | 감사 전후 firmware source diff 없음 | PASS |

## 3. 발견 사항

| 등급 | ID | 발견 사항 | 영향 | 처리 |
|---|---|---|---|---|
| Critical | - | 발견 없음 | - | - |
| Major | M-01 | PHY golden fixture가 Table 2의 `138.4`, `20.5/23.6/34.9 us`를 이용해 symbol time, coded-bit time, PSDU octet을 역산한다. | production에 packet별 golden 상수가 직접 하드코딩되지는 않았지만 같은 결과에서 만든 입력으로 같은 결과를 검증하므로 IEEE/DW3000 PHY의 독립 검증이 아니다. | 미수정. 표준 또는 Qorvo 공식 airtime 식과 독립 frame definition 필요 |
| Major | M-02 | PHR은 `21.5 us` 직접 입력이고 PSDU는 `(octets*8+48)*coded_bit_time` 단일 식이다. FCS 포함 여부와 RS/convolutional coding symbol 계산이 명시적으로 검증되지 않는다. | 실제 frame airtime이 달라질 수 있다. 특히 Response의 FCS convention이 baseline locator에도 unresolved로 표시됨 | 미수정. 근거 없는 값 변경 금지 |
| Major | M-03 | Phase 4 sweep은 CODE_BASELINE의 1650/2522 UUS, packet별 timeout, PLEN1024, alternative slot order를 사용하지 않는다. | 계획의 “paper Table 3과 current timing 주변 후보”를 실제로 탐색하지 않으며 UUS-us 차이도 반영하지 않는다. | 미수정. sweep 설계 재승인 필요 |
| Major | M-04 | `f8e6410` scheduler는 packet airtime만 node activity로 사용하고 packet 도착 전 RX-on 구간을 무시했다. | RX 대기 중 동일 node TX가 허용되어 half-duplex false negative 발생 | 실패 test 후 최소 수정 완료 |
| Major | M-05 | Pareto의 rate 최대화와 duty 최소화가 거의 정확한 역관계다. | 원본 20개 front는 “좋은 20개”가 아니라 목적함수 구조상 서로 지배할 수 없는 20개다. RX waiting을 duty에 반영하면 40개 모두 front가 되어 자동 축소 기능이 사실상 사라짐 | 미수정. 목적함수/제약식 재정의 필요 |
| Major | M-06 | 모든 transition에 하나의 processing과 reply guard 식을 적용한다. `Final->PostFinal`은 동일 tag의 연속 TX인데 paper의 receive-process-reply 모델을 그대로 적용한다. | 5-packet extension timing의 물리적 의미가 검증되지 않음 | 미수정. 실제 firmware state timing 또는 instrumentation 필요 |
| Major | M-07 | UART throughput/drop과 retry/backoff/packet-loss가 candidate 계산에 없다. | C0003을 포함한 rate는 이상적인 무손실·무병목 값이다. | 미수정. 측정 전 `MEASURED` 사용 금지 |
| Minor | m-01 | `f8e6410`은 parameter의 unit 문자열 존재만 검사했다. | `ms/symbol`도 `us/symbol`로 해석될 수 있음 | 실패 test 후 exact unit 검사 추가 |
| Minor | m-02 | `protocol.transitions`와 `protocol.links`는 계산에서 직접 소비되지 않고 packet direction은 코드 상수로 결정된다. | config와 실제 실행이 불일치해도 일부 오류를 놓칠 수 있음 | 미수정 |
| Minor | m-03 | receiver collision은 anchor receiver만 별도 분류하며 tag의 동시 RX는 node overlap으로 분류한다. | hard-fail은 되지만 오류 taxonomy가 비대칭 | 기존 contract와 충돌하므로 미수정 |
| Minor | m-04 | overlap 비교에 `1e-9 us` tolerance가 있다. | 1 ns보다 작은 수치 중첩은 맞닿음으로 처리된다. 현재 요구한 sub-us 0.5 us는 정상 실패 | 미수정 |
| Minor | m-05 | C instrumentation compile test 1개가 compiler 미탐지로 skip된다. | static text contract는 통과하지만 enabled/disabled C build와 실행 경로가 이번 환경에서 검증되지 않음 | 환경 제한, 아래 9절 참조 |
| Observation | O-01 | paper 3-packet과 current 5-packet은 config namespace와 test sequence에서 분리되어 있다. | paper 값이 PostFinal/Report 값으로 직접 복사되지는 않음 | 확인 |
| Observation | O-02 | production airtime 함수는 packet 이름별 golden 값을 반환하지 않는다. | component를 변경하면 계산 결과도 해당 단위만큼 변함 | adversarial test로 확인 |
| Observation | O-03 | 원본 Pareto 20개에는 exact metric duplicate가 없다. | 다만 slot guard만 다른 10개 pair는 실질적으로 같은 timing family다. | 확인 |
| Observation | O-04 | 모든 결과는 `SYNTHETIC`, `hardware_verified=false`로 표시된다. | 실제 DW3000 성능으로 해석할 수 없음 | 확인 |

## 4. PHY airtime 감사

### 4.1 구현된 산식

```text
SHR = (preamble_symbols + sfd_symbols) * preamble_symbol_time_us
STS = sts_symbols * preamble_symbol_time_us
PSDU = (psdu_octets * 8 + rs_parity_bits) * coded_bit_time_us
TOTAL = SHR + STS + PHR + PSDU
```

PLEN128 paper fixture에서는 `(128+8)×1.017647...=138.4 us`, STS는 0, PHR은 21.5 us다. 논문 276쪽은 SFD가 8 또는 64 symbols이고 STS를 설명에서 제외한다고 밝히며, 279쪽 Table 2는 SHR 138.4 us, PHR 21.5 us를 제시한다. 따라서 현재 fixture는 해당 표와 수치상 일치한다.

그러나 다음은 독립 검증되지 않았다.

- 1.017647... us/symbol은 `138.4/136`으로 Table 2에서 역산했다.
- 0.128205... us/bit와 14/17/28 octet도 Table 2 PSDU 결과를 맞추도록 구성했다.
- 48 parity bits의 적용 범위와 RS block/coding 세부를 공식 표준 식으로 교차검증하지 않았다.
- PHR symbol count와 PHR symbol duration을 계산하지 않고 21.5 us를 직접 입력한다.
- code profile의 Poll/Final/PostFinal/Report 길이는 firmware TX frame control상 FCS 포함으로 보이나 Response는 `sizeof(tx_resp_msg)`만 전달하여 convention이 명확하지 않다.

따라서 golden test는 regression fixture로는 유효하지만 “실제 DW3000 airtime이 맞다”는 증거는 아니다.

### 4.2 단위

감사 수정 후 active airtime/sweep 입력은 다음 exact unit을 요구한다.

| 값 | 요구 unit |
|---|---|
| preamble/SFD/STS | `symbol` |
| preamble symbol time | `us/symbol` |
| PHR time | `us` |
| coded bit time | `us/bit` |
| parity | `bit` |
| PSDU | `octet` |
| sweep processing/guard/timeout | `us` |

CODE_BASELINE timing에 기록된 `UUS`는 sweep에서 사용되지 않으며 실제 us로 변환되지도 않는다.

## 5. 3-packet과 5-packet 분리

| 구분 | profile | sequence | 사용 위치 |
|---|---|---|---|
| 논문 재현 | `paper_plen128`, `paper_plen1024` | Poll, Response, Final | golden test |
| 현재 후보 모델 | `code_baseline_plen128` | Poll, Response, Final, PostFinal, Report | parameter sweep |

분리는 실제로 존재한다. 다만 5-packet 흐름의 PostFinal/Report PHY timing은 paper가 제시한 것이 아니며, paper processing 식을 모든 transition에 일반화한 synthetic extension이다.

## 6. Rmarker, delayed TX, RX boundary

| 항목 | 구현 기준 | 감사 결과 |
|---|---|---|
| 첫 Rmarker | packet start + SHR + STS | SFD/SHR 끝 기준으로 일관됨 |
| 다음 Rmarker | 이전 Rmarker + reply delay | 706/717 등 Rmarker-to-Rmarker delta 재현 |
| packet start | Rmarker - SHR - STS | full packet 시작 복원 |
| packet end | start + total airtime | SHR/STS/PHR/PSDU 모두 포함 |
| minimum reply | processing + ceil(outgoing total) | paper Figure 4 산술과 일치 |
| RX ready | 이전 Rmarker + processing | paper minimum 조건에서 사용 |
| deferred RX | max(RX ready, packet start - timeout/2) | 긴 reply에서만 적용되는 ASSUMED 모델 |
| RX timeout | RX start + ceil(packet total) + margin | 전체 incoming packet airtime 포함 |

paper는 “송신된 메시지 Rmarker + `T_P_RX`”를 RX start로 설명한다. 현재 긴 reply 후보에서 RX start를 뒤로 미루는 acquisition lead 모델은 논문값이 아니며 hardware-verified가 아니다. DW3000 delayed-TX quantization, propagation delay, clock drift와 실제 preamble acquisition 조건도 없다.

## 7. Scheduler adversarial 감사

| 사례 | 기대 | 결과 |
|---|---|---|
| 서로 다른 tag -> 동일 anchor 동시 송신 | `RECEIVER_COLLISION` | PASS |
| 동일 node TX와 RX 중첩 | hard-fail | PASS |
| 동일 node 이중 TX | hard-fail | PASS |
| 동일 node 이중 RX | hard-fail | PASS |
| RX waiting 중 동일 node TX | hard-fail | `f8e6410` FAIL, 최소 수정 후 PASS |
| slot end == 다음 slot start | 허용 | PASS |
| 0.5 us overlap | hard-fail | PASS |

수정 후 성공 경로의 RX node activity는 RX start부터 expected packet end까지 점유한다. packet loss 시 timeout end까지의 점유와 retry schedule은 Phase 4에 없으므로 별도 미검증 항목이다.

## 8. Sweep 40개와 Pareto 20개 분석

### 8.1 조합 수

```text
profile            1  (code_baseline_plen128)
processing         2  (522, 800 us)
reply guard         5  (0, 100, 200, 400, 800 us)
timeout margin      2  (100, 200 us)
slot guard          2  (100, 300 us)
--------------------------------------------
total = 1 * 2 * 5 * 2 * 2 = 40
```

누락 또는 고정된 parameter:

- PLEN1024와 기타 PHY profile
- packet별/transition별 processing 및 guard
- firmware CODE_BASELINE 1650/2522 UUS reply delay
- firmware packet별 RX timeout 281/298/279/50000 UUS
- alternative slot order
- separate clock/detection margin
- delayed-TX quantization
- UART payload/baud/queue/drop/flush constraint
- retry/backoff/packet loss/late-TX probability
- CIR/phase/filter 처리 부하
- propagation, antenna delay, oscillator offset

### 8.2 `f8e6410`에서 20개가 Pareto가 된 이유

원본 구현에서 RX waiting은 duty에 포함되지 않았다. 따라서 같은 processing/reply/slot 조합의 timeout 100과 200 후보는 rate와 duty가 같고 timeout headroom만 200이 더 컸다. timeout 100 후보 20개가 정확히 지배되어 제거되고 timeout 200 후보 20개가 남았다.

남은 후보에서는 packet airtime 총합이 고정되어 다음 관계가 형성된다.

```text
superframe_rate ∝ 1 / superframe_duration
max_packet_duty ∝ 1 / superframe_duration
```

rate는 최대화하고 duty는 최소화하므로 duration이 짧은 후보는 rate가 좋지만 duty가 나쁘고, 긴 후보는 그 반대다. 이 때문에 서로를 지배하기 어렵다. 즉 20개라는 수는 강한 후보 선별 결과가 아니라 목적함수의 구조적 상충 결과다.

exact metric duplicate는 없었다. 다만 다음 pair는 processing/reply/timeout이 같고 slot guard만 100/300 us로 다르므로 같은 timing family다.

```text
C0003/C0004, C0007/C0008, C0011/C0012, C0015/C0016, C0019/C0020
C0023/C0024, C0027/C0028, C0031/C0032, C0035/C0036, C0039/C0040
```

RX waiting을 duty에 포함한 감사 수정 후에는 timeout 200 후보가 더 긴 RX-on duty를 가져 timeout 100 후보를 더 이상 지배하지 못하며 40개 모두 Pareto가 된다. 이는 dominance 코드 오류가 아니라 목적함수/제약 정의가 후보 축소에 부적합하다는 증거다.

### 8.3 수작업 dominance 검증

작은 4-row dataset에서 한 후보가 rate, reply/timeout headroom, duty 모두 no-worse이고 하나 이상 better일 때만 다른 후보를 제거함을 추가 test로 확인했다. invalid superframe도 front에서 제외된다. dominance 구현 자체는 의도한 비교 규칙과 일치한다.

## 9. C0003 독립 계산

### 9.1 입력

| parameter | 값 | provenance/status |
|---|---:|---|
| profile | `code_baseline_plen128` | CODE_BASELINE frame length + paper-derived PHY |
| processing | 522 us | PAPER, single-link Figure 4; hardware 미측정 |
| reply guard | 0 us | SWEEP, lower-bound |
| timeout margin | 200 us | SWEEP |
| RX acquisition lead | 100 us | ASSUMED = timeout/2 |
| slot guard | 100 us | ASSUMED |
| links/order | A1-T1, A2-T1, A1-T2, A2-T2 | fixed synthetic schedule |

### 9.2 packet airtime과 reply

공통 SHR는 `(128+8)×1.017647...=138.4 us`, PHR은 21.5 us, parity는 48 bits다.

| outgoing packet | PSDU octet | PSDU 계산 (us) | total (us) | ceil(total) | reply = 522+ceil+0 (us) |
|---|---:|---:|---:|---:|---:|
| Response | 13 | `(13×8+48)×0.128205...=19.487179` | 179.387179 | 180 | 702 |
| Final | 34 | `(34×8+48)×0.128205...=41.025641` | 200.925641 | 201 | 723 |
| PostFinal | 12 | `(12×8+48)×0.128205...=18.461538` | 178.361538 | 179 | 701 |
| Report | 16 | `(16×8+48)×0.128205...=22.564103` | 182.464103 | 183 | 705 |

### 9.3 link와 superframe

동일 PHY SHR를 사용하므로 첫 Poll Rmarker offset과 마지막 Report Rmarker offset이 상쇄된다.

```text
reply sum = 702 + 723 + 701 + 705
          = 2,831 us

one-link duration = reply sum + Report total
                  = 2,831 + 182.464102564
                  = 3,013.464102564 us

complete-superframe duration
    = 4 * one-link duration + 3 * slot_guard
    = 4 * 3,013.464102564 + 3 * 100
    = 12,353.856410256 us

complete-superframe rate
    = 1,000,000 / 12,353.856410256
    = 80.946383606 Hz
```

따라서 원본 보고서의 `12,353.856 us`, `80.946 Hz` 산술은 재현된다.

`80.946 Hz`는 **complete 4-link superframe rate**다. 각 link가 superframe마다 한 번 성공한다고 가정하면 개별 link update rate도 각각 80.946 Hz다. 네 link result를 합산한 이상적 aggregate completion rate는 약 `323.786 link-results/s`지만 production output의 `superframe_rate_hz`가 뜻하는 값은 아니다.

### 9.4 C0003의 미측정 가정

- 522 us가 A1/A2/T1/T2와 네 transition 모두에 동일하다는 가정
- reply guard 0 us에서도 late TX가 없다는 가정
- timeout margin 200 us 및 acquisition lead 100 us가 충분하다는 가정
- slot guard 100 us가 clock drift와 scheduling jitter를 흡수한다는 가정
- UART throughput, queue, serialization, flush, drop이 rate를 제한하지 않는다는 가정
- retry/backoff가 없고 모든 packet이 첫 시도에 성공한다는 가정
- packet loss, CRC/RX error, NLOS와 receiver desense가 없다는 가정
- delayed-TX quantization과 UUS-us 차이가 없다는 가정
- CIR read, phase/filter 및 SPI/IRQ 처리 부하가 522 us에 포함된다는 가정
- PostFinal/Report에 paper processing 식을 그대로 적용할 수 있다는 가정
- propagation delay와 antenna delay가 schedule duration에 유의미하지 않다는 가정

어느 것도 이번 감사에서 `MEASURED`로 승격하지 않았다.

## 10. HIL 전 검토 대상 4개

아래는 firmware 적용 승인 목록이 아니라, 측정값을 얻은 뒤 재검토할 representative family다. slot guard 300 pair와 guard 800 extreme은 우선 제외했다.

| 후보 | processing | reply guard | timeout | slot guard | 원본 modeled rate | 검토 목적 |
|---|---:|---:|---:|---:|---:|---|
| C0007 | 522 | 100 | 200 | 100 | 71.665 Hz | paper processing + 최소 비영(非零) reply guard |
| C0011 | 522 | 200 | 200 | 100 | 64.293 Hz | Table 3 step-scale guard |
| C0027 | 800 | 100 | 200 | 100 | 54.342 Hz | 보수적 processing + 작은 guard |
| C0035 | 800 | 400 | 200 | 100 | 43.100 Hz | 보수적 processing/guard stress |

C0003은 reply headroom 0 us인 mathematical boundary라 connection smoke 후보가 아니라 simulator boundary control로만 유지한다.

## 11. 추가/수정 테스트와 최소 수정

### 추가 테스트

`tests/test_phase0_4_independent_audit.py`:

- dimensionally wrong unit hard-fail
- component perturbation으로 packet-name golden hardcoding 부재 확인
- paper 3-packet / code 5-packet 분리
- Rmarker, packet start/end, RX start/end 기준
- delayed RX waiting half-duplex occupancy
- 동일 node double TX
- 동일 node double RX
- 동일 anchor receiver collision
- exact boundary touch
- 0.5 us overlap
- hand-checked Pareto dataset
- 40-combination cardinality와 C0003 독립 산술

기존 테스트는 삭제하지 않았고 assertion도 완화하지 않았다.

### 최소 수정

- `analysis/phy_airtime_model.py`: active parameter exact-unit 검사
- `analysis/parameter_sweep.py`: sweep dimension의 `us` 검사
- `analysis/scheduler_2a2t.py`: successful RX waiting interval을 node half-duplex activity에 포함

firmware source, PAPER 값, CODE_BASELINE 값은 수정하지 않았다.

## 12. pytest 전후 결과와 skipped test

| 시점 | 결과 |
|---|---|
| 감사 수정 전 `f8e6410` | `79 passed, 1 skipped` |
| adversarial test 최초 실행 | `8 passed, 2 failed` - unit과 RX-window 결함 재현 |
| 최소 수정 후 전체 suite | `91 passed, 1 skipped` |

Skipped test:

```text
tests/test_instrumentation_contract.py::
InstrumentationContractTests::test_sources_compile_when_c_compiler_is_available
```

이유는 PATH에서 `gcc`, `clang`, `cl`을 찾지 못했기 때문이다. 현재 위험은 `trace_gpio.c`와 `timing_probe.c`가 trace disabled, GPIO enabled, software timestamp enabled 조합에서 실제 C compiler로 warning-free build되고 test executable이 정상 종료하는지 확인하지 못했다는 것이다. 정적 event ID, disabled macro, forbidden call contract test는 통과했다.

## 13. firmware와 baseline 무결성

| 파일 | manifest SHA-256 | 현재 결과 |
|---|---|---|
| `ds_twr_initiator_final.c` | `bb0dafc5...d0ab389` | MATCH |
| `ds_twr_responder_final.c` | `d0a63c48...8a417d4` | MATCH |
| `shared_function_jang.c` | `e9773891...0a9943` | MATCH |
| `shared_function_jang.h` | `8b665b3b...736894` | MATCH |

`b8b911f6...f8e6410` 구간의 `firmware_overlay/` diff는 없고, 감사 작업 후에도 `firmware_overlay/` 및 `firmware/` diff는 없다.

## 14. Phase 5 gate

```text
PHASE 5 DECISION = NO-GO
```

재판정 최소 조건:

1. IEEE/Qorvo 공식 근거에서 독립적으로 계산한 PHR/PSDU/FCS airtime fixture를 추가한다.
2. CODE_BASELINE UUS timing과 current 1650/2522/timeout 값을 명시적으로 sweep baseline에 포함한다.
3. UART와 retry를 objective 또는 hard constraint에서 어떻게 취급할지 정의한다.
4. Pareto에서 rate-duty 역관계를 해소할 제약/목적을 정하고 3~5개로 축소되는 근거를 test한다.
5. Final-to-PostFinal을 포함한 transition별 processing 의미를 정의한다.
6. C instrumentation compile skip을 해소한다.

실제 hardware 측정 전에는 processing, timeout, UART, retry, antenna delay 또는 update rate를 `MEASURED`로 표시하면 안 된다.
