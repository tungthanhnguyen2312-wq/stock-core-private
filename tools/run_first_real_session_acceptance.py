"""Read-only explicit-session acceptance, or an isolated offline fixture dry-run."""
import argparse
import json
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import first_real_session_acceptance as acceptance


def dry_run(*, session, cutoff):
    # Test-fixture construction is isolated from every retained/production root.
    sys.path.insert(0,str(ROOT/"tests"))
    from test_prospective_pit_capture import capture_session
    from test_production_call_shape_smoke import _offline_smoke_guard
    with tempfile.TemporaryDirectory(prefix="stocklookup-monday-fixture-") as temporary, _offline_smoke_guard() as counters:
        root=Path(temporary)
        capture_session(root,session,calendar_days=[session])
        report=acceptance.collect(root,session=session,cutoff=cutoff)
        report.pop("artifact_identity");report.pop("artifact_sha256")
        report["evaluation_scope"]="SYNTHETIC_FIXTURE_DIAGNOSTIC"
        report["network_provider_calls"]=dict(counters)
        from prospective_market_snapshot_contract import content_identity
        report.update(content_identity(report,kind="first_real_session_acceptance"))
        return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session",required=True)
    parser.add_argument("--cutoff",required=True)
    parser.add_argument("--source-root",type=Path)
    parser.add_argument("--handoff",type=Path)
    parser.add_argument("--technical-artifact",type=Path)
    parser.add_argument("--volume-flow-artifact",type=Path)
    parser.add_argument("--decision-artifact",type=Path)
    parser.add_argument("--thesis-t0",type=Path);parser.add_argument("--thesis-current",type=Path)
    parser.add_argument("--feedback-pre",type=Path,help="status sidecar of the pre-handoff feedback child (reported, never gating)")
    parser.add_argument("--feedback-post",type=Path,help="status sidecar of the post-handoff feedback child (reported, never gating)")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    output=args.output.resolve()
    if not any(part in {".stocklookup","scratch","first-real-session-acceptance-v1"} for part in output.parts):
        raise ValueError("DIAGNOSTIC_OUTPUT_ROOT_REQUIRED")
    if args.dry_run:
        if any((args.source_root,args.handoff,args.technical_artifact,args.volume_flow_artifact,args.decision_artifact,args.thesis_t0,args.thesis_current)):
            raise ValueError("DRY_RUN_CANNOT_CONSUME_RETAINED_AUTHORITY")
        report=dry_run(session=args.session,cutoff=args.cutoff)
    else:
        if not args.source_root: raise ValueError("EXPLICIT_SOURCE_ROOT_REQUIRED")
        binding=None;thesis={}
        if args.handoff:
            handoff=json.loads(args.handoff.read_bytes())
            if handoff.get("session")!=args.session: raise ValueError("HANDOFF_SESSION_MISMATCH")
            binding=handoff.get("prospective_decision_snapshot")
            thesis=handoff.get("thesis_evidence") or {}
        report=acceptance.collect(args.source_root,session=args.session,cutoff=args.cutoff,
            technical_path=args.technical_artifact,flow_path=args.volume_flow_artifact,snapshot_binding=binding,decision_path=args.decision_artifact,
            thesis_t0_path=args.thesis_t0 or (args.source_root/thesis["t0"]["path"] if (thesis.get("t0") or {}).get("path") else None),
            thesis_current_path=args.thesis_current or (args.source_root/thesis["current"]["path"] if (thesis.get("current") or {}).get("path") else None),thesis_references=thesis,
            feedback_status_paths={"pre":args.feedback_pre,"post":args.feedback_post})
    from atomic_io import atomic_write_json
    atomic_write_json(output,report)
    print(json.dumps({row["capability"]:row["state"] for row in report["rows"]},indent=2))


if __name__=="__main__":main()
