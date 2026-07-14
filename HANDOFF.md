# 2A2T UWB pre-hardware handoff

Final status: `SIMULATED_NOT_HARDWARE_VERIFIED`

```text
소프트웨어 실험환경 구축 완료
mock/dry-run 검증 완료
실제 보드 및 계측기 검증 대기
```

## Repository / baseline

- Repository: `taegon6/UWB-Ranging-Phase-DS-TWR`
- Branch/commit at baseline capture: `ekf` / `b8b911f6d437af9cb70c09f1b4f4562feb0239ac`
- Baseline evidence: `artifacts/baseline/`
- Current analysis: `artifacts/current_code_analysis.md`
- Baseline firmware overlay sources were not modified.
- Full upstream candidate is not clean/reproducible and was not changed.

## Reproduction

See `docs/EXPERIMENT_COMMANDS.md`. The required commands are environment check, mock timing/report, and calibration dry-run. Generated raw files stay under unique `results/` run folders.

## Config matrix

- `configs/mock_hardware.yaml`: deterministic software-only nominal/fault config.
- `configs/local_hardware.example.yaml`: copy to the ignored/local `configs/local_hardware.yaml` and resolve every TODO.
- `configs/experiment_timing.example.yaml`: standalone timing experiment contract.
- `configs/logic_channels.example.yaml`: channel mapping template.
- `configs/antenna_calibration.example.yaml`: separate hardware TODO and synthetic search spaces.

## HIL wiring and next action

Follow `docs/HARDWARE_CONNECTION_CHECKLIST.md` and `docs/LOGIC_ANALYZER_CONNECTION.md`. Recommended next experiment is not 2A2T RF operation: first obtain/repair a clean commit-pinned full SDK, reproduce the unchanged 2A1T baseline build, then perform four-port connection smoke without flash.

## 1. 현재 확정값과 source locator

| Item | Confirmed static value | Source | Hardware status |
|---|---|---|---|
| Baseline Git | `ekf` / `b8b911f6…` | `artifacts/baseline/git_status_before.txt` | not applicable |
| PHY | CH9, PLEN128, PAC8, codes 9/9, 6.8M, STS off | initiator:41-56; responder:51-65 | unverified |
| Topology | one `TG`, anchors `A1/B2` | initiator:67-73 | unverified |
| Flow | Poll/Response/Final/Post-Final/Report | `artifacts/current_code_analysis.md` | unverified |
| CIR read | 7 bytes at `ipatovFpIndex >> 6` | initiator:160,305-309; responder:180 | unverified |
| Median window | 20 | `shared_function_jang.h:48` | unverified |
| Mock provenance | `SYNTHETIC/false` | schema/tests/run manifests | software-tested |

## 2. 미확정값과 확인 방법

| Unresolved value | Why | Verification |
|---|---|---|
| Actual A1/A2/T1/T2 targets/images | overlay-only repo; no A2/T2 targets | clean SDK build manifest and hashes |
| J-Link/UART IDs | devices absent | one-board-at-a-time discovery |
| UART baud/framing | dirty upstream code inspection only | approved firmware config + identity capture |
| GPIO/channel/sample rate | no wiring/schematic mapping approved | checklist, pinmux review, pilot capture |
| SPI/IRQ/UART/CIR timing | no measured waveform | defined event-pair logic capture |
| Antenna delay/search range | no reference-distance data | multi-distance raw collection and validation |
| CIR ownership | undocumented hardware behavior | accumulator-before/after-next-RX experiment |

## 3. Protocol/ranging/operation support matrix

| Protocol / ranging | APPROACH | FINE_ALIGNMENT | FINAL_CONFIRMATION | Current status |
|---|---|---|---|---|
| Current A1/B2 phase 2A1T | n/a | baseline code path | baseline code path | static code only; no run this task |
| INDEPENDENT + DS_ONLY A1/A2/T1/T2 | mock schedule/role orchestration | mock only | mock only | no actual firmware protocol |
| ONE_TO_MANY + DS_ONLY | config/design placeholder | unsupported | unsupported | not implemented |
| INTERLEAVED/ALTERNATING | unsupported | config/design placeholder | unsupported | not implemented |
| DS_CIR_CAPTURE / DS_PHASE_CORRECT 2A2T | unsupported | unsupported | unsupported | requires accumulator/timing HIL |
| HYBRID mode switching | design only | design only | design only | not implemented |

## 4. Test pass/fail matrix

| Area | Result | Evidence |
|---|---|---|
| Config/schema/HAL/mock faults | PASS | 68 passed under Visual Studio x64 developer environment |
| Firmware instrumentation static contract | PASS | 3 static contract tests |
| Firmware instrumentation host compile/run | PASS | MSVC C11 trace-off/trace-on/software-timestamp variants; ordinary shell without vcvars reports one SKIP |
| Logic/UART/timing/calibration analysis | PASS | pytest suite |
| Unified nominal mock run/report | PASS | generated run manifest/report |
| Fault propagation/resume/unique run ID | PASS | integration tests |
| Actual firmware build | NOT RUN | overlay-only baseline, unsafe upstream |
| Board flash/UART/logic/RF | NOT RUN | no hardware connected |
| Antenna-delay calibration | NOT RUN | synthetic dry-run only |

## 5. Unresolved risk / owner / next action

| Risk | Owner | Next action |
|---|---|---|
| Unsafe upstream Git state | User/repository owner | provide or approve clean pinned SDK checkout |
| Probable responder `dist_str[16]` overflow | Firmware owner | reproduce on clean source, fix under separate reviewed change |
| Mixed FCS convention | Firmware owner | driver/API audit and packet golden tests |
| Fast SPI assignment commented | Firmware owner | config review and measured waveform |
| No actual A2/T2 protocol identities | Protocol owner | define packet/address/scheduler before HIL |
| Real J-Link enumeration not implemented | Tooling owner | add verified discovery command/API |
| Real calibration loop guarded | Experiment owner | complete build/range contract after smoke |
| Trace overhead/pin collision | Hardware owner | board-specific mapping and on/off benchmark |

## Known limitations

- Mock timing and calibration numbers are deliberately synthetic.
- Runner real connection smoke currently validates four configured UART ports/captures; it does not establish J-Link, RF or 2A2T success.
- J-Link and logic-analyzer physical enumeration and UART firmware identity/session validation are not implemented; configured entries are not discovery proof.
- Unified-runner real logic/UART adapters are currently blocking and sequential, so they do not yet share one synchronized capture window.
- Real build/flash and calibration loops remain gated by missing clean SDK and role/range contracts.
- Firmware instrumentation has not been integrated into the vendor project or measured on target.
- No packet-time calculator, 2A2T packet codec/scheduler/aggregator, or actual mode-switching firmware was added in this pre-hardware scope.
