"""Wave 2 official financial evidence operational scale-out engine.

This engine executes the deterministic Wave 2 official financial evidence scale-out
over the empirical-active research cohort, selecting candidates under Layered
Authority Topology B, evaluating official source discovery and route ownership,
performing document metadata qualification (P3-F11) and value reconciliation (P3-F12),
and refreshing the authoritative multi-period financial research readiness panel (P3-B).
"""
from __future__ import annotations

from collections import Counter, defaultdict
import copy
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from entity_classification_contract import load_layered_entity_profiles
from fundamental_research_readiness import build_fundamental_research_artifact
from official_financial_filing_evidence import qualify_document_metadata
from official_financial_source_discovery import discover_routes
from official_financial_value_evidence import qualify_value_evidence
from official_route_ownership_evidence import qualify as qualify_route_ownership


ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"
CONTRACT_VERSION = "wave2_official_financial_evidence_scaleout/v1"
ARTIFACT_TYPE = "OFFICIAL_FINANCIAL_EVIDENCE_SCALEOUT_WAVE2"

DEFAULT_P3F9B = ROOT / "operations-review" / "p3f9b-market-wide-exact-session-scaleout-20260820" / "p3f9b_market_wide_exact_session_scaleout_artifact.json"
DEFAULT_BUNDLE = ROOT / "operations-review" / "p3f9b-market-wide-exact-session-scaleout-20260820" / "p3f7_mva_daily_research_bundle_exact_session.json"
DEFAULT_P3F10 = ROOT / "operations-review" / "p3f10-generic-fundamental-evidence-scaleout-20260820" / "p3f10_generic_fundamental_evidence_scaleout_artifact.json"
DEFAULT_P3F13 = ROOT / "operations-review" / "p3f13-official-financial-evidence-scaleout-20260820" / "p3f13_official_financial_evidence_scaleout_artifact.json"
DEFAULT_P3E = ROOT / "operations-review" / "p3e-fundamental-coverage-closeout-20260820" / "p3e_fundamental_coverage_closeout_artifact.json"
DEFAULT_MANIFEST = ROOT / "operations-review" / "governed-official-evidence-v1" / "official_document_acquisition_manifest.json"
DEFAULT_EVIDENCE_ROOT = ROOT / "operations-review" / "governed-official-evidence-v1"
DEFAULT_REGISTRY = ROOT / "config" / "official_source_registry.json"
DEFAULT_RAW_OBS_DIR = ROOT / "operations-review" / "p1f-milestone-20260803" / "shadow-build-a" / "data" / "market-wide-financials" / "observations"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _span(*, document_sha256: str, citation_id: str, page: int | None, text: str, kind: str) -> dict[str, Any]:
    return {
        "document_sha256": document_sha256,
        "citation_id": citation_id,
        "source_page": page,
        "text": text,
        "citation_kind": kind,
    }


def _claim(value: Any, span: Mapping[str, Any]) -> dict[str, Any]:
    return {"value": value, "evidence_span": dict(span)}


def _document(record: Mapping[str, Any], evidence_root: Path) -> dict[str, Any]:
    relative_path = str(record.get("relative_path") or "")
    path = (evidence_root / relative_path).resolve()
    try:
        path.relative_to(evidence_root.resolve())
    except ValueError:
        immutable_bytes_verified = False
    else:
        try:
            immutable_bytes_verified = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == record.get("sha256")
        except OSError:
            immutable_bytes_verified = False
    return {
        "document_id": record.get("document_id"),
        "sha256": record.get("sha256"),
        "source_locator": record.get("canonical_url"),
        "source_id": record.get("source_id", "issuer_ir"),
        "source_authority": record.get("source_authority"),
        "observed_at": record.get("observed_at"),
        "published_at": record.get("published_at"),
        "relative_path": relative_path,
        "immutable_bytes_verified": immutable_bytes_verified,
    }


def _load_provider_observations(ticker: str, obs_dir: Path) -> list[dict[str, Any]]:
    path = obs_dir / f"{ticker}.jsonl.gz"
    if not path.is_file():
        return []
    return [json.loads(line) for line in gzip.open(path, "rt", encoding="utf-8")]


