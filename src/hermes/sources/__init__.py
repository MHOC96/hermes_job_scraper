from __future__ import annotations

from hermes.sources.base import JobSource
from hermes.sources.itpro import ItproSource
from hermes.sources.rooster import RoosterSource
from hermes.sources.topjobs import TopjobsSource
from hermes.sources.xpressjobs import XpressjobsSource

# Canonical order: fetch, validate output, and Telegram interleaving.
SOURCE_ORDER: tuple[str, ...] = ("itpro", "topjobs", "rooster", "xpressjobs")

SOURCE_REGISTRY: dict[str, JobSource] = {
    "itpro": ItproSource(),
    "topjobs": TopjobsSource(),
    "rooster": RoosterSource(),
    "xpressjobs": XpressjobsSource(),
}

__all__ = [
    "SOURCE_ORDER",
    "SOURCE_REGISTRY",
    "JobSource",
    "ItproSource",
    "RoosterSource",
    "TopjobsSource",
    "XpressjobsSource",
]
