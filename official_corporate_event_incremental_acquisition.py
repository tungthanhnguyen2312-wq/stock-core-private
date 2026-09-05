"""Incremental, versioned, idempotent acquisition for official HNX/HOSE corporate-event evidence.

OFFICIAL_CORPORATE_EVENT_INCREMENTAL_ACQUISITION_AND_FRESHNESS_V1.

Reuses the exact existing, already-approved first-party acquisition mechanisms
(``hnx_enumerable_universe_kllh_event_disclosure_scaleout.build()``,
``hose_public_xhr_and_periodic_series_recon.build()``) rather than inventing a new fetch method,
provider, or crawler. This module adds exactly the piece that did not exist: an explicit
acquisition-session wrapper that retains raw evidence content-addressed and immutable (never
overwritten -- both underlying modules already fail closed on ``IMMUTABLE_CONTENT_CONFLICT``),
classifies each retained surface as unchanged-and-reused or new-and-versioned relative to the
prior successful attempt, and resolves the deterministic latest successful session so
``current_official_event_context`` can be materialized fresh instead of forever from one frozen
2026-08-24 snapshot.

Does not infer ex-dates, execution status, or missing dates -- current_official_event_context.py's
own fail-closed contract is reused unmodified. Does not merge the two PIT/price-adjustment ledgers
(corporate_action_ledger.py, official_corporate_action_ledger.py), which remain out of this
module's scope entirely. Does not add a new provider: HNX (hnx.vn) and HOSE (api.hsx.vn) are the
same two public, unauthenticated, first-party surfaces already used by the prior 2026-08-24
acquisition.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import hnx_enumerable_universe_kllh_event_disclosure_scaleout as hnx_module
import hose_public_xhr_and_periodic_series_recon as hose_module
from vn_time import vn_now_iso, vn_today

CONTRACT_VERSION = "official_corporate_event_incremental_acquisition/v1"
RAW_STORE_RELATIVE = Path("operations-review") / "official-corporate-event-raw-store"
SESSIONS_RELATIVE = Path("operations-review") / "official-corporate-event-acquisition-sessions"
ATTEMPT_FILENAME = "acquisition_attempt.json"
BREADTH_FOUNDATION_PREFIX = "current-market-universe-breadth-foundation-v1-"

SUCCESS = "SUCCESS"
FAILURE = "FAILURE"
UNCHANGED_REUSED = "UNCHANGED_REUSED"
CHANGED_NEW_VERSION = "CHANGED_NEW_VERSION"
NEW_SURFACE_OR_PAGE = "NEW_SURFACE_OR_PAGE"


class IncrementalAcquisitionError(ValueError):
    """A retained input did not meet this acquisition's exact contract."""


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _self_verified(payload: Mapping[str, Any], identity_prefix: str) -> dict[str, Any]:
    """A minimal artifact shell satisfying this codebase's existing generic ``_verify()``
    self-consistency check (artifact_sha256 matches the canonicalized payload; artifact_identity
    ends with that hash) -- reused, not a new identity scheme -- for the small derived bridge
    views this module needs between two modules whose native shapes otherwise disagree."""
    body = dict(payload)
    digest = hashlib.sha256(_canonical(body)).hexdigest()
    body["artifact_sha256"] = digest
    body["artifact_identity"] = f"{identity_prefix}:{digest}"
    return body


def _latest_dated_directory(ops: Path, prefix: str) -> Path | None:
    """The lexicographically latest ``{ops}/{prefix}{...}`` directory, or None if none exist.
    Dated suffixes (``YYYYMMDD`` or ``YYYY-MM-DD``) sort correctly as strings."""
    candidates = sorted((p for p in ops.glob(f"{prefix}*") if p.is_dir()), key=lambda p: p.name)
    return candidates[-1] if candidates else None


