"""The one supported StockLookup operating command.

Refreshes and validates the production analysis artifact set end to end, in one process,
under a single-instance lock, with an explicit rollback path. It COMPOSES the existing
entry points rather than reimplementing them:

    tools/build_statement_taxonomy_sidecar.py   generated taxonomy sidecar
    export_ai_bundle.py                         bundle + manifest + exact-session proof
    export_ai_bundle.py --verify                recorded-vs-on-disk sha256 of every source
    ai-core-private/builders/build_ticker_context.py
                                                Consumer load + exact-session validation
    tools/publish_release.py                    the only thing allowed to publish

WHAT IT DOES NOT DO
    It never fetches prices, macro series or news, and never writes to vn_stock.db or any
    other authoritative store: refreshing an analysis bundle is not a reason to mutate
    market or financial data. Use `pipeline_scheduler.py` for the full daily market chain;
    this command consumes what that chain already produced.

QUALIFIED HISTORICAL RESEARCH LANE (Phase 4B/4C/5A/5B, opt-in)
    --include-historical-decision-analysis / --include-portfolio-risk-analysis /
    --include-historical-scaleout / --include-qualified-research-brief forward the matching
    export_ai_bundle.py flags. They were previously reachable only by invoking
    export_ai_bundle.py directly, bypassing this command's verify/Consumer-validate/rollback
    gates. Pass all four together for real brief content; each degrades to an honest
    ineligible/insufficient-evidence result on its own rather than failing.

QUALIFIED MARKET OBSERVATIONS (opt-in, independent of the lane above)
    --include-qualified-market-observations forwards the matching export_ai_bundle.py flag.
    A different lane from the one above: it is gated on a single-provider retained OHLCV
    window through market_basis_capability_registry.py, not on the fundamental-evidence
    pilot set, so it applies to every production ticker, not just HPG/VNM/VCB. Always
    historical_only, is_actionable=False, liquidity_actionable=False -- it never touches the
    generic price_basis_verified/volume_basis_verified gate.

DNSE FOREIGN-FLOW VALUE (opt-in, independent of both lanes above)
    --include-dnse-foreign-flow forwards the matching export_ai_bundle.py flag. Attaches
    tickers[ticker].foreign_flow from the retained DNSE foreign-investor VALUE store
    (buy/sell/net VND per session plus fail-closed multi-session window summaries and an
    exact-trading-session freshness verdict) for whichever tickers have retained
    observations -- every other ticker reports status="missing", never a fabricated value,
    and research eligibility for every ticker is unaffected either way. Always
    is_actionable=False. This command's own default keeps it off, same as every other
    --include-* flag here; tools/release_orchestrator.py's --generate step is the
    authoritative production release profile that opts it in for a real release.

MODES
    (default)              dry run. Reads and reports; writes nothing, publishes nothing.
    --execute              rebuild sidecar + bundle + manifest, verify, Consumer-validate,
                           write the operating report.
    --execute --publish --web-root <served checkout>
                           additionally run the release publisher in ITS dry-run mode.

WHY --web-root IS REQUIRED (for --publish)
    Publication is a promotion from the runtime root into the checkout that is actually
    served, and the runtime root is not that checkout: it routinely sits on a feature
    branch with unrelated generated-artifact drift. Publishing into it committed that drift
    to a branch nothing serves. Naming the served destination explicitly is what makes the
    release land where a reader will see it.

LIVE PUBLISH IS NOT DONE HERE
    --live is retired from this command. tools/release_orchestrator.py is the single
    supported live-publish authority for both release groups (`trusted-ai`, `whole-market`,
    `all`) — run `release_orchestrator.py trusted-ai --live`, adding `--generate` to have it
    call this command's build+validate stage first. This command still builds, verifies and
    Consumer-validates the trusted-ai artifact set exactly as before (--execute, optionally
    --publish for a non-mutating dry-run preview of the release) — only the mutating
    stage/commit/push path moved to release_orchestrator.py, so a live run only ever has one
    lock, one attestation, and one place that can push.

EXIT CODES
    0 success   1 a gate failed (artifacts restored where a rollback point existed)
    2 bad invocation / unusable runtime root / --live   3 another instance holds the lock
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json  # noqa: E402
from pipeline_scheduler import FileLockError, PipelineLock  # noqa: E402
from runtime_paths import RUNTIME_ROOT_ENV  # noqa: E402
from statement_taxonomy_sidecar import SIDECAR_FILENAME  # noqa: E402

WORKSPACE = ROOT.parent
CONSUMER_ROOT = WORKSPACE / "ai-core-private"

#: The exact artifact set this command owns. Also the rollback unit: either all of these
#: are the new session's, or all of them are the previous session's.
PRODUCTION_ARTIFACTS = ("analysis_bundle.json", "bundle_manifest.json", "focus_extract.json",
                        SIDECAR_FILENAME)
#: Upstream artifacts the export consumes. Missing any of them means the daily market chain
#: has not run for this session and no bundle may be built from it.
REQUIRED_UPSTREAM = ("vn_stock.db", "screen_snapshot_live.csv", "market_breadth.csv",
                     "ta_signals.csv", "analysis_latest.json", "macro_snapshot.csv",
                     "Focus_Analysis.md")

#: Remediation codes. A stale input used to surface as `exit code 1` from whichever
#: subprocess happened to notice, which named neither the stale input nor the command that
#: refreshes it. Each code below is one stage of the daily chain and one next action.
METADATA_REFRESH_REQUIRED = "METADATA_REFRESH_REQUIRED"
FOCUS_ANALYSIS_REFRESH_REQUIRED = "FOCUS_ANALYSIS_REFRESH_REQUIRED"
CONTEXT_PACKAGE_REFRESH_REQUIRED = "CONTEXT_PACKAGE_REFRESH_REQUIRED"

#: The daily chain, in dependency order. Each stage consumes what the one before it produced,
#: so a stage that runs on a predecessor's stale output produces a mixed-session artifact that
#: looks current. The order is enforced in `run()` and asserted in the test suite.
DAILY_STAGE_ORDER = ("refresh_metadata", "prepare_inputs", "export_analysis_bundle",
                     "validate_consumer", "publish_release")
#: The published production ticker set. Kept identical to what the last successful export
#: actually shipped -- narrowing it would silently drop tickers the dashboard already
#: presents. Verified 2026-08-09 against the served bundle at
#: worktrees/market-dashboard-main (analysis_bundle.json.tickers_requested): exactly these
#: 11, no VNINDEX. VNINDEX was previously listed here as "deliberately included ... to
#: exercise unproven_tickers in production", but the served release has never actually
#: shipped it -- unproven_tickers is `[]` there, not `["VNINDEX"]`. That drift is what
#: caused a real incident: VNINDEX's context package (an index has no issuer, so nothing
#: about it is analysis-lane-eligible) went stale independently of the other 11 tickers,
#: and requesting VNINDEX by default tripped `preflight_derived_session_inputs` for a
#: symbol the shipped universe never included, inviting an unnecessary `--prepare-inputs`
#: run to satisfy a gate for a ticker that was never part of what gets published. If
#: exercising `unproven_tickers` in production is wanted again, add VNINDEX back
#: deliberately with `--tickers` on a specific run, not silently via this default.
DEFAULT_TICKERS = ("POW", "SSI", "HPG", "EVF", "PAN", "PNJ", "FPT", "QNS", "VNM",
                   "PVD", "NVL")
#: builders/build_ticker_context_config.json::max_batch_size
CONTEXT_BATCH_SIZE = 10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class GateFailure(RuntimeError):
    """A named operating gate refused to pass."""

    def __init__(self, gate: str, detail: str):
        super().__init__(f"{gate}: {detail}")
        self.gate = gate
        self.detail = detail


class Operator:
    def __init__(self, root: Path, tickers: list[str], *, execute: bool, publish: bool,
                 live: bool, prepare: bool = False, web_root: Path | None = None,
                 verify_live_url: str | None = None,
                 include_canonical_financial_facts: bool = False,
                 include_historical_decision_analysis: bool = False,
                 include_portfolio_risk_analysis: bool = False,
                 include_historical_scaleout: bool = False,
                 include_qualified_research_brief: bool = False,
                 include_qualified_market_observations: bool = False,
                 include_dnse_foreign_flow: bool = False,
                 governed_official_evidence_root: Path | None = None,
                 research_changes_v2_baseline: Path | None = None,
                 refresh_metadata: bool = False,
                 runner: Callable[..., Any] = subprocess.run):
        self.root = root
        self.tickers = tickers
        self.execute = execute
        self.publish = publish
        self.live = live
        self.web_root = web_root
        self.verify_live_url = verify_live_url
        self.include_canonical_financial_facts = include_canonical_financial_facts
        self.include_historical_decision_analysis = include_historical_decision_analysis
        self.include_portfolio_risk_analysis = include_portfolio_risk_analysis
        self.include_historical_scaleout = include_historical_scaleout
        self.include_qualified_research_brief = include_qualified_research_brief
        self.include_qualified_market_observations = include_qualified_market_observations
        self.include_dnse_foreign_flow = include_dnse_foreign_flow
        self.governed_official_evidence_root = governed_official_evidence_root
        self.research_changes_v2_baseline = research_changes_v2_baseline
        self.runner = runner
        self.steps: list[dict[str, Any]] = []
        self.rollback_dir: Path | None = None
        self.database_backup: Path | None = None
        self.prepare = prepare
        self.refresh_metadata = refresh_metadata
        self.reference_session_date: str | None = None
        self.database_backed_up = False
        self.started_at = _now()
        self.env = {**os.environ, RUNTIME_ROOT_ENV: str(root), "PYTHONIOENCODING": "utf-8"}

    # ------------------------------------------------------------------ helpers
    def _record(self, name: str, status: str, **detail: Any) -> dict[str, Any]:
        step = {"step": name, "status": status, "at": _now(), **detail}
        self.steps.append(step)
        print(f"[operate] {name}: {status}"
              + (f" — {detail.get('detail')}" if detail.get("detail") else ""), flush=True)
        return step

    def _run(self, name: str, command: list[str], cwd: Path) -> dict[str, Any]:
        result = self.runner(command, cwd=str(cwd), env=self.env, check=False,
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        step = self._record(name, "passed" if result.returncode == 0 else "failed",
                            exit_code=result.returncode,
                            stdout_tail=(result.stdout or "").strip().splitlines()[-8:],
                            stderr_tail=(result.stderr or "").strip().splitlines()[-8:])
        if result.returncode != 0:
            raise GateFailure(name, f"exit code {result.returncode}")
        return step

    def artifact_hashes(self) -> dict[str, str | None]:
        return {name: (_sha256(self.root / name) if (self.root / name).is_file() else None)
                for name in PRODUCTION_ARTIFACTS}

    # ------------------------------------------------------------------ 1. preflight
    def preflight(self) -> None:
        missing_upstream = [n for n in REQUIRED_UPSTREAM if not (self.root / n).is_file()]
        if missing_upstream:
            raise GateFailure("preflight_upstream",
                              f"required upstream artifact(s) absent: {', '.join(missing_upstream)}")
        if not (self.root / "data_bctc").is_dir():
            raise GateFailure("preflight_upstream", "data_bctc/ is absent; no statement payloads to classify")
        if self.execute and not CONSUMER_ROOT.is_dir():
            raise GateFailure("preflight_consumer", "ai-core-private is not present beside the producer repo")
        self._record("preflight_inputs", "passed",
                     upstream_present=len(REQUIRED_UPSTREAM),
                     statement_payloads=len(list((self.root / "data_bctc").glob("*_balance_sheet_quarter.parquet"))))

    def preflight_database(self) -> str:
        """Read-only SQLite integrity probe plus the reference session anchor.

        Never opened for writing by this command, and the anchor is read with the same
        query `export_ai_bundle.py` uses, so the sidecar can be bound to the session the
        export is about to choose without exporting twice.
        """
        database = self.root / "vn_stock.db"
        connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("PRAGMA busy_timeout = 30000")
            verdict = connection.execute("PRAGMA quick_check").fetchone()
            anchor = connection.execute(
                "SELECT DISTINCT date FROM ohlcv ORDER BY date DESC LIMIT 1").fetchone()
        finally:
            connection.close()
        result = verdict[0] if verdict else "no result"
        if str(result).lower() != "ok":
            raise GateFailure("preflight_database", f"vn_stock.db quick_check returned {result!r}")
        if not anchor or not anchor[0]:
            raise GateFailure("preflight_database", "ohlcv carries no trading session to anchor on")
        self._record("preflight_database", "passed", quick_check=str(result),
                     reference_session_date=anchor[0])
        self.reference_session_date = str(anchor[0])
        return str(anchor[0])

    def preflight_locks(self) -> None:
        stale = [p.name for p in (self.root / "locks").glob("*.lock")] if (self.root / "locks").is_dir() else []
        self._record("preflight_locks", "passed", pre_existing_lock_files=stale,
                     detail=("no interrupted job lock present" if not stale
                             else f"pre-existing lock file(s) {', '.join(stale)}; acquiring exclusively anyway"))

    # ------------------------------------------------------------------ 2. rollback point
    def capture_rollback_point(self) -> None:
        before = self.artifact_hashes()
        if not self.execute:
            self._record("rollback_point", "skipped", detail="dry run writes nothing",
                         current_artifact_sha256=before)
            return
        target = self.root / "reports" / "operate_rollback" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target.mkdir(parents=True, exist_ok=True)
        restored = []
        for name in PRODUCTION_ARTIFACTS:
            source = self.root / name
            if source.is_file():
                shutil.copy2(source, target / name)
                restored.append(name)
        self.rollback_dir = target
        self._record("rollback_point", "passed", saved=restored,
                     current_artifact_sha256=before,
                     detail=f"previous artifact set saved under reports/operate_rollback/{target.name}")

    def rollback(self) -> dict[str, Any]:
        if self.rollback_dir is None:
            return {"performed": False, "reason": "no rollback point was captured"}
        restored, removed = [], []
        for name in PRODUCTION_ARTIFACTS:
            saved = self.rollback_dir / name
            live = self.root / name
            if saved.is_file():
                shutil.copy2(saved, live)
                restored.append(name)
            elif live.is_file():
                # The artifact did not exist before this run; leaving the new one behind
                # would present a partial run as a complete artifact set.
                live.unlink()
                removed.append(name)
        return {"performed": True, "restored": restored, "removed": removed,
                "from": f"reports/operate_rollback/{self.rollback_dir.name}",
                # Deliberately not restored automatically: the analyzer's watchlist_history
                # upsert is session-keyed and idempotent, so silently overwriting a 195 MB
                # database on an unrelated downstream gate failure would be the riskier act.
                "database_backup": (f"reports/operate_rollback/{self.rollback_dir.name}/vn_stock.db"
                                    if self.database_backup else None)}

    # ------------------------------------------------------------------ 3. prepare
    def backup_database(self) -> None:
        """Verified copy of vn_stock.db before anything may write a derived table.

        `stock_analyzer.py --strategy` upserts its own `watchlist_history` table. That is
        a derived analyzer output, not market or financial source data, but it is still a
        write to the authoritative database file, so it only happens behind an explicit
        opt-in, under the single-instance lock, with this restorable copy taken and
        hash-verified first.
        """
        if self.database_backed_up:
            # Two stages may now write the database in one run (metadata refresh, then input
            # preparation). The copy must be the pre-run state, so the second stage must not
            # overwrite it with a state the first stage already changed.
            self._record("backup_database", "skipped",
                         detail="a restorable copy was already taken earlier in this run")
            return
        source = self.root / "vn_stock.db"
        target = (self.rollback_dir or self.root / "reports") / "vn_stock.db"
        target.parent.mkdir(parents=True, exist_ok=True)
        before = _sha256(source)
        shutil.copy2(source, target)
        after = _sha256(target)
        if before != after:
            raise GateFailure("database_backup", "copy of vn_stock.db does not match the original")
        self.database_backup = target
        self.database_backed_up = True
        self._record("database_backup", "passed", sha256=before,
                     detail=f"restorable copy at reports/operate_rollback/{target.parent.name}/vn_stock.db")

    def refresh_metadata_stage(self) -> None:
        """Run `meta_sync.py`, the only thing that moves the provider share observation.

        This is the one stage that writes to `vn_stock.db` and reaches the network, which is
        why it is opt-in: without `--refresh-metadata` this command's contract is unchanged
        and it still writes no authoritative store. It runs before `prepare_inputs()` because
        focus analysis and the context packages are derived from what it refreshes; running it
        after would leave both describing the previous observation.
        """
        self._run("refresh_metadata", [sys.executable, str(ROOT / "meta_sync.py"), "--refresh"],
                  ROOT)

    def preflight_share_freshness(self, session: str) -> dict[str, Any]:
        """Measure current-share authority for this session, and refuse to export a stale one.

        The share observation has no session-scoped freshness gate anywhere else: the
        exporter's `check_freshness` covers the snapshot, signals, focus analysis and context
        packages, but never `metadata`. A universe whose share counts were observed days
        before the session therefore passed every gate silently.
        """
        from market_wide_current_shares_resolver import resolve_market_wide_shares

        summary = resolve_market_wide_shares(self.root, session)
        if summary.get("status") != "measured":
            raise GateFailure("preflight_share_freshness",
                              f"{METADATA_REFRESH_REQUIRED}: share stores unreadable — "
                              f"{summary.get('reason')}")

        counts = dict(summary.get("counts") or {})
        observed = sorted({str(result["observation_date"])
                           for result in (summary.get("tickers") or {}).values()
                           if result.get("observation_date")})
        lagged = counts.get("provider_reported_lagged", 0)
        conflicted = (counts.get("provider_reported_unverifiable_freshness", 0)
                      + counts.get("provider_reported_conflicted", 0))
        named = ("qualified_official", "provider_reported_current", "provider_reported_lagged",
                 "provider_reported_unverifiable_freshness", "provider_reported_conflicted",
                 "unavailable")
        detail = {
            "reference_session": session,
            "shares_observation_date": observed[-1] if observed else None,
            "shares_observation_dates_seen": observed,
            "qualified_official_count": counts.get("qualified_official", 0),
            "provider_reported_current_count": counts.get("provider_reported_current", 0),
            "provider_reported_lagged_count": lagged,
            "conflicted_or_unverifiable_count": conflicted,
            "unavailable_count": counts.get("unavailable", 0),
            # Every lane, so the six named fields above can always be reconciled against the
            # universe rather than quietly dropping a lane the caller did not ask about.
            "withheld_other_count": sum(v for k, v in counts.items() if k not in named),
            "counts": counts,
            "counts_reconcile": bool(summary.get("counts_reconcile")),
            "active_universe_count": summary.get("active_universe_count"),
            "measured_at": summary.get("measured_at"),
        }

        # A lagged share count only reaches an artifact through the canonical-financial-facts
        # section; the default bundle carries no share-derived value at all, which is the
        # documented allowance for exporting while lagged. Nothing is relabelled either way.
        if lagged and self.include_canonical_financial_facts:
            self._record("preflight_share_freshness", "failed", **detail)
            raise GateFailure(
                "preflight_share_freshness",
                f"{METADATA_REFRESH_REQUIRED}: {lagged} tickers carry a share observation from "
                f"{detail['shares_observation_date']}, older than session {session}, and "
                "--include-canonical-financial-facts puts that share count into the export. "
                "Re-run with --refresh-metadata, or drop --include-canonical-financial-facts.")

        allowance = (None if not lagged else
                     "default bundle carries no share-derived value; lag cannot reach the artifact")
        self._record("preflight_share_freshness", "passed", lag_allowed_because=allowance, **detail)
        return detail

    def _focus_analysis_session(self) -> str | None:
        from export_ai_bundle import FOCUS_DATE_RE

        path = self.root / "Focus_Analysis.md"
        if not path.is_file():
            return None
        match = FOCUS_DATE_RE.search(path.read_text(encoding="utf-8", errors="replace"))
        return match.group(1) if match else None

    def _context_package_sessions(self) -> dict[str, str | None]:
        from export_ai_bundle import context_package_session_date, context_packages_dir

        directory = context_packages_dir()
        sessions: dict[str, str | None] = {}
        for ticker in self.tickers:
            # No exclusions: this gate must check exactly what the export's own gate checks,
            # and `export_ai_bundle.load_context_package_info()` is passed the full ticker
            # list. Skipping index symbols here made this preflight pass while the export
            # refused, which is worse than not having the preflight at all.
            path = directory / f"{ticker}_context.json"
            if not path.is_file():
                sessions[ticker] = None
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                sessions[ticker] = None
                continue
            sessions[ticker] = context_package_session_date(payload)
        return sessions

    def preflight_derived_session_inputs(self, session: str) -> None:
        """Refuse before the export when focus analysis or a context package is off-session.

        The exporter already refuses this, correctly, but it refuses as `exit code 1` from a
        subprocess after the sidecar has been rebuilt. Checking here names which input is
        stale and which stage refreshes it, before anything is rebuilt on top of it. Both
        readings use the exporter's own parsers so the two gates cannot drift apart.
        """
        focus_session = self._focus_analysis_session()
        if focus_session != session:
            self._record("preflight_derived_session_inputs", "failed",
                         focus_analysis_session=focus_session, reference_session=session)
            raise GateFailure(
                "preflight_derived_session_inputs",
                f"{FOCUS_ANALYSIS_REFRESH_REQUIRED}: Focus_Analysis.md describes session "
                f"{focus_session!r}, not {session!r}. Re-run with --prepare-inputs.")

        sessions = self._context_package_sessions()
        stale = sorted(ticker for ticker, value in sessions.items() if value != session)
        if stale:
            self._record("preflight_derived_session_inputs", "failed",
                         context_package_sessions=sessions, reference_session=session)
            raise GateFailure(
                "preflight_derived_session_inputs",
                f"{CONTEXT_PACKAGE_REFRESH_REQUIRED}: context packages for "
                f"{', '.join(stale)} do not describe session {session!r} "
                f"({ {t: sessions[t] for t in stale} }). Re-run with --prepare-inputs.")

        self._record("preflight_derived_session_inputs", "passed",
                     reference_session=session, focus_analysis_session=focus_session,
                     context_package_sessions=sessions)

    def prepare_inputs(self) -> None:
        """Rebuild the session-scoped derived artifacts the export consumes.

        Offline by construction: no step here fetches prices, macro series or news. Order
        follows ARTIFACT_DEPENDENCY_GRAPH so no downstream artifact ends up older than the
        upstream it was derived from.
        """
        self._run("prepare_candle_scan", [sys.executable, str(ROOT / "candle_scan.py")], ROOT)
        self._run("prepare_strategy_all",
                  [sys.executable, str(ROOT / "stock_analyzer.py"), "--strategy", "all"], ROOT)
        self._run("prepare_market_scan",
                  [sys.executable, str(ROOT / "stock_analyzer.py"), "--scan-market"], ROOT)
        self._run("prepare_focus_analysis",
                  [sys.executable, str(ROOT / "stock_analyzer.py"), "--tickers", *self.tickers], ROOT)
        # --rotate-existing keeps the previous export beside itself rather than
        # overwriting it; the Consumer never destroys a context package. Index symbols are
        # excluded (no issuer to build a company context for) and the list is chunked to
        # the Consumer's own max_batch_size rather than relying on it silently truncating.
        # Every requested ticker, index symbols included. Excluding them here while the
        # export's freshness gate still checks their packages is what let
        # `prepare_context_packages_*` report success against a package it never rebuilt:
        # `VNINDEX_context.json` stayed on the previous session and blocked the export. The
        # Consumer builds an index context perfectly well; there was nothing to exclude.
        for index in range(0, len(self.tickers), CONTEXT_BATCH_SIZE):
            batch = self.tickers[index:index + CONTEXT_BATCH_SIZE]
            self._run(f"prepare_context_packages_{index // CONTEXT_BATCH_SIZE + 1}",
                      [sys.executable, "builders/build_ticker_context.py",
                       "--tickers", ",".join(batch), "--no-dry-run", "--rotate-existing"],
                      CONSUMER_ROOT)

    # ------------------------------------------------------------------ 4. build
    def build_sidecar(self, session: str | None) -> None:
        command = [sys.executable, str(ROOT / "tools" / "build_statement_taxonomy_sidecar.py"),
                   "--runtime-root", str(self.root)]
        if not self.execute:
            command.append("--check")
            if not (self.root / SIDECAR_FILENAME).is_file():
                self._record("taxonomy_sidecar", "skipped",
                             detail="dry run: no sidecar on disk yet, nothing to check")
                return
            self._run("taxonomy_sidecar_check", command, ROOT)
            return
        command += ["--session-identity", session or "", "--generated-at", _now()]
        self._run("taxonomy_sidecar_build", command, ROOT)

    def verify_canonical_fact_store(self) -> None:
        """Verify the market-wide canonical fact store integrity."""
        from canonical_fact_store import verify as verify_fact_store
        res = verify_fact_store(self.root)
        if not res.get("ok"):
            raise GateFailure("verify_canonical_fact_store", str(res.get("reason") or "fact store check failed"))
        self._record("verify_canonical_fact_store", "passed", checked=res.get("checked"))

    def export_bundle(self) -> None:
        command = [sys.executable, str(ROOT / "export_ai_bundle.py"),
                   "--tickers", ",".join(self.tickers),
                   "--include-fundamental-quality-evidence",
                   "--include-analysis-lane-eligibility"]
        if self.include_canonical_financial_facts:
            command.append("--include-canonical-financial-facts")
        if self.governed_official_evidence_root:
            command += ["--include-canonical-financial-facts", "--include-pillar-a-research-projection", "--include-qualified-research-brief"]
        if self.include_historical_decision_analysis:
            command.append("--include-historical-decision-analysis")
        if self.include_portfolio_risk_analysis:
            command.append("--include-portfolio-risk-analysis")
        if self.include_historical_scaleout:
            command.append("--include-historical-scaleout")
        if self.include_qualified_research_brief:
            command.append("--include-qualified-research-brief")
        if self.research_changes_v2_baseline:
            command += ["--research-changes-v2-baseline", str(self.research_changes_v2_baseline)]
        if self.include_qualified_market_observations:
            command.append("--include-qualified-market-observations")
        if self.include_dnse_foreign_flow:
            command.append("--include-dnse-foreign-flow")
        self._run("export_analysis_bundle", command, ROOT)

    # ------------------------------------------------------------------ 4. verify
    def verify_manifest_sources(self) -> None:
        self._run("verify_manifest_source_hashes",
                  [sys.executable, str(ROOT / "export_ai_bundle.py"),
                   "--verify", str(self.root / "bundle_manifest.json")], ROOT)

    def verify_session_artifacts(self) -> dict[str, Any]:
        """Every artifact the manifest declares for this session must exist and match."""
        manifest = json.loads((self.root / "bundle_manifest.json").read_text(encoding="utf-8"))
        proof = manifest.get("trusted_subset")
        if not isinstance(proof, dict):
            raise GateFailure("verify_session_artifacts",
                              "bundle_manifest.json carries no trusted_subset proof")
        mismatches = []
        for item in proof.get("required_artifacts") or []:
            name = item.get("file")
            path = self.root / str(name)
            if not path.is_file():
                mismatches.append(f"{name}: missing")
            elif _sha256(path) != item.get("sha256"):
                mismatches.append(f"{name}: sha256 differs from the manifest")
        if mismatches:
            raise GateFailure("verify_session_artifacts", "; ".join(mismatches))
        bundle = json.loads((self.root / "analysis_bundle.json").read_text(encoding="utf-8"))
        if proof.get("bundle_reference_session_date") != bundle.get("reference_session_date"):
            raise GateFailure("verify_session_artifacts",
                              "manifest session identity does not match the bundle body")
        step = self._record("verify_session_artifacts", "passed",
                            session_identity=proof.get("session_identity"),
                            proven_tickers=proof.get("tickers"),
                            unproven_tickers=proof.get("unproven_tickers"),
                            required_artifacts=[i.get("file") for i in proof.get("required_artifacts") or []])
        return step

    # ------------------------------------------------------------------ 5. consumer
    def validate_consumer(self) -> None:
        script = (
            "import json,sys;"
            "sys.path.insert(0,'.');"
            "from builders import build_ticker_context as b;"
            "cfg=json.load(open('builders/build_ticker_context_config.json',encoding='utf-8'));"
            "p,w=b.load_optional_analysis_bundle(cfg);"
            "v=p.get('trusted_subset_validation') or {};"
            "print(json.dumps({'warning':w,'validation':v},ensure_ascii=False));"
            "sys.exit(0 if v.get('integrity_state')=='exact_session_verified' else 1)"
        )
        self._run("consumer_exact_session_validation", [sys.executable, "-c", script], CONSUMER_ROOT)

    def consumer_context_smoke(self) -> None:
        self._run("consumer_context_smoke",
                  [sys.executable, "builders/build_ticker_context.py",
                   "--tickers", ",".join(self.tickers[:2]), "--dry-run"], CONSUMER_ROOT)

    # ------------------------------------------------------------------ 6. publish
    def publish_release(self) -> None:
        """Promote the verified artifact set into the served checkout, atomically.

        Delegates to `tools/publish_release.py`, which owns the release boundary: an exact
        allowlist, staging, hash verification against the manifest, the Consumer's own
        exact-session validator, a hash-verified rollback copy, atomic rename promotion, and
        a git commit restricted to the allowlist. Nothing about "which files are dirty"
        enters the decision.
        """
        if self.web_root is None:
            raise GateFailure("publish_release", "--publish requires --web-root")
        command = [sys.executable, str(ROOT / "tools" / "publish_release.py"),
                   "--source", str(self.root), "--destination", str(self.web_root),
                   "--json-report", str(self.root / "reports" / "publish_release_latest.json")]
        if self.verify_live_url:
            command += ["--verify-live-url", self.verify_live_url]
        if self.live:
            command.append("--live")
        self._run("publish_release_live" if self.live else "publish_release_dry_run",
                  command, ROOT)

    def post_publish_smoke(self) -> None:
        bundle = json.loads((self.root / "analysis_bundle.json").read_text(encoding="utf-8"))
        problems = []
        if not bundle.get("reference_session_date"):
            problems.append("published bundle has no reference_session_date")
        if not isinstance(bundle.get("tickers"), dict) or not bundle["tickers"]:
            problems.append("published bundle carries no ticker entries")
        if bundle.get("price_basis_verified") is not True and bundle.get("is_actionable") is True:
            problems.append("bundle claims actionable output on an unverified price basis")
        if self.live and self.publish and self.web_root is not None:
            # The release is only published if the served checkout holds these exact bytes.
            for name, digest in self.artifact_hashes().items():
                served = self.web_root / name
                if not served.is_file():
                    problems.append(f"{name} is absent from the served checkout")
                elif _sha256(served) != digest:
                    problems.append(f"{name} in the served checkout does not match the release")
        if problems:
            raise GateFailure("post_publish_smoke", "; ".join(problems))
        self._record("post_publish_smoke", "passed",
                     reference_session_date=bundle.get("reference_session_date"),
                     tickers=len(bundle.get("tickers") or {}),
                     price_basis=bundle.get("price_basis"),
                     price_basis_verified=bundle.get("price_basis_verified"),
                     volume_basis=bundle.get("volume_basis"),
                     volume_basis_verified=bundle.get("volume_basis_verified"))

    # ------------------------------------------------------------------ report
    def market_wide_shares_coverage(self) -> dict[str, Any]:
        """Measure current-share authority across the universe, for the session just resolved.

        Measured on every run. This block previously carried the counts as literals, so the
        report asserted a market-wide coverage figure that no run had computed and that no
        data change could ever move. A measurement that cannot fail is not a measurement.

        Never raises: a report that cannot be produced is reported as such, and an
        unmeasurable coverage block never fails a run whose artifacts are otherwise sound.
        """
        if not self.reference_session_date:
            return {"status": "unavailable", "reason": "no reference session was resolved"}
        try:
            from market_wide_current_shares_resolver import resolve_market_wide_shares
            summary = resolve_market_wide_shares(self.root, self.reference_session_date)
        except Exception as exc:  # noqa: BLE001 - reported, never fatal to the artifact set
            return {"status": "unresolved_error", "reason": f"{type(exc).__name__}: {exc}"}
        # The per-ticker map belongs in the resolver's own output, not in an operating report.
        return {key: value for key, value in summary.items() if key != "tickers"}

    def report(self, outcome: str, failure: GateFailure | None, rollback: dict[str, Any] | None) -> dict[str, Any]:
        payload = {
            "schema_version": "1.0.0",
            "command": "tools/operate_stocklookup.py",
            "mode": "execute" if self.execute else "dry_run",
            "publish": self.publish, "live": self.live,
            "runtime_root_name": self.root.name,
            "web_root": str(self.web_root) if self.web_root else None,
            "tickers": self.tickers,
            "include_canonical_financial_facts": self.include_canonical_financial_facts,
            "include_historical_decision_analysis": self.include_historical_decision_analysis,
            "include_portfolio_risk_analysis": self.include_portfolio_risk_analysis,
            "include_historical_scaleout": self.include_historical_scaleout,
            "include_qualified_research_brief": self.include_qualified_research_brief,
            "include_qualified_market_observations": self.include_qualified_market_observations,
            "include_dnse_foreign_flow": self.include_dnse_foreign_flow,
            "started_at": self.started_at, "ended_at": _now(),
            "outcome": outcome,
            "failed_gate": failure.gate if failure else None,
            "failure_detail": failure.detail if failure else None,
            "rollback": rollback,
            "market_wide_shares_coverage": self.market_wide_shares_coverage(),
            "artifact_sha256": self.artifact_hashes(),
            "steps": self.steps,
        }
        if self.execute:
            reports = self.root / "reports"
            reports.mkdir(parents=True, exist_ok=True)
            atomic_write_json(reports / "operate_stocklookup_latest.json", payload)
        return payload

    # ------------------------------------------------------------------ driver
    def run(self) -> int:
        failure: GateFailure | None = None
        rollback: dict[str, Any] | None = None
        try:
            self.preflight()
            session = self.preflight_database()
            self.preflight_locks()
            self.capture_rollback_point()
            if not self.execute:
                # Read-only stages still run in a dry run: they are what makes the dry run
                # worth running. The write stages below are only described.
                self.preflight_share_freshness(session)
                self.build_sidecar(session)
                if self.include_canonical_financial_facts:
                    self.verify_canonical_fact_store()
                self._record("dry_run_plan", "passed", detail=(
                    ("would refresh metadata via meta_sync.py, " if self.refresh_metadata else "")
                    + ("would rebuild the offline session inputs, " if self.prepare else "")
                    + "would rebuild the taxonomy sidecar, "
                    + ("verify canonical fact store, " if self.include_canonical_financial_facts else "")
                    + "export the bundle + manifest"
                    + (" with canonical financials enabled" if self.include_canonical_financial_facts else "")
                    + (" with the qualified historical research lane enabled"
                       if (self.include_historical_decision_analysis or self.include_qualified_research_brief)
                       else "")
                    + ", verify every declared artifact hash, run Consumer exact-session"
                    " validation, then "
                    + (f"publish live into {self.web_root}" if self.live
                       else f"run the release publisher dry-run against {self.web_root}"
                       if self.publish else "stop before publishing")))
                self.report("dry_run_ok", None, None)
                return 0

            # The daily chain, in dependency order. Metadata first: focus analysis and the
            # context packages are both derived from it, so refreshing it after them would
            # leave every downstream artifact describing the previous observation.
            if self.refresh_metadata:
                self.backup_database()
                self.refresh_metadata_stage()
                session = self.preflight_database()
            self.preflight_share_freshness(session)

            if self.prepare:
                self.backup_database()
                self.prepare_inputs()
                # Re-anchor: preparing inputs is what brings the new session into the
                # database, so the session resolved before it is the previous one. The
                # sidecar is bound to this value below, and binding it to a stale session
                # is exactly what the exact-session proof exists to catch.
                session = self.preflight_database()

            # Focus analysis and context packages must both describe `session` before
            # anything is built on top of them.
            self.preflight_derived_session_inputs(session)
            # Order matters: the sidecar must exist and be bound to this session BEFORE
            # the export, because the export binds the sidecar's bytes into the manifest's
            # required-artifact set and reads its taxonomy for the applicability gate.
            self.build_sidecar(session)
            if self.governed_official_evidence_root:
                source = self.governed_official_evidence_root / "data" / "official-evidence"
                if not (source / "financial_identity_citations.jsonl").is_file():
                    raise GateFailure("governed_official_evidence", "verified financial identity authority is missing")
                target = self.root / "data" / "official-evidence"
                target.mkdir(parents=True, exist_ok=True)
                for item in source.iterdir():
                    if item.is_file(): shutil.copy2(item, target / item.name)
                self._run("ingest_governed_canonical_facts", [sys.executable, str(ROOT / "tools" / "ingest_canonical_financial_facts.py"), "--runtime-root", str(self.root), "--execute", "--ticker", "POW"], ROOT)
            if self.include_canonical_financial_facts:
                self.verify_canonical_fact_store()
            self.export_bundle()
            self.verify_manifest_sources()
            self.verify_session_artifacts()
            self.validate_consumer()
            self.consumer_context_smoke()
            if self.publish:
                self.publish_release()
            self.post_publish_smoke()
        except GateFailure as exc:
            failure = exc
            self._record(exc.gate, "failed", detail=exc.detail)
            rollback = self.rollback()
            self.report("failed", failure, rollback)
            print(f"[operate] FAILED at {exc.gate}: {exc.detail}", file=sys.stderr)
            if rollback.get("performed"):
                print(f"[operate] rolled back to the previous artifact set ({rollback['from']})",
                      file=sys.stderr)
            return 1
        payload = self.report("success", None, None)
        print("[operate] SUCCESS — artifact sha256:")
        for name, digest in payload["artifact_sha256"].items():
            print(f"   {name}: {digest}")
        return 0


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--execute", action="store_true",
                        help="Actually rebuild and validate. Without it this is a strict dry run.")
    parser.add_argument("--prepare-inputs", action="store_true",
                        help="First rebuild the offline session-scoped inputs the export consumes"
                             " (technical signals, strategy report, focus analysis, Consumer context"
                             " packages). Never fetches prices/macro/news. Takes a verified,"
                             " restorable copy of vn_stock.db before running, because"
                             " stock_analyzer.py upserts its own watchlist_history table.")
    parser.add_argument("--refresh-metadata", action="store_true",
                        help=("Run meta_sync.py first, before any input preparation. This is "
                              "the only stage that writes vn_stock.db and reaches the network, "
                              "and the only thing that moves the provider share observation "
                              "onto the current session. Requires --execute."))
    parser.add_argument("--include-canonical-financial-facts", action="store_true",
                        help="Opt-in (P1F): attach market-wide canonical financial facts and readiness to Producer bundle.")
    parser.add_argument("--include-historical-decision-analysis", action="store_true",
                        help="Opt-in (Phase 4B): attach the qualified historical decision-support"
                             " analysis for whichever pilot tickers are in --tickers.")
    parser.add_argument("--include-portfolio-risk-analysis", action="store_true",
                        help="Opt-in (Phase 4C): attach the qualified risk/liquidity/portfolio-fit"
                             " gate. Pair with --include-historical-decision-analysis; without it"
                             " every ticker reports phase_4b_not_eligible.")
    parser.add_argument("--include-historical-scaleout", action="store_true",
                        help="Opt-in (Phase 5A): attach the deterministic bounded cohort"
                             " scale-out coverage matrix beyond the fixed pilot set.")
    parser.add_argument("--include-qualified-research-brief", action="store_true",
                        help="Opt-in (Phase 5B): attach the compact AI-facing qualified research"
                             " brief. Pair with --include-historical-decision-analysis and"
                             " --include-portfolio-risk-analysis for it to carry real content.")
    parser.add_argument("--include-qualified-market-observations", action="store_true",
                        help="Opt-in: attach provider-scoped descriptive/technical price and volume"
                             " observations for every ticker with a single-provider retained OHLCV"
                             " window (market_basis_capability_registry-gated). Independent of the"
                             " fundamental-evidence pilot set; always historical_only and"
                             " is_actionable=False.")
    parser.add_argument("--include-dnse-foreign-flow", action="store_true",
                        help="Opt-in: attach tickers[ticker].foreign_flow (qualified DNSE"
                             " foreign-investor VALUE per session, multi-session summaries, and an"
                             " exact-trading-session freshness verdict) for whichever tickers have"
                             " a retained observation store; every other ticker reports"
                             " status=\"missing\". Independent of every other lane; never affects"
                             " research eligibility. Off by default here -- the authoritative"
                             " production release profile (tools/release_orchestrator.py"
                             " --generate) is what turns this on for a real release.")
    parser.add_argument("--governed-official-evidence-root", type=Path)
    parser.add_argument("--research-changes-v2-baseline", type=Path)
    parser.add_argument("--publish", action="store_true",
                        help="Also run tools/publish_release.py (its own dry-run unless --live).")
    parser.add_argument("--web-root", default=None,
                        help="The Dashboard checkout that is actually served. Required with"
                             " --publish; the release is promoted into it, never into the"
                             " runtime root.")
    parser.add_argument("--verify-live-url", default=None,
                        help="[Not reachable via this CLI: --live is retired here, and this"
                             " only ever applied with --live.] Use tools/release_orchestrator.py"
                             " --verify-live-url for the same check on a real publish.")
    parser.add_argument("--live", action="store_true",
                        help="[RETIRED HERE] Live publish now happens only through "
                             "tools/release_orchestrator.py; passing this flag fails with a "
                             "migration message instead of publishing.")
    return parser.parse_args(argv)


def main(argv=None, runner=subprocess.run) -> int:
    args = parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    root = Path(args.runtime_root).expanduser().resolve()
    if not root.is_dir():
        print(f"[operate] runtime root does not exist: {root}", file=sys.stderr)
        return 2
    if args.live:
        # Single-authority rule: exactly one command may commit and push a release. That is
        # tools/release_orchestrator.py, which also holds the cross-release lock and the
        # Dashboard-repo HEAD/upstream/staged-index checks a live publish needs. This command
        # still builds and dry-run-validates the release (--execute, optionally --publish
        # without --live) exactly as before.
        print("[operate] --live is retired here. The single supported live-publish authority "
              "is tools/release_orchestrator.py — run `release_orchestrator.py trusted-ai "
              "--live` (add --generate to run this command's build+validate stage first). "
              "Drop --live to build and dry-run-validate the release with this command.",
              file=sys.stderr)
        return 2
    if args.refresh_metadata and not args.execute:
        # It writes vn_stock.db and reaches the network. A dry run that did either would not
        # be a dry run.
        print("[operate] --refresh-metadata requires --execute", file=sys.stderr)
        return 2
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        print("[operate] no tickers requested", file=sys.stderr)
        return 2

    if args.prepare_inputs and not args.execute:
        print("[operate] --prepare-inputs requires --execute", file=sys.stderr)
        return 2
    web_root: Path | None = None
    if args.publish:
        if not args.web_root:
            print("[operate] --publish requires --web-root: name the Dashboard checkout that"
                  " is actually served", file=sys.stderr)
            return 2
        web_root = Path(args.web_root).expanduser().resolve()
        if not web_root.is_dir():
            print(f"[operate] web root does not exist: {web_root}", file=sys.stderr)
            return 2
        if web_root == root:
            print("[operate] the web root must not be the runtime root: publishing into the"
                  " runtime root commits its unrelated drift to a branch nothing serves",
                  file=sys.stderr)
            return 2
    operator = Operator(root, tickers, execute=args.execute, publish=args.publish,
                        live=args.live, prepare=args.prepare_inputs, web_root=web_root,
                        verify_live_url=args.verify_live_url,
                        include_canonical_financial_facts=args.include_canonical_financial_facts,
                        include_historical_decision_analysis=args.include_historical_decision_analysis,
                        include_portfolio_risk_analysis=args.include_portfolio_risk_analysis,
                        include_historical_scaleout=args.include_historical_scaleout,
                        include_qualified_research_brief=args.include_qualified_research_brief,
                        include_qualified_market_observations=args.include_qualified_market_observations,
                        include_dnse_foreign_flow=args.include_dnse_foreign_flow,
                        governed_official_evidence_root=args.governed_official_evidence_root,
                        research_changes_v2_baseline=args.research_changes_v2_baseline,
                        refresh_metadata=args.refresh_metadata,
                        runner=runner)
    try:
        with PipelineLock(root / "locks" / "pipeline.lock"):
            return operator.run()
    except FileLockError as exc:
        print(f"[operate] CONCURRENCY LOCKED: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
