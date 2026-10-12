"""Fail-closed projection of official corporate actions for price continuity tests."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

PRICE_TEST_ACTION_TYPES = {"stock_dividend", "bonus_share", "stock_split"}


def _event_hash(event: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def official_event_id(event: Mapping[str, Any], ratio: float) -> str:
    """Deterministic identity owned by the official evidence, never by a provider ID."""
    evidence = event.get("evidence") if isinstance(event.get("evidence"), Mapping) else {}
    source = event.get("official_source_id") or evidence.get("source_url") or evidence.get("evidence_id")
    payload = {"official_source": source, "document_sha256": evidence.get("document_sha256"),
               "ticker": event.get("ticker"), "exchange": event.get("exchange"),
               "event_type": event.get("event_type"), "ex_date": event.get("ex_date"),
               "ratio": ratio, "ratio_basis": event.get("ratio_basis")}
    return "official-ca-" + _event_hash(payload)


def project_price_test_events(entries: list[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Project only direct, official action evidence into price-test events.

    A price-continuity test does not require share-transition completion or a
    provider corporate-action ID. It requires direct official event evidence,
    one unambiguous ex-date, and a direct ratio basis.
    """
    accepted: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    candidates: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        evidence = entry.get("evidence") if isinstance(entry.get("evidence"), Mapping) else {}
        event_type = entry.get("event_type")
        ex_date = entry.get("ex_date")
        ratio = entry.get("entitlement_ratio")
        provider = entry.get("provider")
        provider_version = entry.get("provider_version")
        provider_event_id = entry.get("provider_event_id")
        event_id = entry.get("canonical_event_id") or entry.get("event_id")
        base = {"event_id": event_id, "ticker": entry.get("ticker"), "event_type": event_type}
        if event_type not in PRICE_TEST_ACTION_TYPES:
            excluded.append({**base, "reason": "event_type_not_price_test_eligible"})
        elif entry.get("exchange") != "HOSE":
            excluded.append({**base, "reason": "exchange_identity_missing_or_unsupported"})
        elif not ex_date or entry.get("ratio_basis") != "new_shares_per_existing_share" or not isinstance(ratio, Mapping) or not isinstance(ratio.get("ratio_float"), (int, float)) or ratio["ratio_float"] < 0.10:
            excluded.append({**base, "reason": "qualified_ex_date_or_ratio_missing"})
        elif not (entry.get("official_source_id") or evidence.get("source_url") or evidence.get("evidence_id")) or not evidence.get("citation_id") or not evidence.get("document_sha256") or not entry.get("retrieved_at"):
            excluded.append({**base, "reason": "official_citation_or_source_hash_missing"})
        else:
            candidate = {**base, "canonical_event_id": official_event_id(entry, ratio["ratio_float"]),
                         "provider": provider, "provider_version": provider_version,
                         "provider_event_id": provider_event_id, "exchange": "HOSE", "ex_date": ex_date,
                         "entitlement_ratio": ratio["ratio_float"], "ratio_basis": "new_shares_per_existing_share",
                         "source_field_identities": entry.get("source_field_identities", {}),
                         "citation": evidence, "qualified_for_price_basis_test": True,
                         "qualified_for_share_transition": bool(entry.get("qualified_for_share_transition", False))}
            candidates[(provider, provider_version, provider_event_id)].append(candidate)
    for identity, duplicates in sorted(candidates.items()):
        hashes = {_event_hash(item) for item in duplicates}
        if len(hashes) != 1:
            excluded.append({"provider": identity[0], "provider_version": identity[1], "provider_event_id": identity[2], "reason": "duplicate_identity_conflicting_payload"})
        else:
            accepted.append(duplicates[0])
    return {"accepted": sorted(accepted, key=lambda item: (item["ticker"], item["ex_date"], item["event_id"] or "")),
            "excluded": sorted(excluded, key=lambda item: (item.get("ticker") or "", item.get("event_id") or "", item["reason"]))}
