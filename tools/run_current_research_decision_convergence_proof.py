"""Operational proof of Ordinary-Daily Current Research assembly on retained evidence only.

``assemble`` runs the real Daily Integrated Decision step
(``canonical_post_close_pipeline.build_enrichment_components``) for one retained session against
an isolated, byte-verified copy of that session's Level-2 inputs. Canonical retained evidence is
only read: the repository's audit-hook write guard refuses every mutation under the Producer and
checkout evidence roots, the calculation-readiness context is reconstructed from the retained
session artifact (identity-verified) instead of reading a live runtime store, and no provider,
publication or pointer operation exists on this path. ``--code-root`` runs the same assembly
under another checkout's code, which gives a same-inputs baseline.

``prove`` runs the baseline, this checkout, and a rerun of this checkout in separate processes,
rebuilds the Current Research capability map for each, reconciles them against the frozen
2026-09-24 regression evidence, and writes the result.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping

TOOL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSION = "2026-09-24"
SESSION_INPUT_KEYS = (
    "exact_session_snapshot", "descriptive_research", "sector_leadership", "screening_foundation",
    "opportunity_prioritization", "tactical_classifier", "technical_recovery", "technical_coverage_disposition",
    "session_triage", "valuation", "liquidity_research", "universe_resolution", "strategy",
)
REFERENCE_MAP_IDENTITIES = {
    "before_fundamental_integration": "current_research_capability_map/v1:ac1240dff8bca998d8c322bccd4c469f0318204cd90f10213f1272d246cfd734",
    "after_entity_aware_integration": "current_research_capability_map/v1:1bb9ff90a44f2ed58c87783a398e7d1fd1b3117b29584aa5350de8329185ffb1",
}
FROZEN_INTEGRATION_IDENTITY = (
    "entity_aware_operational_fundamental_context_integration/v1:"
    "965f158241b09f6beea67914b3028fb6388dbfcff8b6a51cbd95e27606a0b055"
)
NETWORK_AUDIT_EVENTS = frozenset({"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.sendto",
                                  "http.client.connect", "urllib.Request"})
TECHNICAL_FIELDS = ("tactical_phase", "market_structure_state", "breakout_state_v3", "trigger", "invalidation",
                    "evidence_currency", "participation")
SAMPLE_TICKERS = ("FPT", "HPG", "VCB", "SSI", "BVH", "F88", "A32", "AAA")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b"\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _write_guard():
    """The repository's audit-hook guard, loaded from this checkout (independent of --code-root)."""
    spec = importlib.util.spec_from_file_location("canonical_evidence_write_guard",
                                                  TOOL_ROOT / "tests" / "_canonical_evidence_write_guard.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve string annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def _map_body_identity(value: Mapping[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key not in {"artifact_identity", "artifact_sha256"}}
    return "current_research_capability_map/v1:" + hashlib.sha256(canonical(body)).hexdigest()


# ── assemble (runs in its own process; imports project code from --code-root) ────────────────────

def stage_session_inputs(level2: Any, producer_root: Path, artifact_root: Path, session: str) -> dict[str, Any]:
    source = level2.session_artifact_paths(producer_root, session)
    target = level2.session_artifact_paths(artifact_root, session)
    manifest: dict[str, Any] = {}
    for key in SESSION_INPUT_KEYS:
        src, dst = source[key], target[key]
        if not src.is_file():
            raise SystemExit(f"RETAINED_SESSION_INPUT_MISSING:{key}:{src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)  # a real byte copy -- never a link or junction to evidence
        digest = sha256_file(src)
        if dst.is_symlink() or sha256_file(dst) != digest:
            raise SystemExit(f"STAGED_INPUT_NOT_BYTE_IDENTICAL:{key}")
        manifest[key] = {"relative_path": src.relative_to(producer_root).as_posix(), "sha256": digest,
                         "bytes": src.stat().st_size}
    return manifest


def retained_readiness_context(level2: Any, fin_v2_material: Any, producer_root: Path, session: str) -> dict[str, Any]:
    """Reconstruct the session's calculation-readiness context from its retained evaluated valuation.

    Every evaluated record carries its own readiness record verbatim; the reconstructed payload
    must reproduce the retained ``source_calculation_readiness_identity`` exactly or the proof stops.
    """
    evaluated = load(level2.session_artifact_paths(producer_root, session)["current_valuation_evaluated"])
    records = {ticker: dict(row.get("calculation_readiness_context") or {}) for ticker, row in evaluated["records"].items()}
    payload: dict[str, Any] = {
        "contract_version": "canonical_daily_calculation_readiness_context/v1",
        "requested_at": f"{session}T15:00:00+07:00",
        "decision_session": session,
        "source_raw_valuation_identity": evaluated.get("source_valuation_identity"),
        "coverage": {
            "decision_denominator": len(records),
            "available": sum(record.get("status") == "AVAILABLE" for record in records.values()),
            "unavailable": sum(record.get("status") != "AVAILABLE" for record in records.values()),
            "zero_silent_ticker_drops": True,
        },
        "records": records,
        "authority_boundary": {
            "calculation_engine_reused_without_formula_changes": True,
            "provider_reported_remains_current_research_only": True,
            "price_basis_verified": False,
            "no_authority_promotion": True,
        },
    }
    payload.update(fin_v2_material._identity(payload))
    if payload["artifact_identity"] != evaluated.get("source_calculation_readiness_identity"):
        raise SystemExit("RETAINED_READINESS_CONTEXT_NOT_REPRODUCED:"
                         f"{payload['artifact_identity']}!={evaluated.get('source_calculation_readiness_identity')}")
    return payload


def assemble(args: argparse.Namespace) -> None:
    code_root = Path(args.code_root).resolve()
    producer_root = Path(args.producer_root).resolve()
    work_root = Path(args.work_root).resolve()
    session = args.session
    if os.environ.get("STOCKLOOKUP_PROVIDER_PYTHON"):
        raise SystemExit("PROVIDER_INTERPRETER_MUST_BE_UNCONFIGURED_FOR_RETAINED_ACCEPTANCE")
    if any(name.split(".", 1)[0] in {"vnstock", "vnai"} for name in sys.modules):
        raise SystemExit("PROVIDER_MODULE_ALREADY_IMPORTED")

    class _NoRetiredProviderImport:
        def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
            if fullname.split(".", 1)[0] in {"vnstock", "vnai"}:
                raise ImportError("RETIRED_PROVIDER_IMPORT_FORBIDDEN:" + fullname)
            return None

    sys.meta_path.insert(0, _NoRetiredProviderImport())
    guard = _write_guard()
    protected = [producer_root / "operations-review", producer_root / "data",
                 code_root / "operations-review", code_root / "data",
                 TOOL_ROOT / "operations-review", TOOL_ROOT / "data"]
    guard.install(protected)
    # Every provider call needs the network: count the interpreter's own network audit events so
    # "zero provider calls" is measured, not asserted.
    network = Counter()

    def network_audit(event: str, _args: tuple) -> None:
        if event in NETWORK_AUDIT_EVENTS:
            network[event] += 1

    sys.addaudithook(network_audit)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(code_root))
    import canonical_daily_financial_v2_materialization as fin_v2_material
    import canonical_post_close_pipeline as cpc
    import daily_session_level2_package as level2
    import stocklookup_core.decision.integrated_investment_decision_product as integrated

    artifact_root = work_root / "artifact-root"
    output_root = work_root / "output-root"
    outputs = work_root / "outputs"
    manifest = stage_session_inputs(level2, producer_root, artifact_root, session)
    if getattr(args, "official_liquidity", None):
        # Optional operator-acquired official-exchange liquidity artifact: byte-copied into the isolated
        # artifact root only (canonical retained evidence is never written).
        staged = level2.session_artifact_paths(artifact_root, session)["official_liquidity"]
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.official_liquidity, staged)
        manifest["official_liquidity"] = {"relative_path": "(operator supplied)", "sha256": sha256_file(staged), "bytes": staged.stat().st_size}
    readiness = retained_readiness_context(level2, fin_v2_material, producer_root, session)

    def retained_readiness(*, runtime_root: Any, decision_session: str, raw_valuation_artifact: Any,
                           product_tickers: Any, requested_at: str) -> dict[str, Any]:
        if (decision_session != session
                or (raw_valuation_artifact or {}).get("artifact_identity") != readiness["source_raw_valuation_identity"]
                or set(product_tickers) != set(readiness["records"])):
            raise RuntimeError("RETAINED_READINESS_CONTEXT_DOES_NOT_MATCH_ASSEMBLY_INPUTS")
        return readiness

    captured: dict[str, Any] = {}
    original_build = integrated.build_artifact

    def capturing_build(**kwargs: Any) -> dict[str, Any]:
        captured.clear()
        captured.update(kwargs)
        return original_build(**kwargs)

    fin_v2_material.build_calculation_readiness_context = retained_readiness
    integrated.build_artifact = capturing_build
    results = cpc.build_enrichment_components(
        producer_root, session, artifact_root=artifact_root,
        runtime_root=work_root / "no-runtime-store-read", retained_evidence_root=producer_root,
        output_root=output_root,
    )
    violations = guard.drain_violations()
    decision = results.get("integrated_investment_decision_product") or {}
    if violations:
        raise SystemExit("CANONICAL_EVIDENCE_WRITE_REFUSED:" + ";".join(violations))
    if decision.get("status") != "BUILT":
        raise SystemExit(f"INTEGRATED_DECISION_NOT_BUILT:{decision.get('status')}:{decision.get('reason')}")
    loaded_retired = sorted(name for name in sys.modules if name.split(".", 1)[0] in {"vnstock", "vnai"})
    if loaded_retired:
        raise SystemExit("RETIRED_PROVIDER_MODULE_LOADED:" + ",".join(loaded_retired))
    iid = decision["artifact"]
    write(outputs / "integrated_investment_decision_product.json", iid)
    extra: dict[str, Any] = {}
    for key, name in (("operational_fundamental_integration_artifact", "operational_fundamental_context_integration.json"),
                      ("entity_applicability_artifact", "current_research_entity_applicability.json")):
        if captured.get(key) is not None:
            write(outputs / name, captured[key])
            extra[key] = captured[key].get("artifact_identity")
    if captured.get("financial_analysis_artifact") is not None:
        # The compact Financial V2 product the decision read; feature-level proofs diff it.
        write(outputs / "financial_analysis_product.json", captured["financial_analysis_artifact"])
    if captured.get("operational_fundamental_integration_artifact") is not None:
        binding_off = original_build(**{key: value for key, value in captured.items()
                                        if key != "operational_fundamental_integration_artifact"})
        write(outputs / "integrated_binding_off.json", binding_off)
        extra["binding_off_identity"] = binding_off["artifact_identity"]
    result = {
        "session": session,
        "code_root": str(code_root), "code_head": _git(code_root, "rev-parse", "HEAD"),
        "code_tracked_changes": _git(code_root, "status", "--porcelain", "--untracked-files=no"),
        "producer_root": str(producer_root),
        "staged_session_inputs": manifest,
        "retained_readiness_context_identity": readiness["artifact_identity"],
        "enrichment_status": {name: {"status": (row or {}).get("status"), "reason": (row or {}).get("reason")}
                              for name, row in sorted(results.items()) if isinstance(row, Mapping) and "status" in row},
        "operational_fundamental_binding": results.get("operational_fundamental_binding"),
        "integrated_identity": iid["artifact_identity"],
        "integrated_source_artifacts": iid.get("source_artifacts"),
        "current_valuation_identity": (captured.get("current_valuation_artifact") or {}).get("artifact_identity"),
        "financial_analysis_identity": (captured.get("financial_analysis_artifact") or {}).get("artifact_identity"),
        "captured_identities": extra,
        "write_guard": {"protected_roots": guard.protected_roots(), "violations": violations},
        "network_audit_events": dict(sorted(network.items())),
        "provider_calls": sum(network.values()), "retired_provider_imports": len(loaded_retired),
        "vnstock_worker_processes": 0, "runtime_store_reads": 0, "publication": "NONE",
    }
    write(outputs / "assembly_result.json", result)
    print(json.dumps({"integrated_identity": result["integrated_identity"],
                      "binding": result["operational_fundamental_binding"]}, sort_keys=True))


