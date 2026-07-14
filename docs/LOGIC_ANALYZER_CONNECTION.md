# Logic Analyzer Connection and Timing-Metric Contract

## 현재 상태

```text
source_type = SYNTHETIC
hardware_verified = false
```

이 문서는 보드 연결 전에 계측 신호와 지표의 의미를 고정하기 위한 연결·분석 계약이다. 현재 DW3000/DWS3000 보드와 logic analyzer가 연결되어 있지 않으므로 실제 캡처, 실제 pulse width, IRQ/SPI/UART/CIR 처리시간을 검증하거나 확정하지 않았다. 문서의 채널 번호와 GPIO 번호는 모두 사용자 입력 대상이다.

## 계측 API 계약

계측 코드는 `firmware/instrumentation/`에 있으며 vendor header에 의존하지 않는다.

- `UWB_TIMING_TRACE_ENABLE=0`이 기본값이다. 이때 `trace_event_set`, `trace_event_clear`, `trace_event_pulse` 호출과 그 인자는 전처리 단계에서 평가되지 않는다.
- `UWB_TIMING_TRACE_ENABLE=1`일 때만 event-to-pin route와 board direct-write callback을 사용한다.
- route가 없거나 `trace_gpio_configure(NULL)`을 사용하면 활성 빌드에서도 null backend로 동작한다.
- 실제 pin 번호는 board-specific translation unit 또는 generated config에만 둔다. 공통 계측 모듈에는 pin 번호를 넣지 않는다.
- `UWB_TIMING_TRACE_SOFTWARE_ENABLE=1`과 `software_timestamp_enabled=1`을 함께 사용하면 동일 event를 사용자 제공 고정 버퍼에 기록할 수 있다.
- software clock callback과 GPIO callback은 bounded direct operation이어야 한다. callback에서 `printf`, 파일/직렬 I/O, 메모리 할당, sleep, lock 또는 blocking log를 호출하면 안 된다.
- software recorder는 단일 producer가 직렬화하여 호출하는 append-only buffer다. 가득 차면 기다리지 않고 `dropped_records`를 증가시킨다. reset과 drain은 RF/ISR 경로 밖에서 한다.
- `trace_event_pulse`는 지연을 삽입하지 않는 최소 폭 pulse다. 지속시간 지표에는 반드시 `set(start_event)`과 `clear(end_event)`를 사용한다.

예시 route는 실제 핀을 의미하지 않는다. 모든 `TODO_USER_INPUT_*`를 schematic과 보드 설정으로 교체한 뒤에만 활성화한다.

```c
static const trace_gpio_route_t board_routes[TRACE_EVENT_COUNT] = {
    [TRACE_ISR_ENTRY] = {
        TODO_USER_INPUT_ISR_PIN, 1u, 1u
    },
    [TRACE_ISR_EXIT] = {
        TODO_USER_INPUT_ISR_PIN, 1u, 1u
    },
    [TRACE_CIR_READ_START] = {
        TODO_USER_INPUT_CIR_PIN, 1u, 1u
    },
    [TRACE_CIR_READ_END] = {
        TODO_USER_INPUT_CIR_PIN, 1u, 1u
    }
};

static void board_trace_write(void *context,
                              trace_gpio_pin_t pin,
                              uint8_t level)
{
    /* TODO(HW_VERIFY): replace with one direct, non-blocking GPIO write. */
    board_gpio_direct_write(context, pin, level);
}
```

보드 초기화 이후, radio IRQ를 enable하기 전에 한 번만 `trace_gpio_configure()`를 호출한다. 계측 중 route를 바꾸지 않는다.

## Event 사용 규칙

필수 event ID 0–20은 fixture와 decoder의 안정적인 계약이다. 새 event는 뒤에만 추가한다.

