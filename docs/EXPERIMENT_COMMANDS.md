# Experiment commands

모든 명령은 repository root에서 실행한다. 현재 hardware-free 결과는 `source_type=SYNTHETIC`, `hardware_verified=false`다.

## 환경과 전체 mock run

```bash
python tools/check_environment.py

python tools/run_hardware_experiment.py \
  --config configs/mock_hardware.yaml \
  --experiment timing_characterization \
  --backend mock \
  --dry-run \
  --analyze \
  --report
```

PowerShell:

```powershell
python tools\run_hardware_experiment.py `
  --config configs\mock_hardware.yaml `
  --experiment timing_characterization `
  --backend mock `
  --dry-run `
  --analyze `
  --report
```

## Calibration dry-run

```bash
python tools/calibrate_antenna_delay.py \
  --config configs/antenna_calibration.example.yaml \
  --backend mock \
  --dry-run
```

## Four-node build/flash planning

```bash
python tools/build_firmware.py \
  --config configs/mock_hardware.yaml \
  --dry-run \
  --output artifacts/pre_hardware/build_dry_run

python tools/flash_all.py \
  --config configs/mock_hardware.yaml \
  --build-manifest artifacts/pre_hardware/build_dry_run/build_manifest.json \
  --dry-run \
  --output artifacts/pre_hardware/flash_plan.json
```

이 명령은 image를 compile하거나 J-Link를 호출하지 않는다.

## Fixture generation and standalone analysis

```bash
python tools/generate_synthetic_fixtures.py --force

python tools/analyze_timing_capture.py \
  tests/fixtures/synthetic_logic_capture.csv \
  --output-dir artifacts/pre_hardware/synthetic_logic_analysis
```

이 명령의 `--force`는 version-controlled synthetic fixture만 결정적으로 재생성한다. 실험 raw data에는 사용하지 않는다.

## Standalone mock UART/logic capture

```bash
python tools/capture_uart.py \
  --config configs/mock_hardware.yaml \
  --backend mock \
  --output-dir artifacts/pre_hardware/mock_uart_capture \
  --duration 1 \
  --dry-run

python tools/capture_logic.py \
  --config configs/mock_hardware.yaml \
  --backend mock \
  --output artifacts/pre_hardware/mock_logic_capture.csv \
  --duration 1 \
  --dry-run
```

## Tests

```bash
python -m pytest -q
```

## First real connection smoke

TODO를 모두 해소하고 연결 checklist를 완료한 뒤에만 실행한다.

```bash
python tools/discover_hardware.py --config configs/local_hardware.yaml

python tools/run_hardware_experiment.py \
  --config configs/local_hardware.yaml \
  --experiment connection_smoke_test \
  --backend real \
  --execute
```

Connection smoke는 구성된 네 UART port가 OS discovery에 없거나 새 raw UART file 4개가 생성되지 않으면 실패한다. 이 통과만으로 RF ranging, 2A2T protocol, timing 또는 antenna delay를 검증한 것은 아니다. J-Link physical enumeration은 현재 backend의 별도 미검증 항목이다.

현재 unified runner의 real logic/UART capture는 blocking·순차 방식이므로 동일 시간창의 동기 계측 명령으로 사용하면 안 된다. UART node identity/session parsing과 analyzer physical enumeration도 후속 구현 항목이다.

## First real calibration launch/readiness gate

```bash
python tools/calibrate_antenna_delay.py \
  --config configs/antenna_calibration.yaml \
  --hardware-config configs/local_hardware.yaml \
  --backend real \
  --execute
```

현재 release는 missing requirement가 있으면 장비 동작 전에 중단한다.

## 검증된 결과

- 위 세 필수 mock 명령과 unit/integration tests는 보드 없이 실행 가능하다.

## 가정한 값

- 실제 config 파일은 example을 사용자가 복사·검토하여 만든다고 가정한다.

## 논문 기반 근거

- 명령 자체에는 논문 기반 숫자가 없다.

## 추후 확인 필요

- 실제 build/flash command와 real logic backend command는 clean SDK와 장비 연결 후 확정한다.
