"""Bounded, allowlist-only DNSE OpenAPI market-data request boundary.

Every capability in MARKET_DATA_ENDPOINTS is GET-only and was copied from the
official `dnse-tech/openapi-sdk` Python client's own method list (read
2026-08-10, `python/dnse/api/client.py`). Account, balance, position, order,
trading-token, OTP, and broker endpoints are deliberately absent from this
dict, so `request_capability()` cannot reach them structurally -- there is no
code path that accepts an arbitrary path or a non-GET method.

This module performs no retries. A transport or HTTP-level failure is
returned as a structured, sanitized result, never raised and never allowed to
carry credential material in its message.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from dnse_access import BASE_URL, auth_headers, redact_value, safe_error_code

PROVIDER = "DNSE"
PROVIDER_INTERFACE_VERSION = "dnse_openapi_rest_unversioned_2026"

MARKET_DATA_ENDPOINTS: dict[str, dict[str, Any]] = {
    "security_definition": {"path": "/price/{symbol}/secdef", "requires_symbol": True, "family": "security_master"},
    "instruments": {"path": "/market/instruments", "requires_symbol": False, "family": "security_master"},
    "working_dates": {"path": "/market/working-dates", "requires_symbol": False, "family": "trading_calendar"},
    "trading_session": {"path": "/market/trading-session", "requires_symbol": False, "family": "trading_calendar"},
    "ohlc": {"path": "/price/ohlc", "requires_symbol": False, "family": "ohlc_history"},
    "trades_latest": {"path": "/price/{symbol}/trades/latest", "requires_symbol": True, "family": "trades"},
    "trades_history": {"path": "/price/{symbol}/trades", "requires_symbol": True, "family": "trades"},
    "quotes_latest": {"path": "/price/{symbol}/quotes/latest", "requires_symbol": True, "family": "bid_ask"},
    "quotes_history": {"path": "/price/{symbol}/quotes", "requires_symbol": True, "family": "bid_ask"},
    "expected_price": {"path": "/price/{symbol}/expected-price", "requires_symbol": True, "family": "current_market"},
    "foreign_trading": {"path": "/price/{symbol}/foreign-trading", "requires_symbol": True, "family": "foreign_flow"},
    "close_price": {"path": "/price/{symbol}/close", "requires_symbol": True, "family": "current_market"},
}


class DnseProbeError(ValueError):
    """Raised only for allowlist violations -- a bug in the caller's own call
    plan, not a network/HTTP condition. Deliberately never raised for a live
    request's outcome, so a qualification run always finishes and reports."""

    def __init__(self, code: str, *, capability: str | None = None) -> None:
        self.code = code
        self.capability = capability
        super().__init__(code)


def resolve_endpoint(capability: str, symbol: str | None = None) -> str:
    spec = MARKET_DATA_ENDPOINTS.get(capability)
    if spec is None:
        raise DnseProbeError("unknown_capability", capability=capability)
    if spec["requires_symbol"]:
        if not symbol:
            raise DnseProbeError("symbol_required", capability=capability)
        return spec["path"].format(symbol=symbol)
    return spec["path"]


def _default_request_get(*args: Any, **kwargs: Any) -> Any:
    # Deliberately more conservative than the vendor SDK's own example client,
    # which disables TLS certificate verification (cert_reqs='CERT_NONE') --
    # `requests.get` verifies by default and this module never overrides that.
    import requests
    return requests.get(*args, **kwargs)


def request_capability(
    capability: str,
    *,
    api_key: str,
    api_secret: str,
    symbol: str | None = None,
    query: Mapping[str, Any] | None = None,
    request_get: Callable[..., Any] | None = None,
    timeout: tuple[float, float] = (5.0, 15.0),
) -> dict[str, Any]:
    """Issue exactly one signed, read-only GET call for `capability`.

    Returns a sanitized result dict in every case (success, HTTP error, or
    transport failure). Never includes request headers, the signature, or
    credential material. Zero automatic retries.
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
            return result
        if status_code != 200:
            result.update(ok=False, error_code=f"http_status_{status_code}")
            try:
                result["body_redacted"] = _bounded_redacted_body(response)
            except Exception:
                pass
            return result
        result["ok"] = True
        result["body_redacted"] = _bounded_redacted_body(response)
        return result
    except Exception as exc:  # noqa: BLE001 - record, never raise, transport failures
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
        result.update(ok=False, error_code=f"request_failed_{safe_error_code(exc)}")
        return result


def _bound_large_lists(value: Any, *, max_items: int = 20) -> Any:
    """Recursively cap any list longer than max_items, preserving its exact
    length and a small sample -- so sibling fields (a response's `total`,
    `page`, or a security's other attributes) never get lost to truncation
    the way a flat string-preview cutoff would lose them."""
    if isinstance(value, Mapping):
        return {k: _bound_large_lists(v, max_items=max_items) for k, v in value.items()}
    if isinstance(value, list):
        if len(value) > max_items:
            return {
                "list_truncated": True,
                "item_count": len(value),
                "sample_first": [_bound_large_lists(v, max_items=max_items) for v in value[:5]],
                "sample_last": [_bound_large_lists(v, max_items=max_items) for v in value[-2:]],
            }
        return [_bound_large_lists(v, max_items=max_items) for v in value]
    return value


def _bounded_redacted_body(response: Any, *, max_chars: int = 6000) -> Any:
    try:
        payload = response.json()
    except Exception:
        text = getattr(response, "text", "") or ""
        return {"non_json_body_preview": str(text)[:max_chars]}
    redacted = _bound_large_lists(redact_value(payload))
    serialized = json.dumps(redacted, sort_keys=True, default=str)
    if len(serialized) <= max_chars:
        return redacted
    # Last-resort defensive cap for pathological cases list-bounding didn't catch.
    return {"truncated": True, "preview": serialized[:max_chars]}


def top_level_schema(body_redacted: Any) -> Any:
    """A bounded structural fingerprint for the capability matrix: keys for an
    object, or a length/sample-keys descriptor for a list. Never values."""
    if isinstance(body_redacted, Mapping):
        if body_redacted.get("truncated"):
            return body_redacted
        return sorted(str(k) for k in body_redacted.keys())
    if isinstance(body_redacted, list):
        if body_redacted and isinstance(body_redacted[0], Mapping):
            return sorted(str(k) for k in body_redacted[0].keys())
        return f"list[{len(body_redacted)}]"
    return type(body_redacted).__name__
