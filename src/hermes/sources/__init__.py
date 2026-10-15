from __future__ import annotations

from hermes.sources.base import JobSource
from hermes.sources.itpro import ItproSource
from hermes.sources.topjobs import TopjobsSource

SOURCE_REGISTRY: dict[str, JobSource] = {
    "itpro": ItproSource(),
    "topjobs": TopjobsSource(),
}

__all__ = ["SOURCE_REGISTRY", "JobSource", "ItproSource", "TopjobsSource"]
