"""Configuration loader for Job Scout."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

import importlib.util

DEFAULT_CONFIG: Dict[str, Any] = {
    "sources": {"enabled": ["dummy"], "placeholders": []},
    "regions_path": "config/regions.json",
    "location_rules": {
        "include_regions": ["EU"],
        "include_countries": ["Italy"],
        "include_cities": ["New York"],
        "exclude_countries": ["UK"],
        "prefer_full_remote": True,
    },
    "role_targeting": {"include_titles": ["manager", "lead", "head"]},
    "salary_rules": {
        "minimum_eur": 52000,
        "allow_missing_salary": True,
        "currency_rates": {"EUR": 1.0, "USD": 0.92, "GBP": 1.17},
    },
    "scoring": {
        "base_score": 100,
        "penalty_weights": {
            "prefer_full_remote": 15,
            "missing_salary": 10,
        },
        "bonus_weights": {
            "full_remote": 5,
        },
    },
    "notifications": {
        "telegram": {
            "enabled": False,
            "bot_token_env_var": "TELEGRAM_BOT_TOKEN",
            "chat_id_env_var": "TELEGRAM_CHAT_ID",
        }
    },
}


def _deep_merge(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Merge incoming configuration into base without mutating inputs."""

    merged = deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path | str) -> Dict[str, Any]:
    """Load YAML configuration from path, applying defaults for missing fields."""

    config_path = Path(path)
    if not config_path.exists():
        return deepcopy(DEFAULT_CONFIG)

    raw = config_path.read_text(encoding="utf-8")
    data = _load_yaml(raw)
    return _deep_merge(DEFAULT_CONFIG, data)


def _load_yaml(raw: str) -> Dict[str, Any]:
    """Load YAML using PyYAML when available, otherwise a minimal parser."""

    yaml_spec = importlib.util.find_spec("yaml")
    if yaml_spec:
        import yaml  # type: ignore[import-not-found]

        return yaml.safe_load(raw) or {}
    return _parse_simple_yaml(raw)


def _parse_simple_yaml(raw: str) -> Dict[str, Any]:
    """Parse a simple subset of YAML for local config defaults."""

    cleaned_lines: List[tuple[int, str]] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        cleaned_lines.append((indent, stripped))

    root: Dict[str, Any] = {}
    stack: List[tuple[int, Any]] = [(0, root)]

    for index, (indent, stripped) in enumerate(cleaned_lines):
        while stack and indent < stack[-1][0]:
            stack.pop()

        current = stack[-1][1]
        if stripped.startswith("- "):
            item_value = _parse_scalar(stripped[2:])
            if isinstance(current, list):
                current.append(item_value)
            continue

        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value == "":
            next_container: Any = {}
            for next_indent, next_stripped in cleaned_lines[index + 1 :]:
                if next_indent <= indent:
                    break
                if next_stripped.startswith("- "):
                    next_container = []
                    break
                break
            if isinstance(current, dict):
                current[key] = next_container
            stack.append((indent + 2, next_container))
        else:
            if isinstance(current, dict):
                current[key] = _parse_scalar(value)
    return root


def _parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "~"}:
        return None
    if value.isdigit():
        return int(value)
    return value.strip("\"'")
