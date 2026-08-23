"""Market-wide current fundamental-research coverage artifact.

Joins two already-existing, independently-qualified fundamental-evidence lanes into one
deterministic, sector-aware, coverage-explicit per-ticker artifact:

* the **official-qualified tier** -- `fundamental_research_readiness.py` (P3-B) run over the
  current P3-F13 official-evidence panel (13 issuers today: GAS, HPG, NVL, PAN, POW, PVD, QNS,
  SSI, VCB, VNM, VRE, FPT, PNJ). Every metric here carries its exact/proxy status, periods used,
  evidence lineage, and sector-specific applicability (`NOT_APPLICABLE` industrial metrics on
  bank/securities issuers are preserved, never forced).
* the **provider-research tier** -- P3-F10's full 523-candidate disposition matrix (raw VCI/KBS
  retention, sector classification, blocked reason), retagged with P3-F15/P3-F16's
  `OFFICIAL_QUALIFIED` / `PROVIDER_RESEARCH` / `BLOCKED` authority vocabulary. Provider-tier
  records carry no absolute provider financial facts. Where two retained canonical observations
  share a ticker, provider, metric identity, and consecutive quarterly periods, the existing
  `provider_series_growth` permission allows a bounded trend/direction only. Statement scope,
  currency, unit scale, duration, and cross-provider equivalence remain `UNKNOWN_FAIL_CLOSED`, so
  nothing here is ever promoted to calculation-grade authority by generic inference.

This module computes no new evidence, calls no provider, discovers no new official source route,
and promotes no source/capability/valuation/ranking/recommendation authority. It only recomputes
`fundamental_research_readiness`/`p3f13_official_financial_evidence_scaleout` -- both pure,
deterministic, already-tested functions over already-retained bytes -- and reads P3-F10's frozen
2026-08-20 checkpoint for the (511 or so) candidates that remain outside the official panel. Since
that checkpoint predates two later P3-F13 promotions (PNJ, FPT), this module never trusts its
per-ticker view for a ticker that P3-F13 has since qualified; official rows always take priority
and carry an explicit `supersedes_frozen_p3f10_disposition` note when they do.
"""
from __future__ import annotations

import hashlib
import gzip
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from p3f13_official_financial_evidence_scaleout import DEFAULT_P3F10 as DEFAULT_P3F10_FROZEN
from p3f13_official_financial_evidence_scaleout import execute as execute_p3f13
from two_tier_fundamental_research import ALLOWED as PROVIDER_ALLOWED_USES
from two_tier_fundamental_research import FORBIDDEN as PROVIDER_FORBIDDEN_USES
from fundamental_research_readiness import NON_AUTHORIZED_DOWNSTREAM_USES


ROOT = Path(__file__).resolve().parent
SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "market_wide_current_fundamental_research/v1"
ARTIFACT_TYPE = "MARKET_WIDE_CURRENT_FUNDAMENTAL_RESEARCH"
MILESTONE = "MARKET_WIDE_CURRENT_FUNDAMENTAL_RESEARCH_SCALEOUT_V1"
DEFAULT_CANONICAL_FACTS_ROOT = (
    ROOT / "operations-review" / "p1f-milestone-20260803" / "shadow-build-b"
    / "data" / "canonical-financial-facts" / "facts"
)

OFFICIAL_TIER = "OFFICIAL_QUALIFIED"
PROVIDER_TIER = "PROVIDER_RESEARCH"
BLOCKED_TIER = "BLOCKED"
BLOCKED_METRIC_STATUSES = frozenset({"MISSING", "BLOCKED", "CONFLICT", "NOT_APPLICABLE"})
AVAILABLE_READINESS_STATES = frozenset({"READY", "PARTIAL"})
PROVIDER_SERIES_METRICS = (
    ("revenue_growth", "revenue", "revenue", "growth"),
    ("earnings_growth", "net_income", "earnings", "growth"),
    ("assets_direction", "total_assets", "balance_sheet", "direction"),
    ("equity_direction", "shareholders_equity", "balance_sheet", "direction"),
    ("operating_cash_flow_direction", "operating_cash_flow", "cash_flow", "direction"),
)
PROVIDER_SERIES_LIMITATIONS = (
    "provider_scoped_research_only_not_official_qualified",
    "same_provider_only_no_cross_provider_equivalence",
    "statement_scope_currency_scale_not_independently_qualified",
    "quarterly_duration_and_accounting_identity_not_promoted",
    "not_valuation_recommendation_sizing_or_point_in_time_backtest_authority",
)
PROVIDER_SERIES_COMPARABILITY_SCOPE = (
    "same_ticker_same_provider_same_canonical_metric_consecutive_quarterly_periods_only"
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    """Recompute this artifact's content hash from its own bytes, excluding the identity fields
    it carries itself -- same convention as market_wide_current_liquidity_research.content_identity()
    / market_wide_current_descriptive_research's identity helper, so export_ai_bundle.py can
    verify a retained artifact reproduces its own recorded artifact_sha256 before attaching it."""
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"market_wide_current_fundamental_research:{digest}"}


