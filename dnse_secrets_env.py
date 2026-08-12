"""The one module permitted to read ``secrets.env``.

Everywhere else in this codebase, "no secrets.env" is a documented invariant --
see ``dnse_access.py`` and every ``tools/ingest_dnse_*.py``/probe module
docstring, which all rely on an external launcher having already populated
the process environment before they start. A bulk, potentially long-running
ingestion run cannot assume that launcher is in front of it, so this module
exists to do the one thing none of those do: read the approved local secrets
file and inject credentials into ``os.environ`` itself.

CONTRACT
    - Reads ``KEY=VALUE`` lines from a ``.env``-style file. No third-party
      ``dotenv`` dependency is used (none is installed in this repository).
    - Only ever injects the exact key names this codebase already consumes
      (``dnse_access.CREDENTIAL_ENV_PAIRS``) -- never an arbitrary key from
      the file.
    - Sets ``os.environ[KEY]`` only when ``KEY`` is not already set. A real
      launcher or an already-configured shell always wins over this file.
    - Never returns, logs, or prints a credential value anywhere. Every
      function here returns a redacted status dict at most (key *names* and
      counts, never values) -- the same discipline ``dnse_access.
      credential_status()`` already uses.
    - Never raises on a missing or unreadable file: that is an expected,
      normal state (e.g. a sandbox without the owner's local file), reported
      structurally rather than as an exception.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dnse_access import CREDENTIAL_ENV_PAIRS, credential_status

#: Overrides the default file location -- e.g. for a machine/session where the
#: owner's approved path is not reachable.
SECRETS_PATH_ENV = "STOCK_LOOKUP_SECRETS_FILE"

#: The owner-approved local credential source (see AGENTS.md and the current
#: milestone brief). A file path is not itself credential material.
DEFAULT_SECRETS_PATH = r"C:\Users\tungt\.stocklookup\secrets.env"

_KNOWN_KEYS = frozenset(key for pair in CREDENTIAL_ENV_PAIRS for key in pair)


def secrets_path(path: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the file to read: explicit arg > env override > owner default."""
    if path is not None:
        return Path(path)
    configured = os.getenv(SECRETS_PATH_ENV, "").strip()
    return Path(configured) if configured else Path(DEFAULT_SECRETS_PATH)


def _parse_env_lines(text: str) -> dict[str, str]:
    """Minimal ``KEY=VALUE`` parser: blank lines and ``#`` comments skipped,
    an optional leading ``export ``, optional surrounding quotes stripped.
    No interpolation, multi-line values, or other full-dotenv behavior --
    the credential file this reads only ever needs flat key/value pairs."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_secrets_env(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load known credential keys from a secrets file into ``os.environ``.

    Returns a redacted status dict describing what happened -- file found,
    which known key *names* it carried, which were injected vs. already set.
    Never includes a value.
    """
    target = secrets_path(path)
    result: dict[str, Any] = {
        "path": str(target),
        "file_found": False,
        "keys_found_in_file": [],
        "keys_injected": [],
        "keys_already_set": [],
    }
    try:
        text = target.read_text(encoding="utf-8-sig")
    except OSError:
        return result
    result["file_found"] = True
    parsed = _parse_env_lines(text)
    found = sorted(key for key in parsed if key in _KNOWN_KEYS)
    result["keys_found_in_file"] = found
    for key in found:
        if os.getenv(key) is not None:
            result["keys_already_set"].append(key)
            continue
        value = parsed[key]
        if value:
            os.environ[key] = value
            result["keys_injected"].append(key)
    parsed.clear()  # never retained beyond this call
    return result


def ensure_credentials_loaded(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load from the secrets file only if no credential pair is already
    configured in the environment, then report the same shape as
    ``dnse_access.credential_status()`` plus where this looked."""
    if credential_status()["configured"]:
        return {**credential_status(), "secrets_file_consulted": False}
    load_result = load_secrets_env(path)
    return {
        **credential_status(),
        "secrets_file_consulted": True,
        "secrets_file_found": load_result["file_found"],
        "secrets_file_path": load_result["path"],
    }
