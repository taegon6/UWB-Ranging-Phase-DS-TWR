# 2A2T Phase 0~4 구현 및 실험 전환 가이드

## 현재 구현 상태

이 구현은 논문 기반 timing 모델을 현재 5-packet 흐름으로 확장하여 A1/A2/T1/T2 네 링크를 한 superframe 안에서 직접 계산한다. 실제 보드, UART, J-Link, logic analyzer는 사용하지 않았으며 firmware source도 수정하지 않았다.

```text
source_type = SYNTHETIC
hardware_verified = false
```

구현 범위는 Phase 0~4뿐이다. Phase 5 mock-runner 통합과 Phase 6 firmware candidate export는 설정에서 비활성화되어 있고, 앞 단계 테스트가 통과하더라도 이번 작업에서는 실행하지 않는다.

## 무엇을 만들었는가

| Phase | 파일 | 역할 |
|---|---|---|
| 0 | `configs/simulation_2a2t_paper_baseline.yaml` | 논문값과 CODE_BASELINE 값을 별도 namespace로 동결 |
| 0 | `artifacts/simulation_2a2t_source_manifest.json` | 논문 PDF와 firmware baseline hash 기록 |
| 0 | `schemas/simulation_2a2t.schema.json` | 값, 단위, evidence class, source locator, 검증 상태 강제 |
| 1 | `analysis/phy_airtime_model.py` | SHR/STS/PHR/PSDU와 packet airtime 계산 |
| 2 | `analysis/twr_timeline_model.py` | Rmarker, reply delay, delayed RX, timeout window 계산 |
| 3 | `analysis/scheduler_2a2t.py` | 네 링크 half-duplex sequential superframe 구성 및 충돌 검사 |
| 4 | `analysis/parameter_sweep.py` | processing/reply/timeout/slot guard 조합 탐색 |
| 4 | `analysis/pareto_selection.py` | rate, headroom, duty cycle 기준 Pareto 후보 선택 |
| 4 | `tools/run_2a2t_parameter_simulation.py` | 설정 검증부터 결과·보고서 생성까지 한 명령으로 수행 |

현재 모델의 packet 순서는 다음과 같다.

```text
Poll -> Response -> Final -> PostFinal -> Report
```

직접 2A2T superframe의 기본 slot 순서는 다음과 같다.

```text
SLOT 0  A1-T1
SLOT 1  A2-T1
SLOT 2  A1-T2
SLOT 3  A2-T2
```

동일 node의 겹치는 TX/RX 또는 두 link 점유는 `NODE_TX_RX_OVERLAP`로 즉시 실패한다. 서로 다른 tag가 같은 anchor에 동시에 송신하면 `RECEIVER_COLLISION`로 즉시 실패한다. 충돌 후보를 결과에서 조용히 제외하지 않고 scheduler 단계에서 예외로 중단하는 것이 golden contract다.

## provenance 처리

논문값과 CODE_BASELINE 값은 서로 덮어쓰지 않는다. 모든 입력 후보는 다음 정보를 함께 저장한다.

```yaml
value: 100
unit: us
evidence_class: SWEEP
source: simulation design
locator: paper timeout-margin scale
hardware_verified: false
```

허용 분류는 `PAPER`, `PAPER_DERIVED`, `CODE_BASELINE`, `ASSUMED`, `SWEEP`, `MEASURED`다. 이번 결과에는 실제 측정값이 없으므로 `MEASURED` parameter가 없다. 계산된 reply delay와 RX acquisition lead에도 별도 provenance가 저장된다.

## software-only 실험 실행법

저장소 root에서 다음을 실행한다.

```powershell
python -m pytest -q
python tools/run_2a2t_parameter_simulation.py
```

두 번째 명령은 다음 규칙으로 새 폴더를 만든다.

```text
results/YYYY-MM-DD_python_2A2T-paper-baseline_parameter-sweep_runNN/
```

