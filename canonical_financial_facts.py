"""Layer 3 of the market-wide pipeline: raw observations -> canonical financial facts.

WHAT THIS IS
    The mapping layer `docs/market_wide_financial_normalization_contract.md` specifies and
    layers 1-2 deliberately left unbuilt. It takes the fully-provenanced raw observations
    retained by `raw_financial_store.py`, resolves each canonical metric against the two
    provider dialects, applies the scope/sign/scale/basis resolvers in
    `canonical_financial_resolvers.py`, and emits one canonical fact per
    (ticker x metric x period x frequency) carrying every dimension needed to decide whether
    it may be used -- or an explicit reason it may not.

THE SIX STATUSES, AND WHY `provider_reported` IS THE HONEST MARKET-WIDE CEILING

    qualified          identity resolved, coherence demonstrated, AND the value agrees
                       digit-for-digit with an independently qualified official citation.
                       Currency and absolute scale come from that citation. Nothing else
                       reaches this status, because nothing else can: see below.
    provider_reported  identity unambiguous, no conflict, internal coherence demonstrated,
                       but currency and absolute unit scale remain unevidenced. This is a
                       legitimate screening tier and is what most of the universe reaches.
    partial            resolved but with a material gap -- a substituted concept, a derived
                       value missing a component, or a resolver the metric needs returning
                       `unknown`.
    conflicted         candidate observations disagree, a period variant disagrees with the
                       primary column, or a coherence gate the metric depends on failed.
    unavailable        no supported raw observation exists for this metric.
    not_applicable     the metric is undefined for this filer's template family. A bank has
                       no EBITDA, and no input will ever produce one.

    A status is never upgraded because a normalized label matched. Label match establishes
    *candidacy*; the resolvers establish everything else.

WHY SO LITTLE REACHES `qualified`
    The retained payloads carry no currency column, no unit header, and no anchor that fixes
    the absolute unit. Vietnamese listed issuers do file in VND under VAS -- that is a
    convention, not evidence in these bytes, and the contract forbids promoting a convention
    to a qualified fact. `qualified` therefore requires agreement with the independently
    promoted official citations in `data/official-evidence/`, which today exist for HPG and
    VNM only. The gap is a citation-coverage gap, and it is reported as one rather than
    papered over with an assumption that happens to be true.

DIALECT IS A PROPERTY OF THE VOCABULARY, NOT OF THE `source` COLUMN
    The contract describes the split as two providers with two vocabularies, which reads as
    though the payload's `source` column selects the dialect. The retained bytes disagree:
    HPG's income statement carries `source = KBS` and the full **VCI** vocabulary
    (`of_which_interest_expense`, `deduction_from_revenue`, `net_profit`). Keying the mapping
    on the provider string therefore drops every metric on that payload -- verified against
    HPG before this module was written.

    So candidate matching keys on the raw item id alone, which is what actually discriminates:
    the two vocabularies are mutually exclusive, which is the property the contract
    established. The dialect is still recorded on every fact, and `detect_dialect` reports the
    dialect a payload's vocabulary evidences, so the coverage report can break every metric
    down by dialect and make a future single-dialect regression visible instead of silent.

CONCEPTS ARE NEVER SILENTLY EQUATED
    `interest_expense` accrued on the income statement and `interest_paid` in the cash-flow
    statement are different quantities. The cash-flow line is accepted only as a lower-
    priority substitute, and doing so forces `partial` and records
    `concept_substitution` in the fact's warnings. The same applies to `amortization`, for
    which the only retained cash-flow line is goodwill amortization -- a strict subset of
    total amortization, and labelled as such.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from canonical_financial_resolvers import (
    UNKNOWN,
    VERSION as RESOLVER_VERSION,
    period_bounds,
    resolve_balance_identity,
    resolve_cross_statement_scale,
    resolve_cumulative_state,
    resolve_currency_and_scale,
    resolve_sign_convention,
    resolve_statement_scope,
)

SCHEMA_VERSION = "1.1.0"
#: Bumped 2026-09-01: STRUCTURED_FINANCIAL_DEPTH_RECOVERY_V1 added `current_assets`,
#: `current_liabilities`, and the finance-lease metrics to METRIC_REGISTRY without bumping
#: this version, so `canonical_fact_store`'s incremental fingerprint (which keys on this
#: value, not on METRIC_REGISTRY's own content) never invalidated the persisted store built
#: under the old registry -- every shard kept reporting `unchanged` and silently continued
#: to omit these metrics even though the mapping and the retained raw observations were both
#: already correct. See the module docstring's "keying only on source payload hashes" warning.
#: Bumped again 2026-09-02: MARKET_WIDE_GROSS_MARGIN_DEPTH_V1 added `gross_profit`.
#: Bumped again 2026-09-05: FINANCIAL_TEMPORAL_SEMANTIC_NORMALIZATION_AND_ANALYTICAL_PANEL_V1
#: changed `_fact()`'s `observed_at` construction (see `_normalize_observed_at`) -- this must
#: invalidate every existing shard, or `canonical_fact_store`'s incremental fingerprint (keyed
#: on this string, not on the mapper's actual behavior) reports every shard `unchanged` and the
#: store keeps serving facts built by the old, timezone-naive `observed_at` logic forever.
MAPPER_VERSION = "1.4.0"
CONTRACT_VERSION = "market-wide-financial-normalization/1.0.0"

#: Retained payloads stamped `scraped_at` as a naive "YYYY-MM-DD HH:MM" Asia/Ho_Chi_Minh
#: wall-clock string before this milestone (see `bctc_sync.normalize_report`/`vn_time.vn_now`).
#: No source timestamp is ever fabricated here -- this only reattaches the offset that value
#: always implicitly carried, so a strict tz-aware parser (`bitemporal_semantic_contract.py`)
#: can accept an observation timestamp that was already correct except for its representation.
_LEGACY_NAIVE_SCRAPED_AT = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
_SCRAPED_AT_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def _normalize_observed_at(raw: Any) -> str | None:
    """Canonicalize a raw observation's `scraped_at` into a timezone-aware ISO-8601 string.

    Idempotent: an already-ISO-8601 value (future syncs, once `bctc_sync.py` emits
    `vn_time.vn_now_iso()` directly) passes through unchanged. Anything not a non-empty string
    stays `None` -- a missing source timestamp is never converted into a fabricated one.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    if _LEGACY_NAIVE_SCRAPED_AT.match(raw):
        try:
            naive = datetime.strptime(raw, "%Y-%m-%d %H:%M")
        except ValueError:
            return raw
        return naive.replace(tzinfo=_SCRAPED_AT_TIMEZONE).isoformat()
    return raw

