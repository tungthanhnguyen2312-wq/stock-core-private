"""release_session_contract.py — single authority for "what release session is this?"

Why this exists: publish_dashboard.py used to derive the dashboard release session by
reading screen_snapshot.csv's own `date` column (max() across non-delisted rows) with no
external cross-check. That heuristic cannot detect staleness: a frozen leftover copy of
screen_snapshot.csv is internally self-consistent (every row shares its own frozen date),
so max() over it always "succeeds" and reports a confident, wrong session. The result was
a dry-run that could report a stale session (e.g. 2026-07-24) as a valid publish plan even
though bundle_manifest.json and every other exact-session artifact already agreed on a
newer session (2026-08-04).

This module cross-validates every session-sensitive artifact in a root directory against
the one external authority the pipeline already produces: bundle_manifest.json's
`freshness.reference_session` (itself anchored to the trading calendar by
export_ai_bundle.py::check_freshness / get_session_anchor_and_prior — see
daily_analysis_pipeline.py and docs/exact_session_bundle_contract.md). Never mtime: two
files can share a modification time and disagree on session, or vice versa (see
export_ai_bundle.py::check_artifact_order, which deliberately keeps mtime scoped to
"was downstream generated after upstream" and never uses it as a stand-in for session
identity — this module follows the same principle).

Design rules (do not relax these; each one closes a real failure mode):
  * The authoritative session comes from bundle_manifest.json when present. A present but
    unreadable/incomplete manifest is a hard failure, not a demotion to legacy mode.
  * Only a genuinely ABSENT manifest enters "legacy_cross_check" mode, and that mode only
    ever succeeds on unanimous agreement among the artifacts that are present — never the
    min, max, first, or any other single-file fallback.
  * A file with no registered session rule, or whose own session field can't be parsed, is
    reported as a failure, never silently skipped.
  * session-neutral artifacts (financial statement snapshots keyed by reporting period,
    not by market session) are named explicitly by the caller and are never compared
    against the reference session.
  * Reporting order always follows the caller-supplied `required` order — deterministic,
    not gathered from dict/set iteration.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

#: Artifacts whose own data represents a reporting period, not a market session (e.g. a
#: quarterly financial statement snapshot). Callers pass the names that apply to their
#: own required list; this module never guesses which artifacts are session-neutral.
FINANCIAL_SNAPSHOT_ARTIFACTS = frozenset({"financial_snapshot.csv", "financial_snapshot.parquet"})


def _csv_session_date(path: Path, *, exclude_delisted: bool) -> str | None:
    """max() of the `date` column — mirrors the existing, already-established convention
    in publish_dashboard.py::validate_snapshot() and export_ai_bundle.py::load_live_snapshot_rows()
    / load_ta_signal_rows(). Never mtime; always the data's own date column."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        dates: list[str] = []
        for row in reader:
            if exclude_delisted and str(row.get("exchange") or "").strip().upper() == "DELISTED":
                continue
            value = str(row.get("date") or "").strip()
            if value:
                dates.append(value)
    return max(dates) if dates else None


def _json_session_date(path: Path, field_path: tuple[str, ...]) -> str | None:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    node: object = payload
    for key in field_path:
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
    return str(node) if node not in (None, "") else None


#: relative filename -> (kind, accessor spec). One explicit, named rule per artifact —
#: adding a new session-sensitive artifact means adding a line here, not inferring one.
ARTIFACT_SESSION_RULES: dict[str, tuple[str, object]] = {
    "screen_snapshot.csv": ("csv", {"exclude_delisted": True}),
    "screen_snapshot_live.csv": ("csv", {"exclude_delisted": False}),
    "market_breadth.csv": ("csv", {"exclude_delisted": False}),
    "ta_signals.csv": ("csv", {"exclude_delisted": False}),
    "analysis_bundle.json": ("json", ("reference_session_date",)),
    "analysis_latest.json": ("json", ("summary", "session_date")),
    "data/candle_signals.json": ("json", ("scan_date",)),
    "data/sector_heatmap.json": ("json", ("scan_date",)),
    "data/candlestick_patterns.json": ("json", ("scan_date",)),
}


@dataclass
class ArtifactSessionResult:
    name: str
    status: str  # "ok" | "mismatch" | "missing" | "unreadable" | "neutral"
    observed: str | None
    detail: str = ""


@dataclass
class ReleaseSessionReport:
    session: str | None
    authority: str  # "bundle_manifest.json" | "legacy_cross_check" | "none"
    ready: bool
    results: list[ArtifactSessionResult] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def mismatch_lines(self) -> list[str]:
        lines = [f"  {p}" for p in self.problems]
        for r in self.results:
            if r.status in ("mismatch", "missing", "unreadable"):
                if r.observed is not None:
                    lines.append(f"  {r.name} observed={r.observed} expected={self.session or 'UNRESOLVED'}")
                else:
                    lines.append(f"  {r.name}: {r.detail}")
        return lines

    def render(self) -> list[str]:
        """Deterministic preflight summary lines, in the order the CLI contract prescribes."""
        validated = [r.name for r in self.results if r.status in ("ok", "neutral")]
        lines = [
            f"RELEASE_SESSION={self.session or 'UNRESOLVED'}",
            f"SESSION_AUTHORITY={self.authority}",
            f"REQUIRED_ARTIFACTS_VALIDATED={','.join(validated) if validated else '(none)'}",
            f"SESSION_MISMATCHES={len(self.mismatch_lines())}",
            f"PUBLISH_READY={'YES' if self.ready else 'NO'}",
        ]
        if not self.ready:
            lines.append("SESSION_MISMATCH:")
            lines.extend(self.mismatch_lines())
        return lines


