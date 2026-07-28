"""Bounded, subprocess-only orchestration pilot for the Phase 2E asset chain.

This module deliberately owns orchestration only.  Metadata export, ticker-context
construction, and AI bundle generation remain the authoritative existing CLIs.
The pilot stages immutable input copies below a caller-selected temporary root and
refuses a production runtime root.  It is not a scheduler and has no promotion path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

DEFAULT_TICKERS = ("POW", "SSI", "HPG", "EVF", "PAN", "PNJ", "QNS", "PDR", "GEX")
RUNTIME_INPUTS = (
    "vn_stock.db", "screen_snapshot_live.csv", "screen_snapshot.csv", "ta_signals.csv",
    "analysis_latest.json", "financial_snapshot.csv", "financial_snapshot.parquet",
    "Focus_Analysis.md", "market_breadth.csv", "macro_snapshot.csv", "news_latest.csv",
    "financial_mapping.py", "news_ticker_mapping.py",
)


class PilotError(RuntimeError):
    """A preflight, asset, or contract failure that must stop downstream assets."""


@dataclass(frozen=True)
class AssetStatus:
    name: str
    status: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    dependencies: tuple[str, ...]
    command: tuple[str, ...] = ()
    detail: str | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {"path": str(path), "exists": True, "sha256": sha256_file(path),
            "size": stat.st_size, "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()}


def require_isolated_root(path: Path, production_runtime: Path) -> Path:
    candidate = path.resolve()
    production = production_runtime.resolve()
    if candidate == production or production in candidate.parents or candidate in production.parents:
        raise PilotError(f"pilot runtime root must be isolated from production runtime: {candidate}")
    return candidate


def copy_runtime_inputs(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    missing = [name for name in RUNTIME_INPUTS if not (source / name).exists()]
    if missing:
        raise PilotError(f"required runtime inputs missing: {', '.join(missing)}")
    for name in RUNTIME_INPUTS:
        shutil.copy2(source / name, destination / name)
    shutil.copytree(source / "config", destination / "config")


def copy_consumer_for_isolation(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise PilotError(f"Consumer source unavailable: {source}")
    shutil.copytree(
        source, destination,
        ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", "exports", "reports"),
    )
    (destination / "exports" / "context_packages").mkdir(parents=True, exist_ok=True)


def run_command(command: Sequence[str], *, cwd: Path, env: dict[str, str], log_path: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", check=False)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f"$ {' '.join(command)}\n\n[stdout]\n{completed.stdout}\n[stderr]\n{completed.stderr}\n",
        encoding="utf-8",
    )
    if completed.returncode:
        raise PilotError(f"command failed ({completed.returncode}); see {log_path}")


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotError(f"invalid JSON output {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PilotError(f"JSON output must be an object: {path}")
    return value


def load_snapshot_groups(snapshot: Path, consumer_root: Path) -> dict:
    """Use the Consumer's schema-hash-gated reader; never parse snapshot JSONL here."""
    builders = str(consumer_root / "builders")
    if builders not in sys.path:
        sys.path.insert(0, builders)
    from metadata_registry_reader import SnapshotError, read_snapshot
    try:
        return read_snapshot(snapshot)
    except SnapshotError as exc:
        raise PilotError(f"registry snapshot failed existing reader/schema validation: {exc}") from exc


def validate_snapshot_ticker_groups(groups: dict, tickers: Sequence[str]) -> None:
    """Require exactly the requested ticker groups after reader validates ticker/field identities."""
    expected = set(tickers)
    actual = set(groups)
    missing, unexpected = sorted(expected - actual), sorted(actual - expected)
    empty = sorted(ticker for ticker in expected & actual if not groups.get(ticker))
    if missing or unexpected or empty:
        raise PilotError(
            f"registry snapshot ticker groups mismatch: missing={missing}, unexpected={unexpected}, empty={empty}"
        )

