# A1/A2/T1/T2 Hardware Connection Checklist

## 현재 상태와 사용 금지 주장

```text
source_type = SYNTHETIC
hardware_verified = false
```

현재 DW3000/DWS3000 보드, UART, J-Link 및 logic analyzer가 연결되어 있지 않다. 이 checklist는 첫 연결 전에 필요한 사용자 입력과 안전 순서를 정리한 것이며, flash·실측·antenna-delay calibration·실제 2A2T 통신이 완료되었다는 의미가 아니다.

실제 장비가 연결되기 전에는 다음을 확정값으로 기록하지 않는다.

- DW3000/DWS3000의 IRQ, SPI, UART, CIR 또는 phase 처리시간
- 실제 GPIO pin, UART port/baud rate, SPI clock, logic analyzer sample rate
- antenna delay 또는 calibration 최적 후보
- 실제 A1/A2/T1/T2 통신 성공 여부
- 실제 logic analyzer capture 성공 여부

## 1. 사용자 입력 준비

`configs/local_hardware.example.yaml`을 `configs/local_hardware.yaml`로 복사하고, 실제 실행 전에 모든 `TODO_USER_INPUT`, `TODO_CODE_OR_HW_VERIFY`, `TODO_HW_VERIFY`를 근거와 함께 해소한다. Calibration은 example을 복사한 `configs/antenna_calibration.yaml`에 입력한다. Mock/dry-run은 placeholder를 허용하지만 `--backend real --execute`는 placeholder가 하나라도 남으면 중단해야 한다.

### A1/A2/T1/T2 및 flash 입력

| 항목/config key | 사용자 입력 | 확인 방법과 기록할 근거 |
|---|---|---|
| 실제 board label과 역할 A1/A2/T1/T2 | 필요 | 네 보드에 물리 라벨 부착 후 사진·serial과 대조 |
| `boards.A1.role` … `boards.T2.role` | `ANCHOR`/`TAG` 확인 | 실험 설계 및 생성 config 대조 |
| `boards.<node>.firmware_target` | `anchor_a1`, `anchor_a2`, `tag_t1`, `tag_t2` 또는 저장소가 지원하는 실제 target | build manifest와 실제 build system 대조; target 존재를 먼저 확인 |
| `boards.<node>.jlink_serial` | 네 J-Link ID | J-Link discovery 결과와 한 대씩 연결했을 때의 보드 라벨 대조 |
| J-Link MCU device/interface/speed/reset 방식 | 필요 시 tool config에 입력 | 실제 MCU/board manual과 기존 project 설정 확인. 추측 금지 |
| J-Link executable 경로 | 환경에 따라 필요 | `tools/check_environment.py` 및 vendor CLI version 출력 기록 |
| 각 firmware image/hash | build가 생성 | node→image mapping과 hash를 flash 전에 사람이 검토 |
| flash/reset stop policy | 확인 | 한 node 실패 시 나머지를 계속하지 않는지 dry-run manifest 검토 |

### UART 입력

| 항목/config key | 사용자 입력 | 확인 방법과 기록할 근거 |
|---|---|---|
| `boards.<node>.serial_port` | A1/A2/T1/T2 각각의 실제 port | 보드를 한 대씩 연결하고 OS port 목록 변화 및 node identity message 대조 |
| `serial.baud_rate` | 코드 확인 또는 실제값 입력 | firmware UART config/board example 확인. 임의 default 사용 금지 |
| `serial.timeout_s` | 실험 요구에 맞게 확인 | capture/reconnect test에서 timeout 동작 확인 |
| data bits/parity/stop bits/flow control | backend가 요구하면 입력 | firmware UART 초기화와 host 설정 대조 |
| UART electrical type | USB CDC 또는 TTL UART 구분 | schematic/adapter manual 확인; RS-232 voltage를 TTL pin에 연결 금지 |
| UART node identity format | 확인 | 각 port가 어느 node인지 식별 가능한 boot/session record 확인 |

