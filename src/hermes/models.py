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
