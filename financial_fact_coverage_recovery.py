"""Current financial-fact coverage recovery and scale-out.

Follow-on inside the existing current-fundamental / current-valuation evidence lane. This module
adds no new financial model, valuation engine, or provider. It exists because
``market_wide_current_fundamental_research.py`` only ever examines a frozen 523-name "empirical
active cohort" snapshot from 2026-08-20, while the retained raw/canonical financial stores it reads
from (``market-wide-financials`` / ``canonical-financial-facts``) already carry observations for
1,493 tickers -- 972 of them with a usable retained fact and never looked at, purely because they
fall outside that frozen cohort's membership list.

Three already-existing, already-tested, deterministic build functions are reused completely
unmodified, only fed a wider (but still retained-evidence-bounded) ticker membership:

* ``p3f10_fundamental_evidence_scaleout.build_scaleout_artifact`` -- generic per-ticker raw/
  canonical disposition, already parameterized by ``cohort``/``raw_records``/``canonical_records``,
  never scoped to any hardcoded cohort inside the function itself.
* ``p3f13_official_financial_evidence_scaleout.build_scaleout_artifact`` -- generic official-tier
  acquisition-disposition check against the already-retained governed manifest, already
  parameterized by ``p3f10_artifact``.
* ``market_wide_current_fundamental_research.build_artifact`` -- the generic per-ticker entity
  classification, trajectory context, and authority-tier assembly, already parameterized by
  ``p3f10_frozen``/``p3f13_current``.

Widening the membership list does not call a new provider, does not acquire a new document, and
does not promote a single ticker to official authority: the official 13-issuer panel is untouched
(only its own coverage rerun, byte-for-byte identical regardless of cohort width). It only lets
tickers with already-retained-but-previously-ignored raw/canonical facts receive the same
disposition, entity-classification, and provider-research trend treatment already given to the 523
frozen names -- and lets tickers with genuinely no retained observation say so explicitly, instead
of being silently absent from the artifact altogether.
"""
from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import market_wide_current_fundamental_research as mwcfr
import p3f10_fundamental_evidence_scaleout as p3f10mod
import p3f13_official_financial_evidence_scaleout as p3f13mod
from field_temporal_contract import stable_id

CONTRACT_VERSION = "financial_fact_coverage_recovery/v1"
ARTIFACT_TYPE = "FINANCIAL_FACT_COVERAGE_RECOVERY"

# The exact identity names already used by the existing valuation contract
# (market_wide_current_valuation_input_scaleout.EARNINGS_IDENTITY_BY_ENTITY /
# EQUITY_IDENTITY_BY_ENTITY) plus the P3-B CORE_METRICS names and the three retained EBITDA
# components (profit_before_tax + interest_expense + depreciation_and_amortization, per the
# existing derived-EBITDA formula). No alias is invented for coverage.
CORPORATE_IDENTITIES: tuple[str, ...] = (
    "revenue", "net_income", "shareholders_equity", "total_assets",
    "cash_and_cash_equivalents", "total_interest_bearing_debt",
    "profit_before_tax", "interest_expense", "depreciation_and_amortization",
)
REQUIRED_IDENTITIES_BY_ENTITY: dict[str, tuple[str, ...]] = {
    "corporate": CORPORATE_IDENTITIES,
    "bank": ("net_profit_parent", "total_equity"),
    "securities": ("profit_after_tax_parent", "total_equity"),
    # Neither market_wide_current_valuation_input_scaleout.EARNINGS_IDENTITY_BY_ENTITY nor
    # EQUITY_IDENTITY_BY_ENTITY defines an entry for these two archetypes: the existing valuation
    # contract has no defined financial-identity requirement for them at all (every non-market_cap
    # metric is already NOT_APPLICABLE). This module does not invent one.
    "insurance": (),
    "finance_company": (),
    "unknown": (),
}
# The five identities `market_wide_current_fundamental_research.PROVIDER_SERIES_METRICS` already
# derives a bounded same-provider trend for.
_PROVIDER_SERIES_SOURCE_METRICS = {item[1] for item in mwcfr.PROVIDER_SERIES_METRICS}
_PROVIDER_SERIES_METRIC_ID_BY_SOURCE = {item[1]: item[0] for item in mwcfr.PROVIDER_SERIES_METRICS}

