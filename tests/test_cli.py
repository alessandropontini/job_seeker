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


def test_cli_run_summary_contains_telegram_fields(tmp_path, monkeypatch):
    import json
    from job_scout import __main__ as main_mod
    from job_scout.pipeline import PipelineSummary

    output_dir = tmp_path / "out"
    config_path = Path("config/config.yaml")

    monkeypatch.setattr(
        main_mod,
        "run_pipeline",
        lambda **_kwargs: (
            [],
            PipelineSummary(3, 3, 1, 1, {"remotive": 2, "wwr": 1}),
        ),
    )
    monkeypatch.setattr(
        main_mod,
        "maybe_notify",
        lambda *args, **kwargs: __import__("job_scout.notifications", fromlist=["NotificationResult"]).NotificationResult(
            notified_count=1,
            notification_mode="daily_window",
            notified=True,
            digest_date_local="2024-02-10",
            window_start="2024-02-09T00:00:00+00:00",
            window_end="2024-02-10T00:00:00+00:00",
            diagnostics={"timezone": "Europe/Rome"},
            telegram_attempted=True,
            telegram_ok=True,
            telegram_message_id=123,
            telegram_chat_id_fingerprint="deadbeef",
            telegram_thread_id=99,
            telegram_error_code=None,
            telegram_description=None,
        ),
    )

    exit_code = main([
        "run",
        "--since-days",
        "1",
        "--output-dir",
        str(output_dir),
        "--config",
        str(config_path),
    ])

    assert exit_code == 0
    summary = json.loads((output_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["telegram_ok"] is True
    assert summary["telegram_message_id"] == 123
    assert summary["digest_mode"] == "TOP"
    assert "threshold_initial" in summary
    assert "threshold_final" in summary
    assert "min_results" in summary
    assert "selected_count" in summary

    assert summary["source_counts"] == {"remotive": 2, "wwr": 1}


def test_cli_sources_all_forwards_to_pipeline(tmp_path, monkeypatch):
    from job_scout import __main__ as main_mod
    from job_scout.pipeline import PipelineSummary

    output_dir = tmp_path / "out"
    config_path = Path("config/config.yaml")
    captured = {}

    def _fake_run_pipeline(**kwargs):
        captured["sources"] = kwargs.get("sources")
        return [], PipelineSummary(0, 0, 0, 0, {})

    monkeypatch.setattr(main_mod, "run_pipeline", _fake_run_pipeline)
    monkeypatch.setattr(
        main_mod,
        "maybe_notify",
        lambda *args, **kwargs: __import__("job_scout.notifications", fromlist=["NotificationResult"]).NotificationResult(
            notified_count=0,
            notification_mode="daily_window",
            notified=False,
            digest_date_local="2024-02-10",
            window_start="2024-02-09T00:00:00+00:00",
            window_end="2024-02-10T00:00:00+00:00",
            diagnostics={"timezone": "Europe/Rome"},
            telegram_attempted=False,
            telegram_ok=False,
            telegram_message_id=None,
            telegram_chat_id_fingerprint=None,
            telegram_thread_id=None,
            telegram_error_code=None,
            telegram_description=None,
        ),
    )

    exit_code = main([
        "run",
        "--since-days",
        "1",
        "--output-dir",
        str(output_dir),
        "--config",
        str(config_path),
        "--sources",
        "all",
    ])

    assert exit_code == 0
    assert captured["sources"] == ["all"]
