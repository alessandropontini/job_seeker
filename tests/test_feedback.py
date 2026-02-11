from datetime import datetime, timezone

from job_scout import feedback
from job_scout.feedback import (
    apply_feedback_items,
    build_callback_data,
    build_short_id,
    is_window_open,
    parse_callback_data,
    session_storage_key,
    register_feedback_window,
    _sign_payload,
)
from job_scout.preferences import PreferenceProfile


def _empty_profile() -> PreferenceProfile:
    return PreferenceProfile(
        token_weights={},
        tag_weights={},
        remote_level_weights={},
        seniority_weights={},
        duplicate_ids=set(),
        last_update_id=None,
        feedback_cache={},
        updated_at="",
    )


def test_callback_data_length_under_limit():
    run_id = "26020508a1b2"
    short_id = "dg01f3c9abcd"
    payload = build_callback_data(run_id, short_id, "L", "a1b2c3d4")
    assert len(payload.encode("utf-8")) <= 64


def test_short_id_is_stable_and_unique():
    used = set()
    first = build_short_id("dummy:alpha", used)
    second = build_short_id("dummy:beta", used)
    assert first != second
    assert first in used
    assert second in used


def test_sign_payload_is_deterministic():
    signature = _sign_payload("secret", "1700000000", b'{"run_id":"x"}')
    assert signature == _sign_payload("secret", "1700000000", b'{"run_id":"x"}')
    assert len(signature) == 64


def test_window_expiry_check():
    open_at = "2024-01-01T00:00:00+00:00"
    close_at = "2024-01-01T01:00:00+00:00"
    assert is_window_open(open_at, close_at, datetime(2024, 1, 1, 0, 30, tzinfo=timezone.utc))
    assert not is_window_open(open_at, close_at, datetime(2024, 1, 1, 2, 0, tzinfo=timezone.utc))


def test_apply_feedback_items_updates_profile():
    profile = _empty_profile()
    feedback_items = [
        {"job_short_id": "a1b2", "action": "L"},
        {"job_short_id": "a1b2", "action": "S"},
        {"job_short_id": "c3d4", "action": "M"},
        {"job_short_id": "c3d4", "action": "X"},
    ]
    job_lookup = {
        "a1b2": {
            "job_key": "dummy:alpha",
            "title": "Data Lead",
            "description_snippet": "Data governance",
            "tags": ["data"],
            "remote_level": "full-remote",
        },
        "c3d4": {
            "job_key": "dummy:beta",
            "title": "Engineering Manager",
            "description_snippet": "Platform",
            "tags": ["platform"],
            "remote_level": "hybrid",
        },
    }
    config = {
        "personalization": {
            "enabled": True,
            "token_weight_step": 2,
            "tag_weight_step": 1,
            "remote_level_step": 2,
            "seniority_step": 1,
            "max_abs_weight": 10,
            "min_token_length": 3,
            "seniority_keywords": ["manager", "lead", "head"],
        }
    }

    result = apply_feedback_items(profile, feedback_items, job_lookup, config)

    assert result.counts["like"] == 1
    assert result.counts["love"] == 1
    assert result.counts["maybe"] == 1
    assert "dummy:beta" in result.updated_profile.duplicate_ids


def test_register_feedback_window_sends_browser_like_headers(monkeypatch):
    captured = {}

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"OK"

    def _fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(feedback.urllib.request, "urlopen", _fake_urlopen)

    result = register_feedback_window(
        run_id="26020508a1b2",
        open_at="2024-01-01T00:00:00+00:00",
        close_at="2024-01-01T01:00:00+00:00",
        jobs=[],
        config={
            "feedback": {
                "enabled": True,
                "webhook_base_url": "https://worker.example",
                "webhook_secret": "secret",
            }
        },
    )

    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert captured["timeout"] == 15
    assert headers["user-agent"].startswith("Mozilla/5.0")
    assert headers["accept"] == "application/json"
    assert headers["accept-language"] == "en-US,en;q=0.9"
    assert result.user_agent_sent is True


def test_register_feedback_window_non_200_keeps_body_excerpt_limit(monkeypatch):
    class _HttpErr(feedback.urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                "https://worker.example/window/open",
                403,
                "Forbidden",
                hdrs=None,
                fp=None,
            )

        def read(self):
            return ("x" * 300).encode("utf-8")

    def _fake_urlopen(_request, timeout=0):
        raise _HttpErr()

    monkeypatch.setattr(feedback.urllib.request, "urlopen", _fake_urlopen)

    result = register_feedback_window(
        run_id="26020508a1b2",
        open_at="2024-01-01T00:00:00+00:00",
        close_at="2024-01-01T01:00:00+00:00",
        jobs=[],
        config={
            "feedback": {
                "enabled": True,
                "webhook_base_url": "https://worker.example",
                "webhook_secret": "secret",
            }
        },
    )

    assert result.ok is False
    assert result.status == 403
    assert len(result.body_excerpt) == 200
    assert result.user_agent_sent is True


def test_callback_roundtrip_uses_worker_session_key_contract():
    run_id = "26020508a1b2"
    short_id = "dg01f3c9abcd"
    action = "L"
    job_hash = "a1b2c3d4"

    payload = build_callback_data(run_id, short_id, action, job_hash)
    parsed = parse_callback_data(payload)

    assert parsed == (run_id, short_id, action, "")
    assert session_storage_key(parsed[0]) == f"session:{run_id}"



def test_parse_callback_data_legacy_contract_supported():
    parsed = parse_callback_data("fb|run123|L")
    assert parsed == ("run123", "legacy", "L", "")