### Logic analyzer 및 GPIO 입력

| 항목/config key | 사용자 입력 | 확인 방법과 기록할 근거 |
|---|---|---|
| `logic_analyzer.device_id` | 실제 analyzer ID | backend discovery 결과와 장비 라벨 대조 |
| logic backend | `saleae` 또는 `sigrok` 등 설치된 실제 backend | dependency/CLI availability와 장비 지원 확인 |
| `logic_analyzer.sample_rate_hz` | 실제 capture rate | 가장 짧은 trace pulse에 충분한 sample 수인지 pilot capture로 확인 |
| analyzer input threshold/logic level | 필요 | board I/O 전압과 analyzer 허용 범위 대조 |
| `logic_analyzer.channels.IRQ_PIN` | 실제 channel 번호 | DW3000 IRQ probe point 및 schematic 대조 |
| `logic_analyzer.channels.ISR_ACTIVE` | 실제 channel 번호 | firmware route GPIO/header pin과 대조 |
| `logic_analyzer.channels.SPI_STATUS` | 실제 channel 번호 | status-read trace route와 대조 |
| `logic_analyzer.channels.SPI_FRAME` | 실제 channel 번호 | frame-read trace route와 대조 |
| `logic_analyzer.channels.UART_ENQUEUE` | 실제 channel 번호 | enqueue trace GPIO route와 대조 |
| `logic_analyzer.channels.UART_TX` | 실제 channel 번호 | UART physical TX probe point와 대조 |
| `logic_analyzer.channels.CIR_READ` | 실제 channel 번호 | CIR trace GPIO route와 대조 |
| `logic_analyzer.channels.PHASE_PROCESS` | 실제 channel 번호 | phase trace GPIO route와 대조 |
| event→GPIO route 전체 | 실제 MCU pin/header pin/polarity | board schematic, pinmux, generated route 및 continuity 대조 |
| capture duration/trigger/pre-trigger | experiment config 입력 | frame 수와 raw capture 크기를 고려하여 dry-run 검토 |
| 선택적 SPI SCK/MOSI/MISO/CS probe | 필요한 경우만 | I/O voltage와 probe loading 확인 후 별도 channel map 기록 |

세부 event와 metric 시작/종료는 `docs/LOGIC_ANALYZER_CONNECTION.md`를 따른다. `IRQ_PIN`은 실제 radio IRQ이며 `ISR_ACTIVE` trace GPIO로 대체하면 안 된다.

### RF 배치 및 antenna-delay calibration 입력

| 항목/config key | 사용자 입력 | 확인 방법과 기록할 근거 |
|---|---|---|
| `calibration.reference_distances_m` | 실제 기준거리 목록 | 교정된 줄자/거리 계측 절차와 측정 불확도 기록 |
| `calibration.samples_per_point` | 실제 계획값 | 시간·저장공간 dry-run 후 확정 |
| `calibration.warmup_samples` | 실제 계획값 | warm-up 제외 정책을 report에 기록 |
| `calibration.search.hardware.initial_min` | 실제 hardware search 하한 | DW3000 API 단위/허용범위를 공식 API와 현재 firmware에서 확인 |
| `calibration.search.hardware.initial_max` | 실제 hardware search 상한 | 동일. mock 후보값을 복사하지 않음 |
| `calibration.search.hardware.coarse_step` | 실제 coarse step | API 단위와 실험 budget 확인 |
| `calibration.search.hardware.fine_step` | 실제 fine step | API 단위와 repeatability 확인 |
| calibration 기준 node | 필요 | reference node 고정 방식 또는 combined-delay mode를 config에 명시 |
| calibration 대상 node/link | 필요 | A1T1/A2T1/A1T2/A2T2 및 순서를 명시 |
| 안테나 기준점 | 필요 | enclosure/antenna의 어느 점을 거리 기준으로 썼는지 사진과 표에 기록 |
| 안테나 높이·방향·편파 | 필요 | 각 node 배치사진, 높이, yaw/orientation 기록 |
| LOS/주변 반사체/환경 | 필요 | 바닥·벽·금속체·사람 움직임·온도 등 관찰사항 기록 |
| TX/RX 분리 식별 가능성 | 확인 | 식별 불가능하면 node별 TX/RX를 따로 확정하지 않고 combined delay로 보고 |

