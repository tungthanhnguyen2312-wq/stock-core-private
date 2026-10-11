"""Typed insider-transaction and major-holder observations from retained HNX disclosures.

WHAT THIS IS
    The event-derivation layer over `hnx_disclosure_feed_parser.parse_disclosure_detail`,
    mirroring `corporate_action_events.py`'s shape: a pure function of one already-retained,
    hash-identified document's parsed fields to one typed, citation-bearing observation. It
    computes no new facts -- every number it reports was already a field in `parse_disclosure_detail`'s
    output; this module only classifies the document's *state* and packages the citation.

WHY REGISTERED AND EXECUTED NEVER DERIVE EACH OTHER
    A registration notice states an intention (`registered_buy_volume`); a result notice states
    what happened (`executed_buy_volume`), and Vietnamese disclosure practice does not guarantee
    a result notice repeats the original registered figure -- when it does (observed on HNX
    2026-08-22 for VNF), both are read as two independently labelled facts from the *same*
    document, never as one implying the other. `derive_transaction_state` only ever reads
    fields that are actually present; it does not look up a prior registration document to fill
    a gap, and a missing field stays `None` (i.e. absent from the record), never becomes 0.

STATE VOCABULARY
    `REGISTERED_BUY`, `REGISTERED_SELL`, `EXECUTED_BUY`, `EXECUTED_SELL`, `PARTIALLY_EXECUTED`,
    `NOT_EXECUTED`, `UNKNOWN` -- the exact set the milestone names. A result notice with an
    explicit executed volume of zero is `NOT_EXECUTED`, never dropped and never confused with a
    missing field.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

VERSION = "1.0.0"

REGISTERED_BUY, REGISTERED_SELL = "REGISTERED_BUY", "REGISTERED_SELL"
EXECUTED_BUY, EXECUTED_SELL = "EXECUTED_BUY", "EXECUTED_SELL"
PARTIALLY_EXECUTED, NOT_EXECUTED, UNKNOWN = "PARTIALLY_EXECUTED", "NOT_EXECUTED", "UNKNOWN"

CEASED_MAJOR_HOLDER = "CEASED_MAJOR_HOLDER"
BECAME_MAJOR_HOLDER = "BECAME_MAJOR_HOLDER"
UNKNOWN_MAJOR_HOLDER_EVENT = "UNKNOWN_MAJOR_HOLDER_EVENT"


def _shares(fields: Mapping[str, Any], key: str) -> float | None:
    entry = fields.get(key)
    return entry.get("shares") if isinstance(entry, Mapping) else None


def derive_transaction_state(fields: Mapping[str, Any]) -> tuple[str, str]:
    """(state, reason) from whichever registered/executed fields this document actually states."""
    registered_buy, registered_sell = _shares(fields, "registered_buy_volume"), _shares(fields, "registered_sell_volume")
    executed_buy, executed_sell = _shares(fields, "executed_buy_volume"), _shares(fields, "executed_sell_volume")

    if executed_buy is not None or executed_sell is not None:
        side, executed, registered = (
            ("BUY", executed_buy, registered_buy) if executed_buy is not None
            else ("SELL", executed_sell, registered_sell))
        if executed == 0:
            return NOT_EXECUTED, f"executed_{side.lower()}_volume is explicitly 0"
        if registered is not None:
            if executed < registered:
                return PARTIALLY_EXECUTED, f"executed {executed:g} of registered {registered:g}"
            return (EXECUTED_BUY if side == "BUY" else EXECUTED_SELL), \
                f"executed {executed:g} >= registered {registered:g} stated in this document"
        return (EXECUTED_BUY if side == "BUY" else EXECUTED_SELL), \
            f"executed_{side.lower()}_volume stated; no registered volume in this document to compare"

    if registered_buy is not None:
        return REGISTERED_BUY, "registered_buy_volume stated; no execution result in this document"
    if registered_sell is not None:
        return REGISTERED_SELL, "registered_sell_volume stated; no execution result in this document"
    return UNKNOWN, "neither a registered nor an executed volume field was recognised in this document"


def derive_major_holder_state(fields: Mapping[str, Any]) -> tuple[str, str]:
    ceased = fields.get("ceased_major_holder_date")
    became = fields.get("became_major_holder_date")
    if isinstance(ceased, Mapping) and ceased.get("raw"):
        return CEASED_MAJOR_HOLDER, "ceased_major_holder_date stated in this document"
    if isinstance(became, Mapping) and became.get("raw"):
        return BECAME_MAJOR_HOLDER, "became_major_holder_date stated in this document"
    return UNKNOWN_MAJOR_HOLDER_EVENT, "neither a ceased- nor a became-major-holder date was recognised"


def _actor_identity(detail: Mapping[str, Any]) -> dict[str, Any]:
    fields = detail.get("fields") or {}
    if fields.get("actor_individual_name"):
        return {"actor_kind": "individual", "actor_name": fields["actor_individual_name"],
               "actor_relationship": "insider" if fields.get("actor_position_at_issuer") else "UNKNOWN",
               "actor_position_at_issuer": fields.get("actor_position_at_issuer")}
    if fields.get("actor_entity_name"):
        return {"actor_kind": "entity", "actor_name": fields["actor_entity_name"],
               "actor_relationship": "related_person_entity" if detail.get("related_persons") else "UNKNOWN",
               "actor_position_at_issuer": None}
    return {"actor_kind": "UNKNOWN", "actor_name": None, "actor_relationship": "UNKNOWN",
           "actor_position_at_issuer": None}


def citation_id(document_id: str, content_sha256: str, field_path: str) -> str:
    return hashlib.sha256(f"hnx_disclosure|{document_id}|{content_sha256}|{field_path}".encode()).hexdigest()


def build_insider_transaction_observation(*, document_id: str, content_sha256: str, source_url: str,
                                          published_at: str | None, detail: Mapping[str, Any]) -> dict[str, Any]:
    """One typed, citation-bearing insider-transaction observation from one retained document.

    `related_persons` is carried verbatim (possibly empty): a notice naming four related
    persons stays four named records, never collapsed into "some related persons".
    """
    fields = dict(detail.get("fields") or {})
    state, state_reason = derive_transaction_state(fields)
    identity = _actor_identity(detail)
    citations = detail.get("citations") or {}
    field_citations = {key: citation_id(document_id, content_sha256, f"fields.{key}")
                       for key in fields if key in citations}
    return {
        "schema_version": VERSION,
        "observation_type": "insider_transaction_observation/v1",
        "document_id": document_id,
        "document_sha256": content_sha256,
        "source_url": source_url,
        "title": detail.get("title"),
        "published_at_raw": published_at,
        "ticker": detail.get("ticker"),
        **identity,
        "related_persons": list(detail.get("related_persons") or []),
        "state": state,
        "state_reason": state_reason,
        "registered_buy_volume": fields.get("registered_buy_volume"),
        "registered_sell_volume": fields.get("registered_sell_volume"),
        "executed_buy_volume": fields.get("executed_buy_volume"),
        "executed_sell_volume": fields.get("executed_sell_volume"),
        "ownership_before": fields.get("shares_held_before"),
        "ownership_after": fields.get("shares_held_after"),
        "non_execution_reason": fields.get("non_execution_reason"),
        "registration_window": {"start": fields.get("registration_start_date"),
                                "end": fields.get("registration_end_date")},
        "execution_window": {"start": fields.get("execution_window_start_date"),
                             "end": fields.get("execution_window_end_date")},
        "purpose": fields.get("purpose"),
        "method": fields.get("method"),
        "unparsed_fields": list(detail.get("unparsed_fields") or []),
        "extraction_complete": bool(detail.get("extraction_complete")),
        "field_citations": field_citations,
        "warnings": (["ticker_not_recognised_in_this_document"] if not detail.get("ticker") else [])
                   + (["fields_present_this_regex_table_does_not_map"]
                      if detail.get("unparsed_fields") else []),
    }


def build_major_holder_observation(*, document_id: str, content_sha256: str, source_url: str,
                                   published_at: str | None, detail: Mapping[str, Any]) -> dict[str, Any]:
    fields = dict(detail.get("fields") or {})
    state, state_reason = derive_major_holder_state(fields)
    identity = _actor_identity(detail)
    return {
        "schema_version": VERSION,
        "observation_type": "major_holder_observation/v1",
        "document_id": document_id,
        "document_sha256": content_sha256,
        "source_url": source_url,
        "title": detail.get("title"),
        "published_at_raw": published_at,
        "ticker": detail.get("ticker"),
        "holder_name": identity["actor_name"],
        "holder_kind": identity["actor_kind"],
        "state": state,
        "state_reason": state_reason,
        "event_date": fields.get("ceased_major_holder_date") or fields.get("became_major_holder_date"),
        "ownership_before": fields.get("shares_held_before"),
        "ownership_after": fields.get("shares_held_after"),
        "executed_buy_volume": fields.get("executed_buy_volume"),
        "executed_sell_volume": fields.get("executed_sell_volume"),
        "unparsed_fields": list(detail.get("unparsed_fields") or []),
        "extraction_complete": bool(detail.get("extraction_complete")),
        "warnings": (["ticker_not_recognised_in_this_document"] if not detail.get("ticker") else []),
    }
