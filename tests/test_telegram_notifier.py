import os

from job_scout.notifier import telegram


class _FakeResponse:
    def __init__(self, status: int = 200, payload: bytes | None = None) -> None:
        self.status = status
        self._payload = payload or b'{"ok": true, "description": "ok"}'

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_send_message_skips_without_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    sent, reason = telegram.send_message("test")
    assert sent is False
    assert reason == "missing Telegram configuration"


def test_send_message_uses_urlopen(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    called = {"count": 0}

    def _fake_urlopen(request, timeout=0):
        assert request is not None
        assert timeout == 15
        called["count"] += 1
        return _FakeResponse(status=200)

    monkeypatch.setattr(telegram.urllib.request, "urlopen", _fake_urlopen)

    sent, reason = telegram.send_message("test")
    assert sent is True
    assert reason is None
    assert called["count"] == 2
