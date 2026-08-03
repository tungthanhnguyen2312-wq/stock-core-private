"""Source-governance gate for official corporate-action evidence (pillar B, step B1).

WHAT THIS IS
    The enforcement half of `config/official_source_registry.json`. Every request for an
    official document passes `admit()` first, and `admit()` answers with a decision and a
    named reason -- never with a silent pass. It performs no I/O and issues no request; it
    only decides whether one would be permitted.

WHY THE REGISTRY DEFAULTS TO REFUSING EVERYTHING
    `docs/official_corporate_action_ingestion_design.md` records that crawling official sites
    is an outward-facing action whose host allowlist, request rate and retention policy are
    **owner decisions, recorded before the first scheduled run**. So the registry ships with
    every source `declared` rather than `approved`, and `admit()` refuses a declared source.
    That makes the reviewable artifact -- the JSON -- the thing that actually gates the
    network, instead of a comment asking a future agent to be careful.

    An agent may not flip `activation` to `approved`. That is written in the registry itself
    and repeated here because it is the rule most likely to be quietly broken.

WHAT IT CHECKS, IN ORDER
    1. the source exists in the registry
    2. the source is `approved`, not merely `declared`
    3. the URL parses, is http(s), and its host is on that source's allowlist
    4. the document type is one that source is declared to publish
    5. the request honours the source's minimum interval since its own last request
    6. the approval's recorded instant is verifiable (see below)

    The instant is checked last so that a bad host, an undeclared document type or a rate
    breach still reports its own reason rather than being masked by a governance verdict.

WHY THE APPROVAL INSTANT IS CHECKED AT ALL
    `approved_at` was recorded as `2026-08-03T14:00:00Z` by a commit created at `07:22Z`,
    seven hours earlier -- the signature of a local time written with a `Z`. Whether it was
    07:00Z or 14:00Z is not something this module may decide, so it decides nothing: an
    instant in the future, or one carrying no provenance for the clock it was read from, is
    `unverified`, and `admit()` refuses. The provenance field is what makes that durable; a
    future-dated instant would otherwise become "verified" by the mere passage of time.

    Host matching is exact against the allowlist, after lower-casing and stripping a port.
    Suffix matching is deliberately not used: `evil-hnx.vn` ends with `hnx.vn` under a naive
    suffix test, and an allowlist that can be defeated by registering a domain is not one.
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

VERSION = "1.0.0"

REGISTRY_FILENAME = "official_source_registry.json"

ADMITTED = "admitted"
REFUSED = "refused"

REASON_UNKNOWN_SOURCE = "unknown_source_id"
REASON_NOT_APPROVED = "source_declared_but_not_owner_approved"
REASON_BAD_URL = "url_unparseable_or_unsupported_scheme"
REASON_HOST_NOT_ALLOWED = "host_not_on_source_allowlist"
REASON_DOCUMENT_TYPE = "document_type_not_declared_for_source"
REASON_RATE = "minimum_request_interval_not_elapsed"
REASON_APPROVAL_TIMESTAMP = "approval_instant_not_verifiable"

#: A verified approval must say which clock its instant was read from. `approved_at` alone
#: cannot distinguish an owner who approved at 14:00 UTC from one who approved at 14:00 local
#: and recorded it with a `Z`, and those are seven hours and one governance claim apart. The
#: field is required rather than inferred, because inferring it would be the agent deciding
#: what the owner meant.
APPROVAL_PROVENANCE_FIELD = "approved_at_provenance"

VERDICT_VERIFIED = "verified"
VERDICT_UNVERIFIED = "unverified"
VERDICT_PENDING = "pending"


class RegistryError(ValueError):
    """The registry file is missing, malformed, or of an unsupported schema."""


def registry_path(root: Path | str | None = None) -> Path:
    base = Path(root) if root is not None else Path(__file__).with_name("config")
    return base / REGISTRY_FILENAME


def load_registry(path: Path | str | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else registry_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RegistryError(f"registry unreadable: {target}") from exc
    except ValueError as exc:
        raise RegistryError(f"registry malformed: {target}") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != VERSION:
        raise RegistryError("registry schema unsupported")
    if not isinstance(payload.get("sources"), list):
        raise RegistryError("registry carries no source list")
    return dict(payload)


def source_index(registry: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(source["source_id"]): dict(source)
            for source in registry.get("sources") or []
            if isinstance(source, Mapping) and source.get("source_id")}


def canonical_host(url: str) -> str | None:
    """Lower-cased host with any port stripped, or None when the URL is unusable."""
    try:
        parsed = urllib.parse.urlsplit(str(url))
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    host = parsed.netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    if host.startswith("["):                      # IPv6 literal
        return host.split("]", 1)[0] + "]"
    return host.split(":", 1)[0]


def approval_instant_verdict(registry: Mapping[str, Any] | None = None, *,
                             now: datetime | None = None) -> dict[str, Any]:
    """Whether the recorded approval instant can be trusted to mean what it says.

    Three ways it cannot, each of which would otherwise activate the network path silently:

    - the state is not `APPROVED` at all (`pending`);
    - the instant is in the future, so the approval it records has not happened;
    - the instant carries no provenance saying which clock it was read from.

    The provenance requirement is what makes this verdict durable. A future-dated instant
    stops being future-dated simply by waiting, so a check against the clock alone would
    turn `unverified` into `verified` with nothing having been verified.

    This adds a requirement to owner approval; it removes none. An unverified instant is
    never treated as approval, and nothing here writes to the registry.
    """
    registry = registry if registry is not None else load_registry()
    state = dict(registry.get("approval_state") or {})
    recorded = str(state.get("state") or "")
    if recorded.upper() != "APPROVED":
        return {"verdict": VERDICT_PENDING, "reason": "approval_state_is_not_approved",
                "approved_at": state.get("approved_at"), "state": recorded}

    raw = state.get("approved_at")
    instant = _parse_instant(raw)
    if instant is None:
        return {"verdict": VERDICT_UNVERIFIED, "reason": "approved_at_missing_or_unparseable",
                "approved_at": raw, "state": recorded}

    evaluated_at = now or datetime.now(timezone.utc)
    if instant > evaluated_at:
        return {"verdict": VERDICT_UNVERIFIED, "reason": "approved_at_is_in_the_future",
                "approved_at": raw, "state": recorded,
                "evaluated_at": evaluated_at.isoformat(),
                "detail": ("an approval cannot be recorded before it happens; a UTC instant "
                           "ahead of the clock is the signature of a local time written "
                           "with a 'Z'")}

    provenance = state.get(APPROVAL_PROVENANCE_FIELD)
    if not (isinstance(provenance, str) and provenance.strip()):
        return {"verdict": VERDICT_UNVERIFIED, "reason": "approved_at_has_no_clock_provenance",
                "approved_at": raw, "state": recorded,
                "detail": (f"{APPROVAL_PROVENANCE_FIELD!r} is absent, so nothing records "
                           "whether the instant was read from a UTC or a local clock. Only "
                           "the owner may supply it.")}

    return {"verdict": VERDICT_VERIFIED, "reason": "approval_instant_carries_clock_provenance",
            "approved_at": raw, "state": recorded, APPROVAL_PROVENANCE_FIELD: provenance}


def _parse_instant(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def admit(source_id: str, url: str, document_type: str, *,
          registry: Mapping[str, Any] | None = None,
          seconds_since_last_request: float | None = None,
          now: datetime | None = None) -> dict[str, Any]:
    """Whether one request would be permitted, with a named reason either way."""
    registry = registry if registry is not None else load_registry()
    sources = source_index(registry)
    source = sources.get(str(source_id))
    if source is None:
        return _decision(REFUSED, REASON_UNKNOWN_SOURCE, source_id, url, document_type,
                         detail=f"{source_id!r} is not declared in the registry")
    if str(source.get("activation")) != "approved":
        return _decision(REFUSED, REASON_NOT_APPROVED, source_id, url, document_type,
                         detail=("the registry declares this source but the owner has not "
                                 "approved it; approval is recorded in the registry and in "
                                 "docs/DECISIONS.md, never set by an agent"))
    host = canonical_host(url)
    if host is None:
        return _decision(REFUSED, REASON_BAD_URL, source_id, url, document_type,
                         detail="only absolute http(s) URLs with a host are admissible")
    allowed = {str(entry).lower() for entry in source.get("allowed_hosts") or []}
    if host not in allowed:
        return _decision(REFUSED, REASON_HOST_NOT_ALLOWED, source_id, url, document_type,
                         detail=f"host {host!r} is not on the {source_id} allowlist")
    if str(document_type) not in {str(entry) for entry in source.get("document_types") or []}:
        return _decision(REFUSED, REASON_DOCUMENT_TYPE, source_id, url, document_type,
                         detail=f"{document_type!r} is not declared for {source_id}")
    interval = float(source.get("min_request_interval_seconds") or 0.0)
    if (seconds_since_last_request is not None
            and float(seconds_since_last_request) < interval):
        return _decision(REFUSED, REASON_RATE, source_id, url, document_type,
                         detail=(f"{seconds_since_last_request:.2f}s since the last "
                                 f"{source_id} request; the declared minimum is {interval}s"))
    # Last, so that a bad host, an undeclared document type or a rate breach still reports
    # its own specific reason. This check governs only whether anything may be admitted.
    instant = approval_instant_verdict(registry, now=now)
    if instant["verdict"] != VERDICT_VERIFIED:
        return _decision(REFUSED, REASON_APPROVAL_TIMESTAMP, source_id, url, document_type,
                         detail=(f"the approval instant is {instant['verdict']} "
                                 f"({instant['reason']}); an approval whose recorded instant "
                                 "cannot be read is not one this gate will act on"))
    return _decision(ADMITTED, "admitted_by_registry", source_id, url, document_type,
                     detail=f"host {host!r} and document type are declared and approved",
                     policy={
                         "connect_timeout_seconds": registry["global_policy"]["connect_timeout_seconds"],
                         "read_timeout_seconds": registry["global_policy"]["read_timeout_seconds"],
                         "max_attempts": registry["global_policy"]["max_attempts"],
                         "max_response_bytes": registry["global_policy"]["max_response_bytes"],
                         "min_request_interval_seconds": interval,
                         "user_agent": registry["global_policy"]["user_agent"],
                         "parser_version": source.get("parser_version"),
                     })


def _decision(decision: str, reason: str, source_id: Any, url: Any, document_type: Any,
              *, detail: str, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "decision": decision,
        "reason": reason,
        "detail": detail,
        "source_id": str(source_id),
        "url": str(url),
        "document_type": str(document_type),
        "registry_version": VERSION,
        "policy": dict(policy or {}),
    }


def approved_source_ids(registry: Mapping[str, Any] | None = None) -> list[str]:
    registry = registry if registry is not None else load_registry()
    return sorted(source_id for source_id, source in source_index(registry).items()
                  if str(source.get("activation")) == "approved")


def registry_summary(registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    registry = registry if registry is not None else load_registry()
    sources = source_index(registry)
    return {
        "policy_version": registry.get("policy_version"),
        "approval_state": dict(registry.get("approval_state") or {}),
        "approval_instant": approval_instant_verdict(registry),
        "source_count": len(sources),
        "approved_source_ids": approved_source_ids(registry),
        "declared_source_ids": sorted(
            source_id for source_id, source in sources.items()
            if str(source.get("activation")) != "approved"),
        "excluded_sources": [dict(entry) for entry in
                             (registry.get("global_policy") or {}).get("excluded_sources") or []],
        "allowed_host_count": sum(len(source.get("allowed_hosts") or [])
                                  for source in sources.values()),
    }
