"""Public Dashboard session companion artifacts from retained canonical evidence.

Publication-layer only.  This module does not acquire market data, does not call
DNSE, and is not a release orchestrator.  It computes the two current-session
files that release-smoke and Deploy Pages require:

    data/session_<YYYY_MM_DD>_manifest.json
    report-<YYYY-MM-DD>.html

Pure ``compute_*`` functions never write.  ``apply_*`` writes the already-computed
bytes.  Dry-run callers must stop at compute/validate.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from atomic_io import atomic_write_file, validate_json_file
from daily_research_session_operations import load_registry

CONTRACT_VERSION = "dashboard_session_companions/v1"
SCHEMA_VERSION = "1.0.0"
SESSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PROHIBITED_CLAIMS = (
    "No price targets or expected returns.",
    "No buy/sell/hold recommendations.",
    "No portfolio weighting or position sizing.",
    "No probabilistic predictions or calibrated bull/bear certainty.",
    "No unqualified liquidity or execution-capacity assertions.",
    "Strict valuation, PIT, and RAW_AS_TRADED remain unpromoted.",
)


class DashboardSessionCompanionError(RuntimeError):
    """A companion computation or apply gate refused to pass."""


@dataclass(frozen=True)
class SessionCompanionPlan:
    session: str
    manifest_relpath: str
    report_relpath: str
    manifest: dict[str, Any]
    manifest_text: str
    report_html: str
    omitted: bool = False
    omit_reason: str | None = None

    @property
    def relpaths(self) -> tuple[str, str]:
        return self.manifest_relpath, self.report_relpath

    @property
    def manifest_bytes(self) -> bytes:
        return self.manifest_text.encode("utf-8")

    @property
    def report_bytes(self) -> bytes:
        return self.report_html.encode("utf-8")


def companion_relpaths(session: str) -> tuple[str, str]:
    """Exact current-session companion paths.  Never a glob."""
    if not SESSION_RE.fullmatch(session or ""):
        raise DashboardSessionCompanionError(f"INVALID_SESSION:{session}")
    return (
        f"data/session_{session.replace('-', '_')}_manifest.json",
        f"report-{session}.html",
    )


def producer_git_head(root: Path) -> str:
    value = _git(root, ["rev-parse", "HEAD"])
    return value or "UNAVAILABLE"


def producer_git_subject(root: Path) -> str:
    value = _git(root, ["log", "-1", "--format=%s"])
    return value or "UNAVAILABLE"


def compute_session_companions(
    producer_root: Path,
    session: str,
    *,
    producer_commit: str,
    producer_commit_summary: str,
    build_id: str,
    producer_run_identity: str | None = None,
) -> SessionCompanionPlan:
    """Pure: load retained canonical evidence and compute both companion artifacts."""
    root = Path(producer_root).resolve()
    if not SESSION_RE.fullmatch(session or ""):
        raise DashboardSessionCompanionError(f"INVALID_SESSION:{session}")
    manifest_relpath, report_relpath = companion_relpaths(session)
    handoff_path = (
        root / "operations-review" / "canonical-post-close-v1" / session / "session_handoff_bundle.json"
    )
    if not handoff_path.is_file():
        return SessionCompanionPlan(
            session=session,
            manifest_relpath=manifest_relpath,
            report_relpath=report_relpath,
            manifest={},
            manifest_text="",
            report_html="",
            omitted=True,
            omit_reason="NO_RETAINED_CANONICAL_HANDOFF",
        )
    handoff = _load_object(handoff_path)
    if handoff.get("session") != session:
        raise DashboardSessionCompanionError("HANDOFF_SESSION_MISMATCH")
    resolved = (handoff.get("market_session_proof") or {}).get("resolved_completed_session")
    if resolved != session:
        raise DashboardSessionCompanionError("HANDOFF_RESOLVED_SESSION_MISMATCH")
    run_path, run_manifest = _unique_producer_run(root, session, run_identity=producer_run_identity)
    handoff_sources = handoff.get("upstream_evidence_identities") or {}
    run_sources = run_manifest.get("upstream_artifact_identities") or {}
    for name in ("descriptive", "screening", "tactical", "triage"):
        if ((handoff_sources.get(name) or {}).get("artifact_identity") !=
                (run_sources.get(name) or {}).get("artifact_identity")):
            raise DashboardSessionCompanionError(f"HANDOFF_SOURCE_LINEAGE_MISMATCH:{name}")
    registry = load_registry(root)
    completed = (registry.get("completed_sessions") or {}).get(session) or {}
    if completed.get("status") != "COMPLETED_RETAINED_EVIDENCE":
        raise DashboardSessionCompanionError(f"SESSION_NOT_COMPLETED_RETAINED_EVIDENCE:{session}")
    entries = (registry.get("sessions") or {}).get(session) or {}
    descriptive = _optional_registry_artifact(root, entries, "descriptive", session)
    tactical = _optional_registry_artifact(root, entries, "tactical", session)
    triage = _optional_registry_artifact(root, entries, "triage", session)
    manifest = _build_manifest(
        session=session,
        producer_commit=producer_commit,
        producer_commit_summary=producer_commit_summary,
        build_id=build_id,
        handoff=handoff,
        run_path=run_path,
        run_manifest=run_manifest,
        completed=completed,
        entries=entries,
        descriptive=descriptive,
        tactical=tactical,
        triage=triage,
        handoff_path=handoff_path,
        root=root,
    )
    manifest_text = _dump_json(manifest)
    report_html = _build_report_html(manifest, build_id=build_id)
    plan = SessionCompanionPlan(
        session=session,
        manifest_relpath=manifest_relpath,
        report_relpath=report_relpath,
        manifest=manifest,
        manifest_text=manifest_text,
        report_html=report_html,
    )
    validate_computed_companions(plan)
    return plan


def validate_computed_companions(plan: SessionCompanionPlan) -> None:
    if plan.omitted:
        raise DashboardSessionCompanionError(f"CANNOT_VALIDATE_OMITTED_COMPANIONS:{plan.omit_reason}")
    if plan.manifest.get("dashboard_session") != plan.session:
        raise DashboardSessionCompanionError("MANIFEST_SESSION_MISMATCH")
    parsed = json.loads(plan.manifest_text)
    if parsed != plan.manifest:
        raise DashboardSessionCompanionError("MANIFEST_SERIALIZATION_DRIFT")
    if plan.session != "2026-08-25":
        forbidden_prior = ("25/08/2026", "Phiên giao dịch 25/08/2026", "246 tăng", "437 giảm",
                           "95 Entry-Relevant", "95 cơ hội")
        lowered = plan.report_html
        for token in forbidden_prior:
            if token in lowered:
                raise DashboardSessionCompanionError(f"REPORT_CONTAINS_PRIOR_SESSION_FACTS:{token}")
    if plan.session not in plan.report_html:
        raise DashboardSessionCompanionError("REPORT_MISSING_SESSION")
    breadth = (plan.manifest.get("market_summary") or {})
    for key in ("advancing", "declining", "unchanged"):
        value = breadth.get(key)
        if isinstance(value, int) and str(value) not in plan.report_html:
            raise DashboardSessionCompanionError(f"REPORT_MISSING_BREADTH:{key}")
    if not plan.manifest_text.strip() or not plan.report_html.strip():
        raise DashboardSessionCompanionError("COMPANION_BYTES_EMPTY")


def apply_session_companions(web_root: Path, plan: SessionCompanionPlan) -> list[str]:
    """LIVE only: write exactly the computed companion bytes."""
    if plan.omitted:
        return []
    validate_computed_companions(plan)
    web = Path(web_root).resolve()
    written: list[str] = []
    mapping = (
        (plan.manifest_relpath, plan.manifest_text, validate_json_file),
        (plan.report_relpath, plan.report_html, None),
    )
    for relative, content, validator in mapping:
        target = web / relative
        atomic_write_file(target, content, validator=validator, encoding="utf-8", newline="\n")
        if target.read_text(encoding="utf-8") != content:
            raise DashboardSessionCompanionError(f"APPLIED_BYTES_DRIFT:{relative}")
        written.append(relative)
    return written


def extend_whitelist(
    whitelist: list[str],
    plan: SessionCompanionPlan,
    *,
    web_root: Path,
    require_exist: bool,
) -> list[str]:
    """Add only the current-session companion paths, never a report-* or data/* glob."""
    if plan.omitted:
        return sorted(whitelist)
    extras = list(plan.relpaths)
    if require_exist:
        missing = [relative for relative in extras if not (Path(web_root) / relative).is_file()]
        if missing:
            raise DashboardSessionCompanionError(
                "COMPANION_WHITELIST_MISSING:" + ",".join(missing)
            )
    return sorted(set(whitelist) | set(extras))


def _git(root: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, check=False, shell=False,
        )
    except OSError:
        return None
    value = (result.stdout or "").strip()
    if result.returncode != 0 or not value:
        return None
    return value


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DashboardSessionCompanionError(f"RETAINED_SOURCE_UNREADABLE:{path}") from exc
    if not isinstance(value, dict):
        raise DashboardSessionCompanionError(f"RETAINED_SOURCE_NOT_OBJECT:{path}")
    return value


def _dump_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _unique_producer_run(
    root: Path, session: str, *, run_identity: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    matches: list[tuple[Path, dict[str, Any]]] = []
    base = root / "operations-review" / "daily-producer-runs-v1" / session
    for path in sorted(base.glob("*/run_manifest.json")):
        data = _load_object(path)
        if data.get("target_market_session") == session:
            matches.append((path, data))
    if run_identity is not None:
        matches = [(path, data) for path, data in matches if data.get("run_identity") == run_identity]
    if len(matches) != 1:
        raise DashboardSessionCompanionError(
            f"DAILY_PRODUCER_RUN_AMBIGUOUS_OR_MISSING:{session}:count={len(matches)}"
        )
    return matches[0]