STATUS_QUALIFIED = "qualified"
STATUS_PROVIDER_REPORTED = "provider_reported"
STATUS_PARTIAL = "partial"
STATUS_CONFLICTED = "conflicted"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NOT_APPLICABLE = "not_applicable"

SUPPORTED_STATUSES = (
    STATUS_QUALIFIED, STATUS_PROVIDER_REPORTED, STATUS_PARTIAL,
    STATUS_CONFLICTED, STATUS_UNAVAILABLE, STATUS_NOT_APPLICABLE,
)

#: Dialects observed in the retained payloads. `common` matches either provider.
DIALECT_VCI = "vci_a"
DIALECT_KBS = "kbs_b"
DIALECT_COMMON = "common"

#: Vocabulary markers that evidence which dialect a payload is written in. These name items
#: that exist in one vocabulary and not the other; they are used for reporting and regression
#: detection, never to filter candidates (see the module docstring).
DIALECT_MARKERS: dict[str, dict[str, tuple[str, ...]]] = {
    "income_statement": {
        DIALECT_VCI: ("of_which_interest_expense", "deduction_from_revenue", "admin_expenses"),
        DIALECT_KBS: ("net_sales", "cost_of_sales", "interest_expenses",
                      "net_accounting_profit_loss_before_tax"),
    },
    "cash_flow": {
        DIALECT_VCI: ("depreciation_of_fixed_assets_and_investment_properties",
                      "operating_cash_flow", "borrowing_costs",
                      "payment_for_fixed_assets_constructions_and_other_long_term_assets"),
        DIALECT_KBS: ("depreciation_and_amortization",
                      "net_cash_inflows_outflows_from_operating_activities", "interest_paid",
                      "purchases_of_fixed_assets_and_other_long_term_assets"),
    },
    "balance_sheet": {
        DIALECT_VCI: ("undistributed_earnings", "owners_other_capital",
                      "minority_interests_before_2015"),
        DIALECT_KBS: ("total_liabilities", "liabilities_and_shareholders_equity",
                      "charter_capital"),
    },
}


def detect_dialect(statement_family: str, raw_item_ids: Iterable[str]) -> str:
    """Which vocabulary a payload is written in, from the items it actually carries.

    Returns `vci_a`, `kbs_b`, `mixed` (both vocabularies evidenced -- a real anomaly worth
    surfacing) or `unknown`. Deliberately independent of the payload's `source` column, which
    the retained bytes show does not determine the vocabulary.
    """
    markers = DIALECT_MARKERS.get(str(statement_family))
    if not markers:
        return UNKNOWN
    present = {str(item).strip() for item in raw_item_ids}
    hits = sorted(dialect for dialect, names in markers.items()
                  if any(name in present for name in names))
    if not hits:
        return UNKNOWN
    if len(hits) > 1:
        return "mixed"
    return hits[0]


class _Candidate:
    """One raw identity that may carry a canonical metric, under one dialect.

    `occurrence` pins which repetition of a repeated `item_id` is meant. The contract records
    that 15.4% of retained observations sit on a repeated id and that a rule keyed on
    `raw_item_id` alone is incorrect by construction; `revenue` is the worst case, appearing
    as both gross and net revenue on the same income statement.
    """

    __slots__ = ("statement_family", "raw_item_id", "dialect", "priority", "occurrence",
                 "concept", "note", "required_provider")

    def __init__(self, statement_family: str, raw_item_id: str, dialect: str, priority: int,
                 *, occurrence: int | None = None, concept: str = "exact", note: str = "",
                 required_provider: str | None = None) -> None:
        self.statement_family = statement_family
        self.raw_item_id = raw_item_id
        self.dialect = dialect
        self.priority = priority
        self.occurrence = occurrence
        self.concept = concept          # "exact" | "substitute" | "narrower"
        self.note = note
        # Almost every candidate matches on raw item id alone (see module docstring:
        # dialect is a vocabulary property, not a provider filter). A small number of
        # metrics are deliberately narrower than their vocabulary: `gross_profit` shares
        # its raw item id across both providers' retained payloads, but only KBS's
        # income-statement quarter carries the provider+statement-family period contract
        # `structured_financial_period_semantics.py` recognizes as `STANDALONE_QUARTER`
        # (VCI's flow-statement duration remains unresolved -- see
        # `VCI_PERIOD_DURATION_REMAINS_UNKNOWN` in docs/STATE.md). Restricting the
        # candidate itself keeps that boundary enforced at canonicalization time rather
        # than relying only on a downstream consumer to notice.
        self.required_provider = required_provider


def _c(*args: Any, **kwargs: Any) -> _Candidate:
    return _Candidate(*args, **kwargs)


BS, IS, CF = "balance_sheet", "income_statement", "cash_flow"

