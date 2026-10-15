from __future__ import annotations

from typing import Protocol

from hermes.config import HermesConfig
from hermes.models import JobPosting


class JobSource(Protocol):
    name: str

    def fetch(self, config: HermesConfig) -> list[JobPosting]: ...
