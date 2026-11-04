from __future__ import annotations

from hermes.sources.base import JobSource
from hermes.sources.itpro import ItproSource
from hermes.sources.jobseeker import JobseekerSource
from hermes.sources.rooster import RoosterSource
from hermes.sources.topjobs import TopjobsSource
from hermes.sources.xpressjobs import XpressjobsSource

SOURCE_ORDER: tuple[str, ...] = (
    "itpro",
    "topjobs",
    "rooster",
    "xpressjobs",
    "jobseeker",
)

SOURCE_REGISTRY: dict[str, JobSource] = {
    "itpro": ItproSource(),
    "topjobs": TopjobsSource(),
    "rooster": RoosterSource(),
    "xpressjobs": XpressjobsSource(),
    "jobseeker": JobseekerSource(),
}

__all__ = [
    "SOURCE_ORDER",
    "SOURCE_REGISTRY",
    "JobSource",
    "JobseekerSource",
    "ItproSource",
    "RoosterSource",
    "TopjobsSource",
    "XpressjobsSource",
]
