# Current firmware code analysis

분석 기준: `ekf` / `b8b911f6d437af9cb70c09f1b4f4562feb0239ac`  
분석 방법: static code inspection  
`source_type = CODE_INSPECTION`  
`hardware_verified = false`

## 검증된 결과

### Repository/build structure

- 기준 저장소는 완전한 SDK가 아니라 `firmware_overlay/`의 C/H 4개, `phase_ds_twr_two_anchor.patch`, standalone `tools/`를 보존한 overlay 저장소다.
- 기준 저장소 자체에는 Make/CMake/SES project, vendor driver, platform port, test framework가 없다.
- 별도 상류 후보 `research/uwb_followup/original_repos/UWB-Ranging-Optimization/`에는 `API/nRF52840-DK/dw3000_api.emProject`가 있으나 index/worktree가 대규모 불일치 상태이고 overlay와 파일 hash도 다르다. 이번 작업에서는 수정·build하지 않았다.
- 기존 `tools/set_uwb_example.py`는 upstream `API/Src/example_selection.h`를 직접 수정해 initiator, responder A1/B2를 선택한다. A2/T2 target은 존재하지 않는다.

### `dwt_config_t`

Initiator `firmware_overlay/API/Src/custom_code/ds_twr_initiator_final.c:41`과 responder `.../ds_twr_responder_final.c:51`의 positional initializer는 같다.

| Field | Baseline value | Status |
|---|---|---|
| channel | `9` | code-confirmed |
| TX preamble | `DWT_PLEN_128` | code-confirmed |
| RX PAC | `DWT_PAC8` | code-confirmed |
| TX/RX code | `9/9` | code-confirmed |
| SFD type | `1` | code-confirmed |
| data rate | `DWT_BR_6M8` | code-confirmed |
| PHR mode/rate | `DWT_PHRMODE_STD/DWT_PHRRATE_STD` | code-confirmed |
| SFD timeout | `129` | expression-confirmed |
| STS | `DWT_STS_MODE_OFF` | code-confirmed |
| STS length field | `DWT_STS_LEN_64` | inactive while STS off |
| PDOA | `DWT_PDOA_M0` | code-confirmed |

### Current five-packet flow

1. Initiator chooses `A1` or `B2` with `current_anchor` and sends Poll (`initiator:255-274`).
2. Responder receives Poll, captures phase, schedules Response (`responder:274-359`).
3. Initiator receives Response, captures phase and sends Final (`initiator:276-346`).
4. Responder receives Final and schedules Post-Final RX (`responder:363-455`); initiator sends Post-Final (`initiator:348-364`).
5. Responder computes raw DS/phase-corrected distance and sends Report (`responder:457-533`); initiator receives and prints it (`initiator:366-404`).

The active topology is one tag ASCII address `TG` and two anchor addresses `A1/B2` (`initiator:67-73`). `current_anchor ^= 1` alternates links (`initiator:421-423`). There is no `superframe_id`, `frame_id`, `slot_id`, T2 identity, or actual 2A2T aggregation.

### Packet map and length convention

Common bytes are frame control `41 88`, sequence byte 2, PAN `CA DE`, destination 5-6, source 7-8, function code byte 9 (`initiator:67-81`, `responder:79-91`). Function codes are Poll `0x21`, Response `0x10`, Final `0x23`, Post-Final `0x12`, Report `0x31`.

| Packet | TX array bytes | Programmed TX frame length including FCS |
|---|---:|---:|
| Poll | 10 | 12 |
| Response | 13 | 13 |
| Final | 32 | 34 |
| Post-Final | 10 | 12 |
| Report | 14 | 16 |

The baseline has two FCS conventions: Response passes `sizeof(tx_resp_msg)` to both APIs (`responder:333-337`), whereas initiator packets and Report add `FCS_LEN` only to `dwt_writetxfctrl` (`initiator:260-263,329-332,353-355`; `responder:497-501`). This inconsistency is preserved as a finding and is not normalized silently.

### Delays, timeouts, and sleeps

| Parameter | Value | Source |
|---|---:|---|
| initiator Poll TX -> Response RX | 1500 UUS | initiator:135 |
| initiator Response RX -> Final TX | 1650 UUS | initiator:136 |
| initiator Response RX timeout | 281 UUS | initiator:137 |
| initiator Final TX -> Post-Final TX | 1650 UUS | initiator:138 |
| initiator Report RX timeout | 50000 UUS | initiator:139 |
| responder Poll RX -> Response TX | 1650 UUS | responder:148 |
| responder Response TX -> Final RX | 1500 UUS | responder:149 |
| responder Final RX timeout | 298 UUS | responder:150 |
| responder Final RX -> Post-Final RX | 1500 UUS | responder:151 |
| responder Post-Final RX timeout | 279 UUS | responder:152 |
| startup sleeps | 2 ms both | initiator:211; responder:224 |
| inter-ranging sleeps | initiator 1 ms; responder 5 ms | initiator:59,423; responder:68,533 |
| pre-Report sleep | 2 ms | responder:502 |

