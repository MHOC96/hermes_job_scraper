from __future__ import annotations

import html
import logging
from collections import defaultdict
from datetime import datetime

import httpx

from hermes.models import JobPosting, SourceStatus
from hermes.sources import SOURCE_ORDER

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
# Telegram hard limit is 4096 characters; keep headroom for HTML entities.
MAX_MESSAGE_CHARS = 3700

SOURCE_LABELS = {
    "itpro": "ITPro.lk",
    "topjobs": "TopJobs.lk",
    "rooster": "Rooster.jobs",
    "xpressjobs": "XpressJobs",
}
_DIVIDER = "━━━━━━━━━━━━━━━"


def _label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def _format_job(index: int, job: JobPosting) -> str:
    title = html.escape(job.title)
    company = html.escape(job.company)
    url = html.escape(job.url, quote=True)

    lines = [f"<b>{index}. {title}</b>", f"🏢 {company}"]

    details: list[str] = []
    if job.location:
        details.append(f"📍 {html.escape(job.location)}")
    if job.posted_at:
        details.append(f"🗓 {job.posted_at.strftime('%d %b %Y')}")
    if details:
        lines.append("  ·  ".join(details))

    lines.append(f'🔗 <a href="{url}">View &amp; apply</a>')
    return "\n".join(lines)


def _group_by_source(jobs: list[JobPosting]) -> list[tuple[str, list[JobPosting]]]:
    buckets: dict[str, list[JobPosting]] = defaultdict(list)
    for job in jobs:
        buckets[job.source].append(job)
    order = [s for s in SOURCE_ORDER if s in buckets]
    order.extend(sorted(set(buckets) - set(order)))

    def newest_first(job: JobPosting) -> tuple[int, float]:
        if job.posted_at is None:
            return (1, 0.0)
        return (0, -job.posted_at.timestamp())

    return [(s, sorted(buckets[s], key=newest_first)) for s in order]


def _summary_block(
    total: int,
    groups: list[tuple[str, list[JobPosting]]],
    source_status: dict[str, SourceStatus] | None,
) -> str:
    counts = {source: len(items) for source, items in groups}
    now = datetime.now().strftime("%d %b %Y, %H:%M")
    noun = "internship" if total == 1 else "internships"

    lines = [
        f"🚀 <b>{total} new {noun}</b>",
        f"<i>{html.escape(now)}</i>",
        "",
        "📊 <b>Sources</b>",
    ]

    names = [s for s in SOURCE_ORDER if s in counts or (source_status and s in source_status)]
    names.extend(sorted(set(counts) - set(names)))
    for name in names:
        status = source_status.get(name) if source_status else None
        label = html.escape(_label(name))
        if status is not None and not status.ok:
            reason = html.escape(status.error or "unavailable")
            lines.append(f"⚠️ {label} — unavailable: {reason}")
        else:
            n = counts.get(name, 0)
            lines.append(f"✅ {label} — {n} new" if n else f"✅ {label} — no new")
    return "\n".join(lines)


def _section_head(label: str, count: int, *, continued: bool) -> str:
    suffix = ", continued" if continued else ""
    return f"{_DIVIDER}\n📌 <b>{label}</b> ({count}{suffix})"


def _build_messages(
    jobs: list[JobPosting],
    source_status: dict[str, SourceStatus] | None,
) -> list[str]:
    """Pack the summary and per-source job lists into Telegram-sized messages."""
    groups = _group_by_source(jobs)
    messages: list[str] = []
    current = _summary_block(len(jobs), groups, source_status)

    for source, items in groups:
        label = html.escape(_label(source))
        section_open = False
        for idx, job in enumerate(items, start=1):
            entry = _format_job(idx, job)
            head = _section_head(label, len(items), continued=idx > 1)
            addition = f"\n\n{entry}" if section_open else f"\n\n{head}\n\n{entry}"
            if len(current) + len(addition) > MAX_MESSAGE_CHARS:
                messages.append(current)
                current = f"{head}\n\n{entry}"
            else:
                current += addition
            section_open = True

    messages.append(current)
    return messages

def _send_message(text: str, *, bot_token: str, chat_id: str) -> None:
    url = TELEGRAM_API.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API error: {body}")


def parse_chat_ids(raw: str | None) -> list[str]:
    """Split a comma/whitespace separated list of chat ids or @channel usernames."""
    if not raw:
        return []
    parts = raw.replace(";", ",").replace("\n", ",").split(",")
    seen: list[str] = []
    for part in parts:
        value = part.strip()
        if value and value not in seen:
            seen.append(value)
    return seen


def send_job_batch(
    jobs: list[JobPosting],
    *,
    bot_token: str,
    chat_id: str,
    source_status: dict[str, SourceStatus] | None = None,
) -> None:
    """Send jobs to every chat in ``chat_id`` (comma-separated ids / @channels).

    Jobs are grouped per source and each source's availability is summarised at
    the top. A failure for one destination does not stop delivery to the others.
    """
    if not jobs:
        return

    messages = _build_messages(jobs, source_status)

    failures: list[str] = []
    for target in parse_chat_ids(chat_id):
        try:
            for number, text in enumerate(messages, start=1):
                _send_message(text, bot_token=bot_token, chat_id=target)
                logger.info(
                    "Sent Telegram message %s/%s to %s", number, len(messages), target
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send jobs to %s: %s", target, type(exc).__name__)
            failures.append(target)
    if failures:
        raise RuntimeError(f"Telegram delivery failed for: {', '.join(failures)}")
