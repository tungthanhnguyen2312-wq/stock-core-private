"""Canonical daily Financial V2 materialization.

Builds the current, best-legitimately-known Financial V2 research context for a decision
session from the pinned ``financial_v2_current_input_authority`` evidence chain, and projects
it over the Daily Product's OWN ticker denominator -- never the engine's own, narrower
cohort. Missing a Financial V2 record for a Daily Product ticker never removes that ticker;
it gets an explicit ABSENT compact record (``financial_analysis_product_projection``'s own
zero-silent-drop contract).

Financial evidence is PERIODIC. "Daily materialization" here means "the latest financial
evidence legitimately known/retained as of this decision session" -- it never fabricates a
same-session financial fact. The same evidence is expected to, and should, repeat with an
IDENTICAL ``financial_v2_engine_identity`` across many consecutive trading sessions between
real financial reports; only ``decision_session`` changes daily by construction.

This module recomputes nothing that Financial V2 already owns: it is orchestration glue over
``market_wide_financial_analysis_v2_scaleout.build_scaleout`` (the engine),
``financial_analysis_product_projection.build_product_projection`` (the compact product),
and ``current_research_valuation_context`` (peer context and valuation evaluation) -- the
same three already-governed builders ``tools/run_core_fundamental_valuation_peer_context_
replay.py`` and ``tools/run_integrated_investment_decision_replay.py`` already prove correct
end to end.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import current_research_valuation_context as valuation_context
import entity_classification_contract as entity_classification
import exchange_industry_classification as industry_classification
import financial_analysis_product_projection as product_projection
import financial_v2_current_input_authority as input_authority
import market_wide_financial_analysis_v2_scaleout as scaleout

CONTRACT_VERSION = "canonical_daily_financial_v2_materialization/v1"
MILESTONE = "CANONICAL_DAILY_FINANCIAL_V2_AND_CURRENT_RESEARCH_ENRICHMENT_V1"
_ADMITTED_ENTITY_TYPES = frozenset({"corporate", "bank", "securities", "insurance", "finance_company"})


class CanonicalFinancialV2MaterializationError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(payload: Mapping[str, Any]) -> dict[str, str]:
    excluded = {"artifact_sha256", "artifact_identity", "requested_at"}
    digest = hashlib.sha256(_canonical({k: v for k, v in payload.items() if k not in excluded}).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def load_semantic_rows(authority: input_authority.FinancialV2InputAuthority) -> tuple[list[dict], dict]:
    artifact = json.loads(authority.semantics_artifact_path.read_text(encoding="utf-8"))
    input_authority.verify_identity(
        label="semantics", observed=artifact.get("artifact_identity"),
        expected=authority.expected_semantics_identity,
    )
    with gzip.open(authority.semantics_facts_path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return rows, artifact


def load_classification_diagnostics(authority: input_authority.FinancialV2InputAuthority) -> dict:
    diagnostics = json.loads(authority.classification_diagnostics_path.read_text(encoding="utf-8"))
    input_authority.verify_identity(
        label="classification_diagnostics", observed=diagnostics.get("diagnostics_identity"),
        expected=authority.expected_classification_diagnostics_identity,
    )
    return diagnostics


def load_industry_by_ticker(authority: input_authority.FinancialV2InputAuthority) -> dict[str, str]:
    """ticker -> retained ICB level-2 sector label. Optional: an absent/malformed snapshot
    degrades peer cohorts to the entity-class fallback, never blocks materialization."""
    if not authority.industry_snapshot_path.is_file():
        return {}
    snapshot = industry_classification.load_snapshot(authority.industry_snapshot_path)
    index = industry_classification.industry_index(snapshot)
    return {
        ticker: record["icb_level_2_label"] for ticker, record in index.items()
        if isinstance(record.get("icb_level_2_label"), str) and record["icb_level_2_label"].strip()
    }


def build_engine_artifact(
    *, root: Path, requested_at: str, authority: input_authority.FinancialV2InputAuthority | None = None,
) -> dict[str, Any]:
    """Build the raw ``financial_analysis_context/v2`` engine artifact from the pinned
    Financial V2 input authority.

    Internal input only -- never expose this raw artifact to the normal Daily/AI product;
    use ``build_compact_product`` for that. Content identity is independent of
    ``requested_at`` and of ``root``'s specific checkout path, so the SAME underlying
    retained evidence reproduces a byte-identical ``artifact_identity`` across sessions.
    """
    authority = authority or input_authority.resolve(root)
    rows, semantics_artifact = load_semantic_rows(authority)
    classification = load_classification_diagnostics(authority)
    records, feature_store_artifact = scaleout.load_feature_store(
        authority.feature_store_artifact_path, authority.feature_store_records_path,
    )
    input_authority.verify_identity(
        label="feature_store", observed=feature_store_artifact.get("artifact_identity"),
        expected=authority.expected_feature_store_identity,
    )
    records_with_types = {ticker: dict(record) for ticker, record in records.items()}
    for row in classification.get("rows") or []:
        ticker = str(row.get("ticker") or "").upper()
        outcome = str(row.get("outcome") or "")
        if ticker in records_with_types and outcome in _ADMITTED_ENTITY_TYPES:
            records_with_types[ticker]["entity_type"] = outcome
    # The frozen classification-scaleout diagnostics snapshot above predates any later
    # classification-tier fix. Layer the CURRENT tracked entity_classification_contract
    # authority over it -- a pure tracked-config read, no DB/network -- so a real later
    # classification correction is never silently masked by this dated snapshot.
    for ticker, entity_type in entity_classification.load_layered_entity_profiles().items():
        if ticker in records_with_types:
            records_with_types[ticker]["entity_type"] = entity_type
    qualified_flow_artifact = scaleout.build_qualified_flow_artifact(
        semantic_rows=rows, feature_records=records_with_types, requested_at=requested_at,
    )
    return scaleout.build_scaleout(
        semantic_rows=rows, feature_records=records_with_types, feature_store_artifact=feature_store_artifact,
        period_semantics_identity=semantics_artifact["artifact_identity"], requested_at=requested_at,
        classification_diagnostics_identity=classification.get("diagnostics_identity"),
        qualified_flow_artifact=qualified_flow_artifact,
    )


def build_compact_product(
    *, engine_artifact: Mapping[str, Any], product_tickers: Sequence[str], requested_at: str,
) -> dict[str, Any]:
    """The ``financial_analysis_product_integration/v1`` compact product, projected over the
    Daily Product's OWN ticker denominator (not the engine's narrower cohort) -- every
    ``product_tickers`` entry gets an explicit AVAILABLE or ABSENT record; zero silent drops.
    """
    return product_projection.build_product_projection(
        financial_context=engine_artifact, product_tickers=product_tickers, requested_at=requested_at,
    )


def build_peer_context(
    *, engine_artifact: Mapping[str, Any], authority: input_authority.FinancialV2InputAuthority,
) -> dict[str, dict[str, Any]]:
    """Sector/industry (entity-class fallback) peer median/percentile context per ticker for
    the curated already-READY-capable headline ratios. Additive alongside, never merged into,
    the compact product's own contract -- this milestone reuses ``current_research_valuation_
    context.attach_engine_fundamental_peers`` unmodified rather than reimplementing it."""
    industry_by_ticker = load_industry_by_ticker(authority)
    return valuation_context.attach_engine_fundamental_peers(
        engine_artifact.get("records") or {}, industry_by_ticker=industry_by_ticker,
    )


def build_calculation_readiness_context(
    *, runtime_root: Path, decision_session: str, raw_valuation_artifact: Mapping[str, Any] | None,
    product_tickers: Sequence[str], requested_at: str,
) -> dict[str, Any]:
    """Project the existing readiness engine into the Current-Research valuation path.

    ``canonical_financial_bundle_section`` already owns the governed, read-only bridge
    from canonical facts to ``market_wide_calculation_readiness``.  This wrapper merely
    supplies the exact retained native close for the decision session and projects one
    explicit context record for every Daily ticker; it does not reproduce a formula or
    create a valuation lane.
    """
    from canonical_financial_bundle_section import SECTION_KEY, attach

    raw_records = (raw_valuation_artifact or {}).get("records") or {}
    entries: dict[str, dict[str, Any]] = {}
    for ticker in product_tickers:
        price = (raw_records.get(ticker) or {}).get("price_input") or {}
        native_close = price.get("provider_native_value")
        entries[ticker] = {"close": native_close} if price.get("status") == "PRICE_READY" and native_close is not None else {}
    attach(entries, runtime_root, include=True, session_date=decision_session, price_basis_verified=False)

    records: dict[str, dict[str, Any]] = {}
    for ticker in product_tickers:
        section = entries[ticker].get(SECTION_KEY)
        if not isinstance(section, Mapping):
            records[ticker] = {
                "status": "UNAVAILABLE", "reason": "CANONICAL_FACTS_OR_EXACT_NATIVE_CLOSE_UNAVAILABLE",
                "calculation_readiness": [],
            }
            continue
        records[ticker] = {
            "status": "AVAILABLE",
            "latest_reporting_period": section.get("latest_reporting_period"),
            "calculation_readiness": list(section.get("calculation_readiness") or []),
            "still_blocked_by_price_basis": list(section.get("still_blocked_by_price_basis") or []),
            "limitations": list(section.get("limitations") or []),
            "readiness_policy_version": section.get("readiness_policy_version"),
            "fact_store_state_fingerprint": section.get("fact_store_state_fingerprint"),
        }
    payload: dict[str, Any] = {
        "contract_version": "canonical_daily_calculation_readiness_context/v1",
        "requested_at": requested_at,
        "decision_session": decision_session,
        "source_raw_valuation_identity": (raw_valuation_artifact or {}).get("artifact_identity"),
        "coverage": {
            "decision_denominator": len(product_tickers),
            "available": sum(record["status"] == "AVAILABLE" for record in records.values()),
            "unavailable": sum(record["status"] != "AVAILABLE" for record in records.values()),
            "zero_silent_ticker_drops": len(records) == len(product_tickers),
        },
        "records": records,
        "authority_boundary": {
            "calculation_engine_reused_without_formula_changes": True,
            "provider_reported_remains_current_research_only": True,
            "price_basis_verified": False,
            "no_authority_promotion": True,
        },
    }
    payload.update(_identity(payload))
    return payload


def build_evaluated_valuation_artifact(
    *, engine_artifact: Mapping[str, Any], raw_valuation_artifact: Mapping[str, Any] | None,
    product_tickers: Sequence[str], requested_at: str,
    calculation_readiness_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate the raw ``market_wide_current_valuation_input_scaleout`` per-ticker records
    into the ``current_research_valuation_context/v1`` shape (``methods``, ``peer_relative_
    context``, ...) that ``integrated_investment_decision_product.evaluate_valuation_context``
    actually reads, joined against this session's Financial V2 engine TTM features.

    Mirrors the one proven-correct wiring in ``tools/run_integrated_investment_decision_
    replay.py``'s ``load_inputs()`` -- the raw price/EPS/BVPS-shaped valuation artifact
    ``derive_market_wide_current_valuation_input_scaleout.py`` produces each session is NOT
    itself the shape the decision engine needs; it must first pass through
    ``evaluate_ticker_valuation``/``attach_peer_relative``.
    """
    engine_records = engine_artifact.get("records") or {}
    valuation_records = (raw_valuation_artifact or {}).get("records") or {}
    rows = {
        ticker: valuation_context.evaluate_ticker_valuation(
            ticker=ticker, feature_record=None,
            valuation_record=valuation_records.get(ticker),
            financial_analysis_record=engine_records.get(ticker),
            financial_analysis_context_identity=engine_artifact.get("artifact_identity"),
            calculation_readiness_record=((calculation_readiness_context or {}).get("records") or {}).get(ticker),
        )
        for ticker in product_tickers
    }
    rows = valuation_context.attach_peer_relative(rows)
    payload: dict[str, Any] = {
        "contract_version": valuation_context.CONTRACT_VERSION,
        "requested_at": requested_at,
        "source_valuation_identity": (raw_valuation_artifact or {}).get("artifact_identity"),
        "source_financial_v2_identity": engine_artifact.get("artifact_identity"),
        "source_calculation_readiness_identity": (calculation_readiness_context or {}).get("artifact_identity"),
        "records": rows,
    }
    payload.update(_identity(payload))
    return payload


