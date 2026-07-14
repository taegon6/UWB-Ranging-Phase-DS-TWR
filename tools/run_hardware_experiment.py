#!/usr/bin/env python3
"""Run the guarded pre-hardware experiment state machine and report pipeline."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from _common import ROOT, root_relative

from analysis.report_generator import generate_experiment_report
from analysis.uart_analysis import decode_uart_file
from check_environment import run_checks
from experiments.definitions import (
    RUN_STAGES,
    StageRecord,
    append_stage,
    base_manifest,
    config_hash,
    create_run_directory,
    validate_stage_order,
    write_source_snapshot,
    write_json,
)
from experiments.timing_characterization import analyze_logic
from hardware import ConfigError, build_inventory, create_backend, load_yaml, validate_config
from tools.build_firmware import build_firmware
from tools.flash_all import plan_flash


def _combine_csv(inputs: list[Path], output: Path) -> None:
    rows: list[dict[str, str]] = []
    fields: list[str] = []
    for path in inputs:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for field in reader.fieldnames or []:
                if field not in fields:
                    fields.append(field)
            rows.extend(reader)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_unresolved(run_dir: Path, *, source_type: str = "SYNTHETIC") -> None:
    (run_dir / "unresolved_items.md").write_text(
        "# Unresolved items\n\n"
        "- `TODO(HW_VERIFY)`: A1/A2/T1/T2 J-Link and UART identity.\n"
        "- `TODO(HW_VERIFY)`: real trace pins, analyzer channel mapping, sample rate, and voltage threshold.\n"
        "- `TODO(HW_VERIFY)`: actual SPI, IRQ, UART, CIR and phase-processing durations.\n"
        "- `TODO(HW_VERIFY)`: reference geometry and antenna-delay constraints.\n"
        "- `TODO(IMPLEMENT_2A2T_FW)`: baseline supports A1/B2 with one TG only.\n\n"
        f"`source_type = {source_type}`  \n`hardware_verified = false`\n",
        encoding="utf-8",
    )


class ExperimentRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.config_path = root_relative(args.config)
        self.config = load_yaml(self.config_path)
        self.experiment = self.config.get("experiments", {}).get(args.experiment)
        if not isinstance(self.experiment, dict):
            raise ConfigError(f"Unknown experiment {args.experiment!r} in {self.config_path}")
        self.output_root = root_relative(args.output_root or self.config.get("outputs", {}).get("results_root", "results"))
        self.start = datetime.now().astimezone()
        self.config_changed = False
        if args.resume:
            self.run_dir = root_relative(args.resume)
            self.manifest = json.loads((self.run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.run_id = str(self.manifest["run_id"])
            if self.manifest.get("status") == "PASS":
                raise ConfigError("Refusing to resume an already completed run")
            if self.manifest.get("backend") != args.backend:
                raise ConfigError("Resume backend must match the original run manifest")
            failed_stages = [
                stage for stage in self.manifest.get("stages", []) if stage.get("status") not in {"PASS", "SKIP", "DRY_RUN_PASS"}
            ]
            self.manifest["status"] = "RUNNING"
            self.manifest["resumed_at"] = self.start.isoformat()
            resumed_hash = config_hash(self.config)
            previous_hash = self.manifest.get("config_hash")
            if previous_hash != resumed_hash:
                self.config_changed = True
                self.manifest.setdefault("resume_config_changes", []).append(
                    {
                        "previous_config_hash": previous_hash,
                        "resumed_config_hash": resumed_hash,
                        "timestamp": self.start.isoformat(),
                    }
                )
                self.manifest["config_hash"] = resumed_hash
                previous_stages = list(self.manifest.get("stages", []))
                self.manifest.setdefault("resume_history", []).extend(failed_stages)
                for stage in previous_stages:
                    if stage in failed_stages:
                        continue
                    self.manifest.setdefault("resume_history", []).append(
                        {**stage, "resume_reason": "config hash changed; stage invalidated"}
                    )
                self.manifest["stages"] = []
            elif failed_stages:
                self.manifest.setdefault("resume_history", []).extend(failed_stages)
                self.manifest["stages"] = [
                    stage
                    for stage in self.manifest.get("stages", [])
                    if stage.get("status") in {"PASS", "SKIP", "DRY_RUN_PASS"}
                ]
            self.manifest.pop("failure", None)
        else:
            self.run_id, self.run_dir = create_run_directory(
                self.output_root,
                args.experiment,
                backend=args.backend,
                now=self.start,
            )
            self.manifest = base_manifest(
                run_id=self.run_id,
                backend=args.backend,
                config=self.config,
                repository_root=ROOT,
                start_time=self.start.isoformat(),
            )
        self.backend: Any = None
        self.devices: list[dict[str, Any]] = []
        self.ports: list[dict[str, Any]] = []
        self.logic_capture = self.run_dir / "raw" / "logic" / "logic_edges.csv"
        self.logic_raw_capture = self.run_dir / "raw" / "logic" / "logic_capture.csv"
        self.uart_files: list[Path] = []
        self.completed = {
            stage["name"]
            for stage in self.manifest.get("stages", [])
            if stage.get("status") in {"PASS", "SKIP", "DRY_RUN_PASS"}
        }
        write_json(self.run_dir / "run_manifest.json", self.manifest)

    def _stage(self, name: str, function: Callable[[], str | None], *, rerun: bool = False) -> None:
        if name in self.completed:
            if rerun:
                function()
            return
        started = time.perf_counter()
        try:
            reason = function() or ""
        except Exception as exc:
            duration = time.perf_counter() - started
            append_stage(
                self.manifest,
                StageRecord(name, "FAIL", duration, f"{type(exc).__name__}: {exc}"),
            )
            write_json(self.run_dir / "run_manifest.json", self.manifest)
            raise
        duration = time.perf_counter() - started
        status = "SKIP" if reason.startswith("SKIP:") else "PASS"
        if status == "SKIP":
            reason = reason.removeprefix("SKIP:").strip()
        append_stage(self.manifest, StageRecord(name, status, duration, reason))
        if not validate_stage_order(self.manifest["stages"]):
            raise RuntimeError("runner stage order or uniqueness is invalid")
        write_json(self.run_dir / "run_manifest.json", self.manifest)

    def validate(self) -> str:
        validate_config(self.config, allow_placeholders=self.args.dry_run)
        configured_backend = self.config.get("backend")
        if self.args.backend == "mock":
            if not self.args.dry_run or self.args.execute:
                raise ConfigError("mock backend requires --dry-run and forbids --execute")
            if configured_backend != "mock":
                raise ConfigError("--backend mock requires config backend: mock")
            outputs = self.config.get("outputs", {})
            if outputs.get("source_type") != "SYNTHETIC" or outputs.get("hardware_verified") is not False:
                raise ConfigError("mock config must declare source_type=SYNTHETIC and hardware_verified=false")
        else:
            if not self.args.execute or self.args.dry_run:
                raise ConfigError("real backend requires explicit --execute")
            if not isinstance(configured_backend, dict):
                raise ConfigError("--backend real requires a flash/serial/logic backend mapping")
            expected = {"flash", "serial", "logic"}
            if set(configured_backend) != expected:
                raise ConfigError(f"real backend mapping must contain exactly {sorted(expected)}")
            mock_adapters = sorted(name for name, value in configured_backend.items() if value == "mock")
            if mock_adapters:
                raise ConfigError("real execution forbids mock adapters: " + ", ".join(mock_adapters))
            allowed = {
                "flash": {"jlink"},
                "serial": {"pyserial", "serial"},
                "logic": {"saleae", "sigrok"},
            }
            invalid = {
                name: configured_backend[name]
                for name in expected
                if configured_backend[name] not in allowed[name]
            }
            if invalid:
                raise ConfigError(f"unsupported real backend mapping: {invalid}")
            unsupported_flags = [
                flag
                for flag, enabled in {
                    "--build": self.args.build,
                    "--flash": self.args.flash,
                    "--capture-logic": self.args.capture_logic,
                    "--analyze": self.args.analyze,
                    "--report": self.args.report,
                }.items()
                if enabled
            ]
            if self.args.experiment != "connection_smoke_test" or unsupported_flags:
                raise ConfigError(
                    "pre-hardware real runner is limited to UART-only connection_smoke_test; "
                    "unsupported options: " + (", ".join(unsupported_flags) or self.args.experiment)
                )
        return "dry-run placeholders allowed" if self.args.dry_run else "real placeholders resolved"

    def check_environment(self) -> str:
        checks = run_checks(root_relative("configs/mock_hardware.yaml") if self.args.backend == "mock" else self.config_path)
        environment = {
            "source_type": "SYNTHETIC" if self.args.backend == "mock" else "ENVIRONMENT_INSPECTION",
            "hardware_verified": False,
            "checks": [asdict(check) for check in checks],
        }
        write_json(self.run_dir / "environment_report.json", environment)
        failures = [check for check in checks if check.status == "FAIL"]
        if failures:
            raise RuntimeError("environment failures: " + "; ".join(check.name for check in failures))
        return f"{len(checks)} checks; optional hardware checks may be SKIP"

    def discover(self) -> str:
        if self.args.backend == "mock":
            self.backend = create_backend("mock", self.config, self.run_dir)
            self.devices = list(self.backend.list_devices())
            self.ports = list(self.backend.list_ports())
            logic_devices = list(self.backend.list_devices(kind="logic"))
        else:
            mapping = self.config["backend"]
            self.backend = {
                "flash": create_backend(mapping["flash"], self.config, self.run_dir),
                "serial": create_backend(mapping["serial"], self.config, self.run_dir),
                "logic": create_backend(mapping["logic"], self.config, self.run_dir),
            }
            self.devices = list(self.backend["flash"].list_devices())
            discovered_serial = list(self.backend["serial"].list_ports())
            discovered_by_device = {
                str(port.get("device")): port for port in discovered_serial
            }
            configured_ports = {
                node: str(board["serial_port"])
                for node, board in self.config["boards"].items()
            }
            missing_ports = {
                node: port
                for node, port in configured_ports.items()
                if port not in discovered_by_device
            }
            if missing_ports:
                raise RuntimeError(f"configured UART ports were not discovered: {missing_ports}")
            self.ports = [
                {**discovered_by_device[port], "node_id": node}
                for node, port in configured_ports.items()
            ]
            logic_devices = list(self.backend["logic"].list_devices())
        inventory = {
            "configured": build_inventory(self.config),
            "flash_devices": self.devices,
            "serial_ports": self.ports,
            "logic_devices": logic_devices,
            "source_type": "SYNTHETIC" if self.args.backend == "mock" else "DISCOVERED_UNVERIFIED",
            "hardware_verified": False,
        }
        write_json(self.run_dir / "device_inventory.json", inventory)
        if self.args.backend == "mock" and (len(self.devices) != 4 or len(self.ports) != 4 or len(logic_devices) != 1):
            raise RuntimeError("mock inventory fault prevented the nominal run")
        return f"flash={len(self.devices)}, serial={len(self.ports)}, logic={len(logic_devices)}"

    def build(self) -> str:
        if self.args.backend == "mock":
            build_firmware(self.config, self.run_dir / "firmware", dry_run=True, execute=False)
            return "A1/A2/T1/T2 build matrix planned; no compiler invoked"
        if not self.args.build:
            return "SKIP: --build not requested"
        build_firmware(self.config, self.run_dir / "firmware", dry_run=False, execute=True)
        return "firmware built but not hardware verified"

    def flash(self) -> str:
        build_manifest_path = self.run_dir / "firmware" / "build_manifest.json"
        build_manifest = json.loads(build_manifest_path.read_text(encoding="utf-8")) if build_manifest_path.exists() else None
        plan = plan_flash(self.config, build_manifest)
        results = []
        if self.args.backend == "mock":
            device_by_node = {str(device["node_id"]): device for device in self.devices}
            for operation in plan["operations"]:
                result = self.backend.flash(
                    device_by_node[operation["node"]],
                    Path(str(operation["image"])),
                    execute=False,
                )
                results.append(result)
                if not result.get("success"):
                    write_json(self.run_dir / "firmware" / "flash_manifest.json", {**plan, "results": results})
                    raise RuntimeError(f"simulated flash failure for {operation['node']}")
            write_json(self.run_dir / "firmware" / "flash_manifest.json", {**plan, "results": results})
            return "four-node flash plan simulated; J-Link not invoked"
        if not self.args.flash:
            return "SKIP: --flash not requested"
        raise RuntimeError("real flash must use verified image paths and backend-specific plan")

    def reset(self) -> str:
        if self.args.backend == "mock":
            for device in self.devices:
                self.backend.reset(device, execute=False)
            return "synthetic reset order A1/A2/T1/T2"
        if not self.args.flash:
            return "SKIP: reset skipped because --flash was not requested"
        for device in self.devices:
            self.backend["flash"].reset(device, execute=True)
        return "real reset requested; result remains unverified until smoke data"

    def start_logic(self) -> str:
        if self.args.backend != "mock" and not self.args.capture_logic:
            return "SKIP: --capture-logic not requested"
        logic_config = dict(self.config.get("logic_analyzer", {}))
        repetitions = int(self.experiment.get("repetitions", 64))
        warmup_frames = int(self.experiment.get("warmup_frames", 0))
        logic_config["frame_count"] = repetitions + warmup_frames
        duration = float(self.experiment.get("capture_duration_s", 1.0))
        logic_sidecar = self.logic_capture.with_suffix(self.logic_capture.suffix + ".metadata.json")
        if self.args.resume and self.logic_capture.exists():
            if self.config_changed:
                raise RuntimeError("changed-config resume will not reuse or overwrite existing logic raw data")
            if not logic_sidecar.exists():
                raise RuntimeError("existing logic raw data has no completion sidecar; start a new run")
            return f"reused completed logic capture; requested_frames={repetitions}, warmup_frames={warmup_frames}"
        if self.args.backend == "mock":
            result = self.backend.capture_logic(logic_config, self.logic_capture, duration_s=duration, execute=False)
        else:
            result = self.backend["logic"].capture(
                logic_config,
                self.logic_raw_capture,
                duration_s=duration,
                execute=True,
            )
            export_result = self.backend["logic"].export_edges(
                self.logic_raw_capture,
                self.logic_capture,
            )
            write_json(
                logic_sidecar,
                {
                    "capture": result,
                    "edge_export": export_result,
                    "source_type": "MEASURED",
                    "hardware_verified": False,
                },
            )
        if not result.get("success", True):
            raise RuntimeError(f"logic capture failed: {result}")
        return (
            f"edges={result.get('edge_count', 'unknown')}; "
            f"requested_frames={repetitions}; warmup_frames={warmup_frames}"
        )

    def start_uart(self) -> str:
        connection_smoke = self.args.experiment == "connection_smoke_test"
        if self.args.backend != "mock" and not (self.args.capture_uart or connection_smoke):
            return "SKIP: --capture-uart not requested"
        duration = float(self.experiment.get("capture_duration_s", 1.0))
        record_count = int(self.experiment.get("repetitions", 8)) + int(self.experiment.get("warmup_frames", 0))
        reused = 0
        for port in self.ports:
            node = str(port.get("node_id", "UNKNOWN"))
            device = str(port.get("device"))
            output = self.run_dir / "raw" / "uart" / f"{node}.bin"
            sidecar = output.with_suffix(output.suffix + ".metadata.json")
            if self.args.resume and output.exists():
                if self.config_changed:
                    raise RuntimeError(f"changed-config resume will not reuse or overwrite {output.name}")
                if not sidecar.exists():
                    raise RuntimeError(f"existing UART raw data has no completion sidecar: {output.name}")
                self.uart_files.append(output)
                reused += 1
                continue
            if self.args.backend == "mock":
                self.backend.capture_serial(
                    device,
                    output,
                    duration,
                    execute=False,
                    record_count=record_count,
                )
            else:
                self.backend["serial"].capture(device, output, duration, execute=True)
            self.uart_files.append(output)
        return f"captured {len(self.uart_files) - reused} and reused {reused} UART streams"

    def run_experiment(self) -> str:
        summary = {
            "experiment": self.args.experiment,
            "definition": self.experiment,
            "backend_history": getattr(self.backend, "history", []),
            "source_type": "SYNTHETIC" if self.args.backend == "mock" else "UNVERIFIED_HW",
            "hardware_verified": False,
        }
        write_json(self.run_dir / "raw" / "experiment_summary.json", summary)
        return "mock event generation complete" if self.args.backend == "mock" else "experiment command dispatched"

    def stop_capture(self) -> str:
        return "synchronous adapters closed"

    def validate_raw(self) -> str:
        if not self.uart_files:
            self.uart_files = sorted((self.run_dir / "raw" / "uart").glob("*.bin"))
        required = []
        if self.logic_capture.exists():
            required.append(self.logic_capture)
        required.extend(path for path in self.uart_files if path.exists())
        if self.args.backend == "mock" and len(required) != 5:
            raise RuntimeError(f"expected one logic and four UART raw files, found {len(required)}")
        if self.args.backend == "real" and self.args.experiment == "connection_smoke_test" and len(self.uart_files) != 4:
            raise RuntimeError(f"connection smoke requires four UART raw files, found {len(self.uart_files)}")
        for path in required:
            if path.stat().st_size == 0:
                raise RuntimeError(f"empty raw file: {path}")
        return f"{len(required)} non-empty raw files preserved"

    def analyze(self) -> str:
        if not self.args.analyze:
            return "SKIP: --analyze not requested"
        if not self.logic_capture.exists():
            raise RuntimeError("logic capture is missing")
        derived_source_type = "SYNTHETIC" if self.args.backend == "mock" else "MEASURED"
        logic_result = analyze_logic(
            self.logic_capture,
            self.run_dir,
            source_type=derived_source_type,
            hardware_verified=False,
            warmup_frames=int(self.experiment.get("warmup_frames", 0)),
        )
        with (self.run_dir / "analysis" / "timing_summary.csv").open("r", encoding="utf-8", newline="") as handle:
            available_metrics = {row["metric"] for row in csv.DictReader(handle)}
        required_metrics = set(self.experiment.get("metrics", []))
        missing_metrics = sorted(required_metrics - available_metrics)
        if missing_metrics:
            write_json(
                self.run_dir / "analysis" / "missing_metrics.json",
                {
                    "missing_metrics": missing_metrics,
                    "source_type": derived_source_type,
                    "hardware_verified": False,
                },
            )
            raise RuntimeError("required logic metrics are missing: " + ", ".join(missing_metrics))
        decoded_paths: list[Path] = []
        uart_error_paths: list[Path] = []
        if not self.uart_files:
            self.uart_files = sorted((self.run_dir / "raw" / "uart").glob("*.bin"))
        for raw in self.uart_files:
            decoded = self.run_dir / "intermediate" / f"decoded_{raw.stem}.csv"
            errors = self.run_dir / "analysis" / f"uart_errors_{raw.stem}.csv"
            decode_uart_file(
                raw,
                decoded,
                errors,
                source_type=derived_source_type,
                hardware_verified=False,
            )
            decoded_paths.append(decoded)
            uart_error_paths.append(errors)
        _combine_csv(decoded_paths, self.run_dir / "intermediate" / "decoded_records.csv")
        _combine_csv(uart_error_paths, self.run_dir / "analysis" / "uart_errors.csv")
        write_json(self.run_dir / "analysis" / "analysis_manifest.json", logic_result)
        return f"{logic_result['metric_count']} timing metrics and {len(decoded_paths)} UART streams"

    def report(self) -> str:
        if not self.args.report:
            return "SKIP: --report not requested"
        self.manifest["status"] = "PASS"
        self.manifest["end_time"] = datetime.now().astimezone().isoformat()
        write_json(self.run_dir / "run_manifest.json", self.manifest)
        generate_experiment_report(self.run_dir)
        return "automatic synthetic validation report generated"

    def archive(self) -> str:
        _write_unresolved(
            self.run_dir,
            source_type="SYNTHETIC" if self.args.backend == "mock" else "UNVERIFIED_HW",
        )
        return "run folder retained; no raw data deleted or overwritten"

    def execute(self) -> Path:
        snapshots = self.run_dir / "config_snapshot"
        snapshots.mkdir(exist_ok=True)
        snapshot_target = snapshots / self.config_path.name
        if self.args.resume and snapshot_target.exists():
            resume_index = len(list(snapshots.glob(f"resume??_{self.config_path.name}"))) + 1
            snapshot_target = snapshots / f"resume{resume_index:02d}_{self.config_path.name}"
        shutil.copy2(self.config_path, snapshot_target)
        source_snapshot = self.run_dir / "source_snapshot"
        source_snapshot.mkdir(exist_ok=True)
        attempt_index = len(list(source_snapshot.iterdir())) + 1
        write_source_snapshot(
            ROOT,
            source_snapshot / f"attempt{attempt_index:02d}",
            extra_sources=[
                ROOT / "artifacts" / "baseline" / "baseline_manifest.json",
                ROOT / "artifacts" / "current_code_analysis.md",
            ],
        )
        actions = [
            ("VALIDATE_CONFIG", self.validate),
            ("CHECK_ENVIRONMENT", self.check_environment),
            ("DISCOVER_DEVICES", self.discover),
            ("BUILD", self.build),
            ("FLASH", self.flash),
            ("RESET_AND_SYNC", self.reset),
            ("START_LOGIC_CAPTURE", self.start_logic),
            ("START_UART_CAPTURE", self.start_uart),
            ("RUN_EXPERIMENT", self.run_experiment),
            ("STOP_CAPTURE", self.stop_capture),
            ("VALIDATE_RAW_DATA", self.validate_raw),
            ("ANALYZE", self.analyze),
            ("GENERATE_REPORT", self.report),
            ("ARCHIVE", self.archive),
        ]
        try:
            for name, action in actions:
                self._stage(name, action, rerun=bool(self.args.resume and name == "DISCOVER_DEVICES"))
            self.manifest["status"] = "PASS"
            self.manifest["end_time"] = datetime.now().astimezone().isoformat()
        except KeyboardInterrupt:
            self.manifest["status"] = "INTERRUPTED"
            self.manifest["end_time"] = datetime.now().astimezone().isoformat()
            write_json(self.run_dir / "run_manifest.json", self.manifest)
            raise
        except Exception as exc:
            self.manifest["status"] = "FAIL"
            self.manifest["failure"] = {"type": type(exc).__name__, "message": str(exc)}
            self.manifest["end_time"] = datetime.now().astimezone().isoformat()
            _write_unresolved(
                self.run_dir,
                source_type="SYNTHETIC" if self.args.backend == "mock" else "UNVERIFIED_HW",
            )
            write_json(self.run_dir / "run_manifest.json", self.manifest)
            raise
        write_json(self.run_dir / "run_manifest.json", self.manifest)
        if self.args.report and self.args.backend == "mock":
            generate_experiment_report(self.run_dir)
        return self.run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--backend", choices=["mock", "real"], required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--capture-uart", action="store_true")
    parser.add_argument("--capture-logic", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--resume", help="Resume a retained run directory")
    parser.add_argument("--output-root")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run_dir = ExperimentRunner(args).execute()
    except (ConfigError, RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return 1
    if args.backend == "mock":
        print("[PASS] mock experiment and report pipeline")
        print("source_type = SYNTHETIC")
        print("hardware_verified = false")
    else:
        print("[PASS] guarded real connection workflow")
        print("source_type = UNVERIFIED_HW")
        print("hardware_verified = false")
    print(f"RESULT_DIR={run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