def _optional_registry_artifact(
    root: Path, entries: Mapping[str, Any], name: str, session: str,
) -> tuple[Path, dict[str, Any]] | None:
    entry = entries.get(name)
    if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str):
        return None
    path = root / str(entry["path"])
    data = _load_object(path)
    expected = entry.get("artifact_identity")
    if expected and data.get("artifact_identity") != expected:
        raise DashboardSessionCompanionError(f"REGISTRY_IDENTITY_MISMATCH:{name}")
    if name in ("descriptive", "tactical") and data.get("session") not in (None, session):
        if data.get("session") != session:
            raise DashboardSessionCompanionError(f"REGISTRY_SESSION_MISMATCH:{name}")
    return path, data


def _rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _descriptor(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, Mapping):
        inner = value.get("descriptor")
        if isinstance(inner, str) and inner:
            return inner
    return None


def _build_manifest(
    *,
    session: str,
    producer_commit: str,
    producer_commit_summary: str,
    build_id: str,
    handoff: Mapping[str, Any],
    run_path: Path,
    run_manifest: Mapping[str, Any],
    completed: Mapping[str, Any],
    entries: Mapping[str, Any],
    descriptive: tuple[Path, dict[str, Any]] | None,
    tactical: tuple[Path, dict[str, Any]] | None,
    triage: tuple[Path, dict[str, Any]] | None,
    handoff_path: Path,
    root: Path,
) -> dict[str, Any]:
    producer = handoff.get("daily_producer") or {}
    coverage = handoff.get("market_coverage") or {}
    run_coverage = run_manifest.get("coverage_summary") or {}
    breadth_h = handoff.get("breadth") or {}
    descriptive_payload = descriptive[1] if descriptive else {}
    market_breadth = descriptive_payload.get("market_breadth") or {}
    trend = market_breadth.get("trend") or {}
    momentum_stats = (market_breadth.get("momentum_descriptor") or {}).get("input_statistics") or {}
    volatility = market_breadth.get("volatility") or {}
    tactical_counts = dict(handoff.get("tactical_counts") or {})
    tactical_states = ((tactical[1].get("coverage") or {}).get("entry_state_counts") if tactical else None) or {}
    triage_counts = (triage[1].get("cohort_counts") if triage else None) or {}

    market_summary: dict[str, Any] = {
        "advancing": breadth_h.get("advancing", market_breadth.get("advancing")),
        "declining": breadth_h.get("declining", market_breadth.get("declining")),
        "unchanged": breadth_h.get("unchanged", market_breadth.get("unchanged")),
        "breadth_descriptor": _descriptor(breadth_h.get("breadth_descriptor"))
        or _descriptor(market_breadth.get("breadth_descriptor")),
        "momentum_descriptor": _descriptor(breadth_h.get("momentum_descriptor"))
        or _descriptor(market_breadth.get("momentum_descriptor")),
    }
    if isinstance(market_breadth.get("advance_ratio"), (int, float)):
        market_summary["advance_ratio"] = market_breadth["advance_ratio"]
    if isinstance(trend.get("above_ma20"), int):
        market_summary["above_ma20"] = trend["above_ma20"]
    if isinstance(trend.get("at_or_below_ma20"), int):
        market_summary["at_or_below_ma20"] = trend["at_or_below_ma20"]
    if isinstance(momentum_stats.get("negative_count"), int):
        market_summary["negative_20d_momentum_count"] = momentum_stats["negative_count"]
    if isinstance(momentum_stats.get("positive_count"), int):
        market_summary["positive_20d_momentum_count"] = momentum_stats["positive_count"]
    if isinstance(volatility.get("median"), (int, float)):
        market_summary["median_20d_cross_sectional_volatility"] = {
            "value": volatility["median"],
            "authority_tier": volatility.get("authority_tier") or "UNAVAILABLE",
            "warning": volatility.get("warning") or "UNAVAILABLE",
        }

    triage_summary: dict[str, Any] = {}
    if isinstance(run_coverage.get("entry_relevant"), int):
        triage_summary["total_entry_relevant"] = run_coverage["entry_relevant"]
    elif handoff.get("entry_relevant_count") is None:
        triage_summary["total_entry_relevant"] = {
            "status": "UNAVAILABLE",
            "reason": "HANDOFF_ENTRY_RELEVANT_COUNT_NULL",
        }
    if isinstance(run_coverage.get("high_priority_review"), int):
        triage_summary["high_priority_review"] = run_coverage["high_priority_review"]
    elif isinstance(handoff.get("high_priority_review_count"), int):
        triage_summary["high_priority_review"] = handoff["high_priority_review_count"]
    elif isinstance(triage_counts.get("TACTICAL_HIGH_PRIORITY_REVIEW"), int):
        triage_summary["high_priority_review"] = triage_counts["TACTICAL_HIGH_PRIORITY_REVIEW"]
    state_map = {
        "breakout_ready": "BREAKOUT_READY",
        "base_building": "BASE_BUILDING",
        "early_reversal_candidate": "EARLY_REVERSAL_CANDIDATE",
        "uptrend_confirmed": "UPTREND_CONFIRMED",
        "selling_pressure_easing": "SELLING_PRESSURE_EASING",
        "sideways_neutral": "SIDEWAYS_NEUTRAL",
        "downtrend": "DOWNTREND",
        "breakdown_risk": "BREAKDOWN_RISK",
        "distribution_risk": "DISTRIBUTION_RISK",
    }
    for public_name, source_name in state_map.items():
        if isinstance(tactical_counts.get(source_name), int):
            triage_summary[public_name] = tactical_counts[source_name]
        elif isinstance(tactical_states.get(source_name), int):
            triage_summary[public_name] = tactical_states[source_name]

    current_session_sources: list[dict[str, Any]] = []
    reusable_prior: list[dict[str, Any]] = []
    for item in (run_manifest.get("source_plan") or {}).get("items") or []:
        if not isinstance(item, Mapping) or not item.get("artifact_identity"):
            continue
        record = {
            "component_id": item.get("input_class"),
            "identity": item.get("artifact_identity"),
            "session": item.get("source_session"),
            "path": item.get("artifact_path"),
            "freshness": item.get("freshness"),
            "execution_disposition": item.get("execution_disposition"),
        }
        if item.get("source_session") == session and item.get("freshness") == "EXACT_SESSION":
            current_session_sources.append(record)
        else:
            reusable_prior.append(record)

    packet = handoff.get("current_research_packet_identity")
    cohort = handoff.get("prospective_cohort_snapshot_identity")
    blocked = list(handoff.get("blocked_dimensions") or run_manifest.get("blocked_dimensions") or [])
    authority = dict(handoff.get("authority_boundary") or run_manifest.get("authority_boundary") or {})

    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "dashboard_session": session,
        "build_id": build_id or {"status": "UNAVAILABLE", "reason": "BUILD_ID_NOT_SUPPLIED"},
        "producer_commit": producer_commit or "UNAVAILABLE",
        "producer_commit_summary": producer_commit_summary or "UNAVAILABLE",
        "producer_commit_semantics": "pre_publication_producer_head",
        "canonical_producer_status": {
            "status": producer.get("status") or "UNAVAILABLE",
            "operation_identity": producer.get("operation_identity")
            or handoff.get("daily_session_operation_identity"),
            "run_identity": producer.get("run_identity") or handoff.get("daily_producer_run_identity"),
            "registration_state": completed.get("status") or "UNAVAILABLE",
            "technical_coverage": coverage.get("same_session_technical_feature_available_count")
            or run_coverage.get("technical"),
            "observed_session_cohort": coverage.get("observed_session_cohort"),
            "active_equity_universe": coverage.get("current_active_equity_denominator"),
            "input_candidates": coverage.get("input_candidates"),
        },
        "market_summary": market_summary,
        "tactical_triage_counts": triage_summary,
        "current_research_packet_identity": packet or {
            "status": "UNAVAILABLE",
            "reason": "NOT_RETAINED_IN_HANDOFF",
        },
        "prospective_cohort_identity": cohort or {
            "status": "UNAVAILABLE",
            "reason": "NOT_RETAINED_IN_HANDOFF",
        },
        "source_artifacts": {
            "canonical_current_session": current_session_sources,
            "reusable_prior_context": reusable_prior,
            "retained_tier_handoff": {
                "path": _rel(root, handoff_path),
                "session": session,
            },
            "daily_producer_run_manifest": {
                "path": _rel(root, run_path),
                "run_identity": run_manifest.get("run_identity"),
            },
        },
        "governed_boundaries": {
            "authority_boundary": authority,
            "blocked_dimensions": blocked,
            "strict_valuation": "BLOCKED" if "STRICT_VALUATION" in blocked else "UNAVAILABLE",
            "liquidity_sizing_execution": "BLOCKED_NO_SIZING_EXECUTION_AUTHORITY"
            if "NO_LIQUIDITY_SIZING_EXECUTION_AUTHORITY" in blocked else "UNAVAILABLE",
            "macro_optional": "UNAVAILABLE" if "MACRO_OPTIONAL_UNAVAILABLE" in blocked else "UNAVAILABLE",
            "explicit_portfolio": "NOT_SUPPLIED" if "NO_EXPLICIT_PORTFOLIO" in blocked else "UNAVAILABLE",
            "pit_raw_as_traded": "NOT_PROMOTED",
            "calibrated_targets_probabilities": "NOT_EMITTED",
            "prohibited_claims": list(PROHIBITED_CLAIMS),
        },
        "warnings": list(handoff.get("warnings") or run_manifest.get("warnings") or []),
    }


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _count(manifest: Mapping[str, Any], key: str) -> str:
    value = (manifest.get("tactical_triage_counts") or {}).get(key)
    if isinstance(value, int):
        return str(value)
    return "unavailable"


