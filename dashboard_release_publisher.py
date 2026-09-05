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
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PRODUCER_ROOT = Path(__file__).resolve().parent
if str(PRODUCER_ROOT) not in sys.path:
    sys.path.insert(0, str(PRODUCER_ROOT))

from canonical_dashboard_runtime_release import (
    CanonicalRuntimeReleaseError,
    materialize_canonical_runtime_release,
)
from dashboard_session_companions import companion_relpaths
from release_checkout_identity import (
    CANONICAL_BRANCH,
    assert_web_checkout_identity,
)
import release_session_contract


class DashboardReleaseError(RuntimeError):
    pass


# This is deliberately a literal boundary rather than a scan of Dashboard source.
# The Daily command is allowed to publish only these generated current-release
# artifacts, plus the two exact-session companions derived from the same Producer
# run.  Source, workflow and presentation files are committed separately.
DASHBOARD_RELEASE_ALLOWLIST = (
    "screen_snapshot.csv",
    "screen_snapshot_live.csv",
    "market_breadth.csv",
    "analysis_latest.json",
    "bundle_manifest.json",
    "analysis_bundle.json",
    "focus_extract.json",
    "statement_taxonomy_sidecar.json",
    "data/candle_signals.json",
    "data/candle_signals.js",
    "data/sector_heatmap.json",
    "data/sector_heatmap.js",
    "data/candlestick_patterns.json",
    "data/candlestick_patterns.js",
    "data/macro_snapshot.json",
    "data/macro_snapshot.js",
    "data/current_decision_cockpit.json",
    "data/screener_data.js",
    "data/build_info.json",
    "data/build_info.js",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_bytes(target: Path, content: bytes) -> None:
    """Write one Dashboard artifact without emitting Producer observability files there."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(dir=target.parent, prefix=f".tmp-{target.name}-", suffix=".tmp")
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def _atomic_copy(source: Path, target: Path) -> None:
    _atomic_write_bytes(target, source.read_bytes())


def _atomic_write_text(target: Path, content: str) -> None:
    _atomic_write_bytes(target, content.encode("utf-8"))


def _git(web_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=web_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise DashboardReleaseError(
            f"DASHBOARD_GIT_FAILED:{' '.join(args)}:{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def _dashboard_preflight(web_root: Path) -> None:
    """Refuse a live publish unless the canonical Dashboard checkout starts clean."""
    top = Path(_git(web_root, "rev-parse", "--show-toplevel"))
    branch = _git(web_root, "branch", "--show-current")
    origin = _git(web_root, "remote", "get-url", "origin")
    _git(web_root, "fetch", "origin", CANONICAL_BRANCH)
    relation = _git(web_root, "rev-list", "--left-right", "--count", f"HEAD...origin/{CANONICAL_BRANCH}")
    ahead, behind = (int(value) for value in relation.split())
    if behind:
        raise DashboardReleaseError("DASHBOARD_REMOTE_AHEAD_OR_DIVERGED")
    try:
        assert_web_checkout_identity(
            web_root,
            origin_url=origin,
            branch=branch,
            live=True,
            git_toplevel=top,
        )
    except Exception as exc:
        raise DashboardReleaseError(f"DASHBOARD_CHECKOUT_IDENTITY_FAILED:{exc}") from exc
    if _git(web_root, "status", "--porcelain", "--untracked-files=all"):
        raise DashboardReleaseError("DASHBOARD_CHECKOUT_NOT_CLEAN")


def _changed_paths(web_root: Path) -> list[str]:
    changed = set(filter(None, _git(web_root, "diff", "--name-only").splitlines()))
    changed.update(filter(None, _git(web_root, "diff", "--cached", "--name-only").splitlines()))
    changed.update(filter(None, _git(web_root, "ls-files", "--others", "--exclude-standard").splitlines()))
    return sorted(changed)


def _publish_generated_release(
    web_root: Path,
    *,
    session: str,
    release_id: str,
    companion_paths: tuple[str, ...],
) -> dict[str, Any]:
    """Commit and push exactly one verified generated Dashboard release."""
    allowed = set(DASHBOARD_RELEASE_ALLOWLIST) | set(companion_paths)
    changed = _changed_paths(web_root)
    escaped = sorted(set(changed) - allowed)
    if escaped:
        raise DashboardReleaseError(
            "DASHBOARD_RELEASE_ALLOWLIST_VIOLATION:" + ",".join(escaped)
        )
    if not changed:
        return {"status": "NO_OP_ALREADY_PUBLISHED", "commit": _git(web_root, "rev-parse", "HEAD")}

    _git(web_root, "add", "--", *changed)
    staged = sorted(filter(None, _git(web_root, "diff", "--cached", "--name-only").splitlines()))
    if set(staged) != set(changed) or set(staged) - allowed:
        raise DashboardReleaseError("DASHBOARD_RELEASE_STAGING_VIOLATION")
    byte_mismatches = []
    for rel in staged:
        target = web_root / rel
        if not target.is_file():
            # Removing an obsolete generated sidecar is a valid, governed release
            # transition.  The allowlist and staged-path checks above still bind it.
            continue
        blob = subprocess.run(
            ["git", "cat-file", "blob", f":{rel}"], cwd=web_root,
            capture_output=True, check=False,
        )
        if blob.returncode or hashlib.sha256(blob.stdout).hexdigest() != _sha256(target):
            byte_mismatches.append(rel)
    if byte_mismatches:
        raise DashboardReleaseError(
            "DASHBOARD_RELEASE_GIT_BYTE_MISMATCH:" + ",".join(byte_mismatches)
        )
    _git(web_root, "commit", "-m", f"data(daily): publish dashboard {session}")
    commit = _git(web_root, "rev-parse", "HEAD")
    remaining = _changed_paths(web_root)
    if remaining:
        raise DashboardReleaseError(
            "DASHBOARD_RELEASE_POST_COMMIT_DIRTY:" + ",".join(remaining)
        )
    _git(web_root, "push", "origin", f"HEAD:{CANONICAL_BRANCH}")
    remote = _git(web_root, "ls-remote", "origin", f"refs/heads/{CANONICAL_BRANCH}").split()
    if not remote or remote[0] != commit:
        raise DashboardReleaseError("DASHBOARD_PUSH_VERIFICATION_FAILED")
    return {
        "status": "PUBLISHED_READY",
        "commit": commit,
        "release_identity": release_id,
        "staged": staged,
    }


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def _current_producer_run_identity(session: str, operation_dir: Path) -> str:
    pointer_path = PRODUCER_ROOT / "operations-review" / "daily-producer-runs-v1" / "LATEST_COMPLETED_RUN.json"
    pointer = _load_json_object(pointer_path, "LATEST_COMPLETED_RUN")
    if pointer.get("session") != session or not isinstance(pointer.get("run_identity"), str):
        raise DashboardReleaseError("CURRENT_DAILY_PRODUCER_RUN_UNRESOLVED")
    relative = pointer.get("relative_directory")
    if not isinstance(relative, str):
        raise DashboardReleaseError("CURRENT_DAILY_PRODUCER_POINTER_MALFORMED")
    manifest = _load_json_object(
        PRODUCER_ROOT / "operations-review" / "daily-producer-runs-v1" / relative / "run_manifest.json",
        "CURRENT_DAILY_PRODUCER_MANIFEST",
    )
    expected_operation = ((manifest.get("daily_session_operation") or {}).get("directory"))
    try:
        actual_operation = str(operation_dir.resolve().relative_to(PRODUCER_ROOT.resolve())).replace("\\", "/")
    except ValueError as exc:
        raise DashboardReleaseError("CURRENT_DAILY_OPERATION_OUTSIDE_PRODUCER") from exc
    if expected_operation != actual_operation:
        raise DashboardReleaseError("CURRENT_DAILY_OPERATION_LINEAGE_MISMATCH")
    return pointer["run_identity"]


def _load_json_object(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardReleaseError(f"{code}_UNREADABLE") from exc
    if not isinstance(value, dict):
        raise DashboardReleaseError(f"{code}_NOT_OBJECT")
    return value


_SIGNAL_COMPONENTS = (
    ("candle_signals", "data/candle_signals.json", "data/candle_signals.js", "CANDLE_SIGNALS"),
    ("sector_heatmap", "data/sector_heatmap.json", "data/sector_heatmap.js", "SECTOR_HEATMAP"),
    ("candlestick_patterns", "data/candlestick_patterns.json", "data/candlestick_patterns.js", "CANDLESTICK_PATTERNS"),
)


def _remove_if_present(path: Path) -> None:
    if path.is_file():
        path.unlink()


def _sidecar_candidates(runtime_root: Path, operation_dir: Path, relpath: str) -> list[Path]:
    """Return explicit lineage locations only; never use a latest-file search."""
    candidates = [runtime_root / relpath, operation_dir / relpath, operation_dir.parent / relpath]
    unique: list[Path] = []
    for candidate in candidates:
        if candidate.is_file() and candidate not in unique:
            unique.append(candidate)
    return unique


def _signal_component_state(runtime_root: Path, operation_dir: Path, relpath: str, session: str) -> tuple[Path | None, dict[str, Any]]:
    """Select one exact signal payload or retain only its stale metadata for disclosure."""
    exact: list[tuple[Path, dict[str, Any]]] = []
    observed: dict[str, Any] = {"status": "UNAVAILABLE_FOR_CURRENT_SESSION", "source_session": None,
                                "generated_at": None, "reason_codes": ["EXACT_SESSION_SIGNAL_ARTIFACT_UNAVAILABLE"]}
    for candidate in _sidecar_candidates(runtime_root, operation_dir, relpath):
        try:
            payload = _load_json_object(candidate, "SIGNAL_SIDECAR")
        except DashboardReleaseError:
            continue
        source_session = payload.get("scan_date")
        generated_at = payload.get("generated_at")
        if observed["source_session"] is None:
            observed.update({"source_session": source_session, "generated_at": generated_at})
        if source_session == session:
            exact.append((candidate, payload))
    if len(exact) > 1:
        hashes = {_sha256(path) for path, _payload in exact}
        if len(hashes) != 1:
            raise DashboardReleaseError(f"AMBIGUOUS_EXACT_SIGNAL_SIDECAR:{relpath}")
    if exact:
        path, payload = exact[0]
        return path, {"status": "CURRENT", "source_session": session,
                      "generated_at": payload.get("generated_at"), "freshness": "EXACT_SESSION",
                      "reason_codes": []}
    if observed["source_session"]:
        observed["status"] = "STALE"
        observed["reason_codes"] = ["SIGNAL_SOURCE_SESSION_MISMATCH"]
    return None, observed


def _write_signal_pair(web_root: Path, json_relpath: str, js_relpath: str, global_name: str, source: Path | None) -> None:
    """Publish JSON and file:// JS as one derived pair; a stale JS cannot survive alone."""
    json_target, js_target = web_root / json_relpath, web_root / js_relpath
    if source is None:
        _remove_if_present(json_target)
        _remove_if_present(js_target)
        return
    payload = _load_json_object(source, "SIGNAL_SIDECAR")
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    _atomic_write_text(json_target, encoded + "\n")
    _atomic_write_text(js_target, f"window.{global_name} = {encoded};\n")


def _macro_domain_state(source: Path | None, session: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Evaluate the existing per-series cadence contract at the Dashboard release session."""
    unavailable = {"status": "UNAVAILABLE", "source_session": None, "data_as_of": None,
                   "generated_at": None, "freshness": "UNAVAILABLE",
                   "reason_codes": ["MACRO_SNAPSHOT_UNAVAILABLE"]}
    if source is None:
        return unavailable, None
    try:
        snapshot = _load_json_object(source, "MACRO_SNAPSHOT")
        as_of = date.fromisoformat(session)
    except (DashboardReleaseError, ValueError):
        return {**unavailable, "reason_codes": ["MACRO_SNAPSHOT_UNREADABLE"]}, None
    stale = 0
    available = 0
    for item in snapshot.get("indicators") or []:
        if not isinstance(item, dict):
            continue
        freshness = item.get("freshness") if isinstance(item.get("freshness"), dict) else {}
        threshold = freshness.get("stale_after_days")
        period = item.get("period")
        try:
            age_days = max(0, (as_of - date.fromisoformat(str(period))).days)
        except ValueError:
            age_days = None
        status = "unknown"
        if isinstance(threshold, int) and age_days is not None:
            status = "stale" if age_days > threshold else "current"
        item["freshness"] = {"status": status, "age_days": age_days, "stale_after_days": threshold}
        if item.get("status") == "available":
            available += 1
        if status == "stale":
            stale += 1
    quality = snapshot.get("quality") if isinstance(snapshot.get("quality"), dict) else {}
    quality["stale_count"] = stale
    quality["is_partial"] = bool(quality.get("missing_count") or stale)
    snapshot["quality"] = quality
    snapshot["dashboard_freshness_evaluated_at"] = session
    if not available:
        status = "UNAVAILABLE"
        reasons = ["MACRO_NO_AVAILABLE_SERIES"]
    elif stale:
        status = "PARTIAL"
        reasons = ["MACRO_CADENCE_STALE_SERIES_PRESENT"]
    else:
        status = "CURRENT"
        reasons = []
    return {"status": status, "source_session": None, "data_as_of": snapshot.get("data_as_of"),
            "generated_at": snapshot.get("generated_at"), "freshness": "CADENCE_AWARE",
            "reason_codes": reasons, "stale_series_count": stale}, snapshot


def publish_dashboard_release(
    session: str,
    operation_dir: Path | str,
    runtime_root: Path | str,
    web_root: Path | str,
    *,
    replay_local: bool = True,
    push: bool = False,
    local_only: bool = False,
) -> dict[str, Any]:
    """Publish a canonical Dashboard release bound to the exact Producer run identity.

    ``local_only=True`` is a structural guarantee, not a caller convention: every write this
    function makes below is redirected to a throwaway staging directory rather than the real
    ``web_root`` Git working tree, by reassigning the local ``web_root`` name once, here, before
    any write occurs. No later line needs to know local-only mode exists. The one piece of
    pre-existing state this function reads before it would otherwise overwrite it
    (``data/build_info.json``, for the repeated-exact-release check) is seeded into the staging
    copy so that check still behaves realistically; nothing else is copied, so this stays cheap
    even for a large checkout. ``local_only`` always takes precedence over ``push`` -- there is
    nothing to push from a directory that was never the real repository, and a caller never
    needs to remember to also pass ``push=False``; there is exactly one way to ask for zero Git
    mutation, not two flags that must agree.
    """
    operation_dir = Path(operation_dir)
    runtime_root = Path(runtime_root)
    web_root = Path(web_root)

    if not web_root.is_dir():
        raise DashboardReleaseError(f"WEB_ROOT_NOT_DIRECTORY:{web_root}")
    if local_only:
        push = False

    real_web_root = web_root
    local_only_staging: Path | None = None
    if local_only:
        local_only_staging = Path(tempfile.mkdtemp(prefix="stocklookup_dashboard_local_only_"))
        existing_build_info_src = web_root / "data" / "build_info.json"
        if existing_build_info_src.is_file():
            staging_data_dir = local_only_staging / "data"
            staging_data_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(existing_build_info_src, staging_data_dir / "build_info.json")
        web_root = local_only_staging

    if push:
        _dashboard_preflight(web_root)

    previous_build_info: dict[str, Any] | None = None
    existing_build_info = web_root / "data" / "build_info.json"
    if existing_build_info.is_file():
        try:
            parsed = json.loads(existing_build_info.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                previous_build_info = parsed
        except (OSError, json.JSONDecodeError):
            pass

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
    for name in (
        "screen_snapshot.csv",
        "screen_snapshot_live.csv",
        "market_breadth.csv",
        "analysis_latest.json",
        "bundle_manifest.json",
        "analysis_bundle.json",
        "focus_extract.json",
        "statement_taxonomy_sidecar.json",
    ):
        src = runtime_root / name
        if src.is_file():
            dst = web_root / name
            _atomic_copy(src, dst)

    # 3. Synchronize presentation sidecars only from their own governed contracts.
    # A JSON/JS pair is atomic: stale file:// fallbacks may never survive a rejected JSON.
    signal_components: dict[str, dict[str, Any]] = {}
    for component, json_name, js_name, global_name in _SIGNAL_COMPONENTS:
        source, state = _signal_component_state(runtime_root, operation_dir, json_name, session)
        _write_signal_pair(web_root, json_name, js_name, global_name, source)
        signal_components[component] = state
    signal_status = "CURRENT" if all(item["status"] == "CURRENT" for item in signal_components.values()) else (
        "STALE" if any(item["status"] == "STALE" for item in signal_components.values()) else "UNAVAILABLE_FOR_CURRENT_SESSION"
    )
    domains: dict[str, dict[str, Any]] = {
        "screening": {"status": "CURRENT", "source_session": session, "freshness": "EXACT_SESSION", "reason_codes": []},
        "breadth": {"status": "CURRENT", "source_session": session, "freshness": "EXACT_SESSION", "reason_codes": []},
        "analysis": {"status": "CURRENT", "source_session": session, "freshness": "EXACT_SESSION", "reason_codes": []},
        "signals": {"status": signal_status, "source_session": session if signal_status == "CURRENT" else None,
                    "freshness": "EXACT_SESSION", "reason_codes": ["SIGNAL_COMPONENT_NOT_EXACT_SESSION"] if signal_status != "CURRENT" else [],
                    "components": signal_components},
    }

    macro_source = next(iter(_sidecar_candidates(runtime_root, operation_dir, "data/macro_snapshot.json")), None)
    macro_state, macro_snapshot = _macro_domain_state(macro_source, session)
    domains["macro"] = macro_state
    macro_json, macro_js = web_root / "data/macro_snapshot.json", web_root / "data/macro_snapshot.js"
    if macro_snapshot is None:
        _remove_if_present(macro_json)
        _remove_if_present(macro_js)
    else:
        macro_encoded = json.dumps(macro_snapshot, ensure_ascii=False, indent=2, allow_nan=False)
        _atomic_write_text(macro_json, macro_encoded + "\n")
        _atomic_write_text(macro_js, f"window.MACRO_SNAPSHOT = {macro_encoded};\n")

    # The cockpit comes only from this exact Daily Research Session Operation.
    cockpit_target = web_root / "data/current_decision_cockpit.json"
    cockpit_source = operation_dir / "current_decision_cockpit_projection.json"
    if cockpit_source.is_file():
        cockpit = _load_json_object(cockpit_source, "CURRENT_COCKPIT")
        if cockpit.get("session") == session:
            _atomic_copy(cockpit_source, cockpit_target)
            domains["cockpit"] = {"status": "CURRENT", "source_session": session,
                                  "freshness": "EXACT_SESSION", "generated_at": cockpit.get("generated_at"),
                                  "reason_codes": []}
        else:
            _remove_if_present(cockpit_target)
            domains["cockpit"] = {"status": "UNAVAILABLE", "source_session": cockpit.get("session"),
                                  "freshness": "EXACT_SESSION", "reason_codes": ["COCKPIT_SESSION_MISMATCH"]}
    else:
        _remove_if_present(cockpit_target)
        domains["cockpit"] = {"status": "UNAVAILABLE", "source_session": None,
                              "freshness": "EXACT_SESSION", "reason_codes": ["EXACT_COCKPIT_PROJECTION_UNAVAILABLE"]}

    # Try generating HTML report companion if retained canonical handoff is available
    companion_paths = companion_relpaths(session)
    if not replay_local:
        from dashboard_session_companions import (
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
            producer_run_identity=_current_producer_run_identity(session, operation_dir),
        )
        if plan.omitted:
            raise DashboardReleaseError(f"CANONICAL_SESSION_COMPANIONS_OMITTED:{plan.omit_reason}")
        _atomic_write_text(web_root / plan.manifest_relpath, plan.manifest_text)
        _atomic_write_text(web_root / plan.report_relpath, plan.report_html)

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
        _atomic_write_text(web_root / "data" / "screener_data.js", screener_js_content)

    # 5. Compute artifact hashes and summary counts
    files_meta: dict[str, dict[str, Any]] = {}
    for rel in (*DASHBOARD_RELEASE_ALLOWLIST, *companion_paths):
        if rel.startswith("data/build_info"):
            continue
        p = web_root / rel
        if p.is_file():
            files_meta[rel] = {
                "sha256": _sha256(p),
                "size_bytes": p.stat().st_size,
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
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
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
        "domains": domains,
        "files": files_meta,
        "hero_summary": {
            "market_session": session,
            "total_surveyed": total_surveyed,
            "up_count": up_count,
            "rs80_count": rs80_count,
        },
    }

    # A repeated exact release must not generate new timestamps or new bytes.  If
    # the release identity already exists but its governed file hashes differ,
    # refuse instead of silently replacing a conflicting release.
    previous_id = (previous_build_info or {}).get("dashboard_release_identity")
    if previous_id == release_id:
        previous_files = (previous_build_info or {}).get("files")
        previous_hashes = {
            rel: value.get("sha256")
            for rel, value in previous_files.items()
            if isinstance(value, dict)
        } if isinstance(previous_files, dict) else {}
        current_hashes = {rel: value["sha256"] for rel, value in files_meta.items()}
        if previous_hashes != current_hashes:
            raise DashboardReleaseError("FAIL_CLOSED_DASHBOARD_RELEASE_IDENTITY_CONFLICT")
    else:
        _atomic_write_text(
            web_root / "data" / "build_info.json",
            json.dumps(build_info_payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        )
        build_info_js = f"window.BUILD_INFO = {json.dumps(build_info_payload, ensure_ascii=False, indent=2)};\n"
        _atomic_write_text(web_root / "data" / "build_info.js", build_info_js)

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

    result = {
        "status": "DASHBOARD_RELEASE_READY",
        "market_session": session,
        "producer_run_identity": producer_run_id,
        "dashboard_release_identity": release_id,
        "build_id": build_id,
        "web_root": str(web_root),
        "validated_artifacts": [r.name for r in report.results if r.status == "ok"],
    }
    if push:
        result.update(_publish_generated_release(
            web_root,
            session=session,
            release_id=release_id,
            companion_paths=companion_paths,
        ))
    if local_only_staging is not None:
        result["status"] = "LOCAL_VALIDATED_NO_GIT_MUTATION"
        result["web_root"] = str(real_web_root)
        result["local_only_staging_root"] = str(local_only_staging)
        shutil.rmtree(local_only_staging, ignore_errors=True)
    return result
