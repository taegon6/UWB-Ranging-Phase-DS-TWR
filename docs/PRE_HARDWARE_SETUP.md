# 2A2T UWB pre-hardware setup

현재 상태는 다음과 같다.

```text
소프트웨어 실험환경 구축 완료
mock/dry-run 검증 완료
실제 보드 및 계측기 검증 대기
source_type = SYNTHETIC
hardware_verified = false
```

## 검증된 결과

- 기준 overlay 저장소 `ekf` / `b8b911f6d437af9cb70c09f1b4f4562feb0239ac`의 변경 전 clean 상태와 tracked-file SHA-256을 `artifacts/baseline/`에 보존했다.
- Python 환경검사, configuration schema, A1/A2/T1/T2 device-role mapping, Flash/UART/logic HAL과 deterministic mock backend가 동작한다.
- synthetic logic edge pairing, missing/overlap 검출, timing 통계, UART corruption recovery, antenna-delay objective/least-squares software 경로가 hardware 없이 test된다.
- unified runner는 unique run ID 아래 raw, intermediate, analysis, manifest, report를 보존한다.
- firmware instrumentation의 trace event/API/no-op static contract test는 통과했다. Visual Studio x64 developer environment에서 MSVC C11 host compile/run 세 변형도 통과했다. 일반 PowerShell PATH에서는 compiler-dependent test 하나가 `SKIP`되며 Embedded firmware 통합은 아직 수행하지 않았다.

## 저장소와 baseline 제약

이 저장소는 완전한 SDK가 아니라 `firmware_overlay/`와 host tools를 보존한 overlay repo다. 별도 상류 후보는 `research/uwb_followup/original_repos/UWB-Ranging-Optimization/`에 있으나 Git index/worktree가 대규모 불일치 상태이고 overlay hash도 다르다. 이번 작업에서는 그 저장소를 수정하거나 build하지 않았다.

따라서 A1/A2/T1/T2 build는 target/image/command mapping dry-run이며, 실제 image가 생성되었다는 뜻이 아니다. 기존 four firmware source files도 수정하지 않았다.

## Python 환경 재현

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-core.txt -r requirements-dev.txt
```

현재 Windows/Python 3.14.4에서 해석된 transitive 버전까지 동일하게 재현하려면 `requirements-lock.txt`를 대신 사용한다.

실제 UART 또는 Saleae adapter를 사용할 때만 optional package를 추가한다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-hardware.txt
```

Linux/macOS shell:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-core.txt -r requirements-dev.txt
```

모든 명령은 repository root에서 실행한다.

## 필수 pre-hardware validation

```bash
python tools/check_environment.py

python tools/run_hardware_experiment.py \
  --config configs/mock_hardware.yaml \
  --experiment timing_characterization \
  --backend mock \
  --dry-run \
  --analyze \
  --report

python tools/calibrate_antenna_delay.py \
  --config configs/antenna_calibration.example.yaml \
  --backend mock \
  --dry-run
```

환경검사기의 hardware `SKIP`은 현재 단계의 실패가 아니다. Mock/config/repository/core dependency 항목의 `FAIL`은 해결해야 한다.

## Mock fault profile

`configs/mock_hardware.yaml`의 `mock.faults`로 다음 분기를 재현한다.

- per-node flash failure
- missing COM node/port
- corrupt UART record와 overflow
- missing logic device/channel/file
- pulse jitter와 IRQ outlier
- SPI/CIR duration 증가
- packet timeout, retry, missing link

Seed는 `mock.random_seed`로 고정한다. Timing profile과 baud/sample-rate 숫자는 `SYNTHETIC_FIXTURE_ONLY`이며 실제 설정으로 복사하지 않는다.

## 결과 보존 계약

Run folder는 workspace 규칙에 맞춰 다음 형식이다.

```text
results/YYYY-MM-DD_<experiment>_mock_pre-hardware_runNN_<id>/
  run_manifest.json
  environment_report.json
  config_snapshot/
  source_snapshot/
  firmware/
  raw/uart/
  raw/logic/
  intermediate/
  analysis/
  figures/
  report.md
  unresolved_items.md
```

Raw file은 exclusive create를 사용하며 기존 파일을 덮어쓰지 않는다. Analysis는 raw edge를 유지한 채 derived pulse/error/statistics table을 별도 생성한다.

## 가정한 값

- A1/A2/T1/T2 target 이름은 orchestration contract이며 baseline firmware의 실제 target 존재를 의미하지 않는다.
- Mock timing, distance, baud 및 sample-rate 값은 branch/test coverage용 synthetic fixture다.
- `source_type=SYNTHETIC`, `hardware_verified=false`인 결과만 현재 검증 범위에 포함된다.

## 논문 기반 근거

- 이번 환경 구축에 논문 기반 timing, antenna-delay 또는 성능 숫자를 사용하지 않았다.

## 추후 확인 필요

- clean, commit-pinned full SDK와 실제 role build command
- A1/A2/T1/T2 J-Link IDs, UART ports, firmware identity record
- 실제 trace GPIO/polarity, analyzer device/channel/sample rate
- SPI clock, IRQ path, CIR accumulator ownership과 processing timing
- 실제 2A2T address/protocol/scheduler/record implementation
- 기준거리, 안테나 높이·방향, 환경 및 calibration search 범위

상세 연결 입력은 `docs/HARDWARE_CONNECTION_CHECKLIST.md`, metric 계약은 `docs/LOGIC_ANALYZER_CONNECTION.md`를 따른다.
