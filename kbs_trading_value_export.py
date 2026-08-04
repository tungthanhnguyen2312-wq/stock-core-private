"""The export seam for KBS trading value: the only way a ``va`` number may leave Producer.

WHAT THE TRACE FOUND
    Nothing exports ``va`` today. The lineage stops three steps before the bundle:

        raw payload            va present on 38 of 66 retained sessions
        vnstock KbsQuote       drops va entirely (get_all=False)
        vn_stock_pipeline      ohlcv(ticker,date,open,high,low,close,volume,source)
        export_ai_bundle       no trading-value field anywhere
        analysis_bundle.json   ohlcv_recent rows are {date,o,h,l,c,volume}

    So there is no bare KBS trading value crossing the boundary, and no coverage metadata to
    retrofit onto one. This module therefore builds **no product surface**. It is a seam: the
    canonical block builder, the validator, and the refusal that fires if a future caller
    tries to export a value without one.

WHY BUILD IT NOW RATHER THAN WHEN THE VALUE ARRIVES
    Because the cheap moment to require coverage is before the first caller exists. Once a
    bare number is in a schema, every consumer of it becomes a migration. The seam costs
    nothing while ``ACTIVE_EXPORT_PATH`` is ``None`` and is already in place the day someone
    flips ``get_all=True``.

WHAT IT IS NOT
    It does not add a bundle section, does not populate a field with nulls, and does not
    claim a value path exists. :data:`ACTIVE_EXPORT_PATH` records the absence explicitly so
    a reader is not left inferring it from silence.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

import evidence_qualification_tiers as tiers
import kbs_trading_value_coverage as cov

VERSION = "1.0.0"

#: Bumped independently of the bundle schema. This block is additive and absent today, so a
#: reader that has never seen it is not broken by it -- see ``compatibility()``.
EXPORT_BLOCK_VERSION = "1.0.0"

PROVIDER = cov.PROVIDER
SOURCE_FIELD = cov.RAW_FIELD

#: There is no active export path for KBS ``va``. Recorded as data, with the trace that
#: established it, so the next reader does not have to redo the search to learn it.
ACTIVE_EXPORT_PATH: None = None

ABSENCE_OF_ACTIVE_VALUE_PATH: dict[str, Any] = {
    "kbs_va_exported": False,
    "traced_at": "2026-08-04",
    "trace": [
        "raw KBS payload: va present on 38 of 66 retained sessions",
        "vnstock.explorer.kbs.quote.Quote.history: drops va unless get_all=True",
        "vn_stock_pipeline: ohlcv table has no value column",
        "export_ai_bundle: no trading-value, va or turnover reference",
        "analysis_bundle.json: ohlcv_recent rows carry {date,open,high,low,close,volume}",
    ],
    "consequence": (
        "No bare KBS trading value crosses the Producer/Consumer boundary today, so there "
        "is nothing to retrofit and no legacy va aggregate to quarantine."
    ),
    "seam_is_future_safe": True,
    "activation": "populated only when a caller supplies observations through build_row_block "
    "or build_window_block; no bundle section is added by this module",
}


class TradingValueExportError(ValueError):
    """Fail-closed rejection in the KBS trading-value export seam."""


# ---------------------------------------------------------------------------------
# Canonical warning tokens -- one source, both repositories
# ---------------------------------------------------------------------------------

#: Warning *tokens*, not sentences, are what cross the boundary. A token is stable, testable
#: and translatable; a sentence generated independently in five modules drifts. Consumer
#: pins the same identifiers and asserts the text hash, so a change here is a change there.
TOKEN_PARTIAL_COVERAGE = "kbs_trading_value_partial_coverage"
TOKEN_PROVIDER_AUTHORITY = "kbs_trading_value_provider_authority"

CANONICAL_WARNINGS: dict[str, str] = {
    TOKEN_PARTIAL_COVERAGE: (
        "KBS trading-value coverage is partial for the requested interval. "
        "Statistics are computed from observed rows only. "
        "Missing sessions were not imputed or treated as zero. "
        "The result is provider-scoped and is not official market turnover "
        "or qualified liquidity evidence."
    ),
    TOKEN_PROVIDER_AUTHORITY: (
        "This is a KBS provider observation with empirically deduced units. "
        "It is not an official exchange trading-value contract."
    ),
}


def warning_text(token: str) -> str:
    if token not in CANONICAL_WARNINGS:
        raise TradingValueExportError(f"unknown_warning_token:{token}")
    return CANONICAL_WARNINGS[token]


def warnings_fingerprint() -> str:
    """Hash of the canonical warning table, so Consumer can pin it."""
    payload = json.dumps(CANONICAL_WARNINGS, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def warnings_for(coverage_state: str) -> list[str]:
    """Which tokens a result in this coverage state must carry.

    The authority token is unconditional: every KBS value is a provider observation whatever
    its coverage. The partial token is added, never substituted -- a partial result is both
    partial *and* provider-scoped.
    """
    tokens = [TOKEN_PROVIDER_AUTHORITY]
    if coverage_state == cov.COVERAGE_PARTIAL_KNOWN:
        tokens.insert(0, TOKEN_PARTIAL_COVERAGE)
    return tokens


# ---------------------------------------------------------------------------------
# The canonical exported block
# ---------------------------------------------------------------------------------

#: Every key the coverage sub-block carries. Fixed so a validator can check presence rather
#: than trusting a producer to have remembered.
COVERAGE_KEYS: tuple[str, ...] = (
    "coverage_state",
    "requested_session_count",
    "returned_row_count",
    "present_numeric_count",
    "present_zero_count",
    "present_null_count",
    "field_omitted_count",
    "malformed_count",
    "row_missing_count",
    "usable_count",
    "coverage_ratio",
    "covered_sessions",
    "missing_sessions",
    "excluded_sessions",
    "statistic_scope",
    "partial_coverage_warning",
    "coverage_generalization",
    "causal_explanation",
    "automatic_imputation_authorized",
    "missing_as_zero_authorized",
)

BLOCK_KEYS: tuple[str, ...] = (
    "export_block_version",
    "provider",
    "source_field",
    "source_field_identity",
    "trading_value_unit",
    "trading_value_unit_qualification",
    "coverage",
    "warning_tokens",
    "warnings",
)


def _envelope() -> dict[str, Any]:
    return {
        "export_block_version": EXPORT_BLOCK_VERSION,
        "provider": PROVIDER,
        "source_field": SOURCE_FIELD,
        "source_field_identity": "qualified",
        "trading_value_unit": "VND",
        "trading_value_unit_qualification": tiers.EMPIRICALLY_DEDUCED,
    }


def build_row_block(row_record: Mapping[str, Any]) -> dict[str, Any]:
    """The block for **one observed row**.

    A single row is not a one-session window. Counting it as ``requested_session_count = 1``
    would invite a reader to compute a ratio and call it coverage of an interval nobody
    asked about, so the scope is ``single_observed_row`` and the window counts stay at the
    one row that exists.
    """
    state = str(row_record["trading_value_field_state"])
    usable = bool(row_record["trading_value_usable_for_row_statistics"])
    counts = {f"{name}_count": 0 for name in
              ("present_numeric", "present_zero", "present_null", "field_omitted",
               "malformed", "row_missing")}
    counts[f"{state}_count"] = 1
    session = str(row_record["session_date"])
    block = {
        **_envelope(),
        "session_date": session,
        "trading_value_value": row_record["trading_value_value"],
        "trading_value_field_state": state,
        "coverage": {
            **counts,
            "coverage_state": cov.COVERAGE_COMPLETE if usable else cov.COVERAGE_ABSENT,
            "requested_session_count": 1,
            "returned_row_count": 1,
            "usable_count": 1 if usable else 0,
            "coverage_ratio": 1.0 if usable else 0.0,
            "covered_sessions": [session] if usable else [],
            "missing_sessions": [],
            "excluded_sessions": (
                [] if usable
                else [{"session_date": session, "state": state,
                       "reason": str(row_record["exclusion_reason"])}]
            ),
            "statistic_scope": cov.SCOPE_SINGLE_ROW,
            "partial_coverage_warning": None,
            "coverage_generalization": "limited_to_retained_windows",
            "causal_explanation": "unknown",
            "automatic_imputation_authorized": False,
            "missing_as_zero_authorized": False,
        },
    }
    tokens = warnings_for(cov.COVERAGE_COMPLETE if usable else cov.COVERAGE_ABSENT)
    block["warning_tokens"] = tokens
    block["warnings"] = [warning_text(token) for token in tokens]
    return assert_block_valid(block)


def build_window_block(
    window_coverage: Mapping[str, Any], *, statistic_scope: str
) -> dict[str, Any]:
    """The block for an aggregate over a window.

    ``window_coverage`` must come from :func:`kbs_trading_value_coverage.window_coverage`.
    Nothing here recomputes a count: every number is copied from the canonical record, so
    the export cannot disagree with the contract that produced it.
    """
    if statistic_scope not in cov.STATISTIC_SCOPES:
        raise TradingValueExportError(f"unknown_statistic_scope:{statistic_scope}")
    state = str(window_coverage["coverage_state"])
    if statistic_scope == cov.SCOPE_COMPLETE_WINDOW and state != cov.COVERAGE_COMPLETE:
        raise TradingValueExportError(
            f"complete_requested_window_scope_requires_complete_coverage:{state}"
        )
    if state == cov.COVERAGE_PARTIAL_KNOWN and statistic_scope != cov.SCOPE_OBSERVED_ROWS_ONLY:
        raise TradingValueExportError(
            f"partial_coverage_must_export_as_observed_rows_only:{statistic_scope}"
        )

    tokens = warnings_for(state)
    coverage = {key: window_coverage.get(key) for key in COVERAGE_KEYS if key in window_coverage}
    coverage.update(
        {
            "statistic_scope": statistic_scope,
            "partial_coverage_warning": (
                warning_text(TOKEN_PARTIAL_COVERAGE)
                if state == cov.COVERAGE_PARTIAL_KNOWN
                else None
            ),
            "coverage_generalization": "limited_to_retained_windows",
            "causal_explanation": "unknown",
            "automatic_imputation_authorized": False,
            "missing_as_zero_authorized": False,
        }
    )
    coverage.setdefault("covered_sessions", [])
    coverage.setdefault("missing_sessions", [])
    coverage.setdefault("excluded_sessions", [])
    block = {
        **_envelope(),
        "ticker": window_coverage.get("ticker"),
        "requested_window": list(window_coverage.get("requested_window", [])),
        "coverage": coverage,
        "warning_tokens": tokens,
        "warnings": [warning_text(token) for token in tokens],
        "not_comparable_to_complete_period_total": state == cov.COVERAGE_PARTIAL_KNOWN,
    }
    return assert_block_valid(block)


def assert_block_valid(block: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an export block: shape, labels, and labels **against counts**.

    The count check is the load-bearing one. Every individual field can be well-formed while
    the block as a whole lies -- ``coverage_state: complete`` beside 6 usable of 11 requested
    is exactly the failure this seam exists to stop, and no per-field check catches it.
    """
    missing = [key for key in BLOCK_KEYS if key not in block]
    if missing:
        raise TradingValueExportError(f"export_block_missing_keys:{','.join(missing)}")
    if block["provider"] != PROVIDER:
        raise TradingValueExportError("export_block_provider_must_be_kbs")
    if block["source_field"] != SOURCE_FIELD:
        raise TradingValueExportError("export_block_source_field_must_be_va")
    if tiers.may_claim_official_semantics(str(block["trading_value_unit_qualification"])):
        raise TradingValueExportError("kbs_trading_value_has_no_documented_unit_to_claim")

    coverage = block["coverage"]
    absent = [key for key in COVERAGE_KEYS if key not in coverage]
    if absent:
        raise TradingValueExportError(f"export_coverage_missing_keys:{','.join(absent)}")

    state = coverage["coverage_state"]
    if state not in cov.COVERAGE_STATES:
        raise TradingValueExportError(f"export_coverage_state_invalid:{state}")
    scope = coverage["statistic_scope"]
    if scope not in cov.STATISTIC_SCOPES:
        raise TradingValueExportError(f"export_statistic_scope_invalid:{scope}")

    usable = coverage["usable_count"]
    requested = coverage["requested_session_count"]
    if isinstance(usable, int) and isinstance(requested, int):
        if state == cov.COVERAGE_COMPLETE and usable < requested:
            raise TradingValueExportError(
                f"export_label_contradicts_counts:complete_but_{usable}_of_{requested}"
            )
        if state == cov.COVERAGE_ABSENT and usable:
            raise TradingValueExportError("absent_coverage_cannot_report_usable_rows")
        if state == cov.COVERAGE_PARTIAL_KNOWN and (usable == 0 or usable >= requested):
            raise TradingValueExportError(
                f"partial_label_contradicts_counts:{usable}_of_{requested}"
            )
        if usable > requested:
            raise TradingValueExportError("usable_rows_exceed_requested_sessions")
    if scope == cov.SCOPE_COMPLETE_WINDOW and state != cov.COVERAGE_COMPLETE:
        raise TradingValueExportError("only_complete_coverage_may_claim_the_requested_window")

    if state == cov.COVERAGE_PARTIAL_KNOWN:
        if not coverage.get("partial_coverage_warning"):
            raise TradingValueExportError("partial_export_must_carry_its_warning")
        if TOKEN_PARTIAL_COVERAGE not in block["warning_tokens"]:
            raise TradingValueExportError("partial_export_must_carry_the_partial_token")
        if not block.get("not_comparable_to_complete_period_total"):
            raise TradingValueExportError("partial_export_must_declare_incomparability")
    if TOKEN_PROVIDER_AUTHORITY not in block["warning_tokens"]:
        raise TradingValueExportError("every_export_must_carry_the_provider_authority_token")
    if coverage["automatic_imputation_authorized"] or coverage["missing_as_zero_authorized"]:
        raise TradingValueExportError("export_must_not_authorize_imputation")
    if coverage["causal_explanation"] != "unknown":
        raise TradingValueExportError("export_must_not_assert_a_causal_explanation")
    return dict(block)