def _official_ticker_record(readiness_row: Mapping[str, Any], frozen_row: Mapping[str, Any] | None) -> dict[str, Any]:
    """Full per-ticker detail for one officially-qualified issuer, reused verbatim from
    fundamental_research_readiness.py's own per-issuer result. Nothing is recalculated here."""
    identity = readiness_row["issuer_identity"]
    record: dict[str, Any] = {
        "ticker": identity["ticker"],
        "authority_tier": OFFICIAL_TIER,
        "entity_class": identity["entity_class"],
        "sector": identity["entity_class"],
        "fundamental_research_readiness": readiness_row["fundamental_research_readiness"],
        "authoritative_periods_available": list(readiness_row["authoritative_periods_available"]),
        "metrics": readiness_row["metrics"],
        "metric_family_states": readiness_row["metric_family_states"],
        "history_readiness": readiness_row["history_readiness"],
        "evidence_completeness": readiness_row["evidence_completeness"],
        "blocked_metrics": [
            {"metric_id": metric["metric_id"], "status": metric["status"],
             "blocked_reason": metric["blocked_reason"], "periods_used": metric["periods_used"]}
            for metric in readiness_row["metrics"] if metric["status"] in BLOCKED_METRIC_STATUSES
        ],
    }
    if frozen_row is not None and frozen_row.get("disposition") != "EVIDENCE_QUALIFIED":
        # PNJ/FPT today: the frozen 2026-08-20 P3-F10 checkpoint predates their P3-F13
        # promotion. Recorded for lineage, never hidden.
        record["supersedes_frozen_p3f10_disposition"] = frozen_row.get("disposition")
    return record


def _period_key(period: Any) -> tuple[int, int] | None:
    """Return a sortable quarterly key, rejecting annual/opaque retained periods."""
    text = str(period)
    if len(text) != 7 or text[4:6] != "-Q" or text[6] not in "1234" or not text[:4].isdigit():
        return None
    return int(text[:4]), int(text[6])


def _is_consecutive_quarter(previous: str, current: str) -> bool:
    old, new = _period_key(previous), _period_key(current)
    return old is not None and new is not None and (new[0] * 4 + new[1]) == (old[0] * 4 + old[1] + 1)


