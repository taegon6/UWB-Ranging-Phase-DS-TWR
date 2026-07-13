# 2A2T Phase 6 실제 Firmware 구현 및 4-board HIL 계획

기준 branch: `codex/pre-hardware-2a2t-foundation`
기준 commit: `641f768a837a731866c5c41a85a7e7e37ce29b7c`
계획 상태: `IMPLEMENTATION_PLAN`
실제 hardware 검증 상태: `NOT_STARTED`

## 1. 결론

기존 firmware를 기반으로 구현하는 것이 맞다. 기존 코드에는 다음 핵심 기능이 이미 있다.

- DW3000 Channel 9 / PLEN128 / PAC8 / 6.8 Mbps / STS-off 설정
- Poll, Response, Final, PostFinal, Report 5-packet 교환
- delayed TX, RX-after-TX, RX timeout 처리
- DS-TWR timestamp와 ToF 계산
- CIR phase 합성 및 corrected distance 계산
- UART report 출력

그러나 현재 topology는 `TG` tag 한 대와 `A1/B2` anchor 두 대를 교대하는 구조다. `T2`, 4-link superframe, slot token, superframe identity와 충돌 복구가 없으므로 timing 상수만 바꾸어서는 실제 2A2T가 되지 않는다.

권장 방식은 원본 `ds_twr_initiator_final.c`, `ds_twr_responder_final.c`를 그대로 rollback baseline으로 보존하고, 이 코드에서 파생한 2A2T 전용 tag/anchor source를 추가하는 것이다.

## 2. 구현 branch와 baseline 보존

구현 시작 시 다음 branch를 새로 만든다.

```text
codex/phase6-2a2t-hil-firmware
```

작업 전 다음을 기록한다.

- 기준 commit과 dirty working tree
- `firmware_overlay/` 전체 SHA-256 manifest
- 기존 두 firmware source의 hash
- simulation config와 Conservative manifest hash
- 실제 SDK/project path와 toolchain version

원본 두 파일은 직접 덮어쓰지 않는다.

```text
firmware_overlay/API/Src/custom_code/
  ds_twr_initiator_final.c       # 기존 baseline 유지
  ds_twr_responder_final.c       # 기존 baseline 유지
  ds_twr_2a2t_tag.c              # initiator 기반 신규 구현
  ds_twr_2a2t_anchor.c           # responder 기반 신규 구현
  uwb_2a2t_config.h              # role/PHY/timing profile
  uwb_2a2t_protocol.h            # 주소, sequence, slot contract
  uwb_2a2t_trace.h               # GPIO/UART instrumentation
```

### 2.1 Source of truth와 clean build sandbox

Phase 6의 수정·review 기준은 이 repository의 `firmware_overlay/`로 고정한다. 전체 SDK 후보는 다음 경로에서 확인되었다.

```text
C:\Users\User\Documents\학부연구생\research\uwb_followup\original_repos\
  UWB-Ranging-Optimization\API\nRF52840-DK\dw3000_api.emProject
```

하지만 해당 upstream working tree에는 현재 대량의 staged deletion과 untracked file이 관찰되었고, `C:\uwb_build` junction도 그 tree를 가리킨다. 이 경로에서 직접 수정·정리·build하지 않는다. 원본 repository를 보존하면서 다음 세 계층을 분리한다.

```text
firmware_overlay/                    # 수정·review하는 canonical source
clean commit-pinned SDK sandbox      # overlay를 적용하는 일회성 build workspace
experiment/results/firmware/         # 4 image, log, manifest, SHA-256 증거
```

build마다 clean SDK commit, overlay manifest, toolchain version을 기록하고, build 후 sandbox 밖의 run 결과 폴더로 image를 복사해 hash를 동결한다. stale HEX를 재사용하거나 dirty upstream의 기존 output을 성공 산출물로 간주하지 않는다.

## 3. 현재 코드에서 재사용할 부분

