"""Secret-safe DNSE OpenAPI credential and request-signing boundary.

Only `auth_headers()` may see credential material, and only to compute an
HMAC-SHA256 request signature per the official `dnse-tech/openapi-sdk`
scheme (verified against the vendor's published Python SDK source,
2026-08-10). The API secret is never transmitted or logged: it is used
solely as the HMAC key. Status/diagnostic helpers must never serialize,
log, or interpolate credential material, and every response/error path in
this module must be safe to print verbatim.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

BASE_URL = "https://openapi.dnse.com.vn"
DEFAULT_API_VERSION_ENV = "DNSE_API_VERSION"
# Default lifted verbatim from the official SDK's common.py (DEFAULT_API_VERSION,
# read 2026-08-10). Overridable so a later server-side rollover does not require
# a code change.
DEFAULT_API_VERSION = "2026-07-23"

# Both name pairs are accepted so this module never needs to know (or care)
# which convention an owner's secrets.env file happens to use. Checked in
# order; the first pair with BOTH values non-empty wins.
CREDENTIAL_ENV_PAIRS: tuple[tuple[str, str], ...] = (
    ("DNSE_API_KEY", "DNSE_API_SECRET"),
    ("LIVESPEED_API_KEY", "LIVESPEED_API_SECRET"),
)

_SENSITIVE_KEY_SUBSTRINGS = (
    "token", "secret", "password", "passwd", "apikey", "api_key", "api-key",
    "authorization", "signature", "cookie", "credential", "otp", "x-api-key",
    "auth",
)
# Deliberately NOT any "session" variant: DNSE market-data responses
# legitimately use "tradingSessions"/"tradingSessionId" for trading-calendar
# and session-state data (the Phase D "TRADING CALENDAR / SESSION" capability
# family) -- a substring match here would silently redact real market
# structure data instead of a credential. "token" alone still catches the
# realistic risky pattern (sessionToken, accessToken, etc).
_REDACTED = "<redacted>"


def _find_credential_pair() -> tuple[str, str] | None:
    for key_name, secret_name in CREDENTIAL_ENV_PAIRS:
        key = os.getenv(key_name, "").strip()
        secret = os.getenv(secret_name, "").strip()
        if key and secret:
            return key, secret
    return None


def credential_status() -> dict[str, Any]:
    """Describe credential availability without naming which env pair matched
    or returning any credential material."""
    return {
        "configured": _find_credential_pair() is not None,
        "source": "environment",
        "validation_status": "not_checked",
    }


def credentials_for_request() -> tuple[str, str] | None:
    """Return (api_key, api_secret) exclusively for request signing, or None."""
    return _find_credential_pair()


def api_version() -> str:
    return os.getenv(DEFAULT_API_VERSION_ENV, "").strip() or DEFAULT_API_VERSION


def _signature_string(method: str, path: str, date_value: str, nonce: str | None) -> str:
    signature_string = f"(request-target): {method.lower()} {path}\ndate: {date_value}"
    if nonce:
        signature_string += f"\nnonce: {nonce}"
    return signature_string


def build_signature(api_secret: str, method: str, path: str, date_value: str,
                     nonce: str | None) -> str:
    """HMAC-SHA256(api_secret, signing_string) -> base64 -> URL-escaped.

    Matches `dnse.api.common.build_signature` for algorithm="hmac-sha256".
    The secret is used only as the HMAC key; it is never included in the
    output.
    """
    mac = hmac.new(api_secret.encode("utf-8"),
                    _signature_string(method, path, date_value, nonce).encode("utf-8"),
                    hashlib.sha256)
    encoded = base64.b64encode(mac.digest()).decode("utf-8")
    # Matches the SDK's own escaping (urllib.parse.quote, safe="").
    from urllib.parse import quote
    return quote(encoded, safe="")


def auth_headers(api_key: str, api_secret: str, method: str, path: str) -> dict[str, str]:
    """Build the signed request headers for one call. `path` excludes the
    query string, matching the official signing scheme exactly."""
    date_value = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
    nonce = uuid.uuid4().hex
    signature = build_signature(api_secret, method, path, date_value, nonce)
    signature_header = (
        f'Signature keyId="{api_key}",algorithm="hmac-sha256",'
        f'headers="(request-target) date",signature="{signature}",nonce="{nonce}"'
    )
    return {
        "Date": date_value,
        "X-Signature": signature_header,
        "x-api-key": api_key,
        "version": api_version(),
    }


def safe_error_code(error: BaseException) -> str:
    """A bounded error identity; exception messages may embed request detail."""
    return type(error).__name__


def sanitize_url(value: str) -> str:
    """Redact any token-like query parameter. Defense in depth: DNSE credentials
    travel in headers, never in the query string, but this keeps the guarantee
    true even if a future endpoint changes that."""
    parts = urlsplit(str(value))
    safe_query = [
        (key, _REDACTED if any(tag in key.lower() for tag in _SENSITIVE_KEY_SUBSTRINGS) else item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_query), parts.fragment))


def redact_value(value: Any) -> Any:
    """Recursively redact any dict value whose key looks credential-shaped.

    A falsy value (None, 0, "", False, empty list) under a sensitive-shaped
    key is passed through unredacted rather than replaced with "<redacted>":
    there is no secret to hide in an absent value, and several DNSE
    pagination fields (e.g. `nextPageToken`) use exactly that falsy value to
    signal "no further pages" -- a fact this qualification pilot needs to
    observe. A genuinely populated value under the same key is still fully
    redacted.
    """
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if any(tag in key_str.lower() for tag in _SENSITIVE_KEY_SUBSTRINGS) and item:
                out[key_str] = _REDACTED
            else:
                out[key_str] = redact_value(item)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    return value


def scrub_text(text: str, *secrets: str) -> str:
    """Last-resort literal scrub of known credential values from free text.
    Structural avoidance (never constructing a printable string that contains
    them) is the primary guarantee; this is defense in depth only."""
    result = text
    for secret in secrets:
        if secret:
            result = result.replace(secret, _REDACTED)
    return result


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Never actually printed by the probe, but kept available/tested so any
    future diagnostic path has a safe default rather than a raw dict."""
    return {
        key: (_REDACTED if any(tag in key.lower() for tag in _SENSITIVE_KEY_SUBSTRINGS) else value)
        for key, value in headers.items()
    }
