"""Retained-evidence closeout for CORE_FINANCIAL_DATA_TO_FUNDAMENTAL_VALUATION_SCALEOUT_V1.

This is deliberately a reporting/replay tool, not another financial engine.  It reads the
already-governed semantic fact store, Financial V2 compact projection, current-valuation
context, and integrated decision product; it only materializes the owner-requested local
operations-review evidence.  No network, provider, database, or remote Git operation is used.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


PRIMARY_SESSION = "2026-09-04"
EARLIER_SESSION = "2026-08-25"
OWNER_OVERRIDE = "OWNER_AUTHORIZATION_2026_09_05_QUEUED_NEXT_EMPTY_CORE_FINANCIAL_DATA_TO_FUNDAMENTAL_VALUATION_SCALEOUT_V1"
MILESTONE = "CORE_FINANCIAL_DATA_TO_FUNDAMENTAL_VALUATION_SCALEOUT_V1"
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import feature_input_fitness_contract as fitness_contract
import owner_research_focus

DEFAULT_OUTPUT = ROOT / "operations-review" / "core-financial-data-to-fundamental-valuation-scaleout-v1-20260905"
PRIMARY_DIR = ROOT / "operations-review" / "core-daily-decision-coherence-and-valuation-integration-v1-20260905"
SEMANTIC_DIR = ROOT / "operations-review" / "market-wide-structured-financial-period-semantics-v1-20260831"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def _semantic_class(fact: Mapping[str, Any]) -> str:
    state = fact.get("period_semantic_state")
    if state == "ANNUAL":
        return "ANNUAL"
    if state == "STANDALONE_QUARTER":
        return "QUARTERLY_STANDALONE"
    if state == "YTD_CUMULATIVE_INTERIM":
        return "QUARTERLY_YTD"
    if state == "POINT_IN_TIME_BALANCE_SHEET":
        return "POINT_IN_TIME_BALANCE_SHEET"
    if state == "UNKNOWN_DURATION":
        return "INTERIM_UNKNOWN_DURATION" if fact.get("native_period_type") in {"quarterly", "interim"} else "UNKNOWN_PERIOD_SEMANTICS"
    return "UNKNOWN_PERIOD_SEMANTICS"


def _inventory_rows(facts_path: Path) -> tuple[list[dict[str, Any]], Counter[str], Counter[str], Counter[str], Counter[str]]:
    """Return metadata-only fact inventory; reported values remain in the retained source file."""
    rows: list[dict[str, Any]] = []
    classes: Counter[str] = Counter()
    metrics: Counter[str] = Counter()
    providers: Counter[str] = Counter()
    timestamp_state: Counter[str] = Counter()
    with gzip.open(facts_path, "rt", encoding="utf-8") as stream:
        for line in stream:
            fact = json.loads(line)
            lineage = fact.get("source_lineage") or {}
            observation_at = fact.get("retrieval_or_observation_timestamp")
            published_at = fact.get("published_timestamp")
            semantic_class = _semantic_class(fact)
            classes[semantic_class] += 1
            metrics[str(fact.get("canonical_metric"))] += 1
            provider = lineage.get("provider") or "UNKNOWN_PROVIDER"
            providers[str(provider)] += 1
            timestamp_state["TIMESTAMP_RETAINED" if (published_at or observation_at) else "TIMESTAMP_MISSING"] += 1
            # This inventory has one row per retained semantic fact, but never repeats reported
            # values or raw labels.  Source facts stay at their immutable gzip path below.
            rows.append({
                "ticker": fact.get("ticker"),
                "metric": fact.get("canonical_metric"),
                "statement_family": fact.get("statement_family"),
                "period": fact.get("native_period_label"),
                "period_type": fact.get("native_period_type"),
                "period_start": fact.get("period_start"),
                "period_end": fact.get("period_end"),
                "period_semantics": semantic_class,
                "retained_period_semantic_state": fact.get("period_semantic_state"),
                "scope": fact.get("statement_scope"),
                "source_provider": lineage.get("provider"),
                "source_status": fact.get("source_status"),
                "authority_state": fact.get("authority_state"),
                "research_semantic_state": fact.get("research_semantic_state"),
                "currency": fact.get("reported_currency"),
                "scale": fact.get("reported_scale"),
                "published_at": published_at,
                "observed_at": observation_at,
                "restatement_or_conflict": bool(fact.get("source_conflicts")),
                "staleness_state": "UNKNOWN_NO_PUBLICATION_OR_OBSERVATION_TIME" if not (published_at or observation_at) else "TIMESTAMP_RETAINED_NO_STALENESS_PROMOTION",
                "lineage": {
                    "fact_id": lineage.get("fact_id"),
                    "source_file": lineage.get("source_file"),
                    "source_sha256": lineage.get("source_sha256"),
                    "raw_item_id": lineage.get("raw_item_id"),
                    "source_observation_ids": lineage.get("source_observation_ids") or [],
                    "lineage_complete": fact.get("lineage_complete") is True,
                },
            })
    return rows, classes, metrics, providers, timestamp_state


def _feature_fitness_matrix(product: Mapping[str, Any], valuation: Mapping[str, Any], integrated: Mapping[str, Any], current_market_valuation: Mapping[str, Any]) -> dict[str, Any]:
    compact = product["financial_analysis_product"]
    records = compact.get("records") or {}
    available = {ticker: row for ticker, row in records.items() if row.get("status") == "AVAILABLE"}
    groups = {
        "FINANCIAL_REVENUE_GROWTH": ("revenue_qoq", "revenue_same_quarter_yoy", "revenue_ytd_yoy", "revenue_ttm_yoy"),
        "FINANCIAL_EARNINGS_GROWTH": ("net_income_qoq", "net_income_same_quarter_yoy", "net_income_ytd_yoy", "net_income_ttm_yoy", "profit_before_tax_qoq", "profit_before_tax_same_quarter_yoy", "profit_before_tax_ttm_yoy"),
        "FINANCIAL_MARGIN": ("gross_margin", "gross_margin_direction", "pbt_margin", "net_margin", "net_margin_direction", "ttm_net_margin"),
        "FINANCIAL_ROE_ROA": ("same_provider_roe_avg_equity", "same_provider_roa_avg_assets", "same_provider_roe_eop_proxy", "same_provider_roa_eop_proxy", "mixed_provider_roa_proxy"),
        "FINANCIAL_LEVERAGE_LIQUIDITY": ("debt_to_equity", "debt_to_assets", "current_ratio", "net_working_capital"),
        "FINANCIAL_CASH_FLOW_QUALITY": ("operating_cash_flow_qoq", "operating_cash_flow_same_quarter_yoy", "operating_cash_flow_ttm", "cfo_to_net_income", "cfo_to_net_income_ttm"),
        "FINANCIAL_FREE_CASH_FLOW_PROXY": ("free_cash_flow_proxy", "free_cash_flow_proxy_direction"),
    }
    matrix: dict[str, Any] = {}
    for family, feature_ids in groups.items():
        status_counts: Counter[str] = Counter()
        ticker_any_usable = 0
        for row in available.values():
            source = row.get("feature_fitness") or {}
            statuses = [str((source.get(feature_id) or {}).get("fitness") or "MISSING_FEATURE") for feature_id in feature_ids]
            status_counts.update(statuses)
            if any(status in {"READY", "RESEARCH_PROXY"} for status in statuses):
                ticker_any_usable += 1
        matrix[family] = {
            "authoritative_registry": fitness_contract.describe(family),
            "engine_feature_ids": list(feature_ids),
            "financial_product_available_denominator": len(available),
            "ticker_any_ready_or_proxy": ticker_any_usable,
            "pass_through_fitness_distribution": _counter_dict(status_counts),
        }

    valuation_records = valuation.get("records") or {}
    valuation_groups = {
        "MARKET_CAP": ("market_cap",), "P_E": ("P/E", "P/E_TTM"), "P_B": ("P/B",),
        "P_S": ("P/S", "P/S_TTM"), "ENTERPRISE_VALUE": ("enterprise_value",),
        "EV_SALES": ("EV/Sales",), "EV_EBITDA": ("EV/EBITDA",),
    }
    for family, method_ids in valuation_groups.items():
        counts: dict[str, Counter[str]] = {method_id: Counter() for method_id in method_ids}
        for row in valuation_records.values():
            methods = row.get("methods") or {}
            readiness = ((row.get("calculation_readiness_context") or {}).get("calculation_readiness") or {})
            if not isinstance(readiness, Mapping):
                readiness = {}
            for method_id in method_ids:
                method = methods.get(method_id)
                if method is not None:
                    counts[method_id][str(method.get("status") or "MISSING_STATUS")] += 1
                elif method_id == "enterprise_value":
                    state = ((readiness.get("enterprise_value") or {}).get("state") or "MISSING_STATUS")
                    counts[method_id][str(state)] += 1
                else:
                    counts[method_id]["MISSING_METHOD"] += 1
        matrix[family] = {
            "authoritative_registry": fitness_contract.describe(family),
            "method_ids": list(method_ids),
            "valuation_context_denominator": len(valuation_records),
            "pass_through_method_status_distribution": {key: _counter_dict(value) for key, value in counts.items()},
            "retained_market_wide_coverage": _market_wide_method_coverage(current_market_valuation, method_ids),
        }

    peer_counts: Counter[str] = Counter()
    history_counts: Counter[str] = Counter()
    pit_counts: Counter[str] = Counter()
    for row in valuation_records.values():
        for peer in (row.get("peer_relative") or {}).values():
            peer_counts[str(peer.get("status") or "MISSING_STATUS")] += 1
    for row in available.values():
        for history in (row.get("history_context") or {}).values():
            history_counts[str(history.get("status") or "MISSING_STATUS")] += 1
        pit_counts["BLOCKED" if row.get("pit_authority") is False else "UNEXPECTED_NON_BLOCKED"] += 1
    matrix["FUNDAMENTAL_PEER_RELATIVE"] = {"authoritative_registry": fitness_contract.describe("FUNDAMENTAL_PEER_RELATIVE"), "pass_through_status_distribution": _counter_dict(peer_counts)}
    matrix["FUNDAMENTAL_OWN_HISTORY"] = {"authoritative_registry": fitness_contract.describe("FUNDAMENTAL_OWN_HISTORY"), "pass_through_status_distribution": _counter_dict(history_counts)}
    matrix["FINANCIAL_POINT_IN_TIME_BACKTEST"] = {"authoritative_registry": fitness_contract.describe("FINANCIAL_POINT_IN_TIME_BACKTEST"), "pass_through_status_distribution": _counter_dict(pit_counts)}
    per_ticker: dict[str, Any] = {}
    for ticker, row in sorted(records.items()):
        source = row.get("feature_fitness") or {}
        feature_families = {
            family: {
                feature_id: dict(source.get(feature_id) or {"fitness": "MISSING_FEATURE", "reason_codes": ["FEATURE_NOT_EMITTED"]})
                for feature_id in feature_ids
            }
            for family, feature_ids in groups.items()
        } if row.get("status") == "AVAILABLE" else {}
        valuation_row = valuation_records.get(ticker) or {}
        per_ticker[ticker] = {
            "financial_product_status": row.get("status"),
            "financial_source_context_identity": row.get("source_context_identity"),
            "feature_fitness": feature_families,
            "valuation_method_fitness": {
                method_id: {"status": method.get("status"), "applicability": method.get("applicability"), "blocker_reason_codes": list(method.get("blocker_reason_codes") or [])}
                for method_id, method in (valuation_row.get("methods") or {}).items() if isinstance(method, Mapping)
            },
            "peer_history_status": {
                "peer_relative": {method_id: peer.get("status") for method_id, peer in (valuation_row.get("peer_relative") or {}).items() if isinstance(peer, Mapping)},
                "own_history": {feature_id: history.get("status") for feature_id, history in (row.get("history_context") or {}).items() if isinstance(history, Mapping)},
            },
            "pit_backtest": "BLOCKED",
        }
    matrix["product_integration"] = {
        "financial_product_coverage": compact.get("coverage"),
        "integrated_fundamental_context_available": (integrated.get("coverage") or {}).get("fundamental_context_available"),
        "authority_effect": "NONE",
    }
    return {"contract_version": "financial_feature_fitness_matrix/v1", "primary_session": PRIMARY_SESSION, "families": matrix, "per_ticker": per_ticker, "authority_effect": "NONE"}


def _market_wide_method_coverage(artifact: Mapping[str, Any], method_ids: tuple[str, ...]) -> dict[str, dict[str, int]]:
    """Read the existing raw valuation artifact's aggregate method coverage verbatim."""
    coverage = artifact.get("coverage") or {}
    aliases = {"market_cap": "market_cap", "enterprise_value": "enterprise_value"}
    result: dict[str, dict[str, int]] = {}
    for method_id in method_ids:
        metric = aliases.get(method_id, method_id)
        result[method_id] = {
            "ready": int((coverage.get("metric_ready_counts") or {}).get(metric, 0)),
            "research_usable": int((coverage.get("metric_research_usable_counts") or {}).get(metric, 0)),
            "blocked": int((coverage.get("metric_blocked_counts") or {}).get(metric, 0)),
            "not_applicable": int((coverage.get("metric_not_applicable_counts") or {}).get(metric, 0)),
        }
    return result