| 기능 | 기존 위치 | 처리 |
|---|---|---|
| PHY config | `ds_twr_initiator_final.c:41-55`, responder `:51-65` | 동일 설정 유지 |
| 5-packet buffer | initiator `:67-71`, responder `:79-83` | packet length를 유지하며 주소만 일반화 |
| Address field 설정 | initiator `:85-113`, responder `:95-120` | A1/A2/T1/T2 table 방식으로 교체 |
| Tag delayed TX/RX | initiator `:242-368` | 공통 link-exchange 함수로 추출 |
| Anchor delayed TX/RX | responder `:307-455` | address/sequence 검증을 추가해 재사용 |
| DS-TWR 계산 | responder `:457-471` | 수식 변경 없이 golden test로 보호 |
| Phase correction | responder `:472-479` | on/off profile로 보호 |
| Report encoding | responder `:497-519` | node/link/superframe log를 별도 추가 |

## 4. 4-link scheduler 구조

고정 순서는 simulation과 동일하게 유지한다.

```text
SLOT 0: A1-T1
SLOT 1: A2-T1
SLOT 2: A1-T2
SLOT 3: A2-T2
```

### 4.1 권장 coordinator 방식

추가 control packet을 만들지 않고 기존 `Report`를 slot token으로 사용한다.

1. T1이 coordinator로 boot된다.
2. T1이 A1-T1과 A2-T1을 완료한다.
3. T2는 A2가 T1으로 보내는 `Report`를 overhear한다.
4. T2는 inter-slot guard 후 A1-T2와 A2-T2를 수행한다.
5. T1은 A2가 T2로 보내는 `Report`를 overhear한다.
6. T1은 superframe guard 후 다음 SLOT 0을 시작한다.

현재 source에는 frame filter enable 호출이 보이지 않지만, 다른 tag가 Report를 안정적으로 overhear할 수 있는지는 실제 SDK 설정과 DW3000 동작으로 확인해야 한다. 구현에서는 의도적으로 frame filter 정책을 명시하고, token 수신 전에는 follower가 TX하지 않도록 한다.

Report overhear가 다음 acceptance를 모두 통과해야 이 방식을 채택한다.

- T1과 T2가 자신에게 직접 주소 지정되지 않은 A2 Report를 선택적으로 수신 가능
- 정상 수신 tag와 overhear tag가 같은 sequence와 Rmarker를 관측
- frame filtering 설정을 바꾸어도 responder 주소 격리가 유지됨
- token loss에서 T2는 계속 silent이고 T1만 bounded watchdog recovery를 수행

하나라도 실패하면 timing 수치를 억지로 조정하지 않는다. fallback은 명시적 `TURN` control frame 또는 유선 GPIO sync이며, 이 경우 5-packet ranging exchange는 유지하되 control airtime을 superframe 모델에 별도로 추가하고 Phase 5 sweep을 다시 수행한다.

### 4.2 Sequence 규칙

MAC sequence byte(index 2)를 4-link exchange sequence로 사용하면 packet byte 수를 늘리지 않아도 된다.

```text
sequence % 4 == 0 -> A1-T1
sequence % 4 == 1 -> A2-T1
sequence % 4 == 2 -> A1-T2
sequence % 4 == 3 -> A2-T2
superframe_id = sequence / 4  (modulo 64)
```

Response, Final, PostFinal, Report는 initiator가 시작한 동일 sequence를 echo한다. 현재처럼 수신 비교 전에 sequence를 무조건 0으로 지우고 independent counter를 증가시키는 방식은 제거한다.

Final의 현재 미사용 bytes 26-31에는 packet 길이를 바꾸지 않고 `protocol_version`, `slot_id`, 축약 `superframe_id`를 넣는다. Report token은 MAC sequence, source/destination, function code, 수신 허용 시간창과 local scheduler state가 모두 맞을 때만 수락한다.

### 4.3 실패 안전 정책

