"""Coverage and safe-aggregation contract for the KBS raw ``va`` trading-value field.

WHY THIS MODULE EXISTS
    The 2026-08-04 lane qualified ``va``'s unit (VND) and left its *availability* as a
    sentence in a capability note: "va is present on only part of the history, so any
    statistic must state its own coverage." That is advice, and advice is not a gate. A
    caller who never reads it computes a period total over 38 of 66 sessions and reports a
    number that is smaller than the truth by a margin nobody can see in the output.

    The failure is quiet, which is what makes it worth structure. A partial sum looks
    exactly like a complete one. So coverage stops being a warning and becomes a required
    input: an aggregate that claims a whole window has to prove the window is covered, and
    one that cannot has to rename itself.

FOUR KINDS OF "NO NUMBER"
    ``field_omitted`` -- the provider never sent the key.
    ``present_null``  -- it sent the key with no value.
    ``present_zero``  -- it sent a real zero. **This is an observation**, and a session that
                         genuinely traded nothing is data, not a gap.
    ``row_missing``   -- the session itself is absent from the response.
    Plus ``malformed`` for a value that is present and unusable. Merging any of these
    destroys the evidence that says which one happened, so nothing here merges them.

WHAT THIS MODULE REFUSES TO DO
    It never imputes. It never fills ``va`` from price x volume -- that quantity is a
    reconstruction, and on the rows where ``va`` is absent the price is an *adjusted* price,
    so the product is not even a historical turnover. It does not explain *why* ``va`` is
    absent: the association with the empirically adjusted row group is recorded as an
    association, and the mechanism stays unknown.

    It is also deliberately not a general missing-data framework. It knows about one field
    of one provider.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import evidence_qualification_tiers as tiers
import kbs_empirical_basis as basis

VERSION = "1.0.0"

PROVIDER = basis.PROVIDER
SOURCE_AUTHORITY = basis.SOURCE_AUTHORITY

FIELD = "kbs.observed_daily_trading_value"
RAW_FIELD = "va"


class TradingValueCoverageError(ValueError):
    """Fail-closed rejection in the KBS trading-value coverage contract."""


# ---------------------------------------------------------------------------------
# Part A/B -- row-level states
# ---------------------------------------------------------------------------------

STATE_PRESENT_NUMERIC = basis.FIELD_STATE_PRESENT_NUMERIC
STATE_PRESENT_ZERO = basis.FIELD_STATE_PRESENT_ZERO
STATE_PRESENT_NULL = basis.FIELD_STATE_PRESENT_NULL
STATE_FIELD_OMITTED = basis.FIELD_STATE_OMITTED
STATE_MALFORMED = basis.FIELD_STATE_MALFORMED
STATE_ROW_MISSING = "row_missing"

ROW_STATES = (
    STATE_PRESENT_NUMERIC,
    STATE_PRESENT_ZERO,
    STATE_PRESENT_NULL,
    STATE_FIELD_OMITTED,
    STATE_MALFORMED,
    STATE_ROW_MISSING,
)

#: States that carry a usable numeric observation. ``present_zero`` is on this list on
#: purpose: a zero is a measurement of a session that did not trade, and excluding it would
#: bias every mean upward while looking like prudence.
USABLE_STATES = frozenset({STATE_PRESENT_NUMERIC, STATE_PRESENT_ZERO})

#: Why a row cannot contribute a number. Each names the *source* condition, so a reader can
#: tell a provider omission from a transport failure from a session that never existed.
EXCLUSION_REASONS: dict[str, str] = {
    STATE_PRESENT_NULL: "provider_sent_the_key_with_no_value",
    STATE_FIELD_OMITTED: "provider_did_not_send_the_field_for_this_session",
    STATE_MALFORMED: "value_present_but_not_a_usable_number",
    STATE_ROW_MISSING: "session_absent_from_the_provider_response",
}


def assert_row_state(state: str) -> str:
    if state not in ROW_STATES:
        raise TradingValueCoverageError(f"unknown_trading_value_row_state:{state}")
    return state


def row_coverage(
    *,
    session_date: str,
    raw_state: str,
    value: float | None,
    price_basis_row_group: str | None = None,
    normalized_field_present: bool = True,
) -> dict[str, Any]:
    """The row-level coverage record for one session.

    ``normalized_field_present`` exists because the production adapter drops ``va`` for
    *every* row regardless of what the provider sent. A pipeline that never carried the
    field is not evidence that the provider omitted it, and conflating the two would
    manufacture a provider finding out of our own configuration.
    """
    assert_row_state(raw_state)
    usable = raw_state in USABLE_STATES
    if usable and value is None:
        raise TradingValueCoverageError(f"usable_state_without_a_value:{session_date}")
    if not usable and value is not None:
        raise TradingValueCoverageError(f"unusable_state_carrying_a_value:{session_date}")
    return {
        "session_date": session_date,
        "provider": PROVIDER,
        "trading_value_field_state": raw_state,
        "trading_value_observed": usable,
        "trading_value_value": value if usable else None,
        "trading_value_unit": "VND" if usable else None,
        "trading_value_qualification": tiers.EMPIRICALLY_DEDUCED if usable else tiers.UNKNOWN,
        "trading_value_usable_for_row_statistics": usable,
        "exclusion_reason": None if usable else EXCLUSION_REASONS[raw_state],
        "normalized_field_present": bool(normalized_field_present),
        "raw_state_is_not_normalized_state": True,
        "price_basis_row_group": price_basis_row_group,
    }


def row_coverage_from_normalized(
    row: Mapping[str, Any], *, price_basis_row_group: str | None = None
) -> dict[str, Any]:
    """Build a row record from a ``normalize_daily`` row, reading the state field."""
    state = row.get("kbs.observed_daily_trading_value_state")
    if state is None:
        # A row from before the state field existed. It cannot be classified, and guessing
        # from the value would collapse omitted and null into one answer.
        raise TradingValueCoverageError(
            f"row_lacks_a_trading_value_state:{row.get('kbs.session_date')}"
        )
    value = row.get(FIELD)
    return row_coverage(
        session_date=row["kbs.session_date"],
        raw_state=str(state),
        value=value if str(state) in USABLE_STATES else None,
        price_basis_row_group=price_basis_row_group,
        normalized_field_present=True,
    )


# ---------------------------------------------------------------------------------
# Part B -- window-level coverage
# ---------------------------------------------------------------------------------

COVERAGE_COMPLETE = "complete"
COVERAGE_PARTIAL_KNOWN = "partial_known"
COVERAGE_ABSENT = "absent"
COVERAGE_CONFLICTED = "conflicted"
COVERAGE_UNKNOWN = "unknown"

COVERAGE_STATES = (
    COVERAGE_COMPLETE,
    COVERAGE_PARTIAL_KNOWN,
    COVERAGE_ABSENT,
    COVERAGE_CONFLICTED,
    COVERAGE_UNKNOWN,
)


def window_coverage(
    *,
    ticker: str,
    requested_window: Sequence[str],
    row_records: Sequence[Mapping[str, Any]],
    expected_sessions: Sequence[str] | None = None,
    expected_session_source: str | None = None,
) -> dict[str, Any]:
    """Aggregate row records into one window-level coverage statement.

    ``expected_sessions`` is optional and, when given, must name where it came from. The
    provider does not publish a trading calendar, so "how many sessions *should* have come
    back" is an outside input; leaving it unset makes ``requested_session_count`` equal the
    returned rows, which is honest but cannot detect a dropped session.
    """
    if expected_sessions is not None and not str(expected_session_source or "").strip():
        raise TradingValueCoverageError("expected_sessions_requires_a_named_source")

    counts = {state: 0 for state in ROW_STATES}
    usable_sessions: list[str] = []
    excluded: list[dict[str, str]] = []
    for record in row_records:
        state = assert_row_state(str(record["trading_value_field_state"]))
        counts[state] += 1
        if record["trading_value_usable_for_row_statistics"]:
            usable_sessions.append(str(record["session_date"]))
        else:
            excluded.append(
                {
                    "session_date": str(record["session_date"]),
                    "state": state,
                    "reason": str(record["exclusion_reason"]),
                }
            )

    returned = sorted(str(record["session_date"]) for record in row_records)
    missing_sessions: list[str] = []
    if expected_sessions is not None:
        missing_sessions = sorted(set(map(str, expected_sessions)) - set(returned))
        counts[STATE_ROW_MISSING] += len(missing_sessions)

    requested_count = (
        len(set(map(str, expected_sessions))) if expected_sessions is not None else len(returned)
    )
    usable_count = len(usable_sessions)
    denominator = requested_count
    ratio = round(usable_count / denominator, 6) if denominator else 0.0

    if denominator == 0:
        state = COVERAGE_UNKNOWN
    elif usable_count == denominator:
        state = COVERAGE_COMPLETE
    elif usable_count == 0:
        state = COVERAGE_ABSENT
    else:
        state = COVERAGE_PARTIAL_KNOWN

    return {
        "schema_version": VERSION,
        "provider": PROVIDER,
        "field": FIELD,
        "raw_field": RAW_FIELD,
        "ticker": str(ticker).upper(),
        "requested_window": [str(part) for part in requested_window],
        "requested_session_count": requested_count,
        "returned_row_count": len(returned),
        "present_numeric_count": counts[STATE_PRESENT_NUMERIC],
        "present_zero_count": counts[STATE_PRESENT_ZERO],
        "present_null_count": counts[STATE_PRESENT_NULL],
        "field_omitted_count": counts[STATE_FIELD_OMITTED],
        "malformed_count": counts[STATE_MALFORMED],
        "row_missing_count": counts[STATE_ROW_MISSING],
        "usable_count": usable_count,
        "covered_sessions": sorted(usable_sessions),
        "coverage_ratio": ratio,
        "missing_sessions": missing_sessions,
        "excluded_sessions": excluded,
        "coverage_state": state,
        "expected_session_source": expected_session_source,
    }


def merge_window_coverage(windows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Combine windows for one ticker. Disagreeing observations of one session conflict."""
    if not windows:
        return {"coverage_state": COVERAGE_UNKNOWN, "reason": "no_windows"}
    per_session: dict[str, set[str]] = {}
    for window in windows:
        for session in window["covered_sessions"]:
            per_session.setdefault(session, set()).add("usable")
        for item in window["excluded_sessions"]:
            per_session.setdefault(item["session_date"], set()).add("excluded")
    conflicted = sorted(session for session, kinds in per_session.items() if len(kinds) > 1)
    usable = sorted(session for session, kinds in per_session.items() if kinds == {"usable"})
    state = (
        COVERAGE_CONFLICTED
        if conflicted
        else COVERAGE_COMPLETE
        if len(usable) == len(per_session)
        else COVERAGE_ABSENT
        if not usable
        else COVERAGE_PARTIAL_KNOWN
    )
    return {
        "schema_version": VERSION,
        "sessions_seen": len(per_session),
        "covered_sessions": usable,
        "conflicted_sessions": conflicted,
        "coverage_state": state,
        "coverage_ratio": round(len(usable) / len(per_session), 6) if per_session else 0.0,
    }


