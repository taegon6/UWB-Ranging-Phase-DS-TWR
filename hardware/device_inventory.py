"""YAML loading, schema validation, and A1/A2/T1/T2 inventory helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = REPOSITORY_ROOT / "schemas"
EXPECTED_NODES = ("A1", "A2", "T1", "T2")
_TODO_RE = re.compile(r"^TODO(?:_|\(|\b)", re.IGNORECASE)


class ConfigError(ValueError):
    """Configuration parsing or validation failure with all known causes."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        self.errors = list(errors or [message])
        super().__init__(message)


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML mapping without mutating or resolving any placeholders."""

    source = Path(path)
    if not source.is_file():
        raise ConfigError(f"Configuration file does not exist: {source}")
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment checker reports it
        raise ConfigError("PyYAML is required to load YAML configuration") from exc
    try:
        loaded = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"Unable to parse YAML configuration {source}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigError(f"Configuration root must be a mapping: {source}")
    return loaded


def _format_path(parts: tuple[str | int, ...]) -> str:
    result = ""
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += ("." if result else "") + str(part)
    return result or "$"


def _placeholder_items(
    value: Any, parts: tuple[str | int, ...] = ()
) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            found.extend(_placeholder_items(value[key], (*parts, str(key))))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_placeholder_items(item, (*parts, index)))
    elif isinstance(value, str) and _TODO_RE.match(value.strip()):
        found.append((_format_path(parts), value.strip()))
    return found


def find_placeholders(config: Mapping[str, Any]) -> list[str]:
    """Return deterministic dotted paths containing unresolved TODO values."""

    return [path for path, _value in _placeholder_items(config)]


def _default_schema(config: Mapping[str, Any]) -> Path:
    kind = str(config.get("config_kind", "")).lower()
    if kind == "dw3000_independent_phy":
        return SCHEMA_ROOT / "dw3000_phy.schema.json"
    if kind.startswith("simulation_2a2t"):
        return SCHEMA_ROOT / "simulation_2a2t.schema.json"
    if "calibration" in config or "calibration" in kind:
        return SCHEMA_ROOT / "antenna_calibration.schema.json"
    if kind == "experiment" or (
        "experiment_id" in config and "boards" not in config
    ):
        return SCHEMA_ROOT / "experiment_config.schema.json"
    return SCHEMA_ROOT / "hardware_config.schema.json"


def _schema_errors(config: Mapping[str, Any], schema_path: Path) -> list[str]:
    if not schema_path.is_file():
        return [f"Schema file does not exist: {schema_path}"]
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return ["jsonschema is required for configuration validation"]
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"Unable to read JSON schema {schema_path}: {exc}"]
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for error in sorted(
        validator.iter_errors(dict(config)),
        key=lambda item: tuple(str(part) for part in item.path),
    ):
        location = _format_path(tuple(error.absolute_path))
        errors.append(f"{location}: {error.message}")
    return errors


def _semantic_errors(config: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    boards = config.get("boards")
    if isinstance(boards, Mapping):
        for node in EXPECTED_NODES:
            board = boards.get(node)
            if not isinstance(board, Mapping):
                continue
            expected_role = "ANCHOR" if node.startswith("A") else "TAG"
            role = str(board.get("role", "")).upper()
            if role and role != expected_role:
                errors.append(
                    f"boards.{node}.role: expected {expected_role}, received {role}"
                )
        for field in ("jlink_serial", "serial_port"):
            seen: dict[str, str] = {}
            for node, board in boards.items():
                if not isinstance(board, Mapping):
                    continue
                raw = board.get(field)
                if raw is None or (isinstance(raw, str) and _TODO_RE.match(raw.strip())):
                    continue
                value = str(raw)
                previous = seen.get(value)
                if previous is not None:
                    errors.append(
                        f"boards.{node}.{field}: duplicates boards.{previous}.{field} ({value})"
                    )
                else:
                    seen[value] = str(node)
    mock = config.get("mock")
    if isinstance(mock, Mapping):
        fault_sources = [mock]
        if isinstance(mock.get("faults"), Mapping):
            fault_sources.append(mock["faults"])
        for source in fault_sources:
            for key, raw in source.items():
                if key.endswith("_probability") and isinstance(raw, (int, float)):
                    if not 0.0 <= float(raw) <= 1.0:
                        errors.append(f"mock.{key}: probability must be between 0 and 1")
    return errors


def validate_config(
    config: Mapping[str, Any],
    schema_path: str | Path | None = None,
    allow_placeholders: bool = False,
) -> list[str]:
    """Validate a configuration and return allowed unresolved placeholder paths.

    Structural, schema, and semantic failures raise :class:`ConfigError` with an
    ``errors`` list.  TODO placeholders are permitted only when the caller
    explicitly sets ``allow_placeholders=True`` (normally a dry-run).
    """

    if not isinstance(config, Mapping):
        raise ConfigError("Configuration root must be a mapping")
    selected_schema = Path(schema_path) if schema_path else _default_schema(config)
    if not selected_schema.is_absolute():
        selected_schema = REPOSITORY_ROOT / selected_schema
    errors = _schema_errors(config, selected_schema)
    errors.extend(_semantic_errors(config))
    placeholders = find_placeholders(config)
    if placeholders and not allow_placeholders:
        errors.extend(
            f"{path}: unresolved placeholder is allowed only for dry-run"
            for path in placeholders
        )
    if errors:
        raise ConfigError("Configuration validation failed:\n- " + "\n- ".join(errors), errors)
    return placeholders


def build_inventory(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build a stable device/role inventory from the four configured boards."""

    boards = config.get("boards")
    if not isinstance(boards, Mapping):
        raise ConfigError("boards must be a mapping")
    semantic_errors = _semantic_errors({"boards": boards})
    if semantic_errors:
        raise ConfigError(
            "Invalid device inventory:\n- " + "\n- ".join(semantic_errors),
            semantic_errors,
        )
    inventory: list[dict[str, Any]] = []
    for node_id in EXPECTED_NODES:
        board = boards.get(node_id)
        if not isinstance(board, Mapping):
            raise ConfigError(f"Missing board mapping: boards.{node_id}")
        values = dict(board)
        entry = {
            "node_id": node_id,
            "role": values.get("role"),
            "jlink_serial": values.get("jlink_serial"),
            "serial_port": values.get("serial_port"),
            "firmware_target": values.get("firmware_target"),
            "placeholders": find_placeholders({"board": values}),
        }
        entry.update(
            {key: value for key, value in values.items() if key not in entry}
        )
        inventory.append(entry)
    return inventory


__all__ = [
    "ConfigError",
    "EXPECTED_NODES",
    "build_inventory",
    "find_placeholders",
    "load_yaml",
    "validate_config",
]