- 예상 token을 놓친 tag는 TX하지 않고 `TOKEN_TIMEOUT`을 기록한다.
- 잘못된 source/destination/sequence의 Report는 stale token으로 거부한다.
- late delayed-TX는 해당 link와 superframe을 실패 처리한다.
- 이전 range를 현재 success로 재사용하지 않는다.
- coordinator가 follower 완료 token을 받지 못하면 임의로 즉시 재시작하지 않는다.
- recovery는 host command 또는 충분히 긴 명시적 recovery epoch에서만 수행한다.

현재 initiator의 PostFinal late-TX 경로(`ds_twr_initiator_final.c:356-359`)는 곧바로 `continue`하여 anchor 전환과 guard(`:422-423`)를 건너뛴다. 2A2T 구현에서는 모든 성공/실패 경로를 하나의 `finish_slot(result)`로 모으고, 실패해도 다음 fixed deadline으로 진행하거나 전체 superframe을 안전 정지한다.

현재 `REPORT_RX_TIMEOUT_UUS=50000`(`:139`, 사용 `:366`)은 목표 superframe period보다 길다. 실제 2A2T에서는 어떤 RX timeout도 해당 slot budget을 넘지 못하도록 config validation과 compile-time assertion을 둔다.

## 5. Node role build

하나의 anchor source와 하나의 tag source를 role define으로 네 image로 빌드한다.

| Image | Compile define | 역할 |
|---|---|---|
| `anchor_a1` | `UWB_NODE_A1` | A1 responder |
| `anchor_a2` | `UWB_NODE_A2` | A2 responder/token source |
| `tag_t1` | `UWB_NODE_T1`, `UWB_2A2T_COORDINATOR` | SLOT 0/1 및 superframe 시작 |
| `tag_t2` | `UWB_NODE_T2`, `UWB_2A2T_FOLLOWER` | SLOT 2/3 및 token 대기 |

`tools/set_uwb_example.py`에는 2A2T tag/anchor 선택과 node define 생성을 추가한다. 단, 현재 repository는 `firmware_overlay/API`만 있고 `.emProject`, Makefile, CMake 또는 IDE project가 없으므로 현재 상태만으로는 실제 image를 빌드할 수 없다. 실제 DWS3000 SDK/project의 위치와 build command가 먼저 필요하다.

확인된 SEGGER project target은 `nRF52840_xxAA`, interface는 SWD, 산출물은 HEX다. 현재 J-Link backend의 기본값 `STM32F429ZI`는 이 보드에 사용하지 않으며, local hardware config에서 `nRF52840_xxAA`를 명시하지 않으면 validation 실패로 처리한다.

기존 3-board A1/B2/TG HEX는 2A2T image로 재사용하지 않는다. 각 build 직후 image 내부 또는 UART BOOT record에서 다음 FWID가 서로 다른 역할로 확인되어야 한다.

```text
node_id, role, source_git, overlay_sha256, config_sha256, build_timestamp
```

## 6. Timing parameter를 C 상수로 옮기는 규칙

Simulation 값과 firmware API 값의 기준시점이 다르므로 숫자를 직접 복사하지 않는다.

### 6.1 직접 매핑 가능한 후보

다음은 Rmarker 기준 의미가 SDK/API와 일치함을 확인한 뒤 explicit conversion helper로 변환한다.

- `POLL_RX_TO_RESP_TX_DLY_UUS`
- `RESP_RX_TO_FINAL_TX_DLY_UUS`
- `FINAL_TX_TO_POST_FINAL_TX_DLY_UUS`
- 신규 `POST_FINAL_RX_TO_REPORT_TX_DLY_UUS`

변환 과정은 다음 정보를 manifest에 기록한다.

```text
input Decimal ps/us
-> UUS conversion
-> delayed-TX hardware quantization
-> integer rounding direction
-> final register/API value
```

### 6.2 직접 매핑하면 안 되는 값

