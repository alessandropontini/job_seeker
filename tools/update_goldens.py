"""Regenerate golden outputs for Job Scout.

WARNING: This script overwrites committed golden files. Only run when
intentional output changes are expected and reviewed.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from job_scout.__main__ import main  # noqa: E402
from job_scout.golden import (  # noqa: E402
    normalize_csv_text,
    normalize_markdown_text,
)


def _build_config(
    source: str,
    allow_missing_salary: bool,
    prefer_full_remote: bool,
) -> str:
    allow_missing = str(allow_missing_salary).lower()
    prefer_remote = str(prefer_full_remote).lower()
    return textwrap.dedent(
        f"""
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
        """
    ).strip()


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
    if exit_code != 0:
        raise SystemExit(exit_code)
    csv_text = normalize_csv_text(
        (output_dir / "report.csv").read_text(encoding="utf-8")
    )
    md_text = normalize_markdown_text(
        (output_dir / "report.md").read_text(encoding="utf-8")
    )
    return csv_text, md_text


def main_cli() -> None:
    print(
        "WARNING: regenerating goldens; review diffs before committing."
    )
    fixture_dir = Path("tests/fixtures")
    if not fixture_dir.exists():
        raise FileNotFoundError("tests/fixtures not found")
    os.environ["JOB_SCOUT_FIXTURE_DIR"] = str(fixture_dir)

    scenarios = [
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
    ]

    golden_dir = Path("tests/golden")
    golden_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(".golden_tmp")
    tmp_path.mkdir(exist_ok=True)

    try:
        for name, config_text, args in scenarios:
            csv_text, md_text = _run_pipeline(tmp_path, config_text, args)
            (golden_dir / f"{name}_report.csv").write_text(
                csv_text, encoding="utf-8"
            )
            (golden_dir / f"{name}_report.md").write_text(
                md_text, encoding="utf-8"
            )
            print(f"Wrote goldens for {name}")
    finally:
        if tmp_path.exists():
            shutil.rmtree(tmp_path)


if __name__ == "__main__":
    raise SystemExit(main_cli())