`calibration.search.synthetic_mock`의 숫자는 software dry-run 전용이다. 실제 search range로 복사하지 않는다.

## 2. 전기·배선 안전 확인

전원 인가 전 다음 항목을 모두 확인한다.

- [ ] 보드 revision, MCU, DWS3000/DW3000 module과 connector pinout을 실제 schematic/manual로 확인했다.
- [ ] 각 board I/O 전압과 logic analyzer/J-Link/UART adapter 허용 전압을 확인했다.
- [ ] TTL UART와 RS-232를 구분했으며, 전압이 다른 신호에는 검증된 level shifter를 준비했다.
- [ ] J-Link `VTref`, SWDIO, SWCLK, GND, RESET의 방향과 pin을 확인했다. J-Link가 target을 공급하는지 여부를 manual에서 확인했다.
- [ ] USB, bench supply, J-Link power 사이 back-power 경로가 없음을 확인했다. 전원 source를 임의로 병렬 연결하지 않는다.
- [ ] 여러 board/analyzer ground 사이 전위차를 확인했고 공통 기준 연결로 인한 ground loop 위험을 검토했다.
- [ ] logic analyzer의 VCC/power pin을 signal reference 용도로 board 전원에 연결하지 않는다.
- [ ] probe는 고임피던스 input이며 UART/SPI/IRQ/GPIO 신호를 구동하지 않는다.
- [ ] trace GPIO가 다른 board 기능, RF control 또는 boot strap pin과 충돌하지 않음을 pinmux에서 확인했다.
- [ ] 인접 pin 단락, 느슨한 clip, 케이블 strain을 전원 off 상태에서 점검했다.
- [ ] antenna/module 취급과 ESD 주의사항을 board manufacturer 문서에서 확인했다.

## 3. 권장 연결 순서

1. 모든 장비 전원을 끄고 A1/A2/T1/T2 물리 라벨을 부착한다.
2. 한 번에 한 board만 USB/J-Link에 연결하여 J-Link ID와 UART port를 기록한다. 이 단계에서는 flash하지 않는다.
3. 전원을 다시 끄고 J-Link SWD/RESET을 실제 pinout대로 연결한다. VTref/power source 역할을 재확인한다.
4. UART가 TTL header라면 board TX→adapter RX를 연결하고, 양방향 제어가 필요할 때만 board RX←adapter TX를 연결한다. GND reference와 전압을 먼저 확인한다.
5. logic analyzer GND를 먼저 연결한다. 여러 보드에 GND probe를 연결하기 전 전위차와 USB ground 구성을 확인한다.
6. `IRQ_PIN`과 선택한 trace GPIO를 한 채널씩 연결하고 channel label을 물리 케이블에 표시한다.
7. SPI physical line도 관측할 경우 pilot scope/logic 연결로 loading과 logic level을 확인한 후 연결한다.
8. 한 board에만 전원을 인가하여 과전류, 발열, 비정상 reset이 없는지 확인하고 idle level을 캡처한다.
9. A1/A2/T1/T2를 차례로 추가하면서 discovery 결과와 port/device mapping이 바뀌지 않는지 확인한다.
10. 종료할 때는 전원을 끄고 signal probe를 먼저 분리하며 공통 GND를 마지막에 분리한다.

## 4. Software preflight

보드가 없는 현재 단계에서 다음 명령은 mock/synthetic 검증용이다.