def _method_status_counts(valuation: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in (valuation.get("records") or {}).values():
        for method_id, method in (row.get("methods") or {}).items():
            counts[str(method_id)][str(method.get("status") or "MISSING_STATUS")] += 1
    return {method: _counter_dict(statuses) for method, statuses in sorted(counts.items())}


def _research_safe_methods(methods: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Mirror the local-AI brief boundary: status and ratio context, never targets/probability."""
    return {
        str(method_id): {key: value for key, value in method.items() if key not in {"fair_value", "target_price", "probability"}}
        for method_id, method in methods.items() if isinstance(method, Mapping)
    }


def _fact_summary_by_ticker(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Metadata-only financial-evidence summary for replay presentation; no values are copied."""
    summary: dict[str, dict[str, Any]] = {}
    latest: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        ticker = str(row.get("ticker"))
        item = summary.setdefault(ticker, {
            "period_semantics_distribution": Counter(), "statement_scope_distribution": Counter(),
            "source_provider_distribution": Counter(), "authority_state_distribution": Counter(),
        })
        item["period_semantics_distribution"][str(row.get("period_semantics"))] += 1
        item["statement_scope_distribution"][str(row.get("scope"))] += 1
        item["source_provider_distribution"][str(row.get("source_provider") or "UNKNOWN_PROVIDER")] += 1
        item["authority_state_distribution"][str(row.get("authority_state"))] += 1
        metric = str(row.get("metric"))
        previous = latest[ticker].get(metric)
        if previous is None or str(row.get("period_end") or "") > str(previous.get("period_end") or ""):
            latest[ticker][metric] = row
    result: dict[str, dict[str, Any]] = {}
    for ticker, item in summary.items():
        result[ticker] = {
            "period_semantics_distribution": _counter_dict(item["period_semantics_distribution"]),
            "statement_scope_distribution": _counter_dict(item["statement_scope_distribution"]),
            "source_provider_distribution": _counter_dict(item["source_provider_distribution"]),
            "authority_state_distribution": _counter_dict(item["authority_state_distribution"]),
            "latest_metric_metadata": {
                metric: {
                    "period": row.get("period"), "period_end": row.get("period_end"),
                    "period_semantics": row.get("period_semantics"), "scope": row.get("scope"),
                    "source_provider": row.get("source_provider"), "authority_state": row.get("authority_state"),
                    "currency": row.get("currency"), "scale": row.get("scale"),
                    "published_at": row.get("published_at"), "observed_at": row.get("observed_at"),
                    "lineage_fact_id": (row.get("lineage") or {}).get("fact_id"),
                }
                for metric, row in sorted(latest[ticker].items())
            },
        }
    return result


def _watchlist_replay(product: Mapping[str, Any], valuation: Mapping[str, Any], integrated: Mapping[str, Any], fact_summary: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    compact_records = product["financial_analysis_product"].get("records") or {}
    valuation_records = valuation.get("records") or {}
    integrated_records = integrated.get("records") or {}
    requested = list(owner_research_focus.broader_watchlist())
    examples = ["VCB", "SSI", "HPG", "VNM", "NVL"]
    tickers = list(dict.fromkeys(requested + examples))
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        financial = compact_records.get(ticker)
        valuation_row = valuation_records.get(ticker) or {}
        integrated_row = integrated_records.get(ticker) or {}
        methods = _research_safe_methods(valuation_row.get("methods") or {})
        rows.append({
            "ticker": ticker,
            "requested_watchlist": ticker in requested,
            "sector_example": ({"VCB": "bank", "SSI": "securities", "HPG": "industrial", "VNM": "consumer", "NVL": "real_estate"}.get(ticker)),
            "financial_analysis": financial if isinstance(financial, Mapping) else {"status": "UNAVAILABLE", "reason_codes": ["FINANCIAL_PRODUCT_TICKER_MISSING"]},
            "financial_evidence_metadata": fact_summary.get(ticker, {"status": "FINANCIAL_FACTS_UNAVAILABLE"}),
            "fundamental_state": integrated_row.get("fundamental_state"),
            "valuation_methods": methods,
            "valuation_method_status": {method_id: method.get("status") for method_id, method in methods.items()},
            "valuation_peer_relative": valuation_row.get("peer_relative") or {},
            "valuation_method_reconciliation": integrated_row.get("valuation_method_reconciliation") or {},
            "material_uncertainties": integrated_row.get("material_uncertainties") or [],
            "lineage": {
                "financial": (financial or {}).get("lineage_ref") if isinstance(financial, Mapping) else None,
                "valuation": valuation.get("artifact_identity"),
                "integrated": integrated.get("artifact_identity"),
            },
        })
    return {
        "contract_version": "watchlist_financial_replay/v1", "primary_session": PRIMARY_SESSION,
        "watchlist_tickers": requested, "required_sector_examples": examples, "records": rows,
        "coverage": {"requested_watchlist_count": len(requested), "records_emitted": len(rows), "financial_available": sum(r["financial_analysis"].get("status") == "AVAILABLE" for r in rows)},
        "authority_boundary": {"no_target_price": True, "no_probability": True, "no_universal_score": True, "no_authority_promotion": True},
    }


def _temporal_replay(facts: Iterable[Mapping[str, Any]], early_valuation: Mapping[str, Any]) -> dict[str, Any]:
    target_end = EARLIER_SESSION + "T23:59:59"
    timestamped = 0
    eligible = 0
    post_target = 0
    missing_timestamp = 0
    for fact in facts:
        timestamp = fact.get("published_at") or fact.get("observed_at")
        if timestamp is None:
            missing_timestamp += 1
        else:
            timestamped += 1
            if str(timestamp) <= target_end:
                eligible += 1
            else:
                post_target += 1
    source_artifacts = early_valuation.get("source_artifacts") or {}
    share_resolution = source_artifacts.get("share_resolution") or {}
    return {
        "contract_version": "temporal_replay_validation/v1",
        "target_session": EARLIER_SESSION,
        "primary_reference_session": PRIMARY_SESSION,
        "financial_fact_timestamp_gate": {
            "timestamped_fact_count": timestamped,
            "eligible_at_or_before_target": eligible,
            "post_target_rejected": post_target,
            "missing_timestamp_rejected_fail_closed": missing_timestamp,
            "look_ahead_violation_count": post_target,
            "rule": "published_timestamp or retrieval_or_observation_timestamp must be <= target-session close; missing time is not claimed PIT-eligible",
        },
        "historical_share_basis_gate": {
            "valuation_artifact_identity": early_valuation.get("artifact_identity"),
            "share_resolution_session_date": share_resolution.get("session_date"),
            "uses_target_session_resolution": share_resolution.get("session_date") == EARLIER_SESSION,
            "current_share_basis_reused_for_historical_session": False,
            "rule": "the 2026-08-25 retained valuation artifact's own share-resolution session is used; 2026-09-04 share data is not joined backward",
        },
        "result": "PASS_NO_RETAINED_POST_TARGET_FINANCIAL_FACT_USED" if post_target == 0 and share_resolution.get("session_date") == EARLIER_SESSION else "BLOCKED_BY_EVIDENCE",
        "authority_boundary": {"point_in_time_financial_authority_promoted": False, "historical_valuation_conclusion_emitted": False},
    }


def build(output: Path) -> dict[str, Any]:
    semantics = _read(SEMANTIC_DIR / "structured_financial_period_semantics_artifact.json")
    product = _read(PRIMARY_DIR / "primary_20260904_financial_analysis_product_artifact.json")
    valuation = _read(PRIMARY_DIR / "primary_20260904_current_research_valuation_context_artifact.json")
    integrated = _read(PRIMARY_DIR / "primary_20260904_integrated_investment_decision_product_artifact.json")
    earlier_valuation = _read(ROOT / "operations-review" / "market-wide-current-valuation-v1-20260825-session20260825" / "market_wide_current_valuation_artifact.json")
    current_market_valuation = _read(ROOT / "operations-review" / "market-wide-current-valuation-v1-20260904-session20260904" / "market_wide_current_valuation_artifact.json")
    facts_path = SEMANTIC_DIR / str((semantics.get("facts_payload") or {}).get("path"))
    rows, classes, metrics, providers, timestamp_state = _inventory_rows(facts_path)
    output.mkdir(parents=True, exist_ok=True)
    requested_at = datetime.now(timezone.utc).isoformat()

    inventory = {
        "contract_version": "financial_data_inventory/v1", "requested_at": requested_at,
        "source_semantics_identity": semantics.get("artifact_identity"),
        "source_facts_path": str(facts_path.relative_to(ROOT)).replace("\\", "/"),
        "source_facts_sha256": (semantics.get("facts_payload") or {}).get("canonical_jsonl_sha256"),
        "reported_values_repeated": False, "record_count": len(rows), "records": rows,
        "coverage": {"period_semantics": _counter_dict(classes), "canonical_metric": _counter_dict(metrics), "source_provider": _counter_dict(providers), "timestamp_state": _counter_dict(timestamp_state)},
        "authority_boundary": {"authority_effect": "NONE", "source_facts_remain_retained_authority": True},
    }
    period_matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        period_matrix[str(row["metric"])][str(row["period_semantics"])] += 1
    matrix = {
        "contract_version": "period_semantics_matrix/v1", "source_semantics_identity": semantics.get("artifact_identity"),
        "required_classes": ["ANNUAL", "QUARTERLY_STANDALONE", "QUARTERLY_YTD", "INTERIM_UNKNOWN_DURATION", "POINT_IN_TIME_BALANCE_SHEET", "UNKNOWN_PERIOD_SEMANTICS"],
        "class_distribution": _counter_dict(classes),
        "by_metric": {metric: _counter_dict(counts) for metric, counts in sorted(period_matrix.items())},
        "semantic_rules": semantics.get("semantic_rules"),
        "authority_boundary": {"no_ttm_created_when_unsafe": True, "no_annual_inference_from_quarter_label": True},
    }
    feature_matrix = _feature_fitness_matrix(product, valuation, integrated, current_market_valuation)
    method_counts = _method_status_counts(valuation)
    existing_daily_brief = _read(next((ROOT / "operations-review" / "daily-research-session-operations-v1" / PRIMARY_SESSION).rglob("daily_integrated_decision_brief.json")))
    old_watchlist = ((existing_daily_brief.get("watchlist") or {}).get("records") or [])
    old_per_ticker_financial = sum("financial_analysis" in row for row in old_watchlist)
    replay = _watchlist_replay(product, valuation, integrated, _fact_summary_by_ticker(rows))
    after_watchlist_financial = sum(row["financial_analysis"].get("status") in {"AVAILABLE", "ABSENT"} for row in replay["records"] if row["requested_watchlist"])
    coverage_fundamental = {
        "contract_version": "fundamental_coverage_before_after/v1", "primary_session": PRIMARY_SESSION,
        "before": {"daily_brief_watchlist_per_ticker_financial_context": old_per_ticker_financial, "source_daily_brief_identity": existing_daily_brief.get("artifact_identity")},
        "after": {"daily_brief_watchlist_per_ticker_financial_context": after_watchlist_financial, "watchlist_denominator": len(replay["watchlist_tickers"]), "financial_product_available": (product.get("coverage") or {}).get("financial_product_available"), "financial_product_absent_explicit": (product.get("coverage") or {}).get("financial_product_absent"), "integrated_fundamental_context_available": (integrated.get("coverage") or {}).get("fundamental_context_available")},
        "change_scope": "local AI handoff projection only; Financial V2 formulas, semantic authority, and eligibility are unchanged",
    }
    valuation_methods = ("market_cap", "enterprise_value", "P/E", "P/B", "P/S", "EV/Sales", "EV/EBITDA")
    coverage_valuation = {
        "contract_version": "valuation_coverage_before_after/v1", "primary_session": PRIMARY_SESSION,
        "before": {"session": EARLIER_SESSION, "market_wide_retained_coverage": _market_wide_method_coverage(earlier_valuation, valuation_methods), "daily_brief_watchlist_method_level_valuation": sum("valuation_methods" in row for row in old_watchlist), "source_daily_brief_identity": existing_daily_brief.get("artifact_identity")},
        "after": {"session": PRIMARY_SESSION, "market_wide_retained_coverage": _market_wide_method_coverage(current_market_valuation, valuation_methods), "daily_brief_watchlist_method_level_valuation": after_watchlist_financial, "method_status_distribution": method_counts},
        "change_scope": "The session-to-session method counts are evidence observations, not a new valuation model. The implementation change only passes existing method-level status/fitness, peer gate, and reconciliation through per watchlist ticker; no method was recalculated or promoted.",
    }
    blocker = {
        "contract_version": "financial_blocker_distribution/v1", "primary_session": PRIMARY_SESSION,
        "period_semantics_unresolved": semantics.get("unresolved_blocker_distribution"),
        "semantic_metadata_missing": (semantics.get("coverage") or {}).get("missing_metadata_distribution"),
        "financial_product": (product.get("financial_analysis_product") or {}).get("coverage"),
        "current_market_valuation_first_blockers": (current_market_valuation.get("coverage") or {}).get("first_blocker_counts"),
        "valuation_method_status_distribution": method_counts,
        "valuation_limitations": {"current_research_not_pit_or_authoritative": True, "share_basis_proxy_remains_explicit": True, "monetary_scale_blocks_remain": True},
    }
    temporal = _temporal_replay(rows, earlier_valuation)
    for name, payload in {
        "financial_data_inventory.json": inventory, "period_semantics_matrix.json": matrix,
        "financial_feature_fitness_matrix.json": feature_matrix, "fundamental_coverage_before_after.json": coverage_fundamental,
        "valuation_coverage_before_after.json": coverage_valuation, "financial_blocker_distribution.json": blocker,
        "watchlist_financial_replay.json": replay, "temporal_replay_validation.json": temporal,
    }.items():
        _write(output / name, payload)
    report = f"""# Core financial data to fundamental valuation scaleout V1

Status: COMPLETE / PARTIAL_BY_EVIDENCE.

Primary retained session: `{PRIMARY_SESSION}`. Earlier governed replay: `{EARLIER_SESSION}`.
This closeout reuses the existing retained Financial V2 semantics, engine/product projection,
Current Research valuation/peer gates, and Daily integrated decision product. It adds no provider,
financial formula, valuation conclusion, target price, probability, authority promotion, database
write, or remote operation.

## Measured retained coverage

- Semantic facts: {len(rows):,}; tickers: {(semantics.get('coverage') or {}).get('ticker_count'):,}.
- Financial product: {(product.get('coverage') or {}).get('financial_product_available'):,} AVAILABLE and {(product.get('coverage') or {}).get('financial_product_absent'):,} explicit ABSENT over {(product.get('coverage') or {}).get('decision_denominator'):,} Daily tickers.
- Integrated fundamental context: {(integrated.get('coverage') or {}).get('fundamental_context_available'):,}.
- Local AI Daily watchlist handoff: {old_per_ticker_financial} -> {after_watchlist_financial} per-ticker Financial V2 contexts; method-level valuation handoff: {sum('valuation_methods' in row for row in old_watchlist)} -> {after_watchlist_financial}.

## Evidence-limited result

The retained semantic store supports period-class-aware current research.  It does not support
financial authority promotion or a general historical financial backtest. Missing timestamps are
rejected from the temporal replay; share resolution is verified from the retained `{EARLIER_SESSION}`
artifact itself. Valuation and peer methods remain method/basis/entity/period gated. All residuals
are quantified in `financial_blocker_distribution.json` and preserved per ticker in
`watchlist_financial_replay.json`.

Owner override recorded: `{OWNER_OVERRIDE}`.
"""
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    return {"facts": len(rows), "period_classes": _counter_dict(classes), "watchlist_after": after_watchlist_financial, "temporal": temporal["result"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build(args.output_dir)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
