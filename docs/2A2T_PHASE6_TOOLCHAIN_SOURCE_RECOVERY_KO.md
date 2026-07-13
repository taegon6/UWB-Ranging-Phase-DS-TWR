# Phase 6.2 레거시 SES·SDK 소스 복구 판정

기준 브랜치/커밋: `codex/phase6-2a2t-hil-firmware` / `5daed298524c0280da27ab87cd18c33232656296`

최종 판정: **LEGACY_BUILD_ENVIRONMENT_NOT_READY**

## 범위와 안전 상태

이 작업은 과거 build 환경의 **출처 증거 조사와 복구 게이트**만 수행했다. firmware protocol/scheduler, baseline initiator/responder, vendor runtime은 수정하지 않았다. 누락 source를 생성·복사하지 않았고 SES를 설치하지 않았으며 build/flash/erase/reset/RF/UART/logic analyzer도 실행하지 않았다.

모든 생성 JSON에는 `hardware_verified = false`와 코드 조사 source type을 기록했다. 따라서 이 문서는 DW3000 보드 동작 또는 실제 firmware build 성공을 주장하지 않는다.

## 1. 현재 build 실패 원인

Phase 6.1의 빈 Output sandbox 직접 compile은 실제 compiler 실행까지 도달했지만 SES 8.28에서 다음 지점에서 중단됐다.

```text
SEGGER_RTT_Syscalls_SES.c:58:10: fatal error: __vfprintf.h: No such file or directory
```

이는 stale HEX/ELF/MAP를 성공으로 인정하지 않은 결과다. 해당 시도는 ELF/HEX를 생성하지 못했고, baseline fresh build는 여전히 불가다.

## 2. 과거 환경 provenance

| 항목 | 확인된 증거 | 판정 |
| --- | --- | --- |
| target/config | sibling `dw3000_api.map`: `nRF52840_xxAA`, Debug | 과거 artifact 단서 |
| linker | `Setup/SEGGER_Flash.icf` | project/MAP 일치 |
| SES runtime | MAP library path의 `SEGGER Embedded Studio for ARM 5.68` | 5.68 흔적 확인 |
| 현재 설치 | SES 8.28만 존재, `emBuild.exe` SHA-256 `c299…c613` | exact 5.68 아님 |
| runtime contract | 8.28 include 경로에 `__vfprintf.h` 없음; local `SEGGER_RTT.h`, 8.28 `__libc.h`/`limits.h`는 존재 | **RUNTIME_HEADER_MISMATCH** |
| historical object | MAP에 custom object 이름이 남음 | stale 가능, fresh build 증거 아님 |

따라서 SES 5.68이라는 **historical version clue**는 얻었지만, 5.68 executable/installer hash가 현재 PC에서 확인되지 않았다. 이 상태는 `EXACT_TOOLCHAIN_IDENTIFIED`가 아니라 `TOOLCHAIN_FAMILY_IDENTIFIED`다.

추가로 `.emSession`에는 과거 `C:/work_tree_2/AoA_Project/...` 및 SES 5.68 include path 흔적이 있으나, PC/user/path 흔적은 source commit이나 설치 hash를 증명하지 않는다.

## 3. 15개 누락 source 추적

다음 표의 `MAP`은 historical object명이 있을 때만 `Y`이다. `후보`는 **정확한 filename**을 발견했다는 뜻일 뿐, target commit·include 관계·source hash가 연결되지 않아 복구용 source가 아니다. 어떠한 후보도 복사하지 않았다.

