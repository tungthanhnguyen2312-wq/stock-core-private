"""Owner CLI: roadmap status or one canonical daily operation plus AI handoff."""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
ROOT=Path(__file__).resolve().parent
def _runtime() -> Path: return Path(os.environ.get("STOCK_LOOKUP_RUNTIME_ROOT", ROOT.parent/"dashboard-runtime"))
def _handoff() -> Path: return Path(os.environ.get("STOCKLOOKUP_AI_HANDOFF_REPO", ROOT.parent/"stocklookup-ai-handoffs"))
def _previous(session: str, root: Path) -> Path|None:
    candidates=[]
    for manifest in sorted((root/"operations-review/daily-research-session-operations-v1").glob("*/*/run_manifest.json")):
        value=json.loads(manifest.read_text(encoding="utf-8")); prior=str(value.get("market_session") or "")
        bundle=manifest.parent/"ai_research_session_bundle.json"
        if prior < session and bundle.is_file() and json.loads(bundle.read_text(encoding="utf-8")).get("session")==prior: candidates.append((prior,bundle))
    return max(candidates,key=lambda item:item[0])[1] if candidates else None
def _latest_operation() -> tuple[str,Path]:
    pointer=json.loads((ROOT/"operations-review/daily-producer-runs-v1/LATEST_COMPLETED_RUN.json").read_text(encoding="utf-8")); session=pointer["session"]
    run=ROOT/"operations-review/daily-producer-runs-v1"/pointer["relative_directory"]/"run_manifest.json"; manifest=json.loads(run.read_text(encoding="utf-8"))
    return session,ROOT/manifest["daily_session_operation"]["directory"]
def main(argv=None)->int:
 p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command",required=True); d=sub.add_parser("daily"); d.add_argument("--session"); d.add_argument("--replay-local",action="store_true"); d.add_argument("--replay-operation",type=Path); d.add_argument("--replay-root",type=Path,default=ROOT); sub.add_parser("roadmap"); a=p.parse_args(argv)
 if a.command=="roadmap": return subprocess.run([sys.executable,str(ROOT/"tools/stocklookup_roadmap.py")]).returncode
 if a.replay_operation:
  if not a.replay_local or not a.session: print("STATUS: FAILED_PRECHECK\nREASON: replay requires --replay-local and --session"); return 2
  session,operation=a.session,a.replay_operation
 else:
  cmd=[sys.executable,str(ROOT/"daily_analysis_pipeline.py"),"--runtime-root",str(_runtime()),"--canonical-post-close"]
  if a.session: cmd += ["--session",a.session]
  code=subprocess.run(cmd).returncode
  if code: print("STATUS: FAILED_PRODUCER\nRECOVERY_ACTION: inspect canonical daily stage output"); return code
  session,operation=_latest_operation()
 try:
  from ai_handoff_publication import publish
  result=publish(_handoff(),operation,session,previous=_previous(session,a.replay_root),producer_checkpoint=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True,encoding="utf-8").strip(),push=not a.replay_local)
  print(f"STOCK LOOKUP DAILY\nSession: {session}\nStatus: {result['status']}\nNext user action: Ask ChatGPT: Phân tích Stock Lookup phiên mới nhất."); return 0
 except Exception as exc: print(f"STATUS: FAILED_PUBLICATION\nREASON: {exc}\nRECOVERY_ACTION: verify private handoff repository"); return 1
if __name__=="__main__": raise SystemExit(main())
