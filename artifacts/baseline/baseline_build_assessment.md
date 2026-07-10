# Firmware baseline build assessment

## 검증된 결과

- 기준 저장소는 `ekf` / `b8b911f6d437af9cb70c09f1b4f4562feb0239ac`에서 변경 전 clean 상태였다.
- 이 저장소에는 `firmware_overlay/`의 C/H 파일 4개와 host-side 도구만 있으며, 완전한 SDK/build tree는 없다.
- 연결 가능한 상류 SDK 후보는 workspace의 `research/uwb_followup/original_repos/UWB-Ranging-Optimization/`에 보존되어 있다.
- 로컬에는 SEGGER J-Link executable이 설치되어 있으나 이번 단계에서는 장치 검색이나 실행을 하지 않았다.

## 추후 확인 필요

- 기준 저장소만으로 firmware image를 생성할 build target은 없다.
- 상류 SDK 후보 working tree는 대규모 index/worktree 불일치 상태이므로 사용자가 정리 또는 재확인하기 전에는 overlay 적용/build에 사용하지 않는다.
- `make`, `cmake`, `arm-none-eabi-gcc`, `nrfjprog`가 현재 PATH에 없다.
- nRF52840 build는 상류의 `API/nRF52840-DK/dw3000_api.emProject`를 사용하는 것으로 보이지만 실제 toolchain/build command는 확인이 필요하다.

## 이번 단계 판단

기존 firmware 파일은 수정하지 않고 SHA-256 snapshot으로 보존한다. Firmware build는 실제 성공으로 기록하지 않으며, A1/A2/T1/T2 orchestration은 command/config/image mapping의 mock dry-run으로만 검증한다.

`hardware_verified = false`

## 가정한 값

- 없음. Build target, toolchain compatibility, image path와 device mapping은 unresolved 상태로 유지했다.

## 논문 기반 근거

- 없음. Build 가능성 판단에 논문 수치나 외부 성능값을 사용하지 않았다.
