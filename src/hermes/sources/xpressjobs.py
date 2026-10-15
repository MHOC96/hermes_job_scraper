from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx
from curl_cffi import requests as curl_requests

from hermes.config import HermesConfig
from hermes.dates import parse_xpress_posted_at
from hermes.models import JobPosting

logger = logging.getLogger(__name__)

API_URL = "https://xpress.jobs/api/jobs/searchJobs"
VIEW_BASE = "https://xpress.jobs/jobs/view"
SITE_ORIGIN = "https://xpress.jobs"

_DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{SITE_ORIGIN}/",
    "Origin": SITE_ORIGIN,
}


class XpressjobsSource:
    name = "xpressjobs"

    def fetch(self, config: HermesConfig) -> list[JobPosting]:
        source_cfg = config.sources.xpressjobs
        if not source_cfg.enabled:
            return []

        keywords = self._search_terms(config, source_cfg.search_terms)
        jobs: list[JobPosting] = []
        seen_ids: set[str] = set()
        blocked_logged = False

        for keyword in keywords:
            for page in range(1, source_cfg.max_pages + 1):
                params = {
                    "keyword": keyword,
                    "page": page,
                    "pageSize": source_cfg.page_size,
                }
                logger.info(
                    "Fetching xpressjobs keyword=%r page=%s", keyword, page
                )
                rows, status = _fetch_search_rows(params)
                if status == 403:
                    if not blocked_logged:
                        logger.warning(
                            "XpressJobs API returned 403 for this server "
                            "(common on cloud/VPS IPs). Skipping xpressjobs for "
                            "this run — set sources.xpressjobs.enabled: false "
                            "on the VM to silence, or use ITPro/TopJobs/Rooster only."
                        )
                        blocked_logged = True
                    return jobs

                if rows is None:
                    logger.error(
                        "Failed to fetch xpressjobs keyword=%r page=%s",
                        keyword,
                        page,
                    )
                    break

                if not rows:
                    logger.info("No xpressjobs rows; stopping keyword pagination")
                    break

                for row in rows:
                    job = self._parse_row(row, source_cfg.listing_days)
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
                "IT intern",
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
            short = " ".join(term.split()[:4]).strip()
            if not short:
                continue
            key = short.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(short)
        return deduped

    def _parse_row(self, row: dict, listing_days: int) -> JobPosting | None:
        job_id = row.get("jobId")
        title = (row.get("jobTitle") or "").strip()
        company = (row.get("organizationName") or "").strip()
        if not job_id or not title:
            return None

        location = (row.get("locations") or "").strip()
        description = (row.get("overview") or "").strip()
        slug = _slugify(title, company)
        url = f"{VIEW_BASE}/{job_id}/{slug}"
        posted_at = parse_xpress_posted_at(row, listing_days=listing_days)

        return JobPosting(
            job_id=f"xpressjobs:{job_id}",
            source=self.name,
            title=title,
            company=company or "Unknown",
            location=location,
            url=url,
            posted_at=posted_at,
            description=description,
        )


def _fetch_search_rows(
    params: dict[str, Any],
) -> tuple[list[dict[str, Any]] | None, int | None]:
    """Return (rows, http_status). rows None on non-403 errors."""
    try:
        response = curl_requests.get(
            API_URL,
            params=params,
            headers=_DEFAULT_HEADERS,
            impersonate="chrome131",
            timeout=45,
        )
        if response.status_code == 403:
            return None, 403
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data, response.status_code
        return None, response.status_code
    except Exception:
        logger.debug("curl_cffi xpress fetch failed; trying httpx", exc_info=True)

    try:
        with httpx.Client(
            timeout=45.0,
            follow_redirects=True,
            headers={
                **_DEFAULT_HEADERS,
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            },
        ) as client:
            response = client.get(API_URL, params=params)
            if response.status_code == 403:
                return None, 403
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data, response.status_code
            return None, response.status_code
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            return None, 403
        return None, exc.response.status_code
    except Exception:
        return None, None


def _slugify(title: str, company: str) -> str:
    text = f"{title}-{company}".lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "job"
