from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
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


def parse_xpress_posted_at(row: dict[str, Any], *, listing_days: int = 30) -> datetime | None:
    """Infer posting time when search API omits createdDate."""
    created = row.get("createdDate")
    if created:
        parsed = parse_itpro_datetime(str(created))
        if parsed:
            return parsed

    expiry_raw = row.get("expiryDateOnWebsite")
    expiry = parse_itpro_datetime(str(expiry_raw)) if expiry_raw else None

    countdown_raw = row.get("expireDayCountDown")
    days_left: int | None = None
    if countdown_raw is not None:
        try:
            days_left = int(countdown_raw)
        except (TypeError, ValueError):
            days_left = None

    if days_left is not None and listing_days > 0:
        days_since_post = max(0, listing_days - days_left)
        return datetime.now(LK_TZ) - timedelta(days=days_since_post)

    if expiry is not None and listing_days > 0:
        return expiry - timedelta(days=listing_days)

    return None


def parse_rooster_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=LK_TZ)
        except ValueError:
            continue
    return parse_itpro_datetime(value)


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
