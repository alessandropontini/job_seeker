from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

from job_scout.config import DEFAULT_CONFIG
from job_scout.matcher import MatchResult
from job_scout.models import JobPosting
from job_scout import notifications
from job_scout.feedback import FeedbackRegistrationResult
from job_scout.writers import ReportRow


def _make_row(job_id: str, score: int, penalties: list[str]) -> ReportRow:
    posting = JobPosting(
        id=job_id,
        source="dummy",
        company="Nimbus",
        title=f"Data Governance Manager {job_id}",
        location_text="Milan, Italy",
        location_country="Italy",
        remote_type="full-remote",
        url=f"https://example.com/{job_id}",
        posted_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        salary_text="€70,000 - €90,000",
        currency="EUR",
        tags=["data"],
    )
    match = MatchResult(
        matches_all=True,
        decision="accepted",
        hard_reject_reasons=[],
        penalties=penalties,
        missing_fields=[],
        reject_reasons=[],
        missing_salary=False,
        salary_min_eur=70000,
        salary_max_eur=90000,
        remote_level="full-remote",
        score=score,
        score_penalties=penalties,
        score_bonuses=["full_remote"],
    )
    return ReportRow(posting=posting, match=match)


def test_dual_channel_digest_includes_sections():
    top_row = _make_row("alpha", 110, [])
    data_row = _make_row("beta", 90, ["prefer_full_remote"])
    digest = notifications._format_dual_channel_digest(
        [top_row],
        [data_row],
        total_in_window=2,
        window_hours=24,
        digest_scope="daily_window",
        data_only_reasons={
            notifications._snapshot_key(data_row): ["data keyword: data"]
        },
    )

    assert "Top matches" in digest
    assert "Data-only best picks" in digest
    assert "[TOP]" in digest
    assert "[DATA]" in digest
    assert "channel: data keyword: data" in digest


def test_dedupe_skips_duplicate_digest(tmp_path, monkeypatch):
    fixed_now = datetime(2024, 2, 5, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(notifications, "_now", lambda: fixed_now)

    row = _make_row("alpha", 110, [])
    row.posting.posted_at = fixed_now - timedelta(hours=1)
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    digest_date = fixed_now.date().isoformat()
    digest_hash = notifications.compute_digest_hash(digest_date, [row], [])
    state_path = output_dir / "last_notified.json"
    state_path.write_text(
        json.dumps(
            {
                "date": digest_date,
                "digest_hash": digest_hash,
                "notified_ids": ["dummy:alpha"],
            }
        ),
        encoding="utf-8",
    )

    called = {"count": 0}

    def _fake_send(*_args, **_kwargs):
        called["count"] += 1
        return True, None

    monkeypatch.setattr(
        notifications.telegram_notifier, "send_messages", _fake_send
    )

    result = notifications.maybe_notify([row], output_dir, DEFAULT_CONFIG)

    assert called["count"] == 0
    assert result.skipped_reason == "duplicate_digest"


def test_last_run_state_includes_digest_payload(tmp_path, monkeypatch):
    fixed_now = datetime(2024, 2, 6, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(notifications, "_now", lambda: fixed_now)

    row = _make_row("alpha", 110, [])
    row.posting.posted_at = fixed_now - timedelta(hours=2)
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    config = deepcopy(DEFAULT_CONFIG)
    config["notifications"]["telegram"]["dry_run"] = True
    config["notifications"]["telegram"]["send_per_job"] = True

    result = notifications.maybe_notify([row], output_dir, config)

    assert result.notification_mode == "daily_window"

    last_run = json.loads(
        (output_dir / "last_run.json").read_text(encoding="utf-8")
    )
    digest = last_run["digest"]
    assert digest["digest_hash"]
    assert digest["run_id"]
    assert digest["feedback_open_at"]
    assert digest["feedback_close_at"]
    assert digest["jobs"]
    assert digest["jobs"][0]["short_id"]
    assert digest["jobs"][0]["job_hash"]
    assert digest["top_matches"]
    assert digest["data_only_best_picks"] == []
    assert last_run["summary"]["digest_count"] == len(digest["jobs"])
    assert "dummy:alpha" in last_run["jobs"]

    last_notified = json.loads(
        (output_dir / "last_notified.json").read_text(encoding="utf-8")
    )
    assert last_notified["notified_ids"]

    payload = json.loads(
        (output_dir / "telegram_payload.json").read_text(encoding="utf-8")
    )
    assert payload["messages"]
    assert payload["messages"][0]["text"]


def test_fallback_digest_when_window_empty(tmp_path, monkeypatch):
    fixed_now = datetime(2024, 2, 7, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(notifications, "_now", lambda: fixed_now)

    row = _make_row("gamma", 105, [])
    row.posting.posted_at = fixed_now - timedelta(days=3)
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    config = deepcopy(DEFAULT_CONFIG)
    config["notifications"]["telegram"]["dry_run"] = True

    result = notifications.maybe_notify([row], output_dir, config)

    assert result.notification_mode == "daily_window"

    last_run = json.loads(
        (output_dir / "last_run.json").read_text(encoding="utf-8")
    )
    digest = last_run["digest"]
    assert digest["scope"] == "fallback_recent"
    assert digest["jobs"]
    assert last_run["summary"]["digest_count"] == len(digest["jobs"])


def test_fake_send_mode_registers_window_and_persists_payload(
    tmp_path, monkeypatch
):
    fixed_now = datetime(2024, 2, 8, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(notifications, "_now", lambda: fixed_now)

    row = _make_row("alpha", 110, [])
    row.posting.posted_at = fixed_now - timedelta(hours=1)
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    config = deepcopy(DEFAULT_CONFIG)
    config["notifications"]["telegram"]["send_mode"] = "fake"
    config["notifications"]["telegram"]["persist_payload"] = True
    config["feedback"]["enabled"] = True

    register_calls = {"count": 0}

    def _fake_register(**_kwargs):
        register_calls["count"] += 1
        return FeedbackRegistrationResult(
            ok=True,
            reason=None,
            endpoint="https://worker.example/window/open",
            method="POST",
            headers=(
                "Content-Type",
                "X-Webhook-Timestamp",
                "X-Webhook-Id",
                "X-Webhook-Signature",
            ),
            status=200,
            body_excerpt="OK",
        )

    monkeypatch.setattr(notifications, "register_feedback_window", _fake_register)

    result = notifications.maybe_notify([row], output_dir, config)

    assert result.notification_mode == "daily_window"
    assert register_calls["count"] == 1
    payload_path = output_dir / "telegram_payload.json"
    assert payload_path.exists()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    keyboard = payload["messages"][1]["reply_markup"]["inline_keyboard"]
    callback_data = keyboard[0][0]["callback_data"]
    assert callback_data.startswith("fb|")
