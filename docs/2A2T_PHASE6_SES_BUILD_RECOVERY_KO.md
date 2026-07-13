# Phase 6.1 SEGGER Embedded Studio build recovery

## 상태

```text
source_type = CODE_INSPECTION_AND_BUILD
hardware_verified = false
flash_executed = false
```

실제 flash, erase, reset, RF/UART 통신, logic analyzer 측정은 수행하지 않았다. firmware protocol/scheduler source도 변경하지 않았다.

## 1. 기존 실패 재현과 stale output 원인

기존 wrapper는 다음 command를 사용했다.

```powershell
emBuild.exe -batch -rebuild -config Debug dw3000_api.emProject
```

`emBuild -batch`는 batch-build로 표시된 project만 대상으로 한다. 이 `.emProject`에는 해당 표시가 없어 exit code `0`, 빈 stdout/stderr, HEX/ELF 없음이라는 false-success가 발생했다. 직접 build로 바꾼 command는 다음과 같다.

```powershell
emBuild.exe -rebuild -echo -verbose -config Debug dw3000_api.emProject
```

이 command에서는 실제 compile command가 출력되고 exit code `1`이 재현됐다. 따라서 `-batch`는 Phase 6 wrapper에서 제거했다.

기존 `Output/Debug/Obj/dw3000_api`의 네 파일은 stale build output처럼 보이지만 SDK commit `3fdc9e9`에 **추적된 파일**이다. SES `-clean`이 추적 파일을 지우지 않는 것이 정상이며, SHA-256은 다음과 같다.

| tracked path | SHA-256 |
|---|---|
| `AoA_rtls_tx_cp.asm` | `28473690e816c5285ef8f7e89635a479eff3121c428bfd31c5a6efac625e8b94` |
| `app_error_PP.c` | `7c61b8bad63b2698b121faa295909701df005b38b957791be78d8b0b7c9d5999` |
| `dw3000_api.ind` | `9acef938b0cc122be0a9ad60fc8a82c421fec0c322233be0ca0fed6f397703c4` |
| `dw3000_api.ld` | `447ef3105430805b877cd94103e4c46c08e4f8417c3428b38d7f483727dcd4e8` |

해결 방식은 fixed commit detached worktree에서 non-cone sparse checkout으로 `API/nRF52840-DK/Output/`만 제외하는 것이다. 이 방식은 원본 파일을 삭제하거나 dirty upstream을 사용하지 않고 빈 output으로 시작한다. resolved path와 reparse-point 검사 결과는 worktree/project/output 모두 symlink/junction이 아니다.

## 2. 실제 SES project 설정

| 항목 | 확인값 |
|---|---|
| project | `API/nRF52840-DK/dw3000_api.emProject` |
| configurations | `Debug`, `Release` |
| target | `nRF52840_xxAA`, Cortex-M4, SWD |
| output | project default `Output/Debug`; `linker_output_format=hex` |
| linker | `Setup/SEGGER_Flash.icf`, `flash_placement.xml` |
| SDK macro | `NordicSDKDir=sdk` |
| pre/post/custom copy | 설정 없음 |
| external project dependency | 설정 없음 |

Debug와 Release는 define/optimization만 다르고 output directory 속성은 별도로 지정하지 않는다. Debug는 `DEBUG`, Level 3, O0이고 Release는 `NDEBUG`, Level 1이다. full source/include/define manifest는 [project_dependency_manifest.json](../artifacts/phase6_build_recovery_attempt03/project_dependency_manifest.json)에 있다.

## 3. 누락 source 분석

요청된 다섯 project reference는 모두 source tree, repository history, sibling SDK file search, `.gitmodules`에서 source를 찾지 못했다. Nordic/Qorvo vendor 기본 source나 nRF52840 BSP source로 확인되지 않았다.

