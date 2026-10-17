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
    """Credentials resolved from the process environment."""

    google_api_key: SecretStr | None = None
    linkedin_access_token: SecretStr | None = None
    linkedin_person_urn: str | None = None
    twitter_cookies_path: Path | None = None
    db_path_override: Path | None = None

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

        cookies = _clean("TWITTER_COOKIES_PATH")
        db_path = _clean("SIDEKICK_DB_PATH")
        linkedin_token = _clean("LINKEDIN_ACCESS_TOKEN")

        return cls(
            google_api_key=SecretStr(google_key) if google_key else None,
            linkedin_access_token=SecretStr(linkedin_token) if linkedin_token else None,
            linkedin_person_urn=person_urn,
            twitter_cookies_path=Path(cookies) if cookies else None,
            db_path_override=Path(db_path) if db_path else None,
        )


class AppConfig(_Base):
    """Fully resolved application configuration."""

    twitter: TwitterConfig = Field(default_factory=TwitterConfig)
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

    # -- convenience --------------------------------------------------------
    @property
    def effective_cookies_path(self) -> Path:
        """Cookies path with the ``TWITTER_COOKIES_PATH`` override applied."""
        return self.secrets.twitter_cookies_path or self.twitter.cookies_path

    @property
    def effective_db_path(self) -> Path:
        """Database path with the ``SIDEKICK_DB_PATH`` override applied."""
        return self.secrets.db_path_override or self.storage.db_path


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
    raw.setdefault("twitter", {})
    if "twitter" in raw and isinstance(raw["twitter"], dict):
        cookies_override = raw["secrets"].twitter_cookies_path
        if cookies_override is not None:
            raw["twitter"]["cookies_path"] = cookies_override

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
    "LoggingConfig",
    "RenderConfig",
    "SchedulerConfig",
    "Secrets",
    "StorageConfig",
    "TwitterConfig",
    "load_config",
]
