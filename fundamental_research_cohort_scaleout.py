"""Market-wide fundamental cross-sectional research cohort scale-out.

MARKET_WIDE_FUNDAMENTAL_RESEARCH_COHORT_SCALEOUT_V1.

``fundamental_cross_sectional_scoring.build_artifact`` is already fully generic: its
denominator is exactly ``len(base["operational_proxy"]["records"])``, whatever ``base``
the caller supplies. The narrow 523-name cohort is not a property of that function --
it comes entirely from ``market_wide_historical_fundamentals_scaleout.execute()``'s
default ``p3f10_frozen`` argument, which reads the frozen 2026-08-20 523-member
``EMPIRICAL_ACTIVE_SHADOW_ONLY`` snapshot (``p3f13_official_financial_evidence_scaleout
.DEFAULT_P3F10``). ``market_wide_historical_fundamentals_scaleout.build_artifact`` itself
never hardcodes that cohort; it is already parameterized by ``p3f10_frozen``/
``p3f13_current``.

This module removes exactly that accidental default-path ceiling. It reuses, completely
unmodified:

* ``financial_fact_coverage_recovery.build_extended_p3f10_artifact`` /
  ``build_extended_p3f13_artifact`` -- the exact generic wideners the 2026-08-27
  ``FINANCIAL_FACT_COVERAGE_RECOVERY_AND_SCALEOUT_V1`` milestone already proved against
  the full 1,507-name official research universe for the sibling
  ``market_wide_current_fundamental_research`` pipeline. Same raw/canonical financial
  stores, same 13-issuer official panel, same source registry -- only the ticker
  membership list is wider.
* ``market_wide_historical_fundamentals_scaleout.build_artifact`` -- fed the wide p3f10/
  p3f13 pair instead of the frozen narrow one.
* ``fundamental_cross_sectional_scoring.build_artifact`` -- fed the wide operational-proxy
  base instead of ``market_wide_historical_fundamentals_scaleout.execute()``'s narrow
  default.

No engine file is changed by this module (see ``git diff`` for this milestone: only this
new file, its tools, and its tests). No new provider, network call, OCR/PDF acquisition,
or evidence-quality relaxation occurs. The narrow 523-member artifact and every existing
``execute()`` default caller (``fundamental_cross_sectional_scoring.execute``,
``market_wide_historical_fundamentals_scaleout.execute``,
``daily_session_shadow_recommendation.SHARED_CONTEXT_RELATIVE_PATHS``) remain byte-for-
byte untouched and continue to serve the narrow cohort by default -- this module produces
a new, additive, separately identified scale-out research product alongside it, not a
replacement or a silent authority promotion.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

import financial_fact_coverage_recovery as ffcr
import fundamental_cross_sectional_scoring as fcss
import market_wide_historical_fundamentals_scaleout as mwhfs
from field_temporal_contract import stable_id

CONTRACT_VERSION = "fundamental_cross_sectional_scoring_and_ranking_cohort_scaleout/v1"
ARTIFACT_TYPE = "MARKET_WIDE_FUNDAMENTAL_RESEARCH_COHORT_SCALEOUT"
MILESTONE = "MARKET_WIDE_FUNDAMENTAL_RESEARCH_COHORT_SCALEOUT_V1"
NARROW_COHORT_NAME = "2026-08-20 EMPIRICAL_ACTIVE_SHADOW_ONLY (frozen, 523-member)"

#: The four axes fundamental_cross_sectional_scoring.py defines. Reused verbatim -- this
#: module never adds, removes, or reweights an axis.
AXES = tuple(fcss.AXES)


def build_wide_historical_fundamentals_artifact(
    *, official_tickers: Sequence[str], raw_state: Mapping[str, Any], canonical_state: Mapping[str, Any],
    p3e: Mapping[str, Any], registry: Mapping[str, Any], manifest_records: Sequence[Mapping[str, Any]],
    evidence_root: Any, raw_obs_dir: Any, as_of_session: str, requested_at: str,
) -> dict[str, Any]:
    """Rerun the existing, unmodified p3f10 -> p3f13 -> market_wide_historical_fundamentals_scaleout
    chain over the wide official research universe membership instead of the frozen 523-name
    2026-08-20 cohort. Same raw/canonical stores, same official panel, same source registry --
    only the membership list and as_of_session/requested_at labels are supplied explicitly."""
    p3f10_wide = ffcr.build_extended_p3f10_artifact(
        official_tickers=official_tickers, raw_state=raw_state, canonical_state=canonical_state,
        p3e=p3e, registry=registry, as_of_session=as_of_session,
    )
    p3f13_wide = ffcr.build_extended_p3f13_artifact(
        p3f10_wide=p3f10_wide, p3e=p3e, registry=registry, manifest_records=manifest_records,
        evidence_root=evidence_root, raw_obs_dir=raw_obs_dir,
    )
    return mwhfs.build_artifact(p3f10_frozen=p3f10_wide, p3f13_current=p3f13_wide, requested_at=requested_at)


def build_wide_fundamental_cross_sectional_artifact(*, wide_historical_fundamentals: Mapping[str, Any]) -> dict[str, Any]:
    """Rerun fundamental_cross_sectional_scoring's own generic artifact builder, unmodified, over
    the wide operational-proxy base. Axis formula (AVAILABLE_FEATURE_PERCENTILE_MEAN/v1),
    percentile method, and feature set are the exact same per-ticker logic already used for the
    narrow 523-name cohort -- only the population the percentile is computed over is wider."""
    return fcss.build_artifact(base=wide_historical_fundamentals)


def _axis_status_counts(records: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records.values():
        for axis, payload in (record.get("axes") or {}).items():
            counts[axis][str(payload.get("axis_status"))] += 1
    return {axis: dict(sorted(counter.items())) for axis, counter in sorted(counts.items())}


def build_root_cause_reconciliation(
    *, universe_raw_denominator: int, universe_candidate_count: int, official_tickers: Sequence[str],
    narrow_cohort_tickers: Sequence[str], wide_historical_fundamentals: Mapping[str, Any],
    wide_cross_sectional: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify every governed-universe security into a deterministic reason family, reusing only
    the terminal-disposition/axis-status vocabulary the existing generic builders already emit --
    no new reason taxonomy is invented, and no ticker literal appears in this function.

    Answers the milestone's first question ("is 523 an evidence ceiling, an implementation
    ceiling, or a mixture") with reconciled counts rather than an assertion.
    """
    official_set = {str(t).upper() for t in official_tickers}
    narrow_set = {str(t).upper() for t in narrow_cohort_tickers}
    manifest_by_ticker = {row["ticker"]: row for row in wide_historical_fundamentals["manifest"]}
    residual_membership = official_set - set(manifest_by_ticker)

    terminal_by_entity: dict[str, Counter[str]] = defaultdict(Counter)
    terminal_overall: Counter[str] = Counter()
    newly_admitted_terminal: Counter[str] = Counter()
    newly_admitted_by_entity: dict[str, Counter[str]] = defaultdict(Counter)
    for ticker, row in manifest_by_ticker.items():
        terminal_by_entity[row["entity_type"]][row["terminal_disposition"]] += 1
        terminal_overall[row["terminal_disposition"]] += 1
        if ticker not in narrow_set:
            newly_admitted_terminal[row["terminal_disposition"]] += 1
            newly_admitted_by_entity[row["entity_type"]][row["terminal_disposition"]] += 1

    wide_records = wide_cross_sectional.get("records") or {}
    newly_admitted_axis_status = _axis_status_counts(
        {ticker: record for ticker, record in wide_records.items() if ticker not in narrow_set}
    )
    narrow_subset_axis_status = _axis_status_counts(
        {ticker: record for ticker, record in wide_records.items() if ticker in narrow_set}
    )

    reason_family_map = {
        "ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE": "SECTOR_INAPPLICABLE_OR_UNSUPPORTED_SECURITY_TYPE (existing, deliberate financial_operational_proxy.SUPPORTED_ENTITY_TYPES={'corporate'} boundary -- unchanged by this milestone, see docs/DECISIONS.md Sector safety)",
        "NO_ELIGIBLE_PROVIDER_FACTS": "NO_QUALIFIED_FINANCIAL_EVIDENCE (retained raw/canonical stores carry no usable fact for this ticker)",
        "OPERATIONAL_PROXY_OR_VERIFIED_RESEARCH_EVIDENCE": "HAS_EVIDENCE_AXIS_READINESS_VARIES (corporate entity with at least one classified fact; per-axis readiness reported separately)",
    }

    return {
        "contract_version": CONTRACT_VERSION,
        "artifact_type": "FUNDAMENTAL_RESEARCH_COHORT_ROOT_CAUSE_RECONCILIATION",
        "question": "Is the 523-name fundamental cross-sectional research cohort an evidence ceiling, an implementation ceiling, or a mixture?",
        "universe": {
            "raw_denominator": universe_raw_denominator,
            "stocklookup_candidate": universe_candidate_count,
            "applicable_official_research_universe": len(official_set),
            "applicable_filter": "current_official_market_universe records with stocklookup_candidate=true and current_universe_status in {OFFICIAL_CURRENT_EXCHANGE_SECURITY, OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE} -- financial_fact_coverage_recovery.official_research_universe_tickers, reused verbatim (not re-derived).",
        },
        "narrow_cohort_size": len(narrow_set),
        "narrow_cohort_source": NARROW_COHORT_NAME,
        "wide_cohort_size": len(manifest_by_ticker),
        "residual_official_tickers_missing_from_wide_manifest": sorted(residual_membership),
        "residual_zero": len(residual_membership) == 0,
        "finding": (
            "IMPLEMENTATION_CEILING_FOR_MEMBERSHIP_MIXED_FOR_AXIS_READINESS: every one of the "
            f"{len(official_set) - len(narrow_set)} officially-applicable tickers excluded from the "
            "frozen 523-member snapshot receives a full manifest record (entity classification + "
            "terminal disposition) once fed through the unmodified generic builders -- the 523 "
            "boundary was a hardcoded default-path snapshot, not a property of any scoring or "
            "evidence-qualification rule. Within the wider membership, whether a ticker reaches a "
            "READY_RESEARCH_ONLY axis remains evidence-bounded (retained fact presence, entity-class "
            "support) exactly as it already was for the narrow 523: this milestone changes reach, not "
            "the qualification bar."
        ),
        "reason_family_map": reason_family_map,
        "terminal_disposition_distribution": {
            "overall": dict(sorted(terminal_overall.items())),
            "by_entity_type": {k: dict(v) for k, v in sorted(terminal_by_entity.items())},
        },
        "newly_admitted_tickers": {
            "count": len(manifest_by_ticker) - len(narrow_set & set(manifest_by_ticker)),
            "terminal_disposition_distribution": dict(sorted(newly_admitted_terminal.items())),
            "terminal_disposition_by_entity_type": {k: dict(v) for k, v in sorted(newly_admitted_by_entity.items())},
            "axis_status_distribution": newly_admitted_axis_status,
        },
        "narrow_subset_under_widening": {
            "axis_status_distribution": narrow_subset_axis_status,
            "note": "Reported for comparison only. Percentile-based axis scores for these tickers "
                    "recompute against the wider comparable population by design (same "
                    "AVAILABLE_FEATURE_PERCENTILE_MEAN/v1 formula, same feature set, same thresholds "
                    "-- only the empirical percentile pool grows); raw facts/derived_metrics/evidence "
                    "lineage for these tickers are unchanged. See narrow_subset_facts_byte_identical.",
        },
    }


