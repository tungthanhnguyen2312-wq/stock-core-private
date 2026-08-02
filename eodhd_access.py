"""Secret-safe EODHD access boundary; tokens never leave this module."""
from __future__ import annotations
import os
def credential_status() -> dict[str, object]:
    return {"configured": bool(os.getenv("EODHD_API_TOKEN", "").strip()), "source": "environment", "validation_status": "not_checked"}
def token_for_request() -> str | None:
    value=os.getenv("EODHD_API_TOKEN", "").strip()
    return value or None
def sanitize(value: str) -> str:
    return value.split("?",1)[0]
