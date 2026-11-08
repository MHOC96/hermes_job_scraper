from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class JobPosting:
    job_id: str
    source: str
    title: str
    company: str
    location: str
    url: str
    posted_at: datetime | None = None
    description: str = ""
    image_url: str = ""


class SourceUnavailableError(RuntimeError):
    """Raised by a source that cannot be reached (e.g. blocked by the site)."""


@dataclass(slots=True)
class SourceStatus:
    """Outcome of one source during a pipeline run."""

    name: str
    ok: bool = True
    fetched: int = 0
    error: str | None = None
