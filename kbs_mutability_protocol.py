"""The evidence protocol that would qualify KBS historical mutability at a future event.

WHY THIS MODULE EXISTS
    The 2026-08-04 lane established that KBS restates prices at corporate-action
    boundaries, and left one question open: does the provider *rewrite already-published
    historical rows* when the event becomes effective, or does it serve a series that was
    always adjusted? Those look identical in any snapshot taken afterwards.

    The lane then proposed re-requesting the HPG 2026-05-18..06-02 window "after enough
    elapsed time". That proposal was wrong, and the reason is worth stating plainly because
    it is the trap this module exists to close: the earliest retained KBS payload for that
    window is dated 2026-08-04, and the ex-right date is 2026-05-25. Whatever the provider
    did at the event, it had already done it before the first observation. A second request
    -- tomorrow, or in a year -- yields another post-event snapshot. Two post-event snapshots
    can only measure *post-event stability*. Elapsed time is not the missing ingredient; a
    snapshot taken **before** an event is.

    So the only route is prospective, and it has to be set up before the event rather than
    reconstructed after it. This module is that setup: a schema, a manifest format, a
    comparison contract and deterministic paths, all validated against frozen fixtures.

WHAT THIS MODULE DELIBERATELY IS NOT
    It issues no request, schedules nothing, watches for no event and polls nothing. It
    contains no network code and no clock-driven behaviour. Identifying a suitable future
    event and authorising the pre-event snapshot is an owner decision, and the protocol is
    inert until one is taken.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

import evidence_qualification_tiers as tiers
import kbs_empirical_basis as basis

VERSION = "1.0.0"

PROVIDER = basis.PROVIDER
SOURCE_AUTHORITY = basis.SOURCE_AUTHORITY

#: Nothing in this module may reach the network, and nothing may put it on a timer. Both
#: are asserted rather than merely intended -- see :func:`protocol_snapshot` and the tests.
NETWORK_ACCESS_AUTHORIZED = False
SCHEDULING_AUTHORIZED = False
EVENT_POLLING_AUTHORIZED = False
AUTOMATIC_ACQUISITION_AUTHORIZED = False


class MutabilityProtocolError(ValueError):
    """Fail-closed rejection in the prospective mutability protocol."""


# ---------------------------------------------------------------------------------
# Part 1 -- what a valid observation requires
# ---------------------------------------------------------------------------------

#: The fields a pre-event snapshot record must carry. A pre-event snapshot missing any of
#: them cannot be shown to *be* pre-event, which is the only property that matters.
PRE_EVENT_MANIFEST_FIELDS: tuple[str, ...] = (
    "protocol_version",
    "provider",
    "ticker",
    "endpoint",
    "request_parameters",
    "historical_window",
    "retrieved_at",
    "raw_artifact",
    "raw_sha256",
    "response_schema_fingerprint",
    "event_id",
    "event_ex_date",
    "event_kind",
    "event_evidence_identity",
    "control_ticker",
    "control_window",
)

#: The post-event record must reproduce the request exactly. Any drift here turns a rewrite
#: test into a comparison of two different questions.
POST_EVENT_MUST_MATCH: tuple[str, ...] = (
    "provider",
    "ticker",
    "endpoint",
    "request_parameters",
    "historical_window",
)

#: Compared field by field. Row presence and schema are on the list because a disappeared
#: row and a renamed field are both rewrites, and neither shows up in a value diff.
COMPARISON_FIELDS: tuple[str, ...] = ("o", "h", "l", "c", "v", "va", "row_presence", "schema")

#: The change classes, kept apart so one cannot stand in for another. In particular a
#: provider correction unrelated to the event is a real possibility and must be separable,
#: or every unrelated data fix would read as an event adjustment.
CHANGE_CLASSES: tuple[str, ...] = (
    "price_rewrite",
    "volume_rewrite",
    "value_rewrite",
    "schema_change",
    "unrelated_provider_correction",
)

#: The only verdicts a single prospective observation may produce. Each is scoped to the
#: tested event and window by construction -- see :func:`assert_verdict_scoped`.
PROSPECTIVE_VERDICTS = frozenset(
    {
        "event_time_price_rewrite_observed",
        "event_time_volume_rewrite_observed",
        "price_rewrite_without_volume_rewrite",
        "no_rewrite_observed_for_tested_event",
        "provider_schema_changed",
        "comparison_conflicted",
        "observation_incomplete",
    }
)

#: A verdict that says nothing about mutability either way. Reported, never silently
#: upgraded into "no rewrite happened".
INCOMPLETE = "observation_incomplete"


def event_kind_is_share_related(event_kind: str) -> bool:
    return str(event_kind) == basis.EVENT_KIND_SHARE


# ---------------------------------------------------------------------------------
# Part 2 -- deterministic artifact paths
# ---------------------------------------------------------------------------------

EVIDENCE_ROOT = "operations-review/kbs-mutability-observation"


def observation_dir(*, event_id: str, ex_date: str) -> str:
    """Where one prospective observation lives. Derived, never chosen ad hoc."""
    slug = "".join(ch for ch in str(event_id).strip().lower() if ch.isalnum() or ch in "-_")
    if not slug:
        raise MutabilityProtocolError("event_id_unusable_for_a_path")
    date = str(ex_date).strip()
    if len(date) != 10 or date[4] != "-" or date[7] != "-":
        raise MutabilityProtocolError(f"ex_date_must_be_yyyy_mm_dd:{ex_date}")
    return f"{EVIDENCE_ROOT}/{date}-{slug}"


def artifact_path(*, event_id: str, ex_date: str, phase: str, ticker: str,
                  retrieved_at: str, sha256: str) -> str:
    """Deterministic path for one raw payload, with its phase in the name.

    The phase is part of the identity rather than metadata beside it: a file whose name
    does not say whether it was taken before or after the event is one filesystem accident
    away from being useless.
    """
    if phase not in {"pre_event", "post_event", "control_pre_event", "control_post_event"}:
        raise MutabilityProtocolError(f"unknown_observation_phase:{phase}")
    name = basis.artifact_name(ticker, retrieved_at=retrieved_at, body_sha256=sha256)
    return f"{observation_dir(event_id=event_id, ex_date=ex_date)}/{phase}/{name}"


# ---------------------------------------------------------------------------------
# Part 3 -- the pre-event manifest
# ---------------------------------------------------------------------------------


def build_pre_event_manifest(**kwargs: Any) -> dict[str, Any]:
    """Assemble and validate a pre-event snapshot record.

    The one substantive check is the one the whole protocol turns on: the snapshot must
    have been retrieved **strictly before** the ex-right date. A record that fails it is
    not a weaker pre-event snapshot, it is a post-event snapshot, and accepting it would
    reproduce exactly the error this protocol was written to prevent.
    """
    missing = [field for field in PRE_EVENT_MANIFEST_FIELDS if field not in kwargs]
    if missing:
        raise MutabilityProtocolError(f"pre_event_manifest_fields_missing:{','.join(sorted(missing))}")
    record = {field: kwargs[field] for field in PRE_EVENT_MANIFEST_FIELDS}

    if record["provider"] != PROVIDER:
        raise MutabilityProtocolError("pre_event_manifest_provider_must_be_kbs")
    basis.assert_ticker_in_scope(str(record["ticker"]))
    basis.assert_endpoint_in_scope(str(record["endpoint"]))
    if not str(record["event_evidence_identity"]).strip():
        raise MutabilityProtocolError("pre_event_manifest_requires_an_event_evidence_identity")
    if record["event_kind"] not in basis.EVENT_KINDS:
        raise MutabilityProtocolError(f"event_kind_unknown:{record['event_kind']}")

    retrieved_on = basis._instant_date(str(record["retrieved_at"]))
    ex_date = str(record["event_ex_date"]).strip()
    if retrieved_on >= ex_date:
        raise MutabilityProtocolError(
            f"snapshot_is_not_pre_event:retrieved_on={retrieved_on}>=ex_date={ex_date}"
        )

    window = record["historical_window"]
    if not isinstance(window, Sequence) or len(window) != 2:
        raise MutabilityProtocolError("historical_window_must_be_a_start_end_pair")
    if str(window[1]) >= ex_date:
        raise MutabilityProtocolError(
            "historical_window_must_end_before_the_ex_date_so_every_row_is_already_closed"
        )
    if not str(record["control_ticker"]).strip():
        raise MutabilityProtocolError("pre_event_manifest_requires_a_control")

    record["protocol_version"] = VERSION
    record["phase"] = "pre_event"
    record["network_access_authorized"] = NETWORK_ACCESS_AUTHORIZED
    return record


def assert_post_event_request_matches(
    *, pre_event: Mapping[str, Any], post_event: Mapping[str, Any]
) -> None:
    """The post-event request must be the same request, or the diff means nothing."""
    for field in POST_EVENT_MUST_MATCH:
        if pre_event.get(field) != post_event.get(field):
            raise MutabilityProtocolError(f"post_event_request_drifted:{field}")
    post_on = basis._instant_date(str(post_event["retrieved_at"]))
    ex_date = str(pre_event["event_ex_date"]).strip()
    if post_on < ex_date:
        raise MutabilityProtocolError(
            f"post_event_snapshot_is_not_post_event:retrieved_on={post_on}<ex_date={ex_date}"
        )


# ---------------------------------------------------------------------------------
# Part 4 -- the comparison contract
# ---------------------------------------------------------------------------------

_FIELD_KEYS = {
    "o": "kbs.observed_open_vnd",
    "h": "kbs.observed_high_vnd",
    "l": "kbs.observed_low_vnd",
    "c": "kbs.observed_close_vnd",
    "v": "kbs.observed_daily_volume",
    "va": "kbs.observed_daily_trading_value",
}

_PRICE_KEYS = ("o", "h", "l", "c")


def compare_snapshots(
    *,
    pre_event_rows: Sequence[Mapping[str, Any]],
    post_event_rows: Sequence[Mapping[str, Any]],
    pre_event_schema_fingerprint: str,
    post_event_schema_fingerprint: str,
) -> dict[str, Any]:
    """Field-by-field diff of the same historical sessions across the event boundary."""
    pre = {row["kbs.session_date"]: row for row in pre_event_rows}
    post = {row["kbs.session_date"]: row for row in post_event_rows}
    shared = sorted(set(pre) & set(post))

    per_field: dict[str, int] = {name: 0 for name in _FIELD_KEYS}
    detail: list[dict[str, Any]] = []
    for session in shared:
        before, after = pre[session], post[session]
        changed = {}
        for name, key in _FIELD_KEYS.items():
            if before.get(key) != after.get(key):
                per_field[name] += 1
                changed[name] = {"pre": before.get(key), "post": after.get(key)}
        if changed:
            detail.append({"session_date": session, "changed_fields": changed})

    return {
        "protocol_version": VERSION,
        "sessions_compared": len(shared),
        "sessions_only_in_pre_event": sorted(set(pre) - set(post)),
        "sessions_only_in_post_event": sorted(set(post) - set(pre)),
        "changed_field_counts": per_field,
        "changed_detail": detail,
        "schema_changed": pre_event_schema_fingerprint != post_event_schema_fingerprint,
        "price_rewrite": any(per_field[name] for name in _PRICE_KEYS),
        "volume_rewrite": bool(per_field["v"]),
        "value_rewrite": bool(per_field["va"]),
        "row_presence_changed": bool(set(pre) ^ set(post)),
    }


def classify_comparison(
    *,
    comparison: Mapping[str, Any],
    control_comparison: Mapping[str, Any] | None,
    pre_event_manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Turn one comparison into one scoped verdict.

    The control does real work here. A provider that quietly restates *everything* on some
    maintenance schedule would produce a changed event window and a changed control window
    alike; only the control distinguishes "the event caused this" from "the provider
    rewrote that week". So a change present in both is classified as
    ``unrelated_provider_correction`` and does not support an event-time verdict.
    """
    if pre_event_manifest is None:
        return {
            "verdict": INCOMPLETE,
            "reason": "no_pre_event_snapshot_retained",
            "note": (
                "Two post-event snapshots cannot substitute. The restatement under test "
                "would already have happened before the earlier of them."
            ),
            "change_classes": [],
        }
    if not comparison.get("sessions_compared"):
        return {
            "verdict": INCOMPLETE,
            "reason": "no_overlapping_sessions_between_the_two_snapshots",
            "change_classes": [],
        }

    classes: list[str] = []
    if comparison.get("schema_changed"):
        classes.append("schema_change")
    control_changed = bool(
        control_comparison
        and (
            control_comparison.get("price_rewrite")
            or control_comparison.get("volume_rewrite")
            or control_comparison.get("value_rewrite")
        )
    )
    if control_changed:
        classes.append("unrelated_provider_correction")
    if comparison.get("price_rewrite"):
        classes.append("price_rewrite")
    if comparison.get("volume_rewrite"):
        classes.append("volume_rewrite")
    if comparison.get("value_rewrite"):
        classes.append("value_rewrite")

    event_kind = str(pre_event_manifest.get("event_kind", ""))
    scope = {
        "event_id": pre_event_manifest.get("event_id"),
        "event_ex_date": pre_event_manifest.get("event_ex_date"),
        "event_kind": event_kind,
        "ticker": pre_event_manifest.get("ticker"),
        "historical_window": list(pre_event_manifest.get("historical_window", [])),
        "coverage_generalization": tiers.COVERAGE_LIMITED,
        "provider_methodology": "unknown",
    }

    if comparison.get("schema_changed") and not (
        comparison.get("price_rewrite") or comparison.get("volume_rewrite")
    ):
        return {"verdict": "provider_schema_changed", "change_classes": classes, "scope": scope}
    if control_changed and (comparison.get("price_rewrite") or comparison.get("volume_rewrite")):
        return {
            "verdict": "comparison_conflicted",
            "reason": "the_control_window_changed_too_so_the_event_is_not_isolated",
            "change_classes": classes,
            "scope": scope,
        }
    if comparison.get("volume_rewrite"):
        return {
            "verdict": "event_time_volume_rewrite_observed",
            "change_classes": classes,
            "scope": scope,
            "note": "Scoped to this event. Volume adjustment is not thereby established "
            "for any other event, and not for a cash distribution at all."
            if event_kind != basis.EVENT_KIND_SHARE
            else "Scoped to this event and window.",
        }
    if comparison.get("price_rewrite"):
        return {
            "verdict": "price_rewrite_without_volume_rewrite",
            "change_classes": classes,
            "scope": scope,
            "note": "The two fields were restated on different schedules for this event.",
        }
    return {
        "verdict": "no_rewrite_observed_for_tested_event",
        "change_classes": classes,
        "scope": scope,
        "note": "Scoped to this event and window. It is not a claim that the provider "
        "never rewrites history.",
    }