def assert_no_bare_value(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Refuse a payload carrying a KBS trading value with no coverage block.

    This is the guard that makes the seam load-bearing rather than optional: a future caller
    that adds a value field to an exported record and forgets the block gets an error, not a
    silently under-specified number.
    """
    value_keys = [
        key for key in record
        if key in {cov.FIELD, "trading_value_value", "va", "kbs.raw_va"}
        and record[key] is not None
    ]
    if value_keys and "coverage" not in record:
        raise TradingValueExportError(
            f"kbs_trading_value_exported_without_a_coverage_block:{','.join(sorted(value_keys))}"
        )
    return record


# ---------------------------------------------------------------------------------
# Legacy classification
# ---------------------------------------------------------------------------------

LEGACY_ROW_OBSERVATION = "legacy_row_observation"
LEGACY_AGGREGATE_WITHOUT_COVERAGE = "legacy_aggregate_without_coverage"
LEGACY_NO_TRADING_VALUE = "legacy_no_trading_value"

LEGACY_CLASSES = (
    LEGACY_ROW_OBSERVATION,
    LEGACY_AGGREGATE_WITHOUT_COVERAGE,
    LEGACY_NO_TRADING_VALUE,
)


def classify_legacy_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Classify a payload written before the coverage block existed.

    The default matters more than the branches. Absence of metadata resolves to
    ``coverage_state = unknown``, never to complete: a bundle that predates the contract has
    not told us its coverage is full, it has told us nothing.
    """
    if "coverage" in payload:
        return {"legacy_class": None, "legacy": False, "coverage_state": payload["coverage"].get("coverage_state")}

    has_value = any(
        payload.get(key) is not None
        for key in (cov.FIELD, "trading_value_value", "va", "trading_value")
    )
    if not has_value:
        return {
            "legacy_class": LEGACY_NO_TRADING_VALUE,
            "legacy": True,
            "coverage_state": cov.COVERAGE_UNKNOWN,
            "unaffected": True,
        }
    row_identity = bool(str(payload.get("session_date") or payload.get("date") or "").strip())
    if row_identity:
        return {
            "legacy_class": LEGACY_ROW_OBSERVATION,
            "legacy": True,
            "coverage_state": cov.COVERAGE_UNKNOWN,
            "display_allowed": True,
            "aggregate_allowed": False,
            "warning_tokens": [TOKEN_PROVIDER_AUTHORITY],
            "legacy_provenance_warning": (
                "Legacy KBS observation without a coverage block. Row identity is explicit, "
                "so the value may be displayed as a provider observation; it cannot support "
                "any statement about an interval."
            ),
        }
    return {
        "legacy_class": LEGACY_AGGREGATE_WITHOUT_COVERAGE,
        "legacy": True,
        "coverage_state": cov.COVERAGE_UNKNOWN,
        "display_allowed": False,
        "aggregate_allowed": False,
        "reason": "legacy_value_without_row_identity_or_coverage_cannot_be_interpreted",
    }


#: Claims a legacy payload can never support, whatever it contains.
LEGACY_BLOCKED_CLAIMS: tuple[str, ...] = (
    "period_total_trading_value",
    "complete_window_mean",
    "trading_value_growth",
    "turnover_for_period",
    "official_vwap_claim",
    "trading_value_liquidity_metric",
    "trading_value_capacity_metric",
    "cross_ticker_trading_value_ranking",
)


def assert_legacy_claim_refused(classification: Mapping[str, Any], *, claim: str) -> None:
    if classification.get("legacy") and claim in LEGACY_BLOCKED_CLAIMS:
        raise TradingValueExportError(
            f"legacy_payload_cannot_support:{claim}:{classification.get('legacy_class')}"
        )


# ---------------------------------------------------------------------------------
# Compatibility and snapshot
# ---------------------------------------------------------------------------------


def compatibility() -> dict[str, Any]:
    """How a reader that has never seen this block should behave, stated explicitly."""
    return {
        "export_block_version": EXPORT_BLOCK_VERSION,
        "bundle_schema_version_bumped": False,
        "why_not": (
            "The block is additive and no exported artifact contains one today, so nothing "
            "a current reader parses changes. Bumping the bundle schema would signal a "
            "breaking change that has not happened."
        ),
        "backward_readable": True,
        "forward_behaviour": "a reader without this block treats KBS trading value as "
        "coverage_state=unknown and refuses aggregate claims",
        "fails_closed_when": "a value is present and the coverage block is absent",
        "unrelated_schemas_bumped": [],
    }


def export_snapshot() -> dict[str, Any]:
    return {
        "schema_version": VERSION,
        "export_block_version": EXPORT_BLOCK_VERSION,
        "provider": PROVIDER,
        "source_field": SOURCE_FIELD,
        "active_export_path": ACTIVE_EXPORT_PATH,
        "absence_of_active_value_path": dict(ABSENCE_OF_ACTIVE_VALUE_PATH),
        "block_keys": list(BLOCK_KEYS),
        "coverage_keys": list(COVERAGE_KEYS),
        "statistic_scopes": list(cov.STATISTIC_SCOPES),
        "legacy_classes": list(LEGACY_CLASSES),
        "legacy_blocked_claims": list(LEGACY_BLOCKED_CLAIMS),
        "canonical_warnings": dict(CANONICAL_WARNINGS),
        "warnings_fingerprint": warnings_fingerprint(),
        "compatibility": compatibility(),
        "non_va_derived_quantities": {
            name: dict(record) for name, record in cov.NON_VA_DERIVED_QUANTITIES.items()
        },
        "liquidity_actionable": False,
        "is_actionable_effect": "none",
    }


def assert_export_fail_closed(snapshot: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    snap = snapshot if snapshot is not None else export_snapshot()
    if snap["active_export_path"] is not None:
        raise TradingValueExportError("active_export_path_must_be_declared_not_assumed")
    if snap["liquidity_actionable"]:
        raise TradingValueExportError("liquidity_actionable_must_stay_false")
    if snap["compatibility"]["unrelated_schemas_bumped"]:
        raise TradingValueExportError("unrelated_schemas_must_not_be_bumped")
    for record in snap["non_va_derived_quantities"].values():
        if record["reads_kbs_va"] or record["provider_observed_trading_value"]:
            raise TradingValueExportError("derived_quantity_claims_to_be_observed_va")
    return snap
