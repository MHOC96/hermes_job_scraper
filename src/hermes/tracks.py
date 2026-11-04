from __future__ import annotations

import html
import logging
import re
from typing import Sequence

from hermes.config import HermesConfig
from hermes.models import JobPosting

logger = logging.getLogger(__name__)

# Order used in Telegram sections (first matching category wins).
DEFAULT_TRACK_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Backend Engineer",
        (
            "backend",
            "back-end",
            "back end",
            "python developer",
            "java developer",
            "api",
            "fastapi",
            "django",
            "flask",
            "spring boot",
        ),
    ),
    (
        "Software Engineer",
        (
            "software engineer",
            "software developer",
            "full stack",
            "fullstack",
            "se engineer",
            "software engineering",
        ),
    ),
    (
        "AI Engineer",
        (
            "ai engineer",
            "artificial intelligence",
            "generative ai",
            "nlp",
            "computer vision",
            "data science",
        ),
    ),
    (
        "ML Engineer",
        (
            "ml engineer",
            "machine learning",
        ),
    ),
    (
        "Data Analysis",
        (
            "data analyst",
            "data analysis",
            "data engineer",
            "data engineering",
            "etl",
            "data pipeline",
            "power bi",
            "powerbi",
            "tableau",
            "rapidminer",
            "rapid miner",
            "analytics",
            "mis",
        ),
    ),
    (
        "Business Analysis",
        (
            "business analyst",
            "ba intern",
        ),
    ),
    (
        "ERP",
        (
            "erp",
            "sap",
            "oracle erp",
            "dynamics",
            "netsuite",
            "erp consultant",
            "erp developer",
            "erp implementation",
        ),
    ),
    (
        "Project Manager",
        (
            "project manager",
            "project management",
            "pm intern",
        ),
    ),
)

OTHER_CATEGORY = "Other"


def _job_blob(job: JobPosting) -> str:
    parts = [job.title, job.company, job.location, job.description]
    return " ".join(p for p in parts if p).lower()


_BOUNDARY_TERMS = frozenset({"erp", "sap", "mis", "api", "etl", "nlp"})


def _keyword_in_blob(term: str, blob: str) -> bool:
    t = term.lower()
    if " " in t:
        return t in blob
    if t in _BOUNDARY_TERMS or len(t) <= 3:
        return re.search(rf"\b{re.escape(t)}\b", blob) is not None
    return t in blob


def _matches_any(blob: str, keywords: Sequence[str]) -> bool:
    return any(_keyword_in_blob(term, blob) for term in keywords)


def classify_track(job: JobPosting, config: HermesConfig) -> str:
    blob = _job_blob(job)
    for name, keywords in DEFAULT_TRACK_CATEGORIES:
        if _matches_any(blob, keywords):
            return name
    # Fall back to configured track keywords grouped loosely by name overlap
    for term in config.track_keywords:
        if _keyword_in_blob(term, blob):
            return term.title()
    return OTHER_CATEGORY


def category_order() -> list[str]:
    return [name for name, _ in DEFAULT_TRACK_CATEGORIES] + [OTHER_CATEGORY]
