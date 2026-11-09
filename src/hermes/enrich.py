from __future__ import annotations

import logging
import time
from dataclasses import replace

from scrapling.fetchers import Fetcher

from hermes.config import HermesConfig
from hermes.images import best_poster_from_html, og_image_from_html
from hermes.models import JobPosting

logger = logging.getLogger(__name__)

_DETAIL_SOURCES = frozenset({"topjobs"})


def enrich_images(jobs: list[JobPosting], config: HermesConfig) -> list[JobPosting]:
    if not config.telegram.send_job_images:
        return jobs
    if not config.telegram.fetch_detail_images:
        return jobs

    telegram = config.telegram
    enriched: list[JobPosting] = []

    for job in jobs:
        if job.image_url:
            enriched.append(job)
            continue
        if job.source not in _DETAIL_SOURCES:
            enriched.append(job)
            continue

        image_url = _fetch_detail_image(job, telegram)
        if image_url:
            enriched.append(replace(job, image_url=image_url))
            logger.debug("Enriched image for %s", job.job_id)
        else:
            enriched.append(job)
        time.sleep(0.4)

    return enriched


def _fetch_detail_image(job: JobPosting, telegram) -> str | None:
    try:
        response = Fetcher.get(job.url, stealthy_headers=True)
    except Exception:
        logger.debug("Detail fetch failed for %s", job.url, exc_info=True)
        return None

    if response.status != 200:
        return None

    html = _response_html(response)
    if not html:
        return None
    return og_image_from_html(html, job.url, telegram=telegram)


def _response_html(response) -> str:
    text = getattr(response, "text", None)
    if text:
        raw = text() if callable(text) else text
        if raw:
            return str(raw)
    body = getattr(response, "body", None)
    if body:
        encoding = getattr(response, "encoding", None) or "utf-8"
        return body.decode(encoding, errors="replace")
    return ""