```bash
python tools/check_environment.py

python tools/run_hardware_experiment.py \
  --config configs/mock_hardware.yaml \
  --experiment timing_characterization \
  --backend mock \
  --dry-run \
  --analyze \
  --report

python tools/calibrate_antenna_delay.py \
  --config configs/antenna_calibration.example.yaml \
  --backend mock \
  --dry-run
```

위 결과에는 반드시 다음 metadata가 있어야 한다.

```text
source_type = SYNTHETIC
hardware_verified = false
```

실제 연결 전에 확인한다.

- [ ] `python tools/check_environment.py`의 hardware 항목은 장비 부재 시 `SKIP`이며 mock 항목은 `PASS`다.
- [ ] A1/A2/T1/T2 node→target→J-Link→UART mapping에 중복이 없다.
- [ ] local config와 calibration config에 unresolved placeholder가 없다.
- [ ] build/flash dry-run의 command, image hash, reset 순서와 stop policy를 검토했다.
- [ ] trace build flag는 baseline에서 0이며, instrumentation run에서만 명시적으로 1이다.
- [ ] 실제 trace route가 board pinmux와 일치한다.
- [ ] raw output directory가 새 run ID이며 기존 raw data를 덮어쓰지 않는다.

## 5. 첫 실제 connection smoke test

먼저 discovery만 실행하여 실제 장치와 사용자 입력을 대조한다.

```bash
python tools/discover_hardware.py --config configs/local_hardware.yaml
```

다음 명령은 mock이 아니라 실제 장치 작업을 허용하는 명시적 `--execute` 명령이다. 위 안전·mapping 확인과 placeholder 검사가 모두 통과한 뒤에만 실행한다.

```bash
python tools/run_hardware_experiment.py \
  --config configs/local_hardware.yaml \
  --experiment connection_smoke_test \
  --backend real \
  --execute
```

Windows PowerShell:

```powershell
python tools/run_hardware_experiment.py `
  --config configs/local_hardware.yaml `
  --experiment connection_smoke_test `
  --backend real `
  --execute
```

현재 자동 smoke acceptance는 연결 확인의 일부로 제한한다.

- 구성한 네 UART port가 OS serial discovery에 존재하고 각 port에서 non-empty raw file이 exclusive-create된다.
- 오류 발생 시 capture orchestration이 중단되고 기존 raw data가 유지된다.
- J-Link/logic analyzer physical enumeration, UART identity/session의 node-label 일치, analyzer idle/marker level은 현재 자동 acceptance가 아니며 사용자가 별도 확인·기록한다.
- 현재 real adapters는 blocking·순차 capture이므로 logic/UART/experiment가 동일 시간창에 동기화되었다고 보지 않는다.

이 acceptance만으로 실제 2A2T ranging, timing 성능 또는 antenna delay를 검증한 것으로 보지 않는다.

## 6. 첫 실제 antenna-delay calibration 명령

`configs/antenna_calibration.example.yaml`을 복사한 `configs/antenna_calibration.yaml`과 `configs/local_hardware.yaml`의 모든 실제-hardware TODO를 해소하고, connection smoke test와 기준거리/배치 검토를 마친 뒤 다음 이중 opt-in 명령을 사용한다.

Calibration 복사본은 `backend: real`, `outputs.source_type: MEASURED`, `outputs.hardware_verified: false`로 시작해야 한다. 실제 validation 전에는 마지막 값을 `true`로 바꾸지 않는다.

```bash
python tools/calibrate_antenna_delay.py \
  --config configs/antenna_calibration.yaml \
  --hardware-config configs/local_hardware.yaml \
  --backend real \
  --execute
```

Windows PowerShell:

```powershell
python tools/calibrate_antenna_delay.py `
  --config configs/antenna_calibration.yaml `
  --hardware-config configs/local_hardware.yaml `
  --backend real `
  --execute
```

