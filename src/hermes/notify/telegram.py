from __future__ import annotations

import html
import logging
from collections import defaultdict

import httpx

from hermes.models import JobPosting

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_JOBS_PER_MESSAGE = 8


def _format_job(job: JobPosting) -> str:
    title = html.escape(job.title)
    company = html.escape(job.company)
    location = html.escape(job.location or "—")
    url = html.escape(job.url, quote=True)
    source = html.escape(job.source)
    date_line = ""
    if job.posted_at:
        date_line = f"\nPosted: {html.escape(job.posted_at.strftime('%Y-%m-%d'))}"
    return (
        f"<b>{title}</b>\n"
        f"{company} · {location}{date_line}\n"
        f'<a href="{url}">View on {source}</a>'
    )


def _interleave_by_source(jobs: list[JobPosting]) -> list[JobPosting]:
    buckets: dict[str, list[JobPosting]] = defaultdict(list)
    for job in jobs:
        buckets[job.source].append(job)
    order = sorted(buckets.keys())
    merged: list[JobPosting] = []
    while any(buckets[s] for s in order):
        for source in order:
            if buckets[source]:
                merged.append(buckets[source].pop(0))
    return merged


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


def send_job_batch(
    jobs: list[JobPosting],
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    if not jobs:
        return

    ordered = _interleave_by_source(jobs)
    total = len(ordered)

    for start in range(0, total, MAX_JOBS_PER_MESSAGE):
        chunk = ordered[start : start + MAX_JOBS_PER_MESSAGE]
        batch_no = start // MAX_JOBS_PER_MESSAGE + 1
        batch_total = (total + MAX_JOBS_PER_MESSAGE - 1) // MAX_JOBS_PER_MESSAGE
        header = (
            f"<b>Hermes — {len(chunk)} job(s)</b> "
            f"(batch {batch_no}/{batch_total}, {total} new total)"
        )
        text = "\n\n".join([header, ""] + [_format_job(j) for j in chunk])
        _send_message(text, bot_token=bot_token, chat_id=chat_id)
        logger.info(
            "Sent Telegram batch %s/%s with %s job(s)",
            batch_no,
            batch_total,
            len(chunk),
        )
