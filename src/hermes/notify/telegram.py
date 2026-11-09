from __future__ import annotations

import html
import logging
import time
from collections import defaultdict
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


def _label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def _truncate_plain(text: str, max_len: int) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _format_job_body(
    job: JobPosting,
    config: HermesConfig,
    *,
    index: int | None = None,
    include_track: bool = True,
) -> str:
    title = html.escape(_truncate_plain(job.title, 200))
    company = html.escape(_truncate_plain(job.company, 120))
    url = html.escape(job.url, quote=True)

    lines: list[str] = []
    if include_track:
        track = html.escape(classify_track(job, config))
        lines.append(f"📌 {track}")

    head = f"<b>{index}. {title}</b>" if index is not None else f"<b>{title}</b>"
    lines.append(head)
    lines.append(f"🏢 {company}")

    meta: list[str] = []
    if job.location:
        meta.append(f"📍 {html.escape(job.location)}")
    if job.posted_at:
        meta.append(f"🗓 {job.posted_at.strftime('%d %b %Y')}")
    if meta:
        lines.append(" · ".join(meta))

    lines.append(f'🔗 <a href="{url}">Apply</a>')
    return "\n".join(lines)


def _format_job(index: int, job: JobPosting, config: HermesConfig) -> str:
    return _format_job_body(job, config, index=index, include_track=False)


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
    noun = "internship" if total == 1 else "internships"

    lines = [f"🚀 <b>{total} new {noun}</b>"]

    for name, items in groups:
        lines.append(f"• {html.escape(name)} — {len(items)}")

    if source_status:
        warnings: list[str] = []
        for name in SOURCE_ORDER:
            status = source_status.get(name)
            if status is None or status.ok:
                continue
            label = html.escape(_label(name))
            reason = html.escape(status.error or "unavailable")
            warnings.append(f"⚠️ {label}: {reason}")
        if warnings:
            lines.append("")
            lines.extend(warnings)

    return "\n".join(lines)


def _section_head(label: str, count: int, *, continued: bool) -> str:
    if continued:
        return ""
    return f"\n<b>{html.escape(label)}</b>"


def _build_messages(
    text_jobs: list[JobPosting],
    config: HermesConfig,
    source_status: dict[str, SourceStatus] | None,
    *,
    total_count: int,
    photo_count: int,
    all_groups: list[tuple[str, list[JobPosting]]] | None = None,
) -> list[str]:
    groups = _group_by_track(text_jobs, config) if text_jobs else []
    summary_groups = all_groups or groups
    messages: list[str] = []
    current = _summary_block(total_count, summary_groups, source_status)

    if not text_jobs:
        messages.append(current)
        return messages

    for category, items in groups:
        section_open = False
        for idx, job in enumerate(items, start=1):
            entry = _format_job(idx, job, config)
            head = _section_head(category, len(items), continued=idx > 1)
            if section_open:
                addition = f"\n\n{entry}"
            elif head:
                addition = f"\n\n{head}\n\n{entry}"
            else:
                addition = f"\n\n{entry}"
            if len(current) + len(addition) > MAX_MESSAGE_CHARS:
                messages.append(current)
                current = f"{head}\n\n{entry}" if head else f"\n\n{entry}".strip()
            else:
                current += addition
            section_open = True

    messages.append(current)
    return messages


def _format_job_caption(job: JobPosting, config: HermesConfig) -> str:
    text = _format_job_body(job, config, index=None, include_track=True)
    if len(text) <= MAX_CAPTION_CHARS:
        return text
    return _format_job_body(
        job,
        config,
        index=None,
        include_track=True,
    )[: MAX_CAPTION_CHARS - 3] + "..."


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
                caption = _format_job_caption(job, config)
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

    tg = config.telegram
    photo_jobs = [
        j for j in jobs if tg.send_job_images and (j.image_url or "").strip()
    ]
    photo_ids = {j.job_id for j in photo_jobs}
    text_jobs = [j for j in jobs if j.job_id not in photo_ids]
    all_groups = _group_by_track(jobs, config)

    messages = _build_messages(
        text_jobs,
        config,
        source_status,
        total_count=len(jobs),
        photo_count=len(photo_jobs),
        all_groups=all_groups,
    )

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
                photo_jobs,
                bot_token=bot_token,
                chat_id=target,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send job photos to %s: %s", target, type(exc).__name__)
    if failures:
        raise RuntimeError(f"Telegram delivery failed for: {', '.join(failures)}")
