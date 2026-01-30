import json

import pytest

from job_scout.regions import load_region_data, normalize_country


def test_load_region_data_success():
    region_data = load_region_data("config/regions.json")
    assert "germany" in region_data.eu_countries
    assert normalize_country("UK", region_data) == "UK"


def test_load_region_data_missing(tmp_path):
    missing_path = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        load_region_data(missing_path)


def test_load_region_data_invalid(tmp_path):
    invalid_path = tmp_path / "regions.json"
    invalid_path.write_text(json.dumps({"eu_countries": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_region_data(invalid_path)
