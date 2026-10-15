from __future__ import annotations

import logging
import re
from typing import Callable

from hermes.config import HermesConfig
from hermes.dates import within_max_age
from hermes.models import JobPosting

logger = logging.getLogger(__name__)

_FIELD_GETTERS: dict[str, Callable[[JobPosting], str]] = {
    "title": lambda job: job.title,
    "company": lambda job: job.company,
    "location": lambda job: job.location,
    "url": lambda job: job.url,
    "source": lambda job: job.source,
}


def _normalize_terms(terms: list[str]) -> list[str]:
    return [t.strip().lower() for t in terms if t and t.strip()]


def _field_text(job: JobPosting, field: str) -> str:
    getter = _FIELD_GETTERS.get(field)
    if getter is None:
        return ""
    return (getter(job) or "").lower()


def _term_matches(term: str, job: JobPosting, fields: list[str]) -> bool:
    pattern = re.escape(term.lower())
    for field in fields:
        if re.search(pattern, _field_text(job, field), re.IGNORECASE):
            return True
    return False


def _substring_match(term: str, text: str) -> bool:
    return term.lower() in text.lower()


def _role_title_matches(job: JobPosting, role_terms: list[str]) -> bool:
    title = (job.title or "").lower()
    for term in role_terms:
        if " " in term:
            if _substring_match(term, title):
                return True
            continue
        if term == "intern":
            if re.search(r"\bintern\b", title) and not re.search(
                r"\binternal\b", title
            ):
                return True
            continue
        if re.search(rf"\b{re.escape(term)}\b", title, re.IGNORECASE):
            return True
    return False


def build_include_terms(config: HermesConfig) -> list[str]:
    combined: list[str] = []
    seen: set[str] = set()
    for term in config.job_titles + config.include_keywords:
        key = term.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        combined.append(term.strip())
    return combined


def _track_terms(config: HermesConfig) -> list[str]:
    if config.track_keywords:
        return _normalize_terms(config.track_keywords)
    return [t.lower() for t in build_include_terms(config)]


def _location_ok(job: JobPosting, config: HermesConfig) -> bool:
    locations = _normalize_terms(config.location_include)
    if not locations:
        return True

    loc = (job.location or "").strip()
    blob = f"{loc} {job.title} {job.company}".lower()

    if config.location_allow_remote and re.search(
        r"\bremote\b|\bwork from home\b|\bwfh\b", blob, re.I
    ):
        return True

    if not loc and config.location_allow_empty:
        return True

    return any(_substring_match(term, blob) for term in locations)


def filter_jobs(jobs: list[JobPosting], config: HermesConfig) -> list[JobPosting]:
    excludes = _normalize_terms(config.exclude_keywords)
    fields = [f for f in config.match_fields if f in _FIELD_GETTERS]
    if not fields:
        fields = ["title", "company", "location"]

    role_terms = _normalize_terms(config.role_keywords)
    track_terms = _track_terms(config)
    use_layered = bool(config.track_keywords or config.role_keywords)

    if not track_terms and not use_layered:
        logger.warning(
            "No track terms (track_keywords or job_titles + include_keywords empty); "
            "include filter is permissive."
        )

    matched: list[JobPosting] = []
    for job in jobs:
        if excludes and any(_term_matches(ex, job, fields) for ex in excludes):
            continue

        if role_terms and not _role_title_matches(job, role_terms):
            continue

        if track_terms:
            if not any(_term_matches(term, job, fields) for term in track_terms):
                continue
        elif not use_layered:
            includes = build_include_terms(config)
            if includes:
                hits = [_term_matches(term, job, fields) for term in includes]
                if config.match_mode == "all":
                    if not all(hits):
                        continue
                elif not any(hits):
                    continue

        if not _location_ok(job, config):
            continue

        if not within_max_age(
            job.posted_at,
            max_days=config.max_posting_age_days,
            include_undated=config.include_undated,
        ):
            continue

        matched.append(job)
    return matched
