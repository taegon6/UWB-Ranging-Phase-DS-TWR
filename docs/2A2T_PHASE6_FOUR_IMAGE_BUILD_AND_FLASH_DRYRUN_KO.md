# Phase 6 4-image build 및 flash dry-run 결과

## 범위와 상태

```text
source_type = CODE_INSPECTION_AND_BUILD
hardware_verified = false
flash_executed = false
```

이 문서는 실제 DW3000/DWS3000 보드, J-Link, UART, RF 통신 또는 logic analyzer를 사용한 결과가 아니다. `--execute`, erase, reset, flash 명령은 실행하지 않았다.

## 고정한 source / SDK baseline

| 항목 | 값 |
|---|---|
| Firmware branch / 시작 commit | `codex/phase6-2a2t-hil-firmware` / `590ec11f75c681e9cffe54adc4a0db8ddacea697` |
| SDK 원본 | `research/uwb_followup/original_repos/UWB-Ranging-Optimization` |
| SDK fixed commit | `3fdc9e93970bdad62549ab1fe48e33c5e8a13136` |
| SDK project | `API/nRF52840-DK/dw3000_api.emProject` |
| Target / config | `nRF52840_xxAA` / `Debug` |
| Toolchain | SEGGER Embedded Studio 8.28 (`emBuild.exe`) |
| baseline initiator SHA-256 | `f5c6bd2d464d3bbb172281136ca24eadc723f0b4decaa4efee645081ee91b486` |
| baseline responder SHA-256 | `27f72cb4b1fcc0c1fbf0c07c57a07b1893fbaa76fbddd60cda80fa06eb37b15a` |

원본 SDK working tree는 11,994개의 dirty/staged 상태가 검출되어 빌드하거나 수정하지 않았다. 대신 위 SDK commit의 detached `git worktree` 4개를 `research/uwb_followup/build_sandboxes/phase6_2a2t_3fdc9e9_attempt02/`에 생성했다.

참고로 dirty upstream의 현재 두 source hash는 각각 `8a68a199...52262`, `86fe3ec...4750f`로 clean commit baseline과 다르다. 이는 작업 시작 전의 upstream dirty 상태이며 이 작업에서 변경하지 않았고, build/overlay 기준으로 사용하지 않았다.

## Overlay 방식

`tools/prepare_phase6_sdk_sandbox.py`가 clean worktree에만 다음 canonical overlay를 복사하고, project include path / source 등록 / example registration / role define를 결정적으로 적용한다.

- `ds_twr_2a2t_tag.c`, `ds_twr_2a2t_anchor.c`
- `uwb_2a2t_config.h`, `uwb_2a2t_protocol.h`
- `uwb_2a2t_trace.h`, `uwb_2a2t_trace.c`
- `uwb_2a2t_build_identity.h` (role 별 FWID 생성)

전체 overlay SHA-256은 `bdd6d2436def38b32d8e0a7171b2c2b0d58340c909e866f6f43a3c3497b6ba41`이다. 네 role 각각에서 baseline 두 C 파일의 before/after hash가 동일함을 기록했다. 상세 manifest는 [overlay_manifest.json](../artifacts/phase6_build/overlay_manifest.json)에 있다.

| image_id | node | role | FWID identity |
|---|---:|---|---|
| `anchor_a1` | A1 | ANCHOR | node=A1, role=ANCHOR |
| `anchor_a2` | A2 | ANCHOR | node=A2, role=ANCHOR |
| `tag_t1` | T1 | TAG_COORDINATOR | node=T1, role=TAG_COORDINATOR |
| `tag_t2` | T2 | TAG_FOLLOWER | node=T2, role=TAG_FOLLOWER |

FWID에는 `source_git`, `overlay_sha256`, `config_sha256`, `build_timestamp`도 포함한다. HEX만으로 FWID를 검증할 수 없을 경우 ELF 문자열 검증을 요구하며, 검증할 ELF가 없으면 성공으로 처리하지 않는다.

## Build 명령 및 결과

실제 시도 command는 다음과 같다.

```powershell
& "C:\Program Files\SEGGER\SEGGER Embedded Studio 8.28\bin\emBuild.exe" -batch -clean -config Debug <sandbox>\API\nRF52840-DK\dw3000_api.emProject
& "C:\Program Files\SEGGER\SEGGER Embedded Studio 8.28\bin\emBuild.exe" -batch -rebuild -config Debug <sandbox>\API\nRF52840-DK\dw3000_api.emProject
```

