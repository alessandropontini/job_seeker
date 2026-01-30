import io
import urllib.error

import pytest

from job_scout.sources import remotive


def test_remotive_http_error(monkeypatch):
    monkeypatch.delenv("JOB_SCOUT_FIXTURE_DIR", raising=False)
    def _raise_http(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="https://remotive.com",
            code=500,
            msg="Internal",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(remotive.urllib.request, "urlopen", _raise_http)
    with pytest.raises(remotive.RemotiveSourceError):
        remotive.fetch_remotive(7)


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_remotive_invalid_json(monkeypatch):
    monkeypatch.delenv("JOB_SCOUT_FIXTURE_DIR", raising=False)
    def _fake_response(*args, **kwargs):
        return _FakeResponse(b"{not-json")

    monkeypatch.setattr(remotive.urllib.request, "urlopen", _fake_response)
    with pytest.raises(remotive.RemotiveSourceError):
        remotive.fetch_remotive(7)


def test_remotive_no_network_guard(monkeypatch):
    monkeypatch.delenv("JOB_SCOUT_FIXTURE_DIR", raising=False)
    monkeypatch.setenv("NO_NETWORK", "1")
    with pytest.raises(remotive.RemotiveSourceError):
        remotive.fetch_remotive(1)
