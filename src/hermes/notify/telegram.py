from __future__ import annotations

import html
import logging
import time
from collections import defaultdict
from datetime import datetime

import httpx

from hermes.config import HermesConfig
from hermes.models import JobPosting, SourceStatus
from hermes.sources import SOURCE_ORDER
from hermes.tracks import category_order, classify_track

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_PHOTO_API = "https://api.telegram.org/bot{token}/sendPhoto"
MAX_MESSAGE_CHARS = 3700
MAX_CAPTION_CHARS = 1020

SOURCE_LABELS = {
    "itpro": "ITPro.lk",
    "topjobs": "TopJobs.lk",
    "rooster": "Rooster.jobs",
    "xpressjobs": "XpressJobs",
    "jobseeker": "Jobseeker.lk",
}
_DIVIDER = "━━━━━━━━━━━━━━━"


def _label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def _format_job(index: int, job: JobPosting) -> str:
    title = html.escape(job.title)
    company = html.escape(job.company)
    url = html.escape(job.url, quote=True)
    source_label = html.escape(_label(job.source))

    lines = [f"<b>{index}. {title}</b>", f"🏢 {company}"]

    details: list[str] = []
    if job.location:
        details.append(f"📍 {html.escape(job.location)}")
    if job.posted_at:
        details.append(f"🗓 {job.posted_at.strftime('%d %b %Y')}")
    details.append(f"via {source_label}")
    if details:
        lines.append("  ·  ".join(details))

    lines.append(f'🔗 <a href="{url}">View &amp; apply</a>')
    return "\n".join(lines)


def _group_by_track(
    jobs: list[JobPosting], config: HermesConfig
) -> list[tuple[str, list[JobPosting]]]:
    buckets: dict[str, list[JobPosting]] = defaultdict(list)
    for job in jobs:
        buckets[classify_track(job, config)].append(job)

    def newest_first(job: JobPosting) -> tuple[int, float]:
        if job.posted_at is None:
            return (1, 0.0)
        return (0, -job.posted_at.timestamp())

    order = [c for c in category_order() if c in buckets]
    order.extend(sorted(set(buckets) - set(order)))
    return [(name, sorted(buckets[name], key=newest_first)) for name in order]


def _summary_block(
    total: int,
    groups: list[tuple[str, list[JobPosting]]],
    source_status: dict[str, SourceStatus] | None,
) -> str:
    now = datetime.now().strftime("%d %b %Y, %H:%M")
    noun = "internship" if total == 1 else "internships"

    lines = [
        f"🚀 <b>{total} new {noun}</b> (Colombo-area focus)",
        f"<i>{html.escape(now)}</i>",
        "",
        "📂 <b>By role</b>",
    ]

    for name, items in groups:
        lines.append(f"• {html.escape(name)} — {len(items)}")

    if source_status:
        lines.extend(["", "📡 <b>Sources</b>"])
        for name in SOURCE_ORDER:
            status = source_status.get(name)
            if status is None:
                continue
            label = html.escape(_label(name))
            if not status.ok:
                reason = html.escape(status.error or "unavailable")
                lines.append(f"⚠️ {label} — {reason}")
            elif status.fetched:
                lines.append(f"✅ {label} — scanned")
            else:
                lines.append(f"✅ {label} — no new")

    return "\n".join(lines)


def _section_head(label: str, count: int, *, continued: bool) -> str:
    suffix = ", continued" if continued else ""
    return f"{_DIVIDER}\n📌 <b>{html.escape(label)}</b> ({count}{suffix})"


def _build_messages(
    jobs: list[JobPosting],
    config: HermesConfig,
    source_status: dict[str, SourceStatus] | None,
) -> list[str]:
    groups = _group_by_track(jobs, config)
    messages: list[str] = []
    current = _summary_block(len(jobs), groups, source_status)

    for category, items in groups:
        section_open = False
        for idx, job in enumerate(items, start=1):
            entry = _format_job(idx, job)
            head = _section_head(category, len(items), continued=idx > 1)
            addition = f"\n\n{entry}" if section_open else f"\n\n{head}\n\n{entry}"
            if len(current) + len(addition) > MAX_MESSAGE_CHARS:
                messages.append(current)
                current = f"{head}\n\n{entry}"
            else:
                current += addition
            section_open = True

    messages.append(current)
    return messages


def _format_job_caption(job: JobPosting) -> str:
    title = html.escape(job.title)
    company = html.escape(job.company)
    url = html.escape(job.url, quote=True)
    source_label = html.escape(_label(job.source))

    lines = [f"<b>{title}</b>", f"🏢 {company}"]
    if job.location:
        lines.append(f"📍 {html.escape(job.location)}")
    if job.posted_at:
        lines.append(f"🗓 {job.posted_at.strftime('%d %b %Y')}")
    lines.append(f"via {source_label}")
    lines.append(f'🔗 <a href="{url}">View &amp; apply</a>')
    text = "\n".join(lines)
    if len(text) > MAX_CAPTION_CHARS:
        return text[: MAX_CAPTION_CHARS - 3] + "..."
    return text


def _send_photo(
    photo_url: str,
    caption: str,
    *,
    bot_token: str,
    chat_id: str,
    client: httpx.Client,
) -> None:
    url = TELEGRAM_PHOTO_API.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
    }
    response = client.post(url, json=payload)
    if response.status_code >= 400:
        downloaded = client.get(photo_url, follow_redirects=True)
        downloaded.raise_for_status()
        content_type = downloaded.headers.get("content-type", "image/jpeg")
        files = {"photo": ("job.jpg", downloaded.content, content_type)}
        data = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "HTML",
        }
        response = client.post(url, data=data, files=files)
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram sendPhoto error: {body}")


def _send_job_photos(
    jobs: list[JobPosting],
    *,
    bot_token: str,
    chat_id: str,
    config: HermesConfig,
) -> None:
    tg = config.telegram
    if not tg.send_job_images:
        return

    delay = tg.photo_delay_seconds
    with httpx.Client(timeout=45.0) as client:
        for target in parse_chat_ids(chat_id):
            for job in jobs:
                if not job.image_url:
                    continue
                caption = _format_job_caption(job)
                try:
                    _send_photo(
                        job.image_url,
                        caption,
                        bot_token=bot_token,
                        chat_id=target,
                        client=client,
                    )
                    logger.info("Sent job photo for %s to %s", job.job_id, target)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Photo failed for %s (%s): %s",
                        job.job_id,
                        job.image_url[:80],
                        type(exc).__name__,
                    )
                if delay > 0:
                    time.sleep(delay)


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
    config: HermesConfig,
    source_status: dict[str, SourceStatus] | None = None,
) -> None:
    if not jobs:
        return

    messages = _build_messages(jobs, config, source_status)

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
            continue
        try:
            _send_job_photos(
                jobs,
                bot_token=bot_token,
                chat_id=target,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send job photos to %s: %s", target, type(exc).__name__)
    if failures:
        raise RuntimeError(f"Telegram delivery failed for: {', '.join(failures)}")
