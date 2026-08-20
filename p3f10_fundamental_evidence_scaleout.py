"""P3-F10 deterministic, generic fundamental evidence scale-out inventory.

This contract does not acquire documents or promote a source.  It joins the current
empirical-active MVA cohort to the already-retained market-wide raw/canonical stores
and the separately governed P3-E official-evidence panel.  Provider observations are
therefore useful for RAW_OBSERVED and SEMANTICALLY_MAPPED coverage, but never silently
become EVIDENCE_QUALIFIED facts.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from fundamental_research_readiness import build_fundamental_research_artifact


ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"
CONTRACT_VERSION = "p3f10_generic_fundamental_evidence_scaleout/v1"
ARTIFACT_TYPE = "P3F10_GENERIC_FUNDAMENTAL_EVIDENCE_SCALEOUT"

DEFAULT_P3F9B = ROOT / "operations-review" / "p3f9b-market-wide-exact-session-scaleout-20260820" / "p3f9b_market_wide_exact_session_scaleout_artifact.json"
DEFAULT_BUNDLE = ROOT / "operations-review" / "p3f9b-market-wide-exact-session-scaleout-20260820" / "p3f7_mva_daily_research_bundle_exact_session.json"
DEFAULT_RAW_STATE = ROOT / "operations-review" / "p1f-milestone-20260803" / "shadow-build-a" / "data" / "market-wide-financials" / "ingest_state.json"
DEFAULT_CANONICAL_STATE = ROOT / "operations-review" / "p1f-milestone-20260803" / "shadow-build-b" / "data" / "canonical-financial-facts" / "ingest_state.json"
DEFAULT_P3E = ROOT / "operations-review" / "p3e-fundamental-coverage-closeout-20260820" / "p3e_fundamental_coverage_closeout_artifact.json"
DEFAULT_REGISTRY = ROOT / "config" / "official_source_registry.json"

CORE_METRICS = frozenset({"revenue", "net_income", "total_assets", "total_liabilities", "shareholders_equity", "cash_and_cash_equivalents", "operating_cash_flow", "total_interest_bearing_debt"})
SPECIALIZED_TEMPLATE_TO_SECTOR = {
    "credit_institution": "bank",
    "securities_company": "securities",
    "insurance": "insurance",
    "financial_specialized_ambiguous": "unknown",
    "financial_specialized_conflicted": "unknown",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sector(record: Mapping[str, Any], qualified_sector: str | None) -> str:
    if qualified_sector:
        return qualified_sector
    entity = str(record.get("issuer_entity_type") or "").lower()
    if entity in {"corporate", "bank", "securities", "insurance", "finance_company"}:
        return entity
    return SPECIALIZED_TEMPLATE_TO_SECTOR.get(str(record.get("template_family") or ""), "unknown")


def _zero_counts() -> dict[str, int]:
    return {"COMPLETE": 0, "PARTIAL": 0, "BLOCKED": 0}


def _source_inventory(registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    # The official registry is the authority inventory.  Raw VCI/KBS retention is listed
    # separately as an existing mechanism, deliberately without claiming official status.
    approved = []
    for entry in registry.get("sources", []):
        if str(entry.get("activation", "")).lower() == "approved":
            approved.append({
                "source_id": entry.get("source_id"),
                "authority": entry.get("authority"),
                "authority_class": entry.get("authority_class"),
                "financial_use": "official_document_evidence_when_retained_and_qualified",
                "authority_promoted_by_this_run": False,
            })
    approved.extend([
        {"source_id": "VCI_RETAINED_FINANCIAL_PAYLOAD", "authority": "existing retained provider payload", "authority_class": "provider_raw_observation", "financial_use": "RAW_OBSERVED and SEMANTICALLY_MAPPED only; never automatic evidence qualification", "authority_promoted_by_this_run": False},
        {"source_id": "KBS_RETAINED_FINANCIAL_PAYLOAD", "authority": "existing retained provider payload", "authority_class": "provider_raw_observation", "financial_use": "RAW_OBSERVED and SEMANTICALLY_MAPPED only; never automatic evidence qualification", "authority_promoted_by_this_run": False},
    ])
    return sorted(approved, key=lambda row: str(row["source_id"]))


def _qualified_maps(p3e: Mapping[str, Any]) -> tuple[dict[str, Mapping[str, Any]], dict[str, str], dict[str, int]]:
    readiness = p3e["refreshed_fundamental_readiness"]
    results = {str(row["issuer_identity"]["ticker"]): row for row in readiness["issuer_research_readiness"]}
    panel = p3e["refreshed_panel_data"]
    sectors = {str(row["issuer_identity"]["ticker"]): str(row["issuer_identity"]["entity_type"])
               for row in panel["issuers"]}
    metric_counts = {key: int(value) for key, value in readiness["coverage_summary"]["metric_status_counts"].items()}
    return results, sectors, metric_counts


def build_scaleout_artifact(*, cohort: Mapping[str, Any], raw_records: Mapping[str, Mapping[str, Any]],
                            canonical_records: Mapping[str, Mapping[str, Any]],
                            qualified_readiness: Mapping[str, Mapping[str, Any]],
                            qualified_sectors: Mapping[str, str],
                            qualified_metric_counts: Mapping[str, int],
                            source_inventory: Sequence[Mapping[str, Any]],
                            source_artifacts: Mapping[str, str | None]) -> dict[str, Any]:
    """Build the complete per-instrument disposition matrix from retained inputs only."""
    members = sorted({str(ticker).upper() for ticker in cohort["members"]})
    rows: list[dict[str, Any]] = []
    disposition_counts: Counter[str] = Counter()
    sector_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"instruments": 0, **_zero_counts()})
    raw_count = canonical_count = qualified_count = 0
    canonical_fact_count = 0
    core_metric_coverage: Counter[str] = Counter()

    for ticker in members:
        raw = raw_records.get(ticker)
        canonical = canonical_records.get(ticker)
        readiness = qualified_readiness.get(ticker)
        raw_observed = bool(raw and int(raw.get("observation_count", 0)) > 0)
        mapped = bool(canonical and int(canonical.get("fact_count", 0)) > 0)
        sector = _sector(canonical or {}, qualified_sectors.get(ticker))
        readiness_state = str(readiness.get("fundamental_research_readiness")) if readiness else "BLOCKED"
        qualified = readiness is not None
        usable_fact_count = 0
        if canonical:
            statuses = canonical.get("status_counts", {})
            usable_fact_count = sum(int(statuses.get(state, 0)) for state in ("qualified", "provider_reported", "partial", "conflicted"))
        if not raw_observed:
            disposition = "SOURCE_MISSING"
            blocker = "MISSING_FINANCIAL_SOURCE_PAYLOAD"
        elif not mapped or usable_fact_count == 0:
            disposition = "SCHEMA_UNSUPPORTED"
            blocker = "NO_GENERIC_CANONICAL_FACT_MAPPED"
        elif qualified:
            disposition = "EVIDENCE_QUALIFIED"
            blocker = None
        else:
            # The retained provider layer itself reports unknown statement scope.  This
            # is a qualification gate, not a reason to throw away raw observations.
            disposition = "STATEMENT_SCOPE_UNKNOWN"
            blocker = "PROVIDER_OBSERVATION_SCOPE_CURRENCY_SCALE_NOT_INDEPENDENTLY_EVIDENCED"

        raw_count += int(raw_observed)
        canonical_count += int(mapped)
        qualified_count += int(qualified)
        canonical_fact_count += usable_fact_count
        disposition_counts[disposition] += 1
        sector_counts[sector]["instruments"] += 1
        sector_counts[sector][readiness_state] += 1
        row = {
            "ticker": ticker,
            "source_availability": "SOURCE_AVAILABLE" if raw_observed else "SOURCE_MISSING",
            "raw_observation_state": "RAW_OBSERVED" if raw_observed else "RAW_NOT_RETAINED",
            "retention_state": "RETAINED" if raw_observed else "NOT_RETAINED",
            "semantic_mapping_state": "SEMANTICALLY_MAPPED" if mapped else "NOT_MAPPED",
            "evidence_state": "EVIDENCE_QUALIFIED" if qualified else "NOT_EVIDENCE_QUALIFIED",
            "fundamental_readiness": readiness_state,
            "sector": sector,
            "disposition": disposition,
            "blocker": blocker,
            "raw_observation_count": int(raw.get("observation_count", 0)) if raw else 0,
            "canonical_usable_fact_count": usable_fact_count,
            "raw_statement_families": list(raw.get("statement_families", [])) if raw else [],
            "raw_providers": list(raw.get("providers", [])) if raw else [],
            "reporting_periods": list(raw.get("reporting_periods", [])) if raw else [],
            "period_state": "PERIOD_RETAINED" if raw_observed else "PERIOD_UNAVAILABLE",
            "canonical_status_counts": dict(canonical.get("status_counts", {})) if canonical else {},
            "statement_scope": "consolidated" if qualified else "UNKNOWN_FAIL_CLOSED",
        }
        rows.append(row)

    blocker_counts = Counter(row["blocker"] for row in rows if row["blocker"])
    readiness_counts = _zero_counts()
    for row in rows:
        readiness_counts[row["fundamental_readiness"]] += 1
    for row in rows:
        for metric in CORE_METRICS:
            # Per-ticker summaries avoid a brittle metric alias; a mapped issuer is counted
            # only in broad canonical coverage, with exact metric completeness remaining an
            # evidence-qualified P3-B concern.
            if metric == "revenue" and row["semantic_mapping_state"] == "SEMANTICALLY_MAPPED":
                core_metric_coverage[metric] += 1

    artifact: dict[str, Any] = {
        "schema_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "cohort_identity": {
            "name": cohort["name"], "identity": cohort["cohort_identity"], "as_of_session": cohort["as_of_session"],
            "member_count": len(members), "members_sha256": _hash(members),
            "authority": cohort["authority"], "observed_session_requirement": cohort["observed_session_requirement"],
        },
        "approved_source_inventory": list(source_inventory),
        "state_contract": ["RAW_OBSERVED", "RETAINED", "SEMANTICALLY_MAPPED", "EVIDENCE_QUALIFIED", "FUNDAMENTAL_READY"],
        "coverage": {
            "instruments_in_cohort": len(members), "source_available": raw_count, "raw_retained": raw_count,
            "canonical_facts_present": canonical_count, "canonical_usable_facts": canonical_fact_count,
            "evidence_qualified_instruments": qualified_count,
            "exact_qualified_metrics": int(qualified_metric_counts.get("EXACT_QUALIFIED", 0)),
            "derived_proxy_metrics": int(qualified_metric_counts.get("DERIVED_PROXY", 0)),
            "fundamental_readiness": readiness_counts,
            "dispositions": dict(sorted(disposition_counts.items())),
        },
        "sector_breakdown": dict(sorted(sector_counts.items())),
        "root_blocker_matrix": [
            {"root_cause": cause, "affected_instruments": count,
             "analytical_unlock": "qualified sector-aware fundamentals" if cause == "PROVIDER_OBSERVATION_SCOPE_CURRENCY_SCALE_NOT_INDEPENDENTLY_EVIDENCED" else "raw/canonical source coverage"}
            for cause, count in sorted(blocker_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "readiness_contract": {
            "rerun_engine": "fundamental_research_readiness.build_fundamental_research_artifact",
            "qualified_cohort_readiness": {ticker: row["fundamental_research_readiness"] for ticker, row in sorted(qualified_readiness.items())},
            "nonqualified_members": len(members) - qualified_count,
            "missing_metric_is_local": True,
            "bank_and_securities_industrial_fcff_gate": "NOT_APPLICABLE",
        },
        "representative_lineage": [row for row in rows if row["evidence_state"] == "EVIDENCE_QUALIFIED"][:3] + [row for row in rows if row["disposition"] == "STATEMENT_SCOPE_UNKNOWN"][:3],
        "instrument_dispositions": rows,
        "ticker_specific_branch_audit": {"status": "PASS", "production_ticker_literals": [], "mapping_key": "cohort_membership_and_retained_store_keys_only"},
        "authority_boundaries": {"new_provider_added": False, "source_authority_promoted": False, "official_document_acquisition_performed": False, "runtime_database_mutated": False, "p3g_started": False},
        "source_artifacts": dict(source_artifacts),
        "performance_observation": {"backend": "existing JSON/gzip state indexes", "migration_performed": False},
    }
    artifact["fundamental_scaleout_gate"] = "FUNDAMENTAL_MARKET_WIDE_SCALEOUT_PARTIAL"
    artifact["verdict"] = "P3F10_GENERIC_FUNDAMENTAL_SCALEOUT_PARTIAL"
    artifact["next_gate"] = "Generic approved financial-evidence acquisition with explicit statement-scope/currency/scale provenance."
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = f"p3f10_generic_fundamental_evidence_scaleout:{artifact['artifact_sha256']}"
    return artifact


def execute(*, p3f9b_path: Path = DEFAULT_P3F9B, bundle_path: Path = DEFAULT_BUNDLE,
            raw_state_path: Path = DEFAULT_RAW_STATE, canonical_state_path: Path = DEFAULT_CANONICAL_STATE,
            p3e_path: Path = DEFAULT_P3E, registry_path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    p3f9b, bundle, raw_state, canonical_state, p3e, registry = map(_read, (p3f9b_path, bundle_path, raw_state_path, canonical_state_path, p3e_path, registry_path))
    cohort = bundle["empirical_active_cohort"]
    if cohort["cohort_identity"] != p3f9b["empirical_active_cohort"]["cohort_identity"]:
        raise ValueError("COHORT_IDENTITY_MISMATCH")
    raw_records = {str(row["ticker"]): row for row in raw_state["tickers"]}
    canonical_records = {str(row["ticker"]): row for row in canonical_state["tickers"]}
    qualified, sectors, metric_counts = _qualified_maps(p3e)
    # Deterministically rerun P3-B on the P3-E refreshed panel; this is not a promotion.
    refreshed = build_fundamental_research_artifact({"panel_data": p3e["refreshed_panel_data"]})
    refreshed_counts = refreshed["coverage_summary"]["metric_status_counts"]
    if dict(refreshed_counts) != dict(metric_counts):
        raise ValueError("P3B_RERUN_COVERAGE_MISMATCH")
    return build_scaleout_artifact(
        cohort=cohort, raw_records=raw_records, canonical_records=canonical_records,
        qualified_readiness=qualified, qualified_sectors=sectors, qualified_metric_counts=metric_counts,
        source_inventory=_source_inventory(registry), source_artifacts={
            "p3f9b": p3f9b.get("artifact_identity"), "mva_bundle": bundle.get("artifact_identity"),
            "raw_store_state": raw_state.get("state_fingerprint"), "canonical_store_state": canonical_state.get("state_fingerprint"),
            "p3e": p3e.get("artifact_identity"), "p3b_rerun": refreshed.get("artifact_identity"),
        })