실행 전 문서인 `question.md`, `protocol.md`, `run_matrix.md`, `metadata.yaml`을 먼저 만든 뒤 simulation을 수행한다. 실행 후에는 `run_log.md`, `qc.md`, `analysis_environment.md`, `results/validation.md`, `closeout.md`를 채운다. 결과 상태는 `raw-only -> qc-passed -> processed -> exploratory`까지만 승격하며 `verified`로 표시하지 않는다.

주요 결과 파일은 다음과 같다.

```text
results/candidates.csv
results/candidates.json
results/pareto_candidates.csv
results/report.md
results/validation.md
```

별도 결과 위치에서 시험하려면 다음처럼 지정한다.

```powershell
python tools/run_2a2t_parameter_simulation.py --results-root C:\temp\uwb_2a2t_results
```

## 현재 synthetic 결과 해석

2026-07-13 run02에서는 40개 조합이 네 링크를 모두 완료했고 모델상 node overlap과 receiver collision은 0이었다. Pareto selector는 20개를 남겼다. 가장 빠른 Pareto 행 `C0003`의 모델상 superframe은 약 12,353.856 us, 약 80.946 Hz다.

이 수치는 현재 airtime 식과 scheduling 가정에서 계산된 값일 뿐 실제 DW3000 update rate가 아니다. 특히 RX enable 시점은 receiver processing 완료 이후이면서 예상 packet 시작 전 `timeout_margin/2`만큼의 acquisition lead를 두는 `ASSUMED` 모델이다.

## 구분해서 읽어야 할 결과

### 검증된 결과

- 논문 PLEN128 Poll/Response/Final airtime golden 값 재현
- 논문 processing 522 us 기준 reply 706/717 us 재현
- PLEN1024 reply 1618/1629 us 재현
- software scheduler의 네 링크 완주 및 두 종류 충돌 hard-fail 동작
- PAPER/CODE_BASELINE 입력 불변성과 firmware source hash 보존

### 가정한 값

- 네 개의 sequential slot 구성
- reply/timeout/slot guard 후보
- PostFinal-to-Report timing 모델
- RX acquisition lead 계산 방식

### 논문 기반 근거

- packet airtime 식과 PLEN128/1024 값
- 522 us processing reference
- 100 us timeout-margin scale

논문은 single-link 3-packet DS-TWR를 다루므로 직접 2A2T 5-packet superframe 자체는 논문 결과가 아니라 본 simulation의 확장이다.

### 추후 확인 필요

- node별 실제 IRQ/ISR, SPI, CIR, phase/filter, UART 처리시간의 p95/p99
- delayed TX 단위와 clock drift
- 실제 frame/FCS 길이 및 RX preamble acquisition lead
- 네 node 주소·role·superframe identity 처리
- 실제 RF packet loss, retry, NLOS, 동시 채널 간섭
- ground truth 거리와 antenna delay calibration

## 실제 보드를 연결한 뒤의 순서

이번 구현은 hardware 명령을 만들거나 실행하지 않는다. 다음 단계에서는 네 보드를 처음부터 모두 사용하는 direct 2A2T conservative smoke를 구성하되, simulation candidate를 firmware에 바로 덮어쓰지 않는다.

1. A1/A2/T1/T2의 serial number, USB/UART port, J-Link serial, firmware image와 역할을 기록한다.
2. 네 UART의 baud rate와 timestamp source를 기록한다.
3. logic analyzer의 IRQ/SPI/UART/trace GPIO channel mapping과 sample rate를 기록한다.
4. 네 link의 ground-truth 거리, 배치, 높이, 방향, LOS/NLOS 조건을 기록한다.
5. 현재 CODE_BASELINE으로 direct 2A2T conservative smoke를 캡처한다.
6. 측정된 processing p99와 clock/RX margin으로 후보를 다시 계산한다.
7. 별도 검토를 거쳐 선택한 값만 firmware 변경 대상으로 삼는다.

실제 connection smoke 및 antenna-delay calibration 명령은 hardware config의 모든 TODO 값과 firmware image가 확정된 다음 사용해야 한다. 현재 synthetic report를 실제 측정 완료 또는 보정 완료의 근거로 사용하면 안 된다.