#: A canonical fact row with one of these statuses is a retained, usable observation. `unavailable`
#: rows exist in the shard (one row per requested metric/period) but carry no retained value at all
#: -- reusing p3f10_fundamental_evidence_scaleout's own `usable_fact_count` definition exactly.
USABLE_FACT_STATUSES = frozenset({"qualified", "provider_reported", "partial", "conflicted"})

REQUIRED_CELL_STATES = (
    "OFFICIAL_QUALIFIED", "PROVIDER_EXACT_RESEARCH_USABLE", "PROVIDER_DESCRIPTIVE_ONLY",
    "ENTITY_IDENTITY_MISMATCH", "PERIOD_MISMATCH", "SCOPE_MISMATCH",
    "UNIT_OR_SCALE_UNRESOLVED", "MISSING", "NOT_APPLICABLE",
)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def official_research_universe_tickers(official_universe: Mapping[str, Any]) -> list[str]:
    """Same OFFICIAL_CURRENT_STATUSES filter already used by
    market_wide_current_valuation_input_scaleout.official_research_universe_tickers -- reused
    verbatim rather than re-derived, so both modules agree on the 1,507-name denominator."""
    statuses = {"OFFICIAL_CURRENT_EXCHANGE_SECURITY", "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"}
    return sorted(
        ticker for ticker, row in (official_universe.get("records") or {}).items()
        if row.get("stocklookup_candidate") and row.get("current_universe_status") in statuses
    )


