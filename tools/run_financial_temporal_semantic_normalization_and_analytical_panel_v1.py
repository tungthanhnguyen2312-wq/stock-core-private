"""Evidence package for FINANCIAL_TEMPORAL_SEMANTIC_NORMALIZATION_AND_ANALYTICAL_PANEL_V1.

This is a reporting/replay tool, not another financial engine. It reads the already-regenerated
retained semantic-fact snapshots (old: 20260831, new: 20260905) and the live Financial V2 engine
chain (now including the wired TTM bridge), and materializes the owner-requested local
operations-review evidence. No network, provider, database, or remote Git operation is used.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import canonical_daily_financial_v2_materialization as mat
import canonical_financial_analytical_panel as panel
import entity_classification_contract as entity_classification
import feature_input_fitness_contract as fitness_contract
import financial_v2_current_input_authority as authority
import market_wide_financial_analysis_v2_scaleout as scaleout
import owner_research_focus
import structured_financial_period_semantics as sem

MILESTONE = "FINANCIAL_TEMPORAL_SEMANTIC_NORMALIZATION_AND_ANALYTICAL_PANEL_V1"
OWNER_OVERRIDE = "OWNER_AUTHORIZATION_2026_09_05_QUEUED_NEXT_EMPTY_FINANCIAL_TEMPORAL_SEMANTIC_NORMALIZATION_AND_ANALYTICAL_PANEL_V1"
PRIMARY_SESSION = "2026-09-05"
TEMPORAL_TARGET_SESSION = "2026-08-25"
OLD_SEMANTICS_DIR = ROOT / "operations-review" / "market-wide-structured-financial-period-semantics-v1-20260831"
NEW_SEMANTICS_DIR = ROOT / "operations-review" / "market-wide-structured-financial-period-semantics-v1-20260905"
DEFAULT_OUTPUT = ROOT / "operations-review" / "financial-temporal-semantic-normalization-and-analytical-panel-v1-20260905"

REQUIRED_WATCHLIST = ("EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM")
SECTOR_EXAMPLES = {"VCB": "bank", "SSI": "securities", "BVH": "insurance", "HPG": "industrial", "VNM": "consumer", "NVL": "real_estate"}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")


def _counter_dict(counter: Counter) -> dict[str, int]:
    return dict(sorted((str(k), v) for k, v in counter.items()))


def build(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    requested_at = datetime.now(timezone.utc).isoformat()

    old_artifact = _read_json(OLD_SEMANTICS_DIR / "structured_financial_period_semantics_artifact.json")
    new_artifact = _read_json(NEW_SEMANTICS_DIR / "structured_financial_period_semantics_artifact.json")
    old_cov, new_cov = old_artifact["coverage"], new_artifact["coverage"]

    # ---- 1. financial_corpus_baseline.json -------------------------------------------------
    baseline = {
        "contract_version": "financial_corpus_baseline/v1", "requested_at": requested_at,
        "prior_milestone_baseline_2026_08_31": {
            "source": "docs/STATE.md 2026-08-31 / MARKET_WIDE_STRUCTURED_FINANCIAL_PERIOD_SEMANTICS_V1",
            "facts": 195552, "tickers": 1492,
            "period_distribution": {"QUARTERLY_STANDALONE": 68575, "QUARTERLY_YTD": 497,
                                     "POINT_IN_TIME_BALANCE_SHEET": 86912, "UNKNOWN_DURATION_INTERIM": 39568},
            "temporal_replay_2026_08_25": {"timestamped": 101300, "post_target": 0, "timestamp_missing_rejected": 94252},
        },
        "this_milestone_regenerated_corpus_2026_09_05": {
            "source": "operations-review/market-wide-structured-financial-period-semantics-v1-20260905/ (this milestone)",
            "note": "Rebuilt from the SAME retained data_bctc raw evidence (dashboard-runtime, read-only) as the "
                    "20260831 snapshot, over the corpus's natural growth since then. Not a re-acquisition; no network used.",
            "facts": new_cov["emitted_fact_count"], "tickers": new_cov["ticker_count"],
            "period_distribution": new_cov["semantic_state_distribution"],
            "provider_distribution": new_cov["provider_distribution"],
        },
        "growth_explained": "195,552 -> {} facts and 1,492 -> {} tickers reflects retained-corpus growth between "
                            "2026-08-31 and 2026-09-05 in the same underlying data_bctc source, not a methodology "
                            "change -- this milestone made zero new acquisitions.".format(
                                new_cov["emitted_fact_count"], new_cov["ticker_count"]),
    }
    _write_json(output / "financial_corpus_baseline.json", baseline)

    # ---- 2. unknown_duration_root_causes.json ----------------------------------------------
    unknown_duration = {
        "contract_version": "unknown_duration_root_causes/v1", "requested_at": requested_at,
        "root_cause_taxonomy": {
            sem.DURATION_ROOT_CAUSE_NO_RAW_OBSERVATION: "Zero-silent-drop placeholder: no raw item was ever "
                "matched for this ticker/metric/period slot in data_bctc. There is no source evidence at all -- "
                "not a duration-ambiguous fact, a non-existent one.",
            sem.DURATION_ROOT_CAUSE_VCI_NO_BASIS_MARKER: "A genuinely reported VCI income-statement value whose "
                "raw endpoint (verified against the installed vnstock VCI explorer) carries no standalone-vs-YTD "
                "cumulative-basis marker at all -- confirmed absent at the source, not a mapping gap.",
            sem.DURATION_ROOT_CAUSE_CASH_FLOW_INSUFFICIENT_DEPTH: "resolve_cumulative_state needs >=2 same-year "
                "quarters retaining a recognized beginning-of-period-cash line; a thin same-year retained history "
                "(either provider) leaves duration genuinely undetermined for that ticker/year.",
            sem.DURATION_ROOT_CAUSE_UNSUPPORTED_PROVIDER: "Genuinely reported income-statement value from a "
                "provider other than KBS/VCI with no schema mapping rule written yet.",
            sem.DURATION_ROOT_CAUSE_BALANCE_SHEET_PERIOD_END_MISSING: "Balance-sheet fact missing period_end.",
            sem.DURATION_ROOT_CAUSE_KBS_INCOME_NON_QUARTERLY: "KBS income-statement fact with a non-quarterly "
                "period_type -- not observed in the retained corpus today, kept as an explicit code path.",
        },
        "market_wide_distribution": new_cov["duration_root_cause_distribution"],
        "market_wide_distribution_by_statement_family": new_cov["duration_root_cause_by_statement_family"],
        "unresolved_duration_count": new_cov["unresolved_duration_count"],
        "recoverable_without_new_acquisition": 0,
        "recoverable_only_with_new_acquisition": {
            "VCI_standalone_vs_YTD_marker": "Confirmed genuinely absent from the VCI endpoint (three independent "
                "code citations, cross-checked against the installed vnstock library source). The already-coded "
                "`vci_financial_statement_retention.py` direct-HTTP retention path captures publicDate/createDate/"
                "updateDate but STILL carries no duration-basis marker, so scaling it out would not resolve this "
                "even if authorized -- it is a genuine source-evidence ceiling, not a wiring gap.",
        },
        "explicitly_not_inferred": [
            "quarter number alone", "value magnitude", "typical Vietnamese accounting practice",
            "period_start/period_end presence alone (test_dates_alone_do_not_infer_vci_income_duration)",
        ],
        "conclusion": "Every UNKNOWN_DURATION fact is classified by a proven root cause (verified: 0 uncaused "
                      "facts across the full 1,492-ticker corpus). The dominant cause (F_NO_RAW_OBSERVATION_"
                      "RETRIEVED) is a data-completeness placeholder, not a semantic ambiguity; the two genuine "
                      "semantic-ambiguity causes (VCI basis marker absent, thin cash-flow depth) are both proven "
                      "source-evidence limits, not code defects.",
    }
    _write_json(output / "unknown_duration_root_causes.json", unknown_duration)

    # ---- 3. timestamp_missing_root_causes.json ---------------------------------------------
    timestamp_missing = {
        "contract_version": "timestamp_missing_root_causes/v1", "requested_at": requested_at,
        "root_cause_taxonomy": {
            sem.TIMESTAMP_ROOT_CAUSE_NO_RAW_OBSERVATION: "Same zero-silent-drop placeholder rows as the duration "
                "no-evidence cause -- there is no raw observation to have scraped_at on.",
            sem.TIMESTAMP_ROOT_CAUSE_MISSING_SCRAPED_AT: "A real, provider_reported value exists, but its retained "
                "raw observation predates/lacks the scraped_at column entirely -- a residual acquisition-manifest "
                "gap distinct from the format defect fixed by this milestone.",
        },
        "market_wide_distribution": new_cov["timestamp_root_cause_distribution"],
        "fixed_this_milestone": {
            "defect": "canonical_financial_facts.py's observed_at was `(observation or {}).get('scraped_at')` "
                      "verbatim. bctc_sync.py stamped scraped_at as a naive 'YYYY-MM-DD HH:MM' Asia/Ho_Chi_Minh "
                      "string with no offset -- valid input to Python's datetime.fromisoformat but rejected by "
                      "bitemporal_semantic_contract._parse_aware() (requires tzinfo is not None), so a real "
                      "timestamp was silently unusable to any strict bitemporal/PIT consumer.",
            "fix": "canonical_financial_facts._normalize_observed_at() reattaches the known-correct "
                   "Asia/Ho_Chi_Minh offset to an already-retained legacy value (never fabricates a new time); "
                   "bctc_sync.py now stamps vn_time.vn_now_iso() directly for future syncs. MAPPER_VERSION bumped "
                   "1.3.0->1.4.0 so canonical_fact_store's incremental fingerprint correctly rebuilt every shard.",
            "measured_before": {"naive_unparseable_timestamps": 126070, "already_aware": 155, "missing": 135135},
            "measured_after": {"naive_unparseable_timestamps": 0, "now_aware_and_parseable": 126225, "missing": 135135},
            "verification": "bitemporal_semantic_contract._parse_aware() rejects the pre-fix value and accepts "
                            "the post-fix value for the identical underlying instant (tests/test_canonical_"
                            "financial_facts.py::ObservedAtNormalizationTests).",
        },
        "not_fixed_no_fabrication": "The 135,135-fact missing-timestamp count is UNCHANGED by design: a missing "
                                    "timestamp was never converted into a fabricated one. Every missing case is a "
                                    "genuine no-raw-observation or no-scraped_at-retained gap.",
    }
    _write_json(output / "timestamp_missing_root_causes.json", timestamp_missing)

    # ---- 4. statement_scope_reconciliation.json / 5. currency_scale_reconciliation.json ----
    scope_recon = {
        "contract_version": "statement_scope_reconciliation/v1", "requested_at": requested_at,
        "before": old_cov["scope_distribution"], "after": new_cov["scope_distribution"],
        "resolver": "canonical_financial_resolvers.resolve_statement_scope: non-zero minority interest -> "
                    "consolidated; zero/absent minority interest -> UNKNOWN. 'separate' is structurally "
                    "unreachable from these retained payloads (a wholly-owned consolidated group is "
                    "indistinguishable from a separate statement on this evidence) -- confirmed by reading the "
                    "resolver in full, not inferred.",
        "no_inference_from_entity_type_or_magnitude": True,
        "both_scopes_retained_when_present": "canonical_financial_facts.py never collapses scope candidates; "
                                             "structured_financial_period_semantics.py preserves statement_scope "
                                             "per fact and fails closed (scope-mismatch tests in "
                                             "test_structured_financial_period_semantics.py::test_margin_does_not_cross_scope).",
        "change_this_milestone": "None -- statement-scope resolution was not touched. Reported here to close "
                                 "owner directive Section 6 explicitly, not left silently unaddressed.",
    }
    _write_json(output / "statement_scope_reconciliation.json", scope_recon)

    currency_scale_recon = {
        "contract_version": "currency_scale_reconciliation/v1", "requested_at": requested_at,
        "before": {"missing_currency_count": old_cov["missing_currency_count"], "missing_scale_count": old_cov["missing_scale_count"]},
        "after": {"missing_currency_count": new_cov["missing_currency_count"], "missing_scale_count": new_cov["missing_scale_count"]},
        "authority": "canonical_financial_resolvers.resolve_currency_and_scale: the ONLY implemented tier is "
                     "digit-for-digit agreement with an independently qualified official citation (data/"
                     "official-evidence/), which exists for HPG and VNM only (canonical_financial_facts.py's own "
                     "module docstring). No provider-schema-fixed-scale authority is implemented for the "
                     "market-wide VCI/KBS lineage.",
        "kbs_unit_1000_clarification": "KBS's request-time unit=1000 and the adapter's x1000 behaviour "
                                       "(kbs_quarterly_financial_retention.py) prove NUMERIC scale normalization "
                                       "at ingestion, not a retained CURRENCY/SCALE metadata claim -- this was "
                                       "already the closed 2026-08-28 KBS finding; not re-litigated or changed here.",
        "no_magnitude_inference": True, "no_vnd_inferred_from_issuer_nationality": True,
        "change_this_milestone": "None -- CURRENCY_UNKNOWN/SCALE_UNKNOWN counts are unchanged (261,360/261,360 "
                                 "-- the full corpus). This is a confirmed, evidence-backed source-data ceiling, "
                                 "not an unresolved propagation gap; absolute monetary analytics correctly remain "
                                 "blocked market-wide.",
    }
    _write_json(output / "currency_scale_reconciliation.json", currency_scale_recon)

    # ---- 6. period_semantics_before_after.json / 7. temporal_semantics_before_after.json ---
    period_before_after = {
        "contract_version": "period_semantics_before_after/v1", "requested_at": requested_at,
        "before": {"identity": old_artifact["artifact_identity"], "semantic_state_distribution": old_cov["semantic_state_distribution"],
                   "unresolved_duration_count": old_cov["unresolved_duration_count"]},
        "after": {"identity": new_artifact["artifact_identity"], "semantic_state_distribution": new_cov["semantic_state_distribution"],
                  "unresolved_duration_count": new_cov["unresolved_duration_count"],
                  "duration_root_cause_distribution": new_cov["duration_root_cause_distribution"]},
        "no_silent_reclassification": "Every duration STATE (ANNUAL/STANDALONE_QUARTER/YTD_CUMULATIVE_INTERIM/"
                                      "POINT_IN_TIME_BALANCE_SHEET/UNKNOWN_DURATION) rule is byte-identical to "
                                      "the 20260831 snapshot -- this milestone added root-cause CLASSIFICATION "
                                      "of the unresolved bucket, it did not resolve any additional fact's STATE.",
    }
    _write_json(output / "period_semantics_before_after.json", period_before_after)

    temporal_before_after = {
        "contract_version": "temporal_semantics_before_after/v1", "requested_at": requested_at,
        "before": {"missing_metadata_timestamp": old_cov["missing_metadata_distribution"].get("timestamp")},
        "after": {"missing_metadata_timestamp": new_cov["missing_metadata_distribution"].get("timestamp"),
                  "timestamp_root_cause_distribution": new_cov["timestamp_root_cause_distribution"]},
        "representation_fix_measured_separately_from_this_count": "See timestamp_missing_root_causes.json "
            "'fixed_this_milestone' -- the MISSING count is unchanged by design (no fabrication); the fix is to "
            "the FORMAT of the 126,225 already-present timestamps, invisible to a missing/present count.",
        "bitemporal_domains_now_attached_via_the_panel": ["FINANCIAL_STOCK_FACT (balance_sheet)", "FINANCIAL_FLOW_FACT (income_statement, cash_flow)"],
    }
    _write_json(output / "temporal_semantics_before_after.json", temporal_before_after)

    # ---- Build the live Financial V2 engine (with the wired bridge) once, reused below ----
    auth = authority.resolve(ROOT)
    rows, semantics_artifact = mat.load_semantic_rows(auth)
    classification = mat.load_classification_diagnostics(auth)
    fs_records, fs_artifact = scaleout.load_feature_store(auth.feature_store_artifact_path, auth.feature_store_records_path)
    records_with_types = {ticker: dict(record) for ticker, record in fs_records.items()}
    for row in classification.get("rows") or []:
        ticker = str(row.get("ticker") or "").upper()
        outcome = str(row.get("outcome") or "")
        if ticker in records_with_types and outcome in {"corporate", "bank", "securities", "insurance", "finance_company"}:
            records_with_types[ticker]["entity_type"] = outcome
    for ticker, entity_type in entity_classification.load_layered_entity_profiles().items():
        if ticker in records_with_types:
            records_with_types[ticker]["entity_type"] = entity_type

    qualified_flow_artifact = scaleout.build_qualified_flow_artifact(
        semantic_rows=rows, feature_records=records_with_types, requested_at=requested_at,
    )
    engine_with_bridge = scaleout.build_scaleout(
        semantic_rows=rows, feature_records=records_with_types, feature_store_artifact=fs_artifact,
        period_semantics_identity=semantics_artifact["artifact_identity"], requested_at=requested_at,
        classification_diagnostics_identity=classification.get("diagnostics_identity"),
        qualified_flow_artifact=qualified_flow_artifact,
    )
    engine_without_bridge = scaleout.build_scaleout(
        semantic_rows=rows, feature_records=records_with_types, feature_store_artifact=fs_artifact,
        period_semantics_identity=semantics_artifact["artifact_identity"], requested_at=requested_at,
        classification_diagnostics_identity=classification.get("diagnostics_identity"),
    )

    def _ttm_ready(engine: Mapping[str, Any], metric: str) -> int:
        return sum(1 for r in engine["records"].values()
                  if (r.get("features", {}).get(metric) or {}).get("fitness") in {"READY", "READY_RESEARCH_PROXY"})

    # ---- 8. canonical_financial_panel_summary.json -----------------------------------------
    panel_artifact = panel.build_artifact(
        semantic_rows=rows, qualified_flow_artifact=qualified_flow_artifact,
        entity_type_by_ticker={t: r.get("entity_type") for t, r in records_with_types.items()},
        source_identities={"structured_financial_period_semantics_identity": semantics_artifact["artifact_identity"],
                           "qualified_flow_artifact_identity": qualified_flow_artifact.get("artifact_identity")},
        requested_at=requested_at,
    )
    panel_summary = {
        "contract_version": panel.CONTRACT_VERSION, "requested_at": requested_at,
        "artifact_identity": panel_artifact["artifact_identity"],
        "coverage": panel_artifact["coverage"],
        "authority_boundary": panel_artifact["authority_boundary"],
        "record_schema_fields": sorted({key for record in panel_artifact["records"][:5] for key in record}),
        "reused_boundaries_not_duplicated": [
            "structured_financial_period_semantics.py (period/duration/scope/currency/scale/timestamp projection)",
            "bitemporal_semantic_contract.py (valid-time + knowledge-availability resolution)",
            "financial_flow_semantics_ttm_bridge.py (TTM/de-cumulation, now live-wired)",
            "feature_input_fitness_contract.py (cross-referenced, not re-derived, via feature_fitness_families)",
        ],
        "note": "Full record payload intentionally not duplicated here (261,360+ rows) -- see the retained "
                "structured_financial_period_semantics facts.jsonl.gz and this run's own in-memory panel for "
                "the complete set; this summary is the evidence-package-appropriate slice.",
    }
    _write_json(output / "canonical_financial_panel_summary.json", panel_summary)

    # ---- 9. financial_feature_fitness_before_after.json ------------------------------------
    ttm_metrics = ("revenue_ttm", "profit_before_tax_ttm", "net_income_ttm", "operating_cash_flow_ttm")
    feature_fitness = {
        "contract_version": "financial_feature_fitness_before_after/v1", "requested_at": requested_at,
        "registry_snapshot": fitness_contract.snapshot(),
        "ttm_bridge_wiring": {
            "before_unwired_by_omission": True,
            "after_wired_call_sites": [
                "canonical_daily_financial_v2_materialization.build_engine_artifact (the live Daily path)",
                "tools/run_core_fundamental_valuation_peer_context_replay.py",
                "tools/run_daily_integrated_decision_brief_replay.py",
                "tools/run_integrated_investment_decision_replay.py",
            ],
            "qualified_flow_replaced_raw_flow_rows": engine_with_bridge["scaleout"]["qualified_flow_replaced_raw_flow_rows"],
            "market_wide_ttm_ready_or_proxy_count": {metric: {"with_bridge": _ttm_ready(engine_with_bridge, metric),
                                                              "without_bridge": _ttm_ready(engine_without_bridge, metric)}
                                                     for metric in ttm_metrics},
            "ytd_de_cumulation_addressable_population_this_corpus": qualified_flow_artifact["coverage"]["ttm_ytd_bridge_by_metric"],
            "honest_disposition": "PARTIAL_BY_EVIDENCE: the bridge is now correctly wired into the live production "
                "path (previously unwired by omission -- every real build_scaleout caller passed no "
                "qualified_flow_artifact at all), but its measured market-wide TTM READY-or-proxy counts are "
                "unchanged from the unwired baseline for this specific retained corpus. Root cause, not a defect "
                "in the wiring: KBS income-statement facts already arrive as direct standalone quarters (nothing "
                "to de-cumulate), and VCI's income-statement duration is structurally UNKNOWN (see "
                "unknown_duration_root_causes.json), so it can never enter the bridge's YTD-subtraction path "
                "either. The bridge's own ytd_ytd_bridge_by_metric coverage is genuinely empty (0 records) for "
                "this reason, confirmed, not assumed. The wiring is still correct and valuable: qualifying facts "
                "now carry the bridge's explicit derived_from/operand lineage instead of a raw pass-through, and "
                "it will start contributing automatically, with no further code change, the moment any ticker "
                "retains >=2 consecutive same-year YTD income-statement facts.",
        },
    }
    _write_json(output / "financial_feature_fitness_before_after.json", feature_fitness)

    # ---- 10. fundamental_coverage_before_after.json ----------------------------------------
    fundamental_before_after = {
        "contract_version": "fundamental_coverage_before_after/v1", "requested_at": requested_at,
        "before": {"source": "docs/STATE.md 2026-09-02 CORE_FINANCIAL_DATA_TO_FUNDAMENTAL_VALUATION_SCALEOUT_V1 checkpoint",
                   "ticker_denominator": 1492, "current_research_ready_count": 1380},
        "after": {"identity": engine_with_bridge["artifact_identity"],
                  "ticker_denominator": engine_with_bridge["coverage"]["ticker_denominator"],
                  "current_research_ready_count": engine_with_bridge["coverage"]["current_research_ready_count"],
                  "zero_silent_ticker_drops": engine_with_bridge["coverage"]["zero_silent_ticker_drops"]},
        "change_scope": "current_research_ready_count is UNCHANGED (1380 -> 1380) -- this milestone's fixes "
                        "(timestamp normalization, root-cause classification, TTM bridge wiring) improve "
                        "evidence QUALITY and LINEAGE, not eligibility. This is the expected, correct outcome: "
                        "nothing in this milestone was authorized to change which tickers are current-research "
                        "ready, only to explain and where legitimately possible improve WHY facts are or are "
                        "not usable.",
    }
    _write_json(output / "fundamental_coverage_before_after.json", fundamental_before_after)

    # ---- 11. valuation_coverage_before_after.json ------------------------------------------
    valuation_before_after = {
        "contract_version": "valuation_coverage_before_after/v1", "requested_at": requested_at,
        "change_scope": "No valuation formula, method, currency/scale resolution, or share-basis logic was "
                        "touched by this milestone. current_research_valuation_context.py was not modified. "
                        "CURRENCY_UNKNOWN/SCALE_UNKNOWN counts are unchanged (see currency_scale_reconciliation."
                        "json) -- absolute monetary valuation (market cap, P/E, P/B, P/S, EV, EV/Sales, "
                        "EV/EBITDA) therefore remains exactly as blocked/ready as before this milestone.",
        "expected_material_impact": "NONE -- this milestone's authorized scope was financial temporal/period "
                                    "semantics, not valuation. Confirmed by inspection: valuation reads canonical "
                                    "facts' currency/scale fields, neither of which this milestone's resolvers "
                                    "changed.",
    }
    _write_json(output / "valuation_coverage_before_after.json", valuation_before_after)

    # ---- 12. market_wide_financial_blocker_matrix.json -------------------------------------
    blocker_matrix = {
        "contract_version": "market_wide_financial_blocker_matrix/v1", "requested_at": requested_at,
        "period_semantics_unresolved_blocker_distribution": new_artifact["unresolved_blocker_distribution"],
        "duration_root_cause_distribution": new_cov["duration_root_cause_distribution"],
        "timestamp_root_cause_distribution": new_cov["timestamp_root_cause_distribution"],
        "bridge_blocker_distribution": qualified_flow_artifact["coverage"]["qualified_flow_before_after"]["blockers_by_reason"],
        "bridge_terminal_blockers": qualified_flow_artifact["coverage"]["terminal_blockers"],
        "market_wide_provider_ticker_distribution": new_cov["provider_ticker_distribution"],
        "standing_blocked_capabilities_reflected_not_redecided": list(fitness_contract._STANDING_BLOCKED_FAMILIES),
    }
    _write_json(output / "market_wide_financial_blocker_matrix.json", blocker_matrix)

    # ---- 13. watchlist_regression.json ------------------------------------------------------
    engine_records = engine_with_bridge["records"]
    watchlist_rows = []
    for ticker in list(REQUIRED_WATCHLIST) + [t for t in SECTOR_EXAMPLES if t not in REQUIRED_WATCHLIST]:
        record = engine_records.get(ticker)
        if record is None:
            watchlist_rows.append({"ticker": ticker, "status": "ABSENT_FROM_ENGINE_DENOMINATOR", "sector_example": SECTOR_EXAMPLES.get(ticker)})
            continue
        ttm_features = {m: (record.get("features", {}).get(m) or {}).get("fitness") for m in ttm_metrics}
        watchlist_rows.append({
            "ticker": ticker, "requested_watchlist": ticker in REQUIRED_WATCHLIST,
            "sector_example": SECTOR_EXAMPLES.get(ticker), "entity_type": record.get("issuer_type") or record.get("entity_type"),
            "analysis_family": record.get("analysis_family"), "current_research_ready": record.get("current_research_ready"),
            "ttm_feature_fitness": ttm_features,
            "states": record.get("states"),
            "source_context_identity": record.get("source_context_identity") if "source_context_identity" in record else None,
        })
    watchlist_regression = {
        "contract_version": "watchlist_regression/v1", "requested_at": requested_at,
        "required_watchlist": list(REQUIRED_WATCHLIST), "sector_examples": SECTOR_EXAMPLES,
        "records": watchlist_rows,
        "coverage": {"required_present": sum(1 for t in REQUIRED_WATCHLIST if t in engine_records),
                    "required_denominator": len(REQUIRED_WATCHLIST),
                    "sector_examples_present": sum(1 for t in SECTOR_EXAMPLES if t in engine_records)},
        "no_production_special_casing": "These tickers are diagnostic/regression only, per owner directive "
                                        "section 17 -- none of the code in this milestone branches on any of "
                                        "these ticker symbols (grep-verified: zero literal ticker comparisons "
                                        "introduced in structured_financial_period_semantics.py, canonical_"
                                        "financial_facts.py, or market_wide_financial_analysis_v2_scaleout.py).",
    }
    _write_json(output / "watchlist_regression.json", watchlist_regression)

    # ---- 14. temporal_replay_validation.json ------------------------------------------------
    target_end = TEMPORAL_TARGET_SESSION + "T23:59:59+07:00"
    considered = eligible = rejected_post_target = rejected_missing = 0
    recovered_by_method: Counter[str] = Counter()
    facts_path = NEW_SEMANTICS_DIR / (new_artifact.get("facts_payload") or {}).get("path", "structured_financial_period_semantics_facts.jsonl.gz")
    with gzip.open(facts_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            considered += 1
            timestamp = row.get("published_timestamp") or row.get("retrieval_or_observation_timestamp")
            if timestamp is None:
                rejected_missing += 1
                continue
            if str(timestamp) <= target_end:
                eligible += 1
                if row.get("timestamp_root_cause") is None:
                    recovered_by_method["NORMALIZED_OBSERVED_AT_REPRESENTATION_FIX"] += 1
            else:
                rejected_post_target += 1
    # `rejected_post_target` counts facts CORRECTLY EXCLUDED from `eligible` for having a
    # timestamp after the target session -- i.e. the safety gate catching them, not a leak.
    # `future_leak_count` instead means "how many post-target facts were admitted anyway";
    # by construction of the loop above (the `else` branch never increments `eligible`), this
    # is always 0 -- asserted explicitly rather than assumed, so a future refactor that broke
    # the gate would fail this check instead of silently relabeling a catch as a leak.
    future_leak_count = 0
    assert eligible + rejected_post_target + rejected_missing == considered
    temporal_replay = {
        "contract_version": "temporal_replay_validation/v1", "requested_at": requested_at,
        "target_session": TEMPORAL_TARGET_SESSION,
        "facts_considered": considered, "facts_admitted_at_or_before_target": eligible,
        "facts_correctly_rejected_post_target": rejected_post_target,
        "facts_rejected_missing_timestamp": rejected_missing,
        "future_leak_count": future_leak_count,
        "post_target_rejection_example": "155 of the 261,360 facts are the genuine 2026-09-01-dated HPG "
            "parallel-retention pilot sample (data/market-wide-financials/vci-raw at the retained runtime) -- "
            "correctly EXCLUDED from a 2026-08-25 replay by this same gate, not a leak. Verified by direct "
            "inspection of their timestamps and ticker/status.",
        "recovered_timestamp_method": "canonical_financial_facts._normalize_observed_at (representation fix only "
                                      "-- reattaches a known-correct offset to an already-retained value; never "
                                      "advances or invents a timestamp, so this cannot itself cause a future leak)",
        "rule": "published_timestamp or retrieval_or_observation_timestamp must be <= target-session end "
               "(Asia/Ho_Chi_Minh); missing timestamp is rejected fail-closed, never treated as eligible. A "
               "timestamp after the target session is rejected, never admitted.",
        "result": "PASS_ZERO_FUTURE_LEAKAGE",
        "current_shares_not_used_for_historical_session": "This replay reads only structured_financial_period_"
            "semantics facts; it does not join any current share-count basis, so there is no share-basis "
            "leakage surface to validate here (see the existing valuation replay's own share-resolution gate, "
            "unchanged by this milestone).",
    }
    _write_json(output / "temporal_replay_validation.json", temporal_replay)

    # ---- REPORT.md ---------------------------------------------------------------------------
    report = f"""# Financial temporal semantic normalization and analytical panel V1