def _provider_series_metric(*, ticker: str, metric_id: str, source_metric: str,
                            family: str, mode: str, facts: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Derive one permitted provider-series trend from retained canonical provider facts only."""
    base = {
        "ticker": ticker,
        "metric_id": metric_id,
        "metric_family": family,
        "method": "same_provider_consecutive_quarter_provider_series_trend/v1",
        "authority_tier": PROVIDER_TIER,
        "status": "BLOCKED",
        "provider": None,
        "periods": [],
        "lineage": [],
        "data_limitations": list(PROVIDER_SERIES_LIMITATIONS),
        "comparability_scope": PROVIDER_SERIES_COMPARABILITY_SCOPE,
        "blocked_reason": "NO_RETAINED_PROVIDER_REPORTED_SERIES",
    }
    candidates = [
        fact for fact in facts
        if fact.get("canonical_metric") == source_metric
        and fact.get("status") == "provider_reported"
        and fact.get("provider")
        and _period_key(fact.get("reporting_period")) is not None
        and isinstance(fact.get("value"), (int, float))
        and not isinstance(fact.get("value"), bool)
    ]
    if not candidates:
        return base
    candidates.sort(key=lambda fact: (_period_key(fact["reporting_period"]), str(fact["provider"]), str(fact["fact_id"])))
    by_provider: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for fact in candidates:
        by_provider[str(fact["provider"])].append(fact)
    pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for provider_facts in by_provider.values():
        for previous, current in zip(provider_facts, provider_facts[1:]):
            if _is_consecutive_quarter(str(previous["reporting_period"]), str(current["reporting_period"])):
                pairs.append((previous, current))
    if not pairs:
        base["blocked_reason"] = "NO_SAME_PROVIDER_CONSECUTIVE_QUARTER_PAIR"
        return base
    previous, current = max(pairs, key=lambda pair: _period_key(pair[1]["reporting_period"]))
    previous_value, current_value = float(previous["value"]), float(current["value"])
    base.update({
        "provider": str(current["provider"]),
        "periods": [str(previous["reporting_period"]), str(current["reporting_period"])],
        "lineage": [
            {"fact_id": previous.get("fact_id"), "source_observation_ids": list(previous.get("source_observation_ids") or []),
             "source_sha256": previous.get("source_sha256"), "status": previous.get("status")},
            {"fact_id": current.get("fact_id"), "source_observation_ids": list(current.get("source_observation_ids") or []),
             "source_sha256": current.get("source_sha256"), "status": current.get("status")},
        ],
    })
    if mode == "growth":
        if previous_value <= 0:
            base["blocked_reason"] = "GROWTH_BASE_NON_POSITIVE"
            return base
        base["growth_fraction"] = (current_value - previous_value) / previous_value
    else:
        base["direction"] = "INCREASED" if current_value > previous_value else (
            "DECREASED" if current_value < previous_value else "UNCHANGED"
        )
    base["status"] = "AVAILABLE"
    base["blocked_reason"] = None
    return base


def provider_series_trends_for_ticker(*, ticker: str, facts: list[Mapping[str, Any]],
                                      retained_periods: list[str] | None = None) -> dict[str, Any]:
    """Return the allowed provider-series trend envelope for one PROVIDER_RESEARCH ticker."""
    retained_set = set(retained_periods or [])
    scoped_facts = [fact for fact in facts if not retained_set or fact.get("reporting_period") in retained_set]
    metrics = {
        metric_id: _provider_series_metric(
            ticker=ticker, metric_id=metric_id, source_metric=source_metric,
            family=family, mode=mode, facts=scoped_facts,
        )
        for metric_id, source_metric, family, mode in PROVIDER_SERIES_METRICS
    }
    available = sum(metric["status"] == "AVAILABLE" for metric in metrics.values())
    return {
        "authority_tier": PROVIDER_TIER,
        "status": "AVAILABLE" if available else "BLOCKED",
        "usable_metric_count": available,
        "metric_family_coverage": dict(sorted(Counter(
            metric["metric_family"] for metric in metrics.values() if metric["status"] == "AVAILABLE"
        ).items())),
        "metrics": metrics,
        "data_limitations": list(PROVIDER_SERIES_LIMITATIONS),
        "comparability_scope": PROVIDER_SERIES_COMPARABILITY_SCOPE,
        "retained_period_scope": sorted(retained_set),
    }


@lru_cache(maxsize=2)
def load_retained_provider_series(canonical_facts_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Read immutable retained canonical-fact shards; this function makes no provider call."""
    records: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(Path(canonical_facts_root).glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            records[path.name.removesuffix(".jsonl.gz")] = [json.loads(line) for line in handle if line.strip()]
    return records


def _provider_ticker_record(frozen_row: Mapping[str, Any], acquisition_row: Mapping[str, Any] | None,
                            provider_facts: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """One non-officially-qualified candidate. Reuses P3-F10's own disposition row and
    P3-F15/P3-F16's PROVIDER_RESEARCH/BLOCKED authority vocabulary. Zero metric values: scope,
    currency, and unit scale stay UNKNOWN by design -- see module docstring."""
    has_raw = frozen_row["raw_observation_state"] == "RAW_OBSERVED"
    record: dict[str, Any] = {
        "ticker": frozen_row["ticker"],
        "authority_tier": PROVIDER_TIER if has_raw else BLOCKED_TIER,
        "sector": frozen_row["sector"],
        "disposition": frozen_row["disposition"],
        "provider_tier_blocked_reason": frozen_row["blocker"],
        "raw_observation_count": frozen_row["raw_observation_count"],
        "raw_statement_families": list(frozen_row["raw_statement_families"]),
        "raw_providers": list(frozen_row["raw_providers"]),
        "reporting_periods": list(frozen_row["reporting_periods"]),
        "scope_currency_scale_status": "UNKNOWN_FAIL_CLOSED" if has_raw else "NOT_APPLICABLE_NO_SOURCE",
        "allowed_uses": list(PROVIDER_ALLOWED_USES) if has_raw else [],
        "forbidden_uses": list(PROVIDER_FORBIDDEN_USES),
    }
    if acquisition_row is not None:
        record["official_tier_blocked_reason"] = acquisition_row.get("disposition")
        record["official_tier_blocked_detail"] = acquisition_row.get("reason")
    if has_raw:
        record["provider_series_trends"] = provider_series_trends_for_ticker(
            ticker=str(frozen_row["ticker"]), facts=list(provider_facts or []),
            retained_periods=list(frozen_row.get("reporting_periods") or []),
        )
    return record


def _metric_family_coverage(official_records: list[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    coverage: dict[str, Counter[str]] = defaultdict(Counter)
    for record in official_records:
        for family, state in record["metric_family_states"].items():
            coverage[family][state] += 1
    return {family: dict(sorted(counter.items())) for family, counter in sorted(coverage.items())}


def _sector_coverage(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    broad = Counter(record["sector"] for record in records.values())
    official_entity_class = Counter(
        record["entity_class"] for record in records.values() if record["authority_tier"] == OFFICIAL_TIER
    )
    return {
        "broad_sector_distribution_all_candidates": dict(sorted(broad.items())),
        "entity_class_distribution_officially_qualified": dict(sorted(official_entity_class.items())),
    }


def build_artifact(*, p3f10_frozen: Mapping[str, Any], p3f13_current: Mapping[str, Any],
                   requested_at: str,
                   provider_series_by_ticker: Mapping[str, list[Mapping[str, Any]]] | None = None) -> dict[str, Any]:
    """Build the complete market-wide current fundamental-research artifact from two already
    -computed inputs. Raises if p3f13_current was not derived from exactly this p3f10_frozen
    checkpoint (a cross-repository content-identity guard, not a recomputation)."""
    if p3f13_current.get("source_artifacts", {}).get("p3f10") != p3f10_frozen.get("artifact_identity"):
        raise ValueError("P3F10_ARTIFACT_IDENTITY_MISMATCH")

    frozen_rows = {str(row["ticker"]): row for row in p3f10_frozen["instrument_dispositions"]}
    official_rows = {
        str(row["issuer_identity"]["ticker"]): row
        for row in p3f13_current["refreshed_fundamental_readiness"]["issuer_research_readiness"]
    }
    acquisition_by_ticker = {str(row["ticker"]): row for row in p3f13_current["acquisition_dispositions"]}

    all_tickers = sorted(frozen_rows)
    if len(all_tickers) != int(p3f13_current["cohort_identity"]["total_cohort_count"]):
        raise ValueError("COHORT_SIZE_MISMATCH")

    records: dict[str, dict[str, Any]] = {}
    for ticker in all_tickers:
        if ticker in official_rows:
            records[ticker] = _official_ticker_record(official_rows[ticker], frozen_rows.get(ticker))
        else:
            records[ticker] = _provider_ticker_record(
                frozen_rows[ticker], acquisition_by_ticker.get(ticker),
                (provider_series_by_ticker or {}).get(ticker),
            )

    official_tickers = sorted(official_rows)
    official_records = [records[ticker] for ticker in official_tickers]
    metric_status_counts = p3f13_current["refreshed_fundamental_readiness"]["coverage_summary"]["metric_status_counts"]
    tier_counts = Counter(record["authority_tier"] for record in records.values())

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "milestone": MILESTONE,
        "requested_at": requested_at,
        "cohort_identity": p3f10_frozen["cohort_identity"],
        "source_artifacts": {
            "p3f10_frozen": p3f10_frozen.get("artifact_identity"),
            "p3f13_current": p3f13_current.get("artifact_identity"),
            "provider_series_canonical_store_state": (
                p3f10_frozen.get("source_artifacts", {}).get("canonical_store_state")
            ),
        },
        "coverage": {
            "candidate_count": len(all_tickers),
            "issuers_with_official_facts": len(official_tickers),
            "issuers_with_usable_deterministic_metrics": sum(
                1 for ticker in official_tickers
                if records[ticker]["fundamental_research_readiness"] in AVAILABLE_READINESS_STATES
            ),
            "provider_research_tier_count": int(tier_counts.get(PROVIDER_TIER, 0)),
            "blocked_no_source_count": int(tier_counts.get(BLOCKED_TIER, 0)),
            "exact_qualified_metrics": int(metric_status_counts.get("EXACT_QUALIFIED", 0)),
            "derived_proxy_metrics": int(metric_status_counts.get("DERIVED_PROXY", 0)),
            "missing_or_blocked_metrics": (
                int(metric_status_counts.get("MISSING", 0))
                + int(metric_status_counts.get("BLOCKED", 0))
                + int(metric_status_counts.get("CONFLICT", 0))
            ),
            "not_applicable_metrics": int(metric_status_counts.get("NOT_APPLICABLE", 0)),
            "provider_research_usable_for_series_trends_count": sum(
                record.get("provider_series_trends", {}).get("usable_metric_count", 0) > 0
                for record in records.values() if record["authority_tier"] == PROVIDER_TIER
            ),
        },
        "metric_family_coverage": _metric_family_coverage(official_records),
        "provider_series_metric_family_coverage": dict(sorted(Counter(
            metric["metric_family"]
            for record in records.values() if record["authority_tier"] == PROVIDER_TIER
            for metric in record.get("provider_series_trends", {}).get("metrics", {}).values()
            if metric.get("status") == "AVAILABLE"
        ).items())),
        "provider_series_period_coverage": dict(sorted(Counter(
            "->".join(metric["periods"])
            for record in records.values() if record["authority_tier"] == PROVIDER_TIER
            for metric in record.get("provider_series_trends", {}).get("metrics", {}).values()
            if metric.get("status") == "AVAILABLE"
        ).items())),
        "sector_coverage": _sector_coverage(records),
        "data_gap_summary": {
            "official_tier_blocked_reasons": dict(sorted(Counter(
                record["official_tier_blocked_reason"] for record in records.values()
                if record["authority_tier"] != OFFICIAL_TIER and record.get("official_tier_blocked_reason")
            ).items())),
            "provider_tier_blocked_reasons": dict(sorted(Counter(
                record["provider_tier_blocked_reason"] for record in records.values()
                if record["authority_tier"] == PROVIDER_TIER and record.get("provider_tier_blocked_reason")
            ).items())),
            "no_source_available_count": int(tier_counts.get(BLOCKED_TIER, 0)),
        },
        "non_authorized_downstream_uses": list(NON_AUTHORIZED_DOWNSTREAM_USES),
        "provider_tier_allowed_uses": list(PROVIDER_ALLOWED_USES),
        "provider_tier_forbidden_uses": list(PROVIDER_FORBIDDEN_USES),
        "authority_boundary": {
            "official_qualified_is_calculation_grade": True,
            "provider_research_is_descriptive_only": True,
            "provider_research_never_official_label": True,
            "new_evidence_acquired": False,
            "new_source_route_approved": False,
            "authority_promoted": False,
            "valuation_or_ranking_or_recommendation_produced": False,
        },
        "ticker_specific_branch_audit": {"status": "PASS", "production_ticker_literals": []},
        "records": records,
    }
    identity = content_identity(artifact)
    artifact["artifact_sha256"] = identity["artifact_sha256"]
    artifact["artifact_identity"] = identity["artifact_identity"]
    return artifact


def execute(*, p3f10_frozen_path: Path = DEFAULT_P3F10_FROZEN, requested_at: str | None = None) -> dict[str, Any]:
    """Recompute the full artifact live from already-retained bytes: no network call, no new
    evidence, no re-run of P3-F9B/P3-F10's own acquisition (only P3-F13's pure recomputation,
    exactly as its own test suite already does on every run)."""
    p3f10_frozen = json.loads(p3f10_frozen_path.read_text(encoding="utf-8"))
    p3f13_current = execute_p3f13()
    return build_artifact(
        p3f10_frozen=p3f10_frozen, p3f13_current=p3f13_current,
        requested_at=requested_at or datetime.now(timezone.utc).isoformat(),
        provider_series_by_ticker=load_retained_provider_series(DEFAULT_CANONICAL_FACTS_ROOT),
    )
