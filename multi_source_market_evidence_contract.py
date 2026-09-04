"""Normalized per-source exact-session observation contract and resolution policy.

Serves CURRENT RESEARCH / DAILY PRODUCT MODE only -- never Audit/PIT/Execution Mode.
Pure and deterministic: no network, no filesystem, no database. Callers (
``multi_source_exact_session_resolver.py``) own all I/O and provider dispatch; this
module only normalizes what a provider returned and decides what the evidence means.

WHY A SEPARATE CONTRACT MODULE
    ``mva_exact_session_snapshot.py`` (DNSE) and ``vn_stock_pipeline.py`` (VCI/KBS)
    each already own their own provider-specific fetch/normalize logic -- this module
    does not duplicate either. It defines the one shared shape both get projected
    into (``SourceObservation``) and the one shared policy for turning a ticker's
    collected observations (usually exactly one, sometimes more) into a resolved
    verdict (``resolve_ticker``).

DOCTRINE
    NOT_AUTHORITATIVE != NOT_USABLE. A resolved observation may support Current
    Research when session/source/normalization/provenance/fitness/conflicts are all
    explicit -- exactly the fields this contract requires. Strict/PIT/RAW_AS_TRADED
    uses remain fail-closed regardless of resolution outcome; see ``authority_boundary``
    in every artifact this powers.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

try:
    from vci_direct_basis_pilot import VCIPilotError, hose_tick_size
except ImportError:  # pragma: no cover - defensive; module is always present in this repo
    class VCIPilotError(ValueError):
        pass

    def hose_tick_size(price_vnd: float) -> int:  # type: ignore[misc]
        if price_vnd <= 0:
            raise VCIPilotError("tick_size_undefined_for_non_positive_price")
        if price_vnd < 10_000:
            return 10
        if price_vnd < 50_000:
            return 50
        return 100

CONTRACT_VERSION = "multi_source_market_evidence_contract/v1"

# ---------------------------------------------------------------------------
# Per-record status (exactly the six the milestone brief names -- no others).
# ---------------------------------------------------------------------------
STATUS_EXACT_SESSION_OBSERVED = "EXACT_SESSION_OBSERVED"
STATUS_SESSION_MISSING = "SESSION_MISSING"
STATUS_SOURCE_REJECTED = "SOURCE_REJECTED"
STATUS_TRANSPORT_FAILED = "TRANSPORT_FAILED"
STATUS_MALFORMED = "MALFORMED"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
OBSERVATION_STATUSES = frozenset({
    STATUS_EXACT_SESSION_OBSERVED, STATUS_SESSION_MISSING, STATUS_SOURCE_REJECTED,
    STATUS_TRANSPORT_FAILED, STATUS_MALFORMED, STATUS_NOT_APPLICABLE,
})

# ---------------------------------------------------------------------------
# Per-ticker resolution outcome (the milestone brief's A/B/C/D semantics).
# ---------------------------------------------------------------------------
RESOLUTION_CORROBORATED = "RESOLVED_CORROBORATED"
RESOLUTION_SINGLE_SOURCE = "RESOLVED_SINGLE_SOURCE_RESEARCH"
RESOLUTION_CONFLICT = "SOURCE_CONFLICT"
# A ticker where DNSE, VCI, and KBS were ALL observed, VCI and KBS materially agree with each
# other, and DNSE materially conflicts with both. Session-date equality alone (DNSE returning
# *an* exact-session bar) never proves DNSE's bar is the right one -- this milestone's own
# 2026-09-03 qualification found DNSE's own MWG/GMD bars diverging from VCI/KBS on low/close and
# volume, consistent with DNSE's snapshot possibly predating ATC-auction settlement for at least
# some sessions. When two independent sources corroborate each other against DNSE, the resolved
# Current Research value uses the corroborated non-DNSE basis instead of naively preferring DNSE
# by tie-break order -- never RAW_AS_TRADED, never PIT authority, and the DNSE observation is
# always retained unchanged in the full evidence record (see resolve_ticker below).
RESOLUTION_CORROBORATED_NON_DNSE = "RESOLVED_CORROBORATED_NON_DNSE_CURRENT_RESEARCH"
RESOLUTION_ALL_MISSING = "SESSION_MISSING_ALL_SOURCES"
RESOLUTION_OUTCOMES = frozenset({
    RESOLUTION_CORROBORATED, RESOLUTION_SINGLE_SOURCE, RESOLUTION_CONFLICT,
    RESOLUTION_CORROBORATED_NON_DNSE, RESOLUTION_ALL_MISSING,
})

# ---------------------------------------------------------------------------
# DNSE same-date provider-health classification (bounded sentinel cohort only --
# see multi_source_exact_session_resolver.select_sentinel_cohort). A ticker having an
# exact-session-dated DNSE bar is coverage, not quality; these states are about whether
# DNSE's own values, on days it DOES return a bar, actually agree with corroborated VCI/KBS.
# ---------------------------------------------------------------------------
DNSE_HEALTH_EXACT_AND_CORROBORATED = "DNSE_EXACT_AND_CORROBORATED"
DNSE_HEALTH_EXACT_BUT_UNCORROBORATED = "DNSE_EXACT_BUT_UNCORROBORATED"
DNSE_HEALTH_MATERIAL_CONFLICT = "DNSE_MATERIAL_CONFLICT"
DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD = "DNSE_BROAD_STALE_OR_INCOMPLETE_EOD"
DNSE_HEALTH_STATES = frozenset({
    DNSE_HEALTH_EXACT_AND_CORROBORATED, DNSE_HEALTH_EXACT_BUT_UNCORROBORATED,
    DNSE_HEALTH_MATERIAL_CONFLICT, DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD,
})

# Fraction of DNSE-assessable sentinel tickers (DNSE observed AND at least one of VCI/KBS also
# observed) found in conflict at/above which the pattern is treated as provider-wide/systemic
# rather than isolated to specific names. Chosen so that a couple of known isolated tickers --
# this milestone's own real MWG/GMD finding, 2 names -- never by themselves trip the broad/
# systemic classification, while a genuinely widespread same-date-but-wrong-value pattern does.
# A majority-of-assessed threshold is the simplest bound that separates those two real shapes;
# it is not a claim of statistical significance over an arbitrarily small sentinel.
DNSE_BROAD_CONFLICT_RATIO_THRESHOLD = 0.5

# A ratio alone is unreliable at tiny sample sizes: a sentinel with exactly one DNSE-assessable
# ticker in conflict is 100% by ratio but is definitionally "a couple of isolated names," not
# "provider-wide." BROAD_STALE_OR_INCOMPLETE_EOD additionally requires at least this many
# DNSE-assessable sentinel tickers -- below it, even a high conflict ratio stays classified as
# MATERIAL_CONFLICT (still surfaced, never silently dropped, just not overclaimed as systemic).
DNSE_BROAD_MIN_ASSESSED_COUNT = 5

# Deterministic tie-break / preferred-value order when more than one source has an
# EXACT_SESSION_OBSERVED value for the same ticker (used to populate the single
# legacy-shaped observation row a CORROBORATED/CONFLICT ticker still needs; the full
# per-source evidence is never discarded -- see multi_source_exact_session_resolver.py).
# DNSE stays preferred per the milestone's explicit SOURCE_PREFERENCE section (it
# remains the established current-market source); VCI is vn_stock_pipeline.py's own
# existing PRIMARY_SRC ahead of its FAILOVER_SRC KBS. This is a tie-break only, never
# a claim that the preferred source's value is more correct -- a genuine cross-source
# price difference is reported via cross_source_conflict, not silently hidden by it.
SOURCE_PREFERENCE_ORDER = ("DNSE", "VCI", "KBS")

# Native price unit per source, established from this project's own retained evidence:
# DNSE's P3F9B close is retained provider-native/undocumented-unit (mva_exact_session_
# snapshot.py never scales it; docs/DECISIONS.md's DNSE_UNIFORM_OHLC_ANCHOR_QUALIFICATION_V1
# treats it as the anchor representation as-is). VCI/KBS via vn_stock_pipeline.py are
# empirically confirmed "thousand VND" (vn_stock_pipeline.SOURCE_SCALES = {"VCI": 1000,
# "KBS": 1000}, 2026-07 verification note in that module). This module never re-derives
# either finding; it only applies them.
NATIVE_PRICE_UNIT_SCALE = {"DNSE": 1, "VCI": 1000, "KBS": 1000}

# A price agreement stricter than "close enough to be the same matched print": more than
# this many HOSE order-price ticks apart is a genuine, economically real difference (see
# hose_tick_size), not float/rounding noise from the x1000 VCI/KBS scale conversion (which
# is exact for clean decimal quotes). HOSE tick size is this repository's only existing
# tick-size contract (vci_direct_basis_pilot.hose_tick_size); it is used here as a general
# bound across exchanges rather than inventing a separate arbitrary percentage tolerance.
PRICE_AGREEMENT_MAX_TICKS = 1

# Cross-source price agreement is checked on each observation's NATIVE value, never its
# NATIVE_PRICE_UNIT_SCALE-derived `normalized`. This milestone's own 2026-09-03 qualification
# empirically confirmed DNSE's undocumented-unit raw quote and VCI/KBS's own native (pre-VND-
# scale) quote share the same real-world magnitude for a given bar (e.g. both ~74 for the same
# MWG print -- see vci_kbs_qualification_20260903.json's own target_session_row_native). Their
# `normalized` fields do NOT share a magnitude: DNSE stays at its raw undocumented scale (~74,
# NATIVE_PRICE_UNIT_SCALE["DNSE"]=1, deliberately never asserted to be literal VND -- see
# DNSE_UNIFORM_OHLC_ANCHOR_QUALIFICATION_V1) while VCI/KBS are confirmed-scaled to literal VND
# (~74000). Comparing `normalized` fields directly would show every DNSE-vs-VCI/KBS pair as
# wildly "conflicting" by construction, regardless of whether the real prices agree -- this is
# not a hypothetical: it was caught here, before any live validation, by tracing exactly this
# arithmetic against real 2026-09-03 data. hose_tick_size's own breakpoints are calibrated for
# literal-VND magnitudes, so the native-scale reference is scaled up only to select the right
# tick bracket, then the resulting tick tolerance is scaled back down to native units -- this
# is mathematically equivalent to the original normalized-vs-normalized check whenever both
# sides already share one scale (e.g. VCI vs KBS), and only changes behavior for the
# DNSE-vs-VCI/KBS case this fix targets.
_NATIVE_COMPARISON_VND_SCALE = 1000

# Cross-provider-FAMILY volume is never assumed comparable (see module docstring on the
# empirical ~30x DNSE-vs-VCI/KBS 2026-09-03 gap this milestone's own qualification probe
# found -- consistent with DNSE's snapshot potentially predating ATC-auction settlement
# for at least some sessions/tickers). Only WITHIN the vnstock family (VCI vs KBS, which
# this project's own probes have observed returning identical volumes) is a volume
# comparison meaningful.
VOLUME_COMPARABLE_SOURCE_FAMILIES = (frozenset({"VCI", "KBS"}),)


class MultiSourceEvidenceError(ValueError):
    """A caller violated this contract's own invariants (never a provider-data problem)."""


