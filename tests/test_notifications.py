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
        why=["match core_title", "match platform", "penalty prefer_full_remote"],
    )
    return ReportRow(posting=posting, match=match)




def _make_rejected_row(job_id: str, reason: str) -> ReportRow:
    posting = JobPosting(
        id=job_id,
        source="dummy",
        company="Nimbus",
        title=f"Role {job_id}",
        location_text="London, UK",
        location_country="United Kingdom",
        remote_type="hybrid",
        url=f"https://example.com/{job_id}",
        posted_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        salary_text="€45,000 - €50,000",
        currency="EUR",
        tags=[],
    )
    match = MatchResult(
        matches_all=False,
        decision="rejected",
        hard_reject_reasons=[reason],
        penalties=[],
        missing_fields=[],
        reject_reasons=[reason],
        missing_salary=False,
        salary_min_eur=45000,
        salary_max_eur=50000,
        remote_level="hybrid",
        score=None,
        score_penalties=[],
        score_bonuses=[],
    )
    return ReportRow(posting=posting, match=match)

def test_dual_channel_digest_includes_sections():
    top_row = _make_row("alpha", 110, [])
    data_row = _make_row("beta", 90, ["prefer_full_remote"])
    digest = notifications._format_dual_channel_digest(
        [top_row],
        [data_row],
        digest_count=2,
        window_hours=24,
        digest_scope="daily_window",
        digest_mode="TOP",
        data_only_reasons={
            notifications._snapshot_key(data_row): ["data keyword: data"]
        },
    )

    assert "Top matches" in digest
    assert "Data-only best picks" in digest
    assert "[TOP]" in digest
    assert "[DATA]" in digest
    assert "channel: data keyword: data" in digest
    assert "Mode: TOP" in digest
    assert "Why:" in digest


def test_select_digest_items_adaptive_or_low_confidence():
    scored_jobs = [
        _make_row("alpha", 66, []),
        _make_row("beta", 63, []),
        _make_row("gamma", 61, []),
        _make_row("delta", 58, []),
        _make_row("epsilon", 55, []),
        _make_row("zeta", 52, []),
    ]

    selected, mode, anti_zero_triggered, final_threshold, selected_count = (
        notifications.select_digest_items(
            scored_jobs,
            fetched_count=8,
            min_results=5,
            high_threshold=70,
            low_threshold=40,
            step=5,
            force_send=True,
            run_mode="manual",
        )
    )

    assert len(selected) == 5
    assert mode in {"ADAPTIVE", "LOW_CONFIDENCE"}
    assert final_threshold <= 70
    assert anti_zero_triggered is (mode == "LOW_CONFIDENCE")
    assert selected_count == len(selected)


def test_select_digest_items_low_confidence_with_few_rows():
    scored_jobs = [
        _make_row("alpha", 35, []),
        _make_row("beta", 32, []),
    ]

    selected, mode, anti_zero_triggered, _final_threshold, _selected_count = (
        notifications.select_digest_items(
            scored_jobs,
            fetched_count=2,
            min_results=5,
            high_threshold=70,
            low_threshold=40,
            step=5,
            force_send=True,
            run_mode="manual",
        )
    )

    assert len(selected) == 2
    assert mode == "LOW_CONFIDENCE"
    assert anti_zero_triggered is True


def test_low_confidence_prefers_positive_scores_over_zeroes():
    scored_jobs = [
        _make_row("alpha", 18, []),
        _make_row("beta", 7, []),
        _make_row("gamma", 0, ["missing_salary"]),
    ]

    selected, mode, anti_zero_triggered, _final_threshold, _selected_count = (
        notifications.select_digest_items(
            scored_jobs,
            fetched_count=3,
            min_results=5,
            high_threshold=70,
            low_threshold=40,
            step=5,
            force_send=True,
            run_mode="manual",
        )
    )

    assert [row.posting.id for row in selected] == ["alpha", "beta"]
    assert mode == "LOW_CONFIDENCE"
    assert anti_zero_triggered is True




def test_select_digest_items_top_mode_when_threshold_met():
    scored_jobs = [
        _make_row("alpha", 95, []),
        _make_row("beta", 88, []),
        _make_row("gamma", 72, []),
    ]

    selected, mode, anti_zero_triggered, final_threshold, selected_count = (
        notifications.select_digest_items(
            scored_jobs,
            fetched_count=3,
            min_results=2,
            high_threshold=70,
            low_threshold=40,
            step=5,
            force_send=True,
            run_mode="manual",
        )
    )

    assert len(selected) == 3
    assert selected_count == 3
    assert mode == "TOP"
    assert anti_zero_triggered is False
    assert final_threshold == 70

