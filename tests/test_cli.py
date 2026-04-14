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
            PipelineSummary(
                3,
                3,
                1,
                1,
                {"remotive": 2, "wwr": 1},
                accepted_count=2,
                accepted_missing_salary_count=1,
                strict_matches_count=1,
                rejected_count=1,
                strict_match_min_score=81,
                strict_match_max_score=81,
            ),
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
    assert summary["trigger_type"]
    assert summary["now_utc"]
    assert summary["now_local"]
    assert summary["digest_mode"] == "TOP"
    assert "threshold_initial" in summary
    assert "threshold_final" in summary
    assert "min_results" in summary
    assert "selection_window_days" in summary
    assert "window_rows_count" in summary
    assert "selection_pool_count" in summary
    assert "selected_count" in summary
    assert "digest_top_matches_count" in summary
    assert "digest_data_only_count" in summary
    assert "digest_count" in summary
    assert "accepted_count" in summary
    assert "accepted_missing_salary_count" in summary
    assert "strict_matches_count" in summary
    assert "rejected_count" in summary
    assert "hard_rejected_count" in summary
    assert "soft_penalized_count" in summary
    assert "top_penalties" in summary
    assert "top_hard_rejects" in summary
    assert "avg_score" in summary
    assert "strict_match_min_score" in summary
    assert "strict_match_max_score" in summary
    assert "selected_min_score" in summary
    assert "selected_max_score" in summary
    assert "digest_min_score" in summary
    assert "digest_max_score" in summary

    assert summary["source_counts"] == {"remotive": 2, "wwr": 1}


def test_cli_run_summary_includes_profession_query(tmp_path, monkeypatch):
    import json
    from job_scout import __main__ as main_mod
    from job_scout.pipeline import PipelineSummary
    from job_scout.notifications import NotificationResult

    output_dir = tmp_path / "out"
    config_path = Path("config/config.yaml")

    monkeypatch.setattr(
        main_mod,
        "run_pipeline",
        lambda **_kwargs: ([], PipelineSummary(0, 0, 0, 0, {})),
    )
    monkeypatch.setattr(
        main_mod,
        "maybe_notify",
        lambda *args, **kwargs: NotificationResult(
            notified_count=0,
            notification_mode="daily_window",
            notified=False,
            digest_date_local="2024-02-10",
            window_start="2024-02-09T00:00:00+00:00",
            window_end="2024-02-10T00:00:00+00:00",
            diagnostics={"timezone": "Europe/Rome"},
        ),
    )

    exit_code = main([
        "run",
        "--since-days",
        "7",
        "--profession",
        "IT Solution Architect",
        "--output-dir",
        str(output_dir),
        "--config",
        str(config_path),
    ])

    assert exit_code == 0
    summary = json.loads((output_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["profession_query"] == "IT Solution Architect"


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


def test_cli_run_summary_includes_reason_when_zero(tmp_path, monkeypatch):
    import json
    from job_scout import __main__ as main_mod
    from job_scout.pipeline import PipelineSummary
    from job_scout.notifications import NotificationResult

    output_dir = tmp_path / "out"
    config_path = Path("config/config.yaml")

    monkeypatch.setattr(
        main_mod,
        "run_pipeline",
        lambda **_kwargs: (
            [],
            PipelineSummary(1, 1, 0, 0, {"dummy": 1}),
        ),
    )
    monkeypatch.setattr(
        main_mod,
        "maybe_notify",
        lambda *args, **kwargs: NotificationResult(
            notified_count=0,
            notification_mode="daily_window",
            skipped_reason="no_matches",
            notified=False,
            digest_date_local="2024-02-10",
            window_start="2024-02-09T00:00:00+00:00",
            window_end="2024-02-10T00:00:00+00:00",
            diagnostics={"timezone": "Europe/Rome"},
            digest_mode="TOP",
            threshold_initial=70,
            threshold_final=70,
            min_results=5,
            selected_count=0,
            reason_when_zero="no_candidates_after_hard_filters",
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
    assert summary["reason_when_zero"] == "no_candidates_after_hard_filters"


def test_cli_sources_list_details(capsys):
    exit_code = main(["sources", "--list", "--details"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "remotive: site=https://remotive.com/remote-jobs" in output
    assert "wwr: site=https://weworkremotely.com/remote-jobs" in output
    assert "arbeitnow: site=https://www.arbeitnow.com/jobs" in output
    assert "greenhouse: site=https://www.greenhouse.io/" in output
    assert "lever: site=https://www.lever.co/" in output


def test_cli_sources_test_includes_site(capsys, monkeypatch):
    from job_scout import __main__ as main_mod

    monkeypatch.setitem(
        main_mod.AVAILABLE_SOURCES,
        "dummy",
        lambda _since_days: [],
    )

    exit_code = main(["sources", "--test", "dummy", "--since-days", "1"])

    assert exit_code == 0
    output = capsys.readouterr().out.strip()
    assert output.startswith("dummy: 0 postings")
    assert "site=https://example.com" in output