| Simulation 값 | 기존 firmware 값 | 이유 |
|---|---|---|
| Poll→Response Rmarker delay | `POLL_TX_TO_RESP_RX_DLY_UUS` | 기존 값은 TX 후 RX enable delay |
| Response→Final Rmarker delay | `RESP_TX_TO_FINAL_RX_DLY_UUS` | 기존 값은 TX 후 RX enable delay |
| timeout margin 300 us | `RESP_RX_TIMEOUT_UUS`, `FINAL_RX_TIMEOUT_UUS` | margin과 실제 timeout duration은 다름 |
| inter-slot guard 200 us | `Sleep(RNG_DELAY_MS)` | millisecond sleep과 precise on-air boundary는 다름 |
| report transition | responder `Sleep(2)` + immediate TX | processing과 scheduling이 분리되지 않음 |

RX start와 timeout은 최소한 다음 항을 사용해 계산한다.

```text
RX enable point = expected packet start - acquisition lead
RX timeout duration = acquisition lead + packet airtime + timeout margin
```

실제 API가 TX start, TX end, RX Rmarker 중 어떤 기준을 사용하는지 Qorvo API와 logic capture로 확인한 뒤 final UUS를 확정한다.

## 7. 첫 실제 profile과 목표 profile을 분리한다

### 7.1 HIL_BOOTSTRAP_SAFE

첫 4-board smoke는 실제 동작 이력이 있는 CODE_BASELINE timing을 유지한다.

- PLEN128, Channel 9, STS off
- 현재 remote delayed-TX 1650 UUS 계열 유지
- current RX-after-TX 및 timeout 유지
- Final→PostFinal 1650 UUS 유지
- responder의 blocking `Sleep(2)` report path는 사용하지 않고, `POST_FINAL_RX_TO_REPORT_DELAY_UUS=2522`의 timestamp-based delayed TX를 사용한다. 이 값은 `CODE_BASELINE_UNVERIFIED`이며 HIL processing p99 측정 전 성능값으로 해석하지 않는다.
- slot/superframe guard는 최소 1 ms의 명시적 bootstrap guard 사용
- CIR/phase off
- 네 보드와 네 link를 처음부터 사용

이 profile은 성능 후보가 아니라 address, token, sequence, 4/4 completion을 확인하기 위한 bring-up profile이다.

단, responder loop 끝의 `Sleep(5)`(`ds_twr_responder_final.c:530-533`)는 제거하고 anchor를 즉시 RX-ready 상태로 되돌린다. 이 sleep은 다음 tag slot을 놓칠 수 있다. 파생 2A2T source는 bootstrap부터 timestamp 기반 delayed Report TX를 사용하며, delay는 logic capture가 완료되기 전까지 `CODE_BASELINE_UNVERIFIED` provenance로 기록한다.

### 7.2 HIL_CONSERVATIVE_TARGET

Simulation 후보 `P5-00029`를 목표로 한다.

- PLEN128
- timeout margin 300 us
- inter-slot guard 200 us
- superframe guard 200 us
- CIR/phase off
- compact UART record
- synthetic target: 16,814.789 us / 59.471 Hz complete-superframe rate

그러나 522 us processing reference는 PAPER sensitivity 값이며 실제 firmware 측정값이 아니다. `P5-00029`의 701.42404 us 및 722.96332 us를 첫 flash에 바로 넣지 않는다. GPIO/logic capture로 processing p99를 측정한 뒤 다음 식으로 재계산한다.

```text
reply delay >= measured processing p99 + outgoing packet airtime + guard
report delay >= measured PostFinal processing p99 + Report airtime + guard
```

## 8. Firmware instrumentation

Timing-critical path에서는 `sprintf`/blocking UART를 직접 호출하지 않고 ring buffer에 binary record를 enqueue한다.

64-byte record를 921600 bps, 8N1로 동기 전송하면 약 694 us가 걸려 200 us guard보다 길다. 따라서 UART 출력은 IRQ/DMA 기반 비동기 drain으로 분리하며, ring overflow는 성공으로 숨기지 않고 `UART_DROP`으로 남긴다.

필수 record:

```text
BOOT
SUPERFRAME_START
SLOT_START
PACKET_TX_SCHEDULED
PACKET_TX_DONE
PACKET_RX_RMARKER
PROCESS_START
PROCESS_END
TOKEN_RX
TOKEN_TIMEOUT
LATE_TX
RX_TIMEOUT
REPORT_READY
SUPERFRAME_DONE
UART_DROP
```

공통 필드:

```text
node_id, boot_id, firmware_git, config_hash
sequence, superframe_id, slot_id, link_id
event_type, status, device_timestamp_dtu
counter, dropped_record_count
```

GPIO trace는 최소 다음 네 신호를 제공한다.

- `TRACE_SLOT_ACTIVE`
- `TRACE_PROCESS_ACTIVE`
- `TRACE_REPORT_READY`
- `TRACE_ERROR`

IRQ/SPI/CIR 세부 신호는 header pin 수를 확인한 뒤 선택한다.

## 9. Host tool 변경

### 9.1 반드시 구현할 부분

- `tools/collect_tag_two_anchor_position.py`의 A1/B2 및 single-tag parser를 A1/A2/T1/T2 record parser로 교체
- 4-port UART 동시 capture와 boot identity 검증
- complete-superframe assembler
- sequence wrap 및 missing-slot 검출
- predicted/measured period 비교
- timeout, late-TX, token miss, UART drop 집계

responder의 phase correction/filter 상태는 향후 활성화할 때 anchor 전역값이 아니라 link별(A1-T1, A1-T2, A2-T1, A2-T2) 상태로 분리한다. bootstrap에서 CIR/phase off이면 diagnostics 및 filter 경로를 compile-gate하고 `corrected_distance=raw_distance`로 명시한다.

### 9.2 Build/flash tooling의 현재 gap

현재 J-Link backend 자체는 안전장치를 갖는다.

- `hardware/jlink_backend.py:81-105`: load/verify script 생성
- `hardware/jlink_backend.py:108-140`: serial/device/SWD command 생성
- `hardware/jlink_backend.py:147-150`: YAML `allow_execute=true` 요구
- `hardware/jlink_backend.py:181-204`: 별도 `execute=True` 요구

그러나 실제 end-to-end flash는 아직 연결되지 않았다.

- `tools/run_hardware_experiment.py:206-221`은 real backend에서 `--build`, `--flash` 등을 거부한다.
- 같은 파일 `:293-315`는 real flash를 의도적으로 실패시킨다.
- `tools/flash_all.py --execute`도 현재 verified backend execution으로 연결되지 않는다.
- J-Link `list_devices()`는 configured inventory일 뿐 physical discovery가 아니다.

따라서 실제 업로드 전에 다음을 구현한다.

1. verified build manifest만 허용한다.
2. node→image→SHA-256→J-Link serial mapping을 검증한다.
3. real runner가 승인된 image에 대해 J-Link backend `flash(..., execute=True)`를 호출하도록 연결한다.
4. 한 node 실패 시 즉시 중단한다.
5. J-Link stdout/stderr와 verify 결과를 immutable flash manifest에 기록한다.
6. flash 후 UART `BOOT node_id/git/config_hash`가 image manifest와 맞아야 통과한다.

build 도구에는 stale output 삭제가 아니라 별도의 empty output directory 사용, build exit code, build log, 산출 시각, role marker, SHA-256, source/config/toolchain provenance 검증을 추가한다. flash 직전에도 image SHA를 다시 계산해 승인된 plan과 다르면 중단한다.

### 9.3 로컬 DW3000 build/upload skill 처리

로컬에는 다음 skill 문서가 존재한다.

```text
C:\Users\User\.codex\skills\dw3000-firmware-build\SKILL.md
```

이 skill은 SEGGER build와 J-Link board flash용이지만, 현재 세션의 Available Skills catalog에는 노출되지 않아 활성 skill로 호출할 수 없다. 또한 현재 내용은 A1/B2/TAG 3-board, 과거 J-Link/COM mapping, unconditional `erase` 중심이며 A2/T2, four-image manifest, plan approval binding, readback, FWID 검증이 없다.