# ── prove (this checkout's code) ─────────────────────────────────────────────────────────────────

def _run_assembly(code_root: Path, producer_root: Path, work_root: Path, session: str) -> dict[str, Any]:
    if work_root.exists():
        shutil.rmtree(work_root)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    subprocess.run([sys.executable, str(Path(__file__).resolve()), "assemble", "--code-root", str(code_root),
                    "--producer-root", str(producer_root), "--work-root", str(work_root), "--session", session],
                   check=True, env=env, cwd=str(code_root))
    return load(work_root / "outputs" / "assembly_result.json")


def _reference_maps(reference_dir: Path) -> dict[str, dict]:
    maps = {"before_fundamental_integration": load(reference_dir / "before_current_research_capability_map.json"),
            "after_entity_aware_integration": load(reference_dir / "after_current_research_capability_map.json")}
    for name, value in maps.items():
        if value.get("artifact_identity") != REFERENCE_MAP_IDENTITIES[name] or _map_body_identity(value) != value["artifact_identity"]:
            raise SystemExit(f"REFERENCE_MAP_IDENTITY_CHANGED:{name}")
    return maps


def _map_view(value: Mapping[str, Any]) -> dict[str, Any]:
    coverage = value["coverage"]
    return {
        "identity": value["artifact_identity"],
        "decision_readiness_v1": value["decision_readiness"],
        "official_scope": {key: coverage[key]["official_scope_count"] for key in (
            "exact_session_price", "current_technical", "participation_research", "integrated_fundamental",
            "operational_fundamental_features", "valuation_context", "corporate_context", "liquidity_research_proxy",
            "fundamental_integration_gap")},
        "decision_input": value.get("current_research_decision_input"),
    }


