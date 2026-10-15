from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

from scrapling.fetchers import Fetcher

from hermes.config import HermesConfig
from hermes.dates import parse_itpro_datetime
from hermes.models import JobPosting

logger = logging.getLogger(__name__)

BASE_URL = "https://itpro.lk/jobs"


class ItproSource:
    name = "itpro"

    def fetch(self, config: HermesConfig) -> list[JobPosting]:
        source_cfg = config.sources.itpro
        if not source_cfg.enabled:
            return []

        jobs: list[JobPosting] = []
        seen_ids: set[str] = set()

        for page in range(1, source_cfg.max_pages + 1):
            url = BASE_URL if page == 1 else f"{BASE_URL}?p={page}"
            logger.info("Fetching itpro page %s: %s", page, url)
            try:
                response = Fetcher.get(url, stealthy_headers=True)
            except Exception:
                logger.exception("Failed to fetch itpro page %s", page)
                break

            if response.status != 200:
                logger.warning("itpro page %s returned status %s", page, response.status)
                break

            cards = response.css("article.job-card")
            if not cards:
                logger.info("No job cards on itpro page %s; stopping pagination", page)
                break

            for card in cards:
                job = self._parse_card(card)
                if job is None or job.job_id in seen_ids:
                    continue
                seen_ids.add(job.job_id)
                jobs.append(job)

        return jobs

    def _parse_card(self, card) -> JobPosting | None:
        href = card.css("a.jcl::attr(href), a::attr(href)").get()
        title = (card.css("h2.jc-title::text, .jc-title::text").get() or "").strip()
        if not href or not title:
            return None

        url = urljoin(BASE_URL, href)
        article_id = card.attrib.get("id") or ""
        job_id = self._job_id_from_article(article_id, url)

        company = (card.css(".jc-company::text").get() or "").strip()
        location = (card.css(".jc-company-info span.la::text").get() or "").strip()
        posted_raw = card.css("time.time-posted::attr(datetime)").get() or ""
        posted_at = parse_itpro_datetime(posted_raw)

        return JobPosting(
            job_id=job_id,
            source=self.name,
            title=title,
            company=company or "Unknown",
            location=location,
            url=url,
            posted_at=posted_at,
        )

    @staticmethod
    def _job_id_from_article(article_id: str, url: str) -> str:
        if article_id:
            return f"itpro:{article_id}"
        path = urlparse(url).path.rstrip("/")
        slug = path.split("/")[-1] if path else url
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", slug).strip("-") or "unknown"
        return f"itpro:{slug}"
