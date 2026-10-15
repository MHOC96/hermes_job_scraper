from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LK_TZ = ZoneInfo("Asia/Colombo")


def parse_topjobs_opening_date(text: str) -> datetime | None:
    text = (text or "").strip()
    if not text:
        return None
    for fmt in ("%a %b %d %Y", "%a %b %d %Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=LK_TZ)
        except ValueError:
            continue
    return None


def parse_itpro_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=LK_TZ)
        return dt
    except ValueError:
        return None


def within_max_age(
    posted_at: datetime | None,
    *,
    max_days: int,
    include_undated: bool,
    now: datetime | None = None,
) -> bool:
    if max_days <= 0:
        return True
    if posted_at is None:
        return include_undated
    ref = now or datetime.now(timezone.utc)
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    cutoff = ref - timedelta(days=max_days)
    return posted_at >= cutoff
