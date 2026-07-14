"""Markdown report generation with a mandatory synthetic-data disclaimer."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

DISCLAIMER_KO = (
    "본 결과는 mock/synthetic data를 이용한 소프트웨어 환경 검증 결과이며,\n"
    "DW3000/DWS3000의 실제 처리시간 또는 antenna delay 보정 결과를 의미하지 않는다."
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def generate_experiment_report(run_dir: Path | str) -> Path:
    run_dir = Path(run_dir)
    manifest = _load_json(run_dir / "run_manifest.json")
    environment = _load_json(run_dir / "environment_report.json")
    timing = _load_csv(run_dir / "analysis" / "timing_summary.csv")
    errors = _load_csv(run_dir / "analysis" / "errors.csv")
    uart_errors = _load_csv(run_dir / "analysis" / "uart_errors.csv")
    experiment_summary = _load_json(run_dir / "raw" / "experiment_summary.json")
    analysis_manifest = _load_json(run_dir / "analysis" / "analysis_manifest.json")
    logic_metadata = _load_json(run_dir / "raw" / "logic" / "logic_edges.csv.metadata.json")
    uart_metadata = [
        _load_json(path)
        for path in sorted((run_dir / "raw" / "uart").glob("*.bin.metadata.json"))
    ]
    if manifest.get("source_type") != "SYNTHETIC" or manifest.get("hardware_verified") is not False:
        raise ValueError("pre-hardware report requires SYNTHETIC / hardware_verified=false manifest")

    stage_lines = []
    for stage in manifest.get("stages", []):
        stage_lines.append(
            f"| {stage.get('name')} | {stage.get('status')} | {stage.get('duration_s', 0):.6f} | {stage.get('reason', '')} |"
        )
    timing_lines = []
    for row in timing:
        timing_lines.append(
            "| {metric} | {count} | {median_us} | {p95_us} | {p99_us} | {max_us} | {source_type} | {hardware_verified} |".format(
                **row
            )
        )
    environment_lines = [
        f"| {check.get('name', '')} | {check.get('status', '')} | {check.get('detail', '')} |"
        for check in environment.get("checks", [])
    ]
    environment_counts: dict[str, int] = {}
    for check in environment.get("checks", []):
        status = str(check.get("status", "UNKNOWN"))
        environment_counts[status] = environment_counts.get(status, 0) + 1
    fault_counts = {
        "UART corrupted/parse records": sum(int(item.get("corrupted_record_count", 0)) for item in uart_metadata),
        "UART buffer overflow streams": sum(bool(item.get("uart_buffer_overflow", False)) for item in uart_metadata),
        "Packet timeouts": sum(int(item.get("packet_timeout_count", 0)) for item in uart_metadata),
        "Retries": sum(int(item.get("retry_count", 0)) for item in uart_metadata),
        "Missing-link flags": sum(int(item.get("missing_link_count", 0)) for item in uart_metadata),
        "Logic frames omitted": int(logic_metadata.get("frame_count_omitted", 0)),
        "Injected IRQ outliers": int(logic_metadata.get("irq_outlier_count", 0)),
        "Derived logic errors/outliers": len(errors),
        "Decoded UART error rows": len(uart_errors),
    }
    fault_lines = [f"| {name} | {count} |" for name, count in fault_counts.items()]
    definition = experiment_summary.get("definition", {})
    report = f"""# 2A2T UWB Pre-Hardware Experiment Environment Validation Report

## Provenance

- Backend: `{manifest.get('backend', 'unknown')}`
- Source type: `{manifest.get('source_type')}`
- Hardware verified: `{str(manifest.get('hardware_verified')).lower()}`
- Git commit: `{manifest.get('git_commit', 'unknown')}`
- Config hash: `{manifest.get('config_hash', 'unknown')}`
- Run ID: `{manifest.get('run_id', 'unknown')}`

## 검증된 결과

The software runner, mock adapters, synthetic capture analysis, and report path completed with status `{manifest.get('status', 'unknown')}`.

| Stage | Status | Duration (s) | Reason |
|---|---:|---:|---|
{chr(10).join(stage_lines)}

### Environment checks

| Check | Status | Detail |
|---|---|---|
{chr(10).join(environment_lines)}

Environment status counts: `{json.dumps(environment_counts, sort_keys=True)}`.

## Synthetic timing fixture summary

The numbers below are generated test-fixture values and are not DW3000 measurements.

| Metric | Count | Median (us) | P95 (us) | P99 (us) | Max (us) | Source | HW verified |
|---|---:|---:|---:|---:|---:|---|---|
{chr(10).join(timing_lines)}

Configured repetitions: `{definition.get('repetitions', 'unknown')}`; configured warm-up frames: `{definition.get('warmup_frames', 'unknown')}`; excluded warm-up frames: `{analysis_manifest.get('warmup_frames_excluded', 0)}`.

### Synthetic fault and omission accounting

| Diagnostic | Count |
|---|---:|
{chr(10).join(fault_lines)}

These counts intentionally exercise parser, timeout, retry, missing-data, and outlier paths. They are fixture diagnostics, not hardware error rates.

## 가정한 값

- Mock seed and fault profile come from the captured configuration.
- Mock timing distributions exist only to exercise software branches.

## 논문 기반 근거

- None used for the synthetic values in this report.

## 추후 확인 필요

- Connected-board identity and role mapping.
- UART baud rate and binary/text firmware logging contract.
- GPIO trace-pin mapping and logic analyzer sample rate.
- SPI clock waveform, IRQ/ISR path, CIR ownership, and processing durations.
- Reference distances, antenna placement, and identifiable calibration constraints.
- Real A1/A2/T1/T2 firmware targets and on-air protocol behavior.

Environment checks: `{len(environment.get('checks', []))}`; logic error/outlier rows: `{len(errors)}`; UART error rows: `{len(uart_errors)}`.

## Conclusion

{DISCLAIMER_KO}

`source_type = SYNTHETIC`  
`hardware_verified = false`
"""
    report_path = run_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path