def _build_report_html(manifest: Mapping[str, Any], *, build_id: str) -> str:
    session = str(manifest["dashboard_session"])
    day, month, year = session[8:10], session[5:7], session[0:4]
    display = f"{day}/{month}/{year}"
    status = manifest.get("canonical_producer_status") or {}
    market = manifest.get("market_summary") or {}
    bounds = manifest.get("governed_boundaries") or {}
    token = _esc(build_id or session)
    advancing = market.get("advancing")
    declining = market.get("declining")
    unchanged = market.get("unchanged")
    technical = status.get("technical_coverage")
    observed = status.get("observed_session_cohort")
    active = status.get("active_equity_universe")
    high_priority = _count(manifest, "high_priority_review")
    entry_relevant = (manifest.get("tactical_triage_counts") or {}).get("total_entry_relevant")
    entry_label = str(entry_relevant) if isinstance(entry_relevant, int) else "unavailable"
    packet = manifest.get("current_research_packet_identity")
    cohort = manifest.get("prospective_cohort_identity")
    packet_s = packet if isinstance(packet, str) else "UNAVAILABLE"
    cohort_s = cohort if isinstance(cohort, str) else "UNAVAILABLE"
    blocked = bounds.get("blocked_dimensions") or []
    blocked_html = "".join(f"<li><code>{_esc(item)}</code></li>" for item in blocked)
    claims_html = "".join(f"<li>{_esc(item)}</li>" for item in (bounds.get("prohibited_claims") or []))
    warnings_html = "".join(f"<li>{_esc(item)}</li>" for item in (manifest.get("warnings") or []))
    current_sources = ((manifest.get("source_artifacts") or {}).get("canonical_current_session") or [])
    source_rows = []
    for item in current_sources:
        source_rows.append(
            "<tr>"
            f"<td>{_esc(item.get('component_id'))}</td>"
            f"<td><code class=\"code-pill\">{_esc(item.get('identity'))}</code></td>"
            f"<td>{_esc(item.get('session'))}</td>"
            f"<td>{_esc(item.get('freshness'))}</td>"
            "</tr>"
        )
    source_table = "\n".join(source_rows) or (
        "<tr><td colspan=\"4\">No exact-session source identities retained.</td></tr>"
    )
    vol = market.get("median_20d_cross_sectional_volatility")
    vol_note = ""
    if isinstance(vol, Mapping) and "value" in vol:
        vol_note = (
            f"Median 20d cross-sectional volatility {vol['value']:.6f} "
            f"({vol.get('authority_tier')}; {vol.get('warning')})."
        )
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Báo cáo phiên {display} | Stock Lookup</title>
  <meta name="description" content="Canonical session report {session}: completed Daily Producer, exact-session coverage, market breadth, tactical counts, and explicit authority boundaries.">
  <link rel="stylesheet" href="style.css?v={token}">