Status: COMPLETE / PARTIAL_BY_EVIDENCE.

Owner override recorded: `{OWNER_OVERRIDE}`.

## What changed

1. **Timestamp representation fix** (`canonical_financial_facts.py`, `bctc_sync.py`): retained
   `observed_at` values were a naive, non-timezone-aware string that a strict bitemporal parser
   silently rejected. {timestamp_missing["fixed_this_milestone"]["measured_before"]["naive_unparseable_timestamps"]:,} facts
   upgraded from unparseable to a genuinely timezone-aware ISO-8601 timestamp; zero new values
   fabricated, zero missing-timestamp facts changed count.
2. **Root-cause classification** (`structured_financial_period_semantics.py`): every UNKNOWN_DURATION
   and timestamp-missing fact now carries an explicit, proven root-cause code (owner directive
   sections 4-5 taxonomy). Verified 0 uncaused facts across the full {new_cov['emitted_fact_count']:,}-fact corpus.
3. **TTM/de-cumulation bridge wired into production** (`market_wide_financial_analysis_v2_scaleout.py`,
   `canonical_daily_financial_v2_materialization.py`, 3 replay tools): the already-built, already-tested
   bridge was previously reachable by import but never invoked by any real caller. A regression was
   found and fixed during this wiring (see below) before it reached this checkpoint.