| source | 책임 분류 | 참조 상태 | MAP | 후보/결정 | 차단 |
| --- | --- | --- | --- | --- | --- |
| `custom_ds_twr_initiator.c` | custom DS-TWR initiator | inactive macro proven | N | 없음 | Y |
| `custom_ds_twr_responder.c` | custom DS-TWR responder | active/unresolved | N | 없음 | Y |
| `switching.c` | custom switching | active/unresolved | Y | 없음 | Y |
| `localization_ds_twr_initiatior.c` | custom localization initiator | inactive macro proven | Y | 없음 | Y |
| `localization_ds_twr_responder.c` | custom localization responder | inactive macro proven | Y | 없음 | Y |
| `AoA_rtls_tx.c` | custom AoA/RTLS | active/unresolved | Y | sibling exact filename, provenance unresolved | Y |
| `AoA_rtls_rx.c` | custom AoA/RTLS | active/unresolved | Y | sibling exact filename, provenance unresolved | Y |
| `AoA_rtls_tx_AI.c` | custom AoA/RTLS | active/unresolved | Y | sibling exact filename, provenance unresolved | Y |
| `AoA_rtls_rx_AI.c` | custom AoA/RTLS | active/unresolved | Y | sibling exact filename, provenance unresolved | Y |
| `UART_test.c` | custom UART experiment | active/unresolved | Y | 없음 | Y |
| `rx_diagnostics_cp.c` | custom diagnostics | active/unresolved | Y | 없음 | Y |
| `AoA_rtls_tx_txt.c` | custom AoA/RTLS | active/unresolved | Y | sibling exact filename, provenance unresolved | Y |
| `AoA_rtls_rx_txt.c` | custom AoA/RTLS | active/unresolved | Y | sibling exact filename, provenance unresolved | Y |
| `AoA_rtls_rx_two.c` | custom AoA/RTLS | active/unresolved | Y | sibling exact filename, provenance unresolved | Y |
| `AoA_rtls_tx_two.c` | custom AoA/RTLS | active/unresolved | Y | sibling exact filename, provenance unresolved | Y |

정확한 expected path, project reference, candidate path/SHA-256, archive ZIP member 검색, Git-history 여부, object 존재 여부는 [`missing_source_matrix.json`](../artifacts/phase6_toolchain_recovery/missing_source_matrix.json)에 source별로 보존했다.

`INACTIVE_REFERENCE_PROVEN`은 현재 selection macro가 정의되지 않았다는 제한된 사실만 뜻한다. source가 존재하거나 project entry를 제거해도 된다는 뜻이 아니므로, 이번 작업에서는 해당 entry를 제거하지 않았다.

## 4. source tree 판정

현재 상태는 **MIXED_INCOMPLETE_OVERLAY_OR_SNAPSHOT**으로 판정한다. 즉 incomplete checkout, 별도 custom/proprietary package 누락, stale project reference가 혼재했을 가능성은 있으나 어느 하나가 증명되지는 않았다. `.gitmodules` 부재만으로 submodule 누락을 배제할 수 없고, generated source라는 근거도 없다. 15개 모두가 blocking이므로, family-level SES 단서가 있어도 최종 환경은 NOT_READY다.

특히 sibling `UWB_AoA_Project`에서 찾은 8개 exact-named source는 target sandbox의 commit/headers/selection/include graph와 일치한다는 증거가 없다. source origin이 명확하지 않은 source를 복사하지 않는 정책상 모두 blocking으로 유지한다.

## 5. source hash 불변성

기존 baseline manifest의 다음 두 hash를 현재 working tree에서 다시 계산했고 일치했다.

| 파일 | SHA-256 | 결과 |
| --- | --- | --- |
| `firmware_overlay/API/Src/custom_code/ds_twr_initiator_final.c` | `bb0dafc5…d0ab389` | unchanged |
| `firmware_overlay/API/Src/custom_code/ds_twr_responder_final.c` | `d0a63c48…8a417d4` | unchanged |

검증 상세는 [`historical_build_provenance.json`](../artifacts/phase6_toolchain_recovery/historical_build_provenance.json)에 있다. 이 hash 검증은 source 보존만 말하며 build 가능성을 뜻하지 않는다.

## 6. 복구 route 비교

