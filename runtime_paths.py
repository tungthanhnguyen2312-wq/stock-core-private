"""Resolve the mutable dashboard runtime directory for local producers."""

from __future__ import annotations

import os
from pathlib import Path


RUNTIME_ROOT_ENV = "STOCK_LOOKUP_RUNTIME_ROOT"


def runtime_root(default: str | os.PathLike[str]) -> Path:
    """Use the configured runtime root, or preserve a caller's legacy default."""
    configured = os.getenv(RUNTIME_ROOT_ENV, "").strip()
    return Path(configured or default).expanduser().resolve()