| 기능 | 시작/marker event | 종료 event | 호출 형태 |
|---|---|---|---|
| IRQ 관측 | `TRACE_IRQ_ASSERT` | 해당 없음 | 실제 DW3000 IRQ 선을 analyzer가 직접 관측한다. ISR에서 이 event를 대신 pulse하지 않는다. |
| ISR active | `TRACE_ISR_ENTRY` | `TRACE_ISR_EXIT` | entry에서 `set`, 모든 exit path에서 `clear` |
| SPI status read | `TRACE_SPI_STATUS_START` | `TRACE_SPI_STATUS_END` | wrapper 직전 `set`, 반환 직후 `clear` |
| SPI RX frame read | `TRACE_SPI_FRAME_START` | `TRACE_SPI_FRAME_END` | 동일 |
| SPI CIR accumulator read | `TRACE_SPI_CIR_START` | `TRACE_SPI_CIR_END` | 동일 |
| UART ring enqueue | `TRACE_UART_ENQUEUE_START` | `TRACE_UART_ENQUEUE_END` | non-blocking enqueue만 포함 |
| UART driver TX window | `TRACE_UART_TX_START` | `TRACE_UART_TX_END` | driver handoff 범위를 명시 |
| CIR aggregate processing | `TRACE_CIR_READ_START` | `TRACE_CIR_READ_END` | 정의한 CIR capture 함수 경계 |
| phase aggregate processing | `TRACE_PHASE_START` | `TRACE_PHASE_END` | phase pipeline 전체 경계 |
| filter update | `TRACE_FILTER_START` | `TRACE_FILTER_END` | median/filter update 경계 |
| frame active window | `TRACE_FRAME_START` | `TRACE_FRAME_END` | 한 frame 처리의 명시적 경계 |
| RX marker | `TRACE_RX_EVENT` | 해당 없음 | `pulse` |
| delayed-TX preparation | `TRACE_TX_PREP_START` | `TRACE_TX_ARMED` | start에서 `set`, armed에서 `clear` 또는 두 software marker |
| logger preparation | `TRACE_LOG_START` | `TRACE_LOG_END` | deferred logger 경계; ISR blocking log 금지 |
| error marker | `TRACE_ERROR_PULSE` | 해당 없음 | `pulse` |
| SPI timestamp read | `TRACE_SPI_TIMESTAMP_START` | `TRACE_SPI_TIMESTAMP_END` | SPI wrapper 경계 |
| SPI configuration write | `TRACE_SPI_CONFIG_START` | `TRACE_SPI_CONFIG_END` | SPI wrapper 경계 |
| UART record encode | `TRACE_UART_ENCODE_START` | `TRACE_UART_ENCODE_END` | encoding만 포함 |
| UART API call | `TRACE_UART_API_START` | `TRACE_UART_API_END` | 호출시간 진단용; ISR에서 blocking API 금지 |
| signed CIR decode | `TRACE_CIR_DECODE_START` | `TRACE_CIR_DECODE_END` | byte-to-signed-sample 변환 경계 |
| phase extraction | `TRACE_PHASE_EXTRACT_START` | `TRACE_PHASE_EXTRACT_END` | extraction만 포함 |
| phase combination | `TRACE_PHASE_COMBINE_START` | `TRACE_PHASE_COMBINE_END` | combination만 포함 |
| result packaging | `TRACE_RESULT_PACKAGE_START` | `TRACE_RESULT_PACKAGE_END` | output record 구성만 포함 |
| host arrival marker | `TRACE_UART_HOST_ARRIVAL` | 해당 없음 | host-side timestamp record 전용; firmware GPIO에 매핑하지 않는다. |

## Metric 시작·종료 정의

아래 정의를 synthetic 분석과 향후 실측에 동일하게 적용한다. `start`와 `end` 사이에 포함되는 코드 경계를 변경하면 metric version도 바꿔야 한다.

