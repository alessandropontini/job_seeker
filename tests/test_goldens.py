from __future__ import annotations

import difflib
from pathlib import Path

import pytest

from job_scout.__main__ import main
from job_scout.golden import normalize_csv_text, normalize_markdown_text


def _build_config(
    source: str,
    allow_missing_salary: bool,
    prefer_full_remote: bool,
) -> str:
    allow_missing = str(allow_missing_salary).lower()
    prefer_remote = str(prefer_full_remote).lower()
    return f"""
regions_path: config/regions.json
sources:
  enabled:
    - {source}

location_rules:
  include_regions:
    - EU
  include_countries:
    - Italy
  include_cities:
    - New York
  exclude_countries:
    - UK
  prefer_full_remote: {prefer_remote}

role_targeting:
  include_titles:
    - manager
    - lead
    - head

salary_rules:
  minimum_eur: 52000
  allow_missing_salary: {allow_missing}
  currency_rates:
    EUR: 1.0
    USD: 0.92
    GBP: 1.17

scoring:
  base_score: 100
  penalty_weights:
    prefer_full_remote: 15
    missing_salary: 10
  bonus_weights:
    full_remote: 5
""".strip()


def _run_pipeline(tmp_path: Path, config_text: str, args: list[str]) -> tuple[str, str]:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_text, encoding="utf-8")
    output_dir = tmp_path / "out"
    command = [
        "run",
        "--since-days",
        "4000",
        "--output-dir",
        str(output_dir),
        "--config",
        str(config_path),
        *args,
    ]
    exit_code = main(command)
    assert exit_code == 0
    csv_text = normalize_csv_text(
        (output_dir / "report.csv").read_text(encoding="utf-8")
    )
    md_text = normalize_markdown_text(
        (output_dir / "report.md").read_text(encoding="utf-8")
    )
    return csv_text, md_text


def _assert_golden(actual: str, golden_path: Path) -> None:
    expected = golden_path.read_text(encoding="utf-8")
    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                actual.splitlines(),
                fromfile=str(golden_path),
                tofile="actual",
                lineterm="",
            )
        )
        raise AssertionError(f"Golden mismatch:\n{diff}")


@pytest.mark.parametrize(
    ("name", "config_text", "args"),
    [
        (
            "dummy_default",
            _build_config("dummy", True, True),
            [],
        ),
        (
            "dummy_strict_disallow_missing",
            _build_config("dummy", False, True),
            ["--strict"],
        ),
        (
            "remotive_no_prefer_full_remote",
            _build_config("remotive", True, False),
            [],
        ),
    ],
)
def test_golden_reports(tmp_path, monkeypatch, name, config_text, args):
    monkeypatch.setenv("JOB_SCOUT_FIXTURE_DIR", "tests/fixtures")
    csv_text, md_text = _run_pipeline(tmp_path, config_text, args)

    golden_dir = Path("tests/golden")
    _assert_golden(csv_text, golden_dir / f"{name}_report.csv")
    _assert_golden(md_text, golden_dir / f"{name}_report.md")