</head>
<body class="bg-bg text-white font-sans" data-page="archive" data-session="{_esc(session)}">
  <main class="vs-content" style="max-width: 1100px; margin: 1.5rem auto; padding: 0 1rem;">
    <p class="section-eyebrow">Báo cáo phiên thị trường</p>
    <h1>Phiên giao dịch {display}</h1>
    <p>
      <span class="badge-soft">Canonical { _esc(status.get("status") or "UNAVAILABLE") }</span>
      <span class="badge-soft">Exact-session coverage {_esc(technical)} / {_esc(observed)} observed · {_esc(active)} active equity</span>
    </p>
    <p>
      Surfaces:
      <a href="dashboard.html?v={token}">dashboard</a> ·
      <a href="screener.html?v={token}">screener</a> ·
      <a href="analysis.html?v={token}">analysis</a>
    </p>

    <section>
      <h2>Độ rộng thị trường</h2>
      <p>Descriptor: <strong>{_esc(market.get("breadth_descriptor"))}</strong></p>
      <p>Momentum: <strong>{_esc(market.get("momentum_descriptor"))}</strong></p>
      <p>Advancing {_esc(advancing)} · Declining {_esc(declining)} · Unchanged {_esc(unchanged)}</p>
      <p>Above MA20: {_esc(market.get("above_ma20"))} · At or below MA20: {_esc(market.get("at_or_below_ma20"))}</p>
      <p>20d momentum counts: negative {_esc(market.get("negative_20d_momentum_count"))} · positive {_esc(market.get("positive_20d_momentum_count"))}</p>
      <p>{_esc(vol_note)}</p>
    </section>

    <section>
      <h2>Tactical / triage summary</h2>
      <ul>
        <li>Entry-relevant: { _esc(entry_label) }</li>
        <li>High-priority review: {_esc(high_priority)}</li>
        <li>BREAKOUT_READY: {_esc(_count(manifest, "breakout_ready"))}</li>
        <li>BASE_BUILDING: {_esc(_count(manifest, "base_building"))}</li>
        <li>EARLY_REVERSAL_CANDIDATE: {_esc(_count(manifest, "early_reversal_candidate"))}</li>
        <li>UPTREND_CONFIRMED: {_esc(_count(manifest, "uptrend_confirmed"))}</li>
        <li>SELLING_PRESSURE_EASING: {_esc(_count(manifest, "selling_pressure_easing"))}</li>
        <li>SIDEWAYS_NEUTRAL: {_esc(_count(manifest, "sideways_neutral"))}</li>
        <li>DOWNTREND: {_esc(_count(manifest, "downtrend"))}</li>
        <li>BREAKDOWN_RISK: {_esc(_count(manifest, "breakdown_risk"))}</li>
        <li>DISTRIBUTION_RISK: {_esc(_count(manifest, "distribution_risk"))}</li>
      </ul>
    </section>

    <section>
      <h2>Authority / blockers</h2>
      <p>These dimensions remain explicitly unavailable for session {_esc(session)}:</p>
      <ul>
        <li>Strict valuation: {_esc(bounds.get("strict_valuation"))}</li>
        <li>Liquidity / sizing / execution: {_esc(bounds.get("liquidity_sizing_execution"))}</li>
        <li>PIT / RAW_AS_TRADED: {_esc(bounds.get("pit_raw_as_traded"))}</li>
        <li>Calibrated targets / probabilities: {_esc(bounds.get("calibrated_targets_probabilities"))}</li>
        <li>Macro optional: {_esc(bounds.get("macro_optional"))}</li>
        <li>Explicit portfolio: {_esc(bounds.get("explicit_portfolio"))}</li>
      </ul>
      <p>Blocked dimensions:</p>
      <ul>{blocked_html}</ul>
      <p>Prohibited claims:</p>
      <ul>{claims_html}</ul>
    </section>

    <section>
      <h2>Lineage</h2>
      <p>Producer commit: <code class="code-pill">{_esc(manifest.get("producer_commit"))}</code></p>
      <p>Producer summary: {_esc(manifest.get("producer_commit_summary"))}</p>
      <p>Operation: <code class="code-pill">{_esc((status.get("operation_identity")))}</code></p>
      <p>Daily Producer run: <code class="code-pill">{_esc(status.get("run_identity"))}</code></p>
      <p>Registration: {_esc(status.get("registration_state"))}</p>
      <p>Current research packet: <code class="code-pill">{_esc(packet_s)}</code></p>
      <p>Prospective cohort: <code class="code-pill">{_esc(cohort_s)}</code></p>
      <table class="provenance-table">
        <thead><tr><th>Component</th><th>Identity</th><th>Session</th><th>Freshness</th></tr></thead>
        <tbody>
          {source_table}
        </tbody>
      </table>
    </section>

    <section>
      <h2>Warnings</h2>
      <ul>{warnings_html}</ul>
    </section>
  </main>
</body>
</html>
"""