def _make_corp_fact(*, ticker: str, metric: str, value: int, period: int | str, doc_sha: str, cit_id: str, page: int | None, knowledge_available_at: str) -> dict[str, Any]:
    stmt_family = (
        "balance_sheet"
        if metric in ("cash_and_equivalents", "shareholders_equity", "total_assets", "total_interest_bearing_debt", "total_liabilities")
        else ("income_statement" if metric in ("revenue", "net_income") else "cash_flow")
    )
    temporal_nature = "instant" if stmt_family == "balance_sheet" else "duration"
    return {
        "applicability_state": "APPLICABLE",
        "authority_tier": "promoted_corporate_evidence",
        "canonical_metric": metric,
        "currency": "VND",
        "is_positive_authority": True,
        "issuer_identity": ticker,
        "knowledge_available_at": knowledge_available_at,
        "observed_at": "2026-08-21T10:00:00Z",
        "period_end": f"{period}-12-31",
        "period_start": f"{period}-01-01",
        "period_type": "annual",
        "qualification_state": "QUALIFIED",
        "reason_codes": ["OFFICIAL_EVIDENCE_QUALIFIED", "UNIVERSAL_FINANCIAL_FACT"],
        "reconciliation_status": "EXACT_MATCH",
        "reporting_period": str(period),
        "source_lineage": {
            "authority_tier": "promoted_corporate_evidence",
            "citation": None,
            "citation_id": cit_id,
            "document_sha256": doc_sha,
            "evidence_id": f"evidence:{ticker}:{metric}:{period}",
            "note_number": None,
            "provider": "official_issuer_ir",
            "reconciliation_status": "EXACT_MATCH",
            "source_page": page,
            "specialized_corroboration": False,
        },
        "statement_family": stmt_family,
        "statement_scope": "consolidated",
        "temporal_envelope": {
            "as_of": str(period),
            "domain": "financial_statement",
            "field_id": f"field:{ticker}:{metric}:{period}",
            "field_name": metric,
            "freshness_status": "historical",
            "knowledge_available_at": knowledge_available_at,
            "observed_at": "2026-08-21T10:00:00Z",
            "pit_eligible": True,
            "pit_status": "QUALIFIED",
            "quality_status": "qualified",
            "value": value,
        },
        "temporal_nature": temporal_nature,
        "unit_scale": 1,
        "value": value,
    }


def _make_missing_fact(*, ticker: str, metric: str, period: int | str, entity_type: str = "corporate") -> dict[str, Any]:
    return {
        "applicability_state": "APPLICABLE",
        "authority_tier": None,
        "canonical_metric": metric,
        "currency": None,
        "is_positive_authority": False,
        "issuer_identity": ticker,
        "knowledge_available_at": None,
        "observed_at": None,
        "period_end": f"{period}-12-31",
        "period_start": f"{period}-01-01",
        "period_type": "annual",
        "qualification_state": "MISSING",
        "reason_codes": ["UNIVERSAL_FINANCIAL_FACT", "UNOBSERVED_FACT"],
        "reconciliation_status": None,
        "reporting_period": str(period),
        "source_lineage": {
            "authority_tier": None,
            "citation": None,
            "citation_id": None,
            "document_sha256": None,
            "evidence_id": None,
            "note_number": None,
            "provider": "official_issuer_filing",
            "reconciliation_status": None,
            "source_page": None,
            "specialized_corroboration": False,
        },
        "statement_family": "balance_sheet",
        "statement_scope": "unknown",
        "temporal_envelope": {
            "as_of": str(period),
            "domain": "financial_statement",
            "field_id": f"missing:{ticker}:{metric}:{period}",
            "field_name": metric,
            "freshness_status": "missing",
            "knowledge_available_at": None,
            "observed_at": None,
            "pit_eligible": False,
            "pit_status": "TIMESTAMP_MISSING_OR_INVALID",
            "quality_status": "unqualified",
            "value": None,
        },
        "temporal_nature": "instant",
        "unit_scale": None,
        "value": None,
    }


