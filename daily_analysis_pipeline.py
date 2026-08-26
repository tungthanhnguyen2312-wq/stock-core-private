"""Sequential canonical post-session analysis pipeline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from freshness_history import freshness_envelope
from runtime_paths import RUNTIME_ROOT_ENV

try:
    from atomic_io import atomic_write_json
except ImportError:
    from stock_core_private.atomic_io import atomic_write_json

try:
    from observability_events import (
        EventOutcome,
        EventStage,
        build_observability_event,
        emit_observability_event,
    )
except ImportError:
    try:
        from stock_core_private.observability_events import (
            EventOutcome,
            EventStage,
            build_observability_event,
            emit_observability_event,
        )
    except ImportError:
        EventOutcome = EventStage = build_observability_event = emit_observability_event = None

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TICKERS = [
    "POW",
    "SSI",
    "HPG",
    "EVF",
    "PAN",
    "PNJ",
    "QNS",
    "PDR",
    "GEX",
]
REQUIRED = ("screen_snapshot.csv", "screen_snapshot_live.csv", "market_breadth.csv",
            "analysis_latest.json", "analysis_latest.md", "Market_Scan.csv", "Market_Scan.md",
            "Focus_Analysis.md", "ta_signals.csv", "ta_signals.json", "macro_snapshot.csv",
            "news_latest.csv", "analysis_bundle.json", "bundle_manifest.json")
DEPS = {"screen_snapshot_live.csv": ("screen_snapshot.csv",),
        "market_breadth.csv": ("screen_snapshot.csv",),
        "ta_signals.csv": ("screen_snapshot.csv",), "ta_signals.json": ("ta_signals.csv",),
        "analysis_latest.json": ("screen_snapshot_live.csv", "ta_signals.csv"),
        "analysis_latest.md": ("analysis_latest.json",), "Market_Scan.csv": ("screen_snapshot_live.csv", "ta_signals.csv"), "Market_Scan.md": ("Market_Scan.csv",),
        "Focus_Analysis.md": ("screen_snapshot_live.csv", "market_breadth.csv", "macro_snapshot.csv", "news_latest.csv"),
        "analysis_bundle.json": ("screen_snapshot_live.csv", "market_breadth.csv", "ta_signals.csv", "analysis_latest.json", "Focus_Analysis.md", "macro_snapshot.csv", "news_latest.csv")}

MANDATORY_SUBSOURCE_FRESHNESS = {
    "vnstock_metadata_snapshot": {"domain": "vnstock_metadata_snapshot", "table": "metadata", "column": "updated"},
}

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()

def inspect(root: Path, names: Sequence[str] = REQUIRED) -> dict[str, dict]:
    """`freshness_status` here is an artifact-presence + mtime-ordering build-dependency signal
    (gates whether this pipeline run may proceed to the next step), never a claim about
    market/business data freshness -- the only consumers are this module's own main() and its
    own tests. `modified_time` is raw filesystem mtime, named honestly; `data_as_of`/session
    identity for published artifacts comes from bundle_manifest.json's content-derived
    freshness.reference_session (see release_session_contract.py), never from here."""
    report = {}
    for name in names:
        p = root / name
        item = {"path": str(p), "exists": p.is_file(), "freshness_status": "missing", "dependency_status": "not_checked"}
        if p.is_file():
            st = p.stat(); item.update(size=st.st_size, modified_time=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"), sha256=digest(p), freshness_status="fresh")
        report[name] = item
    for name, deps in DEPS.items():
        if name not in report:
            continue
        item = report[name]
        if not item["exists"]: item["dependency_status"] = "missing_artifact"; continue
        stale = [dep for dep in deps if not report[dep]["exists"] or (root / name).stat().st_mtime < (root / dep).stat().st_mtime]
        item["dependency_status"] = "stale" if stale else "ok"
        if stale: item.update(freshness_status="stale_dependency", stale_dependencies=stale)
    return report

def upstream_ok(root: Path) -> tuple[bool, dict[str, dict]]:
    report = inspect(root, REQUIRED[:-2])
    return all(x["freshness_status"] == "fresh" for x in report.values()), report

def subsource_as_of(root: Path, table: str, column: str) -> str | None:
    """Read-only MAX(column) probe for one DB-resident sub-source."""
    db_path = root / "vn_stock.db"
    if not db_path.is_file():
        return None
    conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        row = conn.execute(f"SELECT MAX({column}) FROM {table}").fetchone()
        return row[0] if row else None
    except sqlite3.DatabaseError:
        return None
    finally:
        conn.close()

def check_subsource_freshness(root: Path, reference_at: datetime, matrix: dict = MANDATORY_SUBSOURCE_FRESHNESS) -> dict:
    """Mandatory sub-source freshness gate."""
    envelopes = {}
    for name, spec in matrix.items():
        as_of = subsource_as_of(root, spec["table"], spec["column"])
        envelopes[name] = freshness_envelope(domain=spec["domain"], as_of_date=as_of, generated_at=as_of,
                                             source=f"{spec['table']}.{spec['column']}", reference_at=reference_at)
    blocked = any(e["freshness_status"] == "stale" for e in envelopes.values())
    return {"reference_at": reference_at.isoformat(timespec="seconds"), "sources": envelopes, "blocked": blocked}

def run(name: str, command: list[str], env: dict[str, str], runner: Callable, root: Path | None = None) -> dict:
    started, tick = now(), time.monotonic()
    result = runner(command, cwd=SCRIPT_DIR, env=env, check=False)
    record = {"name": name, "command": command, "started_at": started, "ended_at": now(), "exit_code": result.returncode, "duration_seconds": round(time.monotonic()-tick, 3)}
    print(f"[daily_analysis] {name}: exit={result.returncode} duration={record['duration_seconds']}s", flush=True)

    if root and build_observability_event and emit_observability_event:
        try:
            stage = EventStage.ARTIFACT_GENERATION
            if name == "verify_bundle":
                stage = EventStage.MANIFEST_VERIFICATION
            elif name == "publish_dashboard":
                stage = EventStage.PUBLISH_DASHBOARD

            outcome = EventOutcome.SUCCESS if result.returncode == 0 else EventOutcome.FAILED
            ev = build_observability_event(
                stage,
                outcome,
                artifact_filename=name,
                reason=f"step_{name}_failed_exit_{result.returncode}" if result.returncode else None,
                target_path=root / name,
                provenance={"duration_seconds": record["duration_seconds"]},
            )
            emit_observability_event(ev, root / "logs" / "observability_events.jsonl")
        except Exception:
            pass

    if result.returncode:
        raise RuntimeError(f"{name} failed with exit code {result.returncode}")
    return record

def steps(args: argparse.Namespace, tickers: list[str]) -> list[tuple[str, list[str]]]:
    py = sys.executable
    result = []
    def producer_script(name: str) -> str:
        return str(SCRIPT_DIR / name)

    if not args.skip_price_update:
        result.append(("price_update", [py, producer_script("vn_stock_pipeline.py"), "update"]))
    if not args.skip_macro:
        result.append(("macro_sync", [py, producer_script("macro_sync.py")]))
    if not args.skip_news:
        result.append(("news_sync", [py, producer_script("news_sync.py")]))

    base = [
        ("indicators", [py, producer_script("vn_indicators.py")]),
        ("candle_scan", [py, producer_script("candle_scan.py")]),
        ("strategy_all", [py, producer_script("stock_analyzer.py"), "--strategy", "all"]),
        ("market_scan", [py, producer_script("stock_analyzer.py"), "--scan-market"]),
        ("focus_analysis", [py, producer_script("stock_analyzer.py"), "--tickers", *tickers]),
        ("export_bundle", [py, producer_script("export_ai_bundle.py"), "--tickers", ",".join(tickers)]),
    ]
    res = result + base
    if getattr(args, "publish_dashboard", False):
        cmd = [py, producer_script("publish_dashboard.py")]
        if getattr(args, "live_publish", False):
            cmd.append("--live")
        res.append(("publish_dashboard", cmd))
    return res

def enrich(root: Path, tickers: list[str], executed: list[dict], report: dict[str, dict]) -> None:
    path = root / "bundle_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    session = json.loads((root / "analysis_bundle.json").read_text(encoding="utf-8")).get("reference_session_date")
    manifest.update(
        schema_version="1.2.0",
        runtime_root=str(root),
        session_date=session,
        daily_analysis={"generated_at": now(), "command_step_order": executed, "watchlist": tickers},
        artifact_verification=report,
        overall_verification_result="passed",
        subsource_freshness=check_subsource_freshness(root, datetime.now(timezone.utc)),
    )
    atomic_write_json(path, manifest)

def parse(argv=None):
    p = argparse.ArgumentParser(description="Run canonical daily analysis sequentially.")
    p.add_argument("--runtime-root", required=True)
    p.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    p.add_argument("--skip-price-update", action="store_true")
    p.add_argument("--skip-macro", action="store_true")
    p.add_argument("--skip-news", action="store_true")
    p.add_argument("--publish-dashboard", action="store_true", help="Trigger dashboard publisher step post-export")
    p.add_argument("--live-publish", action="store_true", help="Run dashboard publisher in live mode")
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--session", default=None, help="Explicit market session YYYY-MM-DD. Required by --canonical-post-close; ignored by the LEGACY_NON_CANONICAL VCI/KBS step list.")
    p.add_argument("--canonical-post-close", action="store_true",
                    help="Run the canonical DNSE-based post-close pipeline (acquisition, current research, "
                         "Canonical Daily Producer, prospective collection, tiered AI handoff) instead of the "
                         "LEGACY_NON_CANONICAL VCI/KBS step list below. Requires --session. Never falls back "
                         "to vn_stock_pipeline.py.")
    p.add_argument("--workers", type=int, default=12, help="Parallel DNSE fetch workers; only used by --canonical-post-close.")
    return p.parse_args(argv)

def main(argv=None, runner=subprocess.run) -> int:
    args = parse(argv)
    root = Path(args.runtime_root).expanduser().resolve()
    if not root.is_dir():
        print(f"[daily_analysis] runtime root does not exist: {root}", file=sys.stderr)
        return 2
    if args.canonical_post_close:
        if not args.session:
            print("[daily_analysis] --canonical-post-close requires an explicit --session YYYY-MM-DD", file=sys.stderr)
            return 2
        from canonical_post_close_pipeline import CanonicalPostCloseError, print_terminal_handoff, run_canonical_post_close
        try:
            result = run_canonical_post_close(SCRIPT_DIR, root, args.session, workers=args.workers)
        except CanonicalPostCloseError as exc:
            print(f"[daily_analysis] CANONICAL_POST_CLOSE_FAILED: {exc}", file=sys.stderr)
            return 1
        print_terminal_handoff(result)
        return 0
    tickers = [x.upper() for x in args.tickers]
    env = os.environ.copy()
    env[RUNTIME_ROOT_ENV] = str(root)
    executed = []
    try:
        if args.verify_only:
            executed.append(run("verify_bundle", [sys.executable, "export_ai_bundle.py", "--verify", str(root / "bundle_manifest.json")], env, runner, root=root))
            if not all(item["freshness_status"] == "fresh" for item in inspect(root).values()):
                raise RuntimeError("required artifact missing or stale during verification")
            return 0
        else:
            for name, command in steps(args, tickers):
                if name == "export_bundle":
                    if not upstream_ok(root)[0]:
                        raise RuntimeError("required upstream artifact missing or stale; refusing bundle export")
                    subsource = check_subsource_freshness(root, datetime.now(timezone.utc))
                    if subsource["blocked"]:
                        raise RuntimeError(f"mandatory sub-source freshness gate failed; refusing bundle export: {subsource['sources']}")
                executed.append(run(name, command, env, runner, root=root))
            executed.append(run("verify_bundle", [sys.executable, "export_ai_bundle.py", "--verify", str(root / "bundle_manifest.json")], env, runner, root=root))
        report = inspect(root)
        if not all(item["freshness_status"] == "fresh" for item in report.values()):
            raise RuntimeError("required artifact missing or stale after pipeline")
        enrich(root, tickers, executed, report)
        return 0
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"[daily_analysis] FAILED: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