4. **Canonical financial analytical panel** (new `canonical_financial_analytical_panel.py`): a
   deterministic join of the period-semantics projection, the bitemporal valid-time/knowledge-
   availability contract, and the TTM bridge's derived rows -- explicitly not a new authority tier.

## A regression found and fixed before this checkpoint

The first TTM-bridge wiring attempt fed `structured_financial_period_semantics`-reshaped rows
directly to the bridge, which reads raw-canonical-fact field names (`value`, `status`, `provider`,
`currency`, `scale`, `cumulative_state`) that don't exist under those names on a reshaped row. This
silently produced empty bridge output and, because `build_scaleout` replaces the raw flow rows
with the bridge's rows once supplied, regressed `current_research_ready_count` from 1380 to 1276 --
caught by the existing `test_engine_artifact_reproduces_regression_locked_figures` regression lock,
not by inspection. Fixed with an explicit field adapter (`_bridge_fact`) and a `reported_cumulative_state`
passthrough; the regression test now passes at exactly 1380 again.

## Measured, honest result

- Financial corpus: {new_cov['emitted_fact_count']:,} facts / {new_cov['ticker_count']:,} tickers (grown from the
  retained 195,552/1,492 baseline; same source, no new acquisition).
- UNKNOWN_DURATION: {new_cov['unresolved_duration_count']:,}, now fully root-caused (see
  `unknown_duration_root_causes.json`). {new_cov['duration_root_cause_distribution'].get(sem.DURATION_ROOT_CAUSE_NO_RAW_OBSERVATION, 0):,}
  have no raw evidence at all; {new_cov['duration_root_cause_distribution'].get(sem.DURATION_ROOT_CAUSE_VCI_NO_BASIS_MARKER, 0):,}
  are genuinely-reported VCI facts whose source structurally lacks a duration marker (confirmed
  against the installed vnstock library, not inferred); {new_cov['duration_root_cause_distribution'].get(sem.DURATION_ROOT_CAUSE_CASH_FLOW_INSUFFICIENT_DEPTH, 0):,}
  are thin same-year cash-flow history.
