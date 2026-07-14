# Current pre-hardware environment report

Captured: 2026-07-10, Asia/Seoul  
`hardware_verified = false`

## 검증된 결과

| Item | Result |
|---|---|
| OS | Microsoft Windows NT 10.0.26200.0 |
| Shell | Windows PowerShell 5.1.26100.8655 |
| Python | 3.14.4 |
| Git | available |
| Core packages | PyYAML 6.0.3, jsonschema 4.26.0 |
| Data/test packages | numpy 2.4.4, pytest 9.0.3 |
| Serial package | pyserial 3.5 |
| J-Link CLI | `JLink.exe` found; not invoked |
| SEGGER Embedded Studio CLI | `emBuild.exe` found; project was not built |
| Make/CMake/ARM GCC/nrfjprog | not found on PATH |
| sigrok-cli | not found on PATH |
| Host C instrumentation test | Visual Studio 2026 x64 developer environment; MSVC C11 warning-as-error, 4/4 tests passed |
| Firmware repository | overlay-only, no native build project |
| Full upstream candidate | present but unsafe dirty/index-mismatched tree; not modified |
| Existing test framework | none before this work |

Existing firmware uses direct `port_set_dw_ic_spi_fastrate`, `test_run_info`, `dwt_readaccdata`, and polled `SYS_STATUS`; it does not provide injectable Flash/UART/logic interfaces.

### Static firmware/build inventory

| Required inspection item | Code-inspection result | Hardware status |
|---|---|---|
| PHY `dwt_config_t` | CH9, PLEN128, PAC8, TX/RX code 9/9, 6.8M, standard PHR, STS off | unverified |
| Antenna-delay constants | initiator/responder `TX_ANT_DLY=16385`, `RX_ANT_DLY=16385` | uncalibrated/unverified |
| Antenna-delay apply calls | initiator `dwt_setrxantennadelay`/`dwt_settxantennadelay` at 237–238; responder at 251–252 | not executed |
| Role/address model | initiator tag `TG`; alternating anchors `A1/B2`; no A2/T2 target | static only |
| Build project | overlay repo has no project; dirty upstream candidate has `API/nRF52840-DK/dw3000_api.emProject` | not built |
| SPI | `port_set_dw_ic_spi_fastrate` called; upstream fast-frequency assignment is commented | waveform unknown |
| IRQ/event handling | active examples poll `SYS_STATUS`; no measured ISR path | timing unknown |
| CIR | `dwt_readaccdata`, 7-byte buffer, one complex sample at `ipatovFpIndex >> 6` | ownership/timing unknown |
| UART/logging | blocking-style `test_run_info`/`sprintf` text path; dirty upstream suggests 115200 | baud/framing/timing unverified |

Detailed packet, timeout, CIR and failure-path evidence is in `artifacts/current_code_analysis.md`. No value in this table is a measured or optimized result.

## 가정한 값

- None. Installed executable/package discovery does not imply a connected or functional device.

## 논문 기반 근거

- Not applicable to environment discovery.

## 추후 확인 필요

Status: `TODO(HW_VERIFY)`  
Reason: board, UART, J-Link probe, and logic analyzer are not connected.  
Verification method: fill `configs/local_hardware.yaml`, then run `python tools/discover_hardware.py --config configs/local_hardware.yaml`.  
Required input: A1/A2/T1/T2 J-Link IDs, serial ports, baud, device ID, GPIO/channel mapping, and sample rate.

Status: `TODO(BUILD_REPRODUCE)`  
Reason: the baseline repo is overlay-only and the preserved upstream candidate is not clean/reproducible.  
Verification method: obtain a clean commit-pinned SDK checkout, verify overlay hashes, and configure role-specific SES commands.  
Required input: approved upstream path/commit and actual build command/toolchain.