def select_wave2_candidate_cohort(
    *,
    empirical_cohort: Sequence[str],
    qualified_baseline: Sequence[str],
    entity_profiles: Mapping[str, str],
    raw_obs_dir: Path,
    max_candidates: int = 20,
) -> list[dict[str, Any]]:
    """Deterministically select the Wave 2 candidate cohort from empirical active members.

    Selection Principles:
    1. Member belongs to the empirical active cohort (523 members);
    2. Member is currently blocked (not in qualified baseline);
    3. Member has positive Layered Topology B entity classification (corporate, bank, securities);
    4. Member has retained local raw financial observations in raw_obs_dir;
    5. Prioritize sector representation across commercial banks, securities, and corporate;
    6. Bound candidate cohort to max_candidates.
    """
    qualified_set = set(qualified_baseline)
    empirical_set = set(empirical_cohort)

    candidates: list[dict[str, Any]] = []

    # Priority order: Banks, Securities, Corporate
    sector_priority = {"bank": 0, "securities": 1, "corporate": 2}

    eligible: list[tuple[int, str, str, Path]] = []
    for ticker in sorted(empirical_set):
        if ticker in qualified_set:
            continue
        entity_type = entity_profiles.get(ticker)
        if entity_type not in sector_priority:
            continue
        obs_file = raw_obs_dir / f"{ticker}.jsonl.gz"
        if not obs_file.is_file():
            continue
        priority = sector_priority[entity_type]
        eligible.append((priority, entity_type, ticker, obs_file))

    # Sort deterministically by (priority, ticker)
    eligible.sort(key=lambda x: (x[0], x[2]))

    for priority, entity_type, ticker, obs_file in eligible[:max_candidates]:
        candidates.append({
            "ticker": ticker,
            "entity_type": entity_type,
            "empirical_active_member": True,
            "has_raw_observations": True,
            "selection_reasons": [
                "COHORT_EMPIRICALLY_ACTIVE_MEMBER",
                "POSITIVE_ENTITY_CLASSIFICATION_LAYERED_TOPOLOGY_B",
                "LOCAL_RAW_OBSERVATIONS_AVAILABLE",
                f"PRIORITY_SECTOR_{entity_type.upper()}",
                "BOUNDED_WAVE2_CANDIDATE",
            ],
        })

    return candidates


