"""Canonical Dashboard Release Publisher.

Binds the exact Producer run identity to the authoritative Dashboard release,
materializes runtime & web artifacts, generates canonical build_info metadata,
and validates session coherence across all required Dashboard files.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PRODUCER_ROOT = Path(__file__).resolve().parent
if str(PRODUCER_ROOT) not in sys.path:
    sys.path.insert(0, str(PRODUCER_ROOT))

from atomic_io import atomic_copy_file, atomic_write_file, atomic_write_json
from canonical_dashboard_runtime_release import (
    CanonicalRuntimeReleaseError,
    materialize_canonical_runtime_release,
)
import release_session_contract


class DashboardReleaseError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def publish_dashboard_release(
    session: str,
    operation_dir: Path | str,
    runtime_root: Path | str,
    web_root: Path | str,
    *,
    replay_local: bool = True,
    push: bool = False,
) -> dict[str, Any]:
    """Publish a canonical Dashboard release bound to the exact Producer run identity."""
    operation_dir = Path(operation_dir)
    runtime_root = Path(runtime_root)
    web_root = Path(web_root)

    if not web_root.is_dir():
        raise DashboardReleaseError(f"WEB_ROOT_NOT_DIRECTORY:{web_root}")

    # 1. Materialize canonical runtime release in runtime_root if needed
    runtime_manifest = runtime_root / "bundle_manifest.json"
    runtime_snapshot = runtime_root / "screen_snapshot.csv"
    if not (runtime_manifest.is_file() and runtime_snapshot.is_file()):
        try:
            runtime_result = materialize_canonical_runtime_release(PRODUCER_ROOT, runtime_root, session)
        except CanonicalRuntimeReleaseError as exc:
            raise DashboardReleaseError(f"CANONICAL_RUNTIME_MATERIALIZATION_FAILED:{exc}") from exc

    # 2. Synchronize required artifacts from runtime_root to web_root
    web_data_dir = web_root / "data"
    web_data_dir.mkdir(parents=True, exist_ok=True)

    # Core runtime artifacts
    for name in ("screen_snapshot.csv", "screen_snapshot_live.csv", "market_breadth.csv", "analysis_latest.json", "bundle_manifest.json"):
        src = runtime_root / name
        if src.is_file():
            dst = web_root / name
            atomic_copy_file(src, dst)

    # 3. Synchronize / generate data/ companions
    # Candle signals, sector heatmap, candlestick patterns, macro
    signal_files = (
        ("data/candle_signals.json", ("scan_date",)),
        ("data/candle_signals.js", None),
        ("data/sector_heatmap.json", ("scan_date",)),
        ("data/sector_heatmap.js", None),
        ("data/candlestick_patterns.json", ("scan_date",)),
        ("data/candlestick_patterns.js", None),
        ("data/macro_snapshot.json", None),
        ("data/macro_snapshot.js", None),
        ("data/current_decision_cockpit.json", None),
    )
    for name, date_accessor in signal_files:
        src = runtime_root / name
        if not src.is_file():
            alt = operation_dir / name
            if alt.is_file():
                src = alt
            else:
                alt2 = operation_dir.parent / name
                if alt2.is_file():
                    src = alt2

        dst = web_root / name
        if src.is_file():
            # If JSON has scan_date, verify it matches session
            if date_accessor and src.suffix == ".json":
                try:
                    payload = json.loads(src.read_text(encoding="utf-8"))
                    scan_d = payload.get("scan_date")
                    if scan_d and scan_d != session:
                        if dst.is_file():
                            dst.unlink()
                        continue
                except Exception:
                    pass
            dst.parent.mkdir(parents=True, exist_ok=True)
            atomic_copy_file(src, dst)
        else:
            # If destination already has an old/stale file from another session, remove it
            if dst.is_file() and date_accessor and dst.suffix == ".json":
                try:
                    payload = json.loads(dst.read_text(encoding="utf-8"))
                    scan_d = payload.get("scan_date")
                    if scan_d and scan_d != session:
                        dst.unlink()
                except Exception:
                    pass

    # Try generating HTML report companion if retained canonical handoff is available
    try:
        from dashboard_session_companions import (
            apply_session_companions,
            compute_session_companions,
            producer_git_head,
            producer_git_subject,
        )
        plan = compute_session_companions(
            PRODUCER_ROOT,
            session,
            producer_commit=producer_git_head(PRODUCER_ROOT),
            producer_commit_summary=producer_git_subject(PRODUCER_ROOT),
            build_id=f"build_{session.replace('-', '')}",
        )
        if not plan.omitted:
            apply_session_companions(web_root, plan)
    except Exception:
        pass

    # 4. Generate data/screener_data.js (file:// fallback for screener)
    screen_csv_path = web_root / "screen_snapshot.csv"
    breadth_csv_path = web_root / "market_breadth.csv"
    if screen_csv_path.is_file():
        screen_rows = _read_csv_rows(screen_csv_path)
        breadth_rows = _read_csv_rows(breadth_csv_path) if breadth_csv_path.is_file() else []
        screener_js_content = (
            f"window.SCREENER_DATA_META = {{ market_session: {json.dumps(session)} }};\n"
            f"window.SCREEN_ROWS = {json.dumps(screen_rows, ensure_ascii=False)};\n"
            f"window.BREADTH_ROWS = {json.dumps(breadth_rows, ensure_ascii=False)};\n"
        )
        atomic_write_file(web_root / "data" / "screener_data.js", screener_js_content)

    # 5. Compute artifact hashes and summary counts
    files_meta: dict[str, dict[str, Any]] = {}
    for rel in (
        "screen_snapshot.csv",
        "market_breadth.csv",
        "analysis_latest.json",
        "data/screener_data.js",
        "data/candle_signals.json",
        "data/sector_heatmap.json",
        "data/candlestick_patterns.json",
        "data/macro_snapshot.json",
    ):
        p = web_root / rel
        if p.is_file():
            stat = p.stat()
            files_meta[rel] = {
                "sha256": _sha256(p),
                "size_bytes": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }

    # Summary counts
    active_rows = [r for r in screen_rows if str(r.get("exchange") or "").strip().upper() != "DELISTED"] if screen_csv_path.is_file() else []
    up_count = sum(1 for r in active_rows if str(r.get("structure") or "").strip().lower() == "up")
    rs80_count = sum(1 for r in active_rows if float(r.get("rs_rating") or 0) >= 80)
    total_surveyed = len(active_rows)

    now_iso = datetime.now(timezone.utc).isoformat()
    producer_run_id = operation_dir.name if hasattr(operation_dir, "name") else str(operation_dir)

    manifest_bytes = json.dumps({
        "session": session,
        "producer_run_identity": producer_run_id,
        "files": files_meta,
    }, sort_keys=True).encode("utf-8")
    release_digest = hashlib.sha256(manifest_bytes).hexdigest()
    release_id = f"dashboard_release:{release_digest}"
    build_id = release_digest[:10]

    build_info_payload = {
        "schema_version": "dashboard_build_info/v1",
        "market_session": session,
        "producer_run_identity": producer_run_id,
        "dashboard_release_identity": release_id,
        "build_id": build_id,
        "generated_at": now_iso,
        "published_at": now_iso,
        "release_status": "READY",
        "domains": {
            "screening": "current",
            "breadth": "current",
            "analysis": "current",
            "signals": "current",
            "macro": "current",
        },
        "files": files_meta,
        "hero_summary": {
            "market_session": session,
            "total_surveyed": total_surveyed,
            "up_count": up_count,
            "rs80_count": rs80_count,
        },
    }

    # Write data/build_info.json & data/build_info.js
    atomic_write_json(web_root / "data" / "build_info.json", build_info_payload)
    build_info_js = f"window.BUILD_INFO = {json.dumps(build_info_payload, ensure_ascii=False, indent=2)};\n"
    atomic_write_file(web_root / "data" / "build_info.js", build_info_js)

    # 6. Validate session coherence across web_root
    required_session_files = ["screen_snapshot.csv", "market_breadth.csv", "analysis_latest.json"]
    # Check if signals exist in web_root
    for opt in ("data/candle_signals.json", "data/sector_heatmap.json", "data/candlestick_patterns.json"):
        if (web_root / opt).is_file():
            required_session_files.append(opt)

    report = release_session_contract.resolve_release_session(web_root, required_session_files)
    if not report.ready:
        mismatches = report.mismatch_lines()
        raise DashboardReleaseError(
            f"MIXED_SESSION_DASHBOARD_RELEASE: expected {session}, found issues:\n" + "\n".join(mismatches)
        )

    return {
        "status": "DASHBOARD_RELEASE_READY",
        "market_session": session,
        "producer_run_identity": producer_run_id,
        "dashboard_release_identity": release_id,
        "build_id": build_id,
        "web_root": str(web_root),
        "validated_artifacts": [r.name for r in report.results if r.status == "ok"],
    }
