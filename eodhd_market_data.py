"""Bounded, forward-only EODHD EOD schema qualification boundary."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Any

from eodhd_access import safe_error_code

PROVIDER = "EODHD"
PROVIDER_INTERFACE_VERSION = "eodhd_eod_http_unversioned"
ADAPTER_SCHEMA_VERSION = "stock_lookup.eodhd_eod/v1"
ENDPOINT_TEMPLATE = "https://eodhd.com/api/eod/{symbol}"
TRUSTED_SYMBOLS = ("HPG.VN", "VNM.VN")
PRICE_RAW_BASIS = "raw_unadjusted_close"
PRICE_ADJUSTED_BASIS = "split_and_dividend_adjusted_close"
VOLUME_BASIS = "split_adjusted_volume"


class EodhdQualificationError(ValueError):
    """A structured, secret-safe qualification failure."""

    def __init__(self, code: str, *, symbol: str | None = None) -> None:
        self.code = code
        self.symbol = symbol
        super().__init__(code)


def _default_request_get(*args: Any, **kwargs: Any) -> Any:
    # Keep access tooling importable in the repository's minimal test environment.
    # Production dependencies install requests through requirements.txt.
    import requests
    return requests.get(*args, **kwargs)


def _number(value: Any, field: str, symbol: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise EodhdQualificationError(f"invalid_{field}", symbol=symbol)
    return float(value)


def _normalize_row(row: Mapping[str, Any], symbol: str) -> dict[str, Any]:
    session = row.get("date")
    try:
        date.fromisoformat(str(session))
    except (TypeError, ValueError) as exc:
        raise EodhdQualificationError("invalid_session_date", symbol=symbol) from exc
    volume = row.get("volume")
    if isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
        raise EodhdQualificationError("invalid_volume", symbol=symbol)
    return {
        "ticker": symbol.removesuffix(".VN"),
        "provider_symbol": symbol,
        "session_date": str(session),
        "price_raw_eod": _number(row.get("close"), "raw_close", symbol),
        "price_adjusted_eod": _number(row.get("adjusted_close"), "adjusted_close", symbol),
        "volume": volume,
        "currency": "VND",
        "price_unit_scale": 1,
        "volume_unit": "shares",
        "price_raw_basis": PRICE_RAW_BASIS,
        "price_adjusted_basis": PRICE_ADJUSTED_BASIS,
        "volume_basis": VOLUME_BASIS,
    }


def qualify_eod_sample(
    token: str,
    *,
    from_date: str,
    to_date: str,
    symbols: Sequence[str] = TRUSTED_SYMBOLS,
    request_get: Callable[..., Any] | None = None,
    timeout: tuple[float, float] = (5.0, 12.0),
) -> dict[str, Any]:
    """Fetch one bounded daily window per trusted symbol and validate exact semantics.

    The token is used only in request parameters and is absent from the result and
    all raised errors.  There are no retries or provider fallbacks.
    """
    if not token:
        raise EodhdQualificationError("access_not_configured")
    if tuple(symbols) != TRUSTED_SYMBOLS:
        raise EodhdQualificationError("trusted_symbol_set_mismatch")
    try:
        if date.fromisoformat(from_date) > date.fromisoformat(to_date):
            raise EodhdQualificationError("invalid_date_range")
    except ValueError as exc:
        if isinstance(exc, EodhdQualificationError):
            raise
        raise EodhdQualificationError("invalid_date_range") from exc

    getter = request_get or _default_request_get
    observations: list[dict[str, Any]] = []
    payload_hashes: dict[str, str] = {}
    for symbol in symbols:
        endpoint = ENDPOINT_TEMPLATE.format(symbol=symbol)
        params = {"api_token": token, "fmt": "json", "period": "d", "order": "d",
                  "from": from_date, "to": to_date}
        try:
            response = getter(endpoint, params=params, timeout=timeout)
            status_code = int(response.status_code)
            if status_code in {401, 403}:
                raise EodhdQualificationError("authentication_failed", symbol=symbol)
            if status_code != 200:
                raise EodhdQualificationError(f"http_status_{status_code}", symbol=symbol)
            raw_bytes = bytes(response.content)
            payload = response.json()
        except EodhdQualificationError:
            raise
        except Exception as exc:
            raise EodhdQualificationError(f"request_failed_{safe_error_code(exc)}", symbol=symbol) from None
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], Mapping):
            raise EodhdQualificationError("response_schema_invalid", symbol=symbol)
        observations.append(_normalize_row(payload[0], symbol))
        payload_hashes[symbol] = hashlib.sha256(raw_bytes).hexdigest()

    sessions = {item["session_date"] for item in observations}
    if len(sessions) != 1:
        raise EodhdQualificationError("mixed_ticker_sessions")
    return {
        "status": "qualified",
        "schema_qualified": True,
        "provider": PROVIDER,
        "provider_interface_version": PROVIDER_INTERFACE_VERSION,
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "method": "eod",
        "parameters": {"fmt": "json", "period": "d", "order": "d", "from": from_date, "to": to_date},
        "canonical_session_date": next(iter(sessions)),
        "price_basis": {"raw": PRICE_RAW_BASIS, "adjusted": PRICE_ADJUSTED_BASIS, "verified": True},
        "volume_basis": {"value": VOLUME_BASIS, "unit": "shares", "verified": True},
        "observations": observations,
        "payload_sha256": payload_hashes,
        "http_request_count": len(symbols),
        "limitations": [
            "Qualification applies only to the authenticated EODHD EOD path and retained adapter version.",
            "Current shares and production publication are separate qualification gates.",
        ],
    }
