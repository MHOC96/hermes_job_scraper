from __future__ import annotations

import logging
import re
import time
from urllib.parse import quote, urlencode

from scrapling.fetchers import Fetcher

from hermes.config import HermesConfig
from hermes.dates import parse_topjobs_opening_date
from hermes.filters import build_include_terms
from hermes.models import JobPosting

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.topjobs.lk/applicant/vacancybyfunctionalarea.jsp"
SERVLET_PATH = "https://www.topjobs.lk/employer/JobAdvertismentServlet"


class TopjobsSource:
    name = "topjobs"

    def fetch(self, config: HermesConfig) -> list[JobPosting]:
        source_cfg = config.sources.topjobs
        if not source_cfg.enabled:
            return []

        keywords = self._search_terms(config, source_cfg.search_terms)
        jobs: list[JobPosting] = []
        seen_ids: set[str] = set()

        for keyword in keywords:
            for page in range(1, source_cfg.max_pages + 1):
                params = {
                    "jst": "OPEN",
                    "pageNo": str(page),
                    "txtKeyWord": keyword,
                }
                url = f"{SEARCH_URL}?{urlencode(params)}"
                logger.info("Fetching topjobs keyword=%r page=%s", keyword, page)
                try:
                    response = Fetcher.get(url, stealthy_headers=True)
                except Exception:
                    logger.exception("Failed to fetch topjobs page")
                    break

                if response.status != 200:
                    logger.warning("topjobs returned status %s", response.status)
                    break

                page_jobs = self._parse_table(response)
                if not page_jobs:
                    logger.info("No rows on topjobs page; stopping keyword pagination")
                    break

                for job in page_jobs:
                    if job.job_id in seen_ids:
                        continue
                    seen_ids.add(job.job_id)
                    jobs.append(job)

                time.sleep(1)

        return jobs

    @staticmethod
    def _search_terms(config: HermesConfig, configured: list[str]) -> list[str]:
        terms = configured or build_include_terms(config)
        if not terms:
            terms = ["software"]
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

    def _parse_table(self, response) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        seen_row_ids: set[str] = set()
        rows = [
            r
            for r in response.css("#table tr[onclick]")
            if re.fullmatch(r"tr\d+", (r.attrib.get("id") or ""), re.I)
        ]
        if not rows:
            html = response.body.decode(response.encoding or "utf-8", errors="replace")
            if not re.search(r'id=["\']tr\d+', html, re.I):
                return []
            rows = [
                r
                for r in response.css("#table tr")
                if r.attrib.get("onclick")
                and re.fullmatch(r"tr\d+", (r.attrib.get("id") or ""), re.I)
            ]

        for row in rows:
            row_key = row.attrib.get("id") or ""
            if row_key in seen_row_ids:
                continue
            seen_row_ids.add(row_key)
            job = self._parse_row(row)
            if job:
                jobs.append(job)
        return jobs

    def _parse_row(self, row) -> JobPosting | None:
        onclick = row.attrib.get("onclick") or ""
        row_id = row.attrib.get("id") or ""

        alert_args = self._parse_create_alert(onclick)
        if alert_args is None:
            job_num = self._extract_job_number(onclick, row_id)
            if not job_num:
                return None
            url = f"{SERVLET_PATH}?rid={job_num}&ac=&jc=&ec=&pg=applicant/vacancybyfunctionalarea.jsp"
            job_id = f"topjobs:{job_num}"
        else:
            idx, ac, jc, ec, _session = alert_args
            job_num = jc.lstrip("0") or jc
            url = (
                f"{SERVLET_PATH}?rid={quote(idx, safe='')}"
                f"&ac={quote(ac, safe='')}"
                f"&jc={quote(jc, safe='')}"
                f"&ec={quote(ec, safe='')}"
                f"&pg=applicant/vacancybyfunctionalarea.jsp"
            )
            job_id = f"topjobs:{job_num}"

        cells = row.css("td")
        if len(cells) < 3:
            return None

        title, company = self._title_company_from_cell(cells[2])
        location = (cells[-1].css("::text").get() or "").strip()
        opening_text = (
            cells[4].get_all_text(strip=True) if len(cells) > 4 else ""
        )
        posted_at = parse_topjobs_opening_date(opening_text)

        if not title:
            return None

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
    def _parse_create_alert(onclick: str) -> tuple[str, str, str, str, str] | None:
        m = re.search(r"createAlert\s*\((.*)\)", onclick, re.I | re.S)
        if not m:
            return None
        args = re.findall(r"'([^']*)'", m.group(1))
        if len(args) < 5:
            return None
        return args[0], args[1], args[2], args[3], args[4]

    @staticmethod
    def _title_company_from_cell(cell) -> tuple[str, str]:
        lines = [ln.strip() for ln in cell.get_all_text(strip=True).splitlines() if ln.strip()]
        # Drop numeric or opaque id lines at the start of the cell.
        while lines and re.fullmatch(r"[0-9A-Za-z]+", lines[0]) and len(lines[0]) >= 6:
            lines.pop(0)
        if not lines:
            return "", ""
        if len(lines) == 1:
            return lines[0], ""
        return lines[-2], lines[-1]

    @staticmethod
    def _extract_job_number(onclick: str, row_id: str) -> str | None:
        args = TopjobsSource._parse_create_alert(onclick)
        if args:
            return args[2].lstrip("0") or args[2]
        m = re.match(r"tr(\d+)", row_id, re.IGNORECASE)
        if m:
            return m.group(1)
        return None