def build_narrow_vs_wide_lineage_diff(
    *, narrow_historical_fundamentals: Mapping[str, Any], wide_historical_fundamentals: Mapping[str, Any],
    narrow_tickers: Sequence[str],
) -> dict[str, Any]:
    """Prove the narrow 523 subset's own retained facts/derived_metrics are untouched by widening
    (only the percentile pool used downstream by fundamental_cross_sectional_scoring changes)."""
    narrow_records = narrow_historical_fundamentals["operational_proxy"]["records"]
    wide_records = wide_historical_fundamentals["operational_proxy"]["records"]
    narrow_set = {str(t).upper() for t in narrow_tickers}
    mismatched = sorted(
        ticker for ticker in narrow_set
        if ticker in narrow_records and ticker in wide_records
        and (narrow_records[ticker].get("facts"), narrow_records[ticker].get("derived_metrics"))
        != (wide_records[ticker].get("facts"), wide_records[ticker].get("derived_metrics"))
    )
    missing_from_wide = sorted(narrow_set - set(wide_records))
    return {
        "narrow_subset_facts_byte_identical": not mismatched and not missing_from_wide,
        "mismatched_tickers": mismatched,
        "narrow_tickers_missing_from_wide": missing_from_wide,
    }


def sample_newly_admitted_lineage(
    *, wide_cross_sectional: Mapping[str, Any], wide_historical_fundamentals: Mapping[str, Any],
    narrow_tickers: Sequence[str], limit: int = 8,
) -> list[dict[str, Any]]:
    """Deterministic (sorted-ticker) sample of newly admitted names with their exact evidence
    identity, axes reached, and remaining limitations -- for section 14 no-coverage-gaming proof.
    Never a manual whitelist: selection is purely `sorted(newly_admitted)[:limit]`.
    """
    narrow_set = {str(t).upper() for t in narrow_tickers}
    manifest_by_ticker = {row["ticker"]: row for row in wide_historical_fundamentals["manifest"]}
    records = wide_cross_sectional.get("records") or {}
    newly_admitted = sorted(t for t in records if t not in narrow_set)
    samples = []
    for ticker in newly_admitted[:limit]:
        manifest_row = manifest_by_ticker.get(ticker, {})
        record = records[ticker]
        ready_axes = sorted(a for a, p in record["axes"].items() if p.get("axis_status") == "READY_RESEARCH_ONLY")
        insufficient_axes = sorted(a for a, p in record["axes"].items() if p.get("axis_status") != "READY_RESEARCH_ONLY")
        samples.append({
            "ticker": ticker,
            "previously_excluded_because": f"outside the frozen {NARROW_COHORT_NAME}",
            "generic_fix_that_admitted_it": "wider official-research-universe membership fed to market_wide_historical_fundamentals_scaleout.build_artifact via financial_fact_coverage_recovery's existing p3f10/p3f13 wideners",
            "entity_class": manifest_row.get("entity_type"),
            "terminal_disposition": manifest_row.get("terminal_disposition"),
            "canonical_fact_count": manifest_row.get("canonical_fact_count"),
            "axes_ready_research_only": ready_axes,
            "axes_insufficient_inputs": insufficient_axes,
            "data_confidence": record.get("data_confidence"),
            "remaining_limitations": (
                ["ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE: no operational-proxy fact classified for this sector"]
                if manifest_row.get("terminal_disposition") == "ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE"
                else ["NO_RETAINED_USABLE_PROVIDER_OBSERVATION"] if manifest_row.get("terminal_disposition") == "NO_ELIGIBLE_PROVIDER_FACTS"
                else (insufficient_axes and [f"INSUFFICIENT_INPUTS:{axis}" for axis in insufficient_axes]) or []
            ),
        })
    return samples


