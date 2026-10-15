from __future__ import annotations

import logging
from pathlib import Path

import typer

from hermes.config import Settings, validate_config_file
from hermes.pipeline import run_pipeline
from hermes.sources import SOURCE_ORDER

app = typer.Typer(
    name="hermes",
    help="Hermes job agent — scrape, filter, dedupe, and notify.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Configuration commands.")
app.add_typer(config_app, name="config")


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@app.command()
def run(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Fetch and filter jobs without writing to the database or Telegram.",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        help="Path to config.yaml (overrides HERMES_CONFIG_PATH).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the job pipeline once."""
    _configure_logging(verbose)
    jobs = run_pipeline(config_path=config, dry_run=dry_run)
    typer.echo(f"Done. {'Matched' if dry_run else 'New'} jobs: {len(jobs)}")


@config_app.command("validate")
def config_validate(
    config: Path | None = typer.Option(
        None,
        "--config",
        help="Path to config.yaml (defaults to HERMES_CONFIG_PATH or ./config.yaml).",
    ),
) -> None:
    """Validate config.yaml structure."""
    settings = Settings()
    path = config or settings.hermes_config_path
    cfg = validate_config_file(path)
    flags = {
        "itpro": cfg.sources.itpro.enabled,
        "topjobs": cfg.sources.topjobs.enabled,
        "rooster": cfg.sources.rooster.enabled,
        "xpressjobs": cfg.sources.xpressjobs.enabled,
    }
    enabled = [name for name in SOURCE_ORDER if flags.get(name)]
    typer.echo(f"Config OK: {path}")
    typer.echo(f"  role_keywords: {len(cfg.role_keywords)}")
    typer.echo(f"  track_keywords: {len(cfg.track_keywords)}")
    typer.echo(f"  location_include: {len(cfg.location_include)}")
    typer.echo(f"  match_mode: {cfg.match_mode}")
    typer.echo(f"  enabled sources: {', '.join(enabled) or '(none)'}")