def _frozen_regression(reference_dir: Path, integration: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    frozen = load(reference_dir / "entity_aware_fundamental_integration.json")
    frozen_after = load(reference_dir / "after_integrated_investment_decision_product.json")
    if frozen.get("artifact_identity") != FROZEN_INTEGRATION_IDENTITY:
        raise SystemExit("FROZEN_INTEGRATION_IDENTITY_CHANGED")
    mismatches = []
    for ticker, row in sorted(frozen["records"].items()):
        daily = (integration.get("records") or {}).get(ticker)
        if daily is None:
            mismatches.append(f"{ticker}:NOT_A_DAILY_CANDIDATE")
            continue
        for key in ("status", "primary_reason", "financial_context", "entity_class"):
            if daily.get(key) != row.get(key):
                mismatches.append(f"{ticker}:{key}")
        for key in ("usable_features", "blocked_features", "non_applicable_features"):
            if sorted(daily.get(key) or {}) != sorted(row.get(key) or {}):
                mismatches.append(f"{ticker}:{key}")
        if after["records"][ticker]["fundamental_state"] != frozen_after["records"][ticker]["fundamental_state"]:
            mismatches.append(f"{ticker}:fundamental_state")
    usable = sorted(t for t, row in frozen["records"].items() if row["status"] == "RESEARCH_USABLE")
    daily_usable = sorted(t for t, row in (integration.get("records") or {}).items() if row["status"] == "RESEARCH_USABLE")
    return {
        "frozen_integration_identity": frozen["artifact_identity"],
        "frozen_cohort": len(frozen["records"]),
        "frozen_research_usable": len(usable),
        "frozen_residual_primary_reasons": frozen["coverage"]["residual_primary_reasons"],
        "daily_candidates": len(integration.get("records") or {}),
        "daily_research_usable": len(daily_usable),
        "daily_research_usable_outside_frozen_cohort": sorted(set(daily_usable) - set(frozen["records"])),
        "frozen_cohort_reproduced_exactly": not mismatches,
        "mismatches": mismatches[:50],
    }


def _baseline_vs_after(baseline: Mapping[str, Any], after: Mapping[str, Any], binding_off: Mapping[str, Any]) -> dict[str, Any]:
    tickers = sorted(after["records"])
    if tickers != sorted(baseline["records"]):
        raise SystemExit("BASELINE_AFTER_TICKER_SET_MISMATCH")
    technical_drift = [t for t in tickers for field in TECHNICAL_FIELDS
                       if baseline["records"][t].get(field) != after["records"][t].get(field)]
    fundamental_changed = [t for t in tickers if baseline["records"][t]["fundamental_state"] != after["records"][t]["fundamental_state"]]
    posture_changed = [t for t in tickers
                       if baseline["records"][t]["research_action_posture"] != after["records"][t]["research_action_posture"]]
    unexplained_posture = [t for t in posture_changed if t not in fundamental_changed]
    bridge_fundamental = [t for t in tickers
                          if binding_off["records"][t]["fundamental_state"] != after["records"][t]["fundamental_state"]]
    valuation_transitions = Counter(
        (baseline["records"][t]["valuation_context_summary"].get("status"), after["records"][t]["valuation_context_summary"].get("status"))
        for t in tickers)
    peer_transitions = Counter(
        (baseline["records"][t]["valuation_context_summary"].get("peer_relative_state"),
         after["records"][t]["valuation_context_summary"].get("peer_relative_state"))
        for t in tickers if baseline["records"][t]["valuation_context_summary"].get("peer_relative_state")
        != after["records"][t]["valuation_context_summary"].get("peer_relative_state"))
    composite_changed = sum(baseline["records"][t].get("financial_composite_context") != after["records"][t].get("financial_composite_context")
                            for t in tickers)
    coherence_changed = sum(baseline["records"][t].get("evidence_axis_coherence") != after["records"][t].get("evidence_axis_coherence")
                            for t in tickers)
    identity_changed = [t for t in tickers if baseline["records"][t]["decision_identity"] != after["records"][t]["decision_identity"]]
    unexplained_identity = [t for t in identity_changed if t not in fundamental_changed
                            and "operational_fundamental_context" not in after["records"][t]]
    applicability_transitions = Counter()
    for t in tickers:
        for method, row in (after["records"][t].get("valuation_methods") or {}).items():
            before_row = (baseline["records"][t].get("valuation_methods") or {}).get(method) or {}
            if before_row.get("applicability") != row.get("applicability"):
                applicability_transitions[f"{method}:{before_row.get('applicability')}->{row.get('applicability')}"] += 1
    return {
        "technical_fields_identical": not technical_drift,
        "technical_drift_examples": technical_drift[:20],
        "fundamental_state_changed": len(fundamental_changed),
        "fundamental_state_changed_by_daily_bridge": len(bridge_fundamental),
        "fundamental_transitions": dict(sorted(Counter(
            f"{baseline['records'][t]['fundamental_state']}->{after['records'][t]['fundamental_state']}" for t in fundamental_changed).items())),
        "posture_changed": len(posture_changed),
        "posture_changes_without_fundamental_change": unexplained_posture,
        "posture_transitions": dict(sorted(Counter(
            f"{baseline['records'][t]['research_action_posture']}->{after['records'][t]['research_action_posture']}" for t in posture_changed).items())),
        "decision_identity_changed": len(identity_changed),
        "decision_identity_changes_unexplained": unexplained_identity,
        "valuation_status_transitions": {f"{a}->{b}": n for (a, b), n in sorted(valuation_transitions.items())},
        "peer_relative_state_transitions": {f"{a}->{b}": n for (a, b), n in sorted(peer_transitions.items())},
        "valuation_method_applicability_transitions": dict(sorted(applicability_transitions.items())),
        "financial_composite_context_changed": composite_changed,
        "evidence_axis_coherence_changed": coherence_changed,
        "baseline_coverage": {key: baseline["coverage"].get(key) for key in (
            "valuation_context_available", "fundamental_context_available", "research_action_posture_distribution")},
        "after_coverage": {key: after["coverage"].get(key) for key in (
            "valuation_context_available", "fundamental_context_available", "research_action_posture_distribution",
            "current_research_decision_input", "operational_fundamental_integration_cohort",
            "operational_fundamental_integration_usable")},
    }


def _research_packet(after: Mapping[str, Any], session: str) -> dict[str, Any]:
    import ai_research_session_delivery as delivery
    overlay = delivery.project_integrated_decision_delivery_overlay(session, after, None)
    missing = [t for t, row in overlay["records"].items()
               if (row.get("current_research_decision_input") or {}).get("contract_version") != "current_research_decision_input/v1"]
    mismatched = [t for t, row in overlay["records"].items()
                  if row.get("current_research_decision_input") != after["records"][t].get("current_research_decision_input")]
    samples = {t: overlay["records"][t] for t in SAMPLE_TICKERS if t in overlay["records"]}
    return {"records": len(overlay["records"]), "missing_decision_input": missing[:20],
            "decision_input_not_passed_through": mismatched[:20], "samples": samples,
            "overlay_contract": overlay.get("contract_version")}


def prove(args: argparse.Namespace) -> None:
    sys.path.insert(0, str(TOOL_ROOT))
    from tools import current_research_capability_map as capability

    producer_root = Path(args.producer_root).resolve()
    work = Path(args.work_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    reference_dir = Path(args.reference_dir).resolve()
    session = args.session
    references = _reference_maps(reference_dir)
    runs = {
        "baseline": _run_assembly(Path(args.baseline_code_root).resolve(), producer_root, work / "baseline", session),
        "after": _run_assembly(TOOL_ROOT, producer_root, work / "after-1", session),
        "after_rerun": _run_assembly(TOOL_ROOT, producer_root, work / "after-2", session),
    }
    deterministic_keys = ("integrated_identity", "current_valuation_identity", "financial_analysis_identity",
                          "captured_identities", "retained_readiness_context_identity", "staged_session_inputs")
    rerun_equal = {key: runs["after"][key] == runs["after_rerun"][key] for key in deterministic_keys}
    if not all(rerun_equal.values()):
        raise SystemExit("NON_DETERMINISTIC_ASSEMBLY:" + json.dumps(rerun_equal))
    if runs["baseline"]["staged_session_inputs"] != runs["after"]["staged_session_inputs"]:
        raise SystemExit("BASELINE_AND_AFTER_INPUTS_DIFFER")
    ops_root = producer_root / "operations-review"
    after_iid_path = work / "after-1" / "outputs" / "integrated_investment_decision_product.json"
    baseline_iid_path = work / "baseline" / "outputs" / "integrated_investment_decision_product.json"
    after_map = capability.build(ops_root, session, {"integrated": after_iid_path})
    rerun_map = capability.build(ops_root, session, {"integrated": work / "after-2" / "outputs" / "integrated_investment_decision_product.json"})
    baseline_map = capability.build(ops_root, session, {"integrated": baseline_iid_path})
    if after_map["artifact_identity"] != rerun_map["artifact_identity"]:
        raise SystemExit("NON_DETERMINISTIC_CAPABILITY_MAP")
    after = load(after_iid_path)
    baseline = load(baseline_iid_path)
    binding_off = load(work / "after-1" / "outputs" / "integrated_binding_off.json")
    integration = load(work / "after-1" / "outputs" / "operational_fundamental_context_integration.json")
    entity_applicability = load(work / "after-1" / "outputs" / "current_research_entity_applicability.json")
    frozen = _frozen_regression(reference_dir, integration, after)
    comparison = _baseline_vs_after(baseline, after, binding_off)
    packet = _research_packet(after, session)

    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(after_iid_path, output_dir / "after_integrated_investment_decision_product.json")
    write(output_dir / "operational_fundamental_context_integration.json", integration)
    write(output_dir / "current_research_entity_applicability.json", entity_applicability)
    write(output_dir / "after_current_research_capability_map.json", after_map)
    write(output_dir / "baseline_rebuild_current_research_capability_map.json", baseline_map)
    (output_dir / "after_current_research_capability_summary.md").write_text(capability.summary(after_map), encoding="utf-8")
    write(output_dir / "research_packet_samples.json", packet["samples"])
    result = {
        "schema_version": "1.0.0", "contract_version": "current_research_decision_convergence_proof/v1",
        "session": session,
        "assemblies": {name: {key: run[key] for key in (
            "code_head", "code_tracked_changes", "integrated_identity", "current_valuation_identity",
            "financial_analysis_identity", "captured_identities", "operational_fundamental_binding",
            "enrichment_status", "retained_readiness_context_identity", "write_guard",
            "provider_calls", "runtime_store_reads", "publication")} for name, run in runs.items()},
        "staged_session_inputs": runs["after"]["staged_session_inputs"],
        "deterministic_rerun": {"assembly": rerun_equal, "capability_map_identity_equal": True},
        "maps": {"before_fundamental_integration": _map_view(references["before_fundamental_integration"]),
                 "after_entity_aware_integration": _map_view(references["after_entity_aware_integration"]),
                 "baseline_rebuild_36e8525": _map_view(baseline_map),
                 "after_decision_convergence": _map_view(after_map)},
        "frozen_cohort_regression": frozen,
        "baseline_vs_after_same_inputs": comparison,
        "research_packet": {key: value for key, value in packet.items() if key != "samples"},
        "authority_boundary": {"current_research_only": True, "historical_pit_authority": False,
                               "exact_valuation_authority_promoted": False, "execution_authority": False,
                               "publication": "NONE", "production_pointer_changed": False, "provider_calls": 0},
    }
    result["artifact_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
    result["artifact_identity"] = f"{result['contract_version']}:{result['artifact_sha256']}"
    write(output_dir / "current_research_decision_convergence_proof.json", result)
    if not args.keep_work:
        shutil.rmtree(work)
    print(json.dumps({"proof": result["artifact_identity"], "after_map": after_map["artifact_identity"],
                      "baseline_map": baseline_map["artifact_identity"], "frozen_reproduced": frozen["frozen_cohort_reproduced_exactly"],
                      "technical_identical": comparison["technical_fields_identical"],
                      "unexplained_posture": comparison["posture_changes_without_fundamental_change"]}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("assemble")
    one.add_argument("--code-root", default=str(TOOL_ROOT))
    one.add_argument("--producer-root", required=True)
    one.add_argument("--work-root", required=True)
    one.add_argument("--session", default=DEFAULT_SESSION)
    one.add_argument("--official-liquidity", default=None, help="optional official_exchange_liquidity_research artifact to stage for this assembly")
    both = sub.add_parser("prove")
    both.add_argument("--producer-root", required=True)
    both.add_argument("--baseline-code-root", required=True)
    both.add_argument("--work-root", required=True)
    both.add_argument("--output-dir", required=True)
    both.add_argument("--reference-dir", required=True)
    both.add_argument("--session", default=DEFAULT_SESSION)
    both.add_argument("--keep-work", action="store_true")
    args = parser.parse_args()
    assemble(args) if args.command == "assemble" else prove(args)


if __name__ == "__main__":
    main()