| Metric | Start | End | 권장 관측 신호 | 포함/제외 범위 |
|---|---|---|---|---|
| `irq_latency` | DW3000 `IRQ_PIN` active edge (`TRACE_IRQ_ASSERT` 개념 event) | `TRACE_ISR_ENTRY` active edge | `IRQ_PIN`, `ISR_ACTIVE` | MCU interrupt entry까지. ISR 내부 처리는 제외 |
| `isr_duration` | `TRACE_ISR_ENTRY` | `TRACE_ISR_EXIT` | `ISR_ACTIVE` | 모든 ISR branch를 포함. ISR 밖 deferred work 제외 |
| `spi_status_duration` | `TRACE_SPI_STATUS_START` | `TRACE_SPI_STATUS_END` | 전용 GPIO 또는 선택적 `SPI_ACTIVE` profile | status-register wrapper 전체 |
| `spi_frame_duration` | `TRACE_SPI_FRAME_START` | `TRACE_SPI_FRAME_END` | 전용 GPIO 또는 선택적 `SPI_ACTIVE` profile | RX-frame read wrapper 전체 |
| `spi_timestamp_duration` | `TRACE_SPI_TIMESTAMP_START` | `TRACE_SPI_TIMESTAMP_END` | 전용 GPIO 또는 선택적 `SPI_ACTIVE` profile | timestamp read wrapper 전체 |
| `spi_cir_duration` | `TRACE_SPI_CIR_START` | `TRACE_SPI_CIR_END` | 전용 GPIO 또는 선택적 `SPI_ACTIVE` profile | accumulator SPI transfer wrapper만 포함 |
| `spi_config_duration` | `TRACE_SPI_CONFIG_START` | `TRACE_SPI_CONFIG_END` | 전용 GPIO 또는 선택적 `SPI_ACTIVE` profile | configuration-write wrapper 전체 |
| `uart_record_encode_duration` | `TRACE_UART_ENCODE_START` | `TRACE_UART_ENCODE_END` | software timestamp 또는 전용 GPIO | serialization/CRC만 포함 |
| `uart_enqueue_duration` | `TRACE_UART_ENQUEUE_START` | `TRACE_UART_ENQUEUE_END` | `UART_ENQUEUE` | ring-buffer enqueue만 포함; physical TX 제외 |
| `uart_api_call_duration` | `TRACE_UART_API_START` | `TRACE_UART_API_END` | software timestamp 또는 전용 GPIO | API 호출 자체. ISR에서는 blocking API를 호출하지 않음 |
| `uart_driver_tx_window` | `TRACE_UART_TX_START` | `TRACE_UART_TX_END` | marker GPIO | driver가 정의한 TX 구간; 물리 선 시간과 같다고 가정하지 않음 |
| `uart_physical_tx_duration` | UART TX 선의 첫 start bit | 마지막 byte의 stop bit 종료 | 실제 `UART_TX` 선 | analyzer waveform 기준. marker GPIO로 대체하지 않음 |
| `uart_end_to_end_host_arrival` | versioned firmware record-ready timestamp | `TRACE_UART_HOST_ARRIVAL` host monotonic timestamp | binary record + host capture metadata | clock mapping/offset을 명시해야 함. RF timestamp로 사용 금지 |
| `cir_read_duration` | `TRACE_CIR_READ_START` | `TRACE_CIR_READ_END` | `CIR_READ` | 정의된 CIR capture 함수 전체. 내부 `spi_cir_duration`과 중복될 수 있음 |
| `cir_signed_decode_duration` | `TRACE_CIR_DECODE_START` | `TRACE_CIR_DECODE_END` | software timestamp 또는 전용 GPIO | dummy-byte 제거와 signed sample 변환 |
| `phase_processing_duration` | `TRACE_PHASE_START` | `TRACE_PHASE_END` | `PHASE_PROCESS` | extraction, combination 및 명시된 pipeline 단계. filter 포함 여부는 run metadata에 기록 |
| `phase_extraction_duration` | `TRACE_PHASE_EXTRACT_START` | `TRACE_PHASE_EXTRACT_END` | software timestamp 또는 전용 GPIO | phase extraction만 포함 |
| `phase_combination_duration` | `TRACE_PHASE_COMBINE_START` | `TRACE_PHASE_COMBINE_END` | software timestamp 또는 전용 GPIO | phase combination만 포함 |
| `filter_duration` | `TRACE_FILTER_START` | `TRACE_FILTER_END` | 전용 GPIO 또는 software timestamp | median/filter update만 포함 |
| `result_packaging_duration` | `TRACE_RESULT_PACKAGE_START` | `TRACE_RESULT_PACKAGE_END` | software timestamp 또는 전용 GPIO | result record 구성만 포함 |
| `tx_prepare_duration` | `TRACE_TX_PREP_START` | `TRACE_TX_ARMED` | 전용 GPIO 또는 software timestamp | delayed-TX preparation부터 arm 완료까지 |
| `logger_duration` | `TRACE_LOG_START` | `TRACE_LOG_END` | software timestamp 또는 전용 GPIO | deferred logger work. RF critical path와 분리 |
| `frame_active_duration` | `TRACE_FRAME_START` | `TRACE_FRAME_END` | frame marker GPIO | 한 frame의 명시된 active 처리 구간 |
| `frame_period` | frame N의 `TRACE_FRAME_START` | frame N+1의 `TRACE_FRAME_START` | frame marker GPIO | complete-frame rate가 아니라 해당 marker의 period |