def compare_contexts(database_dir: Path, registry_dir: Path, snapshot: Path, tickers: Sequence[str], consumer_root: Path) -> dict:
    builders = str(consumer_root / "builders")
    if builders not in sys.path:
        sys.path.insert(0, builders)
    from metadata_registry_shadow_compare import compare_context_semantic_invariance

    reports: dict[str, dict] = {}
    for ticker in tickers:
        db = _load_json(database_dir / f"{ticker}_context.json")
        registry = _load_json(registry_dir / f"{ticker}_context.json")
        report = compare_context_semantic_invariance(db, registry, snapshot)
        # The comparison function includes full non-provenance context equality; this
        # explicit check makes metadata identity a first-class pilot gate.
        report["metadata_equal"] = db.get("metadata") == registry.get("metadata")
        reports[ticker] = report
    passed = all(r["is_semantically_invariant"] and r["metadata_equal"] for r in reports.values())
    return {"passed": passed, "tickers_compared": len(reports), "per_ticker": reports}


def verify_bundle_contract(runtime_root: Path, tickers: Sequence[str]) -> dict:
    manifest = _load_json(runtime_root / "bundle_manifest.json")
    bundle = _load_json(runtime_root / "analysis_bundle.json")
    if tuple(manifest.get("tickers", ())) != tuple(tickers):
        raise PilotError("bundle manifest ticker set/order differs from requested canary")
    if tuple(bundle.get("tickers_requested", ())) != tuple(tickers):
        raise PilotError("analysis bundle ticker set/order differs from requested canary")
    if set(bundle.get("tickers", {})) != set(tickers):
        raise PilotError("analysis bundle ticker payload is incomplete")
    freshness = manifest.get("freshness")
    if not isinstance(freshness, dict) or freshness.get("blocked") or freshness.get("status") != "fresh":
        raise PilotError("bundle freshness/check gate did not pass")
    required = ("focus_extract.json", "analysis_bundle.json", "bundle_manifest.json")
    if any(not (runtime_root / name).is_file() for name in required):
        raise PilotError("AI artifact set is incomplete")
    return {"schema_versions": {"bundle": bundle.get("schema_version"), "manifest": manifest.get("schema_version")},
            "reference_session_date": bundle.get("reference_session_date"), "freshness_status": freshness.get("status")}


def _asset(name: str, status: str, inputs: Sequence[Path], outputs: Sequence[Path], dependencies: Sequence[str],
           command: Sequence[str] = (), detail: str | None = None) -> AssetStatus:
    return AssetStatus(name, status, tuple(map(str, inputs)), tuple(map(str, outputs)), tuple(dependencies), tuple(command), detail)


