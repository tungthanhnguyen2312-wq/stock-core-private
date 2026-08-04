"""Official sources that *could* one day qualify market-volume composition. None active.

WHY A SEPARATE REGISTRY
    `official_source_registry.py` gates the network. Its `hose` entry is `approved`, for a
    finite list of corporate-action document types, and `admit()` will happily let a caller
    through if a document type is added to that list. Registering "HOSE trading statistics"
    there would therefore be one JSON edit away from becoming a scraper -- in a milestone
    that is explicitly forbidden from acquiring anything.

    So the candidate lives here instead, in a module that performs no I/O, imports nothing
    that can open a socket, and records no URL. A candidate is a *question list*, not an
    address. `assert_not_acquirable()` proves the separation holds by checking the network
    registry does not admit the candidate's document types.

WHAT THE HOSE CANDIDATE IS AND IS NOT
    HOSE publicly distinguishes matched-order from negotiated (put-through) trading in its
    published statistics. That distinction is precisely the one the VCI closeout found
    absent from all 96 observed fields, and it is why the exchange is the preferred path.

    Nothing about those pages has been acquired, fetched, parsed, licensed or qualified.
    Whether a per-ticker, machine-readable, historically-covering, reusable form exists is
    an open question -- one of eight recorded below -- not an assumption. A future,
    separately authorized milestone answers them. This one records them.

    "Preferred currently identified official authority path" is the deliberate wording.
    HOSE is the best candidate anyone here has identified; calling it the only theoretically
    possible authority would be a claim about sources nobody has surveyed.
"""

from __future__ import annotations

from typing import Any, Mapping

VERSION = "1.0.0"

STATUS_FUTURE_CANDIDATE = "future_qualification_candidate"
STATUS_ACTIVE = "active_qualified_source"

#: A candidate is never active. Written as a constant so the distinction is enforced rather
#: than remembered.
CANDIDATE_STATUSES = frozenset({STATUS_FUTURE_CANDIDATE})

AUTHORITY_POSITION = "preferred_currently_identified_official_authority_path"


class AuthorityCandidateError(ValueError):
    """Fail-closed refusal in the candidate registry."""


HOSE_TRADING_STATISTICS: dict[str, Any] = {
    "candidate_id": "hose_trading_statistics",
    "source": "HOSE",
    "authority": "official_exchange",
    "authority_name": "Ho Chi Minh City Stock Exchange",
    "authority_position": AUTHORITY_POSITION,
    "status": STATUS_FUTURE_CANDIDATE,
    "automatic_acquisition_authorized": False,
    "acquisition_state": "nothing_acquired",
    # Deliberately absent: url, endpoint, host, path, api_route. No exact authoritative URL
    # for these statistics has been observed and preserved in this repository, and a URL
    # written from memory is a fabricated locator regardless of how plausible it looks.
    "locator": None,
    "locator_note": (
        "No URL recorded. None has been observed and retained. A future milestone must "
        "obtain the locator from an operator-supplied or observed source, not compose one."
    ),
    "why_this_candidate": (
        "HOSE publicly distinguishes categories that the VCI closeout proved are absent "
        "from every observed VCI surface: matched-order trading statistics, negotiated or "
        "put-through trading statistics, and end-of-day matched volume. Those categories "
        "are the ones that would qualify matched_trade_inclusion and negotiated_inclusion."
    ),
    "publicly_distinguished_categories": (
        "matched_order_trading_statistics",
        "negotiated_or_put_through_trading_statistics",
        "end_of_day_matched_volume",
    ),
    "categories_note": (
        "Recorded as categories the exchange is understood to distinguish publicly. Not a "
        "statement that any specific page, field or file has been located, fetched or read."
    ),
    "candidate_questions": (
        "matched volume definition",
        "negotiated volume definition",
        "relationship between matched and total volume",
        "units and scaling",
        "ticker-level availability",
        "date coverage",
        "machine-readable access",
        "access and reuse terms",
    ),
    "would_reopen": (
        "matched_trade_inclusion",
        "negotiated_inclusion",
        "odd_lot_inclusion",
        "closing_auction_inclusion",
    ),
    "would_not_reopen_by_itself": (
        "volume_corporate_action_adjustment",
    ),
    "blocking_reason_for_activation": (
        "Every one of the eight candidate questions is open. A source whose units, ticker "
        "coverage and reuse terms are unknown cannot qualify anything, and acquisition is "
        "a separately authorized decision in any case."
    ),
}

