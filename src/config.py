"""Configuration loading, validation, and secret resolution.

Secrets come from the environment (``.env``); behavioural settings come from
``config.yaml``.  Both are validated into typed Pydantic models so downstream
agents never guess at a value's type or presence.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_ENV_PATH = Path(".env")

DEFAULT_PROMPT_TEMPLATE = (
    "You are a sharp, thoughtful industry observer on LinkedIn.\n"
    "Write a 1-2 sentence concise, opinionated takeaway based on this tweet.\n"
    "Be insightful, direct, and conversational.\n"
    "Do NOT include hashtags, corporate buzzwords, quotes, or conversational filler."
)


class ConfigurationError(RuntimeError):
    """Raised when configuration or credentials are missing or invalid."""


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class TwitterConfig(_Base):
    """Twitter/X ingestion settings."""

    cookies_path: Path = Path("cookies.json")
    accounts: list[str] = Field(default_factory=lambda: ["sama", "karpathy", "ylecun"])
    lookback_hours: int = Field(default=12, ge=1, le=168)
    exclude_replies: bool = True
    exclude_retweets: bool = True
    max_tweets_per_account: int = Field(default=40, ge=1, le=500)
    account_delay_seconds: float = Field(default=2.0, ge=0.0, le=60.0)

    @field_validator("accounts", mode="before")
    @classmethod
    def _split_accounts(cls, value: Any) -> Any:
        """Accept a comma-separated string as well as a YAML list."""
        if isinstance(value, str):
            return [part.strip() for part in value.split(",")]
        if isinstance(value, (list, tuple)):
            return [str(part).strip() for part in value]
        return value

    @field_validator("accounts")
    @classmethod
    def _require_accounts(cls, value: list[str]) -> list[str]:
        cleaned = [handle.lstrip("@").strip() for handle in value if handle.strip()]
        if not cleaned:
            raise ValueError("at least one monitored twitter account is required")
        return cleaned

    def lookback_cutoff(self, now: datetime | None = None) -> datetime:
        """Return the UTC instant before which tweets are considered stale."""
        reference = now or datetime.now(UTC)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        return reference.astimezone(UTC) - timedelta(hours=self.lookback_hours)


class FeedItemConfig(_Base):
    """Configuration for an individual monitored website RSS/Atom feed."""

    name: str = Field(min_length=1, description="Publication title")
    url: str = Field(min_length=8, description="RSS/Atom XML URL")
    category: str | None = Field(default=None)
    max_items: int | None = Field(default=None, ge=1, le=50)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("feed name cannot be empty")
        return cleaned

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
            raise ValueError(f"feed url must start with http:// or https://: {cleaned!r}")
        return cleaned


class NewsConfig(_Base):
    """RSS and website news ingestion settings."""

    lookback_hours: int = Field(default=24, ge=1, le=168)
    max_articles_per_feed: int = Field(default=8, ge=1, le=50)
    request_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    user_agent: str = Field(default="LinkedInSidekick/1.0")
    feeds: list[FeedItemConfig] = Field(default_factory=list)

    @field_validator("feeds")
    @classmethod
    def _validate_unique_urls(cls, feeds: list[FeedItemConfig]) -> list[FeedItemConfig]:
        seen_urls: set[str] = set()
        for f in feeds:
            normalized = f.url.strip().lower().rstrip("/")
            if normalized in seen_urls:
                raise ValueError(f"duplicate feed url configured: {f.url}")
            seen_urls.add(normalized)
        return feeds

    def lookback_cutoff(self, now: datetime | None = None) -> datetime:
        """Return the UTC instant before which articles are considered stale."""
        reference = now or datetime.now(UTC)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        return reference.astimezone(UTC) - timedelta(hours=self.lookback_hours)


class RenderConfig(_Base):
    """Playwright card capture styling."""

    theme: Literal["dark", "light"] = "dark"
    hide_metrics: bool = True
    viewport_width: int = Field(default=1200, ge=320, le=4096)
    viewport_height: int = Field(default=800, ge=240, le=4096)
    timeout_seconds: int = Field(default=15, ge=1, le=120)
    output_dir: Path = Path(".assets/screenshots")


class AgentConfig(_Base):
    """Gemini commentary synthesis settings."""

    model: str = "gemini-3.8-flash"
    max_sentences: int = Field(default=2, ge=1, le=5)
    grounding: bool = True
    prompt_template: str = DEFAULT_PROMPT_TEMPLATE
    context_dir: Path = Field(default=Path("context"))


class SchedulerConfig(_Base):
    """Dual-mode runner scheduling settings."""

    default_interval_minutes: int = Field(default=60, ge=1)
    auto_publish: bool = False


class StorageConfig(_Base):
    """SQLite persistence settings."""

    db_path: Path = Path("state/sidekick.db")


class LoggingConfig(_Base):
    """Structured logging settings."""

    level: str = "INFO"
    log_file: Path | None = Path("state/sidekick.log")

    @field_validator("level")
    @classmethod
    def _upper_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        normalised = value.upper()
        if normalised not in allowed:
            raise ValueError(f"log level must be one of {sorted(allowed)}")
        return normalised


class Secrets(_Base):
    """Credentials resolved from the process environment.

    Only genuinely secret material lives here.  File-system locations (the
    Twitter cookie export, the ledger database) are ordinary configuration and
    therefore have exactly one home: ``config.yaml``.
    """

    google_api_key: SecretStr | None = None
    linkedin_access_token: SecretStr | None = None
    linkedin_person_urn: str | None = None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Secrets:
        source = env if env is not None else os.environ

        def _clean(key: str) -> str | None:
            raw = source.get(key)
            if raw is None:
                return None
            stripped = raw.strip().strip('"').strip("'")
            return stripped or None

        google_key = _clean("GOOGLE_API_KEY") or _clean("GEMINI_API_KEY")
        person_urn = _clean("LINKEDIN_PERSON_URN")
        if person_urn is not None:
            person_urn = person_urn.rsplit(":", 1)[-1].strip() or None

        linkedin_token = _clean("LINKEDIN_ACCESS_TOKEN")

        return cls(
            google_api_key=SecretStr(google_key) if google_key else None,
            linkedin_access_token=SecretStr(linkedin_token) if linkedin_token else None,
            linkedin_person_urn=person_urn,
        )


class AppConfig(_Base):
    """Fully resolved application configuration."""

    twitter: TwitterConfig = Field(default_factory=TwitterConfig)
    news: NewsConfig = Field(default_factory=NewsConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    secrets: Secrets = Field(default_factory=Secrets)

    # -- credential gates ---------------------------------------------------
    def require_google_api_key(self) -> str:
        """Return the Gemini API key or fail with an actionable message."""
        if self.secrets.google_api_key is None:
            raise ConfigurationError(
                "GOOGLE_API_KEY (or GEMINI_API_KEY) is required to synthesize "
                "commentary. Add it to your .env file."
            )
        return self.secrets.google_api_key.get_secret_value()

    def require_linkedin_credentials(self) -> tuple[str, str]:
        """Return ``(access_token, person_urn)`` or fail with a clear message."""
        if self.secrets.linkedin_access_token is None:
            raise ConfigurationError(
                "LINKEDIN_ACCESS_TOKEN is required to publish. Add it to your "
                ".env file, or run with --dry-run."
            )
        if not self.secrets.linkedin_person_urn:
            raise ConfigurationError(
                "LINKEDIN_PERSON_URN is required to publish. Add it to your "
                ".env file, or run with --dry-run."
            )
        return (
            self.secrets.linkedin_access_token.get_secret_value(),
            self.secrets.linkedin_person_urn,
        )


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem dependent
        raise ConfigurationError(f"Could not read config file {path}: {exc}") from exc

    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in {path}: {exc}") from exc

    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigurationError(
            f"Config file {path} must contain a YAML mapping at the top level."
        )
    return loaded


def load_config(
    config_path: str | Path | None = None,
    *,
    env_path: str | Path | None = None,
    load_env: bool = True,
    env: dict[str, str] | None = None,
) -> AppConfig:
    """Load and validate application configuration.

    Args:
        config_path: Explicit YAML path.  Falls back to ``CONFIG_PATH`` and then
            ``config.yaml``.  When no file exists, built-in defaults are used.
        env_path: Explicit ``.env`` path.  Defaults to ``.env`` in the cwd.
        load_env: Set to ``False`` to skip ``.env`` hydration (used by tests).
        env: Explicit environment mapping used instead of ``os.environ``.

    Raises:
        ConfigurationError: If the YAML is malformed or values fail validation.
    """
    if load_env:
        dotenv_path = Path(env_path) if env_path is not None else DEFAULT_ENV_PATH
        load_dotenv(dotenv_path=dotenv_path, override=False)

    resolved_source: dict[str, str] = env if env is not None else dict(os.environ)
    explicit = config_path is not None
    candidate = config_path or resolved_source.get("CONFIG_PATH") or DEFAULT_CONFIG_PATH
    path = Path(candidate)

    raw: dict[str, Any] = {}
    if path.exists():
        raw = _read_yaml(path)
    elif explicit:
        raise ConfigurationError(f"Config file not found: {path}")

    raw = dict(raw)
    raw["secrets"] = Secrets.from_env(env)

    context_dir_override = resolved_source.get("CONTEXT_DIR")
    if context_dir_override and context_dir_override.strip():
        agent_dict = dict(raw.get("agent") or {})
        agent_dict["context_dir"] = Path(context_dir_override.strip())
        raw["agent"] = agent_dict

    account_delay_override = resolved_source.get("SIDEKICK_ACCOUNT_DELAY_SECONDS")
    if account_delay_override and account_delay_override.strip():
        twitter_dict = dict(raw.get("twitter") or {})
        try:
            twitter_dict["account_delay_seconds"] = float(
                account_delay_override.strip()
            )
            raw["twitter"] = twitter_dict
        except ValueError:
            pass

    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid configuration in {path}:\n{exc}") from exc


__all__ = [
    "AgentConfig",
    "AppConfig",
    "ConfigurationError",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_PROMPT_TEMPLATE",
    "FeedItemConfig",
    "LoggingConfig",
    "NewsConfig",
    "RenderConfig",
    "SchedulerConfig",
    "Secrets",
    "StorageConfig",
    "TwitterConfig",
    "load_config",
]
