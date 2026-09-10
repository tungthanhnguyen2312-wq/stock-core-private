"""Owner CLI: roadmap status or one canonical daily operation plus AI handoff and Dashboard release."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent


def _runtime(configured: Path | None = None) -> Path | None:
    """Resolve only the governed runtime contract; never select a worktree sibling by accident."""
    from daily_execution_environment import resolve_roots
    return resolve_roots(ROOT, runtime_root=configured).runtime_root


def _handoff() -> Path:
    if os.environ.get("STOCKLOOKUP_AI_HANDOFF_REPO"):
        return Path(os.environ["STOCKLOOKUP_AI_HANDOFF_REPO"])
    for candidate in (
        ROOT.parent / "stocklookup-ai-handoffs",
        ROOT.parent.parent / "stocklookup-ai-handoffs",
        Path("C:/Projects/StockLookup/stocklookup-ai-handoffs"),
    ):
        if candidate.is_dir():
            return candidate
    return ROOT.parent / "stocklookup-ai-handoffs"


def _producer_failure_message(code: int) -> str | None:
    """None when daily_analysis_pipeline.py already printed a complete owner-facing status for a
    known not-ready session-gate stage (its own exit code 2 -- CURRENT_SESSION_STABILIZING before
    the post-close floor, or POST_CLOSE_DATA_NOT_READY after it); the FAILED_PRODUCER trailer
    otherwise. A routine early/lagging run must never be relabelled a generic failure."""
    if code and code != 2:
        return "STATUS: FAILED_PRODUCER\nRECOVERY_ACTION: inspect canonical daily stage output"
    return None


def _previous(session: str, root: Path, *, operation_root: Path | None = None) -> Path | None:
    """Latest retained operation bundle strictly before ``session`` that is ALSO governed
    qualified (``completed_sessions[prior].status == "COMPLETED_RETAINED_EVIDENCE"`` in
    ``config/daily_research_session_input_registry.json``) -- not merely the latest bundle that
    happens to exist. A retained bundle for a session the registry never locked as complete (e.g.
    an earlier interrupted/superseded attempt) is real historical evidence, but is never a valid
    "previous session" for next_session_decision_brief, which enforces this exact same
    qualification on the current session and would otherwise reject it one layer later
    (SESSION_NOT_GOVERNED_QUALIFIED) -- see daily_research_session_operations.
    frozen_input_identities, the same qualification check that function already uses.
    """
    from daily_research_session_operations import frozen_input_identities, load_registry
    registry = load_registry(root)
    operation_root = operation_root or root
    candidates = []
    for manifest in sorted((operation_root / "operations-review/daily-research-session-operations-v1").glob("*/*/run_manifest.json")):
        value = json.loads(manifest.read_text(encoding="utf-8"))
        prior = str(value.get("market_session") or "")
        bundle = manifest.parent / "ai_research_session_bundle.json"
        if (
            prior < session
            and bundle.is_file()
            and json.loads(bundle.read_text(encoding="utf-8")).get("session") == prior
            and frozen_input_identities(registry, prior) is not None
        ):
            candidates.append((prior, bundle))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _latest_operation(root: Path = ROOT) -> tuple[str, Path, str]:
    pointer = json.loads((root / "operations-review/daily-producer-runs-v1/LATEST_COMPLETED_RUN.json").read_text(encoding="utf-8"))
    session = pointer["session"]
    run = root / "operations-review/daily-producer-runs-v1" / pointer["relative_directory"] / "run_manifest.json"
    manifest = json.loads(run.read_text(encoding="utf-8"))
    return session, root / manifest["daily_session_operation"]["directory"], pointer["run_identity"]


def _decision_brief(
    session: str, operation: Path, previous_bundle: Path | None, run_identity: str | None,
    root: Path = ROOT, *, registry_root: Path | None = None,
) -> Path | None:
    """Best-effort, non-blocking: the brief is derived evidence, never a gate on publication."""
    try:
        from next_session_decision_brief import build_from_previous_bundle_path
        from daily_research_session_operations import load_registry
        brief = build_from_previous_bundle_path(
            root=root, session=session, source=operation, previous=previous_bundle,
            run_identity=run_identity, registry=load_registry(registry_root or root),
        )
        payload = json.dumps(brief, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        path = operation / "next_session_decision_brief.json"
        if path.exists() and path.read_text(encoding="utf-8") != payload:
            print(f"STATUS: DECISION_BRIEF_CONTENT_CONFLICT_SKIPPED\nSESSION: {session}")
            return None
        path.write_text(payload, encoding="utf-8")
        return path
    except Exception as exc:
        print(f"STATUS: DECISION_BRIEF_SKIPPED\nREASON: {exc}")
        return None


def _daily_integrated_decision_brief(
    session: str, operation: Path, decision_brief_path: Path | None, root: Path = ROOT,
    *, registry_root: Path | None = None,
) -> Path | None:
    """Best-effort, non-blocking: derived evidence riding alongside publication, never a gate on
    it. Requires next_session_decision_brief/v2 to have built successfully (its market_transition/
    sector_transition/posture_transition sections are reused verbatim, never recomputed) and this
    session's own integrated_investment_decision_product to already be materialized by canonical
    post-close -- if that is genuinely missing, this returns None rather than silently reusing a
    stale prior-session product."""
    if decision_brief_path is None:
        print("STATUS: DAILY_INTEGRATED_DECISION_BRIEF_SKIPPED\nREASON: NEXT_SESSION_DECISION_BRIEF_NOT_AVAILABLE")
        return None
    try:
        from daily_integrated_decision_brief import build_from_session
        next_session_brief = json.loads(decision_brief_path.read_text(encoding="utf-8"))
        brief = build_from_session(root=root, session=session, next_session_brief=next_session_brief)
        if brief is None:
            print(f"STATUS: DAILY_INTEGRATED_DECISION_BRIEF_SKIPPED\nREASON: INTEGRATED_INVESTMENT_DECISION_PRODUCT_NOT_MATERIALIZED\nSESSION: {session}")
            return None
        payload = json.dumps(brief, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        path = operation / "daily_integrated_decision_brief.json"
        if path.exists() and path.read_text(encoding="utf-8") != payload:
            print(f"STATUS: DAILY_INTEGRATED_DECISION_BRIEF_CONTENT_CONFLICT_SKIPPED\nSESSION: {session}")
            return None
        path.write_text(payload, encoding="utf-8")
        # Keep the exact rich brief in the freshly built Daily operation as an
        # immutable, bound companion.  The resolver is session-addressed; it
        # never scans operations-review for a newer or similar-looking result.
        try:
            from daily_research_session_operations import load_registry, retain_integrated_decision_brief
            from daily_session_level2_package import session_artifact_paths
            integrated_path = session_artifact_paths(root, session)["integrated_investment_decision_product"]
            integrated = json.loads(integrated_path.read_text(encoding="utf-8"))
            operation_manifest = json.loads((operation / "run_manifest.json").read_text(encoding="utf-8"))
            retain_integrated_decision_brief(
                operation,
                session=session,
                operation_manifest=operation_manifest,
                integrated_investment_decision_product=integrated,
                daily_integrated_decision_brief=brief,
                registry=load_registry(registry_root or root),
            )
        except Exception as retention_exc:
            # Preserve the pre-existing non-blocking brief contract while
            # making a failed companion retention visible to the owner.
            print(f"STATUS: DAILY_INTEGRATED_DECISION_BRIEF_RETENTION_SKIPPED\nREASON: {retention_exc}\nSESSION: {session}")
        return path
    except Exception as exc:
        print(f"STATUS: DAILY_INTEGRATED_DECISION_BRIEF_SKIPPED\nREASON: {exc}")
        return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("daily")
    d.add_argument("--session")
    d.add_argument("--runtime-root", type=Path, default=None, help="Authoritative runtime root for canonical Daily.")
    d.add_argument("--retained-evidence-root", type=Path, default=None, help="Immutable retained-evidence root.")
    d.add_argument("--output-root", type=Path, default=None, help="Operation/Level-2 output root.")
    d.add_argument("--no-new-provider-acquisition", action="store_true", help="Refuse a resume requiring any provider request.")
    d.add_argument("--preflight", action="store_true", help="Print canonical Daily preflight facts and exit without acquisition.")
    d.add_argument("--replay-local", action="store_true")
    d.add_argument("--replay-operation", type=Path)
    d.add_argument("--replay-root", type=Path, default=ROOT)
    d.add_argument(
        "--local-only", action="store_true",
        help=(
            "Full local canonical pipeline with zero Git mutation in the AI-handoff or Dashboard "
            "repositories: no commit, no push, no deploy. Stronger than --replay-local, which "
            "still skips the push but leaves two local commits in the AI-handoff repo -- see "
            "ai_handoff_publication.publish()'s local_only parameter for exactly what this "
            "prevents. Local canonical artifacts, tests, and validation still run normally."
        ),
    )
    sub.add_parser("roadmap")
    portfolio = sub.add_parser("portfolio", help="Private local-only workbook import and status; never enters Daily.")
    portfolio_sub = portfolio.add_subparsers(dest="portfolio_action", required=True)
    portfolio_import = portfolio_sub.add_parser("import", help="Import the owner workbook into private content-addressed local artifacts.")
    portfolio_import.add_argument("--workbook", type=Path, default=None, help="Private workbook path (default: %%USERPROFILE%%\\.stocklookup\\portfolio\\portfolio_input.xlsx).")
    portfolio_import.add_argument("--portfolio-root", type=Path, default=None, help="Private local artifact root (default: %%USERPROFILE%%\\.stocklookup\\portfolio).")
    portfolio_status = portfolio_sub.add_parser("status", help="Read the private latest-import pointer without opening the workbook.")
    portfolio_status.add_argument("--portfolio-root", type=Path, default=None, help="Private local artifact root (default: %%USERPROFILE%%\\.stocklookup\\portfolio).")
    portfolio_evaluate = portfolio_sub.add_parser(
        "evaluate",
        help=(
            "Join the private portfolio state and risk policy against the latest retained "
            "completed Integrated Decision (PORTFOLIO_AWARE_DECISION_AND_RISK_SIZING_V1). "
            "Read-only: no Daily run, no provider call, no re-parse of the owner workbook. "
            "Console output is identities/counts/reason-codes only -- never holdings, "
            "quantities, prices, NAV, cash, or margin balances."
        ),
    )
    portfolio_evaluate.add_argument("--portfolio-root", type=Path, default=None, help="Private local artifact root (default: %%USERPROFILE%%\\.stocklookup\\portfolio).")
    portfolio_evaluate.add_argument("--session", default=None, help="Explicit YYYY-MM-DD session (default: latest retained completed session).")
    portfolio_evaluate.add_argument("--sector-snapshot", type=Path, default=None, help="Optional explicit exchange_industry_classification snapshot path.")
    portfolio_evaluate.add_argument("--exclude", action="append", default=[], help="Ticker to exclude from active portfolio workflow (repeatable).")
    portfolio_shortlist = portfolio_sub.add_parser("shortlist", help="Compose a private retained-evidence owner research shortlist; no Daily or provider call.")
    portfolio_shortlist.add_argument("--portfolio-root", type=Path, default=None)
    portfolio_shortlist.add_argument("--session", required=True)
    portfolio_review = portfolio_sub.add_parser("review", help="Build a private deterministic owner review packet from the retained shortlist.")
    portfolio_review.add_argument("--portfolio-root", type=Path, default=None)
    portfolio_review.add_argument("--session", required=True)
    a = p.parse_args(argv)

    if a.command == "roadmap":
        return subprocess.run([sys.executable, str(ROOT / "tools/stocklookup_roadmap.py")]).returncode

    if a.command == "portfolio":
        from private_portfolio_context import (
            PortfolioImportError,
            import_workbook,
            portfolio_status as load_portfolio_status,
            public_import_summary,
            public_status_summary,
        )
        try:
            if a.portfolio_action == "import":
                result = import_workbook(workbook_path=a.workbook, portfolio_root=a.portfolio_root)
                print(json.dumps(public_import_summary(result), ensure_ascii=False, sort_keys=True))
                return 0
            if a.portfolio_action == "status":
                result = load_portfolio_status(portfolio_root=a.portfolio_root)
                print(json.dumps(public_status_summary(result), ensure_ascii=False, sort_keys=True))
                return 0
            if a.portfolio_action == "shortlist":
                import portfolio_aware_opportunity_shortlist as pas
                import portfolio_aware_decision as pad
                try:
                    root = (a.portfolio_root or __import__("private_portfolio_context").default_portfolio_root()).expanduser()
                    portfolio_path = root / "portfolio_aware_decisions" / a.session / "portfolio_aware_decision_v1.json"
                    integrated = pad.load_integrated_decision_artifact(ROOT, a.session)
                    import asymmetric_dislocation_research as adr
                    asymmetric = adr.build_artifact(session=a.session, integrated_product=integrated)
                    artifact = pas.build_artifact(session=a.session, integrated_decision=integrated,
                        portfolio_aware_decision=json.loads(portfolio_path.read_text(encoding="utf-8")),
                        asymmetric_dislocation=asymmetric)
                except (FileNotFoundError, pas.OpportunityShortlistError, json.JSONDecodeError):
                    print(json.dumps({"status": "BLOCKED", "reason_code": "RETAINED_INPUT_CONTRACT_UNAVAILABLE_OR_INCOMPATIBLE"}, sort_keys=True))
                    return 2
                pas.write_private_artifact(artifact, portfolio_root=root)
                print(json.dumps(pas.public_console_summary(artifact), ensure_ascii=False, sort_keys=True))
                return 0
            if a.portfolio_action == "review":
                import private_portfolio_decision_packet as packet
                root = (a.portfolio_root or __import__("private_portfolio_context").default_portfolio_root()).expanduser()
                path = root / "portfolio_aware_opportunity_shortlists" / a.session / "portfolio_aware_opportunity_shortlist_v1.json"
                try:
                    import portfolio_aware_decision as pad
                    import asymmetric_dislocation_research as adr
                    shortlist = json.loads(path.read_text(encoding="utf-8"))
                    integrated = pad.load_integrated_decision_artifact(ROOT, a.session)
                    portfolio = json.loads((root / "portfolio_aware_decisions" / a.session / "portfolio_aware_decision_v1.json").read_text(encoding="utf-8"))
                    asymmetric = adr.build_artifact(session=a.session, integrated_product=integrated)
                    artifact = packet.build_artifact(shortlist=shortlist, integrated_decision=integrated, portfolio_aware_decision=portfolio, asymmetric_dislocation=asymmetric)
                except (FileNotFoundError, packet.PacketError, json.JSONDecodeError):
                    print(json.dumps({"status":"BLOCKED","reason_code":"RETAINED_SHORTLIST_UNAVAILABLE_OR_INCOMPATIBLE"},sort_keys=True)); return 2
                packet.write_private_artifact(artifact, root)
                print(json.dumps(packet.public_console_summary(artifact),ensure_ascii=False,sort_keys=True)); return 0
            # a.portfolio_action == "evaluate"
            import datetime as _dt

            import portfolio_aware_decision as pad
            try:
                artifact = pad.evaluate_from_retained_artifacts(
                    repo_root=ROOT, session=a.session, portfolio_root=a.portfolio_root,
                    sector_snapshot_path=a.sector_snapshot, excluded_tickers=a.exclude,
                    requested_at=_dt.datetime.now().isoformat(timespec="seconds"),
                )
            except FileNotFoundError as exc:
                print(json.dumps({"status": "BLOCKED", "reason_code": str(exc)}, ensure_ascii=False, sort_keys=True))
                return 2
            pad.write_private_artifact(artifact, portfolio_root=a.portfolio_root)
            summary = pad.public_console_summary(artifact)
            summary["private_artifact_written"] = True
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
            return 0
        except PortfolioImportError as exc:
            print(f"STATUS: {exc}")
            return 2

    daily_runtime: Path | None = None
    daily_retained_evidence_root = ROOT
    daily_output_root = ROOT
    if a.command == "daily":
        from daily_execution_environment import format_preflight, preflight_canonical_daily
        from daily_session_level2_package import resolve_level2_session
        intended_session = resolve_level2_session(a.session)["session"]
        environment = preflight_canonical_daily(
            ROOT,
            session=intended_session,
            runtime_root=a.runtime_root,
            retained_evidence_root=a.retained_evidence_root,
            output_root=a.output_root,
            no_new_provider_acquisition=a.no_new_provider_acquisition,
        )
        if a.preflight or environment["status"] != "PASS":
            print(format_preflight(environment))
        if environment["status"] != "PASS":
            return 2
        if a.preflight:
            return 0
        daily_runtime = Path(environment["roots"]["runtime_root"])
        daily_retained_evidence_root = Path(environment["roots"]["retained_evidence_root"])
        daily_output_root = Path(environment["roots"]["output_root"])

    try:
        from stocklookup_preflight import check
        check(
            producer_root=a.replay_root if a.replay_operation else ROOT,
            runtime_root=daily_runtime or _runtime(),
            transport_root=_handoff(),
            replay_local=a.replay_local,
        )
    except Exception as exc:
        print(f"STATUS: {exc}")
        return 2

    if a.replay_operation:
        if not (a.replay_local or a.local_only) or not a.session:
            print("STATUS: FAILED_PRECHECK\nREASON: replay requires --replay-local (or --local-only) and --session")
            return 2
        session, operation, run_identity = a.session, a.replay_operation, None
    else:
        cmd = [sys.executable, str(ROOT / "daily_analysis_pipeline.py"), "--runtime-root", str(daily_runtime), "--canonical-post-close"]
        if a.session:
            cmd += ["--session", a.session]
        if a.retained_evidence_root:
            cmd += ["--retained-evidence-root", str(a.retained_evidence_root)]
        if a.output_root:
            cmd += ["--output-root", str(a.output_root)]
        if a.no_new_provider_acquisition:
            cmd.append("--no-new-provider-acquisition")
        code = subprocess.run(cmd).returncode
        if code:
            message = _producer_failure_message(code)
            if message:
                print(message)
            return code
        session, operation, run_identity = _latest_operation(daily_output_root)

    previous_bundle = _previous(
        session, a.replay_root, operation_root=daily_retained_evidence_root,
    )
    decision_brief_path = _decision_brief(
        session, operation, previous_bundle, run_identity,
        root=daily_retained_evidence_root, registry_root=a.replay_root,
    )
    daily_integrated_brief_path = _daily_integrated_decision_brief(
        session, operation, decision_brief_path,
        root=daily_output_root, registry_root=a.replay_root,
    )

    try:
        from ai_handoff_publication import publish
        result = publish(
            _handoff(),
            operation,
            session,
            previous=previous_bundle,
            producer_checkpoint=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8").strip(),
            push=not (a.replay_local or a.local_only),
            local_only=a.local_only,
            decision_brief=decision_brief_path,
            daily_integrated_decision_brief=daily_integrated_brief_path,
        )
    except Exception as exc:
        print(f"STATUS: FAILED_PUBLICATION\nREASON: {exc}\nRECOVERY_ACTION: verify private handoff repository")
        return 1

    try:
        from dashboard_release_publisher import publish_dashboard_release
        web_root = Path(os.environ.get("STOCK_LOOKUP_WEB_DIR", ROOT.parent / "market-dashboard"))
        dash_res = publish_dashboard_release(
            session=session,
            operation_dir=operation,
            runtime_root=daily_runtime or _runtime(),
            web_root=web_root,
            replay_local=a.replay_local or a.local_only,
            push=not (a.replay_local or a.local_only),
            local_only=a.local_only,
        )
        lines = [
            "STOCK LOOKUP DAILY",
            f"Session: {session}",
            f"AI Handoff: {result['status']}",
            f"Dashboard: {dash_res['status']}",
            f"REMOTE_PUBLICATION={'SKIPPED_LOCAL_MODE' if a.local_only else 'PUBLISHED'}",
        ]
        if a.local_only:
            # The local, session-scoped AI artifact pointer already exists on disk -- these are
            # the exact files ai_handoff_publication.build_package() just hashed/validated above
            # without ever touching a Git repository. See docs/STATE.md's LOCAL_AI_ARTIFACTS
            # contract: session, operation identity, producer checkpoint, bundle/manifest/brief
            # paths, and artifact hashes are all present in `result["package"]` below.
            lines += [
                "LOCAL_AI_ARTIFACTS:",
                f"  operation_dir: {operation}",
                f"  bundle: {operation / 'ai_research_session_bundle.json'}",
                f"  manifest: {operation / 'ai_research_bundle_manifest.json'}",
                f"  decision_brief: {decision_brief_path or 'NOT_AVAILABLE'}",
                f"  daily_integrated_decision_brief: {daily_integrated_brief_path or 'NOT_AVAILABLE'}",
                f"  producer_checkpoint: {result['package']['lineage'].get('producer_checkpoint')}",
                f"  package_sha256: {result['package']['package_sha256']}",
            ]
        else:
            lines.append("Next user action: Ask ChatGPT: Phân tích Stock Lookup phiên mới nhất.")
        print("\n".join(lines))
        return 0
    except Exception as exc:
        print(f"STATUS: FAILED_DASHBOARD_RELEASE\nREASON: {exc}\nRECOVERY_ACTION: inspect Dashboard release contract and files")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
