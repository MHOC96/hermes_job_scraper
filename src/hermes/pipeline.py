from __future__ import annotations

import logging
from pathlib import Path

from hermes.config import HermesConfig, Settings, load_config
from hermes.filters import filter_jobs
from hermes.models import JobPosting, SourceStatus, SourceUnavailableError
from hermes.notify.telegram import send_job_batch
from hermes.sources import SOURCE_ORDER, SOURCE_REGISTRY
from hermes.store import JobStore

logger = logging.getLogger(__name__)


def _enabled_sources(config: HermesConfig) -> list[str]:
    flags = {
        "itpro": config.sources.itpro.enabled,
        "topjobs": config.sources.topjobs.enabled,
        "rooster": config.sources.rooster.enabled,
        "xpressjobs": config.sources.xpressjobs.enabled,
    }
    return [name for name in SOURCE_ORDER if flags.get(name)]


def fetch_all_sources(
    config: HermesConfig,
) -> tuple[list[JobPosting], dict[str, SourceStatus]]:
    jobs: list[JobPosting] = []
    statuses: dict[str, SourceStatus] = {}
    for name in _enabled_sources(config):
        source = SOURCE_REGISTRY.get(name)
        if source is None:
            logger.warning("Unknown source %r; skipping", name)
            continue
        logger.info("Running source %s", name)
        try:
            fetched = source.fetch(config)
            jobs.extend(fetched)
            statuses[name] = SourceStatus(name=name, fetched=len(fetched))
        except SourceUnavailableError as exc:
            logger.warning("Source %s unavailable: %s", name, exc)
            statuses[name] = SourceStatus(name=name, ok=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Source %s failed", name)
            statuses[name] = SourceStatus(
                name=name, ok=False, error=f"error ({type(exc).__name__})"
            )
    return jobs, statuses


def run_pipeline(
    *,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> list[JobPosting]:
    settings = Settings()
    config = load_config(config_path or settings.hermes_config_path)

    raw_jobs, statuses = fetch_all_sources(config)
    by_source: dict[str, int] = {}
    for job in raw_jobs:
        by_source[job.source] = by_source.get(job.source, 0) + 1
    logger.info(
        "Fetched %s job(s) from sources (%s)",
        len(raw_jobs),
        ", ".join(f"{k}={v}" for k, v in sorted(by_source.items())) or "none",
    )

    filtered = filter_jobs(raw_jobs, config)
    filt_src: dict[str, int] = {}
    for job in filtered:
        filt_src[job.source] = filt_src.get(job.source, 0) + 1
    logger.info(
        "%s job(s) after filtering (%s)",
        len(filtered),
        ", ".join(f"{k}={v}" for k, v in sorted(filt_src.items())) or "none",
    )

    if dry_run:
        for job in filtered:
            logger.info(
                "[dry-run] %s | %s @ %s | %s",
                job.source,
                job.title,
                job.company,
                job.url,
            )
        return filtered

    store = JobStore(settings.hermes_db_path)
    new_jobs = store.insert_new(filtered)
    logger.info("%s new job(s) stored", len(new_jobs))

    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if new_jobs and token and chat_id:
        send_job_batch(
            new_jobs,
            bot_token=token,
            chat_id=chat_id,
            source_status=statuses,
        )
    elif new_jobs:
        logger.warning(
            "New jobs found but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set; "
            "skipping notification."
        )

    return new_jobs