def assert_verdict_scoped(verdict: Mapping[str, Any]) -> Mapping[str, Any]:
    """A prospective verdict must name its event and refuse to generalise.

    One event is one event. Without this, the first observation to come back clean would be
    quoted as "KBS does not rewrite history", which is exactly the overreach the whole
    qualification ladder exists to prevent.
    """
    name = str(verdict.get("verdict", ""))
    if name not in PROSPECTIVE_VERDICTS:
        raise MutabilityProtocolError(f"prospective_verdict_not_in_vocabulary:{name}")
    if name == INCOMPLETE:
        return verdict
    scope = verdict.get("scope") or {}
    for field in ("event_id", "event_ex_date", "ticker", "historical_window"):
        if not scope.get(field):
            raise MutabilityProtocolError(f"prospective_verdict_missing_scope:{field}")
    if scope.get("coverage_generalization") != tiers.COVERAGE_LIMITED:
        raise MutabilityProtocolError("prospective_verdict_must_stay_limited_to_tested_windows")
    if scope.get("provider_methodology") not in (None, "unknown"):
        raise MutabilityProtocolError(
            "one_event_cannot_establish_universal_kbs_methodology:"
            f"{scope.get('provider_methodology')}"
        )
    return verdict


def contract_effect(verdict: Mapping[str, Any]) -> dict[str, Any]:
    """What a completed observation would change, and everything it would not.

    Written now, before any observation exists, so the answer is not negotiated after
    seeing a result. Only the mutability dimensions move; every capability gate stays where
    the 2026-08-04 closeout put it.
    """
    assert_verdict_scoped(verdict)
    name = str(verdict["verdict"])
    rewrote_price = name in {
        "event_time_price_rewrite_observed",
        "price_rewrite_without_volume_rewrite",
    }
    rewrote_volume = name == "event_time_volume_rewrite_observed"
    settled = name in {
        "event_time_price_rewrite_observed",
        "event_time_volume_rewrite_observed",
        "price_rewrite_without_volume_rewrite",
        "no_rewrite_observed_for_tested_event",
    }
    return {
        "historical_mutability": (
            "retrospectively_rewritten" if rewrote_price or rewrote_volume
            else "not_observed" if settled else "unknown"
        ),
        "volume_adjustment_basis": (
            "share_event_adjusted_volume_observed" if rewrote_volume else "not_observed"
        ),
        "raw_as_traded_eligible": False,
        "official_exchange_price": False,
        "volume_market_scope": "unknown",
        "liquidity_actionable": False,
        "is_actionable_effect": "none",
        "production_write": False,
        "capability_activation": False,
        "coverage_generalization": tiers.COVERAGE_LIMITED,
        "note": (
            "A completed observation moves the mutability dimensions and nothing else. It "
            "cannot open liquidity, execution, point-in-time or production capabilities, "
            "and a clean result does not make the series raw as-traded."
        ),
    }


