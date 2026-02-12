from datetime import datetime, timezone

from job_scout.scheduling import check_rome_8am_window


def test_time_gate_accepts_rome_0805_cet():
    result = check_rome_8am_window(datetime(2024, 1, 15, 7, 5, tzinfo=timezone.utc))

    assert result.allowed is True
    assert result.local_hour == 8
    assert result.local_minute == 5


def test_time_gate_rejects_rome_0815_cet():
    result = check_rome_8am_window(datetime(2024, 1, 15, 7, 15, tzinfo=timezone.utc))

    assert result.allowed is False
    assert result.local_hour == 8
    assert result.local_minute == 15


def test_time_gate_accepts_rome_0805_cest():
    result = check_rome_8am_window(datetime(2024, 7, 15, 6, 5, tzinfo=timezone.utc))

    assert result.allowed is True
    assert result.local_hour == 8
    assert result.local_minute == 5