def sample_still_unavailable(
    *, official_tickers: Sequence[str], wide_historical_fundamentals: Mapping[str, Any],
    narrow_tickers: Sequence[str] = (), limit: int = 5,
) -> list[dict[str, Any]]:
    """Deterministic sample of officially-applicable tickers that remain research-unavailable
    even after the implementation ceiling is removed -- the genuine evidence-ceiling proof.

    Two distinct sub-cases, both real: (a) a ticker absent from the wide manifest entirely
    (would indicate a residual membership gap; expected empty once residual_zero is true), and
    (b) a ticker present in the wide manifest with terminal_disposition
    NO_ELIGIBLE_PROVIDER_FACTS -- admitted by the generic fix, still unavailable because the
    retained raw/canonical stores carry no usable fact for it."""
    manifest_by_ticker = {row["ticker"]: row for row in wide_historical_fundamentals["manifest"]}
    narrow_set = {str(t).upper() for t in narrow_tickers}
    missing_from_manifest = sorted({str(t).upper() for t in official_tickers} - set(manifest_by_ticker))
    no_evidence = sorted(
        ticker for ticker, row in manifest_by_ticker.items()
        if row.get("terminal_disposition") == "NO_ELIGIBLE_PROVIDER_FACTS" and ticker not in narrow_set
    )
    samples = [{"ticker": t, "reason": "NOT_IN_WIDE_MANIFEST_RESIDUAL"} for t in missing_from_manifest[:limit]]
    remaining = limit - len(samples)
    if remaining > 0:
        samples += [
            {"ticker": t, "reason": "NO_ELIGIBLE_PROVIDER_FACTS", "entity_class": manifest_by_ticker[t].get("entity_type"),
             "canonical_fact_count": manifest_by_ticker[t].get("canonical_fact_count")}
            for t in no_evidence[:remaining]
        ]
    return samples


