from __future__ import annotations

import logging
import re
import time
from html import unescape

import httpx

from hermes.config import HermesConfig
from hermes.dates import parse_itpro_datetime
from hermes.models import JobPosting

logger = logging.getLogger(__name__)

API_BASE = "https://jobseeker.lk/wp-json/wp/v2/posts"
CATEGORIES_API = "https://jobseeker.lk/wp-json/wp/v2/categories"

_TAG_RE = re.compile(r"<[^>]+>")


class JobseekerSource:
    name = "jobseeker"

    def fetch(self, config: HermesConfig) -> list[JobPosting]:
        source_cfg = config.sources.jobseeker
        if not source_cfg.enabled:
            return []

        category_ids = self._resolve_category_ids(source_cfg.category_slugs)
        if not category_ids:
            logger.warning("jobseeker: no category IDs resolved; nothing to fetch")
            return []

        jobs: list[JobPosting] = []
        seen_ids: set[str] = set()

        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            for cat_id in category_ids:
                for page in range(1, source_cfg.max_pages + 1):
                    params = {
                        "categories": cat_id,
                        "per_page": source_cfg.per_page,
                        "page": page,
                        "_fields": "id,link,title,date,excerpt,content",
                    }
                    logger.info(
                        "Fetching jobseeker category=%s page=%s", cat_id, page
                    )
                    try:
                        response = client.get(API_BASE, params=params)
                        response.raise_for_status()
                        rows = response.json()
                    except Exception:
                        logger.exception("Failed to fetch jobseeker page")
                        break

                    if not isinstance(rows, list) or not rows:
                        logger.info("No jobseeker rows; stopping pagination")
                        break

                    for row in rows:
                        job = self._parse_row(row)
                        if job is None or job.job_id in seen_ids:
                            continue
                        seen_ids.add(job.job_id)
                        jobs.append(job)

                    total_pages = response.headers.get("X-WP-TotalPages")
                    if total_pages and page >= int(total_pages):
                        break
                    if len(rows) < source_cfg.per_page:
                        break

                    time.sleep(0.3)

        return jobs

    @staticmethod
    def _resolve_category_ids(slugs: list[str]) -> list[int]:
        if not slugs:
            slugs = ["internship"]
        ids: list[int] = []
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            for slug in slugs:
                try:
                    response = client.get(
                        CATEGORIES_API, params={"slug": slug.strip()}
                    )
                    response.raise_for_status()
                    data = response.json()
                except Exception:
                    logger.exception("Failed to resolve jobseeker category %r", slug)
                    continue
                if isinstance(data, list) and data:
                    ids.append(int(data[0]["id"]))
        return ids

    def _parse_row(self, row: dict) -> JobPosting | None:
        post_id = row.get("id")
        title_obj = row.get("title") or {}
        title = _plain(title_obj.get("rendered") or "")
        link = (row.get("link") or "").strip()
        if not post_id or not title or not link:
            return None

        excerpt = _plain((row.get("excerpt") or {}).get("rendered") or "")
        content = _plain((row.get("content") or {}).get("rendered") or "")
        description = " ".join(part for part in (excerpt, content) if part).strip()
        location = _guess_location(description)
        company = _guess_company(description) or "See posting"

        posted_at = parse_itpro_datetime(str(row.get("date") or ""))

        return JobPosting(
            job_id=f"jobseeker:{post_id}",
            source=self.name,
            title=title,
            company=company,
            location=location,
            url=link,
            posted_at=posted_at,
            description=description[:4000],
        )


def _plain(html_fragment: str) -> str:
    text = unescape(html_fragment)
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _guess_location(text: str) -> str:
    if not text:
        return ""
    lower = text.lower()
    if re.search(r"\bremote\b|\bwfh\b|work from home", lower):
        if re.search(r"\bcolombo\b", lower):
            return "Colombo (remote/hybrid)"
        return "Remote"
    match = re.search(
        r"\b(colombo|dehiwala|nugegoda|malabe|battaramulla|wattala|rajagiriya|"
        r"kotte|moratuwa|maharagama|mount lavinia)\b",
        lower,
    )
    if match:
        return match.group(1).title()
    if "🇱🇰" in text or "sri lanka" in lower:
        return "Sri Lanka"
    return ""


def _guess_company(text: str) -> str:
    match = re.search(
        r"(?:at|@|company:?)\s+([A-Z][A-Za-z0-9 &.\-]{2,60})",
        text,
    )
    if match:
        return match.group(1).strip()
    return ""
