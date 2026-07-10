# Antenna-delay calibration workflow

## 현재 범위

```text
source_type = SYNTHETIC
hardware_verified = false
calibration_completed = false
```

현재 구현은 candidate generation, synthetic bias table, objective curve, selection, combined-delay identifiability 검사와 report 생성을 dry-run으로 검증한다. Mock selected candidate는 소프트웨어 경로 시험 token이며 firmware에 복사할 calibration 값이 아니다.

## 지원하는 분석 mode

1. `COMBINED_SINGLE_LINK`: 한 link의 combined delay 후보를 평가한다.
2. `REFERENCE_NODE_SEQUENTIAL`: resolved reference node를 고정한 synthetic 순차-node 분기를 실행한다.
3. `OFFLINE_2A2T_LEAST_SQUARES`: A1-T1/A2-T1/A1-T2/A2-T2 네 synthetic link bias의 offline least-squares 분기를 실행한다.

Range bias만으로 node별 TX/RX delay를 각각 식별할 수 없다. 추가 constraint 또는 독립 측정이 없으면 combined contribution만 보고해야 한다. Solver는 rank deficiency를 숨기지 않고 `identifiable=false`로 반환한다.

## Dry-run

```bash
python tools/calibrate_antenna_delay.py \
  --config configs/antenna_calibration.example.yaml \
  --backend mock \
  --dry-run
```

생성 항목:

- `calibration_candidates.csv`
- `mock_bias_table.csv`
- `objective_curve.csv`
- `figures/objective_curve.svg`
- `calibration_result.json`
- `calibration_report.md` 및 run-level `report.md`

`samples_per_point`, `warmup_samples`, objective metric, repeatability penalty/weight와 synthetic noise/seed는 dry-run 계산과 report에 반영된다. `calibration.search.hardware.*` 및 `measurement_metadata.*`의 TODO는 dry-run에서 해소하지 않는다. Mock은 별도 `calibration.search.synthetic_mock`만 사용한다.

## 실제 실험 준비

1. `configs/local_hardware.example.yaml`을 `configs/local_hardware.yaml`로 복사하고 모든 device/port/pin TODO를 채운다.
2. `configs/antenna_calibration.example.yaml`을 `configs/antenna_calibration.yaml`로 복사한다.
3. 복사본의 `backend`를 `real`로, `outputs.source_type`을 `MEASURED`로 바꾸되 `outputs.hardware_verified`는 validation 전까지 `false`로 유지한다.
4. `measurement_metadata`의 target node/link, 거리 기준점·불확도, 안테나 기준점·높이·방향, 환경과 실제 기준거리, sample/warm-up 수, `search.hardware` 범위를 근거와 함께 채운다.
5. Connection smoke와 1A1T raw range record contract를 먼저 통과한다.
6. Clean full SDK, role build commands, image paths와 flash mapping을 검증한다.
7. 거리 기준점, 안테나 높이·방향·편파, LOS/반사체와 환경을 사진/표로 기록한다.

첫 launch/readiness command:

```bash
python tools/calibrate_antenna_delay.py \
  --config configs/antenna_calibration.yaml \
  --hardware-config configs/local_hardware.yaml \
  --backend real \
  --execute
```

현재 pre-hardware release는 placeholder가 남거나 clean SDK/build/range contract가 준비되지 않으면 build·flash·measurement 전에 중단한다. 이는 안전 gate이며 calibration 성공이 아니다.

## 실제 loop 계약

```text
candidate config 생성
-> role firmware build 및 hash
-> 승인된 node/image mapping flash
-> reset/synchronize
-> warm-up 제외
-> N raw range records 수집
-> missing/timeout/retry/quality 검증
-> bias/repeatability objective
-> 다음 candidate
-> final candidate independent validation
-> config/report archive
```

각 candidate마다 raw range, source frame IDs, retry/timeout, config/firmware hash를 보존한다. Previous-frame range를 현재 성공으로 재분류하지 않는다.

## 검증된 결과

- Coarse/fine candidate boundary, weighted absolute bias, repeatability penalty와 rank-aware least-squares를 unit test했다.
- Synthetic four-link system에서 알려진 combined contributions를 복원하는 software test가 통과했다.
- Dry-run 결과는 항상 `SYNTHETIC/false`이고 `calibration_completed=false`다.

## 가정한 값

- `synthetic_mock` range, synthetic truth와 noise는 deterministic fixture일 뿐 DW3000 특성이 아니다.

## 논문 기반 근거

- 현재 candidate 숫자와 objective에는 논문 값을 사용하지 않았다.

## 추후 확인 필요

- DW3000 API antenna-delay 단위/허용범위와 현재 firmware 적용 위치
- 실제 node별 TX/RX 또는 combined parameterization
- reference distance uncertainty 및 weighting policy
- temperature/channel/antenna orientation 반복성
- clean build/flash/range pipeline과 final validation acceptance
