"""Desktop application logging configuration."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .storage import DATA_DIR


def configure_logging() -> None:
    log_file = DATA_DIR / "app.log"
    handler = RotatingFileHandler(
        log_file,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(item, RotatingFileHandler) for item in root.handlers):
        root.addHandler(handler)