def _price_fields_agree(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Compare two observations' NATIVE open/high/low/close (see _NATIVE_COMPARISON_VND_SCALE
    above for why native, never normalized_vnd, is the scale-correct comparison basis)."""
    for field in ("open", "high", "low", "close"):
        va, vb = a.get(field), b.get(field)
        if va is None or vb is None:
            return False
        try:
            va, vb = float(va), float(vb)
        except (TypeError, ValueError):
            return False
        reference = max(abs(va), abs(vb), 1.0)
        try:
            tick = hose_tick_size(reference * _NATIVE_COMPARISON_VND_SCALE) / _NATIVE_COMPARISON_VND_SCALE
        except VCIPilotError:
            tick = 1.0 / _NATIVE_COMPARISON_VND_SCALE
        if abs(va - vb) > PRICE_AGREEMENT_MAX_TICKS * tick:
            return False
    return True


def _volume_comparable(source_a: str, source_b: str) -> bool:
    family = frozenset({source_a, source_b})
    return any(family <= allowed for allowed in VOLUME_COMPARABLE_SOURCE_FAMILIES)


def _volumes_agree(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    va, vb = a.get("volume"), b.get("volume")
    if va is None or vb is None:
        return False
    try:
        return int(va) == int(vb)
    except (TypeError, ValueError):
        return False


def build_source_observation(
    *,
    ticker: str,
    requested_session: str,
    observed_session: str | None,
    source: str,
    provider_interface: str,
    retrieved_at: str,
    status: str,
    native: Mapping[str, Any] | None = None,
    unit_scale: int | None = None,
    price_basis: str = "CURRENT_DESCRIPTIVE_NOT_PROMOTED_RAW_AS_TRADED",
    fitness: str = "CURRENT_RESEARCH_DESCRIPTIVE_ONLY",
    provenance: Mapping[str, Any] | None = None,
    payload_hash: str | None = None,
    reason_code: str | None = None,
) -> dict[str, Any]:
    """Build one normalized SourceObservation record.

    ``native`` (when present) carries the provider's own-unit open/high/low/close/volume;
    ``normalized`` is always derived here by applying ``unit_scale`` -- callers never
    hand-compute the VND-normalized fields themselves, so the one conversion formula
    lives in exactly one place.
    """
    if status not in OBSERVATION_STATUSES:
        raise MultiSourceEvidenceError(f"UNKNOWN_OBSERVATION_STATUS:{status}")
    scale = unit_scale if unit_scale is not None else NATIVE_PRICE_UNIT_SCALE.get(source, 1)
    normalized = None
    if status == STATUS_EXACT_SESSION_OBSERVED and native is not None:
        try:
            normalized = {
                "open_vnd": float(native["open"]) * scale,
                "high_vnd": float(native["high"]) * scale,
                "low_vnd": float(native["low"]) * scale,
                "close_vnd": float(native["close"]) * scale,
                "volume": int(native["volume"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise MultiSourceEvidenceError(f"NATIVE_FIELDS_INCOMPLETE_FOR_OBSERVED_STATUS:{ticker}:{source}") from exc
    return {
        "ticker": ticker,
        "requested_session": requested_session,
        "observed_session": observed_session,
        "source": source,
        "provider_interface": provider_interface,
        "retrieved_at": retrieved_at,
        "native": dict(native) if native is not None else None,
        "native_price_unit": f"{source}_NATIVE_SCALE_{scale}" if native is not None else None,
        "normalized": normalized,
        "normalization_method": "identity_scale_multiply/v1" if normalized is not None else None,
        "unit_scale": scale,
        "price_basis": price_basis,
        "fitness": fitness,
        "provenance": dict(provenance) if provenance is not None else {},
        "payload_hash": payload_hash,
        "status": status,
        "reason_code": reason_code,
    }


def resolve_ticker(ticker: str, observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Reduce one ticker's collected per-source observations to a resolved verdict.

    ``observations`` should include one entry per source that was actually attempted
    for this ticker (NOT_APPLICABLE entries for sources never queried are welcome and
    preserved in the caller's full evidence artifact, but do not affect this function's
    outcome). Never mutates its input.
    """
    observed = [o for o in observations if o.get("status") == STATUS_EXACT_SESSION_OBSERVED]
    if not observed:
        return {
            "ticker": ticker,
            "resolution": RESOLUTION_ALL_MISSING,
            "resolved_source": None,
            "resolved_normalized": None,
            "cross_source_conflict": False,
            "cross_source_volume_comparability": "NOT_APPLICABLE_NO_OBSERVED_SOURCE",
            "contributing_sources": [o.get("source") for o in observations],
        }
    if len(observed) == 1:
        winner = observed[0]
        return {
            "ticker": ticker,
            "resolution": RESOLUTION_SINGLE_SOURCE,
            "resolved_source": winner["source"],
            "resolved_normalized": winner["normalized"],
            "cross_source_conflict": False,
            "cross_source_volume_comparability": "NOT_APPLICABLE_SINGLE_SOURCE",
            "contributing_sources": [winner["source"]],
        }
    # Two or more sources independently observed the exact target session.
    price_conflict = False
    volume_status = "NOT_ESTABLISHED"
    for i in range(len(observed)):
        for j in range(i + 1, len(observed)):
            a, b = observed[i], observed[j]
            if not _price_fields_agree(a["native"], b["native"]):
                price_conflict = True
            if _volume_comparable(a["source"], b["source"]):
                volume_status = "AGREE" if _volumes_agree(a["normalized"], b["normalized"]) else "DISAGREE"
    ordered = sorted(observed, key=lambda o: SOURCE_PREFERENCE_ORDER.index(o["source"]) if o["source"] in SOURCE_PREFERENCE_ORDER else len(SOURCE_PREFERENCE_ORDER))
    preferred = ordered[0]

    # A ticker's exact-session date matching alone never proves DNSE's value is correct -- if
    # VCI and KBS were BOTH observed and materially agree with each other while DNSE conflicts
    # with them, that corroborated pair -- never DNSE's tie-break priority -- becomes the
    # resolved Current Research basis. DNSE's own observation is never dropped from `observed`/
    # `contributing_sources`; only which entry is treated as `resolved_*` changes.
    non_dnse_corroboration = None
    if price_conflict:
        by_source = {o["source"]: o for o in observed}
        dnse_ob, vci_ob, kbs_ob = by_source.get("DNSE"), by_source.get("VCI"), by_source.get("KBS")
        if dnse_ob is not None and vci_ob is not None and kbs_ob is not None and _price_fields_agree(vci_ob["native"], kbs_ob["native"]):
            non_dnse_corroboration = vci_ob  # VCI ahead of KBS per this module's own SOURCE_PREFERENCE_ORDER

    if non_dnse_corroboration is not None:
        resolution = RESOLUTION_CORROBORATED_NON_DNSE
        resolved = non_dnse_corroboration
    else:
        resolution = RESOLUTION_CONFLICT if price_conflict else RESOLUTION_CORROBORATED
        resolved = preferred
    return {
        "ticker": ticker,
        "resolution": resolution,
        "resolved_source": resolved["source"],
        "resolved_normalized": resolved["normalized"],
        "cross_source_conflict": price_conflict,
        "cross_source_volume_comparability": volume_status,
        "contributing_sources": [o["source"] for o in observed],
    }


