#!/usr/bin/env python3
"""StockLookup Production Release Orchestrator.

Authoritative Python CLI for orchestrating StockLookup dashboard releases.
Replaces legacy batch file control planes with strict, fail-closed Python orchestration.

This is the single supported live-publish entry point (both release groups). It assumes the
trusted-ai analysis artifact set already exists and is valid; pass --generate to have it call
tools/operate_stocklookup.py first (as a plain child process, no --publish/--live of its own)
to rebuild and validate that set before publishing. tools/operate_stocklookup.py remains fully
supported standalone for that same build/validate role, but its own --live flag is retired:
this script is the only thing that may commit and push a release.

--generate's trusted-ai/all child command always passes --include-dnse-foreign-flow and
--include-current-state-market-risk: this is the authoritative production release profile,
so a qualified, production-enabled capability reaches every real release without an
operator having to remember an extra flag. Each capability itself stays an explicit,
default-off, independently testable flag one layer down (operate_stocklookup.py,
export_ai_bundle.py) -- only this orchestrator forces it on.
"""

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
import subprocess
from dataclasses import dataclass
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PRODUCER_ROOT = SCRIPT_PATH.parent.parent
if str(PRODUCER_ROOT) not in sys.path:
    sys.path.insert(0, str(PRODUCER_ROOT))

from release_checkout_identity import (  # noqa: E402
    CANONICAL_WEB_ROOT,
    GITHUB_SOURCE_UPDATED,
    PUBLISHED,
    ReleaseIdentityError,
    assert_producer_publisher_file,
    assert_web_checkout_identity,
    publication_state_after_push,
)

WHOLE_MARKET_ALLOWLIST = (
    "screen_snapshot.csv",
    "market_breadth.csv",
    "ai_report_latest.md",
    "ai_report_latest.json",
    "data/macro_snapshot.json",
    "data/macro_snapshot.js",
    "data/candlestick_patterns.json",
    "data/candlestick_patterns.js",
    "data/candle_signals.json",
    "data/candle_signals.js",
    "data/sector_heatmap.json",
    "data/sector_heatmap.js",
    "data/screener_data.js",
    "data/build_info.json",
    "data/build_info.js",
    "data/current_decision_cockpit.json",
)

LOCK_FILE_PATH = Path(tempfile.gettempdir()) / "stock_lookup_release_orchestrator.lock"