따라서 기존 skill은 과거 성공 도구 경로의 참고자료로만 사용한다. 실제 업로드 전에 다음 기준으로 skill을 갱신하고 catalog에서 활성화한 뒤 사용한다.

- role을 A1/A2/T1/T2로 확장
- 깨진 workspace 경로와 현재 tool path 재검증
- `nRF52840_xxAA` 강제
- old J-Link serial/COM을 `HISTORICAL_UNVERIFIED`로 표시하고 재탐색
- 기본 blanket `erase` 제거; 필요할 때 별도 승인
- build/flash plan SHA-256과 사용자 승인 결합
- load/verify 후 readback 또는 `verifybin` 및 UART FWID 확인
- 한 board씩 flash하고 첫 실패에서 중단

## 10. Upload/flash 순서

GitHub push와 board flash는 서로 다른 작업이다.

### 10.1 GitHub 업로드

```text
tests PASS
-> firmware hash/diff review
-> commit
-> codex/phase6-2a2t-hil-firmware push
-> 필요 시 PR
```

### 10.2 Board 업로드

1. 한 번에 한 board만 연결하여 J-Link serial과 UART COM을 확정한다.
2. `configs/local_hardware.yaml`을 생성하고 `allow_execute: false`를 유지한다.
3. 네 image를 build하고 hash manifest를 생성한다.
4. J-Link command를 dry-run으로 생성한다.
5. 사람이 node/image/serial/device/load address를 검토한다.
6. resolved command와 image hash를 포함한 `flash_plan.json`의 `plan_sha256`을 사람이 승인한다.
7. 승인된 run에서만 `allow_execute: true`와 CLI `--execute`를 동시에 사용하고, execute 직전에 plan과 image hash를 재검증한다.
8. A1, A2, T2, T1 순으로 flash/verify한다.
9. coordinator T1은 마지막에 reset하여 다른 세 node가 먼저 RX-ready가 되게 한다.
10. UART BOOT identity 4개가 모두 맞지 않으면 RF test를 시작하지 않는다.

실제 실행 명령은 build system과 image path가 확정된 후 최종화한다. 현재 repository의 placeholder target을 실제 target으로 가장해 flash하지 않는다.

## 11. Test-first 구현 순서

### Phase I - Protocol golden tests

- A1/A2/T1/T2 address encoding
- sequence→slot/superframe mapping
- 255→0 wrap
- Response/Final/PostFinal/Report sequence echo
- stale/wrong token rejection
- missing token에서 TX 금지
- packet byte/FCS length 불변
- DS-TWR/phase golden vector 불변
- 수신 `frame_len` 최소/최대 검증 후에만 `memcmp`
- Response activity/function field와 source/destination 전체 검증
- responder가 Poll에서 peer tag와 exchange sequence를 bind하고 나머지 4 packet을 같은 context로만 처리
- Poll TX, delayed TX, RX enable API 반환값 누락 금지
- CIR/phase off에서도 Final 32-byte/on-air 34-byte convention 유지
- 실제 FCS programmed length convention 회귀 테스트
- responder local bounded distance buffer 및 format overflow test

### Phase II - Scheduler implementation

- T1 coordinator state machine
- T2 follower state machine
- anchor address filter
- A2 Report token handoff
- 4/4 link completion
- late TX/timeout hard failure

### Phase III - Four-role build

- A1/A2/T1/T2 compile
- role define와 embedded identity 확인
- four image hash manifest
- baseline source hash 보존

### Phase IV - Upload orchestration

- real runner gate test
- placeholder/image mismatch rejection
- duplicate J-Link/COM rejection
- stop-on-first-flash-failure
- J-Link verify result 보존
- reset order A1→A2→T2→T1

### Phase V - Dry-run acceptance

