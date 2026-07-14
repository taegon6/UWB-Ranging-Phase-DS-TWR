from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_hardware_experiment.py"
CALIBRATOR = ROOT / "tools" / "calibrate_antenna_delay.py"


def run_cli(arguments: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def write_config(tmp_path: Path, mutate=None) -> Path:
    config = yaml.safe_load((ROOT / "configs" / "mock_hardware.yaml").read_text(encoding="utf-8"))
    if mutate:
        mutate(config)
    path = tmp_path / "mock.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def result_dir(completed: subprocess.CompletedProcess[str]) -> Path:
    line = next(line for line in completed.stdout.splitlines() if line.startswith("RESULT_DIR="))
    return Path(line.split("=", 1)[1])


def runner_command(config: Path, output: Path, *extra: str) -> list[str]:
    return [
        str(RUNNER),
        "--config",
        str(config),
        "--experiment",
        "timing_characterization",
        "--backend",
        "mock",
        "--dry-run",
        "--analyze",
        "--report",
        "--output-root",
        str(output),
        *extra,
    ]


def test_mock_timing_characterization_integration(tmp_path: Path) -> None:
    config = write_config(tmp_path)
    completed = run_cli(runner_command(config, tmp_path / "results"))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    run_dir = result_dir(completed)
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS"
    assert manifest["source_type"] == "SYNTHETIC"
    assert manifest["hardware_verified"] is False
    assert len(manifest["stages"]) == 14
    assert (run_dir / "raw" / "logic" / "logic_edges.csv").is_file()
    assert len(list((run_dir / "raw" / "uart").glob("*.bin"))) == 4
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "hardware_verified = false" in report
    assert "Synthetic fault and omission accounting" in report
    assert "Packet timeouts" in report
    analysis_manifest = json.loads((run_dir / "analysis" / "analysis_manifest.json").read_text(encoding="utf-8"))
    assert analysis_manifest["warmup_frames_excluded"] == 50
    assert (run_dir / "source_snapshot" / "attempt01" / "source_inventory.json").is_file()
    hashes = (run_dir / "firmware" / "hashes.txt").read_text(encoding="utf-8")
    assert "source_type = SYNTHETIC" in hashes
    assert "hardware_verified = false" in hashes


def test_mock_calibration_integration(tmp_path: Path) -> None:
    completed = run_cli(
        [
            str(CALIBRATOR),
            "--config",
            str(ROOT / "configs" / "antenna_calibration.example.yaml"),
            "--backend",
            "mock",
            "--dry-run",
            "--output-root",
            str(tmp_path / "results"),
        ]
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    run_dir = result_dir(completed)
    result = json.loads((run_dir / "analysis" / "calibration" / "calibration_result.json").read_text(encoding="utf-8"))
    assert result["status"] == "DRY_RUN_PASS"
    assert result["calibration_completed"] is False
    assert result["source_type"] == "SYNTHETIC"
    assert result["hardware_verified"] is False
    assert (run_dir / "figures" / "objective_curve.svg").is_file()
    assert result["samples_per_point"] == 1000
    assert result["warmup_samples_discarded_per_point"] == 100
    assert (run_dir / "analysis" / "calibration" / "mock_bias_table.csv").is_file()
    assert (run_dir / "environment_report.json").is_file()
    assert (run_dir / "unresolved_items.md").is_file()
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert f"Selected mock token: `{result['selected_mock_candidate']}`" in report
    svg = (run_dir / "figures" / "objective_curve.svg").read_text(encoding="utf-8")
    assert "source_type = SYNTHETIC" in svg
    assert "hardware_verified = false" in svg


def test_simulated_flash_failure_is_propagated_and_recorded(tmp_path: Path) -> None:
    def mutate(config):
        config["mock"]["faults"]["flash_fail_nodes"] = ["A2"]

    config = write_config(tmp_path, mutate)
    output = tmp_path / "results"
    completed = run_cli(runner_command(config, output))
    assert completed.returncode == 1
    run_dir = next(output.iterdir())
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAIL"
    failed = next(stage for stage in manifest["stages"] if stage["status"] == "FAIL")
    assert failed["name"] == "FLASH"
    assert "simulated flash failure" in failed["reason"]


def test_simulated_serial_disconnect_is_detected(tmp_path: Path) -> None:
    def mutate(config):
        config["mock"]["faults"]["missing_com_nodes"] = ["T2"]

    config = write_config(tmp_path, mutate)
    output = tmp_path / "results"
    completed = run_cli(runner_command(config, output))
    assert completed.returncode == 1
    run_dir = next(output.iterdir())
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert next(stage for stage in manifest["stages"] if stage["status"] == "FAIL")["name"] == "DISCOVER_DEVICES"


def test_simulated_missing_logic_channel_is_detected(tmp_path: Path) -> None:
    def mutate(config):
        config["mock"]["faults"]["missing_logic_channels"] = ["CIR_READ"]

    config = write_config(tmp_path, mutate)
    output = tmp_path / "results"
    completed = run_cli(runner_command(config, output))
    assert completed.returncode == 1
    run_dir = next(output.iterdir())
    missing = json.loads((run_dir / "analysis" / "missing_metrics.json").read_text(encoding="utf-8"))
    assert "cir_read_duration" in missing["missing_metrics"]
    assert missing["hardware_verified"] is False


def test_resume_after_interrupted_failure(tmp_path: Path) -> None:
    def fail(config):
        config["mock"]["faults"]["flash_fail_nodes"] = ["A2"]

    config = write_config(tmp_path, fail)
    output = tmp_path / "results"
    first = run_cli(runner_command(config, output))
    assert first.returncode == 1
    run_dir = next(output.iterdir())
    repaired = yaml.safe_load(config.read_text(encoding="utf-8"))
    repaired["mock"]["faults"]["flash_fail_nodes"] = []
    config.write_text(yaml.safe_dump(repaired, sort_keys=False), encoding="utf-8")
    resumed = run_cli(runner_command(config, output, "--resume", str(run_dir)))
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS"
    assert manifest["resume_history"][0]["name"] == "FLASH"
    assert len({stage["name"] for stage in manifest["stages"]}) == 14


def test_identical_configs_create_unique_run_ids(tmp_path: Path) -> None:
    config = write_config(tmp_path)
    output = tmp_path / "results"
    first = run_cli(runner_command(config, output))
    second = run_cli(runner_command(config, output))
    assert first.returncode == second.returncode == 0
    assert result_dir(first) != result_dir(second)
    assert len(list(output.iterdir())) == 2


def test_real_cli_rejects_mock_adapter_mapping_before_any_operation(tmp_path: Path) -> None:
    config = yaml.safe_load((ROOT / "configs" / "mock_hardware.yaml").read_text(encoding="utf-8"))
    config["backend"] = {"flash": "mock", "serial": "mock", "logic": "mock"}
    path = tmp_path / "unsafe-real.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    completed = run_cli(
        [
            str(RUNNER),
            "--config",
            str(path),
            "--experiment",
            "connection_smoke_test",
            "--backend",
            "real",
            "--execute",
            "--output-root",
            str(tmp_path / "results"),
        ]
    )
    assert completed.returncode == 1
    assert "forbids mock adapters" in completed.stdout