class SingleInstanceLock:
    """Ensures only one release orchestrator process runs at any given time."""

    def __enter__(self):
        try:
            self.fd = os.open(str(LOCK_FILE_PATH), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(self.fd, str(os.getpid()).encode("utf-8"))
        except OSError:
            raise RuntimeError(f"Lock file exists: {LOCK_FILE_PATH}. Another release process is running.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            os.close(self.fd)
            if LOCK_FILE_PATH.exists():
                LOCK_FILE_PATH.unlink()
        except Exception:
            pass


def compute_sha256(filepath: Path) -> str:
    if not filepath.is_file():
        return ""
    return hashlib.sha256(filepath.read_bytes()).hexdigest()


def get_git_output(args: list[str], cwd: Path) -> tuple[int, str]:
    res = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, shell=False)
    return res.returncode, res.stdout.strip()


def get_runtime_session(backend_dir: Path) -> str:
    snapshot_path = backend_dir / "screen_snapshot.csv"
    if not snapshot_path.is_file():
        raise FileNotFoundError(f"Missing backend artifact: {snapshot_path}")
    with open(snapshot_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        dates = [row["date"].strip() for row in reader if row.get("date") and row.get("exchange") != "DELISTED"]
    if not dates:
        raise ValueError(f"No active session dates found in {snapshot_path}")
    return max(dates)


def capture_allowlist_state(web_dir: Path) -> dict[str, bytes]:
    state = {}
    for rel in WHOLE_MARKET_ALLOWLIST:
        p = web_dir / rel
        if p.is_file():
            state[rel] = p.read_bytes()
    return state


def restore_allowlist_state(web_dir: Path, state: dict[str, bytes]):
    for rel, content in state.items():
        p = web_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)


@dataclass
class DashboardTransactionSnapshot:
    """Exact tracked Dashboard bytes and HEAD before a live ``all`` transaction.

    ``all`` first promotes the independently verified trusted subset without git,
    then lets the existing whole-market publisher build and commit the complete
    release.  Any failure before that one final commit must restore the clean
    Dashboard worktree without touching ignored operator tools or unrelated files.
    """

    head: str
    tracked: dict[str, bytes]


def capture_dashboard_transaction(web_dir: Path) -> DashboardTransactionSnapshot:
    rc, head = get_git_output(["rev-parse", "HEAD"], web_dir)
    if rc != 0:
        raise RuntimeError("cannot capture Dashboard transaction HEAD")
    result = subprocess.run(["git", "ls-files", "-z"], cwd=web_dir, capture_output=True,
                            check=False)
    if result.returncode != 0:
        raise RuntimeError("cannot enumerate Dashboard tracked files for rollback")
    paths = [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]
    return DashboardTransactionSnapshot(
        head=head,
        tracked={relative: (web_dir / relative).read_bytes() for relative in paths},
    )


def restore_dashboard_transaction(web_dir: Path, snapshot: DashboardTransactionSnapshot) -> None:
    """Restore tracked bytes and remove a local failed final commit without ``--hard``.

    This deliberately never enumerates/deletes untracked paths, preserving ignored
    operator-owned tools such as the local Tailwind executable.  The transaction is
    entered only from a clean Dashboard index, so a mixed reset to the captured HEAD
    merely drops staging from a failed local final commit before byte restoration.
    """
    rc, current_head = get_git_output(["rev-parse", "HEAD"], web_dir)
    if rc != 0:
        raise RuntimeError("cannot read Dashboard HEAD during rollback")
    if current_head != snapshot.head:
        ancestor_rc, _ = get_git_output(["merge-base", "--is-ancestor", snapshot.head, current_head], web_dir)
        if ancestor_rc != 0:
            raise RuntimeError("Dashboard HEAD changed outside the release transaction; refusing rollback")
        result = subprocess.run(["git", "reset", "--mixed", snapshot.head], cwd=web_dir,
                                capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError("failed to remove local unpushed release commit during rollback")
    else:
        result = subprocess.run(["git", "reset"], cwd=web_dir, capture_output=True,
                                text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError("failed to clear the Dashboard index during rollback")
    for relative, content in snapshot.tracked.items():
        path = web_dir / relative
        if not path.is_file() or path.read_bytes() != content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    rc, dirty = get_git_output(["status", "--porcelain", "--untracked-files=no"], web_dir)
    if rc != 0 or dirty:
        raise RuntimeError(f"Dashboard tracked rollback verification failed: {dirty}")


def require_live_remote_head(web_dir: Path, branch: str) -> None:
    """Fetch once before an ``all`` transaction and require HEAD == origin/branch.

    Isolated test fixtures intentionally have no remote.  Canonical live releases do,
    and must never start a transaction from stale remote state.
    """
    fixture = os.environ.get("STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE")
    if fixture and Path(fixture).resolve() == web_dir.resolve():
        return
    result = subprocess.run(["git", "fetch", "origin", branch], cwd=web_dir,
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError("failed to fetch Dashboard origin before release transaction")
    rc, head = get_git_output(["rev-parse", "HEAD"], web_dir)
    rc_remote, remote = get_git_output(["rev-parse", f"origin/{branch}"], web_dir)
    if rc != 0 or rc_remote != 0 or head != remote:
        raise RuntimeError("Dashboard HEAD differs from origin before release transaction; refusing stale-head mutation")


def resolve_research_changes_v2_baseline(web_dir: Path, backend_dir: Path, producer_dir: Path) -> Path | None:
    """Derive the V2 research-change comparison baseline from what is actually served.

    The correct comparison baseline for the next release is the immediately previous SERVED
    state, not a fixed file picked once and reused release after release. `web_dir` is the
    live-served checkout this orchestrator already validated above; if it is currently serving
    an analysis bundle, this reconstructs -- deterministically, from that bundle's own retained
    content -- the exact V2 snapshot `export_ai_bundle.py` computed for it at serve time (the
    same pure function, run again). No snapshot or event ID is ever hardcoded here: an unserved
    (first-ever) checkout legitimately yields no baseline, and callers may still force a
    specific baseline via --research-changes-v2-baseline.
    """
    served_bundle_path = web_dir / "analysis_bundle.json"
    if not served_bundle_path.is_file():
        return None
    try:
        served_bundle = json.loads(served_bundle_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    sys.path.insert(0, str(producer_dir))
    from qualified_research_snapshot_v2 import from_served_bundle
    baseline = from_served_bundle(served_bundle)
    baseline_dir = backend_dir / "reports"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = baseline_dir / "research_changes_v2_served_baseline.json"
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    return baseline_path


def build_parser() -> argparse.ArgumentParser:
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--live", action="store_true", help="cho phép ghi file, commit/push thật")
    parent_parser.add_argument("--expected-session", type=str, default=None, help="YYYY-MM-DD expected market session date")
    parent_parser.add_argument("--expected-dashboard-head", type=str, default=None, help="Expected git commit SHA for market-dashboard repo")
    parent_parser.add_argument("--backend-dir", type=str, default=None, help="Override backend runtime directory")
    parent_parser.add_argument("--web-dir", type=str, default=None, help="Override web directory")
    parent_parser.add_argument("--producer-dir", type=str, default=None, help="Override producer directory")
    parent_parser.add_argument("--python-exe", type=str, default=sys.executable, help="Python executable for child calls")
    parent_parser.add_argument("--verify-live-url", type=str, default=None,
                                help="With trusted-ai --live: after publish_release.py pushes, "
                                    "re-fetch each artifact from this origin and compare hashes "
                                    "before reporting success (passed through unchanged).")
    parent_parser.add_argument("--generate", action="store_true",
                               help="Before publishing, run tools/operate_stocklookup.py against "
                                    "--backend-dir to rebuild and validate the trusted-ai analysis "
                                    "artifact set (sidecar, bundle, manifest). No effect on the "
                                    "whole-market group alone, which has nothing for it to build. "
                                    "In live mode this passes --execute so the rebuild actually "
                                    "writes; otherwise operate_stocklookup.py runs its own read-only "
                                    "dry run. Never passes --publish/--live to the child: this "
                                    "script remains the only thing that commits and pushes.")
    parent_parser.add_argument("--governed-official-evidence-root", type=Path,
                               help="Explicit governed evidence root used only with --generate.")
    parent_parser.add_argument("--research-changes-v2-baseline", type=Path,
                               help="Explicit previous-served V2 snapshot used only with --generate. "
                                    "Overrides the automatic baseline this orchestrator otherwise "
                                    "reconstructs from --web-dir's currently served analysis bundle.")
    parent_parser.add_argument("--cockpit-projection-source", type=Path,
                               help="Explicit Producer current_decision_cockpit_projection.json for cockpit release only.")
    parent_parser.add_argument("--expected-cockpit-operation-identity",
                               help="Exact Daily Research Session Operation identity for cockpit release only.")

    parser = argparse.ArgumentParser(
        prog="release_orchestrator.py",
        description="Authoritative StockLookup release orchestrator.",
        parents=[parent_parser]
    )

    subparsers = parser.add_subparsers(dest="group", help="Release group subcommand")
    subparsers.add_parser("whole-market", help="Publish whole-market frontend & dashboard only", parents=[parent_parser])
    subparsers.add_parser("trusted-ai", help="Publish trusted AI subset only", parents=[parent_parser])
    subparsers.add_parser("all", help="Publish one atomic trusted-AI + whole-market Dashboard session", parents=[parent_parser])
    subparsers.add_parser("cockpit", help="Publish one explicit Decision Cockpit projection", parents=[parent_parser])
    return parser


def orchestrate(args: argparse.Namespace) -> int:
    if not args.group:
        sys.stderr.write("[ERROR] Missing release group subcommand. Must specify 'whole-market', 'trusted-ai', or 'all'.\n")
        return 1

    group = args.group
    live = args.live
    expected_session = args.expected_session
    expected_dashboard_head = args.expected_dashboard_head

    backend_dir = Path(args.backend_dir or os.environ.get("STOCK_LOOKUP_BACKEND_DIR") or PRODUCER_ROOT / ".." / "dashboard-runtime").resolve()
    web_dir = Path(args.web_dir or os.environ.get("STOCK_LOOKUP_WEB_DIR") or CANONICAL_WEB_ROOT).resolve()
    producer_dir = Path(args.producer_dir or PRODUCER_ROOT).resolve()
    python_exe = args.python_exe

    with SingleInstanceLock():
        try:
            assert_producer_publisher_file(SCRIPT_PATH, role="release_orchestrator")
            # Path/legacy/runtime refusals happen before any git cwd on web_dir, so a
            # deleted or non-directory legacy checkout still fail-closes.
            assert_web_checkout_identity(web_dir, backend_dir=backend_dir, live=False)
        except ReleaseIdentityError as exc:
            sys.stderr.write(f"[ERROR] {exc}\n")
            return 1

        # 1. Fail closed if Backend == Web
        if backend_dir.resolve() == web_dir.resolve():
            sys.stderr.write(f"[ERROR] BACKEND_ROOT ({backend_dir}) equals WEB_ROOT ({web_dir}). Single-root execution forbidden.\n")
            return 1

        # 2. Runtime session validation
        actual_session = "N/A"
        if group != "cockpit":
            actual_session = get_runtime_session(backend_dir)
        if group == "cockpit":
            if not args.cockpit_projection_source or not expected_session or not args.expected_cockpit_operation_identity:
                sys.stderr.write("[ERROR] cockpit requires --cockpit-projection-source, --expected-session, and --expected-cockpit-operation-identity.\n")
                return 1
            try:
                cockpit = json.loads(args.cockpit_projection_source.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                sys.stderr.write(f"[ERROR] Invalid cockpit projection: {exc}\n")
                return 1
            if cockpit.get("session") != expected_session or (cockpit.get("source") or {}).get("operation_identity") != args.expected_cockpit_operation_identity:
                sys.stderr.write("[ERROR] Cockpit projection session/operation identity mismatch.\n")
                return 1
        if group != "cockpit" and expected_session and actual_session != expected_session:
            sys.stderr.write(f"[ERROR] Session mismatch: expected '{expected_session}', got '{actual_session}'. Aborting.\n")
            return 1

        # 3. Git validation for Web repo
        rc, dashboard_head = get_git_output(["rev-parse", "HEAD"], web_dir)
        if rc != 0:
            sys.stderr.write(f"[ERROR] Failed to get Dashboard HEAD in {web_dir}\n")
            return 1

        if expected_dashboard_head and not dashboard_head.startswith(expected_dashboard_head):
            sys.stderr.write(f"[ERROR] Dashboard HEAD mismatch: expected '{expected_dashboard_head}', got '{dashboard_head}'. Aborting.\n")
            return 1

        rc, dashboard_upstream = get_git_output(["rev-parse", "@{u}"], web_dir)
        rc_origin, origin_url = get_git_output(["remote", "get-url", "origin"], web_dir)
        rc_branch, web_branch = get_git_output(["branch", "--show-current"], web_dir)
        rc_om, origin_main = get_git_output(["rev-parse", "origin/main"], web_dir)
        rc_top, git_toplevel = get_git_output(["rev-parse", "--show-toplevel"], web_dir)
        try:
            assert_web_checkout_identity(
                web_dir,
                backend_dir=backend_dir,
                origin_url=origin_url if rc_origin == 0 else None,
                branch=web_branch if rc_branch == 0 else None,
                head=dashboard_head,
                origin_main=origin_main if rc_om == 0 else None,
                live=live,
                git_toplevel=Path(git_toplevel) if rc_top == 0 and git_toplevel else None,
            )
        except ReleaseIdentityError as exc:
            sys.stderr.write(f"[ERROR] {exc}\n")
            return 1
        if rc == 0 and live and dashboard_head != dashboard_upstream:
            sys.stderr.write(f"[ERROR] Dashboard HEAD ({dashboard_head}) differs from upstream ({dashboard_upstream}) in live mode. Aborting.\n")
            return 1

        rc, staged_files = get_git_output(["diff", "--cached", "--name-only"], web_dir)
        if staged_files:
            sys.stderr.write(f"[ERROR] Staged files exist in Dashboard repo: {staged_files}. Aborting.\n")
            return 1

        # 4. Self-integrity check
        running_sha256 = compute_sha256(SCRIPT_PATH)

        # 5. Construct child argv plans
        trusted_ai_invoked = False
        generate_invoked = False
        argv_plans = []

        if group in ("trusted-ai", "all") and args.generate:
            generate_invoked = True
            cmd_generate = [python_exe, str(producer_dir / "tools" / "operate_stocklookup.py"),
                            "--runtime-root", str(backend_dir)]
            if live:
                # --execute is operate_stocklookup.py's own real-write gate (rebuild
                # sidecar + bundle + manifest, verify, Consumer-validate -- see its
                # module docstring). Only send it when this orchestrator itself is
                # --live: a plain --generate preflight must fall through to
                # operate_stocklookup.py's own already-implemented read-only dry run
                # (real preflight/database/share-freshness/sidecar-consistency
                # validation, zero artifact writes), never quietly perform real
                # generation writes under a "preview" label. This was previously
                # unconditional -- the exact defect test_generate_passes_execute_only_in_live_mode
                # exists to catch.
                cmd_generate.append("--execute")
            # The authoritative production release profile opts in the
            # qualified DNSE foreign-flow VALUE capability unconditionally (both
            # preview and live), independent of the --execute gate above. The
            # capability itself stays an explicit, independently testable,
            # default-off flag one layer down (operate_stocklookup.py /
            # export_ai_bundle.py) -- this is the one place that turns it on for a
            # real release, same status as every ticker already carries this
            # bundle: fail-closed to status="missing" when a ticker has no
            # retained observations, never a required input.
            cmd_generate.append("--include-dnse-foreign-flow")
            # Same status as the foreign-flow capability immediately above: a
            # qualified, production-enabled, default-off capability one layer
            # down, forced on unconditionally (both preview and live) only
            # here. Fails closed to status="not_qualified" for every ticker
            # outside the evidence-bounded set (currently HPG only), never a
            # required input and never a fabricated beta/correlation.
            cmd_generate.append("--include-current-state-market-risk")
            if args.governed_official_evidence_root:
                cmd_generate += ["--governed-official-evidence-root", str(args.governed_official_evidence_root)]
            research_changes_v2_baseline = (args.research_changes_v2_baseline
                                            or resolve_research_changes_v2_baseline(web_dir, backend_dir, producer_dir))
            if research_changes_v2_baseline:
                cmd_generate += ["--research-changes-v2-baseline", str(research_changes_v2_baseline)]
            argv_plans.append(cmd_generate)

        if group in ("trusted-ai", "all"):
            trusted_ai_invoked = True
            cmd = [python_exe, str(producer_dir / "tools" / "publish_release.py"), "--source", str(backend_dir), "--destination", str(web_dir)]
            # ``all`` is one logical release.  Preserve publish_release.py's staging,
            # hash, session and Consumer gates, but defer the only Dashboard commit/push
            # to publish_dashboard.py after it has added the whole-market surfaces.
            if group == "all":
                cmd.append("--no-git")
            if live:
                cmd.append("--live")
                if group == "trusted-ai" and args.verify_live_url:
                    cmd += ["--verify-live-url", args.verify_live_url]
            argv_plans.append(cmd)

        if group in ("whole-market", "all"):
            cmd_build = [python_exe, str(producer_dir / "tools" / "build_frontend.py"), "--web-dir", str(web_dir)]
            if live:
                cmd_build.append("--live")
            argv_plans.append(cmd_build)

            cmd_pub = [python_exe, str(producer_dir / "publish_dashboard.py")]
            if group == "all":
                # The final publisher owns the one commit/push and must stage the
                # trusted subset explicitly, never merely because an HTML reference
                # happened to include one of its files.
                cmd_pub.append("--include-trusted-subset")
            if live:
                cmd_pub.append("--live")
            argv_plans.append(cmd_pub)

        if group == "cockpit":
            cmd_cockpit = [python_exe, str(producer_dir / "publish_dashboard.py"), "--cockpit-projection-source", str(args.cockpit_projection_source), "--expected-cockpit-session", expected_session, "--expected-cockpit-operation-identity", args.expected_cockpit_operation_identity]
            if live:
                cmd_cockpit.append("--live")
            argv_plans.append(cmd_cockpit)

        # 6. Print Execution Attestation
        print("============================================================")
        print("STOCK LOOKUP RELEASE ORCHESTRATOR - EXECUTION ATTESTATION")
        print(f"Orchestrator Path     : {SCRIPT_PATH}")
        print(f"Orchestrator SHA256   : {running_sha256}")
        print(f"Dashboard HEAD        : {dashboard_head}")
        print(f"Dashboard Upstream    : {dashboard_upstream if rc == 0 else 'N/A'}")
        print(f"SELECTED_GROUP        : {group}")
        print(f"LIVE_MODE             : {live}")
        print(f"EXPECTED_SESSION      : {expected_session or 'N/A'}")
        print(f"ACTUAL_SESSION        : {actual_session}")
        print(f"TRUSTED_AI_INVOKED    : {'true' if trusted_ai_invoked else 'false'}")
        print(f"GENERATE_INVOKED      : {'true' if generate_invoked else 'false'}")
        print(f"ZERO_MUTATION         : {'PASS' if not live else 'N/A (LIVE)'}")
        if group == "all":
            print("ALL_TRANSACTION       : one final Dashboard commit/push; trusted promotion is --no-git")
        print("Execution Plans:")
        for idx, plan in enumerate(argv_plans, 1):
            print(f"  Plan {idx}: {plan}")
        print("============================================================")

        # 7. Capture pre-run state for rollback.  ``all --live`` mutates both
        # trusted and whole-market tracked files before its one final commit, so
        # its rollback boundary is the complete clean tracked Dashboard tree.
        transaction_snapshot = None
        pre_run_state = capture_allowlist_state(web_dir)
        if live and group == "all":
            try:
                rc, tracked_dirty = get_git_output(["status", "--porcelain", "--untracked-files=no"], web_dir)
                if rc != 0 or tracked_dirty:
                    raise RuntimeError("Dashboard tracked worktree is not clean before all-release transaction")
                require_live_remote_head(web_dir, web_branch)
                transaction_snapshot = capture_dashboard_transaction(web_dir)
            except RuntimeError as exc:
                sys.stderr.write(f"[ERROR] {exc}\n")
                return 1

        # 8. Execute child process plans
        env = os.environ.copy()
        env["STOCK_LOOKUP_BACKEND_DIR"] = str(backend_dir)
        env["STOCK_LOOKUP_WEB_DIR"] = str(web_dir)
        env["STOCK_LOOKUP_PRODUCER_DIR"] = str(producer_dir)

        try:
            for plan in argv_plans:
                print(f"[INFO] Executing child process: {' '.join(plan)}")
                child_cwd = web_dir
                plan_text = " ".join(plan)
                if "operate_stocklookup.py" in plan_text:
                    child_cwd = producer_dir
                res = subprocess.run(plan, cwd=child_cwd, env=env, capture_output=False, shell=False)
                if res.returncode != 0:
                    sys.stderr.write(f"[ERROR] Child process failed with exit code {res.returncode}: {plan}\n")
                    if live:
                        try:
                            if transaction_snapshot is not None:
                                sys.stderr.write("[ROLLBACK] Restoring the pre-release Dashboard transaction...\n")
                                restore_dashboard_transaction(web_dir, transaction_snapshot)
                            else:
                                sys.stderr.write("[ROLLBACK] Restoring pre-run whole-market allowlist files...\n")
                                restore_allowlist_state(web_dir, pre_run_state)
                        except RuntimeError as rollback_exc:
                            sys.stderr.write(f"[ROLLBACK] FAILED: {rollback_exc}\n")
                    return res.returncode
        except Exception as exc:
            sys.stderr.write(f"[ERROR] Exception during execution: {exc}\n")
            if live:
                try:
                    if transaction_snapshot is not None:
                        restore_dashboard_transaction(web_dir, transaction_snapshot)
                    else:
                        restore_allowlist_state(web_dir, pre_run_state)
                except RuntimeError as rollback_exc:
                    sys.stderr.write(f"[ROLLBACK] FAILED: {rollback_exc}\n")
            return 1

        if live:
            state = publication_state_after_push(
                local_validation_pass=True,
                ci_pass=False,
                pages_pass=False,
                public_verify_pass=False,
            )
            print(f"[STATE] {GITHUB_SOURCE_UPDATED}: git push is not {PUBLISHED}.")
            print("[STATE] PUBLISHED requires local validation PASS, Dashboard CI PASS on the same SHA, Deploy Pages PASS on the same SHA, and cache-busted public session verification PASS.")
            print(f"[OK] Release orchestration for '{group}' reached {state}.")
        else:
            print(f"[OK] Release orchestration for '{group}' completed successfully.")
        return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return orchestrate(args)


if __name__ == "__main__":
    sys.exit(main())
