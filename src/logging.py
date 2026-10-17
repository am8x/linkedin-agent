"""Structured logging: rich console output plus rotating file diagnostics.

The module is intentionally named ``src.logging`` to mirror the project layout
described in ``plan.md``.  Because it lives inside the ``src`` package and the
repository root (not ``src/``) is the only path entry on ``sys.path``, the
stdlib ``logging`` module is still imported unambiguously below.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

CONSOLE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s"
FILE_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

ROOT_LOGGER_NAME = "sidekick"
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3

_configured = False


def _build_console_handler(level: int) -> logging.Handler:
    """Prefer rich when available, degrade to a plain stream handler."""
    try:
        from rich.logging import RichHandler
    except ImportError:  # pragma: no cover - rich is a declared dependency
        handler: logging.Handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, datefmt=DATE_FORMAT))
    else:
        handler = RichHandler(
            rich_tracebacks=True,
            show_path=False,
            show_time=True,
            omit_repeated_times=False,
            markup=False,
        )
        # Rich renders its own timestamp/level columns, so the formatter only
        # needs to emit the message body.
        handler.setFormatter(logging.Formatter("%(message)s", datefmt=DATE_FORMAT))
    handler.setLevel(level)
    return handler


def _build_file_handler(log_file: Path, level: int) -> logging.Handler:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT))
    handler.setLevel(level)
    return handler


def setup_logging(
    level: str = "INFO",
    log_file: str | Path | None = None,
    *,
    force: bool = False,
) -> logging.Logger:
    """Configure the ``sidekick`` logger tree and return the root logger.

    Args:
        level: Log level name (``INFO``, ``DEBUG``, ...).
        log_file: Optional rotating diagnostics file.  ``None`` disables file
            logging.
        force: Tear down and rebuild handlers even if already configured.

    Returns:
        The configured ``sidekick`` root logger.
    """
    global _configured

    logger = logging.getLogger(ROOT_LOGGER_NAME)
    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    if _configured and not force:
        logger.setLevel(numeric_level)
        return logger

    for existing in list(logger.handlers):
        logger.removeHandler(existing)
        existing.close()

    logger.setLevel(numeric_level)
    logger.propagate = False
    logger.addHandler(_build_console_handler(numeric_level))

    if log_file is not None:
        logger.addHandler(_build_file_handler(Path(log_file), numeric_level))

    _configured = True
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a namespaced child of the ``sidekick`` logger tree."""
    if not name or name == ROOT_LOGGER_NAME:
        return logging.getLogger(ROOT_LOGGER_NAME)
    if name.startswith(f"{ROOT_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


def is_configured() -> bool:
    """Whether :func:`setup_logging` has already installed handlers."""
    return _configured


__all__ = ["get_logger", "is_configured", "setup_logging"]