실제 calibration report에는 reference distance 원자료, 배치 metadata, raw ranges, 후보 curve, quality rejection, firmware/config hash와 재검증 run을 보존한다. 실제 측정 및 validation이 완료되기 전에는 "antenna delay 보정 완료"라고 표시하지 않는다.

## 7. 연결 후 단계별 확인

| 단계 | 통과 기준 | 실패 시 조치 |
|---|---|---|
| Device discovery | 네 node가 정확히 한 J-Link와 한 UART에 대응 | port/serial mapping 수정; flash 금지 |
| One-board power-on | 정상 voltage/current, 반복 reset 없음 | 즉시 power off 후 wiring/power 조사 |
| UART identity | node/boot/config identity 해석 가능, raw bytes 보존 | baud/framing/port 재확인 |
| Trace idle | 모든 trace pin이 정의된 inactive level | route/polarity/pinmux 수정 |
| IRQ/ISR marker | 실제 IRQ와 ISR marker가 별도 channel에 보임 | probe/hook/polarity 확인; latency 값 보고 금지 |
| SPI/CIR/phase marker | start/end pair가 누락·중첩 없이 보임 | error table 작성 후 hook/route 수정 |
| Four-node orchestration | build/image/device mapping과 stop policy 일치 | 개별 1-node smoke부터 재검증 |
| Calibration readiness | 기준거리·배치·search hardware 범위의 근거 존재 | TODO 해소 전 real execute 금지 |

## 검증된 결과

- 현재 repository의 pre-hardware config 계약은 A1/A2/T1/T2별 J-Link ID, UART port와 firmware target을 사용자 입력으로 요구한다.
- mock 결과와 실제 결과를 `source_type` 및 `hardware_verified`로 구분하도록 요구사항을 고정했다.
- 실제 장비가 연결되지 않았으므로 discovery, flash, UART capture, logic capture 및 RF exchange의 실제 성공 기록은 없다.

## 가정한 값

- `anchor_a1`, `anchor_a2`, `tag_t1`, `tag_t2`는 지시서의 build matrix 이름이며 실제 upstream build target 존재 여부는 아직 확인 대상이다.
- channel symbol `IRQ_PIN`, `ISR_ACTIVE`, `SPI_ACTIVE`, `UART_ENQUEUE`, `UART_TX`, `CIR_READ`, `PHASE_PROCESS`는 논리 이름일 뿐 channel 번호나 physical pin을 의미하지 않는다.
- checklist의 연결 순서는 일반적인 저전압 digital instrumentation 안전 절차이며 실제 board revision의 manufacturer 지침이 우선한다.

## 논문 기반 근거

- 이 checklist에는 논문에서 가져온 antenna delay, timing, 거리 또는 sample-rate 수치를 사용하지 않았다.
- 실제 calibration 설계에서 논문 기반 값을 사용할 경우 문헌, 적용 조건과 실제 config 값을 별도 field로 기록해야 한다.

## 추후 확인 필요

- `TODO(HW_VERIFY)`: 네 J-Link ID, UART port, board revision, MCU device와 firmware target
- `TODO(HW_VERIFY)`: UART baud/framing 및 board별 identity output
- `TODO(HW_VERIFY)`: trace GPIO/header pin, IRQ pin, polarity와 direct-write callback
- `TODO(HW_VERIFY)`: logic analyzer model/device ID, threshold, sample rate와 channel map
- `TODO(HW_VERIFY)`: SPI clock/mode, optional physical probe loading과 hook 경계
- `TODO(HW_VERIFY)`: reference distance, 측정 불확도, antenna 기준점/높이/방향과 환경
- `TODO(HW_VERIFY)`: antenna-delay API 단위·허용범위와 real search min/max/step
- `TODO(HW_VERIFY)`: TX/RX delay의 개별 식별 가능성; 불가능하면 combined delay만 보고
- `TODO(HW_VERIFY)`: 첫 connection smoke test, 1A1T baseline, 이후 2A2T 단계별 실측
