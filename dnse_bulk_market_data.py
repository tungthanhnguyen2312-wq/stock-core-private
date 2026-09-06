"""Bulk-safe DNSE OpenAPI market-data request boundary -- full-fidelity twin of
``dnse_market_data.request_capability``.

WHY A SEPARATE FUNCTION INSTEAD OF REUSING ``request_capability``
    ``dnse_market_data.request_capability`` is a *qualification-probe* tool: its
    result is meant to be safe to print, log, and drop into a Markdown
    evidence file, so it runs every response through ``_bound_large_lists``,
    which replaces any list longer than 20 items with a
    ``{"list_truncated": True, "sample_first": [...5], "sample_last": [...2]}``
    summary. That is the right behavior for a human-readable probe result and
    the wrong one for raw ingestion: a paginated ``/market/instruments`` page
    (up to ~100 rows) or an OHLC window (dozens to hundreds of bars) would be
    silently reduced to 7 sample rows before it ever reached the raw lake --
    an evidence-redaction gap already hit once before in this project (see
    ``operations-review/dnse-bid-ask-foreign-flow-qualification-20260810``,
    "20-item evidence-redaction truncation trap"). This module exists so bulk
    ingestion can never repeat that mistake structurally: it shares the exact
    same allowlist, auth, and GET-only contract as ``dnse_market_data.py``
    (imported, not duplicated), but returns the complete, untruncated response
    body under the key ``body`` -- a different key name from
    ``request_capability``'s ``body_redacted`` on purpose, so the two are
    never accidentally interchangeable.

WHAT IS AND ISN'T REDACTED HERE
    Request headers, the signature, and the API key/secret are still never
    part of the returned result (matching ``request_capability``), and a
    transport exception is still collapsed to ``safe_error_code`` only, never
    its message. But the *response body* itself is returned exactly as the
    provider sent it, with no key-based redaction pass either: every endpoint
    reachable through ``MARKET_DATA_ENDPOINTS`` is a read-only public
    market-data GET (never account/order/position data), a signed HTTP
    request's signature is never echoed back into a JSON response body, and
    the raw lake's own contract (``market_data_contracts.RawObservation``)
    requires unmodified provenance -- redacting the payload here would
    silently corrupt the one thing raw retention promises to preserve.

Zero automatic retries, exactly like ``request_capability``: a caller doing
bulk work owns its own retry/backoff policy (see ``market_raw_lake.py`` /
``tools/bulk_ingest_dnse_raw.py``), so a transient failure is reported once
per call, not retried invisibly underneath the orchestrator counting attempts.
"""
from __future__ import annotations

import time
import math
from collections.abc import Callable, Mapping
from typing import Any

from dnse_access import BASE_URL, auth_headers, safe_error_code
from dnse_market_data import MARKET_DATA_ENDPOINTS, DnseProbeError, resolve_endpoint

PROVIDER = "DNSE"
PROVIDER_INTERFACE_VERSION = "dnse_openapi_rest_unversioned_2026"

__all__ = [
    "DnseProbeError",
    "MARKET_DATA_ENDPOINTS",
    "PROVIDER",
    "PROVIDER_INTERFACE_VERSION",
    "fetch_capability_raw",
    "is_retryable",
    "resolve_endpoint",
]


def _default_request_get(*args: Any, **kwargs: Any) -> Any:
    import requests

    return requests.get(*args, **kwargs)


def _retry_after_seconds(response: Any) -> float | None:
    """Return a usable numeric Retry-After value without retaining headers.

    The bulk caller applies its own configured sleep cap.  This boundary only
    exposes a finite, non-negative delta-seconds value, never an arbitrary
    response-header collection or a provider quota claim.
    """
    headers = getattr(response, "headers", None)
    try:
        raw = headers.get("Retry-After") if headers is not None else None
        value = float(str(raw).strip())
    except (AttributeError, TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def fetch_capability_raw(
    capability: str,
    *,
    api_key: str,
    api_secret: str,
    symbol: str | None = None,
    query: Mapping[str, Any] | None = None,
    request_get: Callable[..., Any] | None = None,
    timeout: tuple[float, float] = (5.0, 15.0),
) -> dict[str, Any]:
    """Issue exactly one signed, read-only GET call and return its full body.

    Returns a sanitized *metadata* envelope in every case (success, HTTP
    error, or transport failure) -- never raises. ``result["body"]`` is
    present only when ``ok`` is true and is the provider's response exactly
    as received (after JSON decoding), with no truncation or redaction.
    """
    path = resolve_endpoint(capability, symbol)
    headers = auth_headers(api_key, api_secret, "GET", path)
    url = f"{BASE_URL}{path}"
    getter = request_get or _default_request_get
    started = time.monotonic()
    result: dict[str, Any] = {
        "capability": capability,
        "family": MARKET_DATA_ENDPOINTS[capability]["family"],
        "endpoint": path,
        "provider": PROVIDER,
        "provider_interface_version": PROVIDER_INTERFACE_VERSION,
        "query_sent": dict(query or {}),
    }
    try:
        response = getter(url, params=dict(query or {}), headers=headers, timeout=timeout)
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
        status_code = int(response.status_code)
        result["http_status"] = status_code
        if status_code in (401, 403):
            result.update(ok=False, error_code="authentication_failed")
            return result
        if status_code == 429:
            result.update(ok=False, error_code="rate_limited")
            retry_after = _retry_after_seconds(response)
            if retry_after is not None:
                result["retry_after_seconds"] = retry_after
            return result
        if status_code != 200:
            result.update(ok=False, error_code=f"http_status_{status_code}")
            try:
                result["body"] = response.json()
            except Exception:
                result["body_text_preview"] = str(getattr(response, "text", "") or "")[:2000]
            return result
        result["ok"] = True
        result["body"] = response.json()
        return result
    except Exception as exc:  # noqa: BLE001 - record, never raise, transport failures
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
        result.update(ok=False, error_code=f"request_failed_{safe_error_code(exc)}")
        return result


def is_retryable(result: Mapping[str, Any]) -> bool:
    """True for a transient failure a caller may reasonably retry.

    Deliberately excludes ``authentication_failed`` (retrying with the same
    credentials cannot succeed -- the whole run should stop, not retry) and
    any ``http_status_4xx`` other than 429 (a malformed request/unknown
    symbol will not change on retry). Only rate limiting and transport-level
    failures (timeouts, connection errors) are retryable.
    """
    if result.get("ok"):
        return False
    error_code = str(result.get("error_code", ""))
    return error_code == "rate_limited" or error_code.startswith("request_failed_")
