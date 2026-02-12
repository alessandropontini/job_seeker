"""Scheduling helpers for workflow and runtime diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class RomeTimeGateResult:
    """Result of checking whether a UTC timestamp is inside Rome 08:00 window."""

    allowed: bool
    now_utc: str
    now_local: str
    timezone: str
    local_hour: int
    local_minute: int


def check_rome_8am_window(
    now_utc: datetime,
    *,
    timezone_name: str = "Europe/Rome",
    target_hour: int = 8,
    minute_window: int = 10,
) -> RomeTimeGateResult:
    """Return whether *now_utc* falls in the configured local-time gate.

    The gate is inclusive and spans ``target_hour:00`` through
    ``target_hour:minute_window`` in ``timezone_name``.
    """

    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    local_tz = ZoneInfo(timezone_name)
    now_local = now_utc.astimezone(local_tz)
    allowed = (
        now_local.hour == target_hour
        and 0 <= now_local.minute <= minute_window
    )
    return RomeTimeGateResult(
        allowed=allowed,
        now_utc=now_utc.isoformat(),
        now_local=now_local.isoformat(),
        timezone=timezone_name,
        local_hour=now_local.hour,
        local_minute=now_local.minute,
    )