| reference / project line | selection guard | 판단 |
|---|---|---|
| `urop_2/custom_ds_twr_initiator.c` / 84 | `CUSTOM_DS_TWR_INITIATOR` | user custom DS-TWR, `BLOCKING_UNRESOLVED` |
| `urop_2/custom_ds_twr_responder.c` / 85 | `CUSTOM_DS_TWR_RESPONDER` | user custom DS-TWR, `BLOCKING_UNRESOLVED` |
| `custom_code/switching.c` / 92 | 없음 | historical custom switching, `BLOCKING_UNRESOLVED` |
| `custom_code/localization_ds_twr_initiatior.c` / 93 | `LOCALIZATION_DS_TWR_INIT` | user localization mode, `BLOCKING_UNRESOLVED` |
| `custom_code/localization_ds_twr_responder.c` / 94 | `LOCALIZATION_DS_TWR_RESP` | user localization mode, `BLOCKING_UNRESOLVED` |

`UWB_AoA_Project`의 과거 map에는 `switching.o` 및 localization object가 존재해 과거 custom source였다는 증거는 있지만, 현재 source/provenance를 복원할 근거는 아니다. 해당 object/HEX/MAP은 stale artifact이므로 build에 사용하지 않았다.

baseline initiator를 선택한 disposable sandbox에서만, 위 다섯 file reference는 inactive selection guard를 확인한 뒤 project에서 제거했다. placeholder/stub source는 만들지 않았다. 이 조치는 custom/localization mode를 복원하지 않으며, 2A2T build에는 아직 적용하지 않는다. 추가로 AoA/UART/rx diagnostics 관련 10개 누락 reference도 발견되어 full project provenance는 여전히 불완전하다.

## 4. baseline fresh-build 결과

authoritative attempt: [build_attempt_manifest.json](../artifacts/phase6_build_recovery_attempt03/build_attempt_manifest.json), [full build log](../artifacts/phase6_build_recovery_attempt03/build_logs/baseline_initiator.log), [missing report](../artifacts/phase6_build_recovery_attempt03/missing_sources_report.json).

| gate | 결과 |
|---|---|
| clean source | fixed commit `3fdc9e93970bdad62549ab1fe48e33c5e8a13136` detached worktree |
| output before build | empty |
| compile command | present (`cc1.exe`) |
| target/config | `nRF52840_xxAA` / Debug |
| HEX / ELF / MAP | 없음 |
| partial output | zero-byte `.asm` 6개; rejected |
| exit code | 1 |
| baseline marker / SHA | ELF가 없어 검증 불가 |

실패 지점은 `SEGGER_RTT_Syscalls_SES.c:58`의 `#include "__vfprintf.h"`다. 현재 설치된 SES는 8.28뿐이고, sibling successful map은 `SEGGER Embedded Studio for ARM 5.68`의 runtime library 경로를 기록한다. 즉 현재 8.28 toolchain은 project가 마지막으로 성공한 것으로 보이는 5.68 runtime과 호환되는지 확인되지 않았다. 내부 runtime header를 복사하거나 임의 include path를 추가하지 않았다.

## 5. four-image / flash 상태

baseline fresh build gate가 실패했으므로 A1/A2/T1/T2 four-image build를 다시 시도하지 않았다. 기존 flash plan은 계속 `FLASH_PLAN_BLOCKED_BUILD_FAILURE`, `allow_execute=false`이며 실제 J-Link command는 실행하지 않았다.

## 6. 다음 재현 절차

1. source commit `3fdc9e9`의 새 detached worktree를 만든다.
2. sparse checkout으로 `API/nRF52840-DK/Output/`을 제외한다.
3. SES **5.68** 설치본 또는 해당 project가 요구하는 runtime source의 정당한 provenance를 확보한다.
4. 새 sandbox에서 `python tools/phase6_ses_recovery.py ...`를 실행한다.
5. baseline HEX/ELF/MAP, marker, SHA, timestamp gate가 모두 통과한 뒤에만 four-image sandbox를 새로 만든다.

검증은 `144 passed, 1 skipped`였다. 전체 suite는 실행 상한 때문에 `tests/test_phase5_phase6_pipeline.py`를 분리해 실행했으며, `python tools/check_environment.py`도 통과했다(미연결 hardware probe는 의도적으로 SKIP).

## 최종 판정

`BASELINE_FRESH_BUILD_NOT_READY`

blocking issue는 (1) SES 5.68 runtime/toolchain provenance 부재, (2) 총 15개 missing custom project references의 provenance 부재다. 이들이 해결되기 전 actual flash는 금지한다.
