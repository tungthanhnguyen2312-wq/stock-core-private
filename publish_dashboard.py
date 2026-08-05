"""Build and publish the public Stock Look Up dashboard safely.

Default mode (no ``--live``) is a strict, read-only dry-run: it validates
inputs, computes the exact plan (which artifacts would be copied, the build
id that would be generated, which HTML pages would get new asset-version
tokens, and the git whitelist), and only *prints* that plan. It does not
copy any artifact, does not write or update the build manifest, does not
touch any HTML/CSS/JS file, does not write a log file, and never invokes a
mutating git command (add/commit/push/fetch/pull).

Only ``--live`` may write files and fetch/pull/stage/commit/push. The
publisher is the single source of truth for copying artifacts, rebuilding
the file:// fallback, writing build_info and deriving the exact git
whitelist.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atomic_io import atomic_copy_file, atomic_write_file, validate_json_file
import release_session_contract
import trusted_subset_contract
try:
    from observability_events import (
        EventOutcome,
        EventStage,
        build_observability_event,
        emit_observability_event,
    )
except ImportError:
    from stock_core_private.observability_events import (
        EventOutcome,
        EventStage,
        build_observability_event,
        emit_observability_event,
    )

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VN_TZ = timezone(timedelta(hours=7))
SCRIPT_ROOT = Path(__file__).resolve().parent

def get_default_backend_root() -> Path:
    if os.environ.get("STOCK_LOOKUP_BACKEND_DIR"):
        return Path(os.environ["STOCK_LOOKUP_BACKEND_DIR"]).expanduser().resolve()
    if os.environ.get("STOCK_LOOKUP_RUNTIME_ROOT"):
        return Path(os.environ["STOCK_LOOKUP_RUNTIME_ROOT"]).expanduser().resolve()
    for candidate_dir in (
        SCRIPT_ROOT / ".." / "dashboard-runtime",
        SCRIPT_ROOT / ".." / ".." / "dashboard-runtime",
    ):
        cand = candidate_dir.resolve()
        if cand.is_dir() and (cand / "screen_snapshot.csv").is_file():
            return cand
    return SCRIPT_ROOT

BACKEND_ROOT = get_default_backend_root()
WEB_ROOT = Path(os.environ.get("STOCK_LOOKUP_WEB_DIR", SCRIPT_ROOT)).expanduser().resolve()

# LIVE_MODE gates every filesystem/log write in this module. main() sets it
# from --live before doing anything else. Tests may also set it directly.
LIVE_MODE = False
# Fixed once per process so every log() call in one run lands in the same
# file; the *directory* is still resolved from the current WEB_ROOT at each
# call (not cached), so monkeypatching WEB_ROOT in tests is respected and a
# dry-run never has a reason to touch this at all (see log() below).
_RUN_TIMESTAMP = f"{datetime.now(VN_TZ):%Y%m%d-%H%M%S}"

COPY_ARTIFACTS = (
    "screen_snapshot.csv", "market_breadth.csv",
    "ai_report_latest.md", "ai_report_latest.json",
    "data/macro_snapshot.json", "data/macro_snapshot.js",
    "data/candlestick_patterns.json", "data/candlestick_patterns.js",
    "data/candle_signals.json", "data/candle_signals.js",
    "data/sector_heatmap.json", "data/sector_heatmap.js",
)
SAFE_WEB_ARTIFACTS = set(COPY_ARTIFACTS) | {
    "data/screener_data.js", "data/build_info.json", "data/build_info.js",
}
NEVER_PUBLISH = {
    "vn_stock.db", "config.json", "publish_log.txt", "tickers.txt",
    "sync_and_publish.bat", "sync_and_push.bat",
}
REQUIRED_SNAPSHOT_COLUMNS = {"ticker", "exchange", "date"}
CANONICAL_EXCHANGES = {"HSX", "HNX", "UPCOM", "DELISTED"}
EXCHANGE_ALIASES = {"HOSE": "HSX", "HCM": "HSX", "UPCOM": "UPCOM"}
ASSET_VERSION_ATTR_RE = re.compile(r'(?P<prefix>\b(?:src|href)=["\'])(?P<url>[^"\']+)(?P<quote>["\'])', re.I)

# Names whose current-truth bytes live in BACKEND_ROOT for this run (the artifacts
# copy_public_artifacts() mirrors into WEB_ROOT). Reading them through source_root()
# instead of a hardcoded WEB_ROOT is what makes the dry-run preview and a live write
# agree on content/build_id, and what lets session validation see the fresh generation
# instead of the previous publish's already-copied — possibly stale — file.
BACKEND_SOURCED = {"screen_snapshot.csv", "market_breadth.csv",
                   "ai_report_latest.md", "ai_report_latest.json"}
# screen_snapshot_live.csv is not copied by this publisher (see COPY_ARTIFACTS) but is
# generated alongside screen_snapshot.csv by the same vn_indicators.py run, so its
# session is cross-checked here whenever it is present.
REQUIRED_SESSION_ARTIFACTS = ("screen_snapshot.csv", "market_breadth.csv")
OPTIONAL_SESSION_ARTIFACTS = ("screen_snapshot_live.csv",)


def source_root(relative: str) -> Path:
    """Where `relative`'s current-truth bytes live for this run.

    BACKEND_ROOT when it is a name copy_public_artifacts() sources from there AND
    BACKEND_ROOT actually has the file; WEB_ROOT otherwise (frontend source, destination
    -only build outputs, or an optional backend artifact never generated there — e.g. a
    single-root invocation where BACKEND_ROOT == WEB_ROOT already covers this trivially).
    """
    if relative in BACKEND_SOURCED and (BACKEND_ROOT / relative).is_file():
        return BACKEND_ROOT
    return WEB_ROOT


def log(message: str) -> None:
    line = f"[{datetime.now(VN_TZ).isoformat(timespec='seconds')}] {message}"
    print(line)
    if not LIVE_MODE:
        return
    log_dir = WEB_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / f"publish-{_RUN_TIMESTAMP}.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def fail(message: str) -> int:
    log(f"[LỖI] {message}")
    return 1


def git(*args: str, timeout: int = 180) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=WEB_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    # Git có thể ghi warning line-ending vào stderr ngay cả khi thành công; dữ liệu
    # máy đọc (SHA, branch, conflict list) chỉ lấy stdout để không báo conflict giả.
    output = (proc.stdout if proc.returncode == 0 else proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, output


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    atomic_write_file(path, content, encoding="utf-8", newline="\n")
    return True


def normalize_exchange(value: object) -> str:
    raw = str(value or "").strip().upper()
    return EXCHANGE_ALIASES.get(raw, raw)


# ---------------------------------------------------------------------------
# Copy artifacts backend -> web: plan (read-only) + apply (writes, LIVE only)
# ---------------------------------------------------------------------------

def plan_copy_artifacts() -> list[str]:
    """Return the relative paths that a live run would copy. Never touches disk."""
    if BACKEND_ROOT == WEB_ROOT:
        return []
    planned: list[str] = []
    for relative in COPY_ARTIFACTS:
        source, target = BACKEND_ROOT / relative, WEB_ROOT / relative
        if not source.exists():
            continue
        if target.exists() and sha256(source) == sha256(target):
            continue
        planned.append(relative)
    return planned


def copy_public_artifacts() -> list[str]:
    """Apply: actually copy the artifacts computed by plan_copy_artifacts(). LIVE only."""
    if BACKEND_ROOT == WEB_ROOT:
        log("Nguồn backend và web trùng nhau; bỏ qua self-copy.")
        return []
    copied: list[str] = []
    for relative in COPY_ARTIFACTS:
        source, target = BACKEND_ROOT / relative, WEB_ROOT / relative
        if not source.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and sha256(source) == sha256(target):
            continue
        validator = validate_json_file if relative.endswith(".json") else None
        atomic_copy_file(source, target, validator=validator)
        copied.append(relative)
    log(f"Đã copy {len(copied)} artifact từ backend: {', '.join(copied) or '(không đổi)'}")
    return copied


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists() or path.stat().st_size == 0:
        raise ValueError(f"thiếu/rỗng: {path.name}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    if not rows:
        raise ValueError(f"không có dòng dữ liệu: {path.name}")
    return rows, fields


def validate_release_session() -> release_session_contract.ReleaseSessionReport:
    """Resolve + validate the one authoritative release session before trusting anything
    already sitting in WEB_ROOT. Runs against BACKEND_ROOT (the fresh generation root;
    identical to WEB_ROOT in a single-root invocation) so a leftover stale WEB_ROOT copy
    from a previous publish can never mask itself as current — see
    docs/dashboard_release_session_contract.md."""
    root = BACKEND_ROOT
    required = list(REQUIRED_SESSION_ARTIFACTS)
    required += [name for name in OPTIONAL_SESSION_ARTIFACTS if (root / name).is_file()]
    return release_session_contract.resolve_release_session(root, required)


def validate_snapshot() -> tuple[list[dict[str, str]], list[dict[str, str]], str]:
    rows, fields = read_csv_rows(BACKEND_ROOT / "screen_snapshot.csv")
    missing = REQUIRED_SNAPSHOT_COLUMNS - set(fields)
    if missing:
        raise ValueError(f"screen_snapshot.csv thiếu cột: {', '.join(sorted(missing))}")
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        row["ticker"] = ticker
        row["exchange"] = normalize_exchange(row.get("exchange"))
        if row["exchange"] and row["exchange"] not in CANONICAL_EXCHANGES:
            raise ValueError(f"sàn không hợp lệ {row['exchange']} tại {ticker}")
        if ticker in seen:
            duplicates.add(ticker)
        seen.add(ticker)
    if duplicates:
        raise ValueError(f"snapshot trùng ticker: {', '.join(sorted(duplicates)[:20])}")
    hpg = [row for row in rows if row["ticker"] == "HPG"]
    if len(hpg) != 1 or hpg[0]["exchange"] != "HSX":
        got = [row.get("exchange") for row in hpg]
        raise ValueError(f"sentinel HPG phải có đúng 1 dòng HSX/HOSE, nhận {got}")
    active_dates = [str(row.get("date") or "") for row in rows
                    if row["exchange"] != "DELISTED" and row.get("date")]
    if not active_dates:
        raise ValueError("không xác định được phiên mới nhất của mã đang niêm yết")
    market_session = max(active_dates)
    breadth, _ = read_csv_rows(BACKEND_ROOT / "market_breadth.csv")
    log(f"Snapshot hợp lệ: {len(rows)} mã, {len(breadth)} dòng breadth, phiên {market_session}, HPG=HSX.")
    return rows, breadth, market_session


def typed_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    converted: list[dict[str, object]] = []
    for row in rows:
        out: dict[str, object] = {}
        for key, value in row.items():
            text = "" if value is None else str(value).strip()
            if text == "":
                out[key] = None
            elif text.lower() in {"true", "false"}:
                out[key] = text.lower() == "true"
            else:
                try:
                    out[key] = float(text) if any(ch in text for ch in ".eE") else int(text)
                except ValueError:
                    out[key] = text
        converted.append(out)
    return converted


def current_head() -> str:
    ok, head = git("rev-parse", "HEAD")
    if not ok:
        raise ValueError(f"không đọc được HEAD: {head}")
    return head.strip()


def build_signature(market_session: str, head: str) -> str:
    digest = hashlib.sha256(f"{market_session}|{head}".encode())
    for relative in (
        "screen_snapshot.csv", "market_breadth.csv", "app.js", "style.css",
        "assets/js/value-format.js", "assets/js/company-panel.js",
        "assets/css/tailwind.generated.css",
    ):
        path = source_root(relative) / relative
        if not path.exists():
            raise ValueError(f"thiếu file build bắt buộc: {relative}")
        digest.update(relative.encode())
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Build manifest + screener_data.js fallback: compute (read-only) + write (LIVE only)
# ---------------------------------------------------------------------------

def screener_fallback_content(rows: list[dict[str, str]], breadth: list[dict[str, str]],
                              market_session: str, generated_at: str) -> str:
    """Pure: the exact text that would become data/screener_data.js. No I/O."""
    meta = {"schema_version": 1, "generated_at": generated_at, "market_session": market_session}
    return (
        "window.SCREENER_DATA_META = " + json.dumps(meta, ensure_ascii=False, separators=(",", ":")) + ";\n"
        "window.SCREEN_ROWS = " + json.dumps(typed_rows(rows), ensure_ascii=False, separators=(",", ":")) + ";\n"
        "window.BREADTH_ROWS = " + json.dumps(typed_rows(breadth), ensure_ascii=False, separators=(",", ":")) + ";\n"
    )


def file_entry(relative: str) -> dict[str, object]:
    path = source_root(relative) / relative
    stat = path.stat()
    return {
        "sha256": sha256(path), "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime, VN_TZ).isoformat(timespec="seconds"),
    }


def compute_manifest(rows: list[dict[str, str]], breadth: list[dict[str, str]],
                     market_session: str, head: str) -> tuple[dict[str, object], str]:
    """Pure: compute the manifest dict + the screener_data.js content it references.

    Reads existing on-disk files (screen_snapshot.csv, market_breadth.csv, the
    build-signature inputs, and the previous data/build_info.json if present)
    but never writes anything. Safe to call in dry-run.
    """
    signature = build_signature(market_session, head)
    build_id = f"{market_session}-{head[:7]}-{signature[:10]}"
    existing_path = WEB_ROOT / "data/build_info.json"
    existing: dict[str, object] = {}
    if existing_path.exists():
        try:
            existing = json.loads(existing_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    generated_at = (existing.get("generated_at") if existing.get("build_id") == build_id else None)
    generated_at = str(generated_at or datetime.now(VN_TZ).isoformat(timespec="seconds"))
    screener_js_content = screener_fallback_content(rows, breadth, market_session, generated_at)
    tracked_files = ["screen_snapshot.csv", "market_breadth.csv"]
    tracked_files += [name for name in ("ai_report_latest.md", "ai_report_latest.json")
                      if (source_root(name) / name).exists()]
    files: dict[str, object] = {name: file_entry(name) for name in tracked_files}
    files["data/screener_data.js"] = {
        "sha256": content_sha256(screener_js_content),
        "size": len(screener_js_content.encode("utf-8")),
        # Chưa ghi ra đĩa ở giai đoạn compute (dry-run có thể dừng ở đây) nên
        # chưa có mtime thật; live apply sẽ có mtime thật sau khi write_build_manifest() ghi file.
        "mtime": None,
    }
    bundle_path = source_root("analysis_bundle.json") / "analysis_bundle.json"

    basis_contract: dict[str, object] = {
        "price_basis": "unknown",
        "price_basis_verified": False,
        "is_actionable": False,
        "volume_basis": "unknown",
        "volume_basis_verified": False,
        "adjustment_source": None,
        "effective_date": None,
        "limitations": ["Price basis is unverified or unknown; corporate actions may affect price and return calculations."],
    }
    if bundle_path.exists():
        try:
            b_data = json.loads(bundle_path.read_text(encoding="utf-8"))
            if isinstance(b_data, dict):
                prov = b_data.get("price_basis_provenance")
                if isinstance(prov, dict):
                    basis_contract.update({
                        "price_basis": prov.get("price_basis", b_data.get("price_basis", "unknown")),
                        "price_basis_verified": prov.get("price_basis_verified", b_data.get("price_basis_verified", False)),
                        "is_actionable": prov.get("is_actionable", False),
                        "volume_basis": prov.get("volume_basis", "unknown"),
                        "volume_basis_verified": prov.get("volume_basis_verified", False) is True,
                        "adjustment_source": prov.get("adjustment_source"),
                        "effective_date": prov.get("effective_date"),
                        "limitations": prov.get("limitations", basis_contract["limitations"]),
                    })
                elif "price_basis" in b_data:
                    basis_contract["price_basis"] = str(b_data["price_basis"])
                    basis_contract["price_basis_verified"] = b_data.get("price_basis_verified") is True
        except (OSError, json.JSONDecodeError):
            pass

    manifest: dict[str, object] = {
        "schema_version": 1,
        "build_id": build_id,
        "generated_at": generated_at,
        "market_session": market_session,
        "git_commit": head,
        "row_counts": {"screen_snapshot": len(rows), "market_breadth": len(breadth)},
        "price_basis_contract": basis_contract,
        "files": files,
    }
    return manifest, screener_js_content


def write_build_manifest(manifest: dict[str, object], screener_js_content: str) -> dict[str, object]:
    """Apply: write data/screener_data.js, data/build_info.json, data/build_info.js. LIVE only.

    Takes the already-computed manifest/content from compute_manifest() so
    preview and live always agree on build_id/content — this function only
    performs the filesystem writes and re-derives the real (post-write) file
    entries for what actually landed on disk.
    """
    changed = write_if_changed(WEB_ROOT / "data/screener_data.js", screener_js_content)
    log(f"Fallback screener_data.js: {'đã tái tạo' if changed else 'không đổi'}.")
    manifest = dict(manifest)
    files = dict(manifest["files"])  # type: ignore[arg-type]
    files["data/screener_data.js"] = file_entry("data/screener_data.js")
    manifest["files"] = files
    existing_path = WEB_ROOT / "data/build_info.json"
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    write_if_changed(existing_path, payload)
    write_if_changed(
        WEB_ROOT / "data/build_info.js",
        "window.STOCK_LOOKUP_BUILD_INFO = "
        + json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
        + ";\nwindow.BUILD_INFO = window.STOCK_LOOKUP_BUILD_INFO;\n",
    )
    # Parse lại chính artifact vừa tạo; hỏng JSON phải dừng trước git.
    json.loads(existing_path.read_text(encoding="utf-8"))
    log(f"Build manifest: {manifest['build_id']} · {manifest['generated_at']}")
    try:
        bc = manifest.get("price_basis_contract", {})
        ev = build_observability_event(
            EventStage.PUBLISH_DASHBOARD,
            EventOutcome.SUCCESS,
            artifact_filename="build_info.json",
            sha256=hashlib.sha256(existing_path.read_bytes()).hexdigest(),
            size_bytes=existing_path.stat().st_size,
            price_basis=bc.get("price_basis") if isinstance(bc, dict) else None,
            volume_basis=bc.get("volume_basis") if isinstance(bc, dict) else None,
            is_actionable=bc.get("is_actionable") if isinstance(bc, dict) else None,
            is_live_write=True,
            target_path=existing_path,
        )
        emit_observability_event(ev, WEB_ROOT / "logs" / "observability_events.jsonl")
    except Exception:
        pass
    return manifest


# ---------------------------------------------------------------------------
# Asset cache-busting in HTML: plan (read-only) + apply (writes, LIVE only)
# ---------------------------------------------------------------------------

def _versioned_html(original: str, build_id: str) -> str:
    """Pure text transform — no I/O. Shared by plan_asset_versions() and update_asset_versions()
    so preview and live can never disagree about which pages/tags would change."""
    def replace(match: re.Match[str]) -> str:
        url = match.group("url")
        if url.startswith(("http://", "https://", "//", "data:", "#", "/")):
            return match.group(0)
        bare = url.split("?", 1)[0].split("#", 1)[0]
        if not bare.lower().endswith((".js", ".css")):
            return match.group(0)
        return f"{match.group('prefix')}{bare}?v={build_id}{match.group('quote')}"
    return ASSET_VERSION_ATTR_RE.sub(replace, original)


def plan_asset_versions(build_id: str) -> list[str]:
    """Return the HTML page names that a live run would rewrite. Never touches disk."""
    changed: list[str] = []
    for page in sorted(WEB_ROOT.glob("*.html")):
        original = page.read_text(encoding="utf-8")
        if _versioned_html(original, build_id) != original:
            changed.append(page.name)
    return changed


def update_asset_versions(build_id: str) -> list[str]:
    """Apply: actually rewrite the HTML pages computed by plan_asset_versions(). LIVE only."""
    changed: list[str] = []
    for page in sorted(WEB_ROOT.glob("*.html")):
        original = page.read_text(encoding="utf-8")
        updated = _versioned_html(original, build_id)
        if updated != original:
            page.write_text(updated, encoding="utf-8", newline="\n")
            changed.append(page.name)
    log(f"Asset cache token {build_id}: cập nhật {len(changed)} trang.")
    return changed


def validate_json_artifacts() -> None:
    for relative in sorted(SAFE_WEB_ARTIFACTS):
        if not relative.endswith(".json"):
            continue
        path = WEB_ROOT / relative
        if not path.exists() or path.stat().st_size == 0:
            raise ValueError(f"artifact JSON thiếu/rỗng: {relative}")
        json.loads(path.read_text(encoding="utf-8-sig"))


def build_whitelist() -> list[str]:
    pages = sorted(path.name for path in WEB_ROOT.glob("*.html"))
    paths = set(pages) | SAFE_WEB_ARTIFACTS
    attr_re = re.compile(r'(?:src|href)=["\']([^"\']+)["\']', re.I)
    data_re = re.compile(r'["\']([\w./-]+\.(?:csv|json|md))["\']', re.I)
    for relative in pages:
        text = (WEB_ROOT / relative).read_text(encoding="utf-8")
        paths.update(attr_re.findall(text))
        paths.update(data_re.findall(text))
    for script in list(WEB_ROOT.glob("*.js")) + list((WEB_ROOT / "assets/js").glob("*.js")):
        paths.update(data_re.findall(script.read_text(encoding="utf-8")))
    cleaned: set[str] = set()
    for raw in paths:
        relative = raw.replace("\\", "/").split("?", 1)[0].split("#", 1)[0]
        if relative.startswith(("http://", "https://", "//", "/", "data:")) or ".." in relative.split("/"):
            continue
        if relative in NEVER_PUBLISH:
            continue
        cleaned.add(relative)
    missing = sorted(relative for relative in cleaned if not (WEB_ROOT / relative).is_file())
    if missing:
        raise ValueError(f"whitelist tham chiếu file thiếu: {', '.join(missing)}")
    leaked = sorted(set(cleaned) & NEVER_PUBLISH)
    if leaked:
        raise ValueError(f"denylist lọt vào whitelist: {', '.join(leaked)}")
    return sorted(cleaned)


def run_release_smoke_tests() -> int:
    """Run tests/release-smoke.test.js against WEB_ROOT — the exact post-copy worktree —
    via `node --test`. LIVE only, and only after copy_public_artifacts()/write_build_manifest()
    have run: a dry-run has not copied anything yet, so there is no post-copy worktree to
    test. This is the authoritative content check trusted_subset_contract cannot perform
    (rendered HTML, per-ticker Altman/statement-taxonomy sections) — it must pass before
    any git add/commit/push. See tests/release-smoke.test.js's own docstring: it runs
    against the committed analysis_bundle.json/bundle_manifest.json, not a fixture."""
    test_path = WEB_ROOT / "tests" / "release-smoke.test.js"
    if not test_path.is_file():
        log(f"[LỖI] không thấy {test_path} — release-smoke bắt buộc trước khi commit.")
        return 1
    proc = subprocess.run(["node", "--test", str(test_path)], cwd=WEB_ROOT,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    for stream in (proc.stdout, proc.stderr):
        if stream:
            log(stream.rstrip())
    return proc.returncode


def git_preflight() -> tuple[str, str, str]:
    ok, root = git("rev-parse", "--show-toplevel")
    if not ok or Path(root).resolve() != WEB_ROOT:
        raise ValueError(f"WEB_ROOT không phải git root: {root}")
    ok, branch = git("branch", "--show-current")
    if not ok or not branch.strip():
        raise ValueError("không xác định được branch hiện tại")
    ok, remote = git("remote", "get-url", "origin")
    if not ok or not remote.strip():
        raise ValueError("thiếu remote origin")
    ok, conflicts = git("diff", "--name-only", "--diff-filter=U")
    if not ok or conflicts:
        raise ValueError(f"worktree có conflict: {conflicts}")
    ok, head = git("rev-parse", "HEAD")
    if not ok:
        raise ValueError(head)
    ok, when = git("show", "-s", "--format=%cI", "HEAD")
    log(f"Git root={root} · branch={branch} · origin={remote}")
    log(f"Local HEAD={head} · commit_time={when if ok else '?'}")
    return branch.strip(), remote.strip(), head.strip()


def sync_remote_before_live(branch: str) -> None:
    ok, output = git("fetch", "origin", branch)
    if not ok:
        raise ValueError(f"git fetch thất bại: {output}")
    ok, remote_head = git("rev-parse", f"origin/{branch}")
    if not ok:
        raise ValueError(f"không đọc được origin/{branch}: {remote_head}")
    ok, relation = git("rev-list", "--left-right", "--count", f"HEAD...origin/{branch}")
    if not ok:
        raise ValueError(relation)
    ahead, behind = [int(part) for part in relation.split()]
    log(f"Remote origin/{branch}={remote_head} · local ahead={ahead}, behind={behind}")
    if ahead and behind:
        raise ValueError("local và remote đã diverge; không tự merge")
    if behind:
        ok, output = git("pull", "--ff-only", "origin", branch)
        if not ok:
            raise ValueError(f"git pull --ff-only thất bại: {output}")


def publish_live(whitelist: list[str], branch: str) -> int:
    ok, staged_before = git("diff", "--cached", "--name-only")
    if not ok:
        return fail(staged_before)
    unrelated = sorted(set(staged_before.splitlines()) - set(whitelist))
    if unrelated:
        return fail(f"đang có file staged ngoài whitelist: {', '.join(unrelated)}")
    ok, output = git("add", "--", *whitelist)
    if not ok:
        return fail(f"git add whitelist thất bại: {output}")
    ok, staged = git("diff", "--cached", "--name-only")
    staged_files = [line for line in staged.splitlines() if line]
    if not ok or set(staged_files) - set(whitelist):
        return fail(f"stage vượt whitelist: {staged}")
    if not staged_files:
        log("Không có thay đổi; không commit/push.")
        return 0
    log(f"Staged {len(staged_files)} file: {', '.join(staged_files)}")
    message = f"Auto update dashboard data - {datetime.now(VN_TZ):%Y-%m-%d %H:%M} (giờ VN)"
    ok, output = git("commit", "-m", message)
    if not ok:
        return fail(f"git commit thất bại: {output}")
    ok, local_head = git("rev-parse", "HEAD")
    if not ok:
        return fail(local_head)
    log(f"Commit thành công: {local_head} · {message}")
    ok, output = git("push", "origin", f"HEAD:{branch}")
    if not ok:
        return fail(f"git push thất bại: {output}")
    ok, remote_line = git("ls-remote", "origin", f"refs/heads/{branch}")
    remote_head = remote_line.split()[0] if ok and remote_line else ""
    if not ok or remote_head != local_head.strip():
        return fail(f"remote SHA không khớp sau push: local={local_head}, remote={remote_head or remote_line}")
    log(f"Push và verify thành công: origin/{branch}={remote_head}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build/publish dashboard with atomic writes, asset versioning, basis contracts, and Phase 2A pipeline integration.")
    parser.add_argument("--live", action="store_true", help="cho phép ghi file, fetch/pull/add/commit/push thật")
    parser.add_argument("--isolated-test-fixture", action="store_true", help="cho phép BACKEND_ROOT trùng WEB_ROOT trong môi trường test isolated")
    args = parser.parse_args()

    global LIVE_MODE
    LIVE_MODE = args.live
    mode = "LIVE" if args.live else "DRY-RUN (read-only)"
    log(f"=== publish_dashboard {mode} ===")
    log(f"Backend={BACKEND_ROOT} · Web={WEB_ROOT}")

    if BACKEND_ROOT.resolve() == WEB_ROOT.resolve() and not args.isolated_test_fixture:
        return fail(f"BACKEND_ROOT và WEB_ROOT trùng nhau ({BACKEND_ROOT}). Cannot publish backend artifacts from web root to itself. Set STOCK_LOOKUP_BACKEND_DIR to point to dashboard-runtime (e.g. C:\\Projects\\StockLookup\\dashboard-runtime).")

    try:
        branch, _remote, head = git_preflight()
        session_report = validate_release_session()
    except (OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        return fail(str(exc))

    for line in session_report.render():
        log(line)
    if not session_report.ready:
        return fail("release session validation failed — see SESSION_MISMATCH above; "
                     "no artifact was copied, no manifest written, no git mutation performed")

    try:
        if args.live:
            sync_remote_before_live(branch)
            head = current_head()
        rows, breadth, market_session = validate_snapshot()
        copy_plan = plan_copy_artifacts()
        manifest, screener_js_content = compute_manifest(rows, breadth, market_session, head)
        version_plan = plan_asset_versions(str(manifest["build_id"]))
        validate_json_artifacts()
        whitelist = build_whitelist()
    except (OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        return fail(str(exc))

    if not args.live:
        log("[DRY-RUN] Kiểm tra xong — CHƯA copy artifact, CHƯA ghi manifest, CHƯA sửa "
            "HTML/CSS/JS, CHƯA git add/commit/push. Không file nào trên đĩa bị thay đổi.")
        log(f"[DRY-RUN] Sẽ copy {len(copy_plan)} artifact từ backend: "
            f"{', '.join(copy_plan) or '(không có — backend=web hoặc đã khớp)'}")
        log(f"[DRY-RUN] Build id dự kiến (phiên {market_session}): {manifest['build_id']}")
        log(f"[DRY-RUN] Sẽ cập nhật asset-version trên {len(version_plan)} trang HTML: "
            f"{', '.join(version_plan) or '(không có)'}")
        log(f"[DRY-RUN] Whitelist git nếu publish thật: {len(whitelist)} file")
        log("[DRY-RUN] Muốn xuất bản thật phải gọi rõ: publish_dashboard.py --live")
        return 0

    try:
        copy_public_artifacts()
        write_build_manifest(manifest, screener_js_content)
        update_asset_versions(str(manifest["build_id"]))
        validate_json_artifacts()
        whitelist = build_whitelist()
    except (OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        return fail(str(exc))

    smoke_rc = run_release_smoke_tests()
    if smoke_rc != 0:
        return fail(f"tests/release-smoke.test.js failed with exit code {smoke_rc}; "
                     "no git mutation performed")

    ok, diff_check = git("diff", "--check", "--", *whitelist)
    if not ok:
        return fail(f"git diff --check thất bại: {diff_check}")
    ok, status = git("status", "--porcelain", "--", *whitelist)
    if not ok:
        return fail(f"git status thất bại: {status}")
    changed = [line for line in status.splitlines() if line]
    log(f"Whitelist hợp lệ: {len(whitelist)} file; thay đổi: {len(changed)}.")
    for line in changed:
        log(f"  {line}")
    if not changed:
        log("Không có thay đổi; exit 0, không commit/push.")
        return 0
    return publish_live(whitelist, branch)


if __name__ == "__main__":
    raise SystemExit(main())