#: The canonical metric registry. Priority orders candidates within a metric; the highest
#: priority candidate present in the payload's own dialect wins, and a lower-priority
#: candidate that also matched is recorded as a corroboration or a conflict.
METRIC_REGISTRY: dict[str, dict[str, Any]] = {
    "revenue": {
        "statement": IS,
        # `revenue` repeats on the VCI income statement -- gross on the first line, net after
        # deductions on the last. Which occurrence is canonical is settled by
        # `_resolve_revenue` from the statement's own arithmetic, never by a pinned line
        # number, which is not stable across filers.
        "candidates": [
            _c(IS, "revenue", DIALECT_VCI, 100),
            _c(IS, "net_sales", DIALECT_KBS, 95),
            _c(IS, "sales", DIALECT_KBS, 80, concept="substitute",
               note="gross sales before deductions"),
        ],
        "revenue_resolution": True,
    },
    "gross_profit": {
        "statement": IS,
        # The retained payloads carry `gross_profit` under the *same* raw item id
        # regardless of which provider produced the file (verified against the full
        # retained income-statement corpus: 1,365 KBS files and 47 VCI files both carry
        # this exact id). Matching would otherwise silently canonicalize the VCI files
        # too -- exactly the "opportunistic VCI gross profit" mapping this milestone's
        # scope forbids, since VCI's income-statement duration is unresolved the same
        # way its cash-flow duration is (`VCI_PERIOD_DURATION_REMAINS_UNKNOWN`).
        # `required_provider` keeps this metric KBS-only until a provider is
        # independently qualified with its own duration evidence.
        "candidates": [
            _c(IS, "gross_profit", DIALECT_KBS, 100, required_provider="KBS"),
        ],
    },
    "profit_before_tax": {
        "statement": IS,
        "candidates": [
            _c(IS, "profit_before_tax", DIALECT_VCI, 100),
            _c(IS, "net_accounting_profit_loss_before_tax", DIALECT_KBS, 95),
            _c(IS, "total_profit_before_tax", DIALECT_COMMON, 80),
        ],
    },
    "net_income": {
        "statement": IS,
        "candidates": [
            _c(IS, "net_profit", DIALECT_VCI, 100),
            _c(IS, "net_profit_loss_after_tax", DIALECT_KBS, 95),
            _c(IS, "profit_after_tax", DIALECT_COMMON, 80),
        ],
    },
    "attributable_net_income": {
        "statement": IS,
        "candidates": [
            _c(IS, "profit_after_tax_for_shareholders_of_parent_company", DIALECT_VCI, 100),
            _c(IS, "attributable_to_parent_company", DIALECT_KBS, 95),
            _c(IS, "profit_after_tax_for_shareholders_of_the_parents_company", DIALECT_COMMON, 90),
            _c(IS, "profit_after_tax_for_shareholders_of_the_parent_company", DIALECT_COMMON, 90),
            _c(IS, "net_profit_atttributable_to_the_equity_holders_of_the_bank", DIALECT_COMMON, 85),
        ],
    },
    "total_assets": {
        "statement": BS,
        "candidates": [_c(BS, "total_assets", DIALECT_COMMON, 100)],
    },
    "shareholders_equity": {
        "statement": BS,
        "candidates": [
            _c(BS, "owners_equity", DIALECT_COMMON, 100),
            _c(BS, "capital_and_reserves", DIALECT_COMMON, 90, concept="substitute",
               note="capital and reserves subtotal, may exclude other equity components"),
        ],
    },
    "retained_earnings": {
        "statement": BS,
        "candidates": [_c(BS, "undistributed_earnings", DIALECT_COMMON, 100)],
    },
    "cash_and_cash_equivalents": {
        "statement": BS,
        "candidates": [_c(BS, "cash_and_cash_equivalents", DIALECT_COMMON, 100)],
    },
    "current_assets": {
        "statement": BS,
        "candidates": [_c(BS, "current_assets", DIALECT_COMMON, 100)],
    },
    "current_liabilities": {
        "statement": BS,
        "candidates": [_c(BS, "current_liabilities", DIALECT_COMMON, 100)],
    },
    "short_term_interest_bearing_debt": {
        "statement": BS,
        "candidates": [_c(BS, "short_term_borrowings", DIALECT_COMMON, 100)],
    },
    "long_term_interest_bearing_debt": {
        "statement": BS,
        "candidates": [_c(BS, "long_term_borrowings", DIALECT_COMMON, 100)],
    },
    "short_term_finance_lease_liabilities": {
        "statement": BS,
        "candidates": [_c(BS, "short_term_finance_lease", DIALECT_COMMON, 100)],
    },
    "long_term_finance_lease_liabilities": {
        "statement": BS,
        "candidates": [_c(BS, "long_term_financial_lease", DIALECT_COMMON, 100)],
    },
    "finance_lease_liabilities": {
        "statement": BS,
        "candidates": [],
        "derived_from": ("short_term_finance_lease_liabilities", "long_term_finance_lease_liabilities"),
        "derivation": "sum",
    },
    "total_interest_bearing_debt": {
        "statement": BS,
        "candidates": [],
        "derived_from": ("short_term_interest_bearing_debt", "long_term_interest_bearing_debt"),
        "derivation": "sum",
    },
    "interest_expense": {
        "statement": IS,
        "candidates": [
            _c(IS, "of_which_interest_expense", DIALECT_VCI, 100),
            _c(IS, "interest_expenses", DIALECT_KBS, 95),
            # Cash paid is not accrued expense. Accepted only as a substitute, which forces
            # `partial` and records `concept_substitution`.
            _c(CF, "borrowing_costs", DIALECT_VCI, 60, concept="substitute",
               note="cash-flow add-back, not the accrued income-statement expense"),
            _c(CF, "interest_expenses_paid", DIALECT_VCI, 55, concept="substitute",
               note="cash interest paid, not accrued expense"),
            _c(CF, "interest_expense", DIALECT_KBS, 58, concept="substitute",
               note="cash-flow add-back, not the accrued income-statement expense"),
            _c(CF, "interest_paid", DIALECT_KBS, 50, concept="substitute",
               note="cash interest paid, not accrued expense"),
        ],
    },
    "depreciation": {
        "statement": CF,
        "candidates": [
            _c(CF, "depreciation_of_fixed_assets_and_investment_properties", DIALECT_VCI, 100),
        ],
    },
    "amortization": {
        "statement": CF,
        "candidates": [
            # The only retained amortization lines are goodwill-specific: a strict subset of
            # total amortization, never a stand-in for it.
            _c(CF, "amortization_of_goodwill", DIALECT_KBS, 60, concept="narrower",
               note="goodwill amortization only; not total amortization"),
            _c(CF, "allocation_of_goodwill", DIALECT_KBS, 55, concept="narrower",
               note="goodwill allocation only; not total amortization"),
        ],
    },
    "depreciation_and_amortization": {
        "statement": CF,
        "candidates": [
            _c(CF, "depreciation_and_amortization", DIALECT_KBS, 100),
            # The VCI dialect reports depreciation alone; goodwill amortization, when
            # retained, is a separate line. Summing them is a documented derivation, not a
            # relabelling, so it is expressed as a fallback derivation rather than a candidate.
            _c(CF, "depreciation_of_fixed_assets_and_investment_properties", DIALECT_VCI, 90,
               concept="narrower",
               note="VCI dialect reports depreciation only; amortization is a separate line"),
        ],
    },
    "operating_cash_flow": {
        "statement": CF,
        "candidates": [
            _c(CF, "operating_cash_flow", DIALECT_VCI, 100),
            _c(CF, "net_cash_inflows_outflows_from_operating_activities", DIALECT_KBS, 100),
        ],
    },
    "capital_expenditure": {
        "statement": CF,
        "candidates": [
            _c(CF, "payment_for_fixed_assets_constructions_and_other_long_term_assets",
               DIALECT_VCI, 100),
            _c(CF, "purchases_of_fixed_assets_and_other_long_term_assets", DIALECT_KBS, 100),
        ],
    },
    "shares_outstanding": {
        "statement": BS,
        # No retained line carries a share *count*. `common_shares` and `paid_in_capital` are
        # VND amounts of paid-in capital; deriving a count from them requires assuming a
        # 10,000 VND par value, which is a convention this layer may not promote. The metric
        # is therefore structurally `unavailable` from provider payloads, and is qualified
        # only from official share-basis citations.
        "candidates": [],
        "unavailable_reason": (
            "no retained provider line carries a share count; `common_shares` and "
            "`paid_in_capital` are paid-in capital amounts in currency, and converting them "
            "to a count requires assuming a par value, which is a convention rather than "
            "evidence. Qualified share counts come from official share-basis citations only."
        ),
    },
}

