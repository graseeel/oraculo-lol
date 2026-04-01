from __future__ import annotations

from .logging_utils import configure_logging
from .paths import ensure_dir
from .settings import load_settings


def init_runtime() -> None:
    s = load_settings()
    configure_logging(level=s.log_level, fmt=s.log_format)
    ensure_dir(s.abs_data_dir())