# ---------------------------------------------------------------------------------
# Part 5 -- the protocol record itself
# ---------------------------------------------------------------------------------


def protocol_snapshot() -> dict[str, Any]:
    """The whole protocol as data, for the closeout artifact and for diffing."""
    return {
        "schema_version": VERSION,
        "provider": PROVIDER,
        "source_authority": SOURCE_AUTHORITY,
        "purpose": "qualify_kbs_event_time_historical_mutability",
        "why_a_retrospective_test_is_impossible": (
            "The earliest retained KBS payload for every tested window is 2026-08-04, and "
            "every qualified ex-right date in those windows precedes it. Any further "
            "request is another post-event snapshot, so no amount of elapsed time yields "
            "the pre/post pair the question requires."
        ),
        "pre_event_manifest_fields": list(PRE_EVENT_MANIFEST_FIELDS),
        "post_event_must_match": list(POST_EVENT_MUST_MATCH),
        "comparison_fields": list(COMPARISON_FIELDS),
        "change_classes": list(CHANGE_CLASSES),
        "prospective_verdicts": sorted(PROSPECTIVE_VERDICTS),
        "evidence_root": EVIDENCE_ROOT,
        "control_required": True,
        "network_access_authorized": NETWORK_ACCESS_AUTHORIZED,
        "scheduling_authorized": SCHEDULING_AUTHORIZED,
        "event_polling_authorized": EVENT_POLLING_AUTHORIZED,
        "automatic_acquisition_authorized": AUTOMATIC_ACQUISITION_AUTHORIZED,
        "activation": "owner_authorization_required_per_event",
        "coverage_generalization": tiers.COVERAGE_LIMITED,
        "corrected_framing": dict(CORRECTED_FRAMING),
        "superseded_recommendation": dict(SUPERSEDED_RECOMMENDATION),
    }


