from pathlib import Path

from job_scout.__main__ import main


def test_cli_run_smoke(tmp_path):
    output_dir = tmp_path / "out"
    config_path = Path("config/config.yaml")

    exit_code = main(
        [
            "run",
            "--since-days",
            "7",
            "--output-dir",
            str(output_dir),
            "--config",
            str(config_path),
        ]
    )

    assert exit_code == 0
    assert (output_dir / "report.csv").exists()
    assert (output_dir / "report.md").exists()


def test_cli_run_with_fixture_file(tmp_path):
    output_dir = tmp_path / "out"
    config_path = Path("config/e2e_fake.yaml")
    fixture_path = Path("tests/fixtures/e2e_fake_jobs.json")

    exit_code = main(
        [
            "run",
            "--since-days",
            "3650",
            "--output-dir",
            str(output_dir),
            "--config",
            str(config_path),
            "--source",
            "dummy",
            "--fixture-file",
            str(fixture_path),
        ]
    )

    assert exit_code == 0
    assert (output_dir / "report.csv").exists()
