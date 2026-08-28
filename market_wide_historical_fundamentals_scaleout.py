"""Deterministic provider-tier historical-fundamentals scaleout.

This is an orchestration contract over retained canonical provider facts.  It
does not acquire a source, change provider semantics, or promote any fact to
official authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import canonical_fact_store as store
import financial_operational_proxy as proxy
import market_wide_fundamental_features as features
import market_wide_current_fundamental_research as research
import p3f13_official_financial_evidence_scaleout as p3f13


ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = ROOT / "operations-review" / "p1f-milestone-20260803" / "shadow-build-b"
PROFILES_PATH = ROOT / "config" / "ticker_entity_profiles.csv"
CONTRACT_VERSION = "market_wide_quarterly_fundamental_research_features/v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def build_artifact(*, p3f10_frozen: Mapping[str, Any], p3f13_current: Mapping[str, Any], requested_at: str,
                   runtime_root: Path = RUNTIME_ROOT, profiles_path: Path = PROFILES_PATH) -> dict[str, Any]:
    """Replay every current-consumer ticker through the unmodified proxy contract."""
    tickers = sorted(str(row["ticker"]) for row in p3f10_frozen["instrument_dispositions"])
    resolved = research.build_artifact(p3f10_frozen=p3f10_frozen, p3f13_current=p3f13_current, requested_at=requested_at,
                                      provider_series_by_ticker=research.load_retained_provider_series(research.DEFAULT_CANONICAL_FACTS_ROOT))
    profiles = store.load_entity_profiles(profiles_path)
    citations = store.load_official_citations(runtime_root)
    facts_by_ticker: dict[str, list[dict[str, Any]]] = {}
    entity_type_by_ticker: dict[str, str | None] = {}
    manifest = []
    for ticker in tickers:
        built = store.build_ticker_facts(runtime_root, ticker, profiles=profiles, official_citations=citations)
        facts_by_ticker[ticker] = built["facts"]
        entity_type = resolved["records"][ticker]["entity_class"]
        entity_type_by_ticker[ticker] = entity_type
        manifest.append({"ticker": ticker, "entity_type": entity_type or "unknown", "canonical_fact_count": len(built["facts"]),
                         "terminal_disposition": "REPLAY_ELIGIBLE" if built["facts"] else "NO_RETAINED_PROVIDER_FACTS"})
    operational = proxy.build_operational_proxy_artifact(
        tickers=tickers, facts_by_ticker=facts_by_ticker, entity_type_by_ticker=entity_type_by_ticker,
        refreshed_panel_data=p3f13_current["refreshed_panel_data"], requested_at=requested_at,
    )
    for row in manifest:
        record = operational["records"][row["ticker"]]
        record["fundamental_features"] = features.build_ticker_features(record)
        row["terminal_disposition"] = (
            "ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE" if not record["entity_type_supported_this_milestone"]
            else "OPERATIONAL_PROXY_OR_VERIFIED_RESEARCH_EVIDENCE" if sum(record["tier_counts"].values())
            else "NO_ELIGIBLE_PROVIDER_FACTS"
        )
        row["tier_counts"] = record["tier_counts"]
    attached = research.build_artifact(
        p3f10_frozen=p3f10_frozen, p3f13_current=p3f13_current, requested_at=requested_at,
        provider_series_by_ticker=research.load_retained_provider_series(research.DEFAULT_CANONICAL_FACTS_ROOT),
        operational_proxy_by_ticker=operational["records"],
    )
    by_entity = defaultdict(Counter); by_blocker = Counter(); depth = Counter(); metric_tiers = Counter(); derived = Counter()
    for row in manifest:
        record = operational["records"][row["ticker"]]
        by_entity[row["entity_type"]][row["terminal_disposition"]] += 1
        by_blocker[row["terminal_disposition"]] += 1
        for fact in record.get("facts", []):
            metric_tiers[(fact["canonical_metric"], fact["evidence_tier"])] += 1
        for fact in record.get("derived_metrics", []):
            derived[(fact["derived_metric_id"], fact["status"])] += 1
        depth[len({str(f.get("reporting_period")) for f in record.get("facts", [])})] += 1
    artifact = {"contract_version": CONTRACT_VERSION, "requested_at": requested_at,
        "manifest": manifest,
        "coverage": {"denominator": len(tickers), "terminal_count": len(manifest), "residual": len(tickers) - len(manifest),
                     "by_entity_type": {key: dict(value) for key, value in sorted(by_entity.items())},
                     "terminal_blockers": dict(sorted(by_blocker.items())), "retained_period_depth_distribution": dict(sorted(depth.items())),
                     "facts_by_metric_and_evidence_tier": {f"{metric}:{tier}": count for (metric, tier), count in sorted(metric_tiers.items(), key=lambda item: (str(item[0][0]), str(item[0][1])))},
                     "derived_metrics": {f"{metric}:{status}": count for (metric, status), count in sorted(derived.items(), key=lambda item: (str(item[0][0]), str(item[0][1])))},
                     "operational_proxy": operational["coverage"], "feature_readiness": features.summarize(operational["records"]), "consumer": attached.get("operational_proxy_coverage")},
        "operational_proxy": operational, "consumer_artifact": attached,
        "authority_boundary": {"authoritative_counts_before": 13, "authoritative_counts_after": 13, "authoritative_evidence_promoted": False,
                               "network_used": False, "ocr_used": False, "valuation_unlocked": False,
                               "forbidden_promotions": ["VALUE", "ranking", "target", "recommendation", "sizing", "probability", "PIT"]}}
    artifact["artifact_sha256"] = _identity(artifact)
    artifact["artifact_identity"] = f"{CONTRACT_VERSION}:{artifact['artifact_sha256']}"
    return artifact


def execute(*, requested_at: str = "2026-08-28T00:00:00+07:00") -> dict[str, Any]:
    frozen = json.loads(research.DEFAULT_P3F10_FROZEN.read_text(encoding="utf-8"))
    return build_artifact(p3f10_frozen=frozen, p3f13_current=p3f13.execute(), requested_at=requested_at)