- build/flash command review
- mock UART 4-port parser
- synthetic superframe assembler
- report generation
- firmware source diff audit

## 12. 첫 실제 4-board experiment

사용자가 요청한 대로 A1/A2/T1/T2 네 보드와 네 link를 처음부터 사용한다.

실행 전에 `YYYY-MM-DD_dws3000_2a2t_phase6_runNN` 형식의 experiment folder를 만들고, `question.md`, `protocol.md`, `run_matrix.md`, `metadata.yaml`을 먼저 작성한다. raw log는 해당 experiment의 `raw/`, canonical 분석 결과는 `results/`에 저장한다. 실제 run 뒤에는 `run_log.md`, `qc.md`, `analysis_environment.md`, `results/validation.md`, `closeout.md`를 순서대로 채운다. 기존 raw/ZIP/log는 이동하지 않고 `raw_manifest.md`에 원본 경로와 SHA-256만 기록한다.

### Stage A - Connection and identity

- J-Link/UART physical mapping
- image hash와 BOOT identity
- coordinator/follower role
- RF TX는 아직 시작하지 않음

### Stage B - HIL_BOOTSTRAP_SAFE 2A2T smoke

- 4/4 slot 순서 확인
- complete-superframe count
- token miss, stale token, timeout, late TX
- raw UART 4개 동시 저장
- 가능한 경우 logic analyzer 저장
- antenna delay/range accuracy 판정 금지

### Stage C - Timing measurement

- Poll RX→Response scheduling processing
- Response RX→Final scheduling processing
- PostFinal RX→Report-ready processing
- RX enable/startup lead
- slot handoff processing
- mean/p95/p99와 worst observed 기록

### Stage D - Candidate regeneration

실측 processing을 `MEASURED` provenance로 새 config에 추가하고 Phase 5 sweep을 다시 수행한다. 기존 synthetic 결과를 덮어쓰지 않는다.

### Stage E - Candidate comparison

- Conservative → Processing-robust → Fast 순서
- 후보당 10초, 최소 3회
- complete-superframe rate와 link별 success
- timeout/late TX/token miss/UART drop
- predicted vs measured model error

## 13. 통과 기준

첫 smoke PASS 최소 조건:

- 네 node BOOT identity와 image hash 일치
- slot 순서가 항상 0→1→2→3
- 모든 complete superframe이 현재 네 link를 포함
- node TX/RX overlap 0
- receiver collision 0
- stale previous range 재사용 0
- UART dropped record 0
- late TX 및 timeout은 발생 시 명시적으로 기록
- 실제 measured period가 raw timestamp에서 재계산 가능

`hardware_verified=true`는 programmer command 성공만으로 설정하지 않는다. 반복 HIL run과 raw evidence가 acceptance를 통과한 항목에만 제한적으로 사용한다.

## 14. 구현 시작 전에 사용자가 제공해야 할 값

- 실제 DWS3000/MCU board revision 4개
- clean SDK/project 경로
- 사용 IDE/toolchain 및 CLI build command
- A1/A2/T1/T2 J-Link serial
- A1/A2/T1/T2 UART COM과 baud/format
- J-Link MCU device name, interface, speed, load address 필요 여부
- GPIO trace 가능 pin과 logic analyzer channel/sample rate
- board 전원/VTref/ground 연결 방식
- Report overhear를 허용할 frame-filter policy 승인 또는 TURN/GPIO fallback 선택

## 15. 최종 판단

기존 코드를 재사용하는 것이 맞지만, 현재 파일의 숫자만 교체하는 작업은 아니다. 최소 변경의 핵심은 다음 세 가지다.

1. A1/A2/T1/T2 주소와 sequence contract
2. T1/T2 Report-token 기반 4-slot scheduler
3. build/J-Link/UART/logic end-to-end 증거 보존

첫 실제 flash profile은 `HIL_BOOTSTRAP_SAFE`, 최종 timing 목표는 measured processing으로 재계산한 `HIL_CONSERVATIVE_TARGET`으로 분리한다.