`getDelayTime_*` helpers exist in `Shared_jang/shared_function_jang.c:53-106`, but calls are commented out (`initiator:189`, `responder:205`). Values above are code constants, not optimized or measured values.

### Timestamps

- Initiator reads Poll TX and Response RX (`initiator:301-303`), predicts Final TX (`311-321`), and writes their low 32 bits into Final bytes 10-21.
- Response phase is signed little-endian milliradians at bytes 22-25 (`initiator:322-327`; `responder:410-414`).
- Responder reads local Response TX and Final RX (`responder:401-408`) and decodes Final timestamps (`416-419`).
- Post-Final timestamps are captured but not used in DS ToF or transported.
- Full DW timestamp helpers in the upstream driver read 40 bits, but Final serialization discards the high byte. No `effective_range_ts` exists in the baseline.

### CIR and phase processing

- `ACCUM_DATA_LEN=7`: one dummy byte plus one 18-bit complex sample (`initiator:160`; `responder:180`; `Shared_jang/shared_function_jang.c:442-459`).
- Sample index is `ipatovFpIndex >> 6` at each capture (`initiator:305-309`; `responder:317-321,404-408,445-449`).
- Four capture phases are Poll RX, Response RX, Final RX, Post-Final RX.
- Combination is `normalize(phi0 + phi1 - phi2 + phi3)` (`responder:472`).
- Raw phase distance and integer wavelength count are filtered independently with `WINDOW_SIZE=20` (`Shared_jang/shared_function_jang.h:48`; implementation `.c:470-540`). The integer cast truncates toward zero.
- First 20 outputs fall back to raw DS distance (`responder:478-481`). Raw DS is not preserved in the transmitted Report separately from corrected distance.

### UART/logging and event handling

- Ranging code calls `test_run_info` for application/failure/distance text and uses `sprintf` in the active path (`initiator:187,387-415`; `responder:204,509-519`).
- Existing host parsing is single-tag UART and recognizes `A1|B2` only (`tools/collect_tag_two_anchor_position.py:26`).
- Current RF events busy-poll `SYS_STATUS` (`initiator:269-271,338-340,370-371`; responder:284-291,347-354,427-428`). IRQ infrastructure in the separate upstream port is not activated by this ranging example.
- The upstream nRF code statically indicates UART 115200 and SPIM3, but this is code inspection from a dirty upstream tree and remains unverified. `port_set_dw_ic_spi_fastrate` has its fast-frequency assignment commented, so the actual waveform rate cannot be inferred safely.

### Antenna-delay baseline application

- Initiator and responder both define `TX_ANT_DLY=16385` and `RX_ANT_DLY=16385` (initiator 63–64; responder 71–72).
- Initiator applies them through `dwt_setrxantennadelay` and `dwt_settxantennadelay` at lines 237–238; responder applies them at 251–252.
- These are preserved baseline constants only. They were not calibrated, flashed, read back, or validated in this task.

### Late TX, timeout, CRC, and retry behavior

- Init/config failure logs and spins forever (`initiator:216-229`; `responder:229-242`).
- Poll `dwt_starttx` return is not checked (`initiator:267`).
- Delayed Final or responder Response failure abandons the exchange (`initiator:334-337`; `responder:337-343`).
- Post-Final delayed-TX failure executes `continue` before anchor toggle/sleep, implicitly repeats the same anchor, and has no retry metadata (`initiator:356-359`).
- CRC/error/timeout conditions are collapsed into aggregate status masks; there is no structured counter or error record. Response misses log only every 50 failures (`initiator:410-415`).
- A retry or previous-frame value cannot be distinguished by identity because baseline records have no boot/superframe/frame/slot/retry tuple.

## 가정한 값

- None of the static constants is treated as an optimized timing or calibrated antenna-delay value.
- A1/A2/T1/T2 names in the new dry-run configuration are orchestration roles, not evidence that baseline firmware supports those nodes.

## 논문 기반 근거

- No paper-derived numeric timing or antenna-delay value is introduced in this analysis.

## 추후 확인 필요

- Repair or obtain a clean, commit-pinned full upstream SDK and reproduce the baseline build.
- Confirm SES/toolchain compatibility and the exact build/flash target.
- Verify FCS policy against the linked driver/API version and on-air frame lengths.
- Verify actual UART baud/pins, SPI clock, IRQ pin/path, trace pins, CIR accumulator ownership, and all processing times.
- Investigate probable responder report buffer overflow: upstream global `dist_str[16]` versus longer `REPORT:` formatting.
- Define and implement actual A1/A2/T1/T2 addressing, T2 role, scheduler, frame identity, retry record, and raw/corrected dual logging before HIL.
