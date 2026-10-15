from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ItproSourceConfig(BaseModel):
    enabled: bool = True
    max_pages: int = Field(default=3, ge=1, le=50)


class TopjobsSourceConfig(BaseModel):
    enabled: bool = True
    search_terms: list[str] = Field(default_factory=list)
    max_pages: int = Field(default=2, ge=1, le=20)


class XpressjobsSourceConfig(BaseModel):
    enabled: bool = True
    search_terms: list[str] = Field(default_factory=list)
    max_pages: int = Field(default=2, ge=1, le=20)
    page_size: int = Field(default=30, ge=5, le=100)
    listing_days: int = Field(
        default=14,
        ge=7,
        le=90,
        description="Assumed ad lifetime on Xpress when createdDate is missing.",
    )


class RoosterSourceConfig(BaseModel):
    enabled: bool = True
    search_terms: list[str] = Field(default_factory=list)
    max_pages: int = Field(default=2, ge=1, le=20)
    page_size: int = Field(default=20, ge=5, le=100)
    country: str = Field(default="Sri Lanka")


class SourcesConfig(BaseModel):
    itpro: ItproSourceConfig = Field(default_factory=ItproSourceConfig)
    topjobs: TopjobsSourceConfig = Field(default_factory=TopjobsSourceConfig)
    rooster: RoosterSourceConfig = Field(default_factory=RoosterSourceConfig)
    xpressjobs: XpressjobsSourceConfig = Field(default_factory=XpressjobsSourceConfig)


class HermesConfig(BaseModel):
    # Legacy: combined into track matching when track_keywords is empty.
    job_titles: list[str] = Field(default_factory=list)
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    match_fields: list[str] = Field(
        default_factory=lambda: ["title", "company", "location"]
    )
    match_mode: Literal["any", "all"] = "any"
    # Internship gate: at least one must appear in the job title.
    role_keywords: list[str] = Field(
        default_factory=lambda: ["intern", "internship", "trainee"]
    )
    # Career tracks: at least one must match match_fields (backend, AI, audit, BA, etc.).
    track_keywords: list[str] = Field(default_factory=list)
    location_include: list[str] = Field(default_factory=list)
    location_allow_remote: bool = True
    location_allow_empty: bool = True
    max_posting_age_days: int = Field(
        default=14,
        ge=0,
        description="Only jobs posted/opened within this many days (0 = no limit).",
    )
    include_undated: bool = Field(
        default=False,
        description="Keep jobs when the site does not expose a posting/opening date.",
    )
    sources: SourcesConfig = Field(default_factory=SourcesConfig)

    @field_validator(
        "job_titles",
        "include_keywords",
        "exclude_keywords",
        "role_keywords",
        "track_keywords",
        "location_include",
        mode="before",
    )
    @classmethod
    def _coerce_str_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return [str(item).strip() for item in value if str(item).strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = Field(default=None, alias="TELEGRAM_CHAT_ID")
    hermes_db_path: Path = Field(
        default=Path("data/hermes.db"), alias="HERMES_DB_PATH"
    )
    hermes_config_path: Path = Field(
        default=Path("config.yaml"), alias="HERMES_CONFIG_PATH"
    )


def default_config_path() -> Path:
    return Settings().hermes_config_path


def load_config(path: Path | None = None) -> HermesConfig:
    config_path = path or default_config_path()
    if not config_path.is_file():
        raise FileNotFoundError(f"Config not found: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return HermesConfig.model_validate(raw)


def validate_config_file(path: Path | None = None) -> HermesConfig:
    return load_config(path)
