#!/usr/bin/env python3
"""Validate the pre-hardware Python, repository, schema, and mock workflow."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from _common import ROOT, root_relative


@dataclass
class Check:
    status: str
    name: str
    detail: str
    next_command: str = ""


def _package_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def run_checks(config_path: Path) -> list[Check]:
    checks: list[Check] = []
    version_ok = sys.version_info >= (3, 10)
    checks.append(Check("PASS" if version_ok else "FAIL", "Python", sys.version.split()[0]))

    required = {
        "PyYAML": _package_version("PyYAML"),
        "jsonschema": _package_version("jsonschema"),
        "numpy": _package_version("numpy"),
        "matplotlib": _package_version("matplotlib"),
    }
    missing = [name for name, version in required.items() if version is None]
    checks.append(
        Check(
            "FAIL" if missing else "PASS",
            "core dependencies",
            "missing: " + ", ".join(missing) if missing else ", ".join(f"{name} {version}" for name, version in required.items()),
            "python -m pip install -r requirements-core.txt" if missing else "",
        )
    )

    required_paths = [
        ROOT / "firmware_overlay" / "API" / "Src" / "custom_code" / "ds_twr_initiator_final.c",
        ROOT / "firmware_overlay" / "API" / "Src" / "custom_code" / "ds_twr_responder_final.c",
        ROOT / "artifacts" / "baseline" / "baseline_manifest.json",
    ]
    absent = [str(path.relative_to(ROOT)) for path in required_paths if not path.exists()]
    checks.append(Check("FAIL" if absent else "PASS", "repository structure", "missing: " + ", ".join(absent) if absent else "overlay and baseline snapshot found"))

    build_tools = {name: shutil.which(name) for name in ["emBuild.exe", "arm-none-eabi-gcc", "make", "cmake"]}
    found_build = [f"{name}={path}" for name, path in build_tools.items() if path]
    checks.append(
        Check(
            "PASS" if found_build else "SKIP",
            "firmware compiler/build tool",
            "; ".join(found_build) if found_build else "not on PATH; mock stage only",
            "Configure the approved SES/toolchain path after obtaining a clean full SDK.",
        )
    )

    jlink = shutil.which("JLink.exe") or shutil.which("JLinkExe")
    checks.append(Check("PASS" if jlink else "SKIP", "J-Link executable", jlink or "not found; hardware stage only", "JLink.exe -?" if not jlink else ""))
    checks.append(Check("SKIP", "J-Link devices", "not probed because boards are disconnected", "python tools/discover_hardware.py --config configs/local_hardware.yaml"))

    serial_version = _package_version("pyserial")
    checks.append(Check("PASS" if serial_version else "SKIP", "serial library", f"pyserial {serial_version}" if serial_version else "optional hardware dependency not installed", "python -m pip install -r requirements-hardware.txt" if not serial_version else ""))
    checks.append(Check("SKIP", "serial devices", "not probed because boards are disconnected", "python tools/discover_hardware.py --config configs/local_hardware.yaml"))

    sigrok = shutil.which("sigrok-cli")
    saleae = _package_version("saleae") or _package_version("logic2-automation")
    logic_details = "; ".join(value for value in [f"sigrok={sigrok}" if sigrok else "", f"Saleae package={saleae}" if saleae else ""] if value)
    checks.append(Check("PASS" if logic_details else "SKIP", "logic analyzer backend", logic_details or "no CLI/package; hardware stage only", "Install a selected optional logic backend, then rerun this checker."))
    checks.append(Check("SKIP", "logic analyzer device", "not probed because no analyzer is connected", "python tools/discover_hardware.py --config configs/local_hardware.yaml"))

    try:
        from hardware import create_backend
        from hardware.device_inventory import load_yaml, validate_config

        config = load_yaml(config_path)
        validate_config(config, allow_placeholders=False)
        checks.append(Check("PASS", "config schema", str(config_path.relative_to(ROOT))))
    except Exception as exc:
        checks.append(Check("FAIL", "config schema", str(exc)))
        config = {}

    results_root = ROOT / "results"
    try:
        results_root.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=results_root, prefix=".write_check_", delete=False) as handle:
            probe = Path(handle.name)
        probe.unlink()
        checks.append(Check("PASS", "output directory write", str(results_root)))
    except OSError as exc:
        checks.append(Check("FAIL", "output directory write", str(exc)))

    if config:
        try:
            with tempfile.TemporaryDirectory(prefix="uwb_mock_check_") as temporary:
                temp = Path(temporary)
                backend = create_backend("mock", config, temp)
                devices = backend.list_devices()
                ports = backend.list_ports()
                logic = backend.capture_logic(
                    {"frame_count": 3, "channels": config.get("logic_analyzer", {}).get("channels", {})},
                    temp / "logic.csv",
                    frame_count=3,
                )
                uart = backend.capture_serial(str(ports[0]["device"]), temp / "uart.bin", 0.05, record_count=4)
                valid = (
                    len(devices) == 4
                    and len(ports) == 4
                    and logic.get("source_type") == "SYNTHETIC"
                    and logic.get("hardware_verified") is False
                    and uart.get("source_type") == "SYNTHETIC"
                    and uart.get("hardware_verified") is False
                )
                checks.append(Check("PASS" if valid else "FAIL", "mock backend", "4-board inventory and synthetic capture provenance"))
                checks.append(Check("PASS" if valid else "FAIL", "dry-run experiment", "temporary mock logic/UART path completed"))
        except Exception as exc:
            checks.append(Check("FAIL", "mock backend", str(exc)))
            checks.append(Check("FAIL", "dry-run experiment", "mock prerequisite failed"))
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/mock_hardware.yaml")
    parser.add_argument("--json-output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks = run_checks(root_relative(args.config))
    for check in checks:
        print(f"[{check.status}] {check.name}: {check.detail}")
        if check.next_command:
            print(f"       Next: {check.next_command}")
    report: dict[str, Any] = {
        "source_type": "ENVIRONMENT_INSPECTION",
        "hardware_verified": False,
        "checks": [asdict(check) for check in checks],
    }
    if args.json_output:
        output = root_relative(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 1 if any(check.status == "FAIL" for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