def assert_protocol_inert(snapshot: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Refuse a protocol record that has switched anything on."""
    snap = snapshot if snapshot is not None else protocol_snapshot()
    for flag in (
        "network_access_authorized",
        "scheduling_authorized",
        "event_polling_authorized",
        "automatic_acquisition_authorized",
    ):
        if snap.get(flag):
            raise MutabilityProtocolError(f"protocol_must_stay_inert:{flag}")
    if not snap.get("control_required"):
        raise MutabilityProtocolError("protocol_must_require_a_control")
    return snap


#: A framing correction against a frozen evidence artifact. The artifact is *not* edited --
#: an evidence record that gets rewritten when the reasoning improves is not an evidence
#: record. Every measurement in it stands; what is corrected is an implication its wording
#: carries.
CORRECTED_FRAMING: dict[str, Any] = {
    "artifact": "operations-review/kbs-empirical-basis-20260804/KBS_EMPIRICAL_BASIS.md",
    "commit": "4a07141",
    "sections": ["3. Price basis / Historical mutability", "5. Volume adjustment", "8. Scope"],
    "asserted_framing": (
        "The rewrite comparison 'spans no qualified share event', and the only as-of pair "
        "'spans no share event'."
    ),
    "why_it_misleads": (
        "Literally true, and it implies the gap is a choice of window -- that picking a "
        "window with an ex-right date inside it would have answered the question. It would "
        "not. Both retrievals (2026-08-01 and 2026-08-04) post-date every qualified "
        "ex-right date in every tested window, so no window selection and no further "
        "elapsed time can produce a pre/post pair from this evidence."
    ),
    "corrected_framing": (
        "Event-time historical mutability requires a snapshot retained BEFORE a future "
        "event and a matching snapshot retained AFTER it. The retained pair is "
        "both_post_event and measures post-event snapshot stability only."
    ),
    "measurements_changed": False,
    "evidence_changed": False,
    "artifact_rewritten": False,
    "corrected_at": "2026-08-04",
    "corrected_by": "kbs_mutability_protocol@1.0.0",
    "also_corrected_in": [
        "docs/kbs_empirical_basis_qualification.md",
        "docs/STATE.md",
        "docs/ROADMAP.md",
        "docs/DECISIONS.md",
        "docs/AI_RULES.md",
    ],
}

#: The superseded *recommendation*, retained so the reasoning error stays visible. This was
#: never committed as a repository claim; it is recorded here because the protocol above
#: exists precisely to make it unrepeatable.
SUPERSEDED_RECOMMENDATION: dict[str, Any] = {
    "recommendation": (
        "Re-request the HPG 2026-05-18..2026-06-02 window after enough elapsed time to "
        "settle historical mutability across the 2026-05-25 event."
    ),
    "proposed_at": "2026-08-04, closing report of commit 4a07141",
    "status": "superseded",
    "root_cause": "post_event_snapshot_treated_as_a_substitute_for_a_pre_event_snapshot",
    "why_it_fails": (
        "The earliest retained KBS payload for that window is 2026-08-04 and the ex-right "
        "date is 2026-05-25. Any further request is a second post-event snapshot, so the "
        "comparison can only measure post-event stability."
    ),
    "superseded_by": "kbs_mutability_protocol.protocol_snapshot()",
    "would_have_settled": [],
    "must_not_be_claimed_to_settle": [
        "historical_mutability_across_the_share_event",
        "corporate_action_adjustment_of_historical_volume",
    ],
}


def assert_not_a_retrospective_substitute(
    *, prior_observed_at: str, current_observed_at: str, event_ex_dates: Sequence[str]
) -> Mapping[str, Any]:
    """Refuse a pair being offered as an event-time test when it cannot be one.

    The callable form of the correction above. A caller that wants to answer the event-time
    question has to pass a pair that straddles the event, and gets an error naming the
    reason if it does not.
    """
    pair = basis.classify_snapshot_pair(
        prior_observed_at=prior_observed_at,
        current_observed_at=current_observed_at,
        event_ex_dates=event_ex_dates,
    )
    if not pair["event_time_testable"]:
        raise MutabilityProtocolError(
            f"pair_cannot_test_event_time_rewriting:{pair['pair_class']}:"
            "a_pre_event_snapshot_is_required_and_elapsed_time_is_not_a_substitute"
        )
    return pair


def protocol_fingerprint() -> str:
    """Stable hash of the protocol definition, so a silent change is detectable."""
    payload = json.dumps(protocol_snapshot(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