def resolve_stocklookup_universe(root: Path) -> Path:
    """The freshest retained ``current_market_universe_breadth_foundation`` artifact -- a
    genuinely daily-refreshed input, unlike the frozen HNX/HOSE snapshots this milestone repairs
    -- used only for its 1683-ticker denominator, per both acquisition modules' own existing
    contract. Universe-membership freshness itself is a separate, already-labelled, out-of-scope
    policy (``ACCEPTED_CURRENT_ASOF_BUILD_NOT_SESSION_LOCKED``); this module does not change it."""
    ops = root / "operations-review"
    latest = _latest_dated_directory(ops, BREADTH_FOUNDATION_PREFIX)
    if latest is None:
        raise IncrementalAcquisitionError("STOCKLOOKUP_UNIVERSE_ARTIFACT_UNAVAILABLE")
    return latest / "current_market_universe_breadth_foundation_artifact.json"


def _session_dir(root: Path, session: str) -> Path:
    return root / SESSIONS_RELATIVE / session


def latest_successful_session(root: Path) -> dict[str, Any] | None:
    """The most recent retained acquisition attempt with ``disposition=SUCCESS``, skipping any
    failed attempts -- a failure is retained explicitly (mission Section 11) but never treated as
    a usable snapshot for downstream materialization."""
    sessions_root = root / SESSIONS_RELATIVE
    if not sessions_root.is_dir():
        return None
    for candidate in sorted((p for p in sessions_root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
        attempt = _load(candidate / ATTEMPT_FILENAME)
        if attempt is not None and attempt.get("disposition") == SUCCESS:
            return attempt
    return None


def compare_captures(prior_captures: Sequence[Mapping[str, Any]] | None,
                      new_captures: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Pure, network-free comparison of two capture lists by content hash, so idempotence and
    versioning can be validated entirely from retained fixtures (mission Section 13: no repeated
    network acquisition needed to prove this). A (surface, page) pair absent from the prior
    attempt is a new surface; present with the same sha256 is reused unchanged; present with a
    different sha256 is a new version. Never overwrites -- both underlying acquisition modules'
    own immutable ``_atomic()`` writers already guarantee that at the raw-file level; this is the
    session-level record of what that meant for this attempt."""
    prior_by_key = {(str(c["surface"]), c.get("page")): str(c["sha256"]) for c in (prior_captures or [])}
    new_by_key = {(str(c["surface"]), c.get("page")): str(c["sha256"]) for c in new_captures}
    classification: dict[str, str] = {}
    for key, new_hash in new_by_key.items():
        label = f"{key[0]}:{key[1]}"
        prior_hash = prior_by_key.get(key)
        classification[label] = (
            NEW_SURFACE_OR_PAGE if prior_hash is None
            else UNCHANGED_REUSED if prior_hash == new_hash
            else CHANGED_NEW_VERSION
        )
    removed = sorted(f"{k[0]}:{k[1]}" for k in (set(prior_by_key) - set(new_by_key)))
    return {
        "per_surface_page": classification,
        "removed_surfaces_or_pages": removed,
        "any_change": any(value != UNCHANGED_REUSED for value in classification.values()) or bool(removed),
        "unchanged_count": sum(value == UNCHANGED_REUSED for value in classification.values()),
        "new_or_changed_count": sum(value != UNCHANGED_REUSED for value in classification.values()),
    }


def _hnx_bridge(hnx_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """hnx_module.build()'s native shape (top-level hnx_official_equity_universe/rights_event_index/
    disclosure_index keys, each with its own "records" list) does not match what either
    hose_module.build()'s hnx_universe reader or current_official_event_context.build_artifact()'s
    hnx reader expect (both want a top-level "datasets" dict keyed by dataset id, plus the original
    "captures" list for source_identity/retrieved_at lookup). This bridges the shape without
    changing either module's own tested output contract -- a real, previously-unexercised gap:
    hnx_module.build()'s own output had never actually been fed into either consumer end to end
    before (the 2026-08-24 setup instead used tools/materialize_hnx_enumerable_universe_artifact.py's
    separate reparse-only path, which happens to already emit the "datasets" shape)."""
    return _self_verified({
        "captures": hnx_artifact["captures"],
        "datasets": {
            "hnx_official_equity_universe/v1": hnx_artifact["hnx_official_equity_universe"]["records"],
            "hnx_official_rights_event_index/v1": hnx_artifact["rights_event_index"]["records"],
        },
    }, "official_corporate_event_incremental_acquisition:hnx_bridge")


def acquire(root: Path, *, session: str | None = None, execute: bool = True, hose_fetcher=None,
            include_hnx_disclosures: bool = False) -> dict[str, Any]:
    """One bounded acquisition attempt over the existing, approved HNX + HOSE public source
    contracts -- no new provider, no crawler, no retry loop (mission Section 12). Raw evidence is
    retained content-addressed and immutable by the underlying modules' own writers; this function
    adds only the session wrapper, change classification against the prior successful attempt, and
    explicit failure retention (never a silent swallow, never a retry). Never overwrites a prior
    session's own manifest -- a second call for the same session raises rather than re-acquiring
    over it.

    ``include_hnx_disclosures`` defaults to False: a real 2026-09-05 acquisition attempt found the
    HNX disclosure-index endpoints (unlike the rights-event index this module actually needs) carry
    no date-range parameter, so a full walk re-fetches the entire historical corpus every time --
    441+ pages as of that real attempt, which failed partway through
    (SOURCE_FETCH_FAILED:hnx_listed_disclosures:441). current_official_event_context.py's own
    contract never reads the disclosure index, so this wrapper does not attempt it by default,
    rather than treating an unneeded, unbounded walk as a required part of every acquisition.
    """
    resolved_session = session or vn_today()
    acquired_at = vn_now_iso()
    raw_root = root / RAW_STORE_RELATIVE
    session_dir = _session_dir(root, resolved_session)
    existing = _load(session_dir / ATTEMPT_FILENAME)
    if existing is not None and existing.get("disposition") == SUCCESS:
        # A successful attempt is retained evidence and is never silently redone. A FAILED
        # attempt is not evidence of anything retained -- only of an outage -- so the same
        # calendar session may be retried (still exactly one attempt per call; the caller
        # decides whether and when to call again, this function never loops or retries itself).
        raise IncrementalAcquisitionError(f"ACQUISITION_SESSION_ALREADY_RETAINED:{resolved_session}")

    prior = latest_successful_session(root)
    attempt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "acquisition_session": resolved_session,
        "acquired_at": acquired_at,
        "prior_session_referenced": prior.get("acquisition_session") if prior else None,
    }
    try:
        stocklookup_universe = resolve_stocklookup_universe(root)
        hnx_artifact = hnx_module.build(destination=raw_root, stocklookup_universe=stocklookup_universe,
                                         execute=execute, include_disclosures=include_hnx_disclosures)
        _write(session_dir / "hnx_artifact.json", hnx_artifact)
        hnx_bridge = _hnx_bridge(hnx_artifact)
        hnx_bridge_path = session_dir / "hnx_universe_bridge.json"
        _write(hnx_bridge_path, hnx_bridge)
        hose_artifact = hose_module.build(
            destination=raw_root, stocklookup_universe=stocklookup_universe,
            hnx_universe=hnx_bridge_path, as_of_date=resolved_session,
            fetcher=hose_fetcher or hose_module.fetch,
        )
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: retain the failure explicitly rather than raising uncaught or retrying
        attempt.update({"disposition": FAILURE, "error_type": type(exc).__name__, "error_message": str(exc)})
        _write(session_dir / ATTEMPT_FILENAME, attempt)
        return attempt

    hnx_changes = compare_captures((prior or {}).get("hnx_captures"), hnx_artifact["captures"])
    hose_changes = compare_captures((prior or {}).get("hose_captures"), hose_artifact["captures"])
    attempt.update({
        "disposition": SUCCESS,
        "hnx_artifact_identity": hnx_artifact["artifact_identity"],
        "hose_artifact_identity": hose_artifact["artifact_identity"],
        "hnx_captures": hnx_artifact["captures"],
        "hose_captures": hose_artifact["captures"],
        "hnx_change_classification": hnx_changes,
        "hose_change_classification": hose_changes,
        "any_change_since_prior_success": prior is None or hnx_changes["any_change"] or hose_changes["any_change"],
        "stocklookup_universe_path": str(stocklookup_universe.relative_to(root)).replace("\\", "/"),
    })
    _write(session_dir / ATTEMPT_FILENAME, attempt)
    _write(session_dir / "hose_artifact.json", hose_artifact)
    return attempt


def materialize_current_official_event_context(
    root: Path, *, acquisition_session: str | None = None, official_universe_path: Path | None = None,
) -> dict[str, Any]:
    """Deterministic latest/current snapshot materialization (mission Section 5): by default,
    resolve the latest SUCCESSFUL acquisition session and build a fresh current_official_event_
    context artifact from it, bound to that session's own acquisition date -- never today's
    calendar date if that differs from when the evidence was actually acquired, and never a
    fabricated date. An explicit ``acquisition_session`` instead targets exactly that retained
    session's own artifacts (never "latest"), which is what makes a genuine historical temporal
    replay possible: materializing session S can only ever see what session S's own acquisition
    attempt actually retained, never a later session's newly-discovered evidence, structurally
    ruling out future-knowledge leakage rather than merely checking for it after the fact (mission
    Sections 14-15). Writes to the exact directory-naming convention
    daily_session_level2_package._latest_official_event_context_dir() already scans for, so the
    canonical Daily pipeline picks up the latest one with zero additional wiring changes."""
    import current_official_event_context as event_context_module

    if acquisition_session is not None:
        attempt = _load(_session_dir(root, acquisition_session) / ATTEMPT_FILENAME)
        if attempt is None or attempt.get("disposition") != SUCCESS:
            raise IncrementalAcquisitionError(f"ACQUISITION_SESSION_NOT_SUCCESSFUL:{acquisition_session}")
        session = acquisition_session
    else:
        latest = latest_successful_session(root)
        if latest is None:
            raise IncrementalAcquisitionError("NO_SUCCESSFUL_ACQUISITION_SESSION_RETAINED")
        session = latest["acquisition_session"]
    session_dir = _session_dir(root, session)
    hnx_artifact = _load(session_dir / "hnx_artifact.json")
    hose_artifact = _load(session_dir / "hose_artifact.json")
    if hnx_artifact is None or hose_artifact is None:
        raise IncrementalAcquisitionError(f"ACQUISITION_SESSION_ARTIFACTS_MISSING:{session}")
    hnx_bridge = _hnx_bridge(hnx_artifact)

    official_universe_path = official_universe_path or (
        root / "operations-review" / "current-official-market-universe-integration-v1-20260824"
        / "current_official_market_universe_artifact.json"
    )
    official_universe = _load(official_universe_path)
    if official_universe is None:
        raise IncrementalAcquisitionError("OFFICIAL_UNIVERSE_ARTIFACT_UNAVAILABLE")

    context = event_context_module.build_artifact(
        official_universe=official_universe, hnx=hnx_bridge, hose=hose_artifact, research_session=session,
    )
    event_context_module.replay(context)

    nodash = session.replace("-", "")
    out_dir = root / "operations-review" / f"current-official-event-context-integration-v1-{nodash}"
    out_path = out_dir / "current_official_event_context_artifact.json"
    _write(out_path, context)
    return {"acquisition_session": session, "output_path": str(out_path.relative_to(root)).replace("\\", "/"),
            "artifact_identity": context["artifact_identity"], "coverage": context["coverage"]}
