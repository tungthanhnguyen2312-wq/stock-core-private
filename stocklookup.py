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


def _runtime() -> Path:
    if os.environ.get("STOCK_LOOKUP_RUNTIME_ROOT"):
        return Path(os.environ["STOCK_LOOKUP_RUNTIME_ROOT"])
    for candidate in (
        ROOT.parent / "dashboard-runtime",
        ROOT.parent.parent / "dashboard-runtime",
        Path("C:/Projects/StockLookup/dashboard-runtime"),
    ):
        if candidate.is_dir():
            return candidate
    return ROOT.parent / "dashboard-runtime"


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


def _previous(session: str, root: Path) -> Path | None:
    candidates = []
    for manifest in sorted((root / "operations-review/daily-research-session-operations-v1").glob("*/*/run_manifest.json")):
        value = json.loads(manifest.read_text(encoding="utf-8"))
        prior = str(value.get("market_session") or "")
        bundle = manifest.parent / "ai_research_session_bundle.json"
        if prior < session and bundle.is_file() and json.loads(bundle.read_text(encoding="utf-8")).get("session") == prior:
            candidates.append((prior, bundle))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _latest_operation() -> tuple[str, Path, str]:
    pointer = json.loads((ROOT / "operations-review/daily-producer-runs-v1/LATEST_COMPLETED_RUN.json").read_text(encoding="utf-8"))
    session = pointer["session"]
    run = ROOT / "operations-review/daily-producer-runs-v1" / pointer["relative_directory"] / "run_manifest.json"
    manifest = json.loads(run.read_text(encoding="utf-8"))
    return session, ROOT / manifest["daily_session_operation"]["directory"], pointer["run_identity"]


def _decision_brief(session: str, operation: Path, previous_bundle: Path | None, run_identity: str | None) -> Path | None:
    """Best-effort, non-blocking: the brief is derived evidence, never a gate on publication."""
    try:
        from next_session_decision_brief import build_from_previous_bundle_path
        brief = build_from_previous_bundle_path(root=ROOT, session=session, source=operation, previous=previous_bundle, run_identity=run_identity)
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


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("daily")
    d.add_argument("--session")
    d.add_argument("--replay-local", action="store_true")
    d.add_argument("--replay-operation", type=Path)
    d.add_argument("--replay-root", type=Path, default=ROOT)
    sub.add_parser("roadmap")
    a = p.parse_args(argv)

    if a.command == "roadmap":
        return subprocess.run([sys.executable, str(ROOT / "tools/stocklookup_roadmap.py")]).returncode

    try:
        from stocklookup_preflight import check
        check(
            producer_root=a.replay_root if a.replay_operation else ROOT,
            runtime_root=_runtime(),
            transport_root=_handoff(),
            replay_local=a.replay_local,
        )
    except Exception as exc:
        print(f"STATUS: {exc}")
        return 2

    if a.replay_operation:
        if not a.replay_local or not a.session:
            print("STATUS: FAILED_PRECHECK\nREASON: replay requires --replay-local and --session")
            return 2
        session, operation, run_identity = a.session, a.replay_operation, None
    else:
        cmd = [sys.executable, str(ROOT / "daily_analysis_pipeline.py"), "--runtime-root", str(_runtime()), "--canonical-post-close"]
        if a.session:
            cmd += ["--session", a.session]
        code = subprocess.run(cmd).returncode
        if code:
            print("STATUS: FAILED_PRODUCER\nRECOVERY_ACTION: inspect canonical daily stage output")
            return code
        session, operation, run_identity = _latest_operation()

    previous_bundle = _previous(session, a.replay_root)
    decision_brief_path = _decision_brief(session, operation, previous_bundle, run_identity)

    try:
        from ai_handoff_publication import publish
        result = publish(
            _handoff(),
            operation,
            session,
            previous=previous_bundle,
            producer_checkpoint=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8").strip(),
            push=not a.replay_local,
            decision_brief=decision_brief_path,
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
            runtime_root=_runtime(),
            web_root=web_root,
            replay_local=a.replay_local,
            push=not a.replay_local,
        )
        print(f"STOCK LOOKUP DAILY\nSession: {session}\nAI Handoff: {result['status']}\nDashboard: {dash_res['status']}\nNext user action: Ask ChatGPT: Phân tích Stock Lookup phiên mới nhất.")
        return 0
    except Exception as exc:
        print(f"STATUS: FAILED_DASHBOARD_RELEASE\nREASON: {exc}\nRECOVERY_ACTION: inspect Dashboard release contract and files")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