def run_pilot(*, workspace: Path, runtime_root: Path | None, evidence_dir: Path, frozen_at: str,
              tickers: Sequence[str] = DEFAULT_TICKERS) -> dict:
    """Run each authoritative command once in a disposable, isolated workspace."""
    workspace = workspace.resolve()
    producer = workspace / "stock-core-private"
    consumer = workspace / "ai-core-private"
    production_runtime = workspace / "dashboard-runtime"
    if not producer.is_dir() or not consumer.is_dir() or not production_runtime.is_dir():
        raise PilotError("workspace must contain stock-core-private, ai-core-private, and dashboard-runtime")
    root = require_isolated_root(runtime_root or Path(tempfile.mkdtemp(prefix="phase2e-orchestration-")), production_runtime)
    if root.exists() and any(root.iterdir()):
        raise PilotError(f"isolated runtime root must be new and empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    if evidence_dir.exists():
        allowed_preflight = {"01_preflight.json"}
        unexpected = {path.name for path in evidence_dir.iterdir()} - allowed_preflight
        if unexpected:
            raise PilotError(f"evidence directory must be new or preflight-only: {evidence_dir}")
    else:
        evidence_dir.mkdir(parents=True, exist_ok=False)
    staged_runtime = root / "dashboard-runtime"
    staged_consumer = root / "ai-runtime"
    copy_runtime_inputs(production_runtime, staged_runtime)
    copy_consumer_for_isolation(consumer, staged_consumer)
    logs = root / "logs"
    snapshot_dir = root / "registry_snapshots"
    context_root = staged_consumer / "exports" / "context_packages"
    direct_context_dir = context_root / "database"
    registry_context_dir = context_root / "registry"
    env = os.environ.copy()
    env.update({
        "STOCK_LOOKUP_RUNTIME_ROOT": str(staged_runtime),
        "STOCK_LOOKUP_AI_RUNTIME_ROOT": str(staged_consumer),
        "STOCK_LOOKUP_CONTEXT_PACKAGES_DIR": str(registry_context_dir),
        "PYTHONUTF8": "1",
    })
    before = {name: fingerprint(production_runtime / name) for name in RUNTIME_INPUTS}
    assets: list[AssetStatus] = []
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_cmd = (sys.executable, str(producer / "metadata_registry_export.py"), "--db", str(staged_runtime / "vn_stock.db"),
                    "--tickers", *tickers, "--registry-snapshot", str(snapshot_dir))
    snapshot: Path | None = None
    try:
        run_command(snapshot_cmd, cwd=producer, env=env, log_path=logs / "01_metadata_snapshot.log")
        snapshots = sorted(snapshot_dir.glob("vnstock_metadata_snapshot_*.jsonl"))
        if len(snapshots) != 1:
            raise PilotError("metadata snapshot asset must produce exactly one immutable JSONL file")
        snapshot = snapshots[0]
        groups = load_snapshot_groups(snapshot, staged_consumer)
        validate_snapshot_ticker_groups(groups, tickers)
        assets.append(_asset("metadata_snapshot", "passed", [staged_runtime / "vn_stock.db"], [snapshot], (), snapshot_cmd))
    except PilotError as exc:
        assets.append(_asset("metadata_snapshot", "failed", [staged_runtime / "vn_stock.db"], [snapshot_dir], (), snapshot_cmd, str(exc)))
        assets.extend((_asset("ticker_context_packages", "skipped", [snapshot_dir], [registry_context_dir], ("metadata_snapshot",), detail="upstream failure"),
                       _asset("ai_artifact_set", "skipped", [registry_context_dir], [staged_runtime / "bundle_manifest.json"], ("ticker_context_packages",), detail="upstream failure")))
        return _write_report(evidence_dir, root, production_runtime, frozen_at, tickers, assets, before, {"passed": False, "reason": str(exc)})

    db_cmd = (sys.executable, str(staged_consumer / "builders" / "build_ticker_context.py"), "--tickers", ",".join(tickers),
              "--no-dry-run", "--output", str(direct_context_dir), "--frozen-clock", frozen_at)
    try:
        run_command(db_cmd, cwd=staged_consumer, env=env, log_path=logs / "02_direct_cli_database_context.log")
    except PilotError as exc:
        assets.append(_asset("ticker_context_packages", "failed", [snapshot, staged_runtime / "vn_stock.db"], [registry_context_dir], ("metadata_snapshot",), db_cmd, f"direct CLI prerequisite failed: {exc}"))
        assets.append(_asset("ai_artifact_set", "skipped", [registry_context_dir], [staged_runtime / "bundle_manifest.json"], ("ticker_context_packages",), detail="upstream failure"))
        return _write_report(evidence_dir, root, production_runtime, frozen_at, tickers, assets, before, {"passed": False, "reason": str(exc)})
    registry_cmd = (sys.executable, str(staged_consumer / "builders" / "build_ticker_context.py"), "--tickers", ",".join(tickers),
                    "--no-dry-run", "--output", str(registry_context_dir), "--frozen-clock", frozen_at,
                    "--metadata-source", "registry_snapshot", "--metadata-registry-snapshot", str(snapshot), "--registry-shadow-gate")
    try:
        run_command(registry_cmd, cwd=staged_consumer, env=env, log_path=logs / "03_registry_context.log")
        comparison = compare_contexts(direct_context_dir, registry_context_dir, snapshot, tickers, staged_consumer)
        if not comparison["passed"]:
            raise PilotError("registry context semantic parity/no-fallback gate failed")
        assets.append(_asset("ticker_context_packages", "passed", [snapshot, staged_runtime / "vn_stock.db"], [registry_context_dir], ("metadata_snapshot",), registry_cmd))
    except PilotError as exc:
        assets.append(_asset("ticker_context_packages", "failed", [snapshot], [registry_context_dir], ("metadata_snapshot",), registry_cmd, str(exc)))
        assets.append(_asset("ai_artifact_set", "skipped", [registry_context_dir], [staged_runtime / "bundle_manifest.json"], ("ticker_context_packages",), detail="upstream failure"))
        return _write_report(evidence_dir, root, production_runtime, frozen_at, tickers, assets, before, {"passed": False, "reason": str(exc)})

    bundle_cmd = (sys.executable, str(producer / "export_ai_bundle.py"), "--tickers", ",".join(tickers), "--evaluation-at", frozen_at)
    try:
        run_command(bundle_cmd, cwd=producer, env=env, log_path=logs / "04_ai_artifact_set.log")
        bundle_check = verify_bundle_contract(staged_runtime, tickers)
        assets.append(_asset("ai_artifact_set", "passed", [registry_context_dir], [staged_runtime / "focus_extract.json", staged_runtime / "analysis_bundle.json", staged_runtime / "bundle_manifest.json"], ("ticker_context_packages",), bundle_cmd))
    except PilotError as exc:
        assets.append(_asset("ai_artifact_set", "failed", [registry_context_dir], [staged_runtime / "bundle_manifest.json"], ("ticker_context_packages",), bundle_cmd, str(exc)))
        return _write_report(evidence_dir, root, production_runtime, frozen_at, tickers, assets, before, {"passed": False, "reason": str(exc)})
    return _write_report(evidence_dir, root, production_runtime, frozen_at, tickers, assets, before, {"passed": True, "comparison": comparison, "bundle": bundle_check})


def _write_report(evidence_dir: Path, root: Path, production_runtime: Path, frozen_at: str, tickers: Sequence[str], assets: Sequence[AssetStatus], before: dict, checks: dict) -> dict:
    # Source production fingerprints are checked only after all temporary outputs exist.
    after = {name: fingerprint(production_runtime / name) for name in RUNTIME_INPUTS}
    report = {"run_id": evidence_dir.name, "frozen_evaluation_time": frozen_at, "tickers": list(tickers),
              "isolated_runtime_root": str(root), "assets": [asdict(asset) for asset in assets], "checks": checks,
              "production_runtime_fingerprints_before": before,
              "production_runtime_fingerprints_after": after,
              "production_runtime_unchanged": before == after}
    (evidence_dir / "PHASE_2E_REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the isolated Phase 2E orchestration pilot.")
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--runtime-root", type=Path, help="new empty temporary root; default is a system temp directory")
    parser.add_argument("--evidence-dir", type=Path, required=True, help="new explicit evidence directory")
    parser.add_argument("--frozen-at", required=True, help="ISO-8601 UTC evaluation timestamp")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS), help="exact comma-separated bounded ticker set")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    tickers = tuple(item.strip().upper() for item in args.tickers.split(",") if item.strip())
    if len(tickers) != 9 or len(set(tickers)) != 9:
        raise SystemExit("exactly nine distinct tickers are required")
    try:
        report = run_pilot(workspace=args.workspace, runtime_root=args.runtime_root, evidence_dir=args.evidence_dir,
                           frozen_at=args.frozen_at, tickers=tickers)
    except PilotError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": "pass" if report["checks"].get("passed") else "fail", "evidence": str(args.evidence_dir)}))
    return 0 if report["checks"].get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