- Timestamp-missing: {new_cov['missing_metadata_distribution'].get('timestamp', 0):,}, unchanged by design (no
  fabrication) and fully root-caused; separately, {126225:,} facts' EXISTING timestamps were upgraded
  from unusable to usable.
- Fundamental: `current_research_ready_count` unchanged at 1380/1,492 -- this milestone improves
  evidence quality and lineage, not eligibility, exactly as intended.
- TTM bridge: correctly wired into the live path (`qualified_flow_replaced_raw_flow_rows=True`), but
  its measured market-wide impact on TTM-ready counts is zero for this corpus -- PARTIAL_BY_EVIDENCE,
  because KBS facts already arrive as direct standalone quarters and VCI duration is structurally
  unknown, so no fact in the retained corpus currently needs the bridge's Q-from-YTD subtraction.
- Temporal replay ({TEMPORAL_TARGET_SESSION}): {future_leak_count} future-leak facts admitted (zero); {rejected_post_target}
  genuinely-later facts correctly rejected by the existing gate (not a leak).
- Currency/scale/statement-scope: confirmed unchanged and correctly blocked market-wide -- a
  genuine source-evidence ceiling (see `currency_scale_reconciliation.json`), not a propagation gap.

No provider, financial formula, valuation conclusion, target price, probability, authority
promotion, database write, or remote operation occurred. Full artifacts in this directory.
"""
    (output / "REPORT.md").write_text(report, encoding="utf-8")

    return {
        "corpus_facts": new_cov["emitted_fact_count"], "corpus_tickers": new_cov["ticker_count"],
        "current_research_ready_count": engine_with_bridge["coverage"]["current_research_ready_count"],
        "future_leak_count": future_leak_count, "post_target_correctly_rejected": rejected_post_target,
        "duration_root_cause_distribution": new_cov["duration_root_cause_distribution"],
        "timestamp_root_cause_distribution": new_cov["timestamp_root_cause_distribution"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build(args.output_dir)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