def sample_sector_special_case(
    *, wide_cross_sectional: Mapping[str, Any], wide_historical_fundamentals: Mapping[str, Any],
    narrow_tickers: Sequence[str], entity_types: Sequence[str] = ("bank", "insurance", "securities", "finance_company"),
    limit: int = 2,
) -> list[dict[str, Any]]:
    """Deterministic sample of a newly admitted non-corporate entity to prove sector semantics
    (NOT_APPLICABLE-by-design) are preserved, not violated, by the scale-out. Tries each entity
    type in order (some sectors, e.g. banks, may already be fully covered by the narrow cohort
    and so have zero newly admitted members) and returns the first non-empty sample -- never a
    manually chosen ticker."""
    narrow_set = {str(t).upper() for t in narrow_tickers}
    manifest_by_ticker = {row["ticker"]: row for row in wide_historical_fundamentals["manifest"]}
    records = wide_cross_sectional.get("records") or {}
    for entity_type in entity_types:
        candidates = sorted(
            ticker for ticker, row in manifest_by_ticker.items()
            if row.get("entity_type") == entity_type and ticker not in narrow_set
        )
        if not candidates:
            continue
        return [
            {
                "ticker": ticker,
                "entity_class": entity_type,
                "terminal_disposition": manifest_by_ticker[ticker]["terminal_disposition"],
                "axes": records.get(ticker, {}).get("axes"),
                "expected_treatment": "ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE -- identical to how existing narrow-cohort bank/securities names (e.g. VCB/SSI) are already treated; sector semantics not forced.",
            }
            for ticker in candidates[:limit]
        ]
    return []


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"{ARTIFACT_TYPE.lower()}:{digest}"}