# ---------------------------------------------------------------------------------
# Part B -- dataset / capability level
# ---------------------------------------------------------------------------------

CROSS_WINDOW_QUALIFIED = "qualified"
CROSS_WINDOW_LIMITED = "limited"
CROSS_WINDOW_UNAVAILABLE = "unavailable"


def dataset_coverage_contract(windows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The dataset-level statement, including what may never be turned on.

    ``automatic_imputation_authorized`` and ``missing_as_zero_authorized`` are constants.
    There is no input that flips them, because both would replace an observation about the
    provider with a number this repository invented.
    """
    states = {window["coverage_state"] for window in windows}
    if not windows:
        comparability = CROSS_WINDOW_UNAVAILABLE
    elif states == {COVERAGE_COMPLETE}:
        comparability = CROSS_WINDOW_QUALIFIED
    elif COVERAGE_CONFLICTED in states or states == {COVERAGE_ABSENT}:
        comparability = CROSS_WINDOW_UNAVAILABLE
    else:
        comparability = CROSS_WINDOW_LIMITED
    return {
        "schema_version": VERSION,
        "provider": PROVIDER,
        "field": FIELD,
        "trading_value_unit": "VND",
        "trading_value_unit_qualification": tiers.EMPIRICALLY_DEDUCED,
        "coverage_generalization": "limited_to_retained_windows",
        "causal_explanation": "unknown",
        "observed_association": OBSERVED_ASSOCIATION["association"],
        "automatic_imputation_authorized": False,
        "missing_as_zero_authorized": False,
        "cross_window_comparability": comparability,
        "window_coverage_states": sorted(states),
        "volume_market_scope": "unknown",
        "liquidity_actionable": False,
    }


# ---------------------------------------------------------------------------------
# The observed association -- recorded, never explained
# ---------------------------------------------------------------------------------

#: What the retained windows show, stated at exactly the width the evidence supports.
#:
#: The association is perfect across 66 sessions and that is genuinely striking, which is
#: precisely why it needs a guard rather than a paragraph: a perfect correlation is the most
#: tempting thing in the world to explain, and an explanation here would be a claim about
#: provider architecture that no observation in this repository can support.
OBSERVED_ASSOCIATION: dict[str, Any] = {
    "association": "va_missing_on_tested_empirically_adjusted_rows",
    "direction": "va absent on off-lattice / empirically adjusted rows; present on tested "
    "on-lattice rows",
    "sessions_observed": 66,
    "exceptions_observed": 0,
    "tickers": ["HPG", "VCB", "VNM"],
    "causal_explanation": "unknown",
    "provider_methodology": "unknown",
    "coverage_generalization": "limited_to_retained_windows",
    "qualification": tiers.OBSERVED_ONLY,
    "note": (
        "An association between two observed row properties. It does not establish that the "
        "provider removes va *because* a price was adjusted, that the two fields share a "
        "pipeline, or anything else about how KBS is built. A mechanism would need a "
        "first-party statement, which does not exist."
    ),
}

#: Phrasings that assert the mechanism. Kept as data so the audit is reproducible rather
#: than a one-off reading of the tree.
CAUSAL_OVERCLAIM_PATTERNS: tuple[str, ...] = (
    "omits it exactly where it restated prices",
    "omits va because",
    "removes va because",
    "drops va because",
    "because the price has been adjusted",
    "because prices are adjusted",
)


#: A phrasing correction against frozen artifacts. They are not edited -- an evidence
#: package that gets rewritten when the wording improves is not evidence. Every measurement
#: in them stands; what is corrected is an implication the wording carries.
CORRECTED_CAUSAL_FRAMING: dict[str, Any] = {
    "artifacts": [
        "operations-review/kbs-empirical-basis-20260804/KBS_EMPIRICAL_BASIS.md",
        "operations-review/kbs-empirical-basis-20260804/capability_matrix.json",
        "operations-review/kbs-empirical-basis-20260804/basis_summary.json",
        "operations-review/kbs-empirical-closeout-20260804/kbs_superseded_verdicts.json",
    ],
    "commits": ["4a07141", "800c746"],
    "asserted_framing": (
        "'the provider omits va exactly where it restated prices' and 'presence tracks the "
        "ex-right boundary'."
    ),
    "why_it_misleads": (
        "Both read as statements about what KBS does and why. The observation is that two "
        "row properties co-occur in the tested windows. Nothing observed distinguishes a "
        "provider that removes va when it adjusts, from two fields sourced independently "
        "that happen to align, from anything else."
    ),
    "corrected_framing": (
        "In the retained tested windows, va absence is perfectly associated with the "
        "empirically adjusted / off-lattice row group. The causal mechanism is unknown and "
        "the finding is not generalised outside the retained windows."
    ),
    "corrected_in_active_source": [
        "kbs_capability_matrix.CAPABILITY_MATRIX[kbs_descriptive_trading_value_statistics]",
        "docs/kbs_empirical_basis_qualification.md",
        "tools/run_kbs_empirical_basis.py",
    ],
    "measurements_changed": False,
    "evidence_changed": False,
    "artifacts_rewritten": False,
    "corrected_at": "2026-08-04",
    "corrected_by": "kbs_trading_value_coverage@1.0.0",
}


def assert_no_causal_claim(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Refuse a coverage record that has acquired a mechanism."""
    explanation = record.get("causal_explanation", "unknown")
    if explanation not in (None, "unknown"):
        raise TradingValueCoverageError(f"causal_explanation_is_not_established:{explanation}")
    if record.get("provider_methodology") not in (None, "unknown"):
        raise TradingValueCoverageError("provider_methodology_is_not_established")
    if record.get("coverage_generalization") not in (None, "limited_to_retained_windows"):
        raise TradingValueCoverageError(
            f"coverage_generalization_too_wide:{record.get('coverage_generalization')}"
        )
    return record


# ---------------------------------------------------------------------------------
# Part D -- operations and their coverage requirements
# ---------------------------------------------------------------------------------

REQUIRES_COMPLETE = "requires_complete_coverage"
PARTIAL_PERMITTED = "partial_permitted_when_labelled"
ROW_LEVEL = "row_level_only"
UNAVAILABLE_BY_CONTRACT = "unavailable_by_contract"

REASON_MARKET_SCOPE = "kbs_volume_market_composition_not_qualified"
REASON_COVERAGE = "trading_value_coverage_is_partial_and_the_claim_covers_a_whole_window"
REASON_SYNTHESIS = "would_require_synthesizing_an_unobserved_provider_value"

#: Every ``va``-touching operation and what coverage it needs. An unregistered operation is
#: refused, which is how a newly added one gets classified instead of inheriting whatever
#: the surrounding code was allowed to do.
OPERATION_REQUIREMENTS: dict[str, str] = {
    # row level -- no aggregation, no window claim
    "display_observed_trading_value": ROW_LEVEL,
    "row_implied_average_price": ROW_LEVEL,
    "trading_value_chart_with_gaps": ROW_LEVEL,
    "trading_value_presence_anomaly_detection": ROW_LEVEL,
    "coverage_report": ROW_LEVEL,
    # partial permitted, only with the scope label attached
    "average_trading_value": PARTIAL_PERMITTED,
    "rolling_trading_value": PARTIAL_PERMITTED,
    "trading_value_dispersion": PARTIAL_PERMITTED,
    "value_to_volume_ratio": PARTIAL_PERMITTED,
    "overlapping_session_research_comparison": PARTIAL_PERMITTED,
    # a whole-window claim -- needs the whole window
    "period_total_trading_value": REQUIRES_COMPLETE,
    "trading_value_growth": REQUIRES_COMPLETE,
    "turnover_for_period": REQUIRES_COMPLETE,
    "cross_period_trading_value_comparison": REQUIRES_COMPLETE,
    "trading_value_technical_indicator": REQUIRES_COMPLETE,
    # never, on these grounds
    "official_market_turnover": UNAVAILABLE_BY_CONTRACT,
    "official_vwap_claim": UNAVAILABLE_BY_CONTRACT,
    "negotiated_versus_matched_value_decomposition": UNAVAILABLE_BY_CONTRACT,
    "trading_value_liquidity_metric": UNAVAILABLE_BY_CONTRACT,
    "trading_value_capacity_metric": UNAVAILABLE_BY_CONTRACT,
    "market_impact_from_trading_value": UNAVAILABLE_BY_CONTRACT,
    "cross_ticker_trading_value_ranking": UNAVAILABLE_BY_CONTRACT,
    "synthesize_missing_trading_value_from_price_times_volume": UNAVAILABLE_BY_CONTRACT,
}

_UNAVAILABLE_REASONS: dict[str, str] = {
    "official_market_turnover": REASON_MARKET_SCOPE,
    "official_vwap_claim": REASON_MARKET_SCOPE,
    "negotiated_versus_matched_value_decomposition": REASON_MARKET_SCOPE,
    "trading_value_liquidity_metric": REASON_MARKET_SCOPE,
    "trading_value_capacity_metric": REASON_MARKET_SCOPE,
    "market_impact_from_trading_value": REASON_MARKET_SCOPE,
    "cross_ticker_trading_value_ranking": REASON_COVERAGE,
    "synthesize_missing_trading_value_from_price_times_volume": REASON_SYNTHESIS,
}

#: Attached to every permitted result.
REQUIRED_RESULT_FIELDS: tuple[str, ...] = (
    "provider",
    "coverage_state",
    "covered_session_count",
    "requested_session_count",
    "missing_or_excluded_sessions",
    "partial_coverage_warning",
)

#: A partial aggregate must carry all of these, or it is not distinguishable from a
#: complete one by anything except a reader's attention.
PARTIAL_RESULT_FIELDS: tuple[str, ...] = (
    "statistic_scope",
    "coverage_state",
    "covered_sessions",
    "excluded_sessions",
    "not_comparable_to_complete_period_total",
)

#: The canonical statistic-scope vocabulary, shared by the coverage contract and the export
#: seam so there is one spelling on both sides of the Producer/Consumer boundary.
SCOPE_SINGLE_ROW = "single_observed_row"
SCOPE_COMPLETE_WINDOW = "complete_requested_window"
SCOPE_OBSERVED_ROWS_ONLY = "observed_rows_only"
SCOPE_NOT_APPLICABLE = "not_applicable"

STATISTIC_SCOPES = (
    SCOPE_SINGLE_ROW,
    SCOPE_COMPLETE_WINDOW,
    SCOPE_OBSERVED_ROWS_ONLY,
    SCOPE_NOT_APPLICABLE,
)


def evaluate_operation(name: str, *, coverage: Mapping[str, Any]) -> dict[str, Any]:
    """Decide one operation against one window's coverage."""
    requirement = OPERATION_REQUIREMENTS.get(name)
    if requirement is None:
        return {
            "operation": name,
            "allowed": False,
            "requirement": "unregistered",
            "reason": "operation_not_classified_in_kbs_trading_value_coverage",
            "reopen_condition": "classify_the_operation_in_OPERATION_REQUIREMENTS",
            "liquidity_actionable": False,
        }
    state = coverage.get("coverage_state", COVERAGE_UNKNOWN)

    if requirement == UNAVAILABLE_BY_CONTRACT:
        return {
            "operation": name,
            "allowed": False,
            "requirement": requirement,
            "reason": _UNAVAILABLE_REASONS[name],
            "coverage_state": state,
            "liquidity_actionable": False,
        }
    if requirement == ROW_LEVEL:
        # Row-level use survives any window state: it makes no claim about the window. A
        # chart with visible gaps is more honest than no chart, not less.
        return {
            "operation": name,
            "allowed": state != COVERAGE_UNKNOWN,
            "requirement": requirement,
            "statistic_scope": SCOPE_OBSERVED_ROWS_ONLY,
            "coverage_state": state,
            "reason": None if state != COVERAGE_UNKNOWN else "coverage_not_established",
            "liquidity_actionable": False,
        }
    if requirement == REQUIRES_COMPLETE:
        allowed = state == COVERAGE_COMPLETE
        return {
            "operation": name,
            "allowed": allowed,
            "requirement": requirement,
            "statistic_scope": SCOPE_COMPLETE_WINDOW if allowed else None,
            "coverage_state": state,
            "reason": None if allowed else REASON_COVERAGE,
            "alternative": None if allowed else "rename_and_structure_the_output_as_partial",
            "liquidity_actionable": False,
        }
    # PARTIAL_PERMITTED
    allowed = state in {COVERAGE_COMPLETE, COVERAGE_PARTIAL_KNOWN}
    return {
        "operation": name,
        "allowed": allowed,
        "requirement": requirement,
        "statistic_scope": SCOPE_OBSERVED_ROWS_ONLY,
        "coverage_state": state,
        "requires_labels": list(PARTIAL_RESULT_FIELDS) if state == COVERAGE_PARTIAL_KNOWN else [],
        "reason": None if allowed else "no_usable_observation_in_the_window",
        "liquidity_actionable": False,
    }


def build_result(
    *, operation: str, value: Any, coverage: Mapping[str, Any]
) -> dict[str, Any]:
    """Wrap a computed statistic with the coverage metadata it is required to carry.

    Construction is the enforcement point. There is no path that produces a number without
    its coverage, because the number and the metadata are made in the same call.
    """
    decision = evaluate_operation(operation, coverage=coverage)
    if not decision["allowed"]:
        raise TradingValueCoverageError(
            f"operation_not_permitted:{operation}:{decision.get('reason')}"
        )
    state = coverage["coverage_state"]
    partial = state == COVERAGE_PARTIAL_KNOWN
    excluded = [item["session_date"] for item in coverage.get("excluded_sessions", [])]
    result = {
        "operation": operation,
        "value": value,
        "provider": PROVIDER,
        "source_authority": SOURCE_AUTHORITY,
        "field": FIELD,
        "trading_value_unit": "VND",
        "trading_value_unit_qualification": tiers.EMPIRICALLY_DEDUCED,
        "coverage_state": state,
        "statistic_scope": decision.get("statistic_scope"),
        "covered_session_count": coverage["usable_count"],
        "requested_session_count": coverage["requested_session_count"],
        "covered_sessions": list(coverage.get("covered_sessions", [])),
        "excluded_sessions": excluded,
        "missing_or_excluded_sessions": sorted(
            set(excluded) | set(coverage.get("missing_sessions", []))
        ),
        "coverage_ratio": coverage["coverage_ratio"],
        "partial_coverage_warning": (
            "Computed over observed rows only; this is not a complete-window figure."
            if partial
            else None
        ),
        "not_comparable_to_complete_period_total": bool(partial),
        "causal_explanation": "unknown",
        "coverage_generalization": "limited_to_retained_windows",
        "liquidity_actionable": False,
    }
    return assert_result_labelled(result)


def assert_result_labelled(result: Mapping[str, Any]) -> dict[str, Any]:
    """Refuse a result that is missing its coverage metadata, or mislabelled."""
    missing = [field for field in REQUIRED_RESULT_FIELDS if field not in result]
    if missing:
        raise TradingValueCoverageError(f"result_missing_coverage_fields:{','.join(missing)}")
    state = result.get("coverage_state")
    if state not in COVERAGE_STATES:
        raise TradingValueCoverageError(f"result_coverage_state_invalid:{state}")
    if state == COVERAGE_PARTIAL_KNOWN:
        absent = [field for field in PARTIAL_RESULT_FIELDS if field not in result]
        if absent:
            raise TradingValueCoverageError(f"partial_result_missing_labels:{','.join(absent)}")
        if result.get("statistic_scope") != SCOPE_OBSERVED_ROWS_ONLY:
            raise TradingValueCoverageError("partial_result_must_declare_observed_rows_only")
        if not result.get("not_comparable_to_complete_period_total"):
            raise TradingValueCoverageError("partial_result_must_declare_incomparability")
        if not result.get("partial_coverage_warning"):
            raise TradingValueCoverageError("partial_result_must_carry_its_warning")
    if state != COVERAGE_COMPLETE and result.get("statistic_scope") == SCOPE_COMPLETE_WINDOW:
        raise TradingValueCoverageError("only_complete_coverage_may_claim_a_complete_window")

    # The label is checked against the numbers it carries, not taken on trust. Otherwise the
    # one relabelling that matters -- flipping coverage_state to complete *and* scope to
    # complete_window together -- passes every individual check, and a partial statistic
    # arrives indistinguishable from a whole-window one. A result that says it covered
    # fewer sessions than it requested is not complete, whatever its state field says.
    covered = result.get("covered_session_count")
    requested = result.get("requested_session_count")
    if isinstance(covered, int) and isinstance(requested, int):
        if state == COVERAGE_COMPLETE and covered < requested:
            raise TradingValueCoverageError(
                f"coverage_state_contradicts_its_own_counts:complete_but_{covered}_of_{requested}"
            )
        if state == COVERAGE_ABSENT and covered:
            raise TradingValueCoverageError("absent_coverage_cannot_report_covered_sessions")
        if covered > requested:
            raise TradingValueCoverageError("covered_sessions_exceed_requested_sessions")
        if result.get("missing_or_excluded_sessions") and state == COVERAGE_COMPLETE:
            raise TradingValueCoverageError(
                "complete_coverage_cannot_carry_missing_or_excluded_sessions"
            )
    if result.get("liquidity_actionable"):
        raise TradingValueCoverageError("liquidity_actionable_must_stay_false")
    return dict(result)


def sum_observed(row_records: Sequence[Mapping[str, Any]]) -> float:
    """Sum the usable observations. Deliberately not called "total"."""
    return float(
        sum(
            record["trading_value_value"]
            for record in row_records
            if record["trading_value_usable_for_row_statistics"]
        )
    )


def mean_observed(row_records: Sequence[Mapping[str, Any]]) -> float | None:
    usable = [
        record["trading_value_value"]
        for record in row_records
        if record["trading_value_usable_for_row_statistics"]
    ]
    return float(sum(usable) / len(usable)) if usable else None


# ---------------------------------------------------------------------------------
# Part E -- no synthesis, ever
# ---------------------------------------------------------------------------------

#: The identity a derived price x volume figure would have to use *if* it were ever
#: authorized. Reserved and defined here so the name exists and is visibly not ``va``;
#: nothing in this milestone populates it.
RECONSTRUCTED_FIELD = "kbs.reconstructed_price_times_volume"

RECONSTRUCTED_FIELD_CONTRACT: dict[str, Any] = {
    "field": RECONSTRUCTED_FIELD,
    "source_field": "derived",
    "provider_observed_trading_value": False,
    "historical_interpretation": "unsupported",
    "implemented": False,
    "authorized": False,
    "why_it_is_not_va": (
        "On exactly the rows where va is absent, the retained price is an empirically "
        "adjusted price. Price x volume there is not a restated turnover and not a "
        "historical one -- it is a product of a number the provider restated and a number "
        "it did not, whose meaning nobody has established."
    ),
}


def assert_no_synthetic_trading_value(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Refuse any attempt to present a derived product as the provider's ``va``.

    The unit work proved that ``va / v`` lands inside the session range. That validated the
    *unit*; it is not a licence to run the identity backwards and manufacture ``va`` where
    the provider sent none.
    """
    for key in (FIELD, "trading_value_value", "va", "kbs.raw_va"):
        if key in record and record.get("source_field") == "derived":
            raise TradingValueCoverageError(f"derived_value_written_into_an_observed_field:{key}")
    if record.get("field") == RECONSTRUCTED_FIELD:
        if record.get("provider_observed_trading_value"):
            raise TradingValueCoverageError("reconstructed_field_claims_to_be_provider_observed")
        if record.get("historical_interpretation") not in (None, "unsupported"):
            raise TradingValueCoverageError("reconstructed_field_claims_historical_support")
        if record.get("authorized"):
            raise TradingValueCoverageError("reconstructed_field_is_not_authorized")
    if record.get("imputed") or record.get("filled_from_price_times_volume"):
        raise TradingValueCoverageError("trading_value_imputation_is_not_authorized")
    return record


def impute(*_args: Any, **_kwargs: Any) -> None:
    """There is no imputation path. Present so the refusal has an address."""
    raise TradingValueCoverageError(
        "trading_value_imputation_is_not_authorized:"
        "missing_va_is_an_observation_about_the_provider_not_a_gap_to_fill"
    )


# ---------------------------------------------------------------------------------
# Part F -- consumer and export gates
# ---------------------------------------------------------------------------------

#: Consumers that actually read KBS ``va``.
#:
#: This map was written at ``ee057b9`` from an assumption and is now written from a trace.
#: The corrected answer is that **there are none**: ``va`` is dropped by the vnstock adapter
#: before the pipeline sees it, the ``ohlcv`` table has no value column, and no exported
#: artifact carries one. See :data:`ACTIVE_EXPORT_PATH`. The four "trading value" consumers
#: previously listed here read no ``va``, and two of them named concepts that do not exist.
#:
#: The entries that remain are the *forbidden* ones. They are kept deliberately: they name
#: uses that would be refused if anyone built them, and a register that only lists what
#: exists cannot refuse anything.
CONSUMER_REQUIREMENTS: dict[str, str] = {
    "opportunity_ranking.turnover_rank": UNAVAILABLE_BY_CONTRACT,
    "risk_liquidity.turnover_liquidity": UNAVAILABLE_BY_CONTRACT,
}

#: Quantities that look like a trading value, are not ``va``, and cross the boundary today.
#:
#: ``gtgd20_ty`` is the real one. It is a 20-session rolling mean of ``close x volume`` in
#: billion VND, computed in ``candlestick_patterns.py`` over the *stored* OHLCV series --
#: overwhelmingly VCI rows -- and it never references ``va``. The closeout at ``ee057b9``
#: stated that no existing consumer creates a price-times-volume field. That was wrong, and
#: this register is the correction: the field exists, it is derived, and it is labelled here
#: so nobody reads it as an observed provider trading value.
#:
#: It is *not* disabled. It reconstructs no missing ``va`` -- it is an independent screening
#: metric that predates this lane, and its volume-side classification already lives in
#: ``market_volume_capability_matrix`` as analytical-not-liquidity. Relabelling is the
#: proportionate action; removing a working screen on the strength of a naming collision
#: would not be.
NON_VA_DERIVED_QUANTITIES: dict[str, dict[str, Any]] = {
    "candlestick_patterns.gtgd20_ty_calc": {
        "expression": "(close * volume).rolling(20, min_periods=3).mean() / 1e9",
        "unit": "billion_VND_per_session",
        "source_field": "derived",
        "reads_kbs_va": False,
        "provider_observed_trading_value": False,
        "is_official_turnover": False,
        "predominant_price_source": "VCI stored ohlcv rows",
        "volume_side_classification": "market_volume_capability_matrix: analytical, "
        "explicitly not qualified market liquidity",
        "must_not_be_labelled": [
            "kbs.observed_daily_trading_value",
            "official_market_turnover",
            "qualified_liquidity",
        ],
    }
}


def classify_derived_quantity(name: str) -> dict[str, Any]:
    """Describe a trading-value-shaped derived quantity, or refuse to recognise it."""
    record = NON_VA_DERIVED_QUANTITIES.get(name)
    if record is None:
        raise TradingValueCoverageError(f"unregistered_derived_quantity:{name}")
    return dict(record)


def assert_derived_quantity_not_relabelled(name: str, *, label: str) -> None:
    """A derived quantity may not be handed an observed-value or official-turnover name."""
    record = classify_derived_quantity(name)
    if label in record["must_not_be_labelled"]:
        raise TradingValueCoverageError(f"derived_quantity_relabelled_as_observed:{name}->{label}")


def classify_consumer(consumer_id: str) -> dict[str, Any]:
    """Classify a trading-value consumer. Unregistered means refused, not permitted."""
    requirement = CONSUMER_REQUIREMENTS.get(consumer_id)
    if requirement is None:
        return {
            "consumer": consumer_id,
            "allowed": False,
            "requirement": "unregistered",
            "reason": "consumer_not_classified_in_kbs_trading_value_coverage",
            "reopen_condition": "classify_the_consumer_in_CONSUMER_REQUIREMENTS",
        }
    return {
        "consumer": consumer_id,
        "allowed": requirement != UNAVAILABLE_BY_CONTRACT,
        "requirement": requirement,
        "required_result_fields": list(REQUIRED_RESULT_FIELDS),
        "reason": _UNAVAILABLE_REASONS.get(consumer_id)
        if requirement == UNAVAILABLE_BY_CONTRACT
        else None,
    }


def gate_legacy_payload(payload: Mapping[str, Any], *, operation: str) -> dict[str, Any]:
    """A payload written before coverage metadata existed cannot support a window claim.

    Row-level display still works -- the numbers in it are real. What it cannot do is
    underwrite an aggregate, because "no coverage block" and "full coverage" are
    indistinguishable in it, and the safe reading of that ambiguity is the pessimistic one.
    """
    has_coverage = "coverage_state" in payload
    requirement = OPERATION_REQUIREMENTS.get(operation)
    if has_coverage:
        return {"operation": operation, "allowed": True, "legacy": False}
    if requirement == ROW_LEVEL:
        return {
            "operation": operation,
            "allowed": True,
            "legacy": True,
            "coverage_state": COVERAGE_UNKNOWN,
            "note": "Row-level display only; the payload carries no coverage block.",
        }
    return {
        "operation": operation,
        "allowed": False,
        "legacy": True,
        "coverage_state": COVERAGE_UNKNOWN,
        "reason": "legacy_payload_without_coverage_metadata_cannot_support_an_aggregate_claim",
    }


def assert_consumer_did_not_upgrade(
    *, producer_coverage: Mapping[str, Any], consumer_coverage: Mapping[str, Any]
) -> None:
    """A consumer may narrow coverage. It may never widen it."""
    order = {
        COVERAGE_UNKNOWN: 0,
        COVERAGE_CONFLICTED: 0,
        COVERAGE_ABSENT: 1,
        COVERAGE_PARTIAL_KNOWN: 2,
        COVERAGE_COMPLETE: 3,
    }
    produced = order.get(str(producer_coverage.get("coverage_state")), 0)
    consumed = order.get(str(consumer_coverage.get("coverage_state")), 0)
    if consumed > produced:
        raise TradingValueCoverageError(
            "consumer_upgraded_coverage:"
            f"{producer_coverage.get('coverage_state')}->{consumer_coverage.get('coverage_state')}"
        )
    if consumer_coverage.get("usable_count", 0) > producer_coverage.get("usable_count", 0):
        raise TradingValueCoverageError("consumer_reported_more_covered_sessions_than_the_producer")


#: Fields that carry no provider namespace and therefore cannot inherit this verdict.
GENERIC_VALUE_FIELDS = frozenset(
    {
        "value",
        "trading_value",
        "turnover",
        "market_turnover",
        "total_value",
        "official_market_turnover",
        "exchange_turnover",
    }
)


def assert_no_generic_field_upgrade(field_name: str) -> None:
    if str(field_name).strip().lower() in GENERIC_VALUE_FIELDS:
        raise TradingValueCoverageError(
            f"generic_value_field_cannot_inherit_kbs_coverage:{field_name}"
        )


def assert_no_provider_inheritance(other_provider: str) -> None:
    if str(other_provider).strip().upper() == PROVIDER:
        return
    raise TradingValueCoverageError(
        f"kbs_trading_value_coverage_does_not_transfer:{str(other_provider).strip().upper()}"
    )


# ---------------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------------


def contract_snapshot(windows: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """The whole contract as data, for the closeout artifact and for diffing."""
    dataset = dataset_coverage_contract(windows)
    return {
        "schema_version": VERSION,
        "provider": PROVIDER,
        "source_authority": SOURCE_AUTHORITY,
        "field": FIELD,
        "raw_field": RAW_FIELD,
        "row_states": list(ROW_STATES),
        "usable_states": sorted(USABLE_STATES),
        "coverage_states": list(COVERAGE_STATES),
        "operation_requirements": dict(sorted(OPERATION_REQUIREMENTS.items())),
        "consumer_requirements": dict(sorted(CONSUMER_REQUIREMENTS.items())),
        "required_result_fields": list(REQUIRED_RESULT_FIELDS),
        "partial_result_fields": list(PARTIAL_RESULT_FIELDS),
        "observed_association": dict(OBSERVED_ASSOCIATION),
        "corrected_causal_framing": dict(CORRECTED_CAUSAL_FRAMING),
        "reconstructed_field_contract": dict(RECONSTRUCTED_FIELD_CONTRACT),
        "dataset": dataset,
    }


def assert_contract_fail_closed(snapshot: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Refuse a contract that has opened something it may not open."""
    snap = snapshot if snapshot is not None else contract_snapshot()
    dataset = snap["dataset"]
    if dataset["automatic_imputation_authorized"] or dataset["missing_as_zero_authorized"]:
        raise TradingValueCoverageError("imputation_must_stay_unauthorized")
    if dataset["liquidity_actionable"]:
        raise TradingValueCoverageError("liquidity_actionable_must_stay_false")
    if dataset["volume_market_scope"] != "unknown":
        raise TradingValueCoverageError("trading_value_coverage_must_not_set_market_scope")
    assert_no_causal_claim(dataset)
    assert_no_causal_claim(snap["observed_association"])
    if snap["reconstructed_field_contract"]["authorized"]:
        raise TradingValueCoverageError("reconstructed_field_must_stay_unauthorized")
    if STATE_PRESENT_ZERO not in snap["usable_states"]:
        raise TradingValueCoverageError("a_real_zero_is_an_observation_and_must_stay_usable")
    return snap