def build_extended_p3f10_artifact(
    *, official_tickers: Sequence[str], raw_state: Mapping[str, Any], canonical_state: Mapping[str, Any],
    p3e: Mapping[str, Any], registry: Mapping[str, Any], as_of_session: str | None = None,
    source_artifacts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rerun p3f10's own generic disposition builder, unmodified, over the full official research
    universe instead of the frozen 523-name 2026-08-20 cohort. Same raw/canonical stores, same
    official panel, same source registry -- only the membership list is wider."""
    qualified, sectors, metric_counts = p3f10mod._qualified_maps(p3e)
    raw_records = {str(row["ticker"]).upper(): row for row in raw_state["tickers"]}
    canonical_records = {str(row["ticker"]).upper(): row for row in canonical_state["tickers"]}
    cohort = {
        "name": "financial_fact_coverage_recovery_full_official_universe",
        "cohort_identity": "financial_fact_coverage_recovery_full_official_universe/v1",
        "as_of_session": as_of_session,
        "members": sorted({str(t).upper() for t in official_tickers}),
        "authority": "current_official_market_universe/v1",
        "observed_session_requirement": None,
    }
    return p3f10mod.build_scaleout_artifact(
        cohort=cohort, raw_records=raw_records, canonical_records=canonical_records,
        qualified_readiness=qualified, qualified_sectors=sectors, qualified_metric_counts=metric_counts,
        source_inventory=p3f10mod._source_inventory(registry),
        source_artifacts=source_artifacts or {
            "p3f9b": None, "mva_bundle": None,
            "raw_store_state": raw_state.get("state_fingerprint"),
            "canonical_store_state": canonical_state.get("state_fingerprint"),
            "p3e": p3e.get("artifact_identity"), "p3b_rerun": None,
        },
    )


def build_extended_p3f13_artifact(
    *, p3f10_wide: Mapping[str, Any], p3e: Mapping[str, Any], registry: Mapping[str, Any],
    manifest_records: Sequence[Mapping[str, Any]], evidence_root: Path, raw_obs_dir: Path,
) -> dict[str, Any]:
    """Rerun p3f13's own generic acquisition-disposition builder, unmodified, against the wider
    p3f10 artifact. Cohort membership comes from `p3f10_artifact["instrument_dispositions"]`
    directly (p3f13 never reads the frozen bundle itself), so this naturally widens too. Every
    lookup here is against already-retained local files (manifest / evidence_root / raw_obs_dir);
    no network call is made by this function or by the reused p3f13 builder."""
    return p3f13mod.build_scaleout_artifact(
        p3f10_artifact=p3f10_wide, p3e_artifact=p3e, source_registry=registry,
        manifest_records=manifest_records, evidence_root=evidence_root, raw_obs_dir=raw_obs_dir,
    )


def build_extended_fundamental_artifact(
    *, p3f10_wide: Mapping[str, Any], p3f13_wide: Mapping[str, Any], requested_at: str,
    provider_series_by_ticker: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Rerun market_wide_current_fundamental_research's own generic artifact builder, unmodified,
    over the wider p3f10/p3f13 pair. Entity-class resolution, trajectory context, and authority-tier
    assembly are the exact same per-ticker logic already used for the narrow 523-name cohort."""
    return mwcfr.build_artifact(
        p3f10_frozen=p3f10_wide, p3f13_current=p3f13_wide, requested_at=requested_at,
        provider_series_by_ticker=provider_series_by_ticker,
    )


def load_canonical_metric_presence(canonical_facts_root: Path) -> dict[str, dict[str, bool]]:
    """Per-ticker, per-canonical_metric: does at least one retained fact carry a usable (non-
    `unavailable`) status? Reads the exact same retained gzip shards already read by
    `market_wide_current_fundamental_research.load_retained_provider_series` -- no new
    acquisition, no network call."""
    presence: dict[str, dict[str, bool]] = {}
    for path in sorted(Path(canonical_facts_root).glob("*.jsonl.gz")):
        ticker = path.name.removesuffix(".jsonl.gz")
        seen: dict[str, bool] = defaultdict(bool)
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                metric = row.get("canonical_metric")
                if metric and row.get("status") in USABLE_FACT_STATUSES:
                    seen[metric] = True
        presence[ticker] = dict(seen)
    return presence


def required_identities_for_entity(entity_class: str) -> tuple[str, ...]:
    return REQUIRED_IDENTITIES_BY_ENTITY.get(entity_class, ())


#: `fundamental_research_readiness.py`'s per-issuer `metrics` list holds derived RATIOS
#: (return_on_equity, debt_to_equity, revenue_growth_yoy, ...), not the raw identity-level facts
#: this inventory classifies. The raw identities live one level down, in the official evidence
#: panel's own per-issuer `facts` list (`canonical_metric` + `qualification_state`), which is where
#: this function reads from instead.
#:
#: One single identity is spelled differently across the two already-existing subsystems for the
#: same real concept: the canonical provider-fact store (and this module's own CORPORATE_IDENTITIES)
#: calls it `cash_and_cash_equivalents`; the official evidence panel's own fact rows call the exact
#: same balance-sheet line `cash_and_equivalents`. This is a documented correspondence between two
#: pre-existing literal spellings, not an invented alias.
OFFICIAL_PANEL_CANONICAL_METRIC_ALIAS: dict[str, str] = {"cash_and_cash_equivalents": "cash_and_equivalents"}


def load_official_facts_by_ticker(p3f13_wide: Mapping[str, Any]) -> dict[str, dict[str, Mapping[str, Any]]]:
    """Per official-qualified ticker, per canonical_metric: the retained fact row (carries
    `qualification_state` in {QUALIFIED, MISSING, NOT_APPLICABLE, CONFLICT}). Reads
    `refreshed_panel_data.issuers[].facts`, the exact same input
    `fundamental_research_readiness.build_fundamental_research_artifact` already consumes -- no new
    evidence, no recomputation."""
    by_ticker: dict[str, dict[str, Mapping[str, Any]]] = {}
    for issuer in (p3f13_wide.get("refreshed_panel_data") or {}).get("issuers", []):
        ticker = str(issuer["issuer_identity"]["ticker"])
        by_ticker[ticker] = {str(fact.get("canonical_metric")): fact for fact in issuer.get("facts", [])}
    return by_ticker


def _official_identity_fact(facts: Mapping[str, Mapping[str, Any]], identity: str) -> Mapping[str, Any] | None:
    canonical_metric = OFFICIAL_PANEL_CANONICAL_METRIC_ALIAS.get(identity, identity)
    return facts.get(canonical_metric)


def classify_identity_cell(
    *, ticker_record: Mapping[str, Any], identity: str, canonical_presence: Mapping[str, bool],
    official_facts: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Classify one (ticker, required-identity) cell into the strongest defensible state. Pure and
    deterministic: identical inputs always produce the identical state, and no ticker literal
    appears anywhere in this function."""
    authority_tier = ticker_record.get("authority_tier")
    if authority_tier == mwcfr.OFFICIAL_TIER:
        fact = _official_identity_fact(official_facts or {}, identity)
        state = (fact or {}).get("qualification_state")
        if state == "QUALIFIED":
            return {
                "state": "OFFICIAL_QUALIFIED",
                "reason": str(fact.get("reconciliation_status") or "QUALIFIED"),
            }
        if state == "NOT_APPLICABLE":
            return {"state": "NOT_APPLICABLE", "reason": "OFFICIAL_METRIC_NOT_APPLICABLE_FOR_ENTITY_CLASS"}
        return {"state": "MISSING", "reason": state or "IDENTITY_NOT_IN_OFFICIAL_EVIDENCE_PANEL"}
    if authority_tier == mwcfr.PROVIDER_TIER:
        series_metric_id = _PROVIDER_SERIES_METRIC_ID_BY_SOURCE.get(identity)
        trend = (
            (ticker_record.get("provider_series_trends", {}) or {}).get("metrics", {}) or {}
        ).get(series_metric_id) if series_metric_id else None
        if trend is not None and trend.get("status") == "AVAILABLE":
            return {"state": "PROVIDER_DESCRIPTIVE_ONLY", "reason": "PROVIDER_SERIES_TREND_AVAILABLE"}
        if canonical_presence.get(identity):
            return {
                "state": "UNIT_OR_SCALE_UNRESOLVED",
                "reason": "RAW_CANONICAL_FACT_RETAINED_SCOPE_CURRENCY_SCALE_NOT_INDEPENDENTLY_EVIDENCED",
            }
        return {"state": "MISSING", "reason": "NO_RETAINED_USABLE_PROVIDER_OBSERVATION"}
    # BLOCKED_TIER: no raw source retained for this ticker at all.
    return {"state": "MISSING", "reason": "NO_RETAINED_FINANCIAL_SOURCE"}


def _trend_comparison_blocker_observations(records: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    """Real, observed period/scope-comparability blockers from the existing trend-comparison layer
    (`_pair_basis_eligibility`'s own blocked_reason vocabulary). Reported separately from the
    single-cell residual-zero inventory below: these describe whether TWO retained periods for the
    same identity are comparable, a different question from whether the identity has any retained
    observation at all."""
    counts: Counter[str] = Counter()
    for record in records.values():
        for metric in (record.get("provider_series_trends", {}) or {}).get("metrics", {}).values():
            reason = metric.get("blocked_reason")
            if reason:
                counts[str(reason)] += 1
    return dict(sorted(counts.items()))


def build_financial_identity_inventory(
    wide_fundamental_artifact: Mapping[str, Any], canonical_presence_by_ticker: Mapping[str, Mapping[str, bool]],
    official_facts_by_ticker: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Phase-1 deterministic ticker x required-financial-identity inventory over the full official
    research universe. Every required cell receives exactly one of REQUIRED_CELL_STATES; residual
    (expected cell count vs. actually classified cell count) must equal zero."""
    records = wide_fundamental_artifact.get("records") or {}
    official_facts_by_ticker = official_facts_by_ticker or {}
    cells: dict[str, list[dict[str, Any]]] = {}
    state_counts: Counter[str] = Counter()
    state_counts_by_entity: dict[str, Counter[str]] = defaultdict(Counter)
    expected_total = 0
    for ticker, record in records.items():
        entity_class = str(record.get("entity_class") or "unknown")
        provenance = record.get("entity_class_provenance") or {}
        unresolved = entity_class == "unknown" or bool(provenance.get("conflict"))
        if unresolved:
            row = [{
                "identity": "ENTITY_CLASS", "state": "ENTITY_IDENTITY_MISMATCH",
                "reason": str(provenance.get("unresolved_reason") or "ENTITY_CLASS_UNRESOLVED_OR_CONFLICTED"),
            }]
            expected_total += 1
        else:
            identities = required_identities_for_entity(entity_class)
            expected_total += len(identities)
            row = []
            for identity in identities:
                classified = classify_identity_cell(
                    ticker_record=record, identity=identity,
                    canonical_presence=canonical_presence_by_ticker.get(ticker, {}),
                    official_facts=official_facts_by_ticker.get(ticker),
                )
                row.append({"identity": identity, **classified})
        cells[ticker] = row
        for cell in row:
            state_counts[cell["state"]] += 1
            state_counts_by_entity[entity_class][cell["state"]] += 1

    actual_total = sum(len(row) for row in cells.values())
    residual = abs(expected_total - actual_total)
    for state in REQUIRED_CELL_STATES:
        state_counts.setdefault(state, 0)

    return {
        "contract_version": CONTRACT_VERSION,
        "artifact_type": "FINANCIAL_IDENTITY_INVENTORY",
        "required_identities_by_entity": {k: list(v) for k, v in REQUIRED_IDENTITIES_BY_ENTITY.items()},
        "universe_denominator": len(records),
        "expected_cell_count": expected_total,
        "actual_cell_count": actual_total,
        "residual": residual,
        "residual_zero": residual == 0,
        "state_counts": dict(sorted(state_counts.items())),
        "state_counts_by_entity_class": {
            entity: dict(sorted(counts.items())) for entity, counts in sorted(state_counts_by_entity.items())
        },
        "provider_exact_research_usable_note": (
            "Zero by construction: no provider-tier fact reaches PROVIDER_EXACT_RESEARCH_USABLE "
            "while statement scope/currency/scale remain UNKNOWN_FAIL_CLOSED for every provider "
            "observation market-wide (module docstring policy, unchanged by this milestone)."
        ),
        "period_scope_note": (
            "PERIOD_MISMATCH/SCOPE_MISMATCH are not selected as a single-cell primary state here; "
            "they describe cross-period trend-comparison eligibility, reported separately in "
            "trend_comparison_blocker_observations using the existing "
            "_pair_basis_eligibility blocked_reason vocabulary."
        ),
        "trend_comparison_blocker_observations": _trend_comparison_blocker_observations(records),
        "cells": cells,
    }


def ai_handoff_financial_fact_projection(
    *, valuation_metric_row: Mapping[str, Any], fundamental_record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Pure, isolated projection: does not rebuild or touch any frozen 26/8 AI artifact. Maps one
    ticker/metric's already-computed retained state onto the five distinctions a future Daily
    Producer record must be able to express to an AI consumer without inventing anything new."""
    authority_tier = (fundamental_record or {}).get("authority_tier")
    status = valuation_metric_row.get("status")
    first_blocker = valuation_metric_row.get("first_blocker")
    if status == "READY":
        label = "OFFICIAL_QUALIFIED_FACT_AVAILABLE"
    elif status == "RESEARCH_USABLE" and authority_tier == mwcfr.OFFICIAL_TIER:
        label = "EXACT_RESEARCH_FINANCIAL_FACT_AVAILABLE"
    elif status == "NOT_APPLICABLE" or first_blocker == "NOT_APPLICABLE":
        label = "ENTITY_NOT_APPLICABLE"
    elif authority_tier == mwcfr.PROVIDER_TIER:
        label = "DESCRIPTIVE_PROVIDER_CONTEXT_ONLY"
    else:
        label = "MISSING_FINANCIAL_FACT"
    return {
        "ai_handoff_financial_fact_state": label,
        "is_actionable": False,
        "authority_tier": authority_tier,
        "metric_status": status,
        "first_blocker": first_blocker,
    }


def build_recovery_coverage_report(
    *, narrow_fundamental: Mapping[str, Any], wide_fundamental: Mapping[str, Any],
    narrow_valuation: Mapping[str, Any], wide_valuation: Mapping[str, Any],
    identity_inventory: Mapping[str, Any],
) -> dict[str, Any]:
    """Before/after coverage-diff report, isolating the financial-fact-recovery effect alone: both
    valuation runs share the identical price/share-authority/official-universe/p3e inputs, so any
    difference between them is attributable only to the wider fundamental-research cohort."""
    narrow_cov, wide_cov = narrow_valuation["coverage"], wide_valuation["coverage"]
    narrow_tiers = Counter(r["authority_tier"] for r in narrow_fundamental["records"].values())
    wide_tiers = Counter(r["authority_tier"] for r in wide_fundamental["records"].values())
    narrow_tickers = set(narrow_fundamental["records"])
    wide_only_tickers = sorted(set(wide_fundamental["records"]) - narrow_tickers)
    unchanged_narrow_subset = all(
        narrow_fundamental["records"][t] == wide_fundamental["records"][t] for t in narrow_tickers
        if t in wide_fundamental["records"]
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "narrow_cohort_size": len(narrow_tickers),
        "wide_cohort_size": len(wide_fundamental["records"]),
        "newly_examined_ticker_count": len(wide_only_tickers),
        "narrow_subset_byte_identical_under_widening": unchanged_narrow_subset,
        "authority_tier_distribution": {"before": dict(sorted(narrow_tiers.items())), "after": dict(sorted(wide_tiers.items()))},
        "entity_class_distribution": {
            "before": dict(wide_fundamental["entity_class_scaleout_coverage"]["before_entity_class_distribution"]),
            "after": dict(wide_fundamental["entity_class_scaleout_coverage"]["after_entity_class_distribution"]),
        },
        "valuation_metric_research_usable_counts": {
            "before_financial_fact_recovery": dict(narrow_cov["metric_research_usable_counts"]),
            "after_financial_fact_recovery": dict(wide_cov["metric_research_usable_counts"]),
        },
        "valuation_metric_ready_counts": {
            "before_financial_fact_recovery": dict(narrow_cov["metric_ready_counts"]),
            "after_financial_fact_recovery": dict(wide_cov["metric_ready_counts"]),
        },
        "first_blocker_counts_overall": {
            "before_financial_fact_recovery": dict(narrow_cov["first_blocker_counts"]["overall"]),
            "after_financial_fact_recovery": dict(wide_cov["first_blocker_counts"]["overall"]),
        },
        "value_strategy_readiness": {
            "before": narrow_valuation["value_strategy_readiness"]["eligible"],
            "after": wide_valuation["value_strategy_readiness"]["eligible"],
        },
        "identity_inventory_summary": {
            "residual": identity_inventory["residual"],
            "state_counts": identity_inventory["state_counts"],
        },
        "official_qualified_issuer_count_unchanged": (
            narrow_fundamental["coverage"]["issuers_with_official_facts"]
            == wide_fundamental["coverage"]["issuers_with_official_facts"]
        ),
        "authority_boundary": {
            "new_provider_added": False,
            "new_official_evidence_acquired": False,
            "official_authority_promoted": False,
            "value_strategy_activated": wide_valuation["value_strategy_readiness"]["eligible"] > 0,
            "frozen_prior_artifacts_rewritten": False,
        },
    }


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"{ARTIFACT_TYPE.lower()}:{digest}"}
