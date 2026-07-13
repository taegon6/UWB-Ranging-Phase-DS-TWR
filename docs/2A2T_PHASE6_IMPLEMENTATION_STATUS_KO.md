# 2A2T Phase 6 구현 상태

기준 branch: `codex/phase6-2a2t-hil-firmware`
구현 상태: `PRE_HARDWARE_IMPLEMENTED`
실제 hardware 검증 상태: `NOT_STARTED`

## 구현한 항목

- 기존 baseline `ds_twr_initiator_final.c`, `ds_twr_responder_final.c`를 보존하고, 파생 source `ds_twr_2a2t_tag.c`, `ds_twr_2a2t_anchor.c`를 추가했다.
- 고정 slot 순서 `A1-T1 → A2-T1 → A1-T2 → A2-T2`와 동일 exchange sequence echo를 구현했다.
- T1은 slot 0/1을 실행하고 A2→T2 Report token을 기다리며, T2는 A2→T1 Report token 전에는 TX하지 않는다.
- 수신 frame은 최소 길이, destination, source, function, sequence를 모두 확인한다. 실패와 token loss는 retry TX가 아니라 fail-closed wait 상태로 처리한다.
- Final bytes 26-31에 protocol version, slot, superframe ID를 넣되 Final data length 32 B / on-air PSDU 34 B를 유지한다.
- phase/CIR은 bootstrap profile에서 off이며 `corrected_distance=raw_distance` 정책이다.
- 64-byte packed trace ring, CRC16, non-blocking UART/DMA submit interface 및 4-slot host assembler를 추가했다. Board-specific UART DMA와 GPIO pin mapping은 SDK port 단계에서 연결해야 한다.
- `set_uwb_example.py`에 `ds-2a2t-anchor-a1`, `ds-2a2t-anchor-a2`, `ds-2a2t-tag-t1`, `ds-2a2t-tag-t2`를 추가했다.
- build는 빈 output directory, per-role FWID marker, immutable image copy, SHA-256, build log를 요구한다.
- flash는 A1→A2→T2→T1 순서이며 image SHA와 J-Link command가 포함된 `plan_sha256` 승인 없이는 실행하지 않는다. 기본 full erase는 사용하지 않는다.

## Baseline 보존

[baseline_firmware_manifest.json](../artifacts/phase6/baseline_firmware_manifest.json)에 다음 source hash를 동결했다.

| Baseline file | SHA-256 |
|---|---|
| `ds_twr_initiator_final.c` | `bb0dafc5f5a478a2481eeb6445e47629b91fd3be96054f50d60b34433d0ab389` |
| `ds_twr_responder_final.c` | `d0a63c4849720f898db54be71cc85a6a4280904f9934120c3d51e437f8a417d4` |

## 검증 범위

- Python protocol/scheduler, build selection, flash plan, trace decode golden test를 추가했다.
- 전체 pytest는 `131 passed, 1 skipped`였다. skip은 host에 C compiler가 없을 때 instrumentation compile test가 skip되는 기존 조건이다.
- mock hardware experiment와 antenna-delay calibration은 synthetic dry-run으로만 통과했다.

## 아직 하지 않은 것

- clean full SDK sandbox에 overlay를 적용한 SES/emBuild 4-image build
- 실제 A1/A2/T1/T2 J-Link/COM mapping 및 flash
- Report overhear/frame-filter policy 검증
- UART DMA submit 및 trace GPIO pin board port
- logic analyzer timing capture와 processing p99 측정
- antenna delay calibration 및 range accuracy 판정

위 항목은 아직 `MEASURED`, `hardware_verified=true`, 또는 실제 DW3000 성능으로 표현할 수 없다.

## 다음 실제 작업

1. clean commit-pinned SDK sandbox를 준비하고 overlay를 적용한다.
2. `example_selection.h`에서 네 role을 각각 선택해 A1/A2/T1/T2 image를 build한다.
3. image 내부 FWID marker, SHA-256, build log를 확인한다.
4. 실제 J-Link/COM mapping을 `configs/local_hardware.yaml`에 입력한다.
5. `flash_all.py --dry-run`으로 plan SHA를 검토한다.
6. 사용자가 해당 SHA를 승인한 뒤에만 guarded real flash를 실행한다.

`source_type = SOURCE_INSPECTION`
`hardware_verified = false`
