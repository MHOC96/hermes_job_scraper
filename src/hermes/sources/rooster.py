from __future__ import annotations

import logging
import time

import httpx

from hermes.config import HermesConfig
from hermes.dates import parse_rooster_datetime
from hermes.models import JobPosting

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.rooster.jobs/jobSearch/jobs/search"
VIEW_BASE = "https://rooster.jobs/jobs"


class RoosterSource:
    name = "rooster"

    def fetch(self, config: HermesConfig) -> list[JobPosting]:
        source_cfg = config.sources.rooster
        if not source_cfg.enabled:
            return []

        keywords = self._search_terms(config, source_cfg.search_terms)
        jobs: list[JobPosting] = []
        seen_ids: set[str] = set()

        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            for keyword in keywords:
                for page in range(1, source_cfg.max_pages + 1):
                    body = {
                        "query": [keyword],
                        "page": page,
                        "limit": source_cfg.page_size,
                        "filters": {"country": source_cfg.country},
                    }
                    logger.info(
                        "Fetching rooster keyword=%r page=%s", keyword, page
                    )
                    try:
                        response = client.post(SEARCH_URL, json=body)
                        response.raise_for_status()
                        envelope = response.json()
                    except Exception:
                        logger.exception("Failed to fetch rooster page")
                        break

                    payload = envelope.get("body") if isinstance(envelope, dict) else None
                    rows = payload.get("data") if isinstance(payload, dict) else None
                    if not isinstance(rows, list) or not rows:
                        logger.info("No rooster rows; stopping keyword pagination")
                        break

                    for row in rows:
                        job = self._parse_row(row)
                        if job is None or job.job_id in seen_ids:
                            continue
                        seen_ids.add(job.job_id)
                        jobs.append(job)

                    if len(rows) < source_cfg.page_size:
                        break

                    time.sleep(0.5)

        return jobs

    @staticmethod
    def _search_terms(config: HermesConfig, configured: list[str]) -> list[str]:
        if configured:
            terms = configured
        else:
            terms = [
                "intern",
                "internship",
                "trainee",
                "backend intern",
                "data engineer intern",
                "business analyst intern",
                "erp intern",
            ]
        deduped: list[str] = []
        seen: set[str] = set()
        for term in terms:
            short = " ".join(term.split()[:6]).strip()
            if not short:
                continue
            key = short.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(short)
        return deduped

    def _parse_row(self, row: dict) -> JobPosting | None:
        job_id = row.get("id")
        title = (row.get("title") or "").strip()
        if not job_id or not title:
            return None

        company = (row.get("company_name") or row.get("subsidiary_company_name") or "").strip()
        location = (row.get("location") or "").strip()
        if row.get("remote"):
            location = f"{location} (remote)".strip() if location else "Remote"

        url = f"{VIEW_BASE}/{job_id}"
        posted_at = parse_rooster_datetime(str(row.get("created_at") or ""))

        return JobPosting(
            job_id=f"rooster:{job_id}",
            source=self.name,
            title=title,
            company=company or "Unknown",
            location=location,
            url=url,
            posted_at=posted_at,
        )
