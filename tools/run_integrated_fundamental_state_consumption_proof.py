"""Retained 2026-09-24 proof for INTEGRATED_FUNDAMENTAL_STATE_CONSUMPTION_RECONCILIATION_V1.

``prove`` runs the real Daily Integrated Decision assembly (``run_current_research_decision_
convergence_proof assemble``) three times over byte-copied retained inputs under the audit-hook
write guard: once under the Financial V2 input-integrity checkpoint code (baseline), twice under
this checkout (after, rerun). ``summarize`` derives the reconciliation from that work root alone:
the producer state inventory, consumption before and after, the states still unused and why, the
semantic contract, the fundamental synthesis, downstream transitions attributed to the exact
restored signal, freshness, representative semantic checks and the P/B regression. Rerunning
``summarize`` over the same work root reproduces the artifact identity. No provider, runtime
store, publication or pointer is touched.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import canonical_daily_financial_v2_materialization as fin_v2_material
import fundamental_signal_consumption_contract as contract
import provider_financial_monetary_basis_verdict as verdict_pin
from tools import current_research_capability_map as capability
from tools import run_current_research_decision_convergence_proof as convergence
from tools import run_financial_v2_analysis_input_integrity_proof as prior

CONTRACT = "integrated_fundamental_state_consumption_reconciliation/v1"
SESSION = "2026-09-24"
BASELINE_COMMIT = "488eaf198b4091e7a8088b0af0f31fc95a090c1b"
WORKSPACE = Path("C:/Projects/StockLookup")
EXPECTED_WORK_ROOT = WORKSPACE / "tmp" / "fundamental-consumption-proof-work"
EXPECTED_OUTPUT_DIR = WORKSPACE / "operations-review" / "integrated-fundamental-state-consumption-reconciliation-v1-20260924"
PRIOR_PROOF = WORKSPACE / "operations-review" / "financial-v2-analysis-input-integrity-v1-20260924" / "financial_v2_analysis_input_integrity_proof.json"
RUNS = ("baseline", "after", "rerun")
ATTEMPTED, OFFICIAL, PRICED = "ATTEMPTED_COHORT", "OFFICIAL_RESEARCH_SCOPE", "PRICED_OFFICIAL_SCOPE"
BRIDGE_METHOD = contract.DIALECT_OPERATIONAL_BRIDGE
FAV, ADV = contract.FAVORABLE, contract.ADVERSE

#: The 488eaf1 reader's literal comparisons, per producer field (its whole vocabulary).
LEGACY_READ_VALUES = {
    "profitability_state": {"PROFITABLE", "LOSS_MAKING", "TURNAROUND_CONTEXT"},
    "earnings_turnaround_state": {"TURNAROUND"},
    "margin_state": {"MARGIN_EXPANDING", "MARGIN_COMPRESSING"},
    "gross_margin_trajectory_state": {"IMPROVING", "WORSENING"},
    "growth_state": {"ACCELERATING", "EXPANDING", "CONTRACTING"},
    "cash_conversion_state": {"HEALTHY", "WEAK"},
    "balance_sheet_state": {"STRENGTHENING", "DETERIORATING"},
    "leverage_state": {"SAFE", "STRESSED"},
    "working_capital_trajectory_state": {"IMPROVING", "WORSENING"},
    "bank_asset_quality_state": {"STRONG", "IMPROVING", "WEAK", "DETERIORATING"},
    "brokerage_mix_trajectory_state": {"BROKERAGE_MIX_RISING"},
}
#: Each 488eaf1 reason code is one vote in one dimension/axis of the contract.
LEGACY_CODE_VOTES = {
    "PROFITABLE_CORE_OPERATIONS": ("PROFITABILITY.LEVEL", FAV), "OBSERVED_LOSS_MAKING": ("PROFITABILITY.LEVEL", ADV),
    "EARNINGS_TURNAROUND_DETECTED": ("PROFITABILITY.TRANSITION", FAV),
    "MARGIN_EXPANSION": ("MARGINS.DIRECTION", FAV), "MARGIN_COMPRESSION": ("MARGINS.DIRECTION", ADV),
    "REVENUE_GROWTH_EXPANDING": ("GROWTH.DIRECTION", FAV), "REVENUE_CONTRACTION": ("GROWTH.DIRECTION", ADV),
    "POSITIVE_CASH_CONVERSION_PROXY": ("CASH_QUALITY.LEVEL", FAV), "WEAK_CASH_CONVERSION_PROXY": ("CASH_QUALITY.LEVEL", ADV),
    "BALANCE_SHEET_STRENGTHENING": ("CAPITAL_STRUCTURE.DIRECTION", FAV),
    "BALANCE_SHEET_DETERIORATING": ("CAPITAL_STRUCTURE.DIRECTION", ADV),
    "CONSERVATIVE_LEVERAGE": ("CAPITAL_STRUCTURE.LEVEL", FAV), "ELEVATED_LEVERAGE_STRESS": ("CAPITAL_STRUCTURE.LEVEL", ADV),
    "WORKING_CAPITAL_IMPROVING": ("LIQUIDITY.DIRECTION", FAV), "WORKING_CAPITAL_WORSENING": ("LIQUIDITY.DIRECTION", ADV),
    "BANK_ASSET_QUALITY_STRONG": ("BANK_ASSET_QUALITY.DIRECTION", FAV),
    "BANK_ASSET_QUALITY_IMPROVING": ("BANK_ASSET_QUALITY.DIRECTION", FAV),
    "BANK_ASSET_QUALITY_WEAK": ("BANK_ASSET_QUALITY.DIRECTION", ADV),
    "BANK_ASSET_QUALITY_DETERIORATING": ("BANK_ASSET_QUALITY.DIRECTION", ADV),
    "SECURITIES_BROKERAGE_MIX_EXPANDING": ("SECURITIES_COMPOSITION.COMPOSITION", FAV),
}
PRODUCER_FIELDS = sorted({spec["producer_field"] for spec in contract.SIGNALS.values()} | set(contract.NOT_CONSUMED))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(convergence.canonical(value) + b"\n")


def _counts(values: Iterable[Any]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def _transitions(pairs: Iterable[tuple[Any, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(f"{a} -> {b}" for a, b in pairs if a != b).items()))


def prove(args: argparse.Namespace) -> dict:
    producer_root, baseline_root = Path(args.producer_root).resolve(), Path(args.baseline_code_root).resolve()
    work_root, output_dir = Path(args.work_root).resolve(), Path(args.output_dir).resolve()
    if work_root != EXPECTED_WORK_ROOT.resolve() or output_dir != EXPECTED_OUTPUT_DIR.resolve():
        raise SystemExit("PROOF_ROOTS_OUTSIDE_NAMED_TARGETS")
    if convergence._git(baseline_root, "rev-parse", "HEAD") != BASELINE_COMMIT:
        raise SystemExit("BASELINE_CODE_ROOT_NOT_AT_INPUT_INTEGRITY_CHECKPOINT")
    if not all(prior._pinned_authority_equal(baseline_root).values()):
        raise SystemExit("PINNED_FINANCIAL_V2_EVIDENCE_DIFFERS_BETWEEN_CODE_ROOTS")
    evidence = prior._evidence_paths(producer_root)
    before = prior._hashes(evidence)
    for name, code_root in (("baseline", baseline_root), ("after", ROOT), ("rerun", ROOT)):
        convergence._run_assembly(code_root, producer_root, work_root / name, SESSION)
    if prior._hashes(evidence) != before:
        raise SystemExit("RETAINED_EVIDENCE_SHA_CHANGED")
    _write(work_root / "retained_evidence_sha256.json", before)
    return summarize(args)


def _legacy_reader(baseline_root: Path):
    """The exact 488eaf1 fundamental reader, loaded from the baseline checkout's own file."""
    spec = importlib.util.spec_from_file_location("baseline_integrated_decision",
                                                  baseline_root / "integrated_investment_decision_product.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.evaluate_fundamental_direction


def _is_bridge(record: Mapping[str, Any]) -> bool:
    return ((record.get("evidence_axes") or {}).get("FUNDAMENTAL") or {}).get("method") == BRIDGE_METHOD


def _legacy_votes(supports: Iterable[str], counters: Iterable[str]) -> dict[str, str]:
    votes: dict[str, str] = {}
    for code in list(supports) + list(counters):
        if code in LEGACY_CODE_VOTES:
            label, polarity = LEGACY_CODE_VOTES[code]
            votes[label] = polarity
    return votes


def _new_votes(synthesis: Mapping[str, Any]) -> dict[str, str]:
    derivation = synthesis.get("derivation") or {}
    return {**{label: FAV for label in derivation.get("favorable_votes") or []},
            **{label: ADV for label in derivation.get("adverse_votes") or []}}


def _cause(label: str, synthesis: Mapping[str, Any]) -> dict[str, Any]:
    """Name the exact signal(s) behind one changed dimension vote."""
    dimension, axis = label.split(".")
    signals = [s for s in synthesis.get("signals") or [] if s["dimension"] == dimension and s["axis"] == axis]
    value = ((synthesis.get("dimensions") or {}).get(dimension) or {}).get(axis.lower())
    restored = [s for s in signals if s["decision_eligible"]
                and s["producer_value"] not in LEGACY_READ_VALUES.get(s["producer_field"], set())]
    excluded = [s for s in signals if not s["decision_eligible"] and s["role"] == contract.DECISION and s.get("exclusion")]
    superseded = ((synthesis.get("dimensions") or {}).get(dimension) or {}).get("superseded_stale_signals") or []
    if value == contract.MIXED:
        category = "WITHIN_DIMENSION_CONFLICT"
    elif restored:
        category = "RESTORED_SIGNAL"
    elif any(s["exclusion"] == "FINANCIAL_PERIOD_UNAVAILABLE_FOR_DECISION" for s in excluded):
        category = "FRESHNESS_GATE_UNAVAILABLE_PERIOD"
    elif any(s["exclusion"].startswith("CASH_CONVERSION") for s in excluded):
        category = "CASH_CONVERSION_SIGN_GUARD"
    elif superseded:
        category = "STALE_SUPERSEDED_BY_CURRENT"
    elif any(s["role"] == contract.EVIDENCE_ONLY for s in signals):
        category = "EVIDENCE_ONLY_RECLASSIFICATION"
    else:
        category = "VOCABULARY_NORMALIZATION"
    return {"dimension": label, "category": category, "dimension_value_after": value,
            "signals": sorted({s["signal_id"] for s in (restored or excluded or signals)}),
            "producer_values": {s["signal_id"]: s["producer_value"] for s in sorted(signals, key=lambda s: s["signal_id"])}}


def _attribution(ticker: str, b: Mapping[str, Any], a: Mapping[str, Any], legacy: tuple[str, list, list]) -> dict[str, Any]:
    synthesis = a["fundamental_synthesis"]
    old_votes, new_votes = _legacy_votes(legacy[1], legacy[2]), _new_votes(synthesis)
    changed = sorted(label for label in set(old_votes) | set(new_votes) if old_votes.get(label) != new_votes.get(label))
    causes = [dict(_cause(label, synthesis), before=old_votes.get(label), after=new_votes.get(label)) for label in changed]
    flags = []
    if _is_bridge(b) != _is_bridge(a):
        flags.append("OPERATIONAL_BRIDGE_CONSULTATION_CHANGED")
    if (b["fundamental_state"] == "TURNAROUND") != (a["fundamental_state"] == "TURNAROUND"):
        flags.append("TURNAROUND_OVERRIDE_CHANGED")
    derivation = synthesis.get("derivation") or {}
    if (a["fundamental_state"] == "INSUFFICIENT" and derivation.get("adverse_votes")
            and not derivation.get("favorable_votes") and not derivation.get("deterioration_gate")):
        flags.append("ADVERSE_EVIDENCE_WITHOUT_DETERIORATION_GATE_RESOLVES_INSUFFICIENT")
    return {"ticker": ticker, "fundamental_state": [b["fundamental_state"], a["fundamental_state"]],
            "votes_before": dict(sorted(old_votes.items())), "votes_after": dict(sorted(new_votes.items())),
            "causes": causes, "flags": flags}


def _inventory(compact: Mapping[str, Any], syntheses: Mapping[str, Mapping[str, Any]], tickers: Iterable[str]) -> dict[str, Any]:
    tickers = sorted(tickers)
    records = compact["records"]
    out: dict[str, Any] = {}
    for field in PRODUCER_FIELDS:
        values = Counter(str(records[t].get(field)) for t in tickers if records[t].get("status") == "AVAILABLE")
        present = {t for t in tickers if records[t].get("status") == "AVAILABLE"
                   and records[t].get(field) not in (None, "UNAVAILABLE", "NOT_APPLICABLE", "WORKING_CAPITAL_UNAVAILABLE")}
        before = sum(records[t].get(field) in LEGACY_READ_VALUES.get(field, set()) for t in present)
        signals = [s for t in present for s in syntheses[t]["signals"] if s["producer_field"] == field]
        out[field] = {
            "values": dict(sorted(values.items())), "present": len(present),
            "consumed_before": before, "unused_before": len(present) - before,
            "decision_after": sum(s["decision_eligible"] for s in signals),
            "evidence_only_after": sum(s["role"] == contract.EVIDENCE_ONLY for s in signals),
            "excluded_after": _counts(s["exclusion"] for s in signals if s["role"] == contract.DECISION and not s["decision_eligible"]),
            "decision_after_freshness": _counts(s["fitness"]["freshness"] for s in signals if s["decision_eligible"]),
            "not_consumed_reason": contract.NOT_CONSUMED.get(field),
        }
    return out


def _engine_value(engine: Mapping[str, Any], ticker: str, feature: str) -> dict[str, Any]:
    item = ((engine["records"].get(ticker) or {}).get("features") or {}).get(feature) or {}
    return {key: item.get(key) for key in ("fitness", "value", "period_identity", "semantic_transition", "growth_basis")}


def _sample(ticker: str, rule: str, b: Mapping[str, Any], a: Mapping[str, Any], engine: Mapping[str, Any],
            features: Iterable[str]) -> dict[str, Any]:
    synthesis = a["fundamental_synthesis"]
    return {"ticker": ticker, "selection_rule": rule,
            "fundamental_state": [b["fundamental_state"], a["fundamental_state"]],
            "research_action_posture": [b["research_action_posture"], a["research_action_posture"]],
            "source_dialect": synthesis.get("source_dialect"),
            "dimensions": synthesis.get("dimensions"), "derivation": synthesis.get("derivation"),
            "strengths": synthesis.get("strengths"), "weaknesses": synthesis.get("weaknesses"),
            "improving": synthesis.get("improving"), "deteriorating": synthesis.get("deteriorating"),
            "stale": synthesis.get("stale"), "non_applicable": synthesis.get("non_applicable"),
            "engine_values_for_review": {feature: _engine_value(engine, ticker, feature) for feature in features}}


def _signal_of(synthesis: Mapping[str, Any], signal_id: str) -> Mapping[str, Any]:
    return next((s for s in synthesis.get("signals") or [] if s["signal_id"] == signal_id), {})


def _numeric(engine: Mapping[str, Any], ticker: str, feature: str) -> float | None:
    value = _engine_value(engine, ticker, feature).get("value")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _usefulness(iid_b: Mapping[str, Any], iid_a: Mapping[str, Any], engine: Mapping[str, Any], official: set[str],
                compact: Mapping[str, Any], fv2: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Representative entities chosen by generic, deterministic rules (never a ticker list)."""
    b, a = iid_b["records"], iid_a["records"]
    corp = sorted(t for t in official if (compact["records"][t].get("analysis_family") == "INDUSTRIAL_FINANCIAL_ANALYSIS"
                                          and a[t]["fundamental_synthesis"].get("source_dialect") == contract.DIALECT_FINANCIAL_V2))

    def pick(candidates: list[str], key) -> str | None:
        return max(candidates, key=lambda t: (key(t), t)) if candidates else None

    def current_eligible(t: str, signal_id: str, value: str) -> bool:
        signal = _signal_of(a[t]["fundamental_synthesis"], signal_id)
        return bool(signal.get("decision_eligible")) and signal.get("value") == value and signal["fitness"]["freshness"] == "CURRENT"

    out: dict[str, Any] = {}
    lev = [t for t in corp if current_eligible(t, "debt_to_equity_direction", contract.IMPROVING) and _numeric(engine, t, "debt_to_equity") is not None]
    t = pick(lev, lambda t: _numeric(engine, t, "debt_to_equity"))
    if t:
        out["improving_leverage_high_absolute_debt"] = _sample(
            t, "official corporate; D/E direction IMPROVING (CURRENT); highest engine D/E value", b[t], a[t], engine,
            ("debt_to_equity", "debt_to_equity_direction", "equity_to_assets", "net_income_sign"))
    margin = [t for t in corp if (current_eligible(t, "net_margin_direction", contract.WORSENING)
                                  or current_eligible(t, "gross_margin_direction", contract.WORSENING))
              and _numeric(engine, t, "gross_margin") is not None]
    t = pick(margin, lambda t: _numeric(engine, t, "gross_margin"))
    if t:
        out["strong_margin_deteriorating_direction"] = _sample(
            t, "official corporate; a margin direction WORSENING (CURRENT); highest engine gross margin", b[t], a[t], engine,
            ("gross_margin", "gross_margin_direction", "net_margin", "net_margin_direction"))
    turn = [t for t in corp if (a[t]["fundamental_synthesis"]["derivation"]["turnaround"] or {}).get("triggered")]
    t = pick(turn, lambda t: _numeric(engine, t, "net_income_sign") or 0.0)
    if t:
        out["turnaround"] = _sample(t, "official corporate; TURNAROUND triggered; largest current net income", b[t], a[t], engine,
                                    ("net_income_sign", "net_income_qoq", "net_income_same_quarter_yoy", "net_income_ttm_yoy"))
    l2p = [t for t in corp if current_eligible(t, "earnings_transition", contract.LOSS_TO_PROFIT)]
    t = pick(l2p, lambda t: _numeric(engine, t, "net_income_sign") or 0.0)
    if t:
        out["loss_to_profit_current_transition"] = _sample(
            t, "official corporate; CURRENT loss-to-profit transition; largest current net income", b[t], a[t], engine,
            ("net_income_sign", "net_income_qoq", "net_income_same_quarter_yoy", "revenue_qoq"))
    det = [t for t in corp if a[t]["fundamental_state"] == "DETERIORATING"
           and a[t]["fundamental_synthesis"]["decision_signal_freshness"].keys() == {"CURRENT"}]
    t = pick(det, lambda t: len(a[t]["fundamental_synthesis"]["derivation"]["adverse_votes"]))
    if t:
        out["deteriorating"] = _sample(t, "official corporate; DETERIORATING on CURRENT signals only; most adverse votes",
                                       b[t], a[t], engine, ("net_income_sign", "net_margin", "debt_to_equity", "equity_to_assets"))
    for issuer in ("bank", "securities"):
        pool = sorted(t for t in official if compact["records"][t].get("issuer_type") == issuer)
        if pool:
            sample = _sample(pool[0], f"first official {issuer} issuer by ticker", b[pool[0]], a[pool[0]],
                             engine, ("net_income_sign", "debt_to_equity"))
            # The decision may come from the operational bridge; applicability is the Financial V2 view.
            sample["financial_v2_view"] = {key: fv2[pool[0]].get(key) for key in (
                "fundamental_state", "non_applicable", "missing", "dimensions")}
            out[f"non_applicable_{issuer}"] = sample
    stale = [t for t in corp if a[t]["fundamental_state"] != "INSUFFICIENT"
             and a[t]["fundamental_synthesis"]["derivation"]["stale_votes"]]
    t = pick(stale, lambda t: max((s["fitness"]["completed_quarter_lag"] or 0) for s in a[t]["fundamental_synthesis"]["signals"]
                                  if s["decision_eligible"]))
    if t:
        out["stale_but_research_usable"] = _sample(t, "official corporate; decided by stale-but-usable votes; oldest period",
                                                   b[t], a[t], engine, ("net_income_sign", "equity_to_assets_direction"))
    checks = {}
    if "improving_leverage_high_absolute_debt" in out:
        s = out["improving_leverage_high_absolute_debt"]
        checks["direction_never_implies_level"] = (s["dimensions"]["CAPITAL_STRUCTURE"].get("level") == contract.UNAVAILABLE
                                                   and "debt_to_equity_direction" in s["improving"])
    if "strong_margin_deteriorating_direction" in out:
        s = out["strong_margin_deteriorating_direction"]
        checks["high_margin_keeps_worsening_direction"] = s["dimensions"]["MARGINS"].get("direction") in (contract.WORSENING, contract.MIXED)
    if "turnaround" in out:
        s = out["turnaround"]
        checks["turnaround_is_current_transition_not_level"] = (
            s["dimensions"]["PROFITABILITY"].get("transition") == contract.LOSS_TO_PROFIT
            and s["derivation"]["turnaround"]["freshness"] == "CURRENT" and "profitability_level" not in s["strengths"])
    if "loss_to_profit_current_transition" in out:
        s = out["loss_to_profit_current_transition"]
        transition = _signal_of(a[s["ticker"]]["fundamental_synthesis"], "earnings_transition")
        checks["loss_to_profit_stays_a_transition"] = (
            s["dimensions"]["PROFITABILITY"].get("transition") == contract.LOSS_TO_PROFIT
            and "earnings_transition" not in s["improving"] and "earnings_transition" not in s["strengths"]
            and (s["fundamental_state"][1] == "TURNAROUND") == (transition["fitness"]["basis"] in contract.TURNAROUND_BASES))
    stale_turn = [t for t in corp if _signal_of(a[t]["fundamental_synthesis"], "earnings_transition").get("value") == contract.LOSS_TO_PROFIT
                  and (_signal_of(a[t]["fundamental_synthesis"], "earnings_transition").get("fitness") or {}).get("basis") in contract.TURNAROUND_BASES
                  and not a[t]["fundamental_synthesis"]["derivation"]["turnaround"]["triggered"]]
    t = pick(stale_turn, lambda t: -(_signal_of(a[t]["fundamental_synthesis"], "earnings_transition")["fitness"]["completed_quarter_lag"] or 0))
    if t:
        out["stale_turnaround_not_current"] = _sample(
            t, "official corporate; YoY/TTM loss-to-profit that does not trigger TURNAROUND; most recent such period",
            b[t], a[t], engine, ("net_income_sign", "net_income_same_quarter_yoy"))
        checks["stale_transition_never_current_turnaround"] = (
            out["stale_turnaround_not_current"]["derivation"]["turnaround"]["freshness"] != "CURRENT")
    for issuer in ("bank", "securities"):
        if f"non_applicable_{issuer}" in out:
            view = out[f"non_applicable_{issuer}"]["financial_v2_view"]
            checks[f"corporate_states_non_applicable_for_{issuer}"] = {
                "growth_direction", "debt_to_equity_direction", "net_working_capital_direction"} <= set(view["non_applicable"])
    if "stale_but_research_usable" in out:
        checks["stale_votes_labelled"] = bool(out["stale_but_research_usable"]["stale"])
    return {"samples": out, "semantic_checks": checks}


def summarize(args: argparse.Namespace) -> dict:
    producer_root, baseline_root = Path(args.producer_root).resolve(), Path(args.baseline_code_root).resolve()
    work_root, output_dir = Path(args.work_root).resolve(), Path(args.output_dir).resolve()
    if work_root != EXPECTED_WORK_ROOT.resolve() or output_dir != EXPECTED_OUTPUT_DIR.resolve():
        raise SystemExit("PROOF_ROOTS_OUTSIDE_NAMED_TARGETS")
    runs = {name: prior._load_run(work_root, name) for name in RUNS}
    for name, run in runs.items():
        guard = run["assembly"]
        if (guard["write_guard"]["violations"] or guard["provider_calls"] or guard["runtime_store_reads"]
                or guard.get("network_audit_events") is None or any(guard["network_audit_events"].values())):
            raise SystemExit(f"EVIDENCE_GUARD_OR_PROVIDER_CALL_VIOLATION:{name}")
    if len({json.dumps(run["assembly"]["staged_session_inputs"], sort_keys=True) for run in runs.values()}) != 1:
        raise SystemExit("STAGED_SESSION_INPUTS_DIFFER")
    for key in ("iid", "compact", "valuation"):
        if runs["after"][key]["artifact_identity"] != runs["rerun"][key]["artifact_identity"]:
            raise SystemExit(f"AFTER_REPLAY_NOT_DETERMINISTIC:{key}")
    prior_proof = convergence.load(PRIOR_PROOF)
    reproduced = {"integrated": runs["baseline"]["iid"]["artifact_identity"],
                  "evaluated_valuation": runs["baseline"]["valuation"]["artifact_identity"],
                  "financial_analysis_product": runs["baseline"]["compact"]["artifact_identity"],
                  "financial_engine": runs["baseline"]["compact"]["source_context_identity"]}
    if any(prior_proof["identities"]["after"][key] != value for key, value in reproduced.items()):
        raise SystemExit("BASELINE_DOES_NOT_REPRODUCE_INPUT_INTEGRITY_CHECKPOINT")
    ops = producer_root / "operations-review"
    maps = {name: capability.build(ops, SESSION, {"integrated": runs[name]["iid_path"]}) for name in RUNS}
    if maps["after"]["artifact_identity"] != maps["rerun"]["artifact_identity"]:
        raise SystemExit("CAPABILITY_MAP_NOT_DETERMINISTIC")
    if maps["baseline"]["artifact_identity"] != prior_proof["identities"]["after"]["capability_map"]:
        raise SystemExit("BASELINE_CAPABILITY_MAP_DOES_NOT_REPRODUCE_CHECKPOINT")
    rows = maps["after"]["records"]
    attempted = set(rows)
    official = {t for t, row in rows.items() if row["universe_status"] == "OFFICIAL_RESEARCH_SCOPE"}
    priced = {t for t in official if rows[t]["research_market_cap_usable"]}
    if not (priced <= official <= attempted) or len(official) != prior_proof["denominators"][OFFICIAL] \
            or len(priced) != prior_proof["denominators"][PRICED]:
        raise SystemExit("DENOMINATORS_DO_NOT_RECONCILE")

    engine = fin_v2_material.build_engine_artifact(root=ROOT, requested_at=f"{SESSION}T15:00:00+07:00")
    if engine["artifact_identity"] != runs["after"]["compact"]["source_context_identity"] \
            or engine["artifact_identity"] != runs["baseline"]["compact"]["source_context_identity"]:
        raise SystemExit("ENGINE_NOT_UNCHANGED_ACROSS_RUNS")
    compact_b, compact_a = runs["baseline"]["compact"], runs["after"]["compact"]
    state_fields = [field for field in PRODUCER_FIELDS]
    state_diffs = sum(compact_b["records"][t].get(f) != compact_a["records"][t].get(f) for t in attempted for f in state_fields)
    if state_diffs:
        raise SystemExit("PRODUCER_STATES_DIFFER_BETWEEN_RUNS")
    iid_b, iid_a = runs["baseline"]["iid"], runs["after"]["iid"]
    b_records, a_records = iid_b["records"], iid_a["records"]
    fv2 = {t: contract.evaluate(compact_a["records"][t], decision_session=SESSION) for t in sorted(attempted)}

    legacy = _legacy_reader(baseline_root)
    operational = convergence.load(work_root / "baseline" / "outputs" / "operational_fundamental_context_integration.json")
    legacy_reads: dict[str, tuple[str, list, list]] = {}
    for t in sorted(attempted):
        source = ((operational["records"].get(t) or {}).get("financial_context") if _is_bridge(b_records[t])
                  else compact_b["records"][t])
        legacy_reads[t] = legacy(source)
        if legacy_reads[t][0] != b_records[t]["fundamental_state"]:
            raise SystemExit(f"LEGACY_READER_DOES_NOT_REPRODUCE_BASELINE:{t}")

    changed = sorted(t for t in attempted if b_records[t]["fundamental_state"] != a_records[t]["fundamental_state"])
    attribution = {t: _attribution(t, b_records[t], a_records[t], legacy_reads[t]) for t in changed}
    cause_counts: dict[str, Counter] = {ATTEMPTED: Counter(), OFFICIAL: Counter()}
    signal_counts: dict[str, Counter] = {ATTEMPTED: Counter(), OFFICIAL: Counter()}
    flag_counts: dict[str, Counter] = {ATTEMPTED: Counter(), OFFICIAL: Counter()}
    for t, entry in attribution.items():
        for population in ((ATTEMPTED,) + ((OFFICIAL,) if t in official else ())):
            cause_counts[population].update({cause["category"] for cause in entry["causes"]})
            signal_counts[population].update({f"{cause['category']}:{signal}" for cause in entry["causes"] for signal in cause["signals"]})
            flag_counts[population].update(entry["flags"])
    decision_changes = {ATTEMPTED: prior._decision_changes(iid_b, iid_a, attempted),
                        OFFICIAL: prior._decision_changes(iid_b, iid_a, official)}
    posture_changed = sorted(t for t in official if b_records[t]["research_action_posture"] != a_records[t]["research_action_posture"])
    posture_attribution = []
    for t in posture_changed:
        entry = attribution.get(t) or {}
        posture_attribution.append({
            "ticker": t, "posture": [b_records[t]["research_action_posture"], a_records[t]["research_action_posture"]],
            "fundamental_state": [b_records[t]["fundamental_state"], a_records[t]["fundamental_state"]],
            "tactical_phase": a_records[t]["tactical_phase"], "market_structure_state": a_records[t]["market_structure_state"],
            "evidence_currency_gate_applied": [b_records[t]["evidence_currency_gate"].get("applied"),
                                               a_records[t]["evidence_currency_gate"].get("applied")],
            "cause_categories": sorted({cause["category"] for cause in entry.get("causes") or []}),
            "cause_signals": sorted({signal for cause in entry.get("causes") or [] for signal in cause["signals"]}),
            "flags": entry.get("flags") or []})
    posture_cause = Counter()
    for item in posture_attribution:
        posture_cause.update(item["cause_categories"] or ["UNATTRIBUTED"])
    unexplained = [item["ticker"] for item in posture_attribution
                   if item["fundamental_state"][0] == item["fundamental_state"][1]]
    if unexplained:
        raise SystemExit("UNEXPLAINED_POSTURE_TRANSITIONS:" + ",".join(unexplained))

    def dim_values(tickers: Iterable[str]) -> dict[str, dict[str, int]]:
        out: dict[str, Counter] = defaultdict(Counter)
        for t in tickers:
            for dimension, entry in (a_records[t]["fundamental_synthesis"].get("dimensions") or {}).items():
                for axis in ("level", "direction", "transition", "composition"):
                    if axis in entry:
                        out[f"{dimension}.{axis.upper()}"][entry[axis]] += 1
        return {key: dict(sorted(value.items())) for key, value in sorted(out.items())}

    def synthesis_view(tickers: Iterable[str]) -> dict[str, Any]:
        tickers = sorted(tickers)
        syn = [a_records[t]["fundamental_synthesis"] for t in tickers]
        return {
            "fundamental_state_before": _counts(b_records[t]["fundamental_state"] for t in tickers),
            "fundamental_state_after": _counts(a_records[t]["fundamental_state"] for t in tickers),
            "fundamental_state_transitions": _transitions((b_records[t]["fundamental_state"], a_records[t]["fundamental_state"]) for t in tickers),
            "source_dialect_after": _counts(s.get("source_dialect") for s in syn),
            "dimension_values_after": dim_values(tickers),
            "records_with": {key: sum(bool(s.get(key)) for s in syn)
                             for key in ("strengths", "weaknesses", "improving", "deteriorating", "transitions", "stale", "context_only")},
            "within_dimension_conflicts": _counts(dimension for s in syn for dimension, entry in (s.get("dimensions") or {}).items()
                                                  if entry.get("conflicting_axes")),
            "turnaround_triggered": sum(bool(s["derivation"]["turnaround"]["triggered"]) for s in syn),
            "records_with_stale_votes": sum(bool(s["derivation"]["stale_votes"]) for s in syn),
            "adverse_only_without_gate_insufficient": sum(
                s["fundamental_state"] == "INSUFFICIENT" and bool(s["derivation"]["adverse_votes"])
                and not s["derivation"]["favorable_votes"] and not s["derivation"]["deterioration_gate"] for s in syn),
        }

    verdict = verdict_pin.resolve(ROOT)
    pb = prior._pb_regression(runs["baseline"]["valuation"], runs["after"]["valuation"], official, verdict)
    pb["evaluated_valuation_identity_unchanged"] = runs["baseline"]["valuation"]["artifact_identity"] == runs["after"]["valuation"]["artifact_identity"]
    pb["integrated_valuation_context_summary_unchanged"] = all(
        b_records[t]["valuation_context_summary"] == a_records[t]["valuation_context_summary"] for t in attempted)
    pb["integrated_valuation_methods_unchanged"] = all(b_records[t]["valuation_methods"] == a_records[t]["valuation_methods"] for t in attempted)
    pb["p_b_current_research_values_byte_identical"] = all(
        convergence.canonical(runs["baseline"]["valuation"]["records"][t]["methods"][prior.PB_METHOD])
        == convergence.canonical(runs["after"]["valuation"]["records"][t]["methods"][prior.PB_METHOD]) for t in attempted)
    if not (pb["evaluated_valuation_identity_unchanged"] and pb["integrated_valuation_context_summary_unchanged"]
            and pb["p_b_current_research_values_byte_identical"] and not pb["method_field_differences_baseline_to_after"]
            and not pb["market_cap_value_differences"]):
        raise SystemExit("VALUATION_REGRESSION")

    fund_dim = lambda records, t: ((records[t].get("current_research_decision_input") or {}).get("dimensions") or {}).get("FUNDAMENTAL") or {}
    samples = _usefulness(iid_b, iid_a, engine, official, compact_a, fv2)
    # A decision identity may move without a fundamental/posture change only because the bridge
    # artifact it cites was rebuilt over a changed candidate set.
    identity_moves = [t for t in sorted(attempted) if b_records[t]["decision_identity"] != a_records[t]["decision_identity"]]
    identity_other = [t for t in identity_moves if b_records[t]["fundamental_state"] == a_records[t]["fundamental_state"]
                      and b_records[t]["research_action_posture"] == a_records[t]["research_action_posture"]]
    identity_unexplained = [t for t in identity_other
                            if b_records[t]["source_identities"].get("operational_fundamental_integration_identity")
                            == a_records[t]["source_identities"].get("operational_fundamental_integration_identity")]
    if identity_unexplained:
        raise SystemExit("UNEXPLAINED_DECISION_IDENTITY_CHANGES:" + ",".join(identity_unexplained[:20]))
    result: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT, "session": SESSION,
        "milestone": "INTEGRATED_FUNDAMENTAL_STATE_CONSUMPTION_RECONCILIATION_V1",
        "baseline_identity": {
            "baseline_commit": BASELINE_COMMIT, "after_code_head": runs["after"]["assembly"]["code_head"],
            "after_code_tracked_changes": runs["after"]["assembly"]["code_tracked_changes"],
            "reproduces_input_integrity_checkpoint": reproduced,
            "staged_session_inputs": runs["after"]["assembly"]["staged_session_inputs"],
            "retained_evidence_sha256": convergence.load(work_root / "retained_evidence_sha256.json"),
        },
        "identities": {name: {"integrated": runs[name]["iid"]["artifact_identity"],
                              "financial_analysis_product": runs[name]["compact"]["artifact_identity"],
                              "financial_engine": runs[name]["compact"]["source_context_identity"],
                              "evaluated_valuation": runs[name]["valuation"]["artifact_identity"],
                              "capability_map": maps[name]["artifact_identity"]} for name in RUNS},
        "guard": {name: {"violations": runs[name]["assembly"]["write_guard"]["violations"],
                         "network_audit_events": runs[name]["assembly"].get("network_audit_events"),
                         "provider_calls": runs[name]["assembly"]["provider_calls"],
                         "runtime_store_reads": runs[name]["assembly"]["runtime_store_reads"],
                         "publication": runs[name]["assembly"]["publication"]} for name in RUNS},
        "denominators": {ATTEMPTED: len(attempted), OFFICIAL: len(official), PRICED: len(priced)},
        "producer_consumer_mismatch": {
            "root_cause": ("integrated_investment_decision_product.evaluate_fundamental_direction (9160188, 2026-09-02) compared "
                           "hypothesised values (SAFE/STRESSED leverage, EXPANDING/ACCELERATING growth, bare TURNAROUND, "
                           "un-prefixed IMPROVING/WORSENING trajectories) that financial_analysis_engine_v2 never emitted; the "
                           "engine vocabulary (de2df6b, 2026-09-01) predates the reader"),
            "legacy_reader_literal_reads": {field: sorted(values) for field, values in sorted(LEGACY_READ_VALUES.items())},
            "legacy_reader_reproduces_baseline_states": True,
            "producer_findings": {
                "profit_to_loss_unreachable": ("engine _growth/_ttm_yoy and the flow bridge classify sign transitions only when the "
                                               "prior value is <= 0, so PROFIT_TO_LOSS is never emitted; a profit-to-loss swing is an "
                                               "ordinary growth value below -100% (feature-store yoy does emit TURNED_TO_LOSS)"),
                "balance_sheet_state_sources": _counts(
                    (_signal_of(fv2[t], "equity_to_assets_direction").get("fitness") or {}).get("source_features", [None])[0]
                    for t in sorted(official) if (_signal_of(fv2[t], "equity_to_assets_direction").get("value") not in (None, "UNAVAILABLE"))),
                "leverage_state_sources": _counts(
                    (_signal_of(fv2[t], "debt_to_equity_direction").get("fitness") or {}).get("source_features", [None])[0]
                    for t in sorted(official) if (_signal_of(fv2[t], "debt_to_equity_direction").get("value") not in (None, "UNAVAILABLE"))),
                "earnings_transition_bases": _counts(
                    (_signal_of(fv2[t], "earnings_transition").get("fitness") or {}).get("basis")
                    for t in sorted(official) if _signal_of(fv2[t], "earnings_transition").get("value") not in (None, "UNAVAILABLE", "NONE_OBSERVED")),
                "gross_margin_direction_freshness": _counts(
                    _signal_of(fv2[t], "gross_margin_direction")["fitness"]["freshness"] for t in sorted(official)
                    if _signal_of(fv2[t], "gross_margin_direction").get("value") not in (None, "UNAVAILABLE")),
            },
        },
        "semantic_consumption_contract": {
            "contract_version": contract.CONTRACT_VERSION, "derivation_rule": contract.DERIVATION_RULE,
            "signals": {signal_id: {key: spec[key] for key in ("producer_field", "dimension", "axis", "family", "role", "values", "codes", "semantic")}
                        for signal_id, spec in sorted(contract.SIGNALS.items())},
            "unclassified_levels": contract.UNCLASSIFIED_LEVELS, "not_consumed": contract.NOT_CONSUMED,
            "turnaround_bases": sorted(contract.TURNAROUND_BASES),
            "turnaround_freshness": sorted(contract.TURNAROUND_FRESHNESS),
            "dimension_vote_rule": ("one vote per dimension and axis: current evidence supersedes stale, agreeing measurements "
                                    "vote once, disagreeing measurements are shown as a conflict and never vote"),
            "fundamental_state_rule": ("TURNAROUND if a decision-eligible CURRENT LOSS_TO_PROFIT transition on a same-quarter YoY or TTM basis; "
                                       "DETERIORATING if adverse votes exceed favorable votes and profitability is STRESSED, growth "
                                       "WORSENING or capital structure WORSENING; IMPROVING if favorable only with growth, margins or "
                                       "liquidity improving; STABLE if favorable only; MIXED if both; otherwise INSUFFICIENT"),
        },
        "engine_state_inventory": {OFFICIAL: _inventory(compact_a, fv2, official), ATTEMPTED: _inventory(compact_a, fv2, attempted)},
        "fundamental_signal_consumption_coverage": {
            OFFICIAL: contract.coverage([a_records[t]["fundamental_synthesis"] for t in sorted(official)]),
            "financial_v2_only_official": contract.coverage([fv2[t] for t in sorted(official)])},
        "fundamental_synthesis": {OFFICIAL: synthesis_view(official), ATTEMPTED: synthesis_view(attempted)},
        "attribution": {
            "changed_fundamental_state": {ATTEMPTED: len(changed), OFFICIAL: sum(t in official for t in changed)},
            "cause_categories": {population: dict(sorted(counter.items())) for population, counter in cause_counts.items()},
            "cause_signals": {population: dict(sorted(counter.items())) for population, counter in signal_counts.items()},
            "flags": {population: dict(sorted(counter.items())) for population, counter in flag_counts.items()},
            "per_ticker": attribution,
        },
        "downstream": {
            "decision_changes": decision_changes,
            "research_classes": {
                "evidence_class": {population: {"before": _counts((b_records[t].get("current_research_decision_input") or {}).get("evidence_class") for t in tickers),
                                                "after": _counts((a_records[t].get("current_research_decision_input") or {}).get("evidence_class") for t in tickers)}
                                   for population, tickers in ((OFFICIAL, official), (PRICED, priced))},
                "decision_readiness_v1_rule": {"before": maps["baseline"]["decision_readiness"], "after": maps["after"]["decision_readiness"]},
            },
            "decision_identity": {
                "changed_attempted": len(identity_moves),
                "changed_by_fundamental_or_posture": len(identity_moves) - len(identity_other),
                "changed_only_by_rebuilt_bridge_identity": len(identity_other),
                "bridge": {"candidates": [runs[name]["assembly"]["operational_fundamental_binding"].get("candidates") for name in ("baseline", "after")],
                           "research_usable": [runs[name]["assembly"]["operational_fundamental_binding"].get("research_usable") for name in ("baseline", "after")],
                           "applied_official": [sum(_is_bridge(records[t]) for t in official) for records in (b_records, a_records)]},
                "unexplained": identity_unexplained},
            "posture_transitions": {"count_official": len(posture_changed),
                                    "transitions": decision_changes[OFFICIAL]["research_action_posture"]["transitions"],
                                    "by_cause_category": dict(sorted(posture_cause.items())),
                                    "per_ticker": posture_attribution, "unexplained": unexplained},
        },
        "freshness": {
            "denominator": OFFICIAL,
            "decision_signal_freshness": contract.coverage([a_records[t]["fundamental_synthesis"] for t in sorted(official)])["decision_signal_freshness"],
            "fundamental_dimension_freshness_when_available": _counts(
                fund_dim(a_records, t).get("freshness", {}).get("freshness_status") for t in official if fund_dim(a_records, t).get("state") == "AVAILABLE"),
            "records_with_stale_votes": synthesis_view(official)["records_with_stale_votes"],
            "records_with_unavailable_period_exclusions": sum(
                any(s.get("exclusion") == "FINANCIAL_PERIOD_UNAVAILABLE_FOR_DECISION" for s in a_records[t]["fundamental_synthesis"]["signals"])
                for t in official),
        },
        "investment_usefulness": samples,
        "p_b_regression": pb,
        "capability_maps": {name: {"identity": maps[name]["artifact_identity"], "decision_readiness": maps[name]["decision_readiness"],
                                   "decision_input_official": {key: maps[name]["current_research_decision_input"][key] for key in (
                                       "evidence_class_distribution", "dimension_state_distribution", "fundamental_freshness_distribution")}}
                            for name in ("baseline", "after")},
        "authority_boundary": {"current_research_only": True, "provider_or_data_authority_promoted": False,
                               "financial_v2_engine_changed": False, "pinned_financial_v2_authority_changed": False,
                               "posture_thresholds_or_policy_changed": False, "exact_valuation_authority": False,
                               "historical_pit_financial_authority": False, "execution_or_sizing_authority": False,
                               "entity_authority_expanded": False, "provider_calls": 0, "financial_data_acquired": False,
                               "vnstock_enabled": False, "publication": "NONE"},
    }
    result["artifact_sha256"] = hashlib.sha256(convergence.canonical(result)).hexdigest()
    result["artifact_identity"] = f"{CONTRACT}:{result['artifact_sha256']}"
    output_dir.mkdir(parents=True, exist_ok=True)
    _write(output_dir / "integrated_fundamental_state_consumption_reconciliation.json", result)
    (output_dir / "SUMMARY.md").write_text(_summary(result), encoding="utf-8")
    return result


def _summary(result: Mapping[str, Any]) -> str:
    d = result["denominators"]
    inv = result["engine_state_inventory"][OFFICIAL]
    syn = result["fundamental_synthesis"][OFFICIAL]
    down = result["downstream"]
    changes = down["decision_changes"][OFFICIAL]
    classes = down["research_classes"]["evidence_class"][OFFICIAL]
    posture = down["posture_transitions"]
    pb = result["p_b_regression"]
    lines = ["# Integrated fundamental state consumption reconciliation (retained 2026-09-24)", "",
             f"Proof: `{result['artifact_identity']}`",
             f"Baseline `{BASELINE_COMMIT[:7]}` reproduces the input-integrity checkpoint decision, valuation, compact product and map.",
             f"Denominators: attempted {d[ATTEMPTED]}; official {d[OFFICIAL]}; priced official {d[PRICED]}.", "",
             "## Producer states: present / consumed before -> decision after (official)", "",
             "| producer field | present | consumed before | decision after | evidence only | excluded after |",
             "|---|---|---|---|---|---|"]
    for field, entry in inv.items():
        if entry["present"]:
            lines.append(f"| {field} | {entry['present']} | {entry['consumed_before']} | {entry['decision_after']} | "
                         f"{entry['evidence_only_after']} | {entry['excluded_after'] or ''} |")
    evidence_only = {field: entry["evidence_only_after"] for field, entry in inv.items() if entry["evidence_only_after"]}
    excluded = {field: entry["excluded_after"] for field, entry in inv.items() if entry["excluded_after"]}
    lines += ["", "## Still unused as decision evidence (official)", "",
              f"- evidence only, by contract: {evidence_only}",
              f"- excluded per signal: {excluded}",
              f"- never consumed: {result['semantic_consumption_contract']['not_consumed']}; levels no producer classifies: "
              f"{result['semantic_consumption_contract']['unclassified_levels']}",
              f"- producer: {result['producer_consumer_mismatch']['producer_findings']['profit_to_loss_unreachable']}",
              "", "## Semantic consumption contract", "",
              f"- `{result['semantic_consumption_contract']['contract_version']}`: {len(result['semantic_consumption_contract']['signals'])} signals on "
              "LEVEL / DIRECTION / TRANSITION / COMPOSITION axes with applicability and fitness.",
              f"- {result['semantic_consumption_contract']['dimension_vote_rule']}.",
              f"- {result['semantic_consumption_contract']['fundamental_state_rule']}.",
              "", "## Fundamental synthesis (official)", "",
              f"- before: {syn['fundamental_state_before']}", f"- after: {syn['fundamental_state_after']}",
              f"- transitions: {syn['fundamental_state_transitions']}",
              f"- cause categories: {result['attribution']['cause_categories'][OFFICIAL]}",
              f"- flags: {result['attribution']['flags'][OFFICIAL]}",
              f"- within-dimension conflicts: {syn['within_dimension_conflicts']}",
              f"- turnaround triggered {syn['turnaround_triggered']}; records with stale votes {syn['records_with_stale_votes']}", "",
              "## Downstream (official)", "",
              f"- financial composite: {changes['financial_composite_state_transitions']}",
              f"- evidence coherence: {changes['evidence_axis_coherence_transitions']}",
              f"- counter-thesis changed {changes['counter_thesis_changed']}; gained {changes['counter_thesis_tags_gained']}; lost {changes['counter_thesis_tags_lost']}",
              f"- evidence class: {classes['before']} -> {classes['after']}",
              f"- research action posture: {posture['count_official']} transitions {posture['transitions']}",
              f"- posture causes: {posture['by_cause_category']}; unexplained {posture['unexplained']}", "",
              "## Freshness (official)", "",
              f"- decision signals: {result['freshness']['decision_signal_freshness']}",
              f"- unavailable-period exclusions: {result['freshness']['records_with_unavailable_period_exclusions']} records", "",
              "## Valuation regression", "",
              f"- evaluated valuation identical: {pb['evaluated_valuation_identity_unchanged']}; P/B research byte-identical: {pb['p_b_current_research_values_byte_identical']}",
              f"- P/B usable {pb['usable_official']}; method field differences {pb['method_field_differences_baseline_to_after'] or 'none'}; market-cap differences {len(pb['market_cap_value_differences'])}",
              f"- verdict {pb['vci_balance_sheet_verdict']}; NCI limitation on every row {pb['nci_limitation_on_every_usable_row']}", "",
              "## Representative semantic checks", ""]
    for name, sample in result["investment_usefulness"]["samples"].items():
        lines.append(f"- {name}: {sample['ticker']} ({sample['selection_rule']}); fundamental_state "
                     f"{sample['fundamental_state'][0]} -> {sample['fundamental_state'][1]}; posture "
                     f"{sample['research_action_posture'][0]} -> {sample['research_action_posture'][1]}")
    lines += [f"- checks: {result['investment_usefulness']['semantic_checks']}", "",
              "## Authority", "",
              f"- {result['authority_boundary']}", "",
              "Retained evidence SHA-256 unchanged; zero provider calls, network audit events, runtime-store reads and write-guard violations.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prove", "summarize"):
        one = sub.add_parser(name)
        one.add_argument("--producer-root", required=True)
        one.add_argument("--baseline-code-root", required=True)
        one.add_argument("--work-root", required=True)
        one.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    result = prove(args) if args.command == "prove" else summarize(args)
    print(json.dumps({"artifact_identity": result["artifact_identity"], "denominators": result["denominators"],
                      "fundamental_state_after": result["fundamental_synthesis"][OFFICIAL]["fundamental_state_after"],
                      "posture": result["downstream"]["posture_transitions"]["transitions"]}, sort_keys=True))


if __name__ == "__main__":
    main()