def resolve_ticker_degraded_dnse(ticker: str, observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Re-resolve one ticker once DNSE has been classified provider-wide degraded
    (``DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD``) for this session -- see
    ``multi_source_exact_session_resolver.resolve_exact_session_with_autorecovery``, which calls
    this ONLY for a ticker whose original DNSE disposition was ``EXACT_SESSION_RETAINED``; a
    ticker DNSE never resolved anyway keeps ``resolve_ticker``'s ordinary (already DNSE-free)
    outcome unchanged.

    DNSE's own observation is NEVER a resolution candidate here -- quarantined from final
    Current Research resolution, regardless of whether a secondary source happens to agree with
    it -- while remaining fully retained as evidence: this function never inspects, mutates, or
    drops DNSE's entry from ``observations``; the caller's evidence artifact keeps it verbatim.

    Exactly four outcomes, driven ENTIRELY by VCI/KBS -- DNSE's own value is never consulted for
    the winner decision, so DNSE can never become the fallback winner in any of them:
      - VCI and KBS both ``EXACT_SESSION_OBSERVED`` and materially agree with each other
        -> RESOLVED_CORROBORATED_NON_DNSE_CURRENT_RESEARCH (VCI's value; VCI ahead of KBS per
           this module's own SOURCE_PREFERENCE_ORDER -- they agree, so which one is reported is a
           formatting choice, never a claim that one is more correct). Applies even when DNSE
           ALSO happens to agree with both -- passive agreement is not evidence DNSE is trustworthy
           for THIS session, only that this particular bar happens to match.
      - Exactly one of VCI/KBS is ``EXACT_SESSION_OBSERVED``
        -> RESOLVED_SINGLE_SOURCE_RESEARCH using that one secondary source only -- the existing
           Current Research single-source policy (see ``resolve_ticker``), just never DNSE.
      - VCI and KBS both ``EXACT_SESSION_OBSERVED`` but materially conflict with each other
        -> SOURCE_CONFLICT, unresolved (``resolved_source``/``resolved_normalized`` both None) --
           a disagreement between the only two sources this session still trusts has no justified
           resolution; never tie-broken toward either one, and never toward DNSE.
      - Neither VCI nor KBS is ``EXACT_SESSION_OBSERVED``
        -> SESSION_MISSING_ALL_SOURCES, unresolved -- DNSE having a same-dated bar is not evidence
           of anything once the provider is broadly degraded for this session.
    Every returned dict carries ``resolved_under_quarantine: True`` so
    ``multi_source_exact_session_resolver._project_to_p3f9_shape`` can label/downgrade the
    projected row correctly without re-deriving which tickers were quarantine-processed.
    """
    observed_by_source = {
        o["source"]: o for o in observations if o.get("status") == STATUS_EXACT_SESSION_OBSERVED
    }
    contributing_sources = sorted(observed_by_source)
    vci_ob, kbs_ob = observed_by_source.get("VCI"), observed_by_source.get("KBS")

    if vci_ob is not None and kbs_ob is not None:
        if _price_fields_agree(vci_ob["native"], kbs_ob["native"]):
            volume_status = "AGREE" if _volumes_agree(vci_ob["normalized"], kbs_ob["normalized"]) else "DISAGREE"
            return {
                "ticker": ticker,
                "resolution": RESOLUTION_CORROBORATED_NON_DNSE,
                "resolved_source": "VCI",
                "resolved_normalized": vci_ob["normalized"],
                "cross_source_conflict": False,
                "cross_source_volume_comparability": volume_status,
                "contributing_sources": contributing_sources,
                "resolved_under_quarantine": True,
            }
        return {
            "ticker": ticker,
            "resolution": RESOLUTION_CONFLICT,
            "resolved_source": None,
            "resolved_normalized": None,
            "cross_source_conflict": True,
            "cross_source_volume_comparability": "NOT_ESTABLISHED",
            "contributing_sources": contributing_sources,
            "resolved_under_quarantine": True,
        }

    winner = vci_ob if vci_ob is not None else kbs_ob
    if winner is not None:
        return {
            "ticker": ticker,
            "resolution": RESOLUTION_SINGLE_SOURCE,
            "resolved_source": winner["source"],
            "resolved_normalized": winner["normalized"],
            "cross_source_conflict": False,
            "cross_source_volume_comparability": "NOT_APPLICABLE_SINGLE_SOURCE",
            "contributing_sources": contributing_sources,
            "resolved_under_quarantine": True,
        }

    return {
        "ticker": ticker,
        "resolution": RESOLUTION_ALL_MISSING,
        "resolved_source": None,
        "resolved_normalized": None,
        "cross_source_conflict": False,
        "cross_source_volume_comparability": "NOT_APPLICABLE_NO_OBSERVED_SOURCE",
        "contributing_sources": contributing_sources,
        "resolved_under_quarantine": True,
    }


def classify_dnse_provider_health(sentinel_observations: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Reduce a bounded sentinel cohort's per-ticker observations to one DNSE same-date
    provider-health verdict for the session.

    ``sentinel_observations`` maps ticker -> that ticker's full observation list (same shape
    ``resolve_ticker`` consumes -- normally DNSE plus whichever of VCI/KBS were queried for the
    sentinel). Only tickers where DNSE itself returned ``STATUS_EXACT_SESSION_OBSERVED`` are a
    DNSE-quality question at all; a ticker DNSE never resolved is a coverage gap (Lane A's own
    concern), not evidence about the quality of the bars DNSE DID return. Pure/deterministic --
    never re-fetches or mutates anything; callers own all I/O.
    """
    assessed = 0
    corroborated = 0
    conflicts = 0
    uncorroborated = 0
    per_ticker: dict[str, str] = {}
    for ticker, observations in sentinel_observations.items():
        dnse_ob = next((o for o in observations if o.get("source") == "DNSE"), None)
        if dnse_ob is None or dnse_ob.get("status") != STATUS_EXACT_SESSION_OBSERVED:
            continue
        other_observed = [
            o for o in observations
            if o.get("source") in ("VCI", "KBS") and o.get("status") == STATUS_EXACT_SESSION_OBSERVED
        ]
        resolution = resolve_ticker(ticker, observations)
        per_ticker[ticker] = resolution["resolution"]
        if not other_observed:
            uncorroborated += 1
            continue
        assessed += 1
        if resolution["resolution"] in (RESOLUTION_CONFLICT, RESOLUTION_CORROBORATED_NON_DNSE):
            conflicts += 1
        elif resolution["resolution"] == RESOLUTION_CORROBORATED:
            corroborated += 1

    if assessed == 0:
        state = DNSE_HEALTH_EXACT_BUT_UNCORROBORATED
    elif assessed >= DNSE_BROAD_MIN_ASSESSED_COUNT and (conflicts / assessed) >= DNSE_BROAD_CONFLICT_RATIO_THRESHOLD:
        state = DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD
    elif conflicts > 0:
        state = DNSE_HEALTH_MATERIAL_CONFLICT
    else:
        state = DNSE_HEALTH_EXACT_AND_CORROBORATED

    return {
        "state": state,
        "sentinel_size": len(sentinel_observations),
        "dnse_assessed_count": assessed,
        "corroborated_count": corroborated,
        "conflict_count": conflicts,
        "uncorroborated_count": uncorroborated,
        "per_ticker_resolution": per_ticker,
    }