def test_dedupe_skips_duplicate_digest(tmp_path, monkeypatch):
    fixed_now = datetime(2024, 2, 5, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(notifications, "_now", lambda: fixed_now)

    row = _make_row("alpha", 110, [])
    row.posting.posted_at = fixed_now - timedelta(hours=1)
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    digest_date = (fixed_now.astimezone(notifications.ZoneInfo("Europe/Rome")).date() - timedelta(days=1)).isoformat()
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


def test_manual_mode_respects_selection_window_days(tmp_path, monkeypatch):
    fixed_now = datetime(2024, 2, 7, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(notifications, "_now", lambda: fixed_now)

    row = _make_row("manual-30d", 105, [])
    row.posting.posted_at = fixed_now - timedelta(days=10)
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    config = deepcopy(DEFAULT_CONFIG)
    config["notifications"]["telegram"]["send_mode"] = "fake"

    result = notifications.maybe_notify(
        [row],
        output_dir,
        config,
        run_mode="manual",
        force_send=True,
        fetched_count=1,
        selection_window_days=30,
    )

    last_run = json.loads(
        (output_dir / "last_run.json").read_text(encoding="utf-8")
    )
    digest = last_run["digest"]
    payload = json.loads(
        (output_dir / "telegram_payload.json").read_text(encoding="utf-8")
    )

    assert result.window_rows_count == 1
    assert result.selection_window_days == 30
    assert digest["scope"] == "manual_since_days"
    assert digest["selection_window_days"] == 30
    assert "Job Scout — Manual Digest (last 30d)" in payload["messages"][0]["text"]


def test_manual_zero_result_message_uses_requested_window(tmp_path, monkeypatch):
    fixed_now = datetime(2024, 2, 7, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(notifications, "_now", lambda: fixed_now)

    output_dir = tmp_path / "out"
    output_dir.mkdir()

    config = deepcopy(DEFAULT_CONFIG)
    config["notifications"]["telegram"]["send_mode"] = "fake"

    notifications.maybe_notify(
        [],
        output_dir,
        config,
        run_mode="manual",
        force_send=True,
        fetched_count=12,
        selection_window_days=30,
    )

    payload = json.loads(
        (output_dir / "telegram_payload.json").read_text(encoding="utf-8")
    )

    assert "Negli ultimi 30 giorni" in payload["messages"][0]["text"]
    assert "finestra=30d" in payload["messages"][0]["text"]


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
            user_agent_sent=True,
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

    registration_log = (output_dir / "feedback_registration_result.log").read_text(encoding="utf-8")
    assert "user_agent_sent=true" in registration_log


def test_env_real_mode_requires_e2e_gate(monkeypatch):
    monkeypatch.setenv("JOB_SCOUT_TELEGRAM_MODE", "real")
    monkeypatch.delenv("JOB_SCOUT_E2E_REAL_TELEGRAM", raising=False)

    mode = notifications._resolve_telegram_send_mode({"send_mode": "fake"})

    assert mode == "fake"


def test_env_real_mode_enabled_with_e2e_gate(monkeypatch):
    monkeypatch.setenv("JOB_SCOUT_TELEGRAM_MODE", "real")
    monkeypatch.setenv("JOB_SCOUT_E2E_REAL_TELEGRAM", "1")

    mode = notifications._resolve_telegram_send_mode({"send_mode": "fake"})

    assert mode == "real"

def test_scheduled_mode_sends_no_match_diagnostic(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    config = deepcopy(DEFAULT_CONFIG)
    config["notifications"]["telegram"]["send_mode"] = "fake"

    result = notifications.maybe_notify(
        [],
        output_dir,
        config,
        run_mode="scheduled",
        force_send=False,
        fetched_count=0,
    )

    payload = json.loads((output_dir / "telegram_payload.json").read_text(encoding="utf-8"))
    assert result.notified is True
    assert result.skipped_reason == "no_matches"
    assert result.telegram_attempted is False
    assert result.digest_mode == "TOP"
    assert "🔎 Oggi non ho trovato offerte davvero in linea" in payload["messages"][0]["text"]
    assert "📚 Ho controllato le fonti configurate" in payload["messages"][0]["text"]
    assert "Contesto: digest=0" in payload["messages"][0]["text"]




def test_scheduled_no_matches_attempts_telegram_in_real_mode(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    config = deepcopy(DEFAULT_CONFIG)
    config["notifications"]["telegram"]["send_mode"] = "real"
    monkeypatch.setenv("JOB_SCOUT_E2E_REAL_TELEGRAM", "1")

    def _fake_send_detailed(_messages, run_chat_check=False):
        return notifications.telegram_notifier.TelegramSendResult(
            sent=True,
            reason=None,
            attempted=True,
            responses=[],
            chat_fingerprint="abc12345",
            thread_id=None,
            chat_check=None,
        )

    monkeypatch.setattr(
        notifications.telegram_notifier,
        "send_messages_detailed",
        _fake_send_detailed,
    )

    result = notifications.maybe_notify(
        [],
        output_dir,
        config,
        run_mode="scheduled",
        force_send=False,
        fetched_count=0,
    )

    assert result.skipped_reason == "no_matches"
    assert result.telegram_attempted is True
    assert result.telegram_ok is True
def test_manual_mode_forces_no_match_diagnostic_payload(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    config = deepcopy(DEFAULT_CONFIG)
    config["notifications"]["telegram"]["send_mode"] = "fake"

    result = notifications.maybe_notify(
        [], output_dir, config, run_mode="manual", force_send=True
    )

    payload = json.loads((output_dir / "telegram_payload.json").read_text(encoding="utf-8"))
    assert result.notified is True
    assert "🔎 Oggi non ho trovato offerte davvero in linea" in payload["messages"][0]["text"]
    assert "📚 Ho controllato le fonti configurate" in payload["messages"][0]["text"]
    assert "Contesto: digest=0" in payload["messages"][0]["text"]




def test_manual_mode_reports_no_candidates_after_hard_filters(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    config = deepcopy(DEFAULT_CONFIG)
    config["notifications"]["telegram"]["send_mode"] = "fake"

    rejected_row = _make_rejected_row("hard-blocked", "excluded_country")
    result = notifications.maybe_notify(
        [rejected_row],
        output_dir,
        config,
        run_mode="manual",
        force_send=True,
        fetched_count=1,
    )

    payload = json.loads((output_dir / "telegram_payload.json").read_text(encoding="utf-8"))
    assert result.selected_count == 0
    assert result.reason_when_zero == "no_candidates_after_hard_filters"
    assert "🧭 Oggi non ho trovato offerte che superano i filtri principali" in payload["messages"][0]["text"]
    assert "🧱 Le offerte viste ci sono state" in payload["messages"][0]["text"]
    assert "Contesto: digest=0" in payload["messages"][0]["text"]


def test_last_run_summary_uses_explicit_digest_counters(tmp_path, monkeypatch):
    fixed_now = datetime(2024, 2, 9, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(notifications, "_now", lambda: fixed_now)

    row = _make_row("alpha", 111, [])
    row.posting.posted_at = fixed_now - timedelta(hours=1)
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    config = deepcopy(DEFAULT_CONFIG)
    config["notifications"]["telegram"]["send_mode"] = "fake"

    result = notifications.maybe_notify(
        [row],
        output_dir,
        config,
        run_mode="manual",
        force_send=True,
        fetched_count=1,
    )

    last_run = json.loads(
        (output_dir / "last_run.json").read_text(encoding="utf-8")
    )
    summary = last_run["summary"]

    assert result.window_rows_count == 1
    assert result.selection_pool_count == 1
    assert result.selected_count == 1
    assert result.digest_top_matches_count == 1
    assert result.digest_data_only_count == 0
    assert result.digest_count == 1
    assert summary["window_rows_count"] == 1
    assert summary["selection_pool_count"] == 1
    assert summary["selected_count"] == 1
    assert summary["top_matches_count"] == 1
    assert summary["data_only_count"] == 0
    assert summary["digest_count"] == 1

def test_telegram_response_metadata_propagated(tmp_path, monkeypatch):
    fixed_now = datetime(2024, 2, 9, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(notifications, "_now", lambda: fixed_now)

    row = _make_row("delta", 111, [])
    row.posting.posted_at = fixed_now - timedelta(hours=1)
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    config = deepcopy(DEFAULT_CONFIG)
    config["notifications"]["telegram"]["send_mode"] = "real"
    monkeypatch.setenv("JOB_SCOUT_E2E_REAL_TELEGRAM", "1")

    def _fake_send_detailed(_messages, run_chat_check=False):
        return notifications.telegram_notifier.TelegramSendResult(
            sent=True,
            reason=None,
            attempted=True,
            responses=[
                {"method": "sendMessage", "status": 200, "response": {"ok": True, "result": {"message_id": 777}}}
            ],
            chat_fingerprint="abc12345",
            thread_id=42,
            chat_check={"ok": True, "is_forum": True},
        )

    monkeypatch.setattr(notifications.telegram_notifier, "send_messages_detailed", _fake_send_detailed)

    result = notifications.maybe_notify([row], output_dir, config, run_mode="manual", force_send=True)

    assert result.telegram_ok is True
    assert result.telegram_message_id == 777
    assert result.telegram_chat_id_fingerprint == "abc12345"
    assert result.telegram_thread_id == 42
    assert result.telegram_attempted is True
