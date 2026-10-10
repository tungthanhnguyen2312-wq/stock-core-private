"""Retained 2026-09-24 proof for CURRENT_RESEARCH_FUNDAMENTAL_PROMOTION_HARDENING_V1.

``prove`` runs the real Daily Integrated Decision assembly (``run_current_research_decision_
convergence_proof assemble``) over byte-copied retained inputs under the audit-hook write guard:

- under each local checkpoint of the chain -- 488eaf1, 66d0fc0 and the exact local head 5729c52;
- under this checkout as a cumulative ladder, one correction at a time (``LADDER``): all four
  posture-affecting corrections neutralised in-process (must reproduce 5729c52's fundamental states
  and postures exactly), then + entity-family gate, + comparable transition basis, + one vote per
  balance-sheet observation, + fiscal-label knowledge gate (= this checkout), and a rerun.

``summarize`` derives the report from that work root alone: the cloud review's findings measured on
5729c52, the exact posture ledger (every 5729c52 -> final change attributed to the ladder stage that
made it; every 488eaf1/66d0fc0 -> final change attributed through the predecessor proof), evidence
availability / risk level / direction / policy-epoch distributions, entity-family exclusions, the
fiscal-period knowledge audit, the asymmetric-dislocation invariant, the valuation value-level diff
across the chain and the authority boundary. Rerunning ``summarize`` over the same work root
reproduces the artifact identity. No provider, runtime store, publication or pointer is touched.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Only stdlib and the assembly tool at import time: the ``assemble`` subcommand imports project code
# from --code-root, which an earlier import of this checkout's modules would shadow.
from tools import run_current_research_decision_convergence_proof as convergence  # noqa: E402

CONTRACT = "fundamental_promotion_hardening_proof/v1"
MILESTONE = "CURRENT_RESEARCH_FUNDAMENTAL_PROMOTION_HARDENING_V1"
SESSION = "2026-09-24"
WORKSPACE = Path("C:/Projects/StockLookup")
EXPECTED_WORK_ROOT = WORKSPACE / "tmp" / "fundamental-promotion-hardening-proof-work"
EXPECTED_OUTPUT_DIR = WORKSPACE / "operations-review" / "current-research-fundamental-promotion-hardening-v1-20260924"
PREDECESSOR_PROOF = (WORKSPACE / "operations-review" / "fundamental-signal-policy-hardening-v1-20260924"
                     / "fundamental_signal_policy_hardening.json")
CHECKPOINTS = {
    "c488eaf1": "488eaf198b4091e7a8088b0af0f31fc95a090c1b",
    "c66d0fc0": "66d0fc0bdc494fe59c84e24266b1cb4dc6097dbb",
    "c5729c52": "5729c52d456f5da6aae50f9dd5a5bfa790bae5b6",
}
#: Which predecessor-proof run each checkpoint must reproduce (Integrated Decision identity).
CHECKPOINT_RECORDED_RUN = {"c488eaf1": "baseline", "c66d0fc0": "prehardening", "c5729c52": "after"}
CORRECTIONS = ("entity", "sequential", "grouping", "fiscal")
CORRECTION_NAMES = {
    "entity": "ENTITY_FAMILY_UNRESOLVED_NEVER_VOTES",
    "sequential": "SIGN_TRANSITION_VOTES_ONLY_ON_COMPARABLE_BASIS",
    "grouping": "ONE_VOTE_PER_BALANCE_SHEET_OBSERVATION",
    "fiscal": "NON_CALENDAR_FISCAL_LABEL_KNOWN_BY_SESSION",
}
LADDER = (
    ("L0_corrections_off", ()),
    ("L1_entity", ("entity",)),
    ("L2_comparable_transition_basis", ("entity", "sequential")),
    ("L3_one_vote_per_balance_sheet_observation", ("entity", "sequential", "grouping")),
    ("final", CORRECTIONS),
    ("rerun", CORRECTIONS),
)
LADDER_STAGE_CORRECTION = {"L1_entity": "entity", "L2_comparable_transition_basis": "sequential",
                           "L3_one_vote_per_balance_sheet_observation": "grouping", "final": "fiscal"}
RUNS = tuple(CHECKPOINTS) + tuple(name for name, _ in LADDER)
ATTEMPTED, OFFICIAL, PRICED = "ATTEMPTED_COHORT", "OFFICIAL_RESEARCH_SCOPE", "PRICED_OFFICIAL_SCOPE"
FISCAL_TICKERS_REPORTED_BY_REVIEW = ("CTD", "ITD", "KTS", "LSS", "SFC", "SLS", "TCH", "TIX")
VALUATION_METHODS = ("P/B_CURRENT_RESEARCH", "P/B", "P/E_TTM", "P/S_TTM", "market_cap")
VALUATION_FIELDS = ("value", "status", "applicability", "blocker_reason_codes", "input_periods", "book_period",
                    "limitations", "equity_definition", "statement_scope")
#: Lineage pointers to the rebuilt Financial V2 engine artifact: provenance, never a value.
ENGINE_LINEAGE_FIELDS = frozenset({"ttm_source_context_identity", "source_financial_v2_identity"})
#: Production modules this milestone changed (scanned for scratch/worktree-only path dependencies).
CHANGED_PRODUCTION_MODULES = (
    "stocklookup_core/financial/fundamental_signal_consumption_contract.py", "integrated_investment_decision_product.py",
    "current_research_decision_input.py", "asymmetric_dislocation_research.py", "multi_session_signal_velocity.py",
    "next_session_decision_brief.py", "prospective_decision_outcome_feedback.py",
    "prospective_decision_outcome_measurement.py", "daily_integrated_decision_brief.py",
    "stocklookup_core/financial/market_wide_financial_analysis_v2_scaleout.py", "canonical_daily_financial_v2_materialization.py",
)
_FORBIDDEN_PATH_FRAGMENTS = ("tmp/", "tmp\\\\", "worktrees", ".stocklookup/scratch", "scratchpad", "AppData")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(convergence.canonical(value) + b"\n")


def _counts(values: Iterable[Any]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def _transitions(pairs: Iterable[tuple[Any, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(f"{a} -> {b}" for a, b in pairs if a != b).items()))


def _digest(value: Any) -> str:
    return hashlib.sha256(convergence.canonical(value)).hexdigest()


# ── assemble (own process; project code imported from --code-root only) ─────────────────────────

def _apply_corrections(contract: Any, active: set[str]) -> None:
    """Neutralise the corrections not in ``active`` (proof ladder only; production has no switch).

    Each neutralisation restores exactly the 5729c52 behaviour of that correction; the L0 stage must
    reproduce 5729c52's fundamental state and posture for every ticker, which proves the replica.
    """
    def non_vote(*, axis: str, freshness: str, applicability: str, basis: str | None) -> str | None:
        if freshness == contract.NON_CALENDAR_FISCAL_PERIOD:
            return contract.FISCAL_CALENDAR_UNRESOLVED_NOT_A_VOTE
        if freshness not in contract._VOTING_FRESHNESS:
            return contract.STALE_NOT_A_CURRENT_VOTE
        if "entity" in active and applicability == contract.UNRESOLVED:
            return contract.ENTITY_UNRESOLVED_NOT_A_VOTE
        if "sequential" in active and axis == contract.TRANSITION and basis not in contract.DECISION_TRANSITION_BASES:
            return (contract.SEQUENTIAL_TRANSITION_NOT_A_VOTE if basis == "QOQ_STANDALONE"
                    else contract.TRANSITION_BASIS_UNRESOLVED_NOT_A_VOTE)
        return None

    contract._non_vote_reason = non_vote
    if "sequential" not in active:
        contract._NI_TRANSITION_SOURCE_ORDER = contract._NI_TRANSITION_FEATURES
    if "grouping" not in active:
        contract._group_votes = lambda resolved, signals: (set(), [])
    if "fiscal" not in active:
        contract.evidence_known_at = lambda record: None


def assemble(args: argparse.Namespace) -> None:
    code_root = Path(args.code_root).resolve()
    active = {item for item in (args.corrections or "").split(",") if item}
    if args.corrections is not None:
        if not active <= set(CORRECTIONS):
            raise SystemExit(f"UNKNOWN_CORRECTION:{sorted(active - set(CORRECTIONS))}")
        sys.path.insert(0, str(code_root))
        import stocklookup_core.financial.fundamental_signal_consumption_contract as contract
        _apply_corrections(contract, active)
    convergence.assemble(argparse.Namespace(code_root=str(code_root), producer_root=args.producer_root,
                                            work_root=args.work_root, session=args.session))
    modules = sorted(name for name in sys.modules if name.split(".")[0] in {"vnstock", "vnai", "vnstock_data"})
    _write(Path(args.work_root).resolve() / "outputs" / "runtime_safety.json", {
        "corrections_active": sorted(active) if args.corrections is not None else None,
        "provider_modules_imported": modules,
    })


def _run(name: str, code_root: Path, producer_root: Path, work_root: Path, corrections: tuple[str, ...] | None) -> None:
    target = work_root / name
    if target.exists():
        import shutil
        shutil.rmtree(target)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    command = [sys.executable, str(Path(__file__).resolve()), "assemble", "--code-root", str(code_root),
               "--producer-root", str(producer_root), "--work-root", str(target), "--session", SESSION]
    if corrections is not None:
        command += ["--corrections", ",".join(corrections)]
    subprocess.run(command, check=True, env=env, cwd=str(code_root))


def _roots(args: argparse.Namespace) -> dict[str, Path]:
    roots = {"producer": Path(args.producer_root).resolve(), "work": Path(args.work_root).resolve(),
             "output": Path(args.output_dir).resolve(),
             **{name: Path(getattr(args, f"{name}_code_root")).resolve() for name in CHECKPOINTS}}
    if roots["work"] != EXPECTED_WORK_ROOT.resolve() or roots["output"] != EXPECTED_OUTPUT_DIR.resolve():
        raise SystemExit("PROOF_ROOTS_OUTSIDE_NAMED_TARGETS")
    for name, commit in CHECKPOINTS.items():
        if convergence._git(roots[name], "rev-parse", "HEAD") != commit:
            raise SystemExit(f"{name.upper()}_CODE_ROOT_NOT_AT_CHECKPOINT")
        if convergence._git(roots[name], "status", "--porcelain", "--untracked-files=no"):
            raise SystemExit(f"{name.upper()}_CODE_ROOT_HAS_TRACKED_CHANGES")
    return roots


def prove(args: argparse.Namespace) -> dict:
    roots = _roots(args)
    from tools import run_financial_v2_analysis_input_integrity_proof as integrity
    for name in CHECKPOINTS:
        if not all(integrity._pinned_authority_equal(roots[name]).values()):
            raise SystemExit(f"PINNED_FINANCIAL_V2_EVIDENCE_DIFFERS:{name}")
    evidence = integrity._evidence_paths(roots["producer"])
    before = integrity._hashes(evidence)
    for name in CHECKPOINTS:
        _run(name, roots[name], roots["producer"], roots["work"], None)
    for name, corrections in LADDER:
        _run(name, ROOT, roots["producer"], roots["work"], corrections)
    if integrity._hashes(evidence) != before:
        raise SystemExit("RETAINED_EVIDENCE_SHA_CHANGED")
    _write(roots["work"] / "retained_evidence_sha256.json", before)
    return summarize(args)


# ── summarize ────────────────────────────────────────────────────────────────────────────────────

def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _projection(record: Mapping[str, Any]) -> dict[str, Any]:
    """The per-ticker decision view a non-final run keeps in memory."""
    synthesis = record.get("fundamental_synthesis") or {}
    derivation = synthesis.get("derivation") or {}
    return {"fundamental_state": record.get("fundamental_state"), "posture": record.get("research_action_posture"),
            "why_now": record.get("why_now"), "dialect": synthesis.get("source_dialect"),
            "favorable": list(derivation.get("favorable_votes") or []), "adverse": list(derivation.get("adverse_votes") or []),
            "folded": list((derivation.get("vote_grouping") or {}).get("folded_votes") or []),
            "evidence_class": (record.get("current_research_decision_input") or {}).get("evidence_class"),
            "decision_identity": record.get("decision_identity")}


def _strip_lineage(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _strip_lineage(item) for key, item in value.items() if key not in ENGINE_LINEAGE_FIELDS}
    if isinstance(value, list):
        return [_strip_lineage(item) for item in value]
    return value


def _valuation_view(valuation: Mapping[str, Any]) -> dict[str, Any]:
    """Per ticker: the regression-gated method fields, peer detail, and a lineage-stripped digest."""
    out = {}
    for ticker, record in (valuation.get("records") or {}).items():
        methods = record.get("methods") or {}
        out[ticker] = {
            "methods": {method: {field: (methods.get(method) or {}).get(field) for field in VALUATION_FIELDS}
                        for method in VALUATION_METHODS},
            "peer": {method: {"status": detail.get("status"), "percentile": detail.get("percentile"),
                              "peer_count": detail.get("peer_count"), "reason": detail.get("reason")}
                     for method, detail in sorted((record.get("peer_relative") or {}).items()) if isinstance(detail, Mapping)},
            "relative_research_state": record.get("relative_research_state"),
            "stripped_digest": _digest(_strip_lineage(record)),
        }
    return {"artifact_identity": valuation.get("artifact_identity"), "records": out}


def _load_runs(work_root: Path, keep_full: set[str]) -> dict[str, dict[str, Any]]:
    import daily_session_level2_package as level2
    runs: dict[str, dict[str, Any]] = {}
    for name in RUNS:
        outputs = work_root / name / "outputs"
        iid = _load(outputs / "integrated_investment_decision_product.json")
        compact = _load(outputs / "financial_analysis_product.json")
        valuation = _load(level2.session_artifact_paths(work_root / name / "artifact-root", SESSION)["current_valuation_evaluated"])
        runs[name] = {
            "assembly": _load(outputs / "assembly_result.json"),
            "runtime_safety": _load(outputs / "runtime_safety.json"),
            "iid_path": outputs / "integrated_investment_decision_product.json",
            "integrated_identity": iid["artifact_identity"],
            "compact_identity": compact["artifact_identity"],
            "valuation_identity": valuation["artifact_identity"],
            "valuation": _valuation_view(valuation),
            "records": {t: _projection(r) for t, r in iid["records"].items()},
            "full": iid["records"] if name in keep_full else None,
            "coverage": iid.get("coverage") if name in keep_full else None,
            "compact": compact["records"] if name in keep_full else None,
        }
        del iid, valuation, compact
    return runs


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def summarize(args: argparse.Namespace) -> dict:
    roots = _roots(args)
    import stocklookup_core.financial.fundamental_signal_consumption_contract as contract
    import asymmetric_dislocation_research as adr
    import multi_session_signal_velocity as velocity
    import next_session_decision_brief as next_brief
    import provider_financial_monetary_basis_verdict as verdict_pin
    from tools import current_research_capability_map as capability
    from tools import run_integrated_fundamental_state_consumption_proof as consumption

    work_root = roots["work"]
    predecessor = _load(PREDECESSOR_PROOF)
    # Capability maps first (each build reads a whole Integrated Decision); only their rows are kept.
    ops = roots["producer"] / "operations-review"
    map_paths = {name: work_root / name / "outputs" / "integrated_investment_decision_product.json"
                 for name in ("c5729c52", "final", "rerun")}
    head_tool = _module(roots["c5729c52"] / "tools" / "current_research_capability_map.py", "head_capability_map")
    maps: dict[str, dict[str, Any]] = {}
    for name, tool in (("c5729c52", head_tool), ("final", capability), ("rerun", capability)):
        built = tool.build(ops, SESSION, {"integrated": map_paths[name]})
        maps[name] = {"artifact_identity": built["artifact_identity"],
                      "records": {t: {key: row.get(key) for key in ("universe_status", "research_market_cap_usable",
                                                                    "fundamental_fitness", "fundamental_evidence_availability",
                                                                    "decision_fitness")}
                                  for t, row in built["records"].items()}}
        del built
    if maps["final"]["artifact_identity"] != maps["rerun"]["artifact_identity"]:
        raise SystemExit("CAPABILITY_MAP_NOT_DETERMINISTIC")
    if maps["c5729c52"]["artifact_identity"] != predecessor["identities"]["after"]["capability_map"]:
        raise SystemExit("HEAD_CAPABILITY_MAP_DOES_NOT_REPRODUCE")
    runs = _load_runs(work_root, keep_full={"c5729c52", "final"})
    for name, run in runs.items():
        guard = run["assembly"]
        if (guard["write_guard"]["violations"] or guard["provider_calls"] or guard["runtime_store_reads"]
                or guard.get("network_audit_events") is None or any(guard["network_audit_events"].values())
                or run["runtime_safety"]["provider_modules_imported"]):
            raise SystemExit(f"EVIDENCE_GUARD_PROVIDER_OR_NETWORK_VIOLATION:{name}")
    if len({json.dumps(run["assembly"]["staged_session_inputs"], sort_keys=True) for run in runs.values()}) != 1:
        raise SystemExit("STAGED_SESSION_INPUTS_DIFFER")
    for key in ("integrated_identity", "compact_identity", "valuation_identity"):
        if runs["final"][key] != runs["rerun"][key]:
            raise SystemExit(f"FINAL_REPLAY_NOT_DETERMINISTIC:{key}")
    for name, recorded in CHECKPOINT_RECORDED_RUN.items():
        if runs[name]["integrated_identity"] != predecessor["identities"][recorded]["integrated"]:
            raise SystemExit(f"{name.upper()}_DOES_NOT_REPRODUCE_ITS_RECORDED_IDENTITY")
        if runs[name]["assembly"]["code_head"] != CHECKPOINTS[name] or runs[name]["assembly"]["code_tracked_changes"]:
            raise SystemExit(f"{name.upper()}_NOT_A_CLEAN_CHECKPOINT_RUN")

    rows = maps["final"]["records"]
    attempted = set(rows)
    official = {t for t, row in rows.items() if row["universe_status"] == OFFICIAL}
    priced = {t for t in official if rows[t]["research_market_cap_usable"]}
    if (len(attempted), len(official), len(priced)) != tuple(predecessor["denominators"][k] for k in (ATTEMPTED, OFFICIAL, PRICED)):
        raise SystemExit("DENOMINATORS_DO_NOT_RECONCILE")

    rec = {name: run["records"] for name, run in runs.items()}
    head, final = runs["c5729c52"], runs["final"]
    # Producer states are untouched: the engine change is lineage only (the knowledge time).
    state_changes = {field: sum(head["compact"][t].get(field) != final["compact"][t].get(field) for t in attempted)
                     for field in consumption.PRODUCER_FIELDS}
    if any(state_changes.values()):
        raise SystemExit(f"UNEXPECTED_PRODUCER_STATE_CHANGE:{state_changes}")
    # L0 (every correction neutralised) must reproduce 5729c52 exactly in state and posture.
    l0_mismatch = sorted(t for t in attempted if (rec["L0_corrections_off"][t]["fundamental_state"], rec["L0_corrections_off"][t]["posture"])
                         != (rec["c5729c52"][t]["fundamental_state"], rec["c5729c52"][t]["posture"]))
    if l0_mismatch:
        raise SystemExit(f"L0_DOES_NOT_REPRODUCE_5729C52:{l0_mismatch[:20]}")

    # Reproduction on the exact head uses the head's own dislocation module, never this checkout's.
    head_adr = _module(roots["c5729c52"] / "asymmetric_dislocation_research.py", "head_asymmetric_dislocation")
    findings = _cloud_findings(contract, head_adr, head, runs, official, predecessor)
    ladder = _ladder(rec, official, attempted)
    ledgers = _ledgers(rec, official, ladder, predecessor)
    for key in ("c5729c52_to_final", "c488eaf1_to_final", "c66d0fc0_to_final"):
        view = ledgers[key]
        if view["unexplained"]:
            raise SystemExit(f"POSTURE_TRANSITION_ATTRIBUTION_INCOMPLETE:{view['unexplained'][:20]}")
    distributions = _distributions(contract, final, rec, official)
    distributions["capability_map_fundamental"] = {
        name: {"fundamental_fitness": _counts(maps[name]["records"][t]["fundamental_fitness"] for t in sorted(official)),
               "fundamental_evidence_availability": _counts(maps[name]["records"][t].get("fundamental_evidence_availability")
                                                            for t in sorted(official)),
               "decision_fitness": _counts(maps[name]["records"][t]["decision_fitness"] for t in sorted(official))}
        for name in ("c5729c52", "final")}
    stale_marked_absent = [t for t in official if final["full"][t].get("fundamental_evidence_availability") != contract.ABSENT
                           and maps["final"]["records"][t]["fundamental_fitness"] != "INTEGRATED_RESEARCH_USABLE"
                           and final["full"][t].get("fundamental_evidence_availability") != contract.NOT_APPLICABLE_ENTITY]
    if stale_marked_absent:
        raise SystemExit(f"KNOWN_EVIDENCE_MARKED_INSUFFICIENT_IN_CAPABILITY_MAP:{sorted(stale_marked_absent)[:20]}")
    entity = _entity_family(contract, head, final, official)
    fiscal = _fiscal_audit(contract, roots, head, final, official)
    dislocation = _dislocation(contract, adr, head, final, official, head_adr)
    epoch = _policy_epoch(contract, velocity, next_brief, head, final, official)
    valuation = _valuation_diff(runs, official, verdict_pin.resolve(ROOT))
    authority = _authority(contract, roots, head, final, attempted)

    result: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT, "session": SESSION, "milestone": MILESTONE,
        "predecessor": {"checkpoint": CHECKPOINTS["c5729c52"], "milestone": "FUNDAMENTAL_SIGNAL_POLICY_HARDENING_V1",
                        "proof_identity": predecessor["artifact_identity"]},
        "baseline_identity": {
            "checkpoints": CHECKPOINTS,
            "final_code_head": final["assembly"]["code_head"],
            "final_code_tracked_changes": final["assembly"]["code_tracked_changes"],
            "staged_session_inputs": final["assembly"]["staged_session_inputs"],
            "retained_evidence_sha256": _load(work_root / "retained_evidence_sha256.json"),
            "checkpoints_reproduce_recorded_identities": True,
            "l0_reproduces_5729c52_state_and_posture": True,
        },
        "identities": {name: {"integrated": run["integrated_identity"], "financial_analysis_product": run["compact_identity"],
                              "evaluated_valuation": run["valuation_identity"],
                              "corrections_active": run["runtime_safety"]["corrections_active"]}
                       for name, run in runs.items()},
        "capability_map_identities": {name: value["artifact_identity"] for name, value in maps.items()},
        "guard": {name: {"violations": run["assembly"]["write_guard"]["violations"],
                         "network_audit_events": run["assembly"]["network_audit_events"],
                         "provider_calls": run["assembly"]["provider_calls"],
                         "runtime_store_reads": run["assembly"]["runtime_store_reads"],
                         "provider_modules_imported": run["runtime_safety"]["provider_modules_imported"],
                         "publication": run["assembly"]["publication"]} for name, run in runs.items()},
        "denominators": {ATTEMPTED: len(attempted), OFFICIAL: len(official), PRICED: len(priced)},
        "policy": {
            "decision_policy_version": contract.DECISION_POLICY_VERSION, "signal_policy": contract.SIGNAL_POLICY,
            "policy_epochs": list(contract.POLICY_EPOCHS), "vote_eligibility": contract.VOTE_ELIGIBILITY_RULE,
            "five_state_availability_rule": contract.FIVE_STATE_AVAILABILITY_RULE, "risk_level_rule": contract.RISK_LEVEL_RULE,
            "vote_grouping_rule": contract.VOTE_GROUPING_RULE, "vote_groups": [
                {"group": g["group"], "members": [".".join(m) for m in g["members"]], "counted": ".".join(g["counted"])}
                for g in contract.VOTE_GROUPS],
            "decision_transition_bases": sorted(contract.DECISION_TRANSITION_BASES),
            "fiscal_period_rule": contract.FISCAL_PERIOD_RULE, "non_vote_reasons": list(contract.NON_VOTE_REASONS),
            "corrections": CORRECTION_NAMES, "ladder": [{"stage": name, "corrections_active": list(active)} for name, active in LADDER],
        },
        "cloud_findings": findings,
        "ladder": ladder,
        "posture_ledgers": ledgers,
        "distributions": distributions,
        "entity_applicability": entity,
        "fiscal_period_audit": fiscal,
        "asymmetric_dislocation": dislocation,
        "policy_epoch": epoch,
        "valuation_value_diff": valuation,
        "authority_boundary": authority,
    }
    result["artifact_sha256"] = hashlib.sha256(convergence.canonical(result)).hexdigest()
    result["artifact_identity"] = f"{CONTRACT}:{result['artifact_sha256']}"
    roots["output"].mkdir(parents=True, exist_ok=True)
    _write(roots["output"] / "fundamental_promotion_hardening.json", result)
    (roots["output"] / "SUMMARY.md").write_text(_summary(result), encoding="utf-8")
    return result


# ── cloud findings, measured on the exact local head ─────────────────────────────────────────────

def _state_of(contract: Any, favorable: set[str], adverse: set[str], dimensions: Mapping[str, Any], turnaround: bool) -> str:
    """The unchanged fundamental_state rule, re-applied to an alternative vote set."""
    gate = [label for label, hit in (
        ("P", (dimensions.get("PROFITABILITY") or {}).get("level") == contract.STRESSED),
        ("G", (dimensions.get("GROWTH") or {}).get("direction") == contract.WORSENING),
        ("C", (dimensions.get("CAPITAL_STRUCTURE") or {}).get("direction") == contract.WORSENING)) if hit]
    drivers = [label for label, hit in (
        ("G", (dimensions.get("GROWTH") or {}).get("direction") == contract.IMPROVING),
        ("M", (dimensions.get("MARGINS") or {}).get("direction") == contract.IMPROVING),
        ("L", (dimensions.get("SHORT_TERM_LIQUIDITY") or {}).get("direction") == contract.IMPROVING)) if hit]
    if turnaround:
        return contract.FUNDAMENTAL_TURNAROUND
    if len(adverse) > len(favorable) and gate:
        return contract.FUNDAMENTAL_DETERIORATING
    if favorable and not adverse:
        return contract.FUNDAMENTAL_IMPROVING if drivers else contract.FUNDAMENTAL_STABLE
    if favorable and adverse:
        return contract.FUNDAMENTAL_MIXED
    if (dimensions.get("PROFITABILITY") or {}).get("level") == contract.HEALTHY:
        return contract.FUNDAMENTAL_STABLE
    return contract.FUNDAMENTAL_INSUFFICIENT


def _cloud_findings(contract: Any, adr: Any, head: Mapping[str, Any], runs: Mapping[str, Any], official: set[str],
                    predecessor: Mapping[str, Any]) -> dict[str, Any]:
    full, compact = head["full"], head["compact"]
    base = runs["c488eaf1"]["records"]
    tickers = sorted(official)
    syn = {t: full[t]["fundamental_synthesis"] for t in tickers}

    # 1. Evidence availability: directional INSUFFICIENT read as absent fundamental context.
    insufficient_posture = [t for t in tickers if full[t]["research_action_posture"] == "INSUFFICIENT_CURRENT_RESEARCH"]
    claims_no_data = [t for t in insufficient_posture if "fundamental analysis data" in (full[t].get("why_now") or "")
                      and (syn[t].get("evidence_availability") or {}).get("state") == contract.AVAILABLE]
    head_five = {t: contract.evidence_availability_of_record(full[t]) for t in tickers}
    availability = {
        "verdict": "CONFIRMED",
        "directional_insufficient_with_qualified_evidence": sum(full[t]["fundamental_state"] == contract.FUNDAMENTAL_INSUFFICIENT
                                                                and (syn[t].get("evidence_availability") or {}).get("state") == contract.AVAILABLE for t in tickers),
        "insufficient_research_posture": len(insufficient_posture),
        "why_now_claims_no_fundamental_data_while_evidence_known": len(claims_no_data),
        "why_now_claims_tickers": claims_no_data,
        "axis_blockers_at_head": _counts(tuple(full[t]["evidence_axes"]["FUNDAMENTAL"]["blocker_reason_codes"]) for t in tickers),
        "composite_label_for_insufficient_with_evidence": _counts(
            full[t]["financial_composite_context"]["financial_composite_state"] for t in tickers
            if full[t]["fundamental_state"] == contract.FUNDAMENTAL_INSUFFICIENT and (syn[t].get("evidence_availability") or {}).get("state") == contract.AVAILABLE),
        "five_state_resolved_on_head_records": _counts(head_five.values()),
        "note": ("5729c52 already separated a binary availability from directional sufficiency in the decision input and "
                 "axis blocker; the posture explanation still named missing fundamental data and no five-state existed."),
    }
    # 2. Direction versus risk level.
    head_risk = {t: contract.risk_level_of_record(full[t])["state"] for t in tickers}
    risk = {
        "verdict": "CONFIRMED",
        "risk_level_field_at_head": "ABSENT",
        "direction_x_resolved_level": _counts(f"{full[t]['fundamental_state']}|{head_risk[t]}" for t in tickers),
        "improving_or_stable_with_adverse_level": sum(full[t]["fundamental_state"] in ("IMPROVING", "STABLE")
                                                      and head_risk[t] in (contract.ADVERSE_LEVEL_CURRENT, contract.ADVERSE_LEVEL_KNOWN_NOT_CURRENT)
                                                      for t in tickers),
        "mixed_with_adverse_level": sum(full[t]["fundamental_state"] == "MIXED"
                                        and head_risk[t] in (contract.ADVERSE_LEVEL_CURRENT, contract.ADVERSE_LEVEL_KNOWN_NOT_CURRENT) for t in tickers),
        "insufficient_with_adverse_level": sum(full[t]["fundamental_state"] == "INSUFFICIENT"
                                               and head_risk[t] in (contract.ADVERSE_LEVEL_CURRENT, contract.ADVERSE_LEVEL_KNOWN_NOT_CURRENT) for t in tickers),
    }

    # 3. Leverage / equity-to-assets identity.
    def sig(t: str, signal_id: str) -> Mapping[str, Any]:
        return next((s for s in syn[t].get("signals") or [] if s["signal_id"] == signal_id), {})

    v2 = [t for t in tickers if syn[t].get("source_dialect") == contract.DIALECT_FINANCIAL_V2]
    fallback = [t for t in v2 if "LEVERAGE_STATE_IS_EQUITY_TO_ASSETS_FALLBACK_DUPLICATE" in (sig(t, "debt_to_equity_direction").get("reason_codes") or [])]
    both_vote = [t for t in v2 if sig(t, "debt_to_equity_direction").get("decision_eligible") and sig(t, "equity_to_assets_direction").get("decision_eligible")]
    leverage = {
        "verdict": "REJECTED_ON_LOCAL_HEAD",
        "leverage_state_is_equity_to_assets_fallback": len(fallback),
        "fallback_already_evidence_only_at_head": all(sig(t, "debt_to_equity_direction").get("role") == contract.EVIDENCE_ONLY for t in fallback),
        "debt_to_equity_and_equity_to_assets_both_current": len(both_vote),
        "second_capital_structure_vote_cast": 0,
        "note": ("Debt/equity and equity/assets are distinct measurements resolved into ONE CAPITAL_STRUCTURE dimension vote; "
                 "the engine's leverage fallback re-reads equity/assets and was already evidence-only, occurring 0 times."),
    }
    # 4. Current ratio + correlated votes (capital structure and short-term liquidity on one balance sheet).
    cases: Counter[str] = Counter()
    collapse: dict[str, list[str]] = defaultdict(list)
    for t in v2:
        derivation = syn[t]["derivation"]
        fav, adv = set(derivation["favorable_votes"]), set(derivation["adverse_votes"])
        cs, lq = "CAPITAL_STRUCTURE.DIRECTION", "SHORT_TERM_LIQUIDITY.DIRECTION"
        pcs = "F" if cs in fav else "A" if cs in adv else None
        plq = "F" if lq in fav else "A" if lq in adv else None
        if not (pcs and plq):
            continue
        signals = [s for s in syn[t]["signals"] if s["decision_eligible"]]
        periods = [{s["fitness"]["as_of_period"] for s in signals if (s["dimension"], s["axis"]) == key}
                   for key in (("CAPITAL_STRUCTURE", "DIRECTION"), ("SHORT_TERM_LIQUIDITY", "DIRECTION"))]
        same = bool(periods[0] & periods[1])
        kind = "SAME_DIRECTION" if pcs == plq else "OPPOSING"
        cases[f"{kind}|{pcs}{plq}|same_balance_sheet_observation={same}"] += 1
        if kind == "SAME_DIRECTION" and same:
            f2, a2 = set(fav), set(adv)
            (f2 if pcs == "F" else a2).discard(lq)
            alt = _state_of(contract, f2, a2, syn[t]["dimensions"], derivation["turnaround"]["triggered"])
            if alt != full[t]["fundamental_state"]:
                collapse[f"{full[t]['fundamental_state']} -> {alt}"].append(t)
    prior_items = predecessor["posture_transitions"]["baseline_to_final"]["per_ticker"]
    restored = sorted(item["ticker"] for item in prior_items if "CURRENT_SIGNAL_RESTORED" in item["cause_categories"])
    restored_cr = sorted(item["ticker"] for item in prior_items for c in item["causes"]
                         if c["category"] == "CURRENT_SIGNAL_RESTORED" and "current_ratio_direction" in c["signals"])
    collapsed = {t for tickers_ in collapse.values() for t in tickers_}
    correlated = {
        "verdict": "CONFIRMED",
        "current_ratio_direction_voting": sum(bool(sig(t, "current_ratio_direction").get("decision_eligible")) for t in v2),
        "capital_structure_and_liquidity_vote_pairs": dict(sorted(cases.items())),
        "correlated_same_direction_same_observation": sum(v for k, v in cases.items() if k.startswith("SAME_DIRECTION") and k.endswith("True")),
        "opposing_pairs": sum(v for k, v in cases.items() if k.startswith("OPPOSING")),
        "fundamental_state_changes_if_counted_once": {k: len(v) for k, v in sorted(collapse.items())},
        "predecessor_posture_transitions_with_current_signal_restored": len(restored),
        "predecessor_posture_transitions_restored_by_current_ratio": len(restored_cr),
        "of_those_on_a_correlated_pair_whose_state_changes": sum(t in collapsed for t in restored_cr),
        "cloud_estimate": "~9 of 58",
        "note": "Exact local count replaces the estimate; the posture effect is measured by the ladder (L3).",
    }
    # 5. The 177 posture transitions.
    posture_177 = sum(base[t]["posture"] != head["records"][t]["posture"] for t in tickers)
    transitions = {"verdict": "CONFIRMED" if posture_177 == 177 else "PARTIAL", "count_488eaf1_to_5729c52_official": posture_177,
                   "by_primary_driver_in_predecessor_proof": predecessor["posture_transitions"]["baseline_to_final"]["by_primary_driver"]}
    # 6. Asymmetric dislocation survivability.
    artifact = adr.build_artifact(session=SESSION, integrated_product={"session": SESSION, "records": {t: full[t] for t in tickers}})
    head_adr = artifact["records"]
    unknown_with_adverse = [t for t in tickers if full[t]["fundamental_state"] == "INSUFFICIENT"
                            and head_risk[t] in (contract.ADVERSE_LEVEL_CURRENT, contract.ADVERSE_LEVEL_KNOWN_NOT_CURRENT)]
    dislocation = {
        "verdict": "CONFIRMED",
        "head_state_distribution": artifact["coverage"]["state_distribution"],
        "insufficient_direction_with_known_adverse_level": len(unknown_with_adverse),
        "classified_as": _counts(head_adr[t]["primary_research_state"] for t in unknown_with_adverse),
        "flagged_fundamental_evidence_unavailable": sum("FUNDAMENTAL_EVIDENCE_UNAVAILABLE" in head_adr[t]["missing_evidence_flags"]
                                                        for t in unknown_with_adverse),
        "quality_dislocation_at_head": sum(r["primary_research_state"] == adr.QUALITY_DISLOCATION for r in head_adr.values()),
        "quality_dislocation_with_adverse_level_at_head": sum(
            head_adr[t]["primary_research_state"] == adr.QUALITY_DISLOCATION
            and head_risk[t] in (contract.ADVERSE_LEVEL_CURRENT, contract.ADVERSE_LEVEL_KNOWN_NOT_CURRENT) for t in tickers),
        "note": ("Survivability was fundamental_state verbatim: 0 retained QUALITY_DISLOCATION records carried an adverse level, "
                 "but the rule admitted it (IMPROVING via directions / MIXED + recovery) and read INSUFFICIENT as unknown."),
    }
    # 7. Entity family: unresolved/generic records voting industrial signals.
    generic_votes = {t: sorted(s["signal_id"] for s in syn[t]["signals"] if s["decision_eligible"] and s["applicability"] == contract.UNRESOLVED)
                     for t in v2}
    generic_votes = {t: v for t, v in generic_votes.items() if v}
    entity = {"verdict": "CONFIRMED", "records_with_unresolved_entity_votes": len(generic_votes),
              "votes": sum(len(v) for v in generic_votes.values()), "tickers": generic_votes,
              "analysis_family_issuer_type": {t: f"{compact[t].get('analysis_family')}|{compact[t].get('issuer_type')}" for t in generic_votes}}
    # 8. Fiscal labels.
    future = {t: sorted({str((f or {}).get("as_of_period")) for f in (compact[t].get("feature_fitness") or {}).values()
                         if isinstance(f, Mapping) and (f or {}).get("as_of_period") and contract._quarter_end((f or {}).get("as_of_period"))
                         and contract._quarter_end((f or {}).get("as_of_period")).isoformat() > SESSION})
              for t in sorted(compact)}
    future = {t: v for t, v in future.items() if v}
    fiscal = {"verdict": "PARTIAL_LABELS_CONFIRMED_LOOK_AHEAD_REJECTED",
              "records_with_post_session_labels": future,
              "matches_review_list": sorted(future) == sorted(FISCAL_TICKERS_REPORTED_BY_REVIEW)}
    # 9. PROFIT_TO_LOSS / sequential transitions.
    rows = [(t, s) for t in v2 for s in syn[t]["signals"] if s["axis"] == contract.TRANSITION and s["decision_eligible"]]
    p2l = {"verdict": "CONFIRMED", "current_transition_votes": _counts(f"{s['value']}|{s['fitness']['basis']}" for _, s in rows),
           "current_transition_votes_on_comparable_basis": sum(s["fitness"]["basis"] in contract.DECISION_TRANSITION_BASES for _, s in rows),
           "profit_to_loss_qoq_votes": sorted(t for t, s in rows if s["value"] == contract.PROFIT_TO_LOSS)}
    # 10. Research P/B surfacing as pb_multiple without its limitation.
    usable = [t for t in tickers if (full[t]["valuation_methods"].get("P/B_CURRENT_RESEARCH") or {}).get("status") == "RESEARCH_USABLE"]
    pb = {"verdict": "CONFIRMED",
          "research_p_b_usable": len(usable),
          "pb_multiple_equals_research_value": sum(full[t]["valuation_context_summary"].get("pb_multiple")
                                                   == full[t]["valuation_methods"]["P/B_CURRENT_RESEARCH"].get("value") for t in usable),
          "summary_carries_nci_or_research_label": sum("NCI" in json.dumps(full[t]["valuation_context_summary"]) for t in usable)}
    return {"evidence_availability": availability, "risk_level_vs_direction": risk, "leverage_equity_to_assets_identity": leverage,
            "correlated_votes": correlated, "posture_transitions_177": transitions, "asymmetric_dislocation": dislocation,
            "entity_family": entity, "fiscal_period_labels": fiscal, "profit_to_loss_basis": p2l, "research_p_b_label": pb}


# ── ladder and ledgers ───────────────────────────────────────────────────────────────────────────

def _ladder(rec: Mapping[str, Mapping[str, Any]], official: set[str], attempted: set[str]) -> dict[str, Any]:
    stages = [name for name, _ in LADDER if name != "rerun"]
    out: dict[str, Any] = {"stages": {}}
    previous = "c5729c52"
    for stage in stages:
        a, b = rec[previous], rec[stage]
        state = sorted(t for t in official if a[t]["fundamental_state"] != b[t]["fundamental_state"])
        posture = sorted(t for t in official if a[t]["posture"] != b[t]["posture"])
        unexplained = sorted(t for t in posture if t not in state
                             and (a[t]["dialect"] == b[t]["dialect"]))
        out["stages"][stage] = {
            "from": previous, "correction": LADDER_STAGE_CORRECTION.get(stage),
            "fundamental_state_changes_official": len(state),
            "fundamental_state_transitions": _transitions((a[t]["fundamental_state"], b[t]["fundamental_state"]) for t in state),
            "posture_changes_official": len(posture),
            "posture_transitions": _transitions((a[t]["posture"], b[t]["posture"]) for t in posture),
            "posture_changes_without_state_change": unexplained,
            "bridge_application_changed": sorted(t for t in official if a[t]["dialect"] != b[t]["dialect"]),
            "per_ticker": {t: {"fundamental_state": [a[t]["fundamental_state"], b[t]["fundamental_state"]],
                               "posture": [a[t]["posture"], b[t]["posture"]],
                               "votes_before": {"favorable": a[t]["favorable"], "adverse": a[t]["adverse"]},
                               "votes_after": {"favorable": b[t]["favorable"], "adverse": b[t]["adverse"], "folded": b[t]["folded"]},
                               "dialect": [a[t]["dialect"], b[t]["dialect"]]}
                           for t in sorted(set(state) | set(posture))},
            "attempted_state_changes": sum(a[t]["fundamental_state"] != b[t]["fundamental_state"] for t in attempted),
        }
        if unexplained:
            raise SystemExit(f"LADDER_POSTURE_CHANGE_WITHOUT_STATE_CHANGE:{stage}:{unexplained[:20]}")
        previous = stage
    return out


def _ledgers(rec: Mapping[str, Mapping[str, Any]], official: set[str], ladder: Mapping[str, Any],
             predecessor: Mapping[str, Any]) -> dict[str, Any]:
    stage_changes = {stage: set(view["per_ticker"]) for stage, view in ladder["stages"].items()}
    stage_posture = {stage: {t for t, item in view["per_ticker"].items() if item["posture"][0] != item["posture"][1]}
                     for stage, view in ladder["stages"].items()}
    prior = {item["ticker"]: item for item in predecessor["posture_transitions"]["baseline_to_final"]["per_ticker"]}
    prior_pre = {item["ticker"]: item for item in predecessor["posture_transitions"]["prehardening_to_final"]["per_ticker"]}

    def view(old: str, prior_items: Mapping[str, Any] | None) -> dict[str, Any]:
        items, unexplained = [], []
        for t in sorted(official):
            before, after = rec[old][t]["posture"], rec["final"][t]["posture"]
            if before == after:
                continue
            stages = [stage for stage, tickers in stage_posture.items() if t in tickers]
            attribution: dict[str, Any] = {"ladder_stages": stages,
                                           "ladder_corrections": [LADDER_STAGE_CORRECTION[s] for s in stages if LADDER_STAGE_CORRECTION.get(s)]}
            if prior_items is not None and t in prior_items:
                attribution["predecessor_causes"] = sorted(prior_items[t]["cause_categories"])
            elif old != "c5729c52" and rec[old][t]["posture"] != rec["c5729c52"][t]["posture"]:
                attribution["predecessor_causes"] = ["MISSING"]
            explained = bool(stages) or bool(attribution.get("predecessor_causes")) and "MISSING" not in attribution.get("predecessor_causes", [])
            if not explained:
                unexplained.append(t)
            items.append({"ticker": t, "posture": [before, after],
                          "fundamental_state": [rec[old][t]["fundamental_state"], rec["c5729c52"][t]["fundamental_state"],
                                                rec["final"][t]["fundamental_state"]],
                          **attribution})
        return {"count_official": len(items), "transitions": _transitions((i["posture"][0], i["posture"][1]) for i in items),
                "by_ladder_correction": _counts(c for i in items for c in i["ladder_corrections"]),
                "per_ticker": items, "unexplained": unexplained}

    head_to_final = view("c5729c52", None)
    removed, preserved = [], []
    for t in sorted(official):
        base, head, fin = rec["c488eaf1"][t]["posture"], rec["c5729c52"][t]["posture"], rec["final"][t]["posture"]
        if base != head:
            (removed if fin == base else preserved).append(t)
    return {
        "c5729c52_to_final": head_to_final,
        "c488eaf1_to_final": view("c488eaf1", prior),
        "c66d0fc0_to_final": view("c66d0fc0", prior_pre),
        "pairwise_counts_official": {f"{a}->{b}": sum(rec[a][t]["posture"] != rec[b][t]["posture"] for t in official)
                                     for a, b in (("c488eaf1", "c66d0fc0"), ("c488eaf1", "c5729c52"), ("c488eaf1", "final"),
                                                  ("c66d0fc0", "c5729c52"), ("c66d0fc0", "final"), ("c5729c52", "final"))},
        "predecessor_177": {"removed_reverted_to_488eaf1": len(removed), "preserved_in_final": len(preserved),
                            "changed_to_a_third_posture": sum(rec["final"][t]["posture"] not in (rec["c488eaf1"][t]["posture"], rec["c5729c52"][t]["posture"])
                                                              for t in preserved),
                            "removed_by_ladder_correction": _counts(LADDER_STAGE_CORRECTION[s] for t in removed
                                                                    for s, ts in stage_posture.items() if t in ts and LADDER_STAGE_CORRECTION.get(s)),
                            "removed_tickers": removed},
    }


# ── distributions, entity, fiscal, dislocation, epoch ────────────────────────────────────────────

def _distributions(contract: Any, final: Mapping[str, Any], rec: Mapping[str, Mapping[str, Any]], official: set[str]) -> dict[str, Any]:
    full = final["full"]
    tickers = sorted(official)
    return {
        "fundamental_evidence_availability": _counts(full[t].get("fundamental_evidence_availability") for t in tickers),
        "fundamental_risk_level": _counts((full[t].get("fundamental_risk_level") or {}).get("state") for t in tickers),
        "direction_x_risk_level": _counts(f"{full[t]['fundamental_state']}|{(full[t].get('fundamental_risk_level') or {}).get('state')}" for t in tickers),
        "fundamental_state": {name: _counts(rec[name][t]["fundamental_state"] for t in tickers)
                              for name in ("c488eaf1", "c66d0fc0", "c5729c52", "final")},
        "research_action_posture": {name: _counts(rec[name][t]["posture"] for t in tickers)
                                    for name in ("c488eaf1", "c66d0fc0", "c5729c52", "final")},
        "evidence_class": {name: _counts(rec[name][t]["evidence_class"] for t in tickers) for name in ("c5729c52", "final")},
        "fundamental_decision_policy_version": _counts(full[t].get("fundamental_decision_policy_version") for t in tickers),
        "axis_blockers": _counts(tuple(full[t]["evidence_axes"]["FUNDAMENTAL"]["blocker_reason_codes"]) for t in tickers),
        "why_now_claims_no_fundamental_data_while_evidence_known": sum(
            "fundamental analysis data" in (full[t].get("why_now") or "")
            and full[t].get("fundamental_evidence_availability") != contract.ABSENT for t in tickers),
        "vote_grouping_outcomes": _counts(g["outcome"] for t in tickers
                                          for g in ((full[t]["fundamental_synthesis"].get("derivation") or {}).get("vote_grouping") or {}).get("groups") or []),
        "non_vote_reasons": _counts(reason for t in tickers
                                    for reason, n in (full[t]["fundamental_synthesis"].get("signal_non_vote_reasons") or {}).items()
                                    for _ in range(n)),
        "iid_coverage_fundamental": {key: (final["coverage"] or {}).get(key) for key in
                                     ("fundamental_evidence_availability", "fundamental_risk_level", "fundamental_decision_policy_version")},
    }


def _entity_family(contract: Any, head: Mapping[str, Any], final: Mapping[str, Any], official: set[str]) -> dict[str, Any]:
    compact, full, before = final["compact"], final["full"], head["full"]
    tickers = sorted(official)
    families = defaultdict(list)
    for t in tickers:
        record = compact[t]
        families[f"{record.get('analysis_family')}|{record.get('issuer_type')}"].append(t)
    by_family = {}
    for family, members in sorted(families.items()):
        by_family[family] = {
            "official_records": len(members),
            "entity_decision_applicability": _counts(contract.entity_decision_applicability(compact[t]) if compact[t].get("status") == "AVAILABLE" else None for t in members),
            "decided_by": _counts(full[t]["fundamental_synthesis"].get("source_dialect") for t in members),
            "financial_v2_votes_by_non_industrial_family": sum(
                1 for t in members if full[t]["fundamental_synthesis"].get("source_dialect") == contract.DIALECT_FINANCIAL_V2
                for s in full[t]["fundamental_synthesis"]["signals"]
                if s["decision_eligible"] and contract.entity_decision_applicability(compact[t]) != contract.ENTITY_DECISION_APPLICABLE
                and contract.SIGNALS[s["signal_id"]]["family"] not in ("BANK", "SECURITIES")),
            "fundamental_evidence_availability": _counts(full[t].get("fundamental_evidence_availability") for t in members),
        }
    unresolved = [t for t in tickers if compact[t].get("status") == "AVAILABLE"
                  and contract.entity_decision_applicability(compact[t]) == contract.ENTITY_FAMILY_UNRESOLVED]
    for family, view in by_family.items():
        if not family.startswith("INDUSTRIAL") and view["financial_v2_votes_by_non_industrial_family"]:
            raise SystemExit(f"NON_INDUSTRIAL_FAMILY_CAST_INDUSTRIAL_VOTES:{family}")
    return {
        "by_family": by_family,
        "unresolved_generic_records": {t: {"fundamental_state": [before[t]["fundamental_state"], full[t]["fundamental_state"]],
                                           "posture": [before[t]["research_action_posture"], full[t]["research_action_posture"]],
                                           "decided_by": full[t]["fundamental_synthesis"].get("source_dialect"),
                                           "research_evidence_kept": sorted(full[t]["fundamental_synthesis"].get("strengths", [])
                                                                            + full[t]["fundamental_synthesis"].get("weaknesses", [])
                                                                            + sorted((full[t]["fundamental_synthesis"].get("research_observations") or {}))),
                                           "fundamental_evidence_availability": full[t].get("fundamental_evidence_availability")}
                                       for t in unresolved},
        "consumer_finance_like_generic": {t: "F88: pawn/consumer lending issuer classified UNCLASSIFIED_GENERIC/unknown"
                                          for t in unresolved if t == "F88"},
    }


def _fiscal_audit(contract: Any, roots: Mapping[str, Path], head: Mapping[str, Any], final: Mapping[str, Any],
                  official: set[str]) -> dict[str, Any]:
    import stocklookup_core.financial.financial_v2_current_input_authority as input_authority
    authority = input_authority.resolve(ROOT)
    semantics = json.loads(authority.semantics_artifact_path.read_text(encoding="utf-8"))
    known_at = semantics.get("requested_at")
    facts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with gzip.open(authority.semantics_facts_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            end = contract._quarter_end(row.get("native_period_label"))
            if end is not None and end.isoformat() > SESSION:
                facts[row["ticker"]].append(row)
    compact, full, before = final["compact"], final["full"], head["full"]
    tickers = {}
    for ticker in sorted(facts):
        rows = facts[ticker]
        observed = sorted({str(row.get("retrieval_or_observation_timestamp")) for row in rows if row.get("retrieval_or_observation_timestamp")})
        labels = sorted({row["native_period_label"] for row in rows})
        valued = [row for row in rows if row.get("normalized_candidate_value") is not None or row.get("reported_value") is not None]
        providers = sorted({str((row.get("source_lineage") or {}).get("provider")) for row in valued})
        semantics_verdicts = {label: contract.fiscal_period_semantics(label, SESSION, known_at)["status"] for label in labels}
        record = compact.get(ticker) or {}
        features = sorted(name for name, entry in (record.get("feature_fitness") or {}).items()
                          if isinstance(entry, Mapping) and entry.get("as_of_period") in labels)
        synthesis = (full.get(ticker) or {}).get("fundamental_synthesis") or {}
        head_synthesis = (before.get(ticker) or {}).get("fundamental_synthesis") or {}
        signals = {s["signal_id"]: {"period": s["fitness"]["as_of_period"], "freshness": s["fitness"]["freshness"],
                                    "research_usable": s["research_usable"], "decision_eligible": s["decision_eligible"],
                                    "non_vote_reason": s.get("non_vote_reason")}
                   for s in synthesis.get("signals") or [] if s["fitness"]["as_of_period"] in labels}
        head_signals = {s["signal_id"]: {"research_usable": s["research_usable"], "decision_eligible": s["decision_eligible"],
                                         "exclusion": s.get("exclusion")}
                        for s in head_synthesis.get("signals") or [] if s["fitness"]["as_of_period"] in labels}
        observation_before_calendar_end = all(stamp[:10] < min(contract._quarter_end(label).isoformat() for label in labels)
                                              for stamp in observed)
        bound = max([stamp[:10] for stamp in observed] + [str(known_at)[:10]])
        tickers[ticker] = {
            "official": ticker in official, "labels": labels,
            "calendar_quarter_ends": {label: contract._quarter_end(label).isoformat() for label in labels},
            "fact_observation_timestamps": observed, "value_bearing_facts": len(valued), "value_providers": providers,
            "statement_families": _counts(row.get("statement_family") for row in valued),
            "observed_before_the_labels_calendar_end": observation_before_calendar_end,
            "knowledge_bound": bound,
            "knowledge_verdict": ("NON_CALENDAR_FISCAL_LABEL_KNOWN_BY_SESSION"
                                  if bound <= SESSION < min(contract._quarter_end(label).isoformat() for label in labels)
                                  and observation_before_calendar_end else "KNOWLEDGE_TIME_UNPROVEN"),
            "contract_verdicts": semantics_verdicts,
            "compact_features_at_these_labels": features,
            "signals_final": signals, "signals_at_head": head_signals,
            "fundamental_state": [(before.get(ticker) or {}).get("fundamental_state"), (full.get(ticker) or {}).get("fundamental_state")],
            "posture": [(before.get(ticker) or {}).get("research_action_posture"), (full.get(ticker) or {}).get("research_action_posture")],
            "any_signal_votes_at_these_labels": any(item["decision_eligible"] for item in signals.values()),
        }
    if any(item["any_signal_votes_at_these_labels"] for item in tickers.values()):
        raise SystemExit("FISCAL_LABEL_WITH_UNRESOLVED_CALENDAR_PERIOD_VOTED")
    return {
        "rule": contract.FISCAL_PERIOD_RULE, "pinned_semantics_knowledge_time": known_at,
        "session": SESSION, "records": tickers, "tickers": sorted(tickers),
        "look_ahead_violations": sorted(t for t, item in tickers.items() if item["knowledge_verdict"] != "NON_CALENDAR_FISCAL_LABEL_KNOWN_BY_SESSION"),
        "residual": ("Labels at or before the session from the same fiscal series are indistinguishable from calendar labels without a "
                     "governed fiscal-year registry (bctc_processor P0-4); their freshness may be overstated by the fiscal offset."),
    }


def _dislocation(contract: Any, adr: Any, head: Mapping[str, Any], final: Mapping[str, Any], official: set[str],
                 head_adr: Any) -> dict[str, Any]:
    tickers = sorted(official)
    before = head_adr.build_artifact(session=SESSION, integrated_product={"session": SESSION, "records": {t: head["full"][t] for t in tickers}})["records"]
    after = adr.build_artifact(session=SESSION, integrated_product={"session": SESSION, "records": {t: final["full"][t] for t in tickers}})["records"]
    # The 5729c52 rule over the final records: separates the fundamental-input effect from the
    # survivability-rule effect.
    old_rule = head_adr.build_artifact(session=SESSION, integrated_product={"session": SESSION, "records": {t: final["full"][t] for t in tickers}})["records"]
    adverse = (contract.ADVERSE_LEVEL_CURRENT, contract.ADVERSE_LEVEL_KNOWN_NOT_CURRENT)
    violations = [t for t in tickers if after[t]["primary_research_state"] == adr.QUALITY_DISLOCATION
                  and after[t]["economic_survivability_context"]["fundamental_risk_level"] in adverse]
    unknown_with_known = [t for t in tickers if "FUNDAMENTAL_EVIDENCE_UNAVAILABLE" in after[t]["missing_evidence_flags"]
                          and (after[t]["economic_survivability_context"]["fundamental_risk_level"] != contract.LEVEL_UNKNOWN
                               or after[t]["economic_survivability_context"]["fundamental_evidence_availability"]
                               not in (contract.ABSENT, contract.NOT_APPLICABLE_ENTITY))]
    if violations or unknown_with_known:
        raise SystemExit(f"DISLOCATION_INVARIANT_VIOLATED:{violations + unknown_with_known}")
    return {
        "state_distribution": {"c5729c52": _counts(r["primary_research_state"] for r in before.values()),
                               "final": _counts(r["primary_research_state"] for r in after.values())},
        "transitions": _transitions((before[t]["primary_research_state"], after[t]["primary_research_state"]) for t in tickers),
        "decomposition": {
            "fundamental_input_effect_under_5729c52_rule": _transitions(
                (before[t]["primary_research_state"], old_rule[t]["primary_research_state"]) for t in tickers),
            "survivability_rule_effect_on_final_inputs": _transitions(
                (old_rule[t]["primary_research_state"], after[t]["primary_research_state"]) for t in tickers),
            "survivability_rule_changes_by_survivability": _counts(
                f"{old_rule[t]['primary_research_state']} -> {after[t]['primary_research_state']} | {after[t]['economic_survivability_context']['survivability']}"
                for t in tickers if old_rule[t]["primary_research_state"] != after[t]["primary_research_state"]),
            "missing_flag_changes_under_rule": _counts(
                f"{sorted(old_rule[t]['missing_evidence_flags'])} -> {sorted(after[t]['missing_evidence_flags'])}"
                for t in tickers if old_rule[t]["missing_evidence_flags"] != after[t]["missing_evidence_flags"]),
        },
        "survivability_final": _counts(after[t]["economic_survivability_context"]["survivability"] for t in tickers),
        "quality_dislocation_with_adverse_level_final": len(violations),
        "fundamental_evidence_unavailable_with_known_level_final": len(unknown_with_known),
        "changed": {t: {"state": [before[t]["primary_research_state"], after[t]["primary_research_state"]],
                        "survivability": after[t]["economic_survivability_context"]["survivability"],
                        "reason_codes": after[t]["reason_codes"]}
                    for t in tickers if before[t]["primary_research_state"] != after[t]["primary_research_state"]},
    }


def _policy_epoch(contract: Any, velocity: Any, next_brief: Any, head: Mapping[str, Any], final: Mapping[str, Any],
                  official: set[str]) -> dict[str, Any]:
    """Cross-epoch comparisons on the real records: 5729c52 (previous) against final (current)."""
    tickers = sorted(official)
    before, after = head["full"], final["full"]
    labels = {t: next_brief._classify_posture_transition(before[t], after[t]) for t in tickers}
    trajectories = {}
    for t in tickers:
        history = []
        for session, record in (("2026-09-23", before[t]), (SESSION, after[t])):
            axis = velocity._axis(record, "fundamental_trajectory")
            axis["session"] = session
            history.append(axis)
        trajectories[t] = velocity._trajectory("fundamental_trajectory", history)["latest_transition"]
    changed_state = [t for t in tickers if before[t]["fundamental_state"] != after[t]["fundamental_state"]]
    masquerading = [t for t in changed_state if trajectories[t] in ("IMPROVING", "DETERIORATING")]
    if masquerading:
        raise SystemExit(f"CROSS_EPOCH_STATE_CHANGE_READ_AS_TRANSITION:{masquerading[:20]}")
    # Same-epoch control: the prior 5729c52 state re-read under the final epoch is a real transition.
    control = next(t for t in changed_state if before[t]["fundamental_state"] != "INSUFFICIENT"
                   and after[t]["fundamental_state"] != "INSUFFICIENT")
    same_epoch = velocity._trajectory("fundamental_trajectory", [
        {**velocity._axis({**before[control], "fundamental_decision_policy_version": contract.DECISION_POLICY_VERSION},
                          "fundamental_trajectory"), "session": "2026-09-23"},
        {**velocity._axis(after[control], "fundamental_trajectory"), "session": SESSION}])["latest_transition"]
    if same_epoch in ("NOT_COMPARABLE", contract.NOT_COMPARABLE_POLICY_CHANGE):
        raise SystemExit(f"SAME_EPOCH_CONTROL_NOT_COMPARED:{control}:{same_epoch}")
    return {
        "epochs": {"c5729c52": _counts(contract.policy_epoch(before[t]) for t in tickers),
                   "final": _counts(contract.policy_epoch(after[t]) for t in tickers)},
        "decision_identity_changed_for_every_record": all(after[t]["decision_identity"] != before[t]["decision_identity"] for t in tickers),
        "posture_transition_labels_5729c52_to_final": _counts(labels.values()),
        "not_comparable_policy_change": sum(label == contract.NOT_COMPARABLE_POLICY_CHANGE for label in labels.values()),
        "fundamental_state_changed_across_epochs": len(changed_state),
        "velocity_fundamental_trajectory_latest_transition": _counts(trajectories.values()),
        "velocity_cross_epoch_changes_read_as_transitions": len(masquerading),
        "same_epoch_control": {"ticker": control, "states": [before[control]["fundamental_state"], after[control]["fundamental_state"]],
                               "latest_transition": same_epoch},
        "historical_records_rewritten": False,
    }


# ── valuation and authority ──────────────────────────────────────────────────────────────────────

def _valuation_diff(runs: Mapping[str, Any], official: set[str], verdict: Mapping[str, Any]) -> dict[str, Any]:
    chain = ("c488eaf1", "c66d0fc0", "c5729c52", "final")
    pairs = list(zip(chain, chain[1:])) + [("c488eaf1", "final")]
    out: dict[str, Any] = {"pairs": {}}
    for a, b in pairs:
        va, vb = runs[a]["valuation"]["records"], runs[b]["valuation"]["records"]
        field_diffs: Counter[str] = Counter()
        peer_diffs: Counter[str] = Counter()
        stripped = sorted(t for t in vb if va[t]["stripped_digest"] != vb[t]["stripped_digest"])
        for t in vb:
            for method in VALUATION_METHODS:
                for field in VALUATION_FIELDS:
                    if va[t]["methods"][method][field] != vb[t]["methods"][method][field]:
                        field_diffs[f"{method}.{field}"] += 1
            for method in sorted(set(va[t]["peer"]) | set(vb[t]["peer"])):
                if va[t]["peer"].get(method) != vb[t]["peer"].get(method):
                    peer_diffs[method] += 1
            if va[t]["relative_research_state"] != vb[t]["relative_research_state"]:
                peer_diffs["relative_research_state"] += 1
        out["pairs"][f"{a}->{b}"] = {"identities": [runs[a]["valuation_identity"], runs[b]["valuation_identity"]],
                                     "records_differing_after_stripping_engine_lineage": len(stripped),
                                     "method_field_differences": dict(sorted(field_diffs.items())),
                                     "peer_differences": dict(sorted(peer_diffs.items()))}
        if stripped or field_diffs or peer_diffs:
            raise SystemExit(f"VALUATION_VALUE_REGRESSION:{a}->{b}:{dict(field_diffs)}:{dict(peer_diffs)}:{stripped[:10]}")
    final = runs["final"]["valuation"]["records"]
    usable = [t for t in sorted(official) if final[t]["methods"]["P/B_CURRENT_RESEARCH"]["status"] == "RESEARCH_USABLE"]
    full = runs["final"]["full"]
    contract_entry = ((verdict.get("semantic_basis_registry") or {}).get("contracts") or {}).get("VCI:balance_sheet") or {}
    checks = {
        "p_b_current_research_usable_official": len(usable),
        "nci_not_deducted_on_every_usable_row": all("NCI_NOT_DEDUCTED" in (final[t]["methods"]["P/B_CURRENT_RESEARCH"]["limitations"] or []) for t in usable),
        "research_only_on_every_usable_row": all({"CURRENT_RESEARCH_ONLY", "NOT_AUTHORITATIVE", "NOT_FOR_TARGET_PRICE"}
                                                 <= set(final[t]["methods"]["P/B_CURRENT_RESEARCH"]["limitations"] or []) for t in usable),
        "exact_p_b_status_official": _counts(final[t]["methods"]["P/B"]["status"] for t in sorted(official)),
        "unknown_scope_peer_ready": sum(str(final[t]["methods"]["P/B_CURRENT_RESEARCH"]["statement_scope"]).lower() in ("unknown", "none")
                                        and (final[t]["peer"].get("P/B_CURRENT_RESEARCH") or {}).get("status") == "READY_RESEARCH_ONLY"
                                        for t in usable),
        "integrated_pb_multiple_labelled_research_only": sum(
            (full[t]["valuation_context_summary"].get("pb_basis") or {}).get("claim") == "RESEARCH_ONLY_NOT_EXACT_NOT_COMMON_SHAREHOLDER"
            and "NCI_NOT_DEDUCTED" in (full[t]["valuation_context_summary"]["pb_basis"].get("limitations") or [])
            and "P_B_IS_RESEARCH_TOTAL_EQUITY_NCI_NOT_DEDUCTED_NOT_COMMON_SHAREHOLDER" in (full[t]["valuation_context_summary"].get("limitations") or [])
            for t in usable),
        "integrated_pb_multiple_value_equals_research_value": sum(full[t]["valuation_context_summary"].get("pb_multiple")
                                                                  == final[t]["methods"]["P/B_CURRENT_RESEARCH"]["value"] for t in usable),
        "vci_balance_sheet_verdict": contract_entry.get("verdict"),
        "status_distribution_official": {method: _counts(final[t]["methods"][method]["status"] for t in sorted(official))
                                         for method in VALUATION_METHODS},
    }
    if (not checks["nci_not_deducted_on_every_usable_row"] or not checks["research_only_on_every_usable_row"]
            or checks["unknown_scope_peer_ready"] or checks["integrated_pb_multiple_labelled_research_only"] != len(usable)
            or checks["integrated_pb_multiple_value_equals_research_value"] != len(usable)):
        raise SystemExit(f"P_B_RESEARCH_LABEL_OR_SCOPE_REGRESSION:{checks}")
    out["checks"] = checks
    return out


def _authority(contract: Any, roots: Mapping[str, Path], head: Mapping[str, Any], final: Mapping[str, Any],
               attempted: set[str]) -> dict[str, Any]:
    import stocklookup_core.financial.financial_v2_current_input_authority as input_authority
    authority = input_authority.resolve(ROOT)
    pinned = [authority.semantics_artifact_path, authority.semantics_facts_path, authority.feature_store_artifact_path,
              authority.feature_store_records_path, authority.classification_diagnostics_path, authority.industry_snapshot_path]
    relative = [(path.resolve().relative_to(ROOT) if path.is_absolute() else path).as_posix() for path in pinned]
    tracked = (convergence._git(ROOT, "ls-files", *relative) or "").splitlines()
    ignored = (convergence._git(ROOT, "check-ignore", "--no-index", *relative) or "").splitlines()
    head_hash = {path: convergence._git(roots["c5729c52"], "rev-parse", f"HEAD:{path}") for path in relative}
    final_hash = {path: convergence._git(ROOT, "hash-object", path) for path in relative}
    full_before, full_after = head["full"], final["full"]
    unchanged_fields = {
        "exact_capabilities_unavailable": sum(full_before[t]["exact_capabilities_unavailable"] != full_after[t]["exact_capabilities_unavailable"] for t in attempted),
        "authority_boundary": sum(full_before[t]["authority_boundary"] != full_after[t]["authority_boundary"] for t in attempted),
        "trigger": sum(full_before[t]["trigger"] != full_after[t]["trigger"] for t in attempted),
        "invalidation": sum(full_before[t]["invalidation"] != full_after[t]["invalidation"] for t in attempted),
        "evidence_currency": sum(full_before[t]["evidence_currency"] != full_after[t]["evidence_currency"] for t in attempted),
        "compact_pit_authority": sum((head["compact"][t].get("pit_authority"), head["compact"][t].get("is_actionable"))
                                     != (final["compact"][t].get("pit_authority"), final["compact"][t].get("is_actionable")) for t in attempted),
    }
    scratch = {}
    for module in CHANGED_PRODUCTION_MODULES:
        text = (ROOT / module).read_text(encoding="utf-8")
        hits = [fragment for fragment in _FORBIDDEN_PATH_FRAGMENTS if fragment in text]
        if hits:
            scratch[module] = hits
    result = {
        "current_research_only": True, "provider_or_data_authority_promoted": False, "financial_data_acquired": False,
        "provider_calls": 0, "network_audit_events": 0, "vnstock_enabled": False, "vnstock_imported_by_any_run": False,
        "pinned_financial_v2_authority_version": authority.authority_version,
        "pinned_files_force_tracked": sorted(tracked) == sorted(relative),
        "pinned_files_under_ignore_rules_so_force_tracked": sorted(ignored),
        "pinned_files_identical_to_5729c52": head_hash == final_hash,
        "pinned_identities_verified_by_engine_build": True,
        "engine_change": "lineage only: period_semantics_knowledge_time in source_identities (no value, state or feature changed)",
        "decision_record_fields_unchanged_5729c52_to_final": unchanged_fields,
        "pit_raw_as_traded_execution_sizing_authority_changed": any(unchanged_fields.values()),
        "exact_valuation_authority": False, "historical_pit_financial_authority": False,
        "execution_or_sizing_authority": False, "posture_thresholds_or_branch_order_changed": False,
        "changed_modules_scratch_or_worktree_path_references": scratch,
        "publication": "NONE",
    }
    if (not result["pinned_files_force_tracked"] or not result["pinned_files_identical_to_5729c52"]
            or result["pit_raw_as_traded_execution_sizing_authority_changed"] or scratch):
        raise SystemExit(f"AUTHORITY_BOUNDARY_VIOLATION:{result}")
    return result


# ── summary ──────────────────────────────────────────────────────────────────────────────────────

def _summary(result: Mapping[str, Any]) -> str:
    d = result["denominators"]
    f = result["cloud_findings"]
    ladder = result["ladder"]["stages"]
    ledgers = result["posture_ledgers"]
    dist = result["distributions"]
    val = result["valuation_value_diff"]
    lines = [
        "# Current Research fundamental promotion hardening (retained 2026-09-24)", "",
        f"Proof: `{result['artifact_identity']}`",
        f"Checkpoints 488eaf1 / 66d0fc0 / 5729c52 each reproduce their recorded Integrated Decision identity; "
        f"L0 (every correction neutralised) reproduces 5729c52's state and posture for all {d[ATTEMPTED]} tickers.",
        f"Denominators: attempted {d[ATTEMPTED]}; official {d[OFFICIAL]}; priced official {d[PRICED]}.", "",
        "## Cloud findings on the exact local head (5729c52)", "",
    ]
    for key, value in f.items():
        compact = {k: v for k, v in value.items() if k not in ("why_now_claims_tickers", "tickers", "records_with_post_session_labels",
                                                                "direction_x_resolved_level", "analysis_family_issuer_type")}
        lines.append(f"- **{key}**: {compact}")
    lines += ["", "## Ladder (5729c52 -> final, official)", ""]
    for stage, view in ladder.items():
        lines.append(f"- {stage} ({view['correction']}): states {view['fundamental_state_changes_official']} "
                     f"{view['fundamental_state_transitions']}; postures {view['posture_changes_official']} {view['posture_transitions']}")
    lines += ["", "## Posture ledgers", "",
              f"- pairwise (official): {ledgers['pairwise_counts_official']}",
              f"- 5729c52 -> final: {ledgers['c5729c52_to_final']['count_official']} {ledgers['c5729c52_to_final']['transitions']}; "
              f"by correction {ledgers['c5729c52_to_final']['by_ladder_correction']}",
              f"- 488eaf1 -> final: {ledgers['c488eaf1_to_final']['count_official']} {ledgers['c488eaf1_to_final']['transitions']}",
              f"- 66d0fc0 -> final: {ledgers['c66d0fc0_to_final']['count_official']}",
              f"- the predecessor's 177: { {k: v for k, v in ledgers['predecessor_177'].items() if k != 'removed_tickers'}}",
              "- unexplained: none", "",
              "## Distributions (final, official)", "",
              f"- evidence availability: {dist['fundamental_evidence_availability']}",
              f"- risk level: {dist['fundamental_risk_level']}",
              f"- fundamental state: {dist['fundamental_state']}",
              f"- policy version: {dist['fundamental_decision_policy_version']}",
              f"- axis blockers: {dist['axis_blockers']}",
              f"- non-vote reasons: {dist['non_vote_reasons']}; vote grouping: {dist['vote_grouping_outcomes']}", "",
              "## Entity family", "", f"- unresolved generic: {result['entity_applicability']['unresolved_generic_records']}", "",
              "## Fiscal-period audit", "",
              f"- tickers {result['fiscal_period_audit']['tickers']}; look-ahead violations {result['fiscal_period_audit']['look_ahead_violations']}; "
              f"knowledge time {result['fiscal_period_audit']['pinned_semantics_knowledge_time']}", "",
              "## Asymmetric dislocation", "",
              f"- {result['asymmetric_dislocation']['state_distribution']}; transitions {result['asymmetric_dislocation']['transitions']}", "",
              "## Policy epoch", "", f"- {result['policy_epoch']}", "",
              "## Valuation value-level diff", "",
              f"- {[(k, v['records_differing_after_stripping_engine_lineage']) for k, v in val['pairs'].items()]}",
              f"- checks: {val['checks']}", "",
              "## Authority", "", f"- {result['authority_boundary']}", "",
              "Retained evidence SHA-256 unchanged; zero provider calls, network audit events, provider-module imports, "
              "runtime-store reads and write-guard violations in every run.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prove", "summarize"):
        one = sub.add_parser(name)
        one.add_argument("--producer-root", required=True)
        for checkpoint in CHECKPOINTS:
            one.add_argument(f"--{checkpoint}-code-root", dest=f"{checkpoint}_code_root", required=True)
        one.add_argument("--work-root", required=True)
        one.add_argument("--output-dir", required=True)
    inner = sub.add_parser("assemble")
    inner.add_argument("--code-root", required=True)
    inner.add_argument("--producer-root", required=True)
    inner.add_argument("--work-root", required=True)
    inner.add_argument("--session", required=True)
    inner.add_argument("--corrections", default=None)
    args = parser.parse_args()
    if args.command == "assemble":
        assemble(args)
        return
    result = prove(args) if args.command == "prove" else summarize(args)
    print(json.dumps({"artifact_identity": result["artifact_identity"], "denominators": result["denominators"],
                      "ledgers": result["posture_ledgers"]["pairwise_counts_official"]}, sort_keys=True))


if __name__ == "__main__":
    main()
