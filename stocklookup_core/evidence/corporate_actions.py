"""Fail-closed canonical projection of bounded VCI corporate-event observations."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


COVERAGE = "partial_unqualified_50_row_cap"


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool): return None
    try: number = float(value)
    except (TypeError, ValueError): return None
    return int(number) if number.is_integer() else number


def _kind(event: Mapping[str, Any]) -> str | None:
    code = _text(event.get("event_code"))
    title = " ".join(filter(None, (_text(event.get("event_name_en")), _text(event.get("event_title_en")), _text(event.get("event_name_vi")), _text(event.get("event_title_vi"))))).lower()
    if code == "DIV" and ("cash dividend" in title or "tiền mặt" in title): return "cash_dividend"
    if code == "ISS" and ("stock dividend" in title or "cổ tức bằng cổ phiếu" in title): return "stock_dividend"
    if code == "ISS" and ("bonus issue" in title or "cổ phiếu thưởng" in title): return "bonus_issue"
    if code == "ISS" and ("rights issue" in title or "quyền mua" in title): return "rights_issue"
    return None


def canonicalize_corporate_actions(events: Sequence[Mapping[str, Any]], *, coverage_status: str, provenance: Mapping[str, Any]) -> dict[str, Any]:
    """Project only identifiable observed actions; no lifecycle or adjustment inference."""
    if coverage_status != COVERAGE:
        return {"status": "unavailable", "records": [], "reason": "coverage_status_unqualified"}
    ids: set[str] = set(); records: list[dict[str, Any]] = []
    for event in events:
        event_id = _text(event.get("provider_event_id") or event.get("id"))
        if not event_id or event_id in ids:
            return {"status": "malformed", "records": [], "reason": "missing_or_duplicate_provider_event_id"}
        ids.add(event_id)
        kind = _kind(event)
        if kind is None: continue
        raw_amount, raw_ratio = _number(event.get("value_per_share")), _number(event.get("exercise_ratio"))
        if event.get("value_per_share") is not None and raw_amount is None or event.get("exercise_ratio") is not None and raw_ratio is None:
            return {"status": "malformed", "records": [], "reason": "malformed_amount_or_ratio"}
        records.append({
            "provider_event_id": event_id, "action_type": kind,
            "date_roles": {name: event.get(name) for name in ("public_date", "record_date", "exright_date", "issue_date", "payout_date", "listing_date")},
            "cash_dividend_per_share": raw_amount if kind == "cash_dividend" else None,
            "cash_dividend_currency": None, "cash_dividend_unit": "per_share" if kind == "cash_dividend" and raw_amount is not None else None,
            "issue_ratio": raw_ratio if kind in {"stock_dividend", "bonus_issue", "rights_issue"} else None,
            "ratio_meaning": "provider_decimal_ratio_as_stated_in_event_title" if kind in {"stock_dividend", "bonus_issue", "rights_issue"} and raw_ratio is not None else None,
            "issue_price": None, "lifecycle_status": "unknown",
            "source_fields": {"event_code": event.get("event_code"), "category": event.get("category"), "event_name_vi": event.get("event_name_vi"), "event_name_en": event.get("event_name_en"), "event_title_vi": event.get("event_title_vi"), "event_title_en": event.get("event_title_en"), "action_type_vi": event.get("action_type_vi"), "action_type_en": event.get("action_type_en"), "value_per_share": event.get("value_per_share"), "exercise_ratio": event.get("exercise_ratio")},
            "provenance": dict(provenance), "coverage_status": coverage_status,
            "adjustment_provenance": "unqualified_no_price_adjustment_claim",
        })
    return {"status": "partial" if records else "unavailable", "records": records,
            "reason": "partial_forward_observations" if records else "no_identifiable_qualified_action"}
