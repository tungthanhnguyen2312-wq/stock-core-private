"""Secret-safe EODHD credential boundary.

Only the request adapter may obtain the token.  Status and diagnostic helpers
must never serialize, log, or interpolate credential material.
"""
from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TOKEN_ENV = "EODHD_API_TOKEN"


def credential_status() -> dict[str, object]:
    """Describe credential availability without returning credential material."""
    return {
        "configured": bool(os.getenv(TOKEN_ENV, "").strip()),
        "source": "environment",
        "validation_status": "not_checked",
    }


def token_for_request() -> str | None:
    """Return the token exclusively for construction of an authenticated request."""
    value = os.getenv(TOKEN_ENV, "").strip()
    return value or None


def sanitize_url(value: str) -> str:
    """Remove authentication values while retaining useful endpoint diagnostics."""
    parts = urlsplit(str(value))
    safe_query = [(key, "<redacted>" if key.lower() == "api_token" else item)
                  for key, item in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_query), parts.fragment))


def safe_error_code(error: BaseException) -> str:
    """Return a bounded error identity; exception messages may contain request URLs."""
    return type(error).__name__