`emBuild`는 이 project에서 0을 반환했어도 fresh HEX/ELF를 만들지 않거나 `-clean` 뒤 `Output/Debug`에 generated 파일을 남겼다. 따라서 orchestration은 반환 코드만으로 성공으로 처리하지 않고 stale output을 거부했다.

| image_id | 결과 | HEX SHA-256 | FWID binary 검증 |
|---|---|---|---|
| anchor_a1 | `BUILD_FAILED` — clean 후 stale output | 없음 | 불가 |
| anchor_a2 | `BUILD_FAILED` — clean 후 stale output | 없음 | 불가 |
| tag_t1 | `BUILD_FAILED` — clean 후 stale output | 없음 | 불가 |
| tag_t2 | `BUILD_FAILED` — clean 후 stale output | 없음 | 불가 |

추가로 `emBuild -show`가 project에 존재하지 않는 source를 보고했다: `API/Src/urop_2/custom_ds_twr_initiator.c`, `custom_ds_twr_responder.c`, `API/Src/custom_code/switching.c`, `localization_ds_twr_initiatior.c`, `localization_ds_twr_responder.c`. baseline source를 임의로 추가·수정하지 않았으므로 이 문제는 SDK/project blocking issue로 남긴다.

결과 manifest: [attempt02 build_manifest.json](../artifacts/phase6_build_attempt02/build_manifest.json), [required build_manifest.json](../artifacts/phase6_build/build_manifest.json). 두 manifest 모두 `BUILD_FAILED`이며, 이전 생성물은 image로 재사용하지 않았다.

## Flash dry-run

`configs/local_hardware.phase6.template.yaml`은 모든 J-Link serial과 UART port를 `UNRESOLVED`로 유지하며 `allow_execute: false`를 강제한다. device는 네 node 모두 `nRF52840_xxAA`이다.

계획 순서는 `A1 -> A2 -> T2 -> T1`이고, T1 coordinator를 마지막에 둔다. build가 실패했으므로 [flash_plan.json](../artifacts/phase6_flash/flash_plan.json)은 `FLASH_PLAN_BLOCKED_BUILD_FAILURE`이다. image SHA-256은 모두 `null`이고 executable command는 없다. [flash_plan_review.md](../artifacts/phase6_flash/flash_plan_review.md)를 함께 확인한다.

## Offline 검증

- clean SDK requirement, stale output rejection, 4-image manifest 형상
- FWID role mismatch rejection 및 image/FWID artifact 존재 확인
- duplicate concrete J-Link serial / UART port rejection
- wrong MCU target / wrong image mapping / `allow_execute=true` rejection
- A1 → A2 → T2 → T1 order, stop-on-first-failure, deterministic plan SHA-256
- 기존 flash plan의 image hash tamper / approval hash rejection

전체 pytest는 도구 실행 상한 때문에 두 구간으로 실행했으며, 합계 `140 passed, 1 skipped`다.

```text
python -m pytest -q --ignore=tests/test_phase5_phase6_pipeline.py  # 134 passed, 1 skipped
python -m pytest tests/test_phase5_phase6_pipeline.py -q           # 6 passed
python tools/check_environment.py                                  # PASS (hardware probe는 의도적으로 SKIP)
```

## 미해결 사항과 다음 단계

1. 이 SDK project의 정상 CLI build invocation과 `emBuild -clean` 동작을 vendor/SDK 기준으로 해결해야 한다.
2. project가 참조하지만 repository에 없는 5개 source의 provenance를 확인해야 한다. 임의 placeholder 추가는 금지한다.
3. 네 image가 fresh HEX와 ELF/FWID 검증을 모두 통과한 뒤에만 flash plan을 `HARDWARE_MAPPING_REQUIRED`로 승격할 수 있다.
4. 그 다음에만 사용자가 A1/A2/T1/T2 J-Link serial, UART COM port, board-to-node mapping, GPIO/IRQ trace wiring을 입력한다.

## 판정

`FOUR_IMAGE_BUILD_NOT_READY`

근거: 네 실제 image의 fresh HEX/ELF/FWID 검증이 모두 실패했고, SDK/project source 누락 및 CLI clean 동작이 해결되지 않았다. 실제 flash는 계속 금지다.