`phase_processing_duration`과 하위 단계의 합이 항상 같다고 가정하지 않는다. 함수 호출 overhead와 명시되지 않은 packaging 단계가 있을 수 있다. `cir_read_duration` 역시 `spi_cir_duration`과 signed decode를 어떤 경계로 감쌌는지 run metadata에 남긴다.

## Logic channel mapping

`configs/local_hardware.yaml`의 다음 값은 모두 `TODO_USER_INPUT` 또는 `TODO_HW_VERIFY`이며 실제 연결 전에 사용자가 채워야 한다.

| Config key | 물리 신호 | 확인 방법 |
|---|---|---|
| `logic_analyzer.device_id` | 사용할 analyzer 식별자 | backend discovery 결과와 장비 라벨 대조 |
| `logic_analyzer.sample_rate_hz` | digital capture sample rate | 가장 짧은 pulse에 충분한 sample 수가 있는지 검증; 값은 `TODO_HW_VERIFY` |
| `logic_analyzer.channels.IRQ_PIN` | DW3000 IRQ physical line | schematic 및 board pinmux 확인 |
| `logic_analyzer.channels.ISR_ACTIVE` | ISR entry/exit route GPIO | generated route와 header pin 연속성 확인 |
| `logic_analyzer.channels.SPI_STATUS` | SPI status metric route GPIO | status wrapper route와 probe 연결 대조 |
| `logic_analyzer.channels.SPI_FRAME` | SPI frame metric route GPIO | frame wrapper route와 probe 연결 대조 |
| `logic_analyzer.channels.UART_ENQUEUE` | enqueue route GPIO | firmware route와 probe 연결 대조 |
| `logic_analyzer.channels.UART_TX` | 실제 UART TX physical line | board schematic와 idle level 확인 |
| `logic_analyzer.channels.CIR_READ` | CIR start/end route GPIO | firmware route와 probe 연결 대조 |
| `logic_analyzer.channels.PHASE_PROCESS` | phase start/end route GPIO | firmware route와 probe 연결 대조 |

하나의 aggregate `SPI_ACTIVE` GPIO에 여러 SPI event pair를 동시에 매핑하는 custom profile을 사용하면 pulse만으로 subtype을 식별할 수 없다. 기본 config처럼 `SPI_STATUS`/`SPI_FRAME`을 분리하거나 다음 중 하나를 선택하고 run metadata에 남긴다.

1. metric family마다 별도 GPIO/logic channel을 사용한다.
2. 한 번의 capture에서 SPI event pair 하나만 enable하는 profile을 사용한다.
3. software event record와 frame/slot context로 waveform pulse를 상관시킨다. 이 경우 clock mapping 오차를 별도 보고한다.

## 연결 안전 절차

1. 모든 보드와 analyzer 전원을 끄고 연결 대상 pin 이름, pin 번호, I/O 전압을 schematic 및 board manual로 확인한다.
2. analyzer 입력 허용 전압과 board I/O 전압이 호환되는지 확인한다. 확인 전에는 probe를 연결하지 않는다.
3. analyzer GND와 board GND 사이 전위차가 없는지 확인한 뒤 GND를 먼저 연결한다. 여러 USB/J-Link 전원에서 ground loop 또는 back-power가 생기지 않는지 확인한다.
4. logic analyzer probe는 입력으로만 사용한다. GPIO, IRQ, SPI, UART 선을 analyzer/adapter가 구동하지 않도록 한다.
5. analyzer의 VCC/전원 pin을 board 전원에 연결하지 않는다. 별도 level shifter가 필요한지 먼저 판단한다.
6. 인접 header pin을 probe clip으로 단락하지 않도록 전원이 꺼진 상태에서 continuity와 채널 대응을 확인한다.
7. `IRQ_PIN`은 실제 DW3000 IRQ 선에, `ISR_ACTIVE`는 별도 trace GPIO에 연결한다. 두 신호를 같은 GPIO로 대체하지 않는다.
8. UART physical duration을 측정할 때는 board TX를 analyzer input에만 연결한다. USB-UART RX/TX 교차 연결과 logic probe 연결을 혼동하지 않는다.
9. 전원 인가 후 먼저 idle level과 과전압/발열/비정상 전류를 확인하고, 그 다음 한 채널씩 signal activity를 확인한다.
10. 종료 시 signal probe를 먼저 제거하고 공통 GND는 마지막에 제거한다.