CANDIDATES: tuple[dict[str, Any], ...] = (HOSE_TRADING_STATISTICS,)

#: Document types a future acquisition would need. Listed so :func:`assert_not_acquirable`
#: has something concrete to check against the network registry -- and so that adding one
#: of these to `config/official_source_registry.json` fails a test rather than passing
#: silently.
CANDIDATE_DOCUMENT_TYPES = frozenset(
    {
        "matched_order_trading_statistics",
        "negotiated_trading_statistics",
        "end_of_day_matched_volume",
    }
)


def candidate(candidate_id: str) -> dict[str, Any]:
    for record in CANDIDATES:
        if record["candidate_id"] == candidate_id:
            return dict(record)
    raise AuthorityCandidateError(f"unknown_authority_candidate:{candidate_id}")


def active_sources() -> tuple[str, ...]:
    """No candidate is an active market-composition source. There are none."""
    return ()


def assert_candidate_only(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Refuse a candidate record that has drifted towards being a source."""
    if record.get("status") not in CANDIDATE_STATUSES:
        raise AuthorityCandidateError(f"candidate_status_invalid:{record.get('status')}")
    if record.get("automatic_acquisition_authorized"):
        raise AuthorityCandidateError("automatic_acquisition_is_not_authorized")
    if record.get("acquisition_state") != "nothing_acquired":
        raise AuthorityCandidateError(f"acquisition_claimed:{record.get('acquisition_state')}")
    if record.get("locator") is not None:
        raise AuthorityCandidateError("candidate_must_not_carry_a_locator")
    for forbidden in ("url", "endpoint", "host", "api_route", "path"):
        if forbidden in record:
            raise AuthorityCandidateError(f"candidate_must_not_carry:{forbidden}")
    if not record.get("candidate_questions"):
        raise AuthorityCandidateError("candidate_without_open_questions_is_not_a_candidate")
    if record.get("authority_position") != AUTHORITY_POSITION:
        raise AuthorityCandidateError(
            "candidate must be recorded as the preferred identified path, not the sole "
            "possible authority"
        )
    return record


def assert_not_acquirable(registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Prove the candidate cannot be fetched through the network-admitting registry.

    Reads `config/official_source_registry.json` only to inspect declared document types.
    Issues no request. If a future edit adds a trading-statistics document type to an
    approved source, this raises -- which is the point.
    """
    import official_source_registry as sources  # local import: keeps this module I/O-free

    loaded = registry if registry is not None else sources.load_registry()
    index = sources.source_index(loaded)
    collisions: list[str] = []
    for source_id, source in index.items():
        admissible = sources.admissible_document_types(source)
        overlap = CANDIDATE_DOCUMENT_TYPES & set(admissible)
        if overlap:
            collisions.append(f"{source_id}:{sorted(overlap)}")
    if collisions:
        raise AuthorityCandidateError(
            f"trading_statistics_document_types_are_admissible_somewhere:{collisions}"
        )
    return {
        "acquirable": False,
        "checked_sources": sorted(index),
        "candidate_document_types": sorted(CANDIDATE_DOCUMENT_TYPES),
        "requests_issued": 0,
    }


def registry_snapshot() -> dict[str, Any]:
    return {
        "schema_version": VERSION,
        "active_market_composition_sources": list(active_sources()),
        "candidates": [dict(record) for record in CANDIDATES],
        "automatic_acquisition_authorized": False,
        "note": (
            "Registering a candidate records what would have to be answered. It authorizes "
            "no request, and this module makes none."
        ),
    }
