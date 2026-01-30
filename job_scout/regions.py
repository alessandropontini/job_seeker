"""Region and country mapping utilities."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RegionData:
    """Region metadata loaded from configuration."""

    eu_countries: set[str]
    country_aliases: dict[str, str]


def load_region_data(path: Path | str) -> RegionData:
    """Load region metadata from a JSON file."""

    region_path = Path(path)
    if not region_path.exists():
        raise FileNotFoundError(
            f"Region data file not found: {region_path}"
        )
    raw = region_path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Region data file is not valid JSON: {region_path}"
        ) from exc
    return _parse_region_payload(payload, region_path)


def normalize_country(value: str | None, region_data: RegionData) -> str:
    """Normalize a country name using alias rules."""

    if not value:
        return ""
    trimmed = value.strip()
    if not trimmed:
        return ""
    alias_key = trimmed.lower()
    return region_data.country_aliases.get(alias_key, trimmed)


def _parse_region_payload(payload: Any, source: Path) -> RegionData:
    if not isinstance(payload, dict):
        raise ValueError(f"Region data must be a JSON object: {source}")
    eu_countries = payload.get("eu_countries")
    if not isinstance(eu_countries, list) or not eu_countries:
        raise ValueError(
            f"Region data requires non-empty eu_countries list: {source}"
        )
    aliases = payload.get("country_aliases", {})
    if not isinstance(aliases, dict):
        raise ValueError(
            f"Region data requires country_aliases mapping: {source}"
        )
    eu_set = {str(country).strip().lower() for country in eu_countries}
    alias_map = {
        str(key).strip().lower(): str(value).strip()
        for key, value in aliases.items()
    }
    return RegionData(eu_countries=eu_set, country_aliases=alias_map)