def _manifest_authority(root: Path, today: str) -> tuple[str | None, str, list[str]]:
    """Read bundle_manifest.json's freshness.reference_session as authority.

    Returns (session_or_None, authority_label, problems). A manifest that is present but
    malformed/incomplete is reported as a problem under authority "bundle_manifest.json" —
    it never falls through to legacy mode, because a broken manifest is not the same thing
    as no manifest.
    """
    manifest_path = root / "bundle_manifest.json"
    if not manifest_path.is_file():
        return None, "legacy_cross_check", []

    problems: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return None, "bundle_manifest.json", [f"bundle_manifest.json is not readable JSON: {exc}"]
    if not isinstance(manifest, Mapping):
        return None, "bundle_manifest.json", ["bundle_manifest.json does not contain a JSON object"]

    freshness = manifest.get("freshness")
    if not isinstance(freshness, Mapping):
        return None, "bundle_manifest.json", ["bundle_manifest.json has no freshness block"]

    session = freshness.get("reference_session")
    if not session or not isinstance(session, str):
        return None, "bundle_manifest.json", [
            "bundle_manifest.json freshness.reference_session is missing or not a string"]

    if freshness.get("blocked") is True:
        problems.append(f"bundle_manifest.json freshness.blocked=true (status={freshness.get('status')!r})")
    if session > today:
        problems.append(f"bundle_manifest.json freshness.reference_session={session!r} is in the future (today={today})")

    trusted = manifest.get("trusted_subset")
    if isinstance(trusted, Mapping):
        identity = trusted.get("session_identity")
        if identity and identity != session:
            problems.append(
                f"trusted_subset.session_identity={identity!r} disagrees with "
                f"freshness.reference_session={session!r}")

    return session, "bundle_manifest.json", problems


def resolve_release_session(
    root: Path | str,
    required: Sequence[str],
    *,
    session_neutral: Iterable[str] = (),
    today: str | None = None,
) -> ReleaseSessionReport:
    """Resolve and validate the one authoritative release session for `root`.

    `required` is validated in the exact order given — that order becomes the report's
    order, so callers should pass a fixed, explicit sequence (a module-level tuple), not
    a set or a directory listing, to keep output deterministic.
    """
    root = Path(root)
    neutral = set(session_neutral)
    today = today or datetime.now(timezone.utc).date().isoformat()

    session, authority, problems = _manifest_authority(root, today)

    results: list[ArtifactSessionResult] = []
    observed_by_name: dict[str, str] = {}
    for name in required:
        if name in neutral:
            results.append(ArtifactSessionResult(name, "neutral", None, "session-neutral artifact; not compared"))
            continue
        path = root / name
        if not path.is_file():
            results.append(ArtifactSessionResult(name, "missing", None, f"missing from {root}"))
            continue
        rule = ARTIFACT_SESSION_RULES.get(name)
        if rule is None:
            results.append(ArtifactSessionResult(name, "unreadable", None,
                                                  f"no session rule registered for {name!r}"))
            continue
        kind, spec = rule
        try:
            observed = _csv_session_date(path, **spec) if kind == "csv" else _json_session_date(path, spec)  # type: ignore[arg-type]
        except (OSError, ValueError, UnicodeDecodeError, csv.Error) as exc:
            results.append(ArtifactSessionResult(name, "unreadable", None, f"{name}: {exc}"))
            continue
        if not observed:
            results.append(ArtifactSessionResult(name, "missing", None, f"{name} has no parseable session/date value"))
            continue
        observed_by_name[name] = observed
        results.append(ArtifactSessionResult(name, "pending", observed))

    if session is None and authority == "legacy_cross_check" and not problems:
        distinct = sorted(set(observed_by_name.values()))
        if len(distinct) == 1:
            session = distinct[0]
        elif len(distinct) > 1:
            problems.append(
                "no bundle_manifest.json authority is present and the required artifacts "
                f"disagree on session: {', '.join(distinct)}")
        # len == 0: session stays None; caught by the check below.

    if session is None and not problems:
        problems.append("no authoritative session could be resolved (no manifest, and nothing to cross-check)")

    for r in results:
        if r.status != "pending":
            continue
        if session is not None and r.observed == session:
            r.status = "ok"
        else:
            r.status = "mismatch"

    ready = session is not None and not problems and all(r.status in ("ok", "neutral") for r in results)
    return ReleaseSessionReport(session=session, authority=authority, ready=ready, results=results, problems=problems)