| 우선순위 | route | 허용 조건 | 현재 상태 |
| --- | --- | --- | --- |
| A | exact legacy reproduction | SES 5.68 installer/executable hash, 완전한 origin-proven source, pin된 SDK commit | 차단 |
| B | compatible legacy toolchain | 동일 runtime/header contract를 hash로 입증 | 차단 |
| C | SES 8.28 migration | A/B 불가 시 diff·영향 목록만 작성 | 계획 전용 |

Route A가 유일한 우선 경로다. 필요한 설치본은 **SES 5.68 exact installer/version**이며, 확보 후 기존 8.28을 덮어쓰지 않는 side-by-side 설치와 `emBuild.exe` SHA-256 기록이 필요하다. 자동 설치는 수행하지 않았다.

Route C의 사전 분석 결론은 `SEGGER_RTT_Syscalls_SES.c`의 legacy private runtime header 의존, SES project schema/compiler/linker 변화, printf/float/runtime binary-size 및 timing 변화 가능성이다. migration source 수정은 이번 범위 밖이다.

## 7. baseline 및 four-image gate

`recovery_plan.json`의 실행 권한은 모두 false다.

```text
allow_baseline_build   = false
allow_four_image_build = false
allow_flash_execute    = false
allow_execute          = false
```

baseline fresh build를 한 번만 허용하는 선행 조건은 (1) source 15개 전체의 origin/hash/inclusion relationship 확정, (2) exact 또는 runtime-contract-compatible SES 확보, (3) empty Output에서 compile command·새 object·ELF·HEX·timestamp·SHA-256를 모두 확인하는 것이다. 하나라도 빠지면 four-image build도 flash도 진행하지 않는다.

## 8. 추가 테스트와 결과

`tests/test_phase6_toolchain_source_recovery.py`에 다음 gate를 추가했다.

- 15 source scope 고정
- exact toolchain version mismatch 거부
- duplicate candidate hash ambiguity 거부
- candidate hash mismatch 및 placeholder/stub 거부
- inactive reference와 truly unresolved reference 구분
- legacy runtime header mismatch
- baseline/2A2T hash invariant 변조 탐지
- provenance 부족 시 baseline/four-image/flash 및 `allow_execute` 차단

수정 전: 신규 test module import 실패(구현 전 expected failure).

수정 후: recovery tests `10 passed`; 기존 SES/build/flash gate 포함 `23 passed`.

최종 pytest는 안정적으로 분리 실행했다. pipeline 외 test와 pipeline test를 각각 실행해, 합계 **`154 passed, 1 skipped`**를 확인했다. skip은 기존 테스트의 상태이며 assertion을 삭제하거나 완화하지 않았다.

## 9. 남은 차단 항목과 다음 조치

1. SES 5.68 설치본의 공식 또는 조직 내 provenance, installer SHA-256, executable SHA-256를 확보한다.
2. 15 source 각각의 original archive/commit/path와 expected SHA-256를 확보한다. sibling source의 파일명 일치만으로는 충분하지 않다.
3. exact SDK/Nordic/Qorvo/DW3000 API archive hash 및 complete source-tree manifest를 확보한다.
4. 이후 isolated sandbox에서 **baseline initiator 하나**만 fresh build한다. successful build 전 four-image/flash는 금지다.

## 산출물

- [`toolchain_evidence.json`](../artifacts/phase6_toolchain_recovery/toolchain_evidence.json)
- [`missing_source_matrix.json`](../artifacts/phase6_toolchain_recovery/missing_source_matrix.json)
- [`historical_build_provenance.json`](../artifacts/phase6_toolchain_recovery/historical_build_provenance.json)
- [`source_tree_candidates.json`](../artifacts/phase6_toolchain_recovery/source_tree_candidates.json)
- [`recovery_plan.json`](../artifacts/phase6_toolchain_recovery/recovery_plan.json)
- [`investigation_log.json`](../artifacts/phase6_toolchain_recovery/investigation_log.json) 및 [`artifact_inventory.json`](../artifacts/phase6_toolchain_recovery/artifact_inventory.json)