def _observed_period_range(engine_artifact: Mapping[str, Any]) -> tuple[str | None, str | None]:
    periods: set[str] = set()
    for record in (engine_artifact.get("records") or {}).values():
        for feature in (record.get("features") or {}).values():
            if isinstance(feature, Mapping):
                periods.update(str(p) for p in (feature.get("period_identity") or []) if p)
    if not periods:
        return None, None
    ordered = sorted(periods)
    return ordered[0], ordered[-1]


def build_session_artifact(
    *, root: Path, decision_session: str, product_tickers: Sequence[str], requested_at: str,
    authority: input_authority.FinancialV2InputAuthority | None = None,
    engine_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the full canonical session-delivery artifact.

    This is a SESSION DELIVERY artifact binding a decision run to the financial evidence it
    legitimately used -- never a claim that the underlying financial facts are session-dated.
    Its identity is expected to change every ``decision_session`` (a decision-run binding),
    while ``financial_v2_engine_identity`` and ``financial_analysis_product``'s own identity
    stay byte-identical across sessions whenever the underlying retained evidence is
    unchanged -- exactly the distinction between "current-known financial evidence" and
    "financial facts happened on this market session."

    ``engine_artifact``, when supplied, is reused as-is instead of rebuilding the ~1,500-
    ticker engine a second time -- a caller (such as the canonical post-close pipeline) that
    also needs the raw engine artifact for a sibling computation (e.g. valuation TTM) should
    build it once via ``build_engine_artifact`` and pass it to both call sites.
    """
    authority = authority or input_authority.resolve(root)
    engine_artifact = engine_artifact if engine_artifact is not None else build_engine_artifact(
        root=root, requested_at=requested_at, authority=authority,
    )
    compact_product = build_compact_product(
        engine_artifact=engine_artifact, product_tickers=product_tickers, requested_at=requested_at,
    )
    peer_context = build_peer_context(engine_artifact=engine_artifact, authority=authority)
    earliest_period, latest_period = _observed_period_range(engine_artifact)
    engine_coverage = engine_artifact.get("coverage") or {}
    product_summary = compact_product.get("financial_analysis_market_summary") or {}
    payload: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "schema_version": "1.0.0",
        "milestone": MILESTONE,
        "requested_at": requested_at,
        "decision_session": decision_session,
        "financial_evidence_as_of_period": latest_period,
        "financial_evidence_period_range": {
            "earliest_observed_period_identity": earliest_period,
            "latest_observed_period_identity": latest_period,
        },
        "financial_input_authority": authority.to_manifest(),
        "financial_source_identity": engine_artifact.get("artifact_identity"),
        "financial_v2_engine_identity": engine_artifact.get("artifact_identity"),
        "financial_analysis_product": compact_product,
        "financial_content_identity": compact_product.get("artifact_identity"),
        "engine_fundamental_peer_context": peer_context,
        "coverage": {
            "decision_denominator": len(product_tickers),
            "financial_engine_denominator": engine_coverage.get("ticker_denominator"),
            "financial_product_available": product_summary.get("compact_coverage"),
            "financial_product_absent": product_summary.get("absent_coverage"),
            "zero_silent_ticker_drops": (compact_product.get("coverage") or {}).get("zero_silent_ticker_drops"),
        },
        "temporal_semantics": {
            "financial_evidence_is_periodic": True,
            "note": (
                "Financial evidence identity is expected to repeat identically across many "
                "consecutive decision sessions between real financial reports; only "
                "decision_session changes daily by construction. This artifact never "
                "manufactures a same-session financial update."
            ),
        },
        "authority_boundary": {
            "is_actionable": False, "research_only": True, "no_score": True,
            "no_target_price": True, "no_probability": True, "proxies_never_promoted_to_ready": True,
        },
    }
    payload.update(_identity(payload))
    return payload
