"""Hermetic zero-active Vnstock contract audit. Emits metadata only, never provider payloads."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_BASE_SHA = "3137441656019e4b7974978f034915d361b5c307"
ENTRYPOINTS = (
    "stocklookup", "tools.run_owner_daily", "canonical_daily_operation",
    "canonical_post_close_pipeline", "daily_session_level2_package",
    "canonical_daily_financial_v2_materialization", "current_research_decision_input",
    "stocklookup_core.valuation.current_research_valuation_context", "current_corporate_event_context",
    "official_liquidity_market_wide", "prospective_pit_evidence_analysis",
    "dnse_prospective_pit_shadow", "execution_capacity_research", "portfolio_aware_decision",
    "tools.run_market_wide_current_technical_coverage_scaleout",
    "tools.run_market_data_historical_series_failover",
    "tools.run_multi_source_exact_session_resolver",
)
FORBIDDEN_ROOTS = {"vnstock", "vnai"}
RETIRED_MODULES = (
    "vnstock_worker_process.py", "vnstock_worker_client.py", "vnstock_worker_protocol.py",
    "vnstock_rate_governor.py", "vn_stock_pipeline.py",
)
RETAINED_SUMMARY = Path("operations-review/market-wide-structured-financial-period-semantics-v1-20260905/structured_financial_period_semantics_artifact.json")


def _local_module(root: Path, name: str) -> Path | None:
    relative = Path(*name.split("."))
    for candidate in (root / relative.with_suffix(".py"), root / relative / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
                names.update(node.module + "." + alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "import_module" and node.args and isinstance(node.args[0], ast.Constant):
                if isinstance(node.args[0].value, str):
                    names.add(node.args[0].value)
    return names


def build_audit(root: Path = ROOT) -> dict:
    root = root.resolve()
    findings: list[str] = []
    pending = list(ENTRYPOINTS)
    visited: set[str] = set()
    forbidden_imports: list[str] = []
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        visited.add(module)
        path = _local_module(root, module)
        if path is None:
            findings.append(f"ENTRYPOINT_OR_LOCAL_IMPORT_MISSING:{module}")
            continue
        for name in _imports(path):
            if name.split(".", 1)[0] in FORBIDDEN_ROOTS:
                forbidden_imports.append(f"{path.relative_to(root).as_posix()}:{name}")
            elif _local_module(root, name) is not None:
                pending.append(name)
    for filename in ("requirements.txt", "requirements-providers.txt"):
        for line in (root / filename).read_text(encoding="utf-8").splitlines():
            requirement = line.split("#", 1)[0].strip().lower()
            if requirement.startswith(("vnstock", "vnai")):
                findings.append(f"ACTIVE_REQUIREMENT:{filename}:{requirement}")
    policy_document = json.loads((root / "config/provider_runtime_policy.json").read_text(encoding="utf-8"))
    policy = policy_document.get("providers", {}).get("VNSTOCK_KBS_VCI", {})
    if policy.get("policy") != "RETIRED_PROVIDER":
        findings.append("RETIRED_POLICY_NOT_SET")
    for filename in RETIRED_MODULES:
        if (root / filename).exists():
            findings.append(f"RETIRED_WORKER_OR_PIPELINE_PRESENT:{filename}")
    from_source = root / "multi_source_exact_session_resolver.py"
    resolver_tree = ast.parse(from_source.read_text(encoding="utf-8"))
    active_sources = None
    for node in resolver_tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "ACTIVE_RECOVERY_SOURCES" for target in targets):
                active_sources = ast.literal_eval(node.value)
    if active_sources != ():
        findings.append("ACTIVE_RECOVERY_SOURCES_NOT_EMPTY")
    forbidden_imports.sort()
    findings.extend(f"FORBIDDEN_REACHABLE_IMPORT:{item}" for item in forbidden_imports)
    vnstock_imports = [item for item in forbidden_imports if item.rsplit(":", 1)[-1].split(".", 1)[0] == "vnstock"]
    vnai_imports = [item for item in forbidden_imports if item.rsplit(":", 1)[-1].split(".", 1)[0] == "vnai"]
    providers_text = (root / "requirements-providers.txt").read_text(encoding="utf-8")
    provider_requirement_names = [
        line.split("#", 1)[0].strip().split(">", 1)[0].split("=", 1)[0].strip().lower()
        for line in providers_text.splitlines() if line.split("#", 1)[0].strip()
    ]
    retained_path = root / RETAINED_SUMMARY
    retained = {"KBS": None, "VCI": None}
    retained_identity = None
    if retained_path.is_file():
        summary = json.loads(retained_path.read_text(encoding="utf-8"))
        distribution = summary["coverage"]["provider_distribution"]
        retained = {source: int(distribution[source]) for source in ("KBS", "VCI")}
        retained_identity = summary["artifact_identity"]
        if min(retained.values()) <= 0:
            findings.append("RETAINED_PROVIDER_LINEAGE_MISSING")
    body = {
        "contract_version": "zero_active_vnstock_audit/v1",
        "canonical_base_sha": CANONICAL_BASE_SHA,
        "checked_entrypoints": list(ENTRYPOINTS),
        "reachable_first_party_modules": len(visited),
        "active_vnstock_import_count": len(vnstock_imports),
        "active_vnai_import_count": len(vnai_imports),
        "active_kbs_vci_acquisition_path_count": len(active_sources or ()),
        "active_dependency_count": (
            len(forbidden_imports)
            + sum(item.startswith("ACTIVE_REQUIREMENT") for item in findings)
            + len(active_sources or ())
        ),
        "retired_runtime_files": list(RETIRED_MODULES),
        "retired_runtime_files_present": [name for name in RETIRED_MODULES if (root / name).exists()],
        "runtime_policy_state": policy.get("policy"),
        "provider_requirements_state": {
            "file": "requirements-providers.txt",
            "declared_names": provider_requirement_names,
            "vnstock_or_vnai_declared": sorted(
                name for name in provider_requirement_names if name in {"vnstock", "vnai"}
            ),
        },
        "retired_family_state": policy.get("policy"),
        "active_recovery_sources": list(active_sources or ()),
        "retained_historical_lineage_count": retained,
        "retained_summary_identity": retained_identity,
        "retained_session_acceptance": {
            "session": "2026-09-28",
            "governed_denominator": 1683,
            "verdict": "PASS",
            "baseline_integrated_identity": (
                "integrated_investment_decision_product/v1:"
                "03f51230a1cb4492653cb41ea47f40950a32b8948aaec011da778b8489fb0c32"
            ),
            "after_integrated_identity": (
                "integrated_investment_decision_product/v1:"
                "03f51230a1cb4492653cb41ea47f40950a32b8948aaec011da778b8489fb0c32"
            ),
            "acceptance_content_identity": (
                "zero_active_vnstock_retained_acceptance/v1:"
                "732547442c666d8c49236bcb2b749b3afffc5505679dd85a4f1ab1c3890143dd"
            ),
        },
        "forbidden_import_findings": forbidden_imports,
        "findings": sorted(findings),
    }
    digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    body["content_identity"] = f"zero_active_vnstock_audit/v1:{digest}"
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = build_audit()
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if not result["findings"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
