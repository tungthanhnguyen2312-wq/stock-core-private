"""Retained 2026-09-24 proof for FUNDAMENTAL_SIGNAL_POLICY_HARDENING_V1.

``prove`` runs the real Daily Integrated Decision assembly (``run_current_research_decision_
convergence_proof assemble``) four times over byte-copied retained inputs under the audit-hook
write guard: under the Financial V2 input-integrity checkpoint (baseline, 488eaf1), under the
unhardened fundamental-consumption checkpoint (prehardening, 66d0fc0), and twice under this
checkout (after, rerun). ``summarize`` derives the report from that work root alone: freshness
voting, the working-capital reclassification, earnings sign transitions, evidence availability
versus directional sufficiency, fundamental states and Current Research classes across the three
code states, every posture transition attributed to the exact current signal (or removed stale
vote) behind it, the valuation regression and the authority boundary. Rerunning ``summarize``
over the same work root reproduces the artifact identity. No provider, runtime store,
publication or pointer is touched.
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
import stocklookup_core.financial.fundamental_signal_consumption_contract as contract
import provider_financial_monetary_basis_verdict as verdict_pin
from tools import current_research_capability_map as capability
from tools import run_current_research_decision_convergence_proof as convergence
from tools import run_financial_v2_analysis_input_integrity_proof as integrity
from tools import run_integrated_fundamental_state_consumption_proof as consumption

CONTRACT = "fundamental_signal_policy_hardening_proof/v1"
SESSION = "2026-09-24"
BASELINE_COMMIT = consumption.BASELINE_COMMIT
PREHARDENING_COMMIT = "66d0fc0bdc494fe59c84e24266b1cb4dc6097dbb"
WORKSPACE = Path("C:/Projects/StockLookup")
EXPECTED_WORK_ROOT = WORKSPACE / "tmp" / "fundamental-policy-hardening-proof-work"
EXPECTED_OUTPUT_DIR = WORKSPACE / "operations-review" / "fundamental-signal-policy-hardening-v1-20260924"
CONSUMPTION_PROOF = consumption.EXPECTED_OUTPUT_DIR / "integrated_fundamental_state_consumption_reconciliation.json"
RUNS = ("baseline", "prehardening", "after", "rerun")
ATTEMPTED, OFFICIAL, PRICED = "ATTEMPTED_COHORT", "OFFICIAL_RESEARCH_SCOPE", "PRICED_OFFICIAL_SCOPE"
FAV, ADV = contract.FAVORABLE, contract.ADVERSE
STALE, CURRENT = "STALE_BUT_RESEARCH_USABLE", "CURRENT"
SIGN_TRANSITIONS = (contract.LOSS_TO_PROFIT, contract.PROFIT_TO_LOSS, contract.LOSS_NARROWED, contract.LOSS_WIDENED)
NI_FEATURES = ("net_income_qoq", "net_income_same_quarter_yoy", "net_income_ttm_yoy")
#: Producer states the earnings sign-transition correction may change (and nothing else).
ENGINE_CHANGED_STATES = frozenset({"earnings_turnaround_state", "growth_state"})
#: Lineage pointers to the (rebuilt) Financial V2 engine artifact: provenance, never a value.
ENGINE_LINEAGE_FIELDS = frozenset({"ttm_source_context_identity", "source_financial_v2_identity"})
DEFENSIVE_POSTURES = frozenset({"AVOID", "REDUCE"})


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(convergence.canonical(value) + b"\n")


def _counts(values: Iterable[Any]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def _transitions(pairs: Iterable[tuple[Any, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(f"{a} -> {b}" for a, b in pairs if a != b).items()))


def _roots(args: argparse.Namespace) -> tuple[Path, Path, Path, Path, Path]:
    roots = tuple(Path(value).resolve() for value in (args.producer_root, args.baseline_code_root,
                                                     args.prehardening_code_root, args.work_root, args.output_dir))
    if roots[3] != EXPECTED_WORK_ROOT.resolve() or roots[4] != EXPECTED_OUTPUT_DIR.resolve():
        raise SystemExit("PROOF_ROOTS_OUTSIDE_NAMED_TARGETS")
    return roots  # type: ignore[return-value]


def prove(args: argparse.Namespace) -> dict:
    producer_root, baseline_root, pre_root, work_root, _ = _roots(args)
    for root, commit, label in ((baseline_root, BASELINE_COMMIT, "BASELINE"), (pre_root, PREHARDENING_COMMIT, "PREHARDENING")):
        if convergence._git(root, "rev-parse", "HEAD") != commit:
            raise SystemExit(f"{label}_CODE_ROOT_NOT_AT_CHECKPOINT")
        if not all(integrity._pinned_authority_equal(root).values()):
            raise SystemExit(f"PINNED_FINANCIAL_V2_EVIDENCE_DIFFERS:{label}")
    evidence = integrity._evidence_paths(producer_root)
    before = integrity._hashes(evidence)
    for name, code_root in (("baseline", baseline_root), ("prehardening", pre_root), ("after", ROOT), ("rerun", ROOT)):
        convergence._run_assembly(code_root, producer_root, work_root / name, SESSION)
    if integrity._hashes(evidence) != before:
        raise SystemExit("RETAINED_EVIDENCE_SHA_CHANGED")
    _write(work_root / "retained_evidence_sha256.json", before)
    return summarize(args)


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dim(name: str) -> str:
    """66d0fc0 called the current-ratio / NWC dimension LIQUIDITY."""
    return "SHORT_TERM_LIQUIDITY" if name == "LIQUIDITY" else name


def _label(label: str) -> str:
    dimension, axis = label.split(".")
    return f"{_dim(dimension)}.{axis}"


def _votes(synthesis: Mapping[str, Any]) -> dict[str, str]:
    derivation = synthesis.get("derivation") or {}
    return {**{_label(label): FAV for label in derivation.get("favorable_votes") or []},
            **{_label(label): ADV for label in derivation.get("adverse_votes") or []}}


def _signals_at(synthesis: Mapping[str, Any] | None, label: str) -> list[Mapping[str, Any]]:
    dimension, axis = label.split(".")
    return [s for s in (synthesis or {}).get("signals") or [] if (_dim(s["dimension"]), s["axis"]) == (dimension, axis)]


def _is_bridge(record: Mapping[str, Any]) -> bool:
    return consumption._is_bridge(record)


def _cause(label: str, before: str | None, after: str | None, a_syn: Mapping[str, Any], *,
           b_syn: Mapping[str, Any] | None, legacy: bool, growth_changed: bool) -> dict[str, Any]:
    """Name the exact signal(s) behind one changed dimension vote (``after`` is always CURRENT)."""
    dimension, axis = label.split(".")
    a_sig, b_sig = _signals_at(a_syn, label), _signals_at(b_syn, label)
    value_after = ((a_syn.get("dimensions") or {}).get(dimension) or {}).get(axis.lower())
    voting = [s for s in a_sig if s["decision_eligible"]]
    stale = [s for s in a_sig if s.get("research_usable") and s["role"] == contract.DECISION and not s["decision_eligible"]]
    unavailable = [s for s in a_sig if s.get("exclusion") == "FINANCIAL_PERIOD_UNAVAILABLE_FOR_DECISION"]
    guard = [s for s in a_sig if str(s.get("exclusion") or "").startswith("CASH_CONVERSION")]
    # Only a CURRENT pre-hardening NWC vote is a working-capital cause; a stale one was a stale vote.
    prior_nwc = [s for s in b_sig if s["signal_id"] == "net_working_capital_direction" and s.get("decision_eligible")
                 and (s.get("fitness") or {}).get("freshness") in (CURRENT, contract.NOT_EVALUATED)]
    prior_stale = [s for s in b_sig if s.get("decision_eligible") and (s.get("fitness") or {}).get("freshness") == STALE]
    restored = [s for s in voting if s["producer_value"] not in consumption.LEGACY_READ_VALUES.get(s["producer_field"], set())]
    if value_after == contract.MIXED:
        category, signals = "CURRENT_WITHIN_DIMENSION_CONFLICT", voting
    elif prior_nwc and (dimension, axis) == ("SHORT_TERM_LIQUIDITY", contract.DIRECTION):
        category, signals = "NWC_AMOUNT_TRAJECTORY_EVIDENCE_ONLY", prior_nwc + voting
    elif after and any(s["value"] == contract.PROFIT_TO_LOSS for s in voting):
        category, signals = "CURRENT_PROFIT_TO_LOSS_TRANSITION", voting
    elif dimension == "GROWTH" and growth_changed:
        category, signals = "GROWTH_CONSENSUS_EXCLUDES_SIGN_TRANSITION", voting or a_sig
    elif before and after is None and (stale or prior_stale):
        category, signals = "STALE_VOTE_REMOVED", stale or prior_stale
    elif after and legacy and restored:
        category, signals = "CURRENT_SIGNAL_RESTORED", restored
    elif before and after is None and unavailable:
        category, signals = "FRESHNESS_GATE_UNAVAILABLE_PERIOD", unavailable
    elif guard:
        category, signals = "CASH_CONVERSION_SIGN_GUARD", guard
    elif after and voting:
        category, signals = "CURRENT_SIGNAL_VOTE", voting
    else:
        category, signals = "UNATTRIBUTED", a_sig
    return {"dimension": label, "category": category, "before": before, "after": after, "dimension_value_after": value_after,
            "signals": sorted({s["signal_id"] for s in signals}),
            "signal_detail": {s["signal_id"]: {"producer_value": s.get("producer_value"), "value": s.get("value"),
                                               "as_of_period": (s.get("fitness") or {}).get("as_of_period"),
                                               "freshness": (s.get("fitness") or {}).get("freshness"),
                                               "consumption_class": s.get("consumption_class")}
                              for s in sorted(signals, key=lambda s: s["signal_id"])}}


def _attribution(old_votes: Mapping[str, str], a_syn: Mapping[str, Any], *, b_syn: Mapping[str, Any] | None,
                 legacy: bool, growth_changed: bool) -> list[dict[str, Any]]:
    new_votes = _votes(a_syn)
    changed = sorted(label for label in set(old_votes) | set(new_votes) if old_votes.get(label) != new_votes.get(label))
    return [_cause(label, old_votes.get(label), new_votes.get(label), a_syn, b_syn=b_syn, legacy=legacy,
                   growth_changed=growth_changed) for label in changed]


def _final_vote_audit(synthesis: Mapping[str, Any]) -> dict[str, Any]:
    """Every signal behind a final vote, with its period and class (each must be CURRENT)."""
    used = [s for s in synthesis.get("signals") or [] if s.get("decision_eligible")]
    return {"signals": {s["signal_id"]: {"value": s["value"], "as_of_period": s["fitness"]["as_of_period"],
                                         "freshness": s["fitness"]["freshness"], "consumption_class": s["consumption_class"]}
                        for s in sorted(used, key=lambda s: s["signal_id"])},
            "all_current": all(s["fitness"]["freshness"] in (CURRENT, contract.NOT_EVALUATED)
                               and s["consumption_class"] in (contract.CURRENT_DECISION_VOTE, contract.TRANSITION_EVENT)
                               for s in used)}


def _strip_engine_lineage(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _strip_engine_lineage(item) for key, item in value.items() if key not in ENGINE_LINEAGE_FIELDS}
    if isinstance(value, list):
        return [_strip_engine_lineage(item) for item in value]
    return value


def _valuation_regression(base: Mapping[str, Any], after: Mapping[str, Any], b_iid: Mapping[str, Any],
                          a_iid: Mapping[str, Any], official: set[str], verdict: Mapping[str, Any]) -> dict[str, Any]:
    lineage_only: Counter[str] = Counter()
    value_diffs: Counter[str] = Counter()
    for ticker in sorted(set(base["records"]) | set(after["records"])):
        old, new = base["records"].get(ticker) or {}, after["records"].get(ticker) or {}
        if old == new:
            continue
        if _strip_engine_lineage(old) == _strip_engine_lineage(new):
            lineage_only["records"] += 1
            for method, entry in (new.get("methods") or {}).items():
                if entry != (old.get("methods") or {}).get(method):
                    lineage_only[f"methods.{method}"] += 1
            continue
        for key in sorted(set(old) | set(new)):
            if _strip_engine_lineage(old.get(key)) != _strip_engine_lineage(new.get(key)):
                value_diffs[key] += 1
    top_level = sorted(key for key in set(base) | set(after)
                       if key not in ("records", "artifact_identity", "artifact_sha256") and base.get(key) != after.get(key))
    pb = integrity._pb_regression(base, after, official, verdict)
    pb_values = {t: after["records"][t]["methods"][integrity.PB_METHOD] for t in after["records"]}
    iid_summary_diffs = sum(b_iid["records"][t]["valuation_context_summary"] != a_iid["records"][t]["valuation_context_summary"]
                            for t in a_iid["records"])
    iid_method_diffs = sum(_strip_engine_lineage(b_iid["records"][t]["valuation_methods"])
                           != _strip_engine_lineage(a_iid["records"][t]["valuation_methods"]) for t in a_iid["records"])
    unknown_scope_peer_ready = sum(
        ((after["records"][t].get("peer_relative") or {}).get(integrity.PB_METHOD) or {}).get("status") == "READY_RESEARCH_ONLY"
        for t, method in pb_values.items() if str(method.get("statement_scope")).lower() in ("unknown", "none"))
    methods_of_interest = {}
    for method in ("P/B_CURRENT_RESEARCH", "P/B", "market_cap", "P/E_TTM", "P/S_TTM"):
        methods_of_interest[method] = {
            "status_distribution_official": _counts((after["records"][t]["methods"].get(method) or {}).get("status") for t in sorted(official)),
            "value_differences": sum((base["records"][t]["methods"].get(method) or {}).get("value")
                                     != (after["records"][t]["methods"].get(method) or {}).get("value") for t in after["records"]),
            "field_differences_excluding_engine_lineage": sum(
                _strip_engine_lineage(base["records"][t]["methods"].get(method)) != _strip_engine_lineage(after["records"][t]["methods"].get(method))
                for t in after["records"])}
    return {
        "evaluated_valuation_identity": [base["artifact_identity"], after["artifact_identity"]],
        "identity_changed_only_by_engine_lineage": not value_diffs and set(top_level) <= ENGINE_LINEAGE_FIELDS,
        "top_level_differences": top_level,
        "records_differing_only_in_engine_lineage": dict(sorted(lineage_only.items())),
        "record_value_differences_excluding_engine_lineage": dict(sorted(value_diffs.items())),
        "methods": methods_of_interest,
        "p_b_current_research": {key: pb[key] for key in ("vci_balance_sheet_verdict", "usable_official", "usable_by_statement_scope",
                                                           "nci_limitation_on_every_usable_row", "equity_definition",
                                                           "research_only_limitations", "is_actionable", "exact_pb_status_transitions",
                                                           "peer_before", "peer_after", "relative_research_state_transitions_official")},
        "method_field_differences_excluding_engine_lineage": {method: fields for method, fields in pb["method_field_differences_baseline_to_after"].items()
                                         if set(fields) - ENGINE_LINEAGE_FIELDS},
        "market_cap_value_differences": pb["market_cap_value_differences"],
        "unknown_scope_peer_ready": unknown_scope_peer_ready,
        "integrated_valuation_context_summary_differences": iid_summary_diffs,
        "integrated_valuation_method_differences_excluding_engine_lineage": iid_method_diffs,
    }


def summarize(args: argparse.Namespace) -> dict:
    producer_root, baseline_root, pre_root, work_root, output_dir = _roots(args)
    runs = {name: integrity._load_run(work_root, name) for name in RUNS}
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
    prior = convergence.load(CONSUMPTION_PROOF)
    for name, recorded in (("baseline", "baseline"), ("prehardening", "after")):
        reproduced = {"integrated": runs[name]["iid"]["artifact_identity"],
                      "financial_analysis_product": runs[name]["compact"]["artifact_identity"],
                      "financial_engine": runs[name]["compact"]["source_context_identity"],
                      "evaluated_valuation": runs[name]["valuation"]["artifact_identity"]}
        if any(prior["identities"][recorded][key] != value for key, value in reproduced.items()):
            raise SystemExit(f"{name.upper()}_DOES_NOT_REPRODUCE_ITS_CHECKPOINT")
    ops = producer_root / "operations-review"
    tools = {"baseline": _module(baseline_root / "tools" / "current_research_capability_map.py", "baseline_capability_map"),
             "prehardening": _module(pre_root / "tools" / "current_research_capability_map.py", "prehardening_capability_map"),
             "after": capability, "rerun": capability}
    maps = {name: tools[name].build(ops, SESSION, {"integrated": runs[name]["iid_path"]}) for name in RUNS}
    if maps["after"]["artifact_identity"] != maps["rerun"]["artifact_identity"]:
        raise SystemExit("CAPABILITY_MAP_NOT_DETERMINISTIC")
    for name, recorded in (("baseline", "baseline"), ("prehardening", "after")):
        if maps[name]["artifact_identity"] != prior["identities"][recorded]["capability_map"]:
            raise SystemExit(f"{name.upper()}_CAPABILITY_MAP_DOES_NOT_REPRODUCE")
    rows = maps["after"]["records"]
    attempted = set(rows)
    official = {t for t, row in rows.items() if row["universe_status"] == OFFICIAL}
    priced = {t for t in official if rows[t]["research_market_cap_usable"]}
    if (len(attempted), len(official), len(priced)) != tuple(prior["denominators"][key] for key in (ATTEMPTED, OFFICIAL, PRICED)):
        raise SystemExit("DENOMINATORS_DO_NOT_RECONCILE")

    engine = fin_v2_material.build_engine_artifact(root=ROOT, requested_at=f"{SESSION}T15:00:00+07:00")
    if engine["artifact_identity"] != runs["after"]["compact"]["source_context_identity"]:
        raise SystemExit("AFTER_ENGINE_NOT_REPRODUCED")
    if runs["baseline"]["compact"]["source_context_identity"] != runs["prehardening"]["compact"]["source_context_identity"]:
        raise SystemExit("PRE_HARDENING_ENGINE_DIFFERS_FROM_BASELINE")
    compact = {name: runs[name]["compact"]["records"] for name in RUNS}
    state_changes = {field: sorted(t for t in attempted if compact["prehardening"][t].get(field) != compact["after"][t].get(field))
                     for field in consumption.PRODUCER_FIELDS}
    unexpected = {field: len(tickers) for field, tickers in state_changes.items() if tickers and field not in ENGINE_CHANGED_STATES}
    if unexpected:
        raise SystemExit(f"UNEXPECTED_PRODUCER_STATE_CHANGE:{unexpected}")
    growth_changed = set(state_changes["growth_state"])
    rec = {name: runs[name]["iid"]["records"] for name in RUNS}
    b, p, a = rec["baseline"], rec["prehardening"], rec["after"]
    fv2 = {t: contract.evaluate(compact["after"][t], decision_session=SESSION) for t in sorted(attempted)}

    legacy_reader = consumption._legacy_reader(baseline_root)
    operational = convergence.load(work_root / "baseline" / "outputs" / "operational_fundamental_context_integration.json")
    legacy_votes: dict[str, dict[str, str]] = {}
    for t in sorted(attempted):
        source = ((operational["records"].get(t) or {}).get("financial_context") if _is_bridge(b[t]) else compact["baseline"][t])
        read = legacy_reader(source)
        if read[0] != b[t]["fundamental_state"]:
            raise SystemExit(f"LEGACY_READER_DOES_NOT_REPRODUCE_BASELINE:{t}")
        legacy_votes[t] = {_label(label): polarity for label, polarity in consumption._legacy_votes(read[1], read[2]).items()}

    syn = {name: {t: rec[name][t]["fundamental_synthesis"] for t in attempted} for name in ("prehardening", "after")}

    # ── Attribution: baseline -> final and pre-hardening -> final ────────────────────────────
    def attribute_changed(old: str) -> dict[str, dict[str, Any]]:
        out = {}
        for t in sorted(attempted):
            if rec[old][t]["fundamental_state"] == a[t]["fundamental_state"] and rec[old][t]["research_action_posture"] == a[t]["research_action_posture"]:
                continue
            votes = legacy_votes[t] if old == "baseline" else _votes(syn["prehardening"][t])
            causes = _attribution(votes, syn["after"][t], b_syn=syn["prehardening"][t] if old == "prehardening" else None,
                                  legacy=old == "baseline", growth_changed=t in growth_changed)
            flags = []
            if _is_bridge(rec[old][t]) != _is_bridge(a[t]):
                flags.append("OPERATIONAL_BRIDGE_APPLICATION_CHANGED")
            out[t] = {"fundamental_state": [rec[old][t]["fundamental_state"], a[t]["fundamental_state"]],
                      "votes_before": dict(sorted(votes.items())), "votes_after": dict(sorted(_votes(syn["after"][t]).items())),
                      "causes": causes, "flags": flags}
        return out

    fundamental_attribution = {"baseline": attribute_changed("baseline"), "prehardening": attribute_changed("prehardening")}

    def posture_view(old: str) -> dict[str, Any]:
        items = []
        for t in sorted(official):
            if rec[old][t]["research_action_posture"] == a[t]["research_action_posture"]:
                continue
            entry = fundamental_attribution[old].get(t) or {}
            causes = entry.get("causes") or []
            audit = _final_vote_audit(syn["after"][t])
            flags = list(entry.get("flags") or [])
            if a[t]["research_action_posture"] == "INSUFFICIENT_CURRENT_RESEARCH":
                flags.append("NO_CURRENT_TECHNICAL_AND_NO_CURRENT_FUNDAMENTAL_DIRECTION")
            stale_adverse = any(c["category"] == "STALE_VOTE_REMOVED" and c["before"] == ADV for c in causes)
            if stale_adverse:
                flags.append("STALE_ADVERSE_VOTE_REMOVED")
            if (rec[old][t]["research_action_posture"] in DEFENSIVE_POSTURES and a[t]["research_action_posture"] not in DEFENSIVE_POSTURES
                    and stale_adverse):
                flags.append("LEFT_DEFENSIVE_POSTURE_AFTER_STALE_ADVERSE_VOTE_REMOVED")
            if (a[t]["research_action_posture"] in DEFENSIVE_POSTURES and rec[old][t]["research_action_posture"] not in DEFENSIVE_POSTURES):
                flags.append("ENTERED_DEFENSIVE_POSTURE")
            dinput = a[t].get("current_research_decision_input") or {}
            items.append({
                "ticker": t, "posture": [rec[old][t]["research_action_posture"], a[t]["research_action_posture"]],
                "fundamental_state": {"baseline": b[t]["fundamental_state"], "prehardening": p[t]["fundamental_state"],
                                      "final": a[t]["fundamental_state"]},
                "tactical_phase": a[t]["tactical_phase"], "market_structure_state": a[t]["market_structure_state"],
                "why_now": [rec[old][t].get("why_now"), a[t].get("why_now")],
                "cause_categories": sorted({c["category"] for c in causes}),
                "causes": causes,
                "final_votes": audit["signals"], "final_votes_all_current": audit["all_current"],
                "evidence_class": dinput.get("evidence_class"),
                "action_posture_gated_by_current_evidence": (dinput.get("synthesis") or {}).get("action_posture_gated_by_current_evidence"),
                "flags": sorted(flags)})
        unexplained = [item["ticker"] for item in items if item["fundamental_state"][old] == item["fundamental_state"]["final"]
                       and "OPERATIONAL_BRIDGE_APPLICATION_CHANGED" not in item["flags"]]
        unattributed = [item["ticker"] for item in items if "UNATTRIBUTED" in item["cause_categories"] or not item["causes"]]
        not_current = [item["ticker"] for item in items if not item["final_votes_all_current"]]
        category_counts = Counter(category for item in items for category in item["cause_categories"])
        signal_counts = Counter(f"{cause['category']}:{signal}:{cause['after'] or 'NO_VOTE'}" for item in items
                                for cause in item["causes"] for signal in cause["signals"])
        primary = Counter(_primary(item) for item in items)
        return {"count_official": len(items),
                "transitions": _transitions((item["posture"][0], item["posture"][1]) for item in items),
                "by_cause_category": dict(sorted(category_counts.items())),
                "by_cause_signal": dict(sorted(signal_counts.items())),
                "by_primary_driver": dict(sorted(primary.items())),
                "flags": _counts(flag for item in items for flag in item["flags"]),
                "per_ticker": items, "unexplained": unexplained, "unattributed": unattributed,
                "final_votes_not_current": not_current}

    posture = {"baseline_to_final": posture_view("baseline"), "prehardening_to_final": posture_view("prehardening")}
    for view in posture.values():
        if view["unexplained"] or view["unattributed"] or view["final_votes_not_current"]:
            raise SystemExit(f"POSTURE_TRANSITION_ATTRIBUTION_INCOMPLETE:{view['unexplained'] + view['unattributed'] + view['final_votes_not_current']}")
    pre_transitions = {t: [b[t]["research_action_posture"], p[t]["research_action_posture"]] for t in sorted(official)
                       if b[t]["research_action_posture"] != p[t]["research_action_posture"]}
    final_transitions = {item["ticker"] for item in posture["baseline_to_final"]["per_ticker"]}
    disappeared = []
    for t, pair in pre_transitions.items():
        if t in final_transitions and a[t]["research_action_posture"] == pair[1]:
            continue
        causes = (fundamental_attribution["prehardening"].get(t) or {}).get("causes") or []
        disappeared.append({"ticker": t, "posture_baseline_prehardening_final": [pair[0], pair[1], a[t]["research_action_posture"]],
                            "fundamental_state_baseline_prehardening_final": [b[t]["fundamental_state"], p[t]["fundamental_state"], a[t]["fundamental_state"]],
                            "reverted_to_baseline": a[t]["research_action_posture"] == pair[0],
                            "cause_categories": sorted({c["category"] for c in causes}), "causes": causes})
    persisted = sorted(t for t, pair in pre_transitions.items() if a[t]["research_action_posture"] == pair[1])

    # ── Freshness voting ─────────────────────────────────────────────────────────────────────
    def freshness_view(tickers: Iterable[str]) -> dict[str, Any]:
        totals: Counter[str] = Counter()
        per_signal: dict[str, Counter] = defaultdict(Counter)
        for t in tickers:
            totals.update(syn["after"][t].get("signal_freshness_voting") or {})
            for s in syn["after"][t]["signals"]:
                if s["role"] != contract.DECISION or s["applicability"] == contract.NON_APPLICABLE:
                    continue
                bucket = ("CURRENT_VOTING" if s["decision_eligible"] else "STALE_RESEARCH_ONLY" if s["research_usable"]
                          else "UNAVAILABLE_EXCLUDED" if s.get("exclusion") == "FINANCIAL_PERIOD_UNAVAILABLE_FOR_DECISION" else None)
                if bucket:
                    per_signal[s["signal_id"]][bucket] += 1
        return {"signals": dict(sorted(totals.items())),
                "per_signal": {key: dict(sorted(value.items())) for key, value in sorted(per_signal.items())},
                "records_with_stale_research_evidence": sum(bool(syn["after"][t].get("stale_research_evidence")) for t in tickers),
                "records_with_only_stale_evidence": sum(
                    (syn["after"][t].get("evidence_availability") or {}).get("state") == contract.AVAILABLE
                    and not (syn["after"][t]["evidence_availability"].get("current_signals")) for t in tickers)}

    prehardening_freshness: Counter[str] = Counter()
    for t in official:
        prehardening_freshness.update(syn["prehardening"][t].get("decision_signal_freshness") or {})
    freshness = {"denominator": OFFICIAL, "final": freshness_view(sorted(official)),
                 "prehardening_decision_signal_freshness": dict(sorted(prehardening_freshness.items())),
                 "prehardening_records_with_stale_votes": sum(bool((syn["prehardening"][t].get("derivation") or {}).get("stale_votes"))
                                                              for t in official),
                 "fundamental_dimension_freshness_final": _counts(
                     ((a[t]["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"].get("freshness") or {}).get("freshness_status"))
                     for t in sorted(official))}

    # ── Working-capital reclassification (pre-hardening -> final) ───────────────────────────
    def sig(synthesis: Mapping[str, Any], signal_id: str) -> Mapping[str, Any]:
        return next((s for s in synthesis.get("signals") or [] if s["signal_id"] == signal_id), {})

    def liquidity(name: str) -> dict[str, Any]:
        label = "LIQUIDITY" if name == "prehardening" else "SHORT_TERM_LIQUIDITY"
        votes = Counter()
        conflicts = 0
        for t in official:
            derivation = syn[name][t].get("derivation") or {}
            votes.update(f"{FAV}" for v in derivation.get("favorable_votes") or [] if v == f"{label}.DIRECTION")
            votes.update(f"{ADV}" for v in derivation.get("adverse_votes") or [] if v == f"{label}.DIRECTION")
            conflicts += "DIRECTION" in ((syn[name][t].get("dimensions") or {}).get(label) or {}).get("conflicting_axes", [])
        return {"dimension": label, "votes": dict(sorted(votes.items())), "within_dimension_conflicts": conflicts,
                "net_working_capital_direction_voting": sum(bool(sig(syn[name][t], "net_working_capital_direction").get("decision_eligible")) for t in official),
                "current_ratio_direction_voting": sum(bool(sig(syn[name][t], "current_ratio_direction").get("decision_eligible")) for t in official),
                "current_ratio_direction_voting_freshness": _counts(
                    sig(syn[name][t], "current_ratio_direction")["fitness"]["freshness"] for t in official
                    if sig(syn[name][t], "current_ratio_direction").get("decision_eligible"))}

    divergence = Counter()
    for t in official:
        nwc, ratio = sig(syn["after"][t], "net_working_capital_direction"), sig(syn["after"][t], "current_ratio_direction")
        if nwc.get("research_usable") and ratio.get("research_usable"):
            divergence[f"{nwc['value']}+{ratio['value']}"] += 1
    wc_tickers = sorted(t for t, entry in fundamental_attribution["prehardening"].items() if t in official
                        and any(c["category"] == "NWC_AMOUNT_TRAJECTORY_EVIDENCE_ONLY" for c in entry["causes"]))
    changes_pre = integrity._decision_changes(runs["prehardening"]["iid"], runs["after"]["iid"], official)
    changes_wc = integrity._decision_changes(runs["prehardening"]["iid"], runs["after"]["iid"], wc_tickers)
    working_capital = {
        "prehardening": liquidity("prehardening"), "final": liquidity("after"),
        "net_working_capital_evidence_only_final": sum(sig(syn["after"][t], "net_working_capital_direction").get("consumption_class")
                                                        == contract.RESEARCH_EVIDENCE_ONLY for t in official),
        "amount_and_ratio_combinations_final": dict(sorted(divergence.items())),
        "records_changed_by_nwc_reclassification": len(wc_tickers),
        "fundamental_state_transitions": changes_wc["fundamental_state_transitions"],
        "evidence_axis_coherence_transitions": changes_wc["evidence_axis_coherence_transitions"],
        "counter_thesis": {"changed": changes_wc["counter_thesis_changed"], "gained": changes_wc["counter_thesis_tags_gained"],
                           "lost": changes_wc["counter_thesis_tags_lost"]},
        "posture_transitions": changes_wc["research_action_posture"]["transitions"],
        "counter_thesis_all_official_prehardening_to_final": {"gained": changes_pre["counter_thesis_tags_gained"],
                                                              "lost": changes_pre["counter_thesis_tags_lost"]},
    }

    # ── Sign transitions ─────────────────────────────────────────────────────────────────────
    def producer_transitions(name: str) -> dict[str, dict[str, int]]:
        return {feature: _counts(((compact[name][t].get("feature_fitness") or {}).get(feature) or {}).get("semantic_transition")
                                 for t in sorted(official)
                                 if ((compact[name][t].get("feature_fitness") or {}).get(feature) or {}).get("semantic_transition"))
                for feature in NI_FEATURES}

    def consumed(name: str) -> dict[str, Any]:
        rows = [s for t in official for s in syn[name][t]["signals"] if s["axis"] == contract.TRANSITION]
        by_value = {value: {"current_voting": sum(s["value"] == value and s["decision_eligible"] and s["fitness"]["freshness"] != STALE
                                                  for s in rows),
                            "stale_voting": sum(s["value"] == value and s["decision_eligible"] and s["fitness"]["freshness"] == STALE
                                                for s in rows),
                            "stale_research_only": sum(s["value"] == value and not s["decision_eligible"]
                                                       and s["fitness"]["freshness"] == STALE for s in rows)}
                    for value in SIGN_TRANSITIONS}
        return {"by_value": by_value,
                "by_value_basis_freshness": _counts(f"{s['value']}|{s['fitness']['basis']}|{s['fitness']['freshness']}" for s in rows),
                "turnaround_triggered": sum(bool(syn[name][t]["derivation"]["turnaround"]["triggered"]) for t in official)}

    transitions = {
        "producer_feature_transitions": {"prehardening": producer_transitions("prehardening"), "final": producer_transitions("after")},
        "producer_earnings_turnaround_state": {"prehardening": _counts(compact["prehardening"][t].get("earnings_turnaround_state") for t in sorted(official)),
                                               "final": _counts(compact["after"][t].get("earnings_turnaround_state") for t in sorted(official))},
        "consumed_signal": {"prehardening": consumed("prehardening"), "final": consumed("after")},
        "producer_state_changes_attempted": {field: len(tickers) for field, tickers in state_changes.items() if tickers},
        "growth_state_transitions_official": _transitions((compact["prehardening"][t].get("growth_state"), compact["after"][t].get("growth_state"))
                                                           for t in sorted(official)),
    }

    # ── Evidence availability versus directional sufficiency ─────────────────────────────────
    insufficient_with_evidence = sorted(t for t in official if a[t]["fundamental_state"] == contract.FUNDAMENTAL_INSUFFICIENT
                                        and (syn["after"][t].get("evidence_availability") or {}).get("state") == contract.AVAILABLE)
    lost = [t for t in insufficient_with_evidence
            if a[t]["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["state"] != "AVAILABLE"
            or rows[t]["fundamental_fitness"] != "INTEGRATED_RESEARCH_USABLE"]
    if lost:
        raise SystemExit(f"QUALIFIED_EVIDENCE_DROPPED_FROM_FUNDAMENTAL_RESEARCH:{lost[:20]}")

    def blocker_count(records: Mapping[str, Any], code: str) -> int:
        return sum(code in ((records[t].get("evidence_axes") or {}).get("FUNDAMENTAL") or {}).get("blocker_reason_codes", []) for t in official)

    evidence = {
        "directional_insufficient_with_qualified_evidence": len(insufficient_with_evidence),
        "by_evidence_polarity": _counts(syn["after"][t]["evidence_availability"]["polarity"] for t in insufficient_with_evidence),
        "by_evidence_currency": _counts("CURRENT_EVIDENCE_WITHOUT_DIRECTION" if syn["after"][t]["evidence_availability"]["current_signals"]
                                        else "STALE_EVIDENCE_ONLY" for t in insufficient_with_evidence),
        "with_weaknesses": sum(bool(syn["after"][t]["weaknesses"]) for t in insufficient_with_evidence),
        "with_strengths": sum(bool(syn["after"][t]["strengths"]) for t in insufficient_with_evidence),
        "decision_input_fundamental_available": sum(a[t]["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["state"] == "AVAILABLE"
                                                    for t in insufficient_with_evidence),
        "capability_map_integrated_fundamental": sum(rows[t]["fundamental_fitness"] == "INTEGRATED_RESEARCH_USABLE" for t in insufficient_with_evidence),
        "evidence_availability_final": _counts(f"{syn['after'][t]['evidence_availability']['state']}:"
                                               f"{syn['after'][t]['evidence_availability']['directional_sufficiency']}" for t in sorted(official)),
        "fundamental_context_absent_blocker": {name: blocker_count(rec[name], "FUNDAMENTAL_CONTEXT_ABSENT") for name in ("baseline", "prehardening", "after")},
        "current_direction_insufficient_blocker_final": blocker_count(a, "FUNDAMENTAL_CURRENT_DIRECTION_INSUFFICIENT"),
        "evidence_class": {name: _counts((rec[name][t].get("current_research_decision_input") or {}).get("evidence_class") for t in sorted(official))
                           for name in ("baseline", "prehardening", "after")},
        "evidence_class_transitions": {
            "baseline_to_prehardening": _transitions((b[t]["current_research_decision_input"]["evidence_class"], p[t]["current_research_decision_input"]["evidence_class"]) for t in sorted(official)),
            "baseline_to_final": _transitions((b[t]["current_research_decision_input"]["evidence_class"], a[t]["current_research_decision_input"]["evidence_class"]) for t in sorted(official)),
            "prehardening_to_final": _transitions((p[t]["current_research_decision_input"]["evidence_class"], a[t]["current_research_decision_input"]["evidence_class"]) for t in sorted(official))},
        "evidence_class_priced": {name: _counts((rec[name][t].get("current_research_decision_input") or {}).get("evidence_class") for t in sorted(priced))
                                  for name in ("baseline", "prehardening", "after")},
        "decision_readiness_v1": {name: maps[name]["decision_readiness"] for name in ("baseline", "prehardening", "after")},
        "action_posture_gated_by_current_evidence": {name: sum(bool(((rec[name][t].get("current_research_decision_input") or {}).get("synthesis") or {})
                                                                    .get("action_posture_gated_by_current_evidence")) for t in official)
                                                     for name in ("baseline", "prehardening", "after")},
    }

    # ── States, downstream and representative checks ─────────────────────────────────────────
    states = {name: _counts(rec[name][t]["fundamental_state"] for t in sorted(official)) for name in ("baseline", "prehardening", "after")}
    state_transitions = {
        "baseline_to_prehardening": _transitions((b[t]["fundamental_state"], p[t]["fundamental_state"]) for t in sorted(official)),
        "baseline_to_final": _transitions((b[t]["fundamental_state"], a[t]["fundamental_state"]) for t in sorted(official)),
        "prehardening_to_final": _transitions((p[t]["fundamental_state"], a[t]["fundamental_state"]) for t in sorted(official))}
    cause_rollup = {old: _counts(c["category"] for t, entry in fundamental_attribution[old].items() if t in official for c in entry["causes"])
                    for old in ("baseline", "prehardening")}
    downstream = {"baseline_to_final": integrity._decision_changes(runs["baseline"]["iid"], runs["after"]["iid"], official),
                  "prehardening_to_final": changes_pre}
    for view in downstream.values():
        view["research_action_posture"].pop("attribution", None)  # attributed above, per ticker

    verdict = verdict_pin.resolve(ROOT)
    valuation = _valuation_regression(runs["baseline"]["valuation"], runs["after"]["valuation"], runs["baseline"]["iid"],
                                      runs["after"]["iid"], official, verdict)
    if (not valuation["identity_changed_only_by_engine_lineage"] or valuation["method_field_differences_excluding_engine_lineage"]
            or valuation["market_cap_value_differences"] or valuation["unknown_scope_peer_ready"]
            or valuation["integrated_valuation_context_summary_differences"]
            or valuation["integrated_valuation_method_differences_excluding_engine_lineage"]
            or any(entry["field_differences_excluding_engine_lineage"] for entry in valuation["methods"].values())):
        raise SystemExit("VALUATION_REGRESSION")

    applicability = {}
    for issuer in ("bank", "securities"):
        pool = sorted(t for t in official if compact["after"][t].get("issuer_type") == issuer)
        corporate_votes = sum(1 for t in pool for s in fv2[t]["signals"]
                              if s["decision_eligible"] and contract.SIGNALS[s["signal_id"]]["family"] in ("CORPORATE",))
        applicability[issuer] = {"official_records": len(pool), "corporate_signal_votes": corporate_votes,
                                 "non_applicable_corporate_signals": sum(len(fv2[t]["non_applicable"]) for t in pool),
                                 "decided_by": _counts(a[t]["fundamental_synthesis"].get("source_dialect") for t in pool)}
        if corporate_votes:
            raise SystemExit(f"CORPORATE_SIGNAL_VOTED_FOR_{issuer.upper()}")
    samples = _samples(a, syn["after"], compact["after"], official)

    result: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT, "session": SESSION,
        "milestone": "FUNDAMENTAL_SIGNAL_POLICY_HARDENING_V1",
        "predecessor": {"checkpoint": PREHARDENING_COMMIT, "milestone": "INTEGRATED_FUNDAMENTAL_STATE_CONSUMPTION_RECONCILIATION_V1",
                        "proof_identity": prior["artifact_identity"]},
        "baseline_identity": {
            "baseline_commit": BASELINE_COMMIT, "prehardening_commit": PREHARDENING_COMMIT,
            "after_code_head": runs["after"]["assembly"]["code_head"],
            "after_code_tracked_changes": runs["after"]["assembly"]["code_tracked_changes"],
            "staged_session_inputs": runs["after"]["assembly"]["staged_session_inputs"],
            "retained_evidence_sha256": convergence.load(work_root / "retained_evidence_sha256.json"),
            "baseline_and_prehardening_reproduce_their_checkpoint_proofs": True,
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
        "hardened_signal_policy": {
            "contract_version": contract.CONTRACT_VERSION, "signal_policy": contract.SIGNAL_POLICY,
            "vote_eligibility": contract.VOTE_ELIGIBILITY_RULE, "evidence_availability_rule": contract.EVIDENCE_AVAILABILITY_RULE,
            "derivation_rule_unchanged": contract.DERIVATION_RULE,
            "policy_classes": list(contract.POLICY_CLASSES),
            "state_policy_table": contract.policy_table(),
            "unclassified_levels": contract.UNCLASSIFIED_LEVELS,
        },
        "freshness_voting": freshness,
        "working_capital_reclassification": working_capital,
        "sign_transitions": transitions,
        "evidence_vs_directional_sufficiency": evidence,
        "fundamental_state": {"distribution": states, "transitions": state_transitions,
                              "cause_categories": cause_rollup,
                              "changed_official": {old: sum(t in official for t in fundamental_attribution[old]) for old in ("baseline", "prehardening")}},
        "downstream": downstream,
        "posture_transitions": {**posture,
                                "baseline_to_prehardening": {"count_official": len(pre_transitions),
                                                             "transitions": _transitions(tuple(pair) for pair in pre_transitions.values())},
                                "prehardening_transitions_disappeared": disappeared,
                                "prehardening_transitions_persisted": persisted},
        "fundamental_attribution": {old: {t: entry for t, entry in fundamental_attribution[old].items() if t in official}
                                    for old in ("baseline", "prehardening")},
        "valuation_regression": valuation,
        "entity_applicability": applicability,
        "representative_checks": samples,
        "authority_boundary": {"current_research_only": True, "provider_or_data_authority_promoted": False,
                               "pinned_financial_v2_authority_changed": False, "financial_v2_engine_changed": True,
                               "financial_v2_engine_change": "earnings sign-transition classification only (PROFIT_TO_LOSS; TTM loss narrowed/widened)",
                               "posture_thresholds_or_branch_order_changed": False, "exact_valuation_authority": False,
                               "historical_pit_financial_authority": False, "execution_or_sizing_authority": False,
                               "entity_authority_expanded": False, "provider_calls": 0, "financial_data_acquired": False,
                               "vnstock_enabled": False, "publication": "NONE"},
    }
    result["artifact_sha256"] = hashlib.sha256(convergence.canonical(result)).hexdigest()
    result["artifact_identity"] = f"{CONTRACT}:{result['artifact_sha256']}"
    output_dir.mkdir(parents=True, exist_ok=True)
    _write(output_dir / "fundamental_signal_policy_hardening.json", result)
    (output_dir / "SUMMARY.md").write_text(_summary(result), encoding="utf-8")
    return result


_PRIMARY_ORDER = ("STALE_VOTE_REMOVED", "NWC_AMOUNT_TRAJECTORY_EVIDENCE_ONLY", "CURRENT_PROFIT_TO_LOSS_TRANSITION",
                  "GROWTH_CONSENSUS_EXCLUDES_SIGN_TRANSITION", "CURRENT_SIGNAL_RESTORED", "CURRENT_WITHIN_DIMENSION_CONFLICT",
                  "FRESHNESS_GATE_UNAVAILABLE_PERIOD", "CASH_CONVERSION_SIGN_GUARD", "CURRENT_SIGNAL_VOTE")


def _primary(item: Mapping[str, Any]) -> str:
    """A single headline driver per posture transition (the full cause list stays on the item)."""
    categories = item["cause_categories"]
    if "NO_CURRENT_TECHNICAL_AND_NO_CURRENT_FUNDAMENTAL_DIRECTION" in item["flags"]:
        return "STALE_VOTE_REMOVED->INSUFFICIENT_CURRENT_RESEARCH"
    return next((category for category in _PRIMARY_ORDER if category in categories), "OPERATIONAL_BRIDGE_APPLICATION_CHANGED")


def _samples(records: Mapping[str, Any], syntheses: Mapping[str, Any], compact: Mapping[str, Any], official: set[str]) -> dict[str, Any]:
    """Representative entities chosen by generic, deterministic rules (never a ticker list)."""
    corp = sorted(t for t in official if compact[t].get("analysis_family") == "INDUSTRIAL_FINANCIAL_ANALYSIS"
                  and syntheses[t].get("source_dialect") == contract.DIALECT_FINANCIAL_V2)

    def signal(t: str, signal_id: str) -> Mapping[str, Any]:
        return next((s for s in syntheses[t]["signals"] if s["signal_id"] == signal_id), {})

    def pick(candidates: list[str], key) -> str | None:
        return max(candidates, key=lambda t: (key(t), t)) if candidates else None

    def view(t: str, rule: str) -> dict[str, Any]:
        s = syntheses[t]
        return {"ticker": t, "selection_rule": rule, "fundamental_state": records[t]["fundamental_state"],
                "research_action_posture": records[t]["research_action_posture"],
                "evidence_availability": s["evidence_availability"], "dimensions": s["dimensions"],
                "strengths": s["strengths"], "weaknesses": s["weaknesses"], "improving": s["improving"],
                "deteriorating": s["deteriorating"], "stale_research_evidence": s["stale_research_evidence"],
                "consumption_classes": s["consumption_classes"]}

    out: dict[str, Any] = {}
    checks: dict[str, bool] = {}
    oldest = pick([t for t in corp if syntheses[t]["stale_research_evidence"]],
                  lambda t: max((s["fitness"]["completed_quarter_lag"] or 0) for s in syntheses[t]["signals"] if s.get("research_usable")))
    if oldest:
        out["oldest_stale_research_evidence"] = view(oldest, "official corporate with stale research evidence; oldest period")
        checks["stale_evidence_visible_never_votes"] = all(
            not s["decision_eligible"] for s in syntheses[oldest]["signals"]
            if s["signal_id"] in syntheses[oldest]["stale_research_evidence"])
    lev = [t for t in corp if signal(t, "debt_to_equity_direction").get("decision_eligible") and signal(t, "debt_to_equity_direction")["value"] == contract.IMPROVING]
    if lev:
        t = lev[0] if "TH1" not in lev else "TH1"
        out["improving_leverage_direction_without_level"] = view(t, "official corporate; current D/E direction IMPROVING (TH1 when present)")
        checks["leverage_direction_never_a_level"] = syntheses[t]["dimensions"]["CAPITAL_STRUCTURE"]["level"] == contract.UNAVAILABLE
    p2l = [t for t in corp if signal(t, "earnings_transition").get("value") == contract.PROFIT_TO_LOSS and signal(t, "earnings_transition").get("decision_eligible")]
    if p2l:
        out["current_profit_to_loss"] = view(p2l[0], "first official corporate with a CURRENT PROFIT_TO_LOSS transition")
        checks["profit_to_loss_is_adverse_transition"] = syntheses[p2l[0]]["dimensions"]["PROFITABILITY"].get("transition") in (contract.PROFIT_TO_LOSS, contract.MIXED)
    div = [t for t in corp if signal(t, "net_working_capital_direction").get("value") == contract.RISING
           and signal(t, "current_ratio_direction").get("value") == contract.WORSENING and signal(t, "current_ratio_direction").get("decision_eligible")]
    if div:
        out["nwc_amount_rising_current_ratio_worsening"] = view(div[0], "first official corporate: NWC amount RISING while current ratio WORSENING")
        checks["nwc_amount_never_cancels_ratio"] = syntheses[div[0]]["dimensions"]["SHORT_TERM_LIQUIDITY"]["direction"] == contract.WORSENING
    adverse = [t for t in corp if records[t]["fundamental_state"] == contract.FUNDAMENTAL_INSUFFICIENT
               and syntheses[t]["evidence_availability"]["polarity"] == contract.ADVERSE]
    if adverse:
        out["directionally_insufficient_adverse_evidence"] = view(adverse[0], "first official corporate: direction INSUFFICIENT, evidence ADVERSE")
        checks["adverse_evidence_kept_in_research"] = (
            records[adverse[0]]["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["state"] == "AVAILABLE")
    return {"samples": out, "semantic_checks": checks}


def _summary(result: Mapping[str, Any]) -> str:
    d = result["denominators"]
    fresh = result["freshness_voting"]
    wc = result["working_capital_reclassification"]
    tr = result["sign_transitions"]
    ev = result["evidence_vs_directional_sufficiency"]
    fs = result["fundamental_state"]
    pt = result["posture_transitions"]
    val = result["valuation_regression"]
    lines = ["# Fundamental signal policy hardening (retained 2026-09-24)", "",
             f"Proof: `{result['artifact_identity']}`",
             f"Baseline `{BASELINE_COMMIT[:7]}` and pre-hardening `{PREHARDENING_COMMIT[:7]}` each reproduce their checkpoint proof.",
             f"Denominators: attempted {d[ATTEMPTED]}; official {d[OFFICIAL]}; priced official {d[PRICED]}.", "",
             "## Freshness voting (official, vote-capable signals)", "",
             f"- final: {fresh['final']['signals']}",
             f"- pre-hardening decision-signal freshness: {fresh['prehardening_decision_signal_freshness']} "
             f"(records with stale votes {fresh['prehardening_records_with_stale_votes']})",
             f"- records with stale research evidence {fresh['final']['records_with_stale_research_evidence']}; "
             f"with only stale evidence {fresh['final']['records_with_only_stale_evidence']}", "",
             "## Working-capital reclassification (pre-hardening -> final)", "",
             f"- pre-hardening: {wc['prehardening']}", f"- final: {wc['final']}",
             f"- NWC amount evidence-only (final): {wc['net_working_capital_evidence_only_final']}; amount+ratio combinations "
             f"{wc['amount_and_ratio_combinations_final']}",
             f"- records changed by the reclassification: {wc['records_changed_by_nwc_reclassification']}; states {wc['fundamental_state_transitions']}",
             f"- coherence {wc['evidence_axis_coherence_transitions']}; counter-thesis {wc['counter_thesis']}; posture {wc['posture_transitions']}", "",
             "## Sign transitions (official)", "",
             f"- producer features pre-hardening: {tr['producer_feature_transitions']['prehardening']}",
             f"- producer features final: {tr['producer_feature_transitions']['final']}",
             f"- consumed final: {tr['consumed_signal']['final']['by_value']}",
             f"- consumed pre-hardening: {tr['consumed_signal']['prehardening']['by_value']}",
             f"- growth_state (official): {tr['growth_state_transitions_official']}", "",
             "## Evidence availability versus directional sufficiency (official)", "",
             f"- directionally INSUFFICIENT with qualified evidence: {ev['directional_insufficient_with_qualified_evidence']} "
             f"(polarity {ev['by_evidence_polarity']}; {ev['by_evidence_currency']}); all kept in the decision input "
             f"({ev['decision_input_fundamental_available']}) and capability map ({ev['capability_map_integrated_fundamental']})",
             f"- FUNDAMENTAL_CONTEXT_ABSENT blocker: {ev['fundamental_context_absent_blocker']}; current-direction-insufficient blocker "
             f"(final) {ev['current_direction_insufficient_blocker_final']}",
             f"- evidence class: {ev['evidence_class']}", f"- evidence class transitions: {ev['evidence_class_transitions']}",
             f"- decision readiness v1: {ev['decision_readiness_v1']}", "",
             "## Fundamental state (official)", "",
             f"- 488eaf1 baseline: {fs['distribution']['baseline']}", f"- 66d0fc0 pre-hardening: {fs['distribution']['prehardening']}",
             f"- final: {fs['distribution']['after']}", f"- causes vs baseline: {fs['cause_categories']['baseline']}",
             f"- causes vs pre-hardening: {fs['cause_categories']['prehardening']}", "",
             "## Research action posture (official)", "",
             f"- 488eaf1 -> 66d0fc0: {pt['baseline_to_prehardening']['count_official']} {pt['baseline_to_prehardening']['transitions']}",
             f"- 488eaf1 -> final: {pt['baseline_to_final']['count_official']} {pt['baseline_to_final']['transitions']}",
             f"- primary drivers (488eaf1 -> final): {pt['baseline_to_final']['by_primary_driver']}",
             f"- cause signals (488eaf1 -> final): {pt['baseline_to_final']['by_cause_signal']}",
             f"- flags: {pt['baseline_to_final']['flags']}",
             f"- 66d0fc0 -> final: {pt['prehardening_to_final']['count_official']} {pt['prehardening_to_final']['transitions']}",
             f"- 66d0fc0 transitions that disappeared: {len(pt['prehardening_transitions_disappeared'])}; persisted "
             f"{len(pt['prehardening_transitions_persisted'])}",
             "- unexplained / unattributed / non-current final votes: none", "",
             "## Valuation regression", "",
             f"- evaluated valuation identity changed only by engine lineage: {val['identity_changed_only_by_engine_lineage']} "
             f"({val['records_differing_only_in_engine_lineage']})",
             f"- P/B usable {val['p_b_current_research']['usable_official']}; NCI on every row {val['p_b_current_research']['nci_limitation_on_every_usable_row']}; "
             f"verdict {val['p_b_current_research']['vci_balance_sheet_verdict']}; unknown-scope peer-ready {val['unknown_scope_peer_ready']}",
             f"- methods: {val['methods']}", "",
             "## Entity applicability", "", f"- {result['entity_applicability']}", "",
             "## Representative checks", "", f"- {result['representative_checks']['semantic_checks']}", "",
             "## Authority", "", f"- {result['authority_boundary']}", "",
             "Retained evidence SHA-256 unchanged; zero provider calls, network audit events, runtime-store reads and write-guard violations.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prove", "summarize"):
        one = sub.add_parser(name)
        one.add_argument("--producer-root", required=True)
        one.add_argument("--baseline-code-root", required=True)
        one.add_argument("--prehardening-code-root", required=True)
        one.add_argument("--work-root", required=True)
        one.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    result = prove(args) if args.command == "prove" else summarize(args)
    print(json.dumps({"artifact_identity": result["artifact_identity"], "denominators": result["denominators"],
                      "fundamental_state_final": result["fundamental_state"]["distribution"]["after"],
                      "posture_baseline_to_final": result["posture_transitions"]["baseline_to_final"]["transitions"]}, sort_keys=True))


if __name__ == "__main__":
    main()