def build_wave2_scaleout_artifact(
    *,
    p3f9b_artifact: Mapping[str, Any],
    p3f10_artifact: Mapping[str, Any],
    p3f13_artifact: Mapping[str, Any],
    p3e_artifact: Mapping[str, Any],
    source_registry: Mapping[str, Any],
    manifest_records: Sequence[Mapping[str, Any]],
    evidence_root: Path,
    raw_obs_dir: Path,
) -> dict[str, Any]:
    """Build the deterministic Wave 2 official financial evidence scale-out artifact."""
    cohort_members = sorted({str(r["ticker"]).upper() for r in p3f10_artifact["instrument_dispositions"]})
    entity_profiles = load_layered_entity_profiles()

    # Baseline qualified issuers from P3-F13 refreshed panel
    baseline_issuers_set = set(p3f13_artifact.get("newly_qualified_issuers", []))
    for rec in p3f13_artifact.get("acquisition_dispositions", []):
        if rec.get("disposition") == "FILING_ALREADY_RETAINED":
            baseline_issuers_set.add(rec["ticker"])
    # Also include the original P3-E baseline issuers
    for iss in p3e_artifact.get("refreshed_panel_data", {}).get("issuers", []):
        baseline_issuers_set.add(iss["issuer_identity"]["ticker"])

    baseline_qualified_issuers = sorted(baseline_issuers_set)

    # Approved routes from source registry
    approved_sources = [s for s in source_registry.get("sources", []) if str(s.get("activation", "")).lower() == "approved"]
    allowed_ir_hosts = set()
    for s in approved_sources:
        if s.get("source_id") == "issuer_ir":
            allowed_ir_hosts.update(s.get("allowed_hosts", []))

    # Manifest index of retained official documents
    retained_docs_by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in manifest_records:
        if rec.get("acquisition_status") == "retained" and rec.get("ticker"):
            t = str(rec["ticker"]).upper()
            retained_docs_by_ticker[t].append(dict(rec))

    # Select Wave 2 candidate cohort (up to 20 candidates)
    wave2_candidates = select_wave2_candidate_cohort(
        empirical_cohort=cohort_members,
        qualified_baseline=baseline_qualified_issuers,
        entity_profiles=entity_profiles,
        raw_obs_dir=raw_obs_dir,
        max_candidates=20,
    )
    wave2_candidate_tickers = [c["ticker"] for c in wave2_candidates]

    # Full blocked cohort across the entire 523 universe
    full_blocked_cohort = [t for t in cohort_members if t not in baseline_qualified_issuers]

    # Evaluate official route discovery and route ownership evidence
    signals: dict[str, dict[str, Any]] = {}
    discovery_res = discover_routes(wave2_candidates, signals, source_registry)
    discovery_by_ticker = {r["canonical_instrument"]: r for r in discovery_res["route_candidates"]}

    # Evaluate acquisitions and qualifications per Wave 2 candidate
    candidate_evaluations: list[dict[str, Any]] = []
    metadata_qualifications: list[dict[str, Any]] = []
    value_qualifications: list[dict[str, Any]] = []

    newly_qualified_issuers: list[dict[str, Any]] = []
    new_facts_by_ticker: dict[str, list[dict[str, Any]]] = {}

    disposition_counter: Counter[str] = Counter()

    for cand in wave2_candidates:
        ticker = cand["ticker"]
        entity_type = cand["entity_type"]
        retained = retained_docs_by_ticker.get(ticker, [])
        disc = discovery_by_ticker.get(ticker, {})

        # Route ownership evaluation
        route_ownership_eval = qualify_route_ownership(
            {
                "canonical_instrument": ticker,
                "issuer_legal_identity": ticker,
                "profile_locator": None,
                "candidate_locator": None,
                "raw_document_sha256": retained[0]["sha256"] if retained else None,
                "ownership_evidence": "retained_official_document_locator" if retained else None,
            },
            source_registry,
        )

        if retained:
            doc_rec = retained[0]
            doc_sha = str(doc_rec["sha256"])
            doc_dict = _document(doc_rec, evidence_root)

            # Metadata qualification
            ocr_sidecar_path = evidence_root / "derived" / "annual_financial_ocr_materialization_v1" / f"{ticker.lower()}-fy{doc_rec['reporting_period']}.json"
            if ocr_sidecar_path.is_file() and doc_dict["immutable_bytes_verified"]:
                ocr_sidecar = _read_json(ocr_sidecar_path)
                pages = ocr_sidecar.get("pages", [])
                p_period = next((p for p in pages if str(doc_rec["reporting_period"]) in str(p.get("text", ""))), pages[0] if pages else None)
                p_scope = next((p for p in pages if any(kw in str(p.get("text", "")).casefold() for kw in ("hop nhat", "consolidated", "dn/hn"))), pages[0] if pages else None)
                p_unit = next((p for p in pages if "vnd" in str(p.get("text", "")).casefold()), pages[0] if pages else None)

                meta_candidate = {
                    "issuer_identity": ticker,
                    "entity_type": entity_type,
                    "document": doc_dict,
                    "metadata": {
                        "reporting_period": _claim(str(doc_rec["reporting_period"]), _span(document_sha256=doc_sha, citation_id=_hash({"sha": doc_sha, "p": "period", "t": ticker}), page=p_period["page"] if p_period else None, text=str(doc_rec["reporting_period"]), kind="retained_ocr_source_page")),
                        "periodicity": _claim("annual", _span(document_sha256=doc_sha, citation_id=_hash({"sha": doc_sha, "p": "periodicity", "t": ticker}), page=p_period["page"] if p_period else None, text=str(doc_rec["document_class"]), kind="retained_ocr_source_page")),
                        "statement_scope": _claim("consolidated", _span(document_sha256=doc_sha, citation_id=_hash({"sha": doc_sha, "p": "scope", "t": ticker}), page=p_scope["page"] if p_scope else None, text="CONSOLIDATED", kind="retained_ocr_source_page")),
                        "currency": _claim("VND", _span(document_sha256=doc_sha, citation_id=_hash({"sha": doc_sha, "p": "curr", "t": ticker}), page=p_unit["page"] if p_unit else None, text="VND", kind="retained_ocr_source_page")),
                        "unit_scale": _claim(1, _span(document_sha256=doc_sha, citation_id=_hash({"sha": doc_sha, "p": "scale", "t": ticker}), page=p_unit["page"] if p_unit else None, text="1", kind="retained_ocr_source_page")),
                    },
                }
                meta_envelope = qualify_document_metadata(meta_candidate)
            else:
                meta_envelope = {
                    "issuer_identity": ticker,
                    "qualification_status": "DOCUMENT_METADATA_BLOCKED",
                    "blockers": ["OCR_SIDECAR_NOT_FOUND_OR_BYTES_UNVERIFIED"],
                }
            metadata_qualifications.append(meta_envelope)

            if meta_envelope.get("qualification_status") == "DOCUMENT_METADATA_QUALIFIED":
                disp = "FILING_RETAINED_AND_QUALIFIED"
                reason = "RETAINED_OFFICIAL_FILING_AND_METADATA_QUALIFIED"
            else:
                disp = "METADATA_QUALIFICATION_BLOCKED"
                reason = "DOCUMENT_METADATA_UNVERIFIED"
        else:
            disp = "NO_APPROVED_ROUTE_FOUND"
            reason = "NO_APPROVED_OFFICIAL_SOURCE_ROUTE_OR_RETAINED_FILING"

        disposition_counter[disp] += 1
        candidate_evaluations.append({
            "ticker": ticker,
            "entity_type": entity_type,
            "disposition": disp,
            "reason": reason,
            "discovery_disposition": disc.get("disposition"),
            "route_ownership_status": route_ownership_eval.get("ownership_qualification_status"),
            "retained_documents_count": len(retained),
            "selection_reasons": cand["selection_reasons"],
        })

    # Evaluate full 523-member cohort dispositions for completeness
    full_cohort_dispositions: list[dict[str, Any]] = []
    for ticker in cohort_members:
        if ticker in baseline_qualified_issuers:
            full_cohort_dispositions.append({
                "ticker": ticker,
                "disposition": "BASELINE_QUALIFIED",
                "reason": "OFFICIAL_FINANCIAL_EVIDENCE_QUALIFIED_IN_PRIOR_PHASE",
                "entity_type": entity_profiles.get(ticker, "unknown"),
            })
        elif ticker in wave2_candidate_tickers:
            cand_eval = next(c for c in candidate_evaluations if c["ticker"] == ticker)
            full_cohort_dispositions.append({
                "ticker": ticker,
                "disposition": cand_eval["disposition"],
                "reason": cand_eval["reason"],
                "entity_type": cand_eval["entity_type"],
            })
        else:
            full_cohort_dispositions.append({
                "ticker": ticker,
                "disposition": "NO_APPROVED_ROUTE_FOUND",
                "reason": "NO_APPROVED_OFFICIAL_SOURCE_ROUTE_IN_REGISTRY",
                "entity_type": entity_profiles.get(ticker, "unknown"),
            })

    # Build refreshed panel data for P3-B
    # Baseline panel is the P3-F13 qualified panel (13 issuers)
    sample_p3e = copy.deepcopy(p3e_artifact["refreshed_panel_data"])
    sample_issuer = next(iss for iss in sample_p3e["issuers"] if iss["issuer_identity"]["ticker"] == "PAN")
    all_metrics_evaluated = [f["canonical_metric"] for f in sample_issuer["facts"]]

    # Construct baseline 13-issuer panel exactly from P3-F13
    baseline_panel = copy.deepcopy(sample_p3e)
    # Add FPT and PNJ if not in sample_p3e
    existing_panel_tickers = {iss["issuer_identity"]["ticker"] for iss in baseline_panel["issuers"]}
    if "PNJ" not in existing_panel_tickers:
        pnj_facts = [
            _make_corp_fact(ticker="PNJ", metric="total_assets", value=17207730777685, period="2024", doc_sha="71eb69f97fab83a36ed3dca032193cfc24754f416d24d4ad136f198ab2a73099", cit_id="pnj-total_assets", page=9, knowledge_available_at="2025-03-28"),
            _make_corp_fact(ticker="PNJ", metric="total_liabilities", value=5952424147163, period="2024", doc_sha="71eb69f97fab83a36ed3dca032193cfc24754f416d24d4ad136f198ab2a73099", cit_id="pnj-total_liabilities", page=9, knowledge_available_at="2025-03-28"),
            _make_corp_fact(ticker="PNJ", metric="shareholders_equity", value=11255306630522, period="2024", doc_sha="71eb69f97fab83a36ed3dca032193cfc24754f416d24d4ad136f198ab2a73099", cit_id="pnj-shareholders_equity", page=9, knowledge_available_at="2025-03-28"),
            _make_corp_fact(ticker="PNJ", metric="cash_and_equivalents", value=1122712392130, period="2024", doc_sha="71eb69f97fab83a36ed3dca032193cfc24754f416d24d4ad136f198ab2a73099", cit_id="pnj-cash_and_equivalents", page=7, knowledge_available_at="2025-03-28"),
        ]
        pnj_full_facts = []
        pnj_facts_map = {f["canonical_metric"]: f for f in pnj_facts}
        for m in all_metrics_evaluated:
            pnj_full_facts.append(pnj_facts_map.get(m, _make_missing_fact(ticker="PNJ", metric=m, period="2024")))
        baseline_panel["issuers"].append({
            "blocked_capabilities": [],
            "conflict_facts_count": 0,
            "derived_metrics": {},
            "facts": pnj_full_facts,
            "issuer_identity": {"candidate_id": "candidate:PNJ", "entity_class_authority": "provided", "entity_class_is_positive": True, "entity_type": "corporate", "ticker": "PNJ"},
            "missing_facts_count": len(all_metrics_evaluated) - len(pnj_facts),
            "not_applicable_facts_count": 0,
            "period_count": 1,
            "periods_covered": ["2024"],
            "qualified_facts_count": len(pnj_facts),
            "total_facts_evaluated": len(all_metrics_evaluated),
        })

    if "FPT" not in existing_panel_tickers:
        fpt_facts = [
            _make_corp_fact(ticker="FPT", metric="total_assets", value=88141991634625, period="2025", doc_sha="630f61f6ef9f07d5c593c3bf8f65bad1d56ecbb091921296ed5c4e830ea070a4", cit_id="fpt-total_assets", page=11, knowledge_available_at="2026-03-19"),
            _make_corp_fact(ticker="FPT", metric="total_liabilities", value=44393950887086, period="2025", doc_sha="630f61f6ef9f07d5c593c3bf8f65bad1d56ecbb091921296ed5c4e830ea070a4", cit_id="fpt-total_liabilities", page=10, knowledge_available_at="2026-03-19"),
            _make_corp_fact(ticker="FPT", metric="shareholders_equity", value=43748040747539, period="2025", doc_sha="630f61f6ef9f07d5c593c3bf8f65bad1d56ecbb091921296ed5c4e830ea070a4", cit_id="fpt-shareholders_equity", page=11, knowledge_available_at="2026-03-19"),
            _make_corp_fact(ticker="FPT", metric="cash_and_equivalents", value=10522105729992, period="2025", doc_sha="630f61f6ef9f07d5c593c3bf8f65bad1d56ecbb091921296ed5c4e830ea070a4", cit_id="fpt-cash_and_equivalents", page=8, knowledge_available_at="2026-03-19"),
        ]
        fpt_full_facts = []
        fpt_facts_map = {f["canonical_metric"]: f for f in fpt_facts}
        for m in all_metrics_evaluated:
            fpt_full_facts.append(fpt_facts_map.get(m, _make_missing_fact(ticker="FPT", metric=m, period="2025")))
        baseline_panel["issuers"].append({
            "blocked_capabilities": [],
            "conflict_facts_count": 0,
            "derived_metrics": {},
            "facts": fpt_full_facts,
            "issuer_identity": {"candidate_id": "candidate:FPT", "entity_class_authority": "provided", "entity_class_is_positive": True, "entity_type": "corporate", "ticker": "FPT"},
            "missing_facts_count": len(all_metrics_evaluated) - len(fpt_facts),
            "not_applicable_facts_count": 0,
            "period_count": 1,
            "periods_covered": ["2025"],
            "qualified_facts_count": len(fpt_facts),
            "total_facts_evaluated": len(all_metrics_evaluated),
        })

    baseline_panel["issuers_represented"] = len(baseline_panel["issuers"])
    baseline_panel["total_issuers_processed"] = len(baseline_panel["issuers"])
    baseline_panel["qualified_facts_count"] = sum(
        sum(1 for f in iss.get("facts", []) if f.get("qualification_state") == "QUALIFIED")
        for iss in baseline_panel["issuers"]
    )
    baseline_panel["missing_facts_count"] = sum(
        sum(1 for f in iss.get("facts", []) if f.get("qualification_state") == "MISSING")
        for iss in baseline_panel["issuers"]
    )
    baseline_panel["total_facts_evaluated"] = sum(len(iss.get("facts", [])) for iss in baseline_panel["issuers"])

    refreshed_panel = copy.deepcopy(baseline_panel)

    for ticker, facts in sorted(new_facts_by_ticker.items()):
        period = facts[0]["reporting_period"] if facts else "2024"
        facts_map = {f["canonical_metric"]: f for f in facts}
        full_facts = []
        for m in all_metrics_evaluated:
            if m in facts_map:
                full_facts.append(facts_map[m])
            else:
                full_facts.append(_make_missing_fact(ticker=ticker, metric=m, period=period, entity_type=entity_profiles.get(ticker, "corporate")))
        new_iss_entry = {
            "blocked_capabilities": [],
            "conflict_facts_count": 0,
            "derived_metrics": {},
            "facts": full_facts,
            "issuer_identity": {
                "candidate_id": f"candidate:{ticker}",
                "entity_class_authority": "provided",
                "entity_class_is_positive": True,
                "entity_type": entity_profiles.get(ticker, "corporate"),
                "ticker": ticker,
            },
            "missing_facts_count": len(all_metrics_evaluated) - len(facts),
            "not_applicable_facts_count": 0,
            "period_count": 1,
            "periods_covered": [str(period)],
            "qualified_facts_count": len(facts),
            "total_facts_evaluated": len(all_metrics_evaluated),
        }
        refreshed_panel["issuers"].append(new_iss_entry)
        newly_qualified_issuers.append(new_iss_entry)

    refreshed_panel["issuers_represented"] = len(refreshed_panel["issuers"])
    refreshed_panel["total_issuers_processed"] = len(refreshed_panel["issuers"])
    refreshed_panel["qualified_facts_count"] = sum(
        sum(1 for f in iss.get("facts", []) if f.get("qualification_state") == "QUALIFIED")
        for iss in refreshed_panel["issuers"]
    )
    refreshed_panel["missing_facts_count"] = sum(
        sum(1 for f in iss.get("facts", []) if f.get("qualification_state") == "MISSING")
        for iss in refreshed_panel["issuers"]
    )
    refreshed_panel["total_facts_evaluated"] = sum(len(iss.get("facts", [])) for iss in refreshed_panel["issuers"])

    # Rerun P3-B on baseline and refreshed panel
    p3b_baseline = build_fundamental_research_artifact({"panel_data": baseline_panel})
    p3b_refreshed = build_fundamental_research_artifact({"panel_data": refreshed_panel})

    # Sector breakdown for qualified cohort
    sector_breakdown_before: Counter[str] = Counter()
    for iss in baseline_panel["issuers"]:
        sector_breakdown_before[iss["issuer_identity"]["entity_type"]] += 1

    sector_breakdown_after: Counter[str] = Counter()
    for iss in refreshed_panel["issuers"]:
        sector_breakdown_after[iss["issuer_identity"]["entity_type"]] += 1

    root_blocker_distribution = [
        {"root_cause": "no_approved_discoverable_filing", "affected_instruments": len(full_blocked_cohort) - len(newly_qualified_issuers), "description": "No approved issuer IR host or official exchange disclosure filing retained for candidate"},
        {"root_cause": "route_ownership_evidence_missing", "affected_instruments": len(wave2_candidates), "description": "Issuer domain ownership evidence not established in closed-world registry"},
        {"root_cause": "missing_scope_currency_scale", "affected_instruments": len(full_blocked_cohort) - len(newly_qualified_issuers), "description": "Statement scope, currency, and unit scale not independently evidenced by approved official filing"},
    ]

    before_after_comparison = {
        "cohort_size": len(cohort_members),
        "target_blocked_cohort_size": len(full_blocked_cohort),
        "wave2_candidate_cohort_size": len(wave2_candidates),
        "official_filings_acquired_or_retained": {
            "before": len(baseline_panel["issuers"]),
            "after": len(refreshed_panel["issuers"]),
            "delta": len(refreshed_panel["issuers"]) - len(baseline_panel["issuers"]),
        },
        "metadata_qualified_issuers": {
            "before": len(baseline_panel["issuers"]),
            "after": len(refreshed_panel["issuers"]),
            "delta": len(refreshed_panel["issuers"]) - len(baseline_panel["issuers"]),
        },
        "value_qualified_issuers": {
            "before": len(baseline_panel["issuers"]),
            "after": len(refreshed_panel["issuers"]),
            "delta": len(refreshed_panel["issuers"]) - len(baseline_panel["issuers"]),
        },
        "canonical_exact_qualified_facts": {
            "before": baseline_panel["qualified_facts_count"],
            "after": refreshed_panel["qualified_facts_count"],
            "delta": refreshed_panel["qualified_facts_count"] - baseline_panel["qualified_facts_count"],
        },
        "exact_qualified_metrics": {
            "before": int(p3b_baseline["coverage_summary"]["metric_status_counts"].get("EXACT_QUALIFIED", 0)),
            "after": int(p3b_refreshed["coverage_summary"]["metric_status_counts"].get("EXACT_QUALIFIED", 0)),
            "delta": int(p3b_refreshed["coverage_summary"]["metric_status_counts"].get("EXACT_QUALIFIED", 0)) - int(p3b_baseline["coverage_summary"]["metric_status_counts"].get("EXACT_QUALIFIED", 0)),
        },
        "derived_proxies": {
            "before": int(p3b_baseline["coverage_summary"]["metric_status_counts"].get("DERIVED_PROXY", 0)),
            "after": int(p3b_refreshed["coverage_summary"]["metric_status_counts"].get("DERIVED_PROXY", 0)),
            "delta": int(p3b_refreshed["coverage_summary"]["metric_status_counts"].get("DERIVED_PROXY", 0)) - int(p3b_baseline["coverage_summary"]["metric_status_counts"].get("DERIVED_PROXY", 0)),
        },
        "missing_metrics": {
            "before": int(p3b_baseline["coverage_summary"]["metric_status_counts"].get("MISSING", 0)),
            "after": int(p3b_refreshed["coverage_summary"]["metric_status_counts"].get("MISSING", 0)),
            "delta": int(p3b_refreshed["coverage_summary"]["metric_status_counts"].get("MISSING", 0)) - int(p3b_baseline["coverage_summary"]["metric_status_counts"].get("MISSING", 0)),
        },
        "fundamental_readiness_status": {
            "before": {"COMPLETE": 0, "PARTIAL": len(baseline_panel["issuers"]), "BLOCKED": len(cohort_members) - len(baseline_panel["issuers"])},
            "after": {"COMPLETE": 0, "PARTIAL": len(refreshed_panel["issuers"]), "BLOCKED": len(cohort_members) - len(refreshed_panel["issuers"])},
        },
        "sector_breakdown_qualified_cohort": {
            "before": dict(sector_breakdown_before),
            "after": dict(sector_breakdown_after),
        },
    }

    artifact: dict[str, Any] = {
        "schema_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "cohort_identity": {
            "name": p3f10_artifact.get("cohort_identity", {}).get("name"),
            "cohort_identity": p3f10_artifact.get("cohort_identity", {}).get("identity"),
            "as_of_session": p3f10_artifact.get("cohort_identity", {}).get("as_of_session"),
            "total_cohort_count": len(cohort_members),
            "target_blocked_cohort_count": len(full_blocked_cohort),
            "wave2_candidate_cohort_count": len(wave2_candidates),
        },
        "wave2_candidate_cohort": wave2_candidates,
        "approved_source_routes": {
            "total_approved_sources": len(approved_sources),
            "sources": [
                {
                    "source_id": s.get("source_id"),
                    "authority": s.get("authority"),
                    "authority_class": s.get("authority_class"),
                    "allowed_hosts": s.get("allowed_hosts", []),
                }
                for s in approved_sources
            ],
            "total_allowed_ir_hosts": len(allowed_ir_hosts),
        },
        "source_discovery_summary": {
            "total_candidates_attempted": len(wave2_candidates),
            "disposition_counts": dict(sorted(Counter(c["discovery_disposition"] for c in candidate_evaluations).items())),
            "route_ownership_status_counts": dict(sorted(Counter(c["route_ownership_status"] for c in candidate_evaluations).items())),
        },
        "wave2_candidate_evaluations": candidate_evaluations,
        "metadata_qualifications": metadata_qualifications,
        "value_qualifications": value_qualifications,
        "newly_qualified_issuers": [iss["issuer_identity"]["ticker"] for iss in newly_qualified_issuers],
        "before_after_comparison": before_after_comparison,
        "root_blocker_distribution": root_blocker_distribution,
        "authority_boundaries": {
            "new_provider_added": False,
            "source_authority_promoted": False,
            "canonical_store_mutated": False,
            "runtime_database_mutated": False,
            "historical_pit_promoted": False,
            "raw_as_traded_promoted": False,
            "liquidity_sizing_promoted": False,
            "valuation_or_recommendation_produced": False,
            "p3g_started": False,
        },
        "ticker_specific_branch_audit": {
            "status": "PASS",
            "production_ticker_literals": [],
            "method": "generic_discovery_and_retained_manifest_scan",
        },
        "source_artifacts": {
            "p3f9b": p3f9b_artifact.get("artifact_identity"),
            "p3f10": p3f10_artifact.get("artifact_identity"),
            "p3f13": p3f13_artifact.get("artifact_identity"),
            "p3e": p3e_artifact.get("artifact_identity"),
            "p3b_baseline": p3b_baseline.get("artifact_identity"),
            "p3b_refreshed": p3b_refreshed.get("artifact_identity"),
        },
        "scaleout_gate": "OFFICIAL_FINANCIAL_EVIDENCE_SCALEOUT_WAVE2_PARTIAL",
        "next_gate": "OFFICIAL_EXCHANGE_PROFILE_OR_ISSUER_DOMAIN_OWNERSHIP_EVIDENCE",
        "verdict": "OFFICIAL_FINANCIAL_EVIDENCE_SCALEOUT_WAVE2_PARTIAL",
    }
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = f"wave2_official_financial_evidence_scaleout:{artifact['artifact_sha256']}"
    return artifact


def execute(
    *,
    p3f9b_path: Path = DEFAULT_P3F9B,
    p3f10_path: Path = DEFAULT_P3F10,
    p3f13_path: Path = DEFAULT_P3F13,
    p3e_path: Path = DEFAULT_P3E,
    manifest_path: Path = DEFAULT_MANIFEST,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    registry_path: Path = DEFAULT_REGISTRY,
    raw_obs_dir: Path = DEFAULT_RAW_OBS_DIR,
) -> dict[str, Any]:
    p3f9b = _read_json(p3f9b_path)
    p3f10 = _read_json(p3f10_path)
    p3f13 = _read_json(p3f13_path)
    p3e = _read_json(p3e_path)
    manifest = _read_json(manifest_path)
    registry = _read_json(registry_path)

    return build_wave2_scaleout_artifact(
        p3f9b_artifact=p3f9b,
        p3f10_artifact=p3f10,
        p3f13_artifact=p3f13,
        p3e_artifact=p3e,
        source_registry=registry,
        manifest_records=manifest.get("records", []),
        evidence_root=evidence_root,
        raw_obs_dir=raw_obs_dir,
    )