#: Metrics whose value combines a balance-sheet and a cash-flow or income-statement number,
#: and which therefore depend on the cross-statement coherence gate.
CROSS_STATEMENT_DEPENDENT = frozenset({"total_interest_bearing_debt"})

#: Metrics defined only for the corporate earnings model. Mirrors
#: `financial_entity_applicability.CORPORATE_ONLY_METRICS` at the fact layer.
_CORPORATE_ONLY_STATEMENT_METRICS = frozenset()

_PERIOD_RE = re.compile(r"^(?P<year>\d{4})(?:-Q(?P<quarter>[1-4]))?$")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _observed_dialects(records: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Dialect evidenced by each statement family present in one period's records."""
    by_family: dict[str, list[str]] = {}
    for record in records:
        by_family.setdefault(str(record["statement_family"]), []).append(
            str(record["raw_item_id"]))
    return {family: detect_dialect(family, ids) for family, ids in by_family.items()}


def _index_observations(observations: Iterable[Mapping[str, Any]]) -> dict[tuple, list[dict]]:
    """Group observations by (statement_family, reporting_period, period_variant_index)."""
    grouped: dict[tuple, list[dict]] = {}
    for observation in observations:
        key = (str(observation["statement_family"]),
               str(observation["reporting_period"]),
               int(observation["period_variant_index"]))
        grouped.setdefault(key, []).append(dict(observation))
    return grouped


def _item_map(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """First occurrence of each raw item id -> raw value, for the resolvers."""
    items: dict[str, Any] = {}
    for record in sorted(records, key=lambda r: (int(r["item_id_occurrence"]), int(r["row_ordinal"]))):
        items.setdefault(str(record["raw_item_id"]), record["raw_value"])
    return items


def _match_candidates(metric: str, definition: Mapping[str, Any],
                      records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every candidate that matches an observation, with its dialect check applied."""
    by_id: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        by_id.setdefault(str(record["raw_item_id"]), []).append(record)

    # Matching keys on the raw item id, never on the payload's `source` column: the two
    # vocabularies are mutually exclusive, and the provider string does not select between
    # them (HPG's income statement is `source = KBS` written in the VCI vocabulary).
    matches: list[dict[str, Any]] = []
    for candidate in definition.get("candidates", []):
        for record in by_id.get(candidate.raw_item_id, []):
            if str(record["statement_family"]) != candidate.statement_family:
                continue
            if candidate.occurrence is not None and int(record["item_id_occurrence"]) != candidate.occurrence:
                continue
            if (candidate.required_provider is not None
                    and str(record.get("provider") or "").upper() != candidate.required_provider):
                continue
            matches.append({"candidate": candidate, "observation": record,
                            "dialect": candidate.dialect})
    matches.sort(key=lambda match: (-match["candidate"].priority,
                                    match["observation"]["raw_item_id"],
                                    int(match["observation"]["item_id_occurrence"])))
    return matches


def _variant_conflict(metric: str, definition: Mapping[str, Any],
                      grouped: Mapping[tuple, list[dict]], statement: str,
                      period: str) -> dict[str, Any] | None:
    """Whether a restated (suffixed) period column disagrees with the primary column.

    Layer 1 retains duplicate period columns as restatement candidates and never collapses
    them. A disagreement between them is a genuine conflict about what the period's value is,
    and it is resolved here by refusing to pick one.
    """
    primary = grouped.get((statement, period, 0))
    if primary is None:
        return None
    primary_match = _match_candidates(metric, definition, primary)
    if not primary_match:
        return None
    primary_value = primary_match[0]["observation"]["raw_value"]

    for (family, reporting_period, variant), records in sorted(grouped.items()):
        if family != statement or reporting_period != period or variant == 0:
            continue
        variant_match = _match_candidates(metric, definition, records)
        if not variant_match:
            continue
        variant_value = variant_match[0]["observation"]["raw_value"]
        try:
            differs = abs(float(primary_value) - float(variant_value)) > max(
                1e-9, abs(float(primary_value)) * 1e-9)
        except (TypeError, ValueError):
            differs = primary_value != variant_value
        if differs:
            return {
                "period_variant_index": variant,
                "primary_value": primary_value,
                "variant_value": variant_value,
                "variant_observation_id": variant_match[0]["observation"]["observation_id"],
            }
    return None


def _resolve_revenue(matches: Sequence[Mapping[str, Any]],
                     records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Decide which `revenue` occurrence is the canonical net top line.

    The VCI income statement lays out gross revenue, then `deduction_from_revenue`, then net
    revenue -- all three under ids that repeat. Picking a line number is fragile, so the
    choice is made from the arithmetic: if `gross - deductions` reconciles to a later
    occurrence, that occurrence is net revenue and is canonical. If the statement carries
    deductions but no reconciling net line, net revenue is derived and the fact degrades to
    `partial`. If deductions reconcile to nothing and no second occurrence exists, the single
    retained line is used as reported.

    Reconciliation is allowed a thousand-unit tolerance: the retained payloads round to the
    nearest thousand, so an exact-integer test would reject a correct reconciliation.
    """
    warnings: list[str] = []
    conflicts: list[dict[str, Any]] = []
    primary = matches[0]["observation"]
    revenue_rows = sorted(
        (record for record in records
         if str(record["raw_item_id"]) == str(primary["raw_item_id"])),
        key=lambda record: int(record["item_id_occurrence"]))
    deduction = next((record for record in records
                      if str(record["raw_item_id"]) == "deduction_from_revenue"), None)

    if deduction is None or len(revenue_rows) < 1:
        return {"value": primary["raw_value"], "observation": primary, "net_of": None,
                "warnings": warnings, "conflicts": conflicts, "degrade_to_partial": False,
                "reason": ""}

    gross = revenue_rows[0]
    try:
        expected = float(gross["raw_value"]) - float(deduction["raw_value"])
    except (TypeError, ValueError):
        return {"value": primary["raw_value"], "observation": primary, "net_of": None,
                "warnings": warnings, "conflicts": conflicts, "degrade_to_partial": False,
                "reason": ""}

    for candidate_row in revenue_rows[1:]:
        try:
            actual = float(candidate_row["raw_value"])
        except (TypeError, ValueError):
            continue
        if abs(actual - expected) <= max(1000.0, abs(expected) * 1e-9):
            warnings.append("revenue_net_of_deductions_reconciled")
            return {"value": candidate_row["raw_value"], "observation": candidate_row,
                    "net_of": "deduction_from_revenue", "warnings": warnings,
                    "conflicts": conflicts, "degrade_to_partial": False, "reason": ""}

    if len(revenue_rows) > 1:
        conflicts.append({
            "kind": "revenue_occurrences_do_not_reconcile_with_deductions",
            "gross": gross["raw_value"], "deductions": deduction["raw_value"],
            "expected_net": expected,
            "occurrences": [row["raw_value"] for row in revenue_rows],
        })
        return {"value": gross["raw_value"], "observation": gross, "net_of": None,
                "warnings": warnings, "conflicts": conflicts, "degrade_to_partial": False,
                "reason": ""}

    net = int(expected) if float(expected).is_integer() else expected
    warnings.append("revenue_net_derived_from_deductions")
    return {"value": net, "observation": gross, "net_of": "deduction_from_revenue",
            "warnings": warnings, "conflicts": conflicts, "degrade_to_partial": True,
            "reason": ("net revenue derived as gross revenue less deductions; no reconciling "
                       "net revenue line is retained")}


def _official_agreement(official_citations: Mapping[tuple, Mapping[str, Any]] | None,
                        ticker: str, metric: str, period: str, value: Any) -> dict[str, Any] | None:
    """Whether an independently qualified official citation reports this exact value."""
    if not official_citations:
        return None
    citation = official_citations.get((ticker.upper(), metric, str(period)))
    if citation is None:
        return None
    try:
        agrees = abs(float(citation["value"]) - float(value)) <= max(
            1e-9, abs(float(citation["value"])) * 1e-9)
    except (TypeError, ValueError, KeyError):
        return None
    return {
        "agrees": agrees,
        "citation_id": citation.get("citation_id"),
        "evidence_id": citation.get("evidence_id"),
        "currency": citation.get("currency"),
        "scale": citation.get("scale", "units"),
        "official_value": citation.get("value"),
    }


def _confidence(status: str, concept: str, resolved: Mapping[str, Any]) -> float:
    """A bounded, deterministic confidence. Never a probability, and never a signal."""
    base = {
        STATUS_QUALIFIED: 1.0,
        STATUS_PROVIDER_REPORTED: 0.6,
        STATUS_PARTIAL: 0.35,
        STATUS_CONFLICTED: 0.0,
        STATUS_UNAVAILABLE: 0.0,
        STATUS_NOT_APPLICABLE: 0.0,
    }[status]
    if status in {STATUS_CONFLICTED, STATUS_UNAVAILABLE, STATUS_NOT_APPLICABLE}:
        return 0.0
    if concept == "substitute":
        base -= 0.15
    elif concept == "narrower":
        base -= 0.10
    if resolved.get("statement_scope") == UNKNOWN:
        base -= 0.05
    if resolved.get("sign_convention") == UNKNOWN:
        base -= 0.05
    return round(max(0.0, min(1.0, base)), 4)


def build_facts(ticker: str, observations: Iterable[Mapping[str, Any]], *,
                applicability: Mapping[str, Any] | None = None,
                official_citations: Mapping[tuple, Mapping[str, Any]] | None = None,
                metrics: Iterable[str] | None = None) -> dict[str, Any]:
    """Every canonical fact this ticker's retained observations support.

    Pure: no I/O, no clock. `observations` is one ticker's shard;
    `applicability` is a `financial_entity_applicability.evaluate_ticker` result;
    `official_citations` maps `(ticker, metric, period)` onto a qualified official value.
    """
    ticker = str(ticker).upper()
    grouped = _index_observations(observations)
    wanted = list(metrics) if metrics is not None else list(METRIC_REGISTRY)

    metric_applicability = dict((applicability or {}).get("metric_applicability") or {})

    # Per-period resolver evidence, computed once and shared by every metric in the period.
    periods = sorted({period for _, period, variant in grouped if variant == 0})
    cash_flow_by_period = {
        period: _item_map(grouped.get((CF, period, 0), []))
        for period in periods
    }
    cumulative = resolve_cumulative_state(cash_flow_by_period)

    period_evidence: dict[str, dict[str, Any]] = {}
    for period in periods:
        bs_items = _item_map(grouped.get((BS, period, 0), []))
        is_items = _item_map(grouped.get((IS, period, 0), []))
        cf_items = cash_flow_by_period.get(period, {})
        period_evidence[period] = {
            "scope": resolve_statement_scope(bs_items),
            "sign": resolve_sign_convention(is_items),
            "balance_identity": resolve_balance_identity(bs_items),
            "cross_statement": resolve_cross_statement_scale(bs_items, cf_items),
        }

    facts: list[dict[str, Any]] = []
    for period in periods:
        evidence = period_evidence[period]
        for metric in wanted:
            definition = METRIC_REGISTRY.get(metric)
            if definition is None:
                continue
            fact = _build_one(
                ticker=ticker, metric=metric, definition=definition, period=period,
                grouped=grouped, evidence=evidence, cumulative=cumulative,
                metric_applicability=metric_applicability,
                official_citations=official_citations, facts_so_far=facts)
            if fact is not None:
                facts.append(fact)

    facts.sort(key=lambda fact: (fact["reporting_period"], fact["canonical_metric"]))
    payload_dialects = _observed_dialects([record for records in grouped.values()
                                           for record in records])
    return {
        "schema_version": SCHEMA_VERSION,
        "mapper_version": MAPPER_VERSION,
        "contract_version": CONTRACT_VERSION,
        "resolver_version": RESOLVER_VERSION,
        "ticker": ticker,
        "reporting_periods": periods,
        "cumulative_state": cumulative,
        "payload_dialects": payload_dialects,
        "facts": facts,
        "status_counts": _status_counts(facts),
    }


def _status_counts(facts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in SUPPORTED_STATUSES}
    for fact in facts:
        counts[str(fact["status"])] = counts.get(str(fact["status"]), 0) + 1
    return counts


def _build_one(*, ticker: str, metric: str, definition: Mapping[str, Any], period: str,
               grouped: Mapping[tuple, list[dict]], evidence: Mapping[str, Any],
               cumulative: Mapping[str, Any], metric_applicability: Mapping[str, Any],
               official_citations: Mapping[tuple, Mapping[str, Any]] | None,
               facts_so_far: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    statement = str(definition["statement"])
    warnings: list[str] = []
    conflicts: list[dict[str, Any]] = []

    scope = evidence["scope"]["statement_scope"]
    sign = evidence["sign"]["sign_convention"]
    basis = cumulative["cumulative_state"]
    balance_identity = evidence["balance_identity"]["balance_identity"]
    cross_statement = evidence["cross_statement"]["cross_statement_scale"]

    resolved = {"statement_scope": scope, "sign_convention": sign, "cumulative_state": basis}

    # 1. Applicability closes the question before inputs are considered.
    applicability = metric_applicability.get(metric)
    if applicability and applicability.get("status") == "not_applicable":
        return _fact(
            ticker=ticker, metric=metric, definition=definition, period=period,
            status=STATUS_NOT_APPLICABLE, observation=None, candidate=None,
            value=None, evidence=evidence, cumulative=cumulative,
            reason=applicability.get("reason", "metric is not defined for this filer"),
            warnings=["metric_not_defined_for_template_family"], conflicts=[],
            authority=applicability.get("authority"),
            substitute_metrics=applicability.get("substitute_metrics") or [])

    # 2. Derived metrics are assembled from already-built facts of the same period.
    if definition.get("derived_from"):
        return _build_derived(
            ticker=ticker, metric=metric, definition=definition, period=period,
            evidence=evidence, cumulative=cumulative, facts_so_far=facts_so_far,
            cross_statement=cross_statement)

    # Candidates may live on a different statement from the metric's declared home:
    # `interest_expense` prefers the income statement but falls back to a cash-flow add-back.
    # Scoping the lookup to `definition["statement"]` alone would make that fallback
    # unreachable and report `unavailable` for a metric the payload does carry.
    candidate_statements = {candidate.statement_family
                            for candidate in definition.get("candidates", [])} or {statement}
    records = [record for family in sorted(candidate_statements)
               for record in grouped.get((family, period, 0), [])]
    matches = _match_candidates(metric, definition, records)
    if not matches:
        reason = definition.get("unavailable_reason") or (
            f"no retained {statement} observation matches any canonical candidate for "
            f"{metric} in the payload's dialect")
        return _fact(
            ticker=ticker, metric=metric, definition=definition, period=period,
            status=STATUS_UNAVAILABLE, observation=None, candidate=None, value=None,
            evidence=evidence, cumulative=cumulative, reason=reason,
            warnings=["no_supported_observation"], conflicts=[], authority=None,
            substitute_metrics=[])

    chosen = matches[0]
    candidate = chosen["candidate"]
    observation = chosen["observation"]
    value = observation["raw_value"]
    # Coherence gates below key on where the value actually came from, not on where the
    # metric nominally lives.
    statement = candidate.statement_family

    # 3. Two *different* raw identities of equal priority that disagree are a conflict, not a
    #    tie to be broken. Two occurrences of the *same* id are an occurrence-disambiguation
    #    problem, which the metric's own resolver handles (see `_resolve_revenue`).
    for other in matches[1:]:
        if other["candidate"].priority != candidate.priority:
            continue
        if other["candidate"].raw_item_id == candidate.raw_item_id:
            continue
        other_value = other["observation"]["raw_value"]
        try:
            differs = abs(float(value) - float(other_value)) > max(
                1e-9, abs(float(value)) * 1e-9)
        except (TypeError, ValueError):
            differs = value != other_value
        if differs:
            conflicts.append({
                "kind": "equal_priority_candidates_disagree",
                "chosen_raw_item_id": candidate.raw_item_id,
                "other_raw_item_id": other["candidate"].raw_item_id,
                "chosen_value": value, "other_value": other_value,
            })

    # 4. Gross-vs-net revenue, settled by the statement's own arithmetic.
    net_of_note = None
    if definition.get("revenue_resolution"):
        resolution = _resolve_revenue(matches, records)
        value = resolution["value"]
        observation = resolution["observation"]
        net_of_note = resolution["net_of"]
        warnings.extend(resolution["warnings"])
        conflicts.extend(resolution["conflicts"])
        if resolution["degrade_to_partial"]:
            candidate = _Candidate(IS, str(observation["raw_item_id"]), candidate.dialect,
                                   candidate.priority, concept="substitute",
                                   note=resolution["reason"])

    # 5. A restated period column that disagrees with the primary one is a conflict.
    variant = _variant_conflict(metric, definition, grouped, statement, period)
    if variant is not None:
        conflicts.append({"kind": "restated_period_column_disagrees", **variant})

    if observation.get("warnings"):
        for flag in observation["warnings"]:
            if flag in {"ambiguous_raw_item_id", "duplicate_period_column", "raw_item_id_absent"}:
                warnings.append(f"source_{flag}")

    # 6. Coherence gates.
    if statement == BS and balance_identity == "violated":
        conflicts.append({"kind": "balance_sheet_identity_violated",
                          "detail": evidence["balance_identity"]["reason"]})
    if metric in CROSS_STATEMENT_DEPENDENT and cross_statement == "divergent":
        conflicts.append({"kind": "cross_statement_scale_divergent",
                          "detail": evidence["cross_statement"]["reason"]})

    # The cash-flow payload's period labels are not independently trustworthy. HPG's
    # cash-flow column labelled `2025-Q2` carries an end-of-period cash balance that matches
    # the *2026-Q1* balance sheet, so the label does not identify the period the numbers
    # describe. End-of-period cash is the only cross-check the retained payloads offer, so a
    # cash-flow fact is period-attributable only when that check passes: a divergence is a
    # conflict, and an unavailable check caps the fact at `partial`. Without this gate a
    # depreciation figure from one quarter would silently be combined with a profit figure
    # from another.
    if statement == CF:
        if cross_statement == "divergent":
            conflicts.append({"kind": "cash_flow_period_attribution_unverified",
                              "detail": evidence["cross_statement"]["reason"]})
        elif cross_statement == UNKNOWN:
            warnings.append("cash_flow_period_attribution_unverifiable")
        elif cross_statement == "coherent_thousand_rounded":
            warnings.append("cash_flow_precision_reduced_to_thousands")

    # 7. Status. `agreement` is resolved once, after any value adjustment in step 4, so the
    #    qualification branch and the disagreement check below cannot diverge.
    agreement = _official_agreement(official_citations, ticker, metric, period, value)

    if conflicts:
        status = STATUS_CONFLICTED
        reason = "; ".join(sorted(conflict["kind"] for conflict in conflicts))
    else:
        currency_scale = resolve_currency_and_scale(agreement)
        if candidate.concept != "exact":
            status = STATUS_PARTIAL
            warnings.append("concept_substitution" if candidate.concept == "substitute"
                            else "narrower_concept_than_canonical_metric")
            reason = candidate.note or f"{metric} resolved from a {candidate.concept} concept"
        elif agreement and agreement.get("agrees"):
            status = STATUS_QUALIFIED
            reason = currency_scale["reason"]
        elif scope == UNKNOWN and statement == BS:
            status = STATUS_PROVIDER_REPORTED
            reason = ("identity resolved and balance-sheet arithmetic coherent; statement "
                      "scope, currency and unit scale remain unevidenced")
        else:
            status = STATUS_PROVIDER_REPORTED
            reason = ("identity resolved with no conflict; currency and unit scale remain "
                      "unevidenced by the retained payload")
        if status == STATUS_PARTIAL and agreement and agreement.get("agrees"):
            reason += f"; value agrees with official citation {agreement.get('citation_id')}"
        if ("cash_flow_period_attribution_unverifiable" in warnings
                and status == STATUS_PROVIDER_REPORTED):
            status = STATUS_PARTIAL
            reason = ("identity resolved, but no end-of-period cash line is retained on both "
                      "statements, so the period this cash-flow value describes cannot be "
                      "confirmed against the balance sheet")

    # An official citation that reports a different number is a conflict, never an override:
    # the provider value is not silently replaced by the audited one.
    if agreement is not None and not agreement.get("agrees"):
        conflicts.append({
            "kind": "official_citation_disagrees",
            "citation_id": agreement.get("citation_id"),
            "official_value": agreement.get("official_value"), "provider_value": value,
        })
        status = STATUS_CONFLICTED
        reason = "official_citation_disagrees"

    currency_scale = resolve_currency_and_scale(
        agreement if status != STATUS_CONFLICTED else None)

    if scope == UNKNOWN:
        warnings.append("statement_scope_unknown")
    if currency_scale["currency"] == UNKNOWN:
        warnings.append("currency_unknown")
    if currency_scale["scale"] == UNKNOWN:
        warnings.append("unit_scale_unknown")
    if sign == UNKNOWN:
        warnings.append("sign_convention_unknown")
    if basis == UNKNOWN and statement in {IS, CF}:
        warnings.append("cumulative_basis_unknown")

    return _fact(
        ticker=ticker, metric=metric, definition=definition, period=period, status=status,
        observation=observation, candidate=candidate, value=value, evidence=evidence,
        cumulative=cumulative, reason=reason, warnings=warnings, conflicts=conflicts,
        authority=currency_scale["authority"], substitute_metrics=[],
        currency=currency_scale["currency"], scale=currency_scale["scale"],
        net_of=net_of_note)


def _build_derived(*, ticker: str, metric: str, definition: Mapping[str, Any], period: str,
                   evidence: Mapping[str, Any], cumulative: Mapping[str, Any],
                   facts_so_far: Sequence[Mapping[str, Any]],
                   cross_statement: str) -> dict[str, Any]:
    """A metric assembled from other canonical facts of the same period."""
    components = definition["derived_from"]
    found = {
        fact["canonical_metric"]: fact for fact in facts_so_far
        if fact["reporting_period"] == period and fact["canonical_metric"] in components
    }
    missing = [name for name in components if name not in found]
    usable = {STATUS_QUALIFIED, STATUS_PROVIDER_REPORTED, STATUS_PARTIAL}
    unusable = [name for name, fact in found.items() if fact["status"] not in usable]

    if missing or unusable:
        blocking = sorted(missing + unusable)
        status = (STATUS_CONFLICTED
                  if any(found.get(name, {}).get("status") == STATUS_CONFLICTED
                         for name in unusable)
                  else STATUS_UNAVAILABLE)
        return _fact(
            ticker=ticker, metric=metric, definition=definition, period=period, status=status,
            observation=None, candidate=None, value=None, evidence=evidence,
            cumulative=cumulative,
            reason=f"derivation blocked by component(s): {', '.join(blocking)}",
            warnings=["derivation_component_unavailable"], conflicts=[], authority=None,
            substitute_metrics=[], derived_from=list(components))

    total = 0.0
    for name in components:
        total += float(found[name]["value"])
    value = int(total) if float(total).is_integer() else total

    statuses = {found[name]["status"] for name in components}
    if statuses == {STATUS_QUALIFIED}:
        status = STATUS_QUALIFIED
    elif STATUS_PARTIAL in statuses:
        status = STATUS_PARTIAL
    else:
        status = STATUS_PROVIDER_REPORTED

    warnings = ["derived_metric"]
    currencies = {found[name]["currency"] for name in components}
    scales = {found[name]["scale"] for name in components}
    if len(currencies) > 1 or len(scales) > 1:
        return _fact(
            ticker=ticker, metric=metric, definition=definition, period=period,
            status=STATUS_CONFLICTED, observation=None, candidate=None, value=None,
            evidence=evidence, cumulative=cumulative,
            reason="components disagree on currency or unit scale",
            warnings=warnings, conflicts=[{"kind": "component_unit_mismatch",
                                           "currencies": sorted(map(str, currencies)),
                                           "scales": sorted(map(str, scales))}],
            authority=None, substitute_metrics=[], derived_from=list(components))

    currency = next(iter(currencies))
    scale = next(iter(scales))
    if currency == UNKNOWN:
        warnings.append("currency_unknown")
    if scale == UNKNOWN:
        warnings.append("unit_scale_unknown")
    if evidence["scope"]["statement_scope"] == UNKNOWN:
        warnings.append("statement_scope_unknown")

    return _fact(
        ticker=ticker, metric=metric, definition=definition, period=period, status=status,
        observation=None, candidate=None, value=value, evidence=evidence,
        cumulative=cumulative,
        reason=f"{definition['derivation']} of {', '.join(components)}",
        warnings=warnings, conflicts=[],
        authority=next(iter({found[name]["unit_authority"] for name in components})
                       if len({found[name]["unit_authority"] for name in components}) == 1
                       else [None]),
        substitute_metrics=[], currency=currency, scale=scale,
        derived_from=list(components),
        source_observation_ids=sorted(
            observation_id
            for name in components
            for observation_id in (found[name]["source_observation_ids"] or [])),
    )


def _fact(*, ticker: str, metric: str, definition: Mapping[str, Any], period: str, status: str,
          observation: Mapping[str, Any] | None, candidate: _Candidate | None, value: Any,
          evidence: Mapping[str, Any], cumulative: Mapping[str, Any], reason: str,
          warnings: Sequence[str], conflicts: Sequence[Mapping[str, Any]],
          authority: Any, substitute_metrics: Sequence[str],
          currency: str = UNKNOWN, scale: str = UNKNOWN, net_of: str | None = None,
          derived_from: Sequence[str] | None = None,
          source_observation_ids: Sequence[str] | None = None) -> dict[str, Any]:
    """Assemble one canonical fact with every contract dimension present."""
    basis = cumulative["cumulative_state"]
    bounds = period_bounds(period, basis)
    scope = evidence["scope"]["statement_scope"]
    sign = evidence["sign"]["sign_convention"]

    identity = {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "canonical_metric": metric,
        "reporting_period": period,
        # The statement the value actually came from, which is not always the metric's
        # declared home (see the cross-statement candidate note in `_build_one`).
        "statement_family": str((observation or {}).get("statement_family")
                                or definition["statement"]),
        "mapper_version": MAPPER_VERSION,
    }

    fact = {
        **identity,
        "fact_id": _fingerprint({**identity, "value": value, "status": status}),
        "identity_key": _fingerprint(identity),
        "contract_version": CONTRACT_VERSION,
        "resolver_version": RESOLVER_VERSION,

        "provider": (observation or {}).get("provider"),
        "dialect": candidate.dialect if candidate else ("derived" if derived_from else None),
        "source_file": (observation or {}).get("source_file"),
        "source_sha256": (observation or {}).get("source_sha256"),
        "raw_item_id": candidate.raw_item_id if candidate else None,
        "raw_item_occurrence": (observation or {}).get("item_id_occurrence"),
        "raw_label_vi": (observation or {}).get("raw_label_vi"),
        "raw_label_en": (observation or {}).get("raw_label_en"),
        "source_observation_ids": (list(source_observation_ids) if source_observation_ids
                                   else ([observation["observation_id"]] if observation else [])),
        "observed_at": _normalize_observed_at((observation or {}).get("scraped_at")),
        # Retain provider-native report metadata distinctly from canonical period bounds.
        # The mapper must never treat VCI `lengthReport` as a duration inference.
        "provider_report_metadata": dict((observation or {}).get("provider_report_metadata") or {}),

        "reporting_frequency": (observation or {}).get("reporting_frequency"),
        "period_type": "quarterly" if "-Q" in period else "annual",
        "period_start": bounds["period_start"],
        "period_end": bounds["period_end"],
        # Preserve explicit upstream duration metadata when a retained observation carries it.
        # Existing VCI/KBS parquet observations do not, so their canonical value remains
        # unknown; no reporting-period label is used to fill it here.
        "flow_period_basis": (observation or {}).get("flow_period_basis", UNKNOWN),
        "flow_period_basis_evidence": (observation or {}).get("flow_period_basis_evidence"),
        "duration_months": (observation or {}).get("duration_months"),

        "statement_scope": scope,
        "statement_scope_reason": evidence["scope"]["reason"],
        "currency": currency,
        "scale": scale,
        "unit_authority": authority if not isinstance(authority, list) else (authority[0] if authority else None),
        "sign_convention": sign,
        "cumulative_state": basis,
        "cumulative_state_reason": cumulative["reason"],
        "balance_identity": evidence["balance_identity"]["balance_identity"],
        "cross_statement_scale": evidence["cross_statement"]["cross_statement_scale"],

        "value": value,
        "status": status,
        "reason": reason,
        "confidence": _confidence(status, candidate.concept if candidate else "exact",
                                  {"statement_scope": scope, "sign_convention": sign}),
        "warnings": sorted(set(warnings)),
        "conflicts": list(conflicts),
        "substitute_metrics": list(substitute_metrics),
        "derived_from": list(derived_from) if derived_from else None,
        "net_of_raw_item_id": net_of,
        "qualification_state": status,
    }
    return fact