## Capture와 분석 기록 규칙

- raw capture를 덮어쓰거나 삭제하지 않는다. 새 run ID 아래 저장한다.
- run manifest에 backend, analyzer ID, firmware/config hash, sample rate, threshold/logic level, channel map, probe point, trace build flags를 기록한다.
- actual capture만 `source_type=MEASURED` 후보가 될 수 있다. 장비가 열렸다는 사실만으로 `hardware_verified=true`로 바꾸지 않는다. 연결과 데이터 품질 acceptance가 모두 통과해야 한다.
- synthetic CSV/VCD와 mock backend 결과에는 항상 `source_type=SYNTHETIC`, `hardware_verified=false`를 기록한다.
- missing edge, overlapping pulse, invalid pair, capture truncation, counter overflow, software probe drop을 숨기지 않고 오류 table에 남긴다.
- software timestamp tick frequency, wrap width, monotonicity와 GPIO callback overhead를 실제 보드에서 별도 측정한다.
- trace overhead는 tracing off/on 두 build의 동일 workload를 비교하고 compiler optimization, event 수, mapping profile을 함께 기록한다. 아직 overhead 수치는 없다.

## 검증된 결과

- 지시서에 정의된 필수 event 21개의 이름과 ID를 `trace_events.h`에 고정했다.
- 공통 계측 구현에는 vendor GPIO/DW3000 header, 동적 할당, stdio, sleep 호출이 없다.
- 기본 비활성 호출은 인자를 평가하지 않는 no-op macro이며, 활성 빌드에 route가 없어도 null backend로 실행 가능하다.
- pytest는 trace event/API/no-op source contract를 정적으로 검증했다. Visual Studio x64 developer environment에서는 MSVC C11 warning-as-error로 trace-off, trace-on, software-timestamp 세 host 구성을 compile/run했다. 일반 PowerShell PATH에서는 compiler-dependent test 하나가 `SKIP`된다. 이는 embedded target build 또는 실제 GPIO timing 검증이 아니다.
- 현재 실제 보드와 logic analyzer capture는 존재하지 않는다. 따라서 이 문서에는 실측 timing 결과가 없다.

## 가정한 값

- 예시 route의 `active_high=1`은 설명용이며 실제 GPIO polarity가 아니다.
- 동일 start/end event pair가 같은 physical trace pin에 매핑된다는 예시는 board pin 가용성 확인 전 가정이다.
- software clock이 monotonic하고 ISR-safe하다는 것은 callback 구현자가 검증해야 하는 통합 전제다.
- 최소 pulse에 충분한 sample 수를 확보한다는 selection rule만 정했으며 sample rate 숫자는 가정하지 않았다.

## 논문 기반 근거

- 이 연결·지표 계약에는 논문에서 가져온 timing 수치나 pin mapping을 사용하지 않았다.
- event 목록과 지표 경계는 첨부 구현 지시서에 따른 software measurement definition이다. 향후 논문 수치를 비교할 때도 measured 값과 literature 값의 source를 분리한다.

## 추후 확인 필요

- `TODO(HW_VERIFY)`: A1/A2/T1/T2 각각에서 사용할 trace GPIO와 header pin, polarity, drive 설정
- `TODO(HW_VERIFY)`: DW3000 IRQ pin, IRQ active polarity와 MCU ISR entry hook 위치
- `TODO(HW_VERIFY)`: GPIO direct-write callback의 실제 instruction path와 trace overhead
- `TODO(HW_VERIFY)`: software clock source, tick frequency, wrap 및 read overhead
- `TODO(HW_VERIFY)`: UART baud/framing, physical TX boundary와 host arrival clock mapping
- `TODO(HW_VERIFY)`: SPI clock/mode와 status/frame/timestamp/CIR/config wrapper의 정확한 hook 위치
- `TODO(HW_VERIFY)`: logic analyzer model, input threshold, device ID, sample rate와 channel 번호
- `TODO(HW_VERIFY)`: all exit/error paths에서 active trace pin이 반드시 clear되는지 fault capture로 확인
- `TODO(HW_VERIFY)`: 실제 pulse의 missing/overlap 여부와 analyzer bandwidth 적합성
