from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_environment_checker_cli() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_environment.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "[PASS] mock backend" in completed.stdout
    assert "[SKIP] serial devices" in completed.stdout


def test_multi_uart_fixture_capture_and_overwrite_guard(tmp_path: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "tools" / "capture_uart.py"),
        "--config",
        str(ROOT / "configs" / "mock_hardware.yaml"),
        "--backend",
        "mock",
        "--output-dir",
        str(tmp_path / "uart"),
        "--duration",
        "0.1",
        "--dry-run",
    ]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=20, check=False)
    assert first.returncode == 0, first.stdout + first.stderr
    assert len(list((tmp_path / "uart").glob("*.bin"))) == 4
    second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=20, check=False)
    assert second.returncode != 0
    assert "overwrite" in (second.stdout + second.stderr).lower()


def test_subprocess_build_failure_propagates(tmp_path: Path) -> None:
    config = yaml.safe_load((ROOT / "configs" / "mock_hardware.yaml").read_text(encoding="utf-8"))
    failure = [sys.executable, "-c", "import sys; sys.exit(7)"]
    config["firmware"] = {
        "working_directory": ".",
        "role_build_commands": {node: failure for node in ["A1", "A2", "T1", "T2"]},
    }
    config_path = tmp_path / "build_failure.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "build_firmware.py"),
            "--config",
            str(config_path),
            "--output",
            str(tmp_path / "build"),
            "--execute",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode != 0
    assert "build failed for A1 with exit code 7" in completed.stderr
