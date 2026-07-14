# 2A2T Phase 0~4.5 PHY 및 timeline 모델 보강 보고서

## 1. 결론

판정은 **PHY_MODEL_CONDITIONAL**이다.

현재 STS-off DW3000 PHY airtime은 논문 Table 2 역산값 없이 Qorvo 공식 DW3000 symbol timing과 repository frame length에서 독립적으로 계산한다. paper 3-packet reproduction과 current firmware 5-packet calculation도 별도 module/config/test 계층으로 분리했다. `Final->PostFinal`은 CODE_BASELINE same-node delayed-TX로 분리했고, `PostFinal->Report`는 측정 또는 확정 가능한 Rmarker delay가 없으므로 `UNRESOLVED` hard-fail로 남겼다.

```text
source_type = CODE_INSPECTION
hardware_verified = false
```

실제 DW3000 airtime 측정, 실제 2A2T 통신, processing time, UART, retry 또는 antenna delay가 검증된 것은 아니다. Phase 5/6과 firmware source는 변경하지 않았다.

## 2. 독립 근거

| Source | 사용 근거 | SHA-256 |
|---|---|---|
| [Qorvo DW3000 Datasheet v1.3](https://www.qorvo.com/products/d/da008142) | Table 18 symbol timing, Figure 12 PPDU/FCS/RS, Figure 7 STS 구조 | `33759927...5C9E216` |
| [Qorvo DW3xxx API Guide v4.1](https://forum.qorvo.com/uploads/short-url/xD3TlXKvkujjdUaJWXv2b4E7GQN.pdf) | `dwt_config_t`, code/PRF, SFD, PHR, FCS, TX buffer/frame-control convention | `1EC42876...21898F36` |
| repository firmware overlay | 실제 positional config, packet array와 driver call | commit `b8b911f6...` |
| jkiees-36-3-274 | paper 3-packet regression comparison | Table 2는 current PHY 입력으로 사용하지 않음 |

DW3000 Datasheet Table 18은 64 MHz PRF/6.81 Mbps에서 SHR symbol `1017.63 ns`, standard 0.85 Mbps PHR symbol `1025.64 ns`, data symbol `128.21 ns`를 제시한다. Figure 12는 PHR 21 symbols와 PSDU의 `8*frame length + 48 RS bits per 330 data bits or less`를 제시하며 최대 frame length에 2-byte FCS가 포함된다고 명시한다.

## 3. repository에서 재추출한 현재 PHY

Initiator `ds_twr_initiator_final.c:41-55`와 responder `ds_twr_responder_final.c:51-65`는 동일하다.

| 항목 | 현재 값 | code/Qorvo 해석 | 상태 |
|---|---|---|---|
| channel | 9 | 7987.2 MHz, 499.2 MHz bandwidth | CODE_BASELINE |
| preamble | `DWT_PLEN_128` | 128 symbols | CODE_BASELINE |
| PAC | `DWT_PAC8` | 8 symbols | CODE_BASELINE |
| TX/RX code | 9/9 | Qorvo API Table 2의 64 MHz PRF code | RESOLVED |
| SFD type | numeric 1 | `DWT_SFD_DW_8`, 8 symbols | RESOLVED |
| data rate | `DWT_BR_6M8` | 6.81 Mbps timing row | RESOLVED |
| PHR mode | `DWT_PHRMODE_STD` | standard frame, 5~127 octets | RESOLVED |
| PHR rate | `DWT_PHRRATE_STD` | standard 0.85 Mbps PHR symbol timing | RESOLVED |
| STS mode | `DWT_STS_MODE_OFF` | STS airtime 0 | RESOLVED |
| STS length field | `DWT_STS_LEN_64` | STS off이므로 inactive | INACTIVE |
| SFD timeout | 129 | `128+1+8-8` | CODE_BASELINE |

## 4. packet byte 및 FCS convention

공통 header layout은 다음과 같다.

```text
frame control 2 + sequence 1 + PAN 2 + destination 2 + source 2 = 9 octets
function code = 1 octet
FCS = 2 octets, DW3000 hardware generation enabled by default
```

`dwt_writetxdata()` 길이는 TX buffer에 쓰는 byte 수이며 FCS 자리 2 bytes를 포함해도 되고 생략해도 된다. `dwt_writetxfctrl()`의 frame length는 2-byte CRC/FCS를 포함한 total on-air PSDU length다.

| Packet | MAC/header | function | body/application | meaningful buffer | driver buffer arg | FCS placeholder 포함 | frame-control arg | FCS | on-air PSDU |
|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| Poll | 9 | 1 | 0 | 10 | 10 | no | 12 | 2 | 12 |
| Response | 9 | 1 | 1 | 11 | 13 | yes | 13 | 2 | 13 |
| Final | 9 | 1 | 22 | 32 | 32 | no | 34 | 2 | 34 |
| PostFinal | 9 | 1 | 0 | 10 | 10 | no | 12 | 2 | 12 |
| Report | 9 | 1 | 4 | 14 | 14 | no | 16 | 2 | 16 |

Response array의 마지막 2 zero bytes는 `dwt_writetxfctrl(sizeof(tx_resp_msg))`가 total 13-byte frame을 지정하므로 generated FCS가 차지하는 placeholder로 해석한다. 이 convention은 Qorvo API 설명과 일치하지만 실제 TX buffer/register 또는 on-air capture로 확인된 것은 아니다.

## 5. 독립 airtime 식

모든 계산은 `Decimal` canonical picosecond(`ps`)로 수행한다.

```text
T_preamble = preamble_symbols * SHR_symbol_time
T_SFD      = SFD_symbols * SHR_symbol_time
T_STS      = 0 when STS off; enabled mode requires explicit resolved duration
T_PHR      = 21 * selected_PHR_symbol_time

data_bits       = on_air_PSDU_octets * 8
RS_blocks       = ceil(data_bits / 330)
encoded_bits    = data_bits + 48 * RS_blocks
T_PSDU          = encoded_bits * data_symbol_time

T_packet = T_preamble + T_SFD + T_STS + T_PHR + T_PSDU
```

논문 Table 2의 `138.4`, `21.5`, `20.5/23.6/34.9 us`는 위 상수의 입력이 아니다. 기존 paper fixture에서만 published result reproduction에 사용한다.

### PLEN128 current firmware 결과

| Packet | T_preamble | T_SFD | T_STS | T_PHR | T_PSDU | T_packet (us) |
|---|---:|---:|---:|---:|---:|---:|
| Poll | 130.25664 | 8.14104 | 0 | 21.53844 | 18.46224 | 178.39836 |
| Response | 130.25664 | 8.14104 | 0 | 21.53844 | 19.48792 | 179.42404 |
| Final | 130.25664 | 8.14104 | 0 | 21.53844 | 41.02720 | 200.96332 |
| PostFinal | 130.25664 | 8.14104 | 0 | 21.53844 | 18.46224 | 178.39836 |
| Report | 130.25664 | 8.14104 | 0 | 21.53844 | 22.56496 | 182.50108 |

### PLEN1024 structural regression

동일 frame/data 설정에서 preamble만 1024 symbols로 바꾸면 다음과 같다.

| Packet | T_packet (us) |
|---|---:|
| Poll | 1090.19484 |
| Response | 1091.22052 |
| Final | 1112.75980 |
| PostFinal | 1090.19484 |
| Report | 1094.29756 |

## 6. canonical unit 변환표

| 입력 unit | canonical ps 변환 | 비고 |
|---|---|---|
| `ps` | value | canonical |
| `ns` | value × 1,000 | DW3000 symbol table 입력 |
| `us` | value × 1,000,000 | explicit synthetic/processing 입력 |
| `dtu` | value × `10^12/(499.2e6×128)` ps | 1 dtu ≈ 15.6500400641 ps |
| `UUS` | value × 65,536 dtu | 1 UUS ≈ 1.02564102564 us |

`ms`, bare number time, `symbol`을 time처럼 사용하는 것과 기타 미지원 unit은 schema/runtime에서 실패한다. `symbol`, `octet`, `bit`는 dimension count이며 time unit과 혼용하지 않는다.

## 7. paper 3-packet과 current 5-packet 차이

| 항목 | paper reproduction | current firmware independent PHY |
|---|---|---|
| 목적 | published Table 2 regression | repository frame의 DW3000 airtime 계산 |
| packets | Poll, Response, Final | Poll, Response, Final, PostFinal, Report |
| packet lengths | 14/17/28 octets, PAPER_DERIVED fixture | 12/13/34/12/16 on-air octets, CODE_BASELINE trace |
| symbol timing | Table 2 결과를 재현하는 legacy fixture | DW3000 Datasheet Table 18 |
| RS coding | legacy single 48-bit fixture | 48 bits per 330-bit block or less |
| internal time | legacy float microsecond | Decimal canonical picosecond |
| Table 2 역할 | expected regression output | input 금지, comparison only |
| timeline | 두 remote reply | transition별 timing kind |

기존 `analysis/phy_airtime_model.py`와 `tests/test_paper_golden_values.py`는 paper regression 전용으로 보존한다. current model은 `analysis/dw3000_phy_model.py`, `configs/dw3000_current_phy.yaml`, `tests/test_dw3000_independent_phy.py`를 사용한다.

## 8. current 5-packet transition 분리

| Transition | timing kind | 계산/상태 |
|---|---|---|
| Poll->Response | `REMOTE_RX_TO_TX_REPLY` | remote processing + exact outgoing Response airtime + guard |
| Response->Final | `REMOTE_RX_TO_TX_REPLY` | remote processing + exact outgoing Final airtime + guard |
| Final->PostFinal | `SAME_NODE_DELAYED_TX` | CODE_BASELINE 1650 UUS를 explicit UUS->ps 변환 |
| PostFinal->Report | `POST_PROCESS_REPORT` | `UNRESOLVED`, hard-fail |

따라서 remote processing 또는 guard를 변경해도 `Final->PostFinal`과 explicit `PostFinal->Report` 값은 변하지 않는다. `PostFinal->Report`를 paper reply 식으로 자동 계산하지 않는다.

`Final->PostFinal` 1650 UUS는 약 1692.307692 us이며 측정값이 아니라 firmware scheduling constant다. `PostFinal->Report`는 responder의 CIR/phase/filter 처리, `Sleep(2)`, immediate TX와 packet preparation이 섞여 있어 code inspection만으로 Rmarker-to-Rmarker delay를 확정할 수 없다.

## 9. 테스트 계층

### Paper reproduction

- `tests/test_paper_golden_values.py`
- paper PLEN128 Table 2 및 706/717, PLEN1024 regression
- 기존 assertion 유지

### Independent PHY/timeline

- unsupported unit schema/runtime rejection
- packet별 FCS include/exclude convention
- STS off, unresolved-on hard-fail, explicit ASSUMED mode1/mode2 구조
- PLEN128 exact Decimal output
- PLEN1024 component separation
- 1-byte 증가 monotonicity
- paper 3-packet/current 5-packet definition separation
- Final->PostFinal remote formula 독립성
- PostFinal->Report unresolved hard-fail 및 explicit assumption 독립성
- ps/ns/us/dtu/UUS explicit conversion
- repeated calculation deterministic equality

## 10. unresolved 및 blocking 항목

1. `PostFinal->Report` 실제 Rmarker delay와 processing breakdown
2. STS enabled exact duration과 STS-on RMARKER semantics - 현재 firmware는 STS off라 current calculation에는 영향 없음
3. repository overlay에 대응하는 exact vendor driver/API version - full SDK가 없음
4. Response FCS placeholder convention의 hardware/on-air 확인
5. node/transition별 remote processing p95/p99
6. delayed-TX quantization과 HPDWARN margin의 실제 적용 결과
7. clock drift, RX acquisition/detection margin
8. UART, retry 및 packet loss가 superframe timing에 주는 영향

이 항목들은 `MEASURED`가 아니며 임의 상수로 확정하지 않았다.

## 11. 변경 파일

- `analysis/dw3000_phy_model.py`
- `analysis/twr_timeline_model.py`
- `analysis/phy_airtime_model.py` - legacy paper role 명시만 추가
- `configs/dw3000_current_phy.yaml`
- `schemas/dw3000_phy.schema.json`
- `hardware/device_inventory.py`
- `tests/test_dw3000_independent_phy.py`
- `artifacts/dw3000_phy_source_manifest.json`

firmware source, PAPER 값, CODE_BASELINE 값, 기존 test assertion은 수정하지 않았다.

## 12. 다음 판정

```text
PHY_MODEL_CONDITIONAL
```

STS-off current packet airtime과 `Final->PostFinal` policy separation은 software model에 사용할 수 있다. 그러나 `PostFinal->Report`가 unresolved이고 full current 5-packet end-to-end timeline을 확정할 수 없으므로 Phase 5로 진행할 준비가 완료된 것은 아니다.
