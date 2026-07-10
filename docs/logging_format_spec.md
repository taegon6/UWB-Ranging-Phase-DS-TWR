# Pre-hardware logging format specification

## Provenance invariant

모든 mock raw/derived row와 sidecar에는 다음 두 필드가 있어야 한다.

```text
source_type = SYNTHETIC
hardware_verified = false
```

## 현재 format

- Mock logic: long-form CSV `timestamp_us,channel,value,frame_id,source_type,hardware_verified`.
- Mock UART runner: binary-safe file handle에 JSON Lines를 기록하며 각 JSON record에 provenance, node, superframe, link, timeout/retry/missing-link 상태를 둔다. Corrupt byte sequence는 parser error로 보존한다.
- Checked-in UART fixture: host-test framing `U2AT` magic, version byte, little-endian payload length, UTF-8 JSON payload, CRC32. Decoder는 corrupt record 뒤 다음 magic으로 resynchronize한다.
- Existing baseline UART text `ANCHOR:<id> DIST:<value> m`도 compatibility parser가 지원하지만 실제 format version은 아니다.

Host-test framing은 아직 firmware binary logger wire format이 아니다. Firmware integration 전에 fixed-size header, record length, device timestamp, boot/superframe/frame/slot identity, CRC policy와 endian golden vector를 별도 확정해야 한다.

## Raw/derived separation

- `raw/`는 overwrite하지 않는다.
- `intermediate/decoded_records.csv`와 `edge_pairs.csv`는 raw source locator를 유지하는 derived table이다.
- `analysis/errors.csv`와 `uart_errors.csv`는 missing edge, overlap, CRC/parse corruption을 숨기지 않는다.
- Host timestamp를 RF effective range timestamp로 사용하지 않는다.

## 검증된 결과

- Synthetic binary round-trip과 corrupt-record recovery가 test된다.

## 가정한 값

- Fixture payload JSON은 software test convenience이며 embedded bandwidth/overhead 최적화 결과가 아니다.

## 논문 기반 근거

- 없음.

## 추후 확인 필요

- Firmware ring buffer, actual wire schema, timestamp mapping, drop counter와 overhead
- Raw DS/phase/CIR를 동시에 보존하는 actual measurement record
