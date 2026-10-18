"""Unit tests for configuration loading.

These guard one invariant: file-system locations — the Twitter cookie export
and the SQLite publication ledger — are configured **only** in ``config.yaml``.
No environment variable may shadow them, so there is exactly one source of
truth per path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.agent.capture import create_capture_agent
from src.agent.ingestion import create_ingestion_agent
from src.config import (
    ConfigurationError,
    Secrets,
    load_config,
)
from src.runner import PipelineRunner, RunnerOptions

YAML_TEMPLATE = """\
twitter:
  cookies_path: "{cookies}"
  accounts: ["sama"]
  lookback_hours: 12
storage:
  db_path: "{db}"
"""


def write_yaml(tmp_path: Path, cookies: str, db: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(YAML_TEMPLATE.format(cookies=cookies, db=db), encoding="utf-8")
    return path


def load(tmp_path: Path, cookies: str, db: str, env: dict[str, str] | None = None):
    yaml_path = write_yaml(tmp_path, cookies, db)
    return load_config(yaml_path, load_env=False, env=env or {})


# ---------------------------------------------------------------------------
# config.yaml is the single source of truth
# ---------------------------------------------------------------------------
class TestYamlIsTheSingleSourceOfTruth:
    def test_paths_come_from_the_yaml_file(self, tmp_path: Path) -> None:
        config = load(tmp_path, "cookies.json", "state/sidekick.db")
        assert config.twitter.cookies_path == Path("cookies.json")
        assert config.storage.db_path == Path("state/sidekick.db")

    def test_environment_cannot_shadow_the_yaml_paths(self, tmp_path: Path) -> None:
        config = load(
            tmp_path,
            "real-cookies.json",
            "state/real.db",
            env={
                "TWITTER_COOKIES_PATH": "shadow-cookies.json",
                "SIDEKICK_DB_PATH": "shadow.db",
            },
        )
        assert config.twitter.cookies_path == Path("real-cookies.json")
        assert config.storage.db_path == Path("state/real.db")

    def test_config_path_env_selects_the_yaml_file(self, tmp_path: Path) -> None:
        yaml_path = write_yaml(tmp_path, "from-env.json", "state/from-env.db")
        config = load_config(load_env=False, env={"CONFIG_PATH": str(yaml_path)})
        assert config.twitter.cookies_path == Path("from-env.json")

    def test_explicit_missing_file_fails_fast(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError, match="not found"):
            load_config(tmp_path / "ghost.yaml", load_env=False, env={})

    def test_defaults_apply_when_no_file_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)  # no config.yaml here
        config = load_config(load_env=False, env={})
        assert config.twitter.cookies_path == Path("cookies.json")
        assert config.storage.db_path == Path("state/sidekick.db")


# ---------------------------------------------------------------------------
# Secrets hold credentials only — never file-system locations
# ---------------------------------------------------------------------------
class TestSecretsCarryOnlyCredentials:
    def test_secrets_model_has_no_path_fields(self) -> None:
        secrets = Secrets()
        assert not hasattr(secrets, "twitter_cookies_path")
        assert not hasattr(secrets, "db_path_override")

    def test_path_env_vars_do_not_leak_into_secrets(self) -> None:
        secrets = Secrets.from_env(
            {
                "GOOGLE_API_KEY": "key-123",
                "TWITTER_COOKIES_PATH": "cookies.json",
                "SIDEKICK_DB_PATH": "state/sidekick.db",
            }
        )
        assert secrets.google_api_key is not None
        assert not hasattr(secrets, "twitter_cookies_path")


# ---------------------------------------------------------------------------
# The YAML values reach the components that actually use them
# ---------------------------------------------------------------------------
class TestPathWiring:
    def test_ingestion_agent_uses_the_yaml_cookies_path(self, tmp_path: Path) -> None:
        config = load(tmp_path, "yaml-cookies.json", "state/x.db")
        agent = create_ingestion_agent(config)
        assert agent.cookies_path == Path("yaml-cookies.json")

    def test_capture_agent_uses_the_yaml_cookies_path(self, tmp_path: Path) -> None:
        config = load(tmp_path, "yaml-cookies.json", "state/x.db")
        agent = create_capture_agent(config)
        assert agent.cookies_path == Path("yaml-cookies.json")

    def test_runner_opens_the_ledger_at_the_yaml_db_path(self, tmp_path: Path) -> None:
        db_path = tmp_path / "ledger.db"
        config = load(tmp_path, "cookies.json", db_path.as_posix())

        runner = PipelineRunner(RunnerOptions(), config=config)

        assert db_path.exists()
        assert runner.ledger.count() == 0

    def test_config_is_a_plain_validated_model(self, tmp_path: Path) -> None:
        config = load(tmp_path, "cookies.json", "state/sidekick.db")
        dumped: dict[str, Any] = config.model_dump()
        assert dumped["twitter"]["cookies_path"] == Path("cookies.json")


class TestContextDirConfiguration:
    def test_context_dir_default_path(self, tmp_path: Path) -> None:
        config = load(tmp_path, "cookies.json", "state/sidekick.db")
        assert config.agent.context_dir == Path("context")

    def test_context_dir_from_yaml_relative_and_absolute(self, tmp_path: Path) -> None:
        yaml_content = """
twitter:
  cookies_path: "cookies.json"
storage:
  db_path: "state/sidekick.db"
agent:
  context_dir: "custom/context"
"""
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")
        config = load_config(yaml_path, load_env=False)
        assert config.agent.context_dir == Path("custom/context")

        # Absolute path
        abs_context = (tmp_path / "absolute_context").resolve()
        yaml_content_abs = f"""
twitter:
  cookies_path: "cookies.json"
storage:
  db_path: "state/sidekick.db"
agent:
  context_dir: "{abs_context.as_posix()}"
"""
        yaml_path.write_text(yaml_content_abs, encoding="utf-8")
        config_abs = load_config(yaml_path, load_env=False)
        assert config_abs.agent.context_dir == abs_context

    def test_context_dir_environment_override(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(
            """
twitter:
  cookies_path: "cookies.json"
storage:
  db_path: "state/sidekick.db"
agent:
  context_dir: "from_yaml"
""",
            encoding="utf-8",
        )
        config = load_config(
            yaml_path, load_env=False, env={"CONTEXT_DIR": "from_env/context"}
        )
        assert config.agent.context_dir == Path("from_env/context")

    def test_context_dir_cli_flag(self) -> None:
        from src.runner import parse_args

        opts = parse_args(["--context-dir", "cli/context"])
        assert opts.context_dir == Path("cli/context")

    def test_account_delay_seconds_from_yaml_and_default(self, tmp_path: Path) -> None:
        from src.config import TwitterConfig

        tc = TwitterConfig(accounts=["sama"])
        assert tc.account_delay_seconds == 2.0

        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(
            """
twitter:
  cookies_path: "cookies.json"
  accounts: ["sama"]
  account_delay_seconds: 4.5
storage:
  db_path: "state/sidekick.db"
""",
            encoding="utf-8",
        )
        config = load_config(yaml_path, load_env=False)
        assert config.twitter.account_delay_seconds == 4.5

    def test_account_delay_seconds_environment_override(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(
            """
twitter:
  cookies_path: "cookies.json"
  accounts: ["sama"]
  account_delay_seconds: 2.0
storage:
  db_path: "state/sidekick.db"
""",
            encoding="utf-8",
        )
        config = load_config(
            yaml_path,
            load_env=False,
            env={"SIDEKICK_ACCOUNT_DELAY_SECONDS": "5.5"},
        )
        assert config.twitter.account_delay_seconds == 5.5
