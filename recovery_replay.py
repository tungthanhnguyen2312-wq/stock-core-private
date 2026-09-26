"""RECOVERY_REPLAY: bounded, isolated, resumable retrospective session-market reconstruction.

DNSE_FIRST_DAILY_AND_RECOVERY_INFRASTRUCTURE_CORRECTIVE (2026-09-26, owner-authorized).

What this is
    A first-class, explicitly *non-ordinary* operating mode that re-acquires one past session's
    DNSE daily bars (and, optionally, the existing 11-name DNSE foreign-flow cohort) into explicit
    isolated roots, retains every raw provider response before interpretation, journals every
    request so a crashed/stopped run resumes deterministically without re-spending provider calls,
    and builds ``recovery_session_market_reconstruction/v1`` -- a descriptive reconstruction of that
    session's market, nothing more.

What this is NOT (hard labels on every output)
    * ``operating_mode = RECOVERY_REPLAY`` -- never ORDINARY_DAILY, never M1 live acceptance
      (``m1_live_acceptance_eligible = false``), never an ordinary-Daily reuse input (the Level-2 /
      post-close reuse gates refuse any artifact carrying ``operating_mode = RECOVERY_REPLAY`` or a
      ``recovery_replay`` block -- ``daily_session_level2_package.is_recovery_replay_artifact``).
    * ``temporal_claim = SESSION_MARKET_RECONSTRUCTION_ONLY`` and
      ``pit_friday_decision_reconstruction = false`` -- no Integrated Investment Decision, Daily
      Integrated Decision Brief, ``research_action_posture``, AI handoff, Dashboard, cockpit or
      Action Center is built here. The recovery artifact never claims what Stock Lookup "would have
      decided" on the target session.
    * ``publication = FORBIDDEN``. Nothing under the producer checkout, a production runtime root,
      a git work tree, the Dashboard, the AI handoff, the ordinary Daily registry/completion record
      or any current/latest pointer is ever written (``assert_isolated_roots`` +
      ``RecoveryWriter``).
    * Acquisition is retrospective: every raw record carries its real ``acquired_at``; nothing
      claims it was acquired on the target session. DNSE REST daily bars are the qualified
      adjusted/retrospective descriptive basis -- RAW_AS_TRADED and historical PIT stay NOT
      PROMOTED.
    * The acquisition candidate list is the *current* governed runtime metadata ticker list read
      at recovery time: ``ACQUISITION_ATTEMPT_COHORT`` only, never an official 2026-09-25 market
      denominator. ``ACTIVE_UNIVERSE`` stays UNKNOWN / NOT PROMOTED. Exchange/industry labels and
      every other non-session-locked retained artifact are
      ``CURRENT_RESEARCH_OVERLAY_ACQUIRED_OR_RETAINED_LATER``; ``KNOWN_AS_OF_<session>`` is never
      inferred.

No session is hard-coded here: the target session is always an explicit argument.
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from vn_time import VN_TZ, vn_now

ROOT = Path(__file__).resolve().parent

OPERATING_MODE = "RECOVERY_REPLAY"
RECONSTRUCTION_CONTRACT = "recovery_session_market_reconstruction/v1"
PLAN_CONTRACT = "recovery_acquisition_plan/v1"
JOURNAL_CONTRACT = "recovery_acquisition_journal/v1"
RAW_CONTRACT = "recovery_raw_provider_response/v1"
QUALITY_CONTRACT = "recovery_acquisition_quality/v1"
FOREIGN_FLOW_CONTRACT = "recovery_foreign_flow_value/v1"
TEMPORAL_CLAIM = "SESSION_MARKET_RECONSTRUCTION_ONLY"
OVERLAY_LABEL = "CURRENT_RESEARCH_OVERLAY_ACQUIRED_OR_RETAINED_LATER"
PRICE_BASIS = "DNSE_REST_DAILY_ADJUSTED_RETROSPECTIVE_DESCRIPTIVE_RAW_AS_TRADED_NOT_PROMOTED"

HARD_LABELS: dict[str, Any] = {
    "operating_mode": OPERATING_MODE,
    "temporal_claim": TEMPORAL_CLAIM,
    "pit_friday_decision_reconstruction": False,
    "m1_live_acceptance_eligible": False,
    "publication": "FORBIDDEN",
    "ordinary_daily_reuse": "FORBIDDEN",
    "is_actionable": False,
}
AUTHORITY_BOUNDARY = {
    "RAW_AS_TRADED": "NOT_PROMOTED",
    "HISTORICAL_PIT": "NOT_QUALIFIED",
    "ACTIVE_UNIVERSE": "UNKNOWN_NOT_PROMOTED",
    "LIQUIDITY_SIZING": "BLOCKED",
    "VALUATION": "NOT_ATTACHED",
    "RECOMMENDATION": "NONE",
    "EXECUTION": "NONE",
    "BACKTEST": "NONE",
    "SUPPLEMENTAL_PROVIDER": "NOT_USED_VNSTOCK_KBS_VCI_OPTIONAL_SUPPLEMENTAL_DEFERRED",
}
# Products a RECOVERY_REPLAY must never build or publish (the addendum's scope, verbatim).
FORBIDDEN_PRODUCTS = (
    "INTEGRATED_INVESTMENT_DECISION", "DAILY_INTEGRATED_DECISION_BRIEF", "RESEARCH_ACTION_POSTURE",
    "AI_HANDOFF", "DASHBOARD", "CURRENT_DECISION_COCKPIT", "ACTION_CENTER",
)
# Keys whose presence in a recovery artifact would mean a decision product leaked in.
FORBIDDEN_OUTPUT_KEYS = frozenset({
    "research_action_posture", "integrated_investment_decision", "daily_integrated_decision_brief",
    "decision_identity", "research_stance", "entry_action", "recommendation", "target_price",
    "position_size", "KNOWN_AS_OF",
})

# --- dispositions ------------------------------------------------------------------------------
EXACT_SESSION_OBSERVED = "EXACT_SESSION_OBSERVED"
PRIOR_SESSION_ONLY = "PRIOR_SESSION_ONLY"
PROVIDER_REJECTED = "PROVIDER_REJECTED"
NO_HISTORY = "NO_HISTORY"
TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
RATE_LIMITED = "RATE_LIMITED"
UNKNOWN = "UNKNOWN"
NOT_ATTEMPTED = "NOT_ATTEMPTED"
AUTH_FAILED = "AUTH_FAILED"
DISPOSITIONS = (
    EXACT_SESSION_OBSERVED, PRIOR_SESSION_ONLY, PROVIDER_REJECTED, NO_HISTORY,
    TRANSPORT_FAILURE, RATE_LIMITED, UNKNOWN, NOT_ATTEMPTED,
)
KNOWN_DISPOSITIONS = frozenset({EXACT_SESSION_OBSERVED, PRIOR_SESSION_ONLY, PROVIDER_REJECTED, NO_HISTORY})
RETRYABLE = frozenset({TRANSPORT_FAILURE, RATE_LIMITED})

TERMINAL = "TERMINAL"
PENDING = "PENDING"
RETRYABLE_PENDING = "RETRYABLE_PENDING"
STOPPED_CONFLICT = "STOPPED_RAW_PAYLOAD_CONFLICT"

RUN_COMPLETE = "COMPLETE"
RUN_STOPPED_RATE_LIMIT = "STOPPED_FOR_REVIEW_CONSECUTIVE_RATE_LIMIT"
RUN_STOPPED_AUTH = "STOPPED_AUTHENTICATION_FAILURE"
RUN_STOPPED_BUDGET = "STOPPED_CALL_BUDGET_EXHAUSTED"
RUN_STOPPED_RETRY_BUDGET = "STOPPED_TRANSIENT_RETRY_BUDGET_EXHAUSTED"

# --- default request controls (tomorrow's plan) -------------------------------------------------
DEFAULT_MIN_START_INTERVAL_SECONDS = 1.0
DEFAULT_MAX_TRANSIENT_RETRIES = 85
DEFAULT_MAX_ATTEMPTS_PER_TICKER = 3
DEFAULT_STOP_AFTER_CONSECUTIVE_429 = 3
DEFAULT_RETRY_AFTER_CAP_SECONDS = 120.0
DEFAULT_FOREIGN_FLOW_CALL_BUDGET = 400
DEFAULT_FOREIGN_FLOW_MAX_PAGES = 1000
OHLC_LOOKBACK_CALENDAR_DAYS = 365  # identical to the ordinary exact-session acquisition window
ORDINARY_DAILY_COVERAGE_FLOOR = 0.20  # canonical_post_close_pipeline.MIN_EXACT_SESSION_COVERAGE_RATIO

# Path components that always denote a production/current namespace.
PRODUCTION_NAMESPACE_MARKERS = frozenset({
    "operations-review", "dashboard-runtime", "market-dashboard", "stocklookup-ai-handoffs",
    "ai-core-private", "ai-runtime", "analysis-handoff", "data-landing",
})
PRODUCTION_SENTINEL_FILES = ("vn_stock.db", "bundle_manifest.json", "LATEST.json", "daily_operation_record.json")


class RecoveryIsolationError(ValueError):
    """A recovery root or write target overlaps a production/current namespace."""


class RecoveryPlanError(ValueError):
    """The frozen plan and the requested run disagree, or an argument is invalid."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _identity(payload: Mapping[str, Any], *, prefix: str, exclude: Iterable[str] = ()) -> dict[str, Any]:
    body = {k: v for k, v in payload.items() if k not in {"artifact_sha256", "artifact_identity", *exclude}}
    digest = sha256_text(canonical_json(body))
    return {**dict(payload), "artifact_sha256": digest, "artifact_identity": f"{prefix}:{digest}"}


# =================================================================================================
# Isolation
# =================================================================================================


def _resolved(path: Path | str) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _norm(path: Path) -> Path:
    """Case/separator-normalized form for containment checks (Windows paths are case-insensitive)."""
    return Path(os.path.normcase(str(path)))


def _within(child: Path, parent: Path) -> bool:
    return _norm(child).is_relative_to(_norm(parent))


def _overlaps(a: Path, b: Path) -> bool:
    return _within(a, b) or _within(b, a)


def _inside_git_work_tree(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def default_production_roots(producer_root: Path = ROOT) -> list[Path]:
    """Every production/current root this process can name without guessing."""
    roots = [producer_root]
    configured = os.environ.get("STOCK_LOOKUP_RUNTIME_ROOT", "").strip()
    if configured:
        roots.append(Path(configured))
    # tools/run_owner_daily.py's DEFAULT_RUNTIME is ROOT.parent / "dashboard-runtime" of the main
    # checkout; a worktree's parent differs, so name both.
    roots.append(producer_root.parent / "dashboard-runtime")
    return [_resolved(p) for p in roots]


def assert_isolated_roots(
    roots: Mapping[str, Path | str | None], *, production_roots: Sequence[Path | str] | None = None,
    read_only_roots: Sequence[Path | str] = (),
) -> dict[str, Path]:
    """Fail closed unless every recovery root is explicit and outside production/current namespaces.

    Refuses: a missing/relative root; a root equal to, inside or containing the producer checkout,
    a production runtime root or a read-only source root; any root inside a git work tree (the
    producer checkout, the Dashboard and AI-handoff repositories are all git work trees); any path
    component naming a production namespace; an existing root that already holds a production
    sentinel file; and overlapping recovery roots.
    """
    production = [_resolved(p) for p in (production_roots if production_roots is not None else default_production_roots())]
    read_only = [_resolved(p) for p in read_only_roots]
    resolved: dict[str, Path] = {}
    for name, raw in roots.items():
        if raw is None or str(raw).strip() == "":
            raise RecoveryIsolationError(f"RECOVERY_ROOT_NOT_EXPLICIT:{name}")
        if not Path(raw).expanduser().is_absolute():
            raise RecoveryIsolationError(f"RECOVERY_ROOT_NOT_ABSOLUTE:{name}")
        path = _resolved(raw)
        lowered = {part.lower() for part in path.parts}
        marker = sorted(lowered & PRODUCTION_NAMESPACE_MARKERS)
        if marker:
            raise RecoveryIsolationError(f"RECOVERY_ROOT_IN_PRODUCTION_NAMESPACE:{name}:{marker[0]}")
        for prod in production:
            if _overlaps(path, prod):
                raise RecoveryIsolationError(f"RECOVERY_ROOT_OVERLAPS_PRODUCTION_ROOT:{name}:{prod}")
        for source in read_only:
            if _overlaps(path, source):
                raise RecoveryIsolationError(f"RECOVERY_ROOT_OVERLAPS_READ_ONLY_SOURCE:{name}:{source}")
        work_tree = _inside_git_work_tree(path)
        if work_tree is not None:
            raise RecoveryIsolationError(f"RECOVERY_ROOT_INSIDE_GIT_WORK_TREE:{name}:{work_tree}")
        if path.is_dir():
            for sentinel in PRODUCTION_SENTINEL_FILES:
                if (path / sentinel).exists():
                    raise RecoveryIsolationError(f"RECOVERY_ROOT_CONTAINS_PRODUCTION_SENTINEL:{name}:{sentinel}")
        resolved[name] = path
    names = sorted(resolved)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if _overlaps(resolved[a], resolved[b]):
                raise RecoveryIsolationError(f"RECOVERY_ROOTS_OVERLAP:{a}:{b}")
    return resolved


@dataclass
class RecoveryWriter:
    """The only write path recovery code uses: every target must sit inside an isolated root."""

    allowed_roots: Mapping[str, Path]
    writes: list[str] = field(default_factory=list)

    def _check(self, path: Path) -> Path:
        target = _resolved(path)
        if not any(_within(target, root) for root in self.allowed_roots.values()):
            raise RecoveryIsolationError(f"RECOVERY_WRITE_OUTSIDE_ISOLATED_ROOTS:{target}")
        return target

    def write_json_atomic(self, path: Path, payload: Any) -> str:
        target = self._check(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, target)
        self.writes.append(str(target))
        return sha256_text(text)

    def write_once(self, path: Path, text: str) -> str:
        """Write-once bytes. Identical existing bytes are a no-op; different bytes are a conflict."""
        target = self._check(path)
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if existing != text:
                raise RawPayloadConflict(str(target))
            return sha256_text(existing)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, target)
        self.writes.append(str(target))
        return sha256_text(text)

    def guard(self, path: Path) -> Path:
        """Assert a path a delegated writer (e.g. the isolated foreign-flow store) will use."""
        return self._check(path)


class RawPayloadConflict(RuntimeError):
    """The same deterministic request identity already retained different bytes."""


# =================================================================================================
# Plan
# =================================================================================================


def validate_target_session(target_session: str, *, now: datetime | None = None) -> str:
    try:
        parsed = date.fromisoformat(str(target_session))
    except ValueError as exc:
        raise RecoveryPlanError(f"TARGET_SESSION_INVALID:{target_session}") from exc
    today = (now or vn_now()).astimezone(VN_TZ).date()
    if parsed >= today:
        raise RecoveryPlanError(f"TARGET_SESSION_NOT_A_PAST_SESSION:{target_session}")
    if parsed.weekday() >= 5:
        raise RecoveryPlanError(f"TARGET_SESSION_IS_A_WEEKEND:{target_session}")
    return parsed.isoformat()


def ohlc_request_query(ticker: str, target_session: str) -> dict[str, Any]:
    """Deterministic: derived from the target session only, never from the wall clock."""
    target = date.fromisoformat(target_session)
    start = datetime.combine(target - timedelta(days=OHLC_LOOKBACK_CALENDAR_DAYS), datetime.min.time(), VN_TZ)
    end = datetime.combine(target + timedelta(days=1), datetime.min.time(), VN_TZ) - timedelta(seconds=1)
    return {"symbol": ticker, "resolution": "1D", "from": int(start.timestamp()), "to": int(end.timestamp()), "type": "STOCK"}


def ohlc_request_identity(ticker: str, target_session: str) -> str:
    return "dnse_ohlc_1d:" + sha256_text(canonical_json({
        "provider": "DNSE", "capability": "ohlc", "endpoint": "/price/ohlc", "target_session": target_session,
        "query": ohlc_request_query(ticker, target_session),
    }))[:32]


def read_candidate_source(candidate_runtime_root: Path) -> dict[str, Any]:
    """Read (never mutate) the governed candidate list and its current metadata overlay."""
    import sqlite3

    database = _resolved(candidate_runtime_root) / "vn_stock.db"
    if not database.is_file():
        raise RecoveryPlanError(f"CANDIDATE_SOURCE_DATABASE_MISSING:{database}")
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(metadata)")}
        wanted = [c for c in ("exchange", "industry") if c in columns]
        select = ", ".join(["ticker", *wanted])
        rows = connection.execute(f"SELECT {select} FROM metadata ORDER BY ticker").fetchall()
    finally:
        connection.close()
    tickers = sorted({str(row[0]).upper() for row in rows})
    overlay = {}
    for row in rows:
        values = dict(zip(wanted, row[1:]))
        overlay[str(row[0]).upper()] = {k: (None if v is None else str(v)) for k, v in values.items()}
    return {"tickers": tickers, "overlay": overlay, "database": str(database)}


def build_plan(
    *, target_session: str, candidates: Sequence[str], candidate_source: str,
    metadata_overlay: Mapping[str, Mapping[str, Any]] | None = None,
    foreign_flow_cohort: Sequence[str] = (), call_budget: int | None = None,
    max_transient_retries: int = DEFAULT_MAX_TRANSIENT_RETRIES,
    min_start_interval_seconds: float = DEFAULT_MIN_START_INTERVAL_SECONDS,
    max_attempts_per_ticker: int = DEFAULT_MAX_ATTEMPTS_PER_TICKER,
    stop_after_consecutive_429: int = DEFAULT_STOP_AFTER_CONSECUTIVE_429,
    retry_after_cap_seconds: float = DEFAULT_RETRY_AFTER_CAP_SECONDS,
    foreign_flow_call_budget: int = DEFAULT_FOREIGN_FLOW_CALL_BUDGET,
    foreign_flow_max_pages: int = DEFAULT_FOREIGN_FLOW_MAX_PAGES,
    created_at: str | None = None,
) -> dict[str, Any]:
    tickers = sorted({str(t).upper() for t in candidates})
    if not tickers:
        raise RecoveryPlanError("ACQUISITION_ATTEMPT_COHORT_EMPTY")
    if min_start_interval_seconds < DEFAULT_MIN_START_INTERVAL_SECONDS:
        raise RecoveryPlanError("MIN_START_INTERVAL_BELOW_ONE_SECOND")
    if max_transient_retries < 0 or max_attempts_per_ticker < 1 or stop_after_consecutive_429 < 1:
        raise RecoveryPlanError("REQUEST_CONTROL_INVALID")
    budget = call_budget if call_budget is not None else len(tickers) + max_transient_retries
    if budget < 1:
        raise RecoveryPlanError("CALL_BUDGET_INVALID")
    overlay = {t: dict((metadata_overlay or {}).get(t) or {}) for t in tickers}
    plan = {
        "schema_version": "1.0.0",
        "contract_version": PLAN_CONTRACT,
        **HARD_LABELS,
        "recovery_replay": {"target_session": target_session},
        "target_session": target_session,
        "created_at": created_at or vn_now().isoformat(),
        "acquisition_attempt_cohort": {
            "cohort": "ACQUISITION_ATTEMPT_COHORT",
            "source": candidate_source,
            "source_kind": "GOVERNED_RUNTIME_METADATA_TICKERS_READ_ONLY_AT_RECOVERY_TIME",
            "temporal_semantics": "CURRENT_CANDIDATE_LIST_NOT_A_TARGET_SESSION_PIT_UNIVERSE",
            "is_market_breadth_denominator": False,
            "candidate_count": len(tickers),
            "candidate_sha256": sha256_text(canonical_json(tickers)),
            "tickers": tickers,
        },
        "metadata_overlay": {
            "label": OVERLAY_LABEL,
            "fields": ["exchange", "industry"],
            "known_as_of_target_session": False,
            "records": overlay,
        },
        "request_contract": {
            "provider": "DNSE", "capability": "ohlc", "endpoint": "/price/ohlc", "resolution": "1D",
            "type": "STOCK", "lookback_calendar_days": OHLC_LOOKBACK_CALENDAR_DAYS,
            "request_identity_scheme": "sha256(provider,capability,endpoint,target_session,query)",
        },
        "controls": {
            "max_in_flight": 1,
            "min_start_interval_seconds": float(min_start_interval_seconds),
            "call_budget": int(budget),
            "max_transient_retries": int(max_transient_retries),
            "max_attempts_per_ticker": int(max_attempts_per_ticker),
            "stop_after_consecutive_429": int(stop_after_consecutive_429),
            "retry_after_honored": True,
            "retry_after_cap_seconds": float(retry_after_cap_seconds),
            "retryable_dispositions": sorted(RETRYABLE),
            "never_retried": [PROVIDER_REJECTED, NO_HISTORY, PRIOR_SESSION_ONLY, EXACT_SESSION_OBSERVED, UNKNOWN],
            "authentication_failure": "STOPS_NETWORK_ACQUISITION",
        },
        "foreign_flow": {
            "cohort": sorted({str(t).upper() for t in foreign_flow_cohort}),
            "cohort_source": "owner_research_focus.broader_watchlist",
            "capability": "foreign_trading", "call_budget": int(foreign_flow_call_budget),
            "max_pages_per_ticker": int(foreign_flow_max_pages), "limit": 100, "order": "DESC",
            "authority": "DNSE_RETROSPECTIVE_VALUE_ONLY",
        },
    }
    return _identity(plan, prefix="recovery_acquisition_plan", exclude=("created_at",))


def plan_matches(existing: Mapping[str, Any], requested: Mapping[str, Any]) -> list[str]:
    """Differences that forbid resuming ``existing`` with ``requested`` arguments."""
    diffs = []
    for key in ("target_session", "request_contract", "controls", "foreign_flow"):
        if existing.get(key) != requested.get(key):
            diffs.append(key)
    if (existing.get("acquisition_attempt_cohort") or {}).get("candidate_sha256") != (
            requested.get("acquisition_attempt_cohort") or {}).get("candidate_sha256"):
        diffs.append("acquisition_attempt_cohort")
    return diffs


# =================================================================================================
# Layout
# =================================================================================================


@dataclass(frozen=True)
class RecoveryLayout:
    output_root: Path
    runtime_root: Path
    state_root: Path

    @property
    def plan_path(self) -> Path:
        return self.state_root / "acquisition_plan.json"

    @property
    def run_state_path(self) -> Path:
        return self.state_root / "run_state.json"

    def journal_path(self, ticker: str) -> Path:
        return self.state_root / "journal" / "dnse_ohlc" / f"{ticker.upper()}.json"

    def raw_path(self, ticker: str, request_identity: str, attempt: int) -> Path:
        token = request_identity.split(":", 1)[-1]
        return self.state_root / "raw" / "dnse_ohlc" / ticker.upper() / f"{token}__attempt{attempt:02d}.json"

    def ff_journal_path(self, ticker: str) -> Path:
        return self.state_root / "journal" / "dnse_foreign_trading" / f"{ticker.upper()}.json"

    def ff_raw_path(self, ticker: str, page_index: int) -> Path:
        return self.state_root / "raw" / "dnse_foreign_trading" / ticker.upper() / f"page_{page_index:04d}.json"

    @property
    def reconstruction_path(self) -> Path:
        return self.output_root / "recovery_session_market_reconstruction.json"

    @property
    def quality_path(self) -> Path:
        return self.output_root / "recovery_acquisition_quality.json"

    @property
    def foreign_flow_path(self) -> Path:
        return self.output_root / "recovery_foreign_flow_value.json"

    def rel(self, path: Path) -> str:
        return _resolved(path).relative_to(self.state_root).as_posix()


# =================================================================================================
# Raw records + disposition
# =================================================================================================


def _row_date(epoch: Any) -> str | None:
    if isinstance(epoch, bool) or not isinstance(epoch, (int, float)):
        return None
    return datetime.fromtimestamp(epoch, tz=VN_TZ).date().isoformat()


def classify_ohlc_response(response: Mapping[str, Any], target_session: str) -> dict[str, Any]:
    """Deterministic provider-session disposition of one raw OHLC response (never imputes)."""
    error = str(response.get("error_code") or "")
    status = response.get("http_status")
    if not response.get("ok"):
        if error == "authentication_failed":
            return {"disposition": AUTH_FAILED, "reason": error}
        if error == "rate_limited" or status == 429:
            return {"disposition": RATE_LIMITED, "reason": error or "http_status_429"}
        if error.startswith("request_failed_") or (isinstance(status, int) and status >= 500):
            return {"disposition": TRANSPORT_FAILURE, "reason": error}
        if isinstance(status, int) and 400 <= status < 500:
            return {"disposition": PROVIDER_REJECTED, "reason": error}
        return {"disposition": UNKNOWN, "reason": error or "NOT_OK_UNCLASSIFIED"}
    body = response.get("body")
    if not isinstance(body, Mapping):
        return {"disposition": UNKNOWN, "reason": "BODY_NOT_OBJECT"}
    arrays = {key: body.get(key) for key in ("t", "o", "h", "l", "c", "v")}
    if any(not isinstance(value, list) for value in arrays.values()) or len({len(v) for v in arrays.values()}) != 1:
        if all(body.get(k) in (None, []) for k in arrays):
            return {"disposition": NO_HISTORY, "reason": "EMPTY_HISTORY_BODY", "session_counts": {}}
        return {"disposition": UNKNOWN, "reason": "MALFORMED_OHLC_ARRAYS"}
    sessions = [_row_date(epoch) for epoch in arrays["t"]]
    if not sessions:
        return {"disposition": NO_HISTORY, "reason": "ZERO_BARS", "session_counts": {}}
    exact = sum(1 for s in sessions if s == target_session)
    future = sum(1 for s in sessions if s is not None and s > target_session)
    prior = sum(1 for s in sessions if s is not None and s < target_session)
    counts = {"exact": exact, "prior": prior, "future": future, "undated": sum(1 for s in sessions if s is None)}
    latest_prior = max((s for s in sessions if s is not None and s < target_session), default=None)
    if exact == 1:
        return {"disposition": EXACT_SESSION_OBSERVED, "reason": None, "session_counts": counts, "latest_prior_session": latest_prior}
    if exact > 1:
        return {"disposition": UNKNOWN, "reason": "EXACT_SESSION_AMBIGUOUS", "session_counts": counts}
    if future:
        return {"disposition": UNKNOWN, "reason": "MISDATED_FUTURE_SESSION_ROWS_WITHOUT_TARGET", "session_counts": counts}
    return {"disposition": PRIOR_SESSION_ONLY, "reason": "TARGET_SESSION_BAR_ABSENT", "session_counts": counts,
            "latest_prior_session": latest_prior}


def build_raw_record(
    *, ticker: str, target_session: str, request_identity: str, attempt: int, response: Mapping[str, Any],
    started_at: str, acquired_at: str, capability: str = "ohlc",
) -> dict[str, Any]:
    body = response.get("body")
    timestamps = body.get("t") if isinstance(body, Mapping) and isinstance(body.get("t"), list) else []
    query = dict(response.get("query_sent") or {})
    record = {
        "contract_version": RAW_CONTRACT,
        "operating_mode": OPERATING_MODE,
        "provider": "DNSE",
        "capability": capability,
        "endpoint": response.get("endpoint"),
        "provider_interface_version": response.get("provider_interface_version"),
        "ticker": ticker,
        "target_session": target_session,
        "request_identity": request_identity,
        "attempt": attempt,
        "requested_range": {
            "query": query,
            "from_session": _row_date(query.get("from")),
            "to_session": _row_date(query.get("to")),
        },
        "request_started_at": started_at,
        "acquired_at": acquired_at,
        "acquisition_temporal_claim": "ACQUIRED_RETROSPECTIVELY_AT_ACQUIRED_AT_NOT_ON_TARGET_SESSION",
        "http_status": response.get("http_status"),
        "ok": bool(response.get("ok")),
        "error_code": response.get("error_code"),
        "retry_after_seconds": response.get("retry_after_seconds"),
        "elapsed_ms": response.get("elapsed_ms"),
        "body": body,
        "body_text_preview": response.get("body_text_preview"),
        "body_sha256": sha256_text(canonical_json(body)) if body is not None else None,
        "provider_session_timestamps": {
            "epoch_seconds": [t for t in timestamps if isinstance(t, (int, float)) and not isinstance(t, bool)],
            "sessions": sorted({s for s in (_row_date(t) for t in timestamps) if s}),
        },
        "price_basis": PRICE_BASIS if capability == "ohlc" else None,
    }
    return record


def raw_record_text(record: Mapping[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# =================================================================================================
# Acquisition
# =================================================================================================

Fetcher = Callable[..., Mapping[str, Any]]


@dataclass
class Pacer:
    """One request in flight; at least ``min_interval`` seconds between request STARTS."""

    min_interval: float
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    last_start: float | None = None
    slept: float = 0.0

    def wait_turn(self, extra_delay: float = 0.0) -> None:
        now = self.clock()
        due = max(
            (self.last_start + self.min_interval) if self.last_start is not None else now,
            now + max(0.0, extra_delay),
        )
        if due > now:
            self.sleep(due - now)
            self.slept += due - now
        self.last_start = self.clock()


@dataclass
class RunCounters:
    calls: int = 0
    transient_retries: int = 0
    consecutive_429: int = 0
    ff_calls: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"calls": self.calls, "transient_retries": self.transient_retries,
                "consecutive_429": self.consecutive_429, "foreign_flow_calls": self.ff_calls}


def _new_journal(ticker: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    target = plan["target_session"]
    identity = ohlc_request_identity(ticker, target)
    return {
        "contract_version": JOURNAL_CONTRACT, "operating_mode": OPERATING_MODE,
        "ticker": ticker, "target_session": target, "request_identity": identity,
        "request_range": ohlc_request_query(ticker, target),
        "attempts": [], "state": PENDING, "disposition": NOT_ATTEMPTED,
        "retry_state": {"transient_retries_used": 0, "exhausted": False},
        "conflict": None,
    }


def _verify_retained_attempt(layout: RecoveryLayout, attempt: Mapping[str, Any]) -> str | None:
    """None when the retained raw bytes still hash to the journaled SHA-256; else a conflict code."""
    raw_rel = attempt.get("raw_path")
    if not raw_rel:
        return "RAW_PATH_MISSING_FROM_JOURNAL"
    path = layout.state_root / raw_rel
    if not path.is_file():
        return "RETAINED_RAW_FILE_MISSING"
    actual = sha256_text(path.read_text(encoding="utf-8"))
    if actual != attempt.get("raw_sha256"):
        return "RETAINED_RAW_HASH_MISMATCH"
    return None


def acquire_ohlc(
    *, plan: Mapping[str, Any], layout: RecoveryLayout, writer: RecoveryWriter, fetcher: Fetcher,
    api_key: str, api_secret: str, pacer: Pacer, counters: RunCounters,
    now_iso: Callable[[], str] = lambda: vn_now().isoformat(),
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Resumable, deterministic, sequential acquisition over the frozen candidate list."""
    controls = plan["controls"]
    target = plan["target_session"]
    tickers = plan["acquisition_attempt_cohort"]["tickers"]
    stop: str | None = None
    network_calls_this_run = 0
    reused_without_network = 0

    # Resume: count every call already journaled against the hard budget.
    journals: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        existing = _load_json(layout.journal_path(ticker))
        journals[ticker] = existing if isinstance(existing, Mapping) else _new_journal(ticker, plan)
        journals[ticker] = dict(journals[ticker])
        counters.calls += sum(1 for a in journals[ticker].get("attempts", []) if a.get("network_call"))
        counters.transient_retries += int((journals[ticker].get("retry_state") or {}).get("transient_retries_used", 0))

    for ticker in tickers:
        journal = journals[ticker]
        if journal.get("request_identity") != ohlc_request_identity(ticker, target):
            journal["state"], journal["disposition"] = STOPPED_CONFLICT, UNKNOWN
            journal["conflict"] = "JOURNAL_REQUEST_IDENTITY_MISMATCH"
            writer.write_json_atomic(layout.journal_path(ticker), journal)
            continue
        if journal["state"] in (TERMINAL, STOPPED_CONFLICT):
            # Resume without a network call only when the retained bytes still validate.
            last = (journal.get("attempts") or [None])[-1]
            if journal["state"] == TERMINAL and last is not None:
                problem = _verify_retained_attempt(layout, last)
                if problem is not None:
                    journal["state"], journal["disposition"], journal["conflict"] = STOPPED_CONFLICT, UNKNOWN, problem
                    writer.write_json_atomic(layout.journal_path(ticker), journal)
                else:
                    reused_without_network += 1
            continue
        if stop is not None:
            continue
        while journal["state"] in (PENDING, RETRYABLE_PENDING):
            attempt_no = len(journal["attempts"]) + 1
            raw_path = layout.raw_path(ticker, journal["request_identity"], attempt_no)
            # Crash between raw write and journal write: the orphan raw file is the attempt.
            orphan = _load_json(raw_path) if raw_path.is_file() else None
            from_orphan = isinstance(orphan, Mapping) and orphan.get("request_identity") == journal["request_identity"]
            if from_orphan:
                text = raw_path.read_text(encoding="utf-8")
                response = {"ok": orphan.get("ok"), "http_status": orphan.get("http_status"),
                            "error_code": orphan.get("error_code"), "body": orphan.get("body"),
                            "retry_after_seconds": orphan.get("retry_after_seconds")}
                raw_sha = sha256_text(text)
                # The crashed process really spent this call; count it against the hard budget.
                network_call = True
                counters.calls += 1
                acquired_at = orphan.get("acquired_at")
            else:
                if counters.calls >= controls["call_budget"]:
                    stop = RUN_STOPPED_BUDGET
                    break
                retry_after = 0.0
                if journal["attempts"]:
                    previous = journal["attempts"][-1]
                    if previous.get("disposition") == RATE_LIMITED and previous.get("retry_after_seconds") is not None:
                        retry_after = min(float(previous["retry_after_seconds"]), controls["retry_after_cap_seconds"])
                pacer.wait_turn(retry_after)
                started_at = now_iso()
                query = ohlc_request_query(ticker, target)
                response = dict(fetcher("ohlc", api_key=api_key, api_secret=api_secret, symbol=None, query=query))
                response.setdefault("query_sent", query)
                response.setdefault("endpoint", "/price/ohlc")
                counters.calls += 1
                network_calls_this_run += 1
                network_call = True
                acquired_at = now_iso()
                record = build_raw_record(
                    ticker=ticker, target_session=target, request_identity=journal["request_identity"],
                    attempt=attempt_no, response=response, started_at=started_at, acquired_at=acquired_at,
                )
                try:
                    raw_sha = writer.write_once(raw_path, raw_record_text(record))
                except RawPayloadConflict:
                    journal["state"], journal["disposition"], journal["conflict"] = (
                        STOPPED_CONFLICT, UNKNOWN, "CONFLICTING_RETAINED_RAW_PAYLOAD")
                    break
            verdict = classify_ohlc_response(response, target)
            disposition = verdict["disposition"]
            journal["attempts"].append({
                "attempt": attempt_no, "network_call": network_call, "acquired_at": acquired_at,
                "recovered_from_orphan_raw": from_orphan,
                "http_status": response.get("http_status"), "error_code": response.get("error_code"),
                "retry_after_seconds": response.get("retry_after_seconds"),
                "raw_path": layout.rel(raw_path), "raw_sha256": raw_sha,
                "disposition": disposition, "reason": verdict.get("reason"),
                "session_counts": verdict.get("session_counts"),
            })
            if disposition == RATE_LIMITED:
                counters.consecutive_429 += 1
            elif network_call:
                counters.consecutive_429 = 0
            if disposition == AUTH_FAILED:
                journal["state"], journal["disposition"] = PENDING, NOT_ATTEMPTED
                stop = RUN_STOPPED_AUTH
                break
            if disposition in RETRYABLE:
                can_retry = (
                    attempt_no < controls["max_attempts_per_ticker"]
                    and counters.transient_retries < controls["max_transient_retries"]
                )
                if counters.consecutive_429 >= controls["stop_after_consecutive_429"]:
                    journal["state"], journal["disposition"] = RETRYABLE_PENDING, disposition
                    stop = RUN_STOPPED_RATE_LIMIT
                    break
                if can_retry:
                    counters.transient_retries += 1
                    journal["retry_state"]["transient_retries_used"] += 1
                    journal["state"], journal["disposition"] = RETRYABLE_PENDING, disposition
                    writer.write_json_atomic(layout.journal_path(ticker), journal)
                    continue
                journal["retry_state"]["exhausted"] = True
                journal["state"], journal["disposition"] = TERMINAL, disposition
                if counters.transient_retries >= controls["max_transient_retries"] and attempt_no < controls["max_attempts_per_ticker"]:
                    journal["retry_state"]["reason"] = RUN_STOPPED_RETRY_BUDGET
                break
            journal["state"], journal["disposition"] = TERMINAL, disposition
            journal["provider_session_disposition"] = verdict
            break
        writer.write_json_atomic(layout.journal_path(ticker), journal)
        if progress:
            progress(f"{ticker}:{journal['disposition']}:{journal['state']}")

    states = [journals[t]["state"] for t in tickers]
    if stop is None and all(s in (TERMINAL, STOPPED_CONFLICT) for s in states):
        status = RUN_COMPLETE
    else:
        status = stop or "INCOMPLETE"
    return {
        "status": status, "network_calls_this_run": network_calls_this_run,
        "reused_without_network": reused_without_network, "counters": counters.as_dict(),
        "journals": journals,
    }


# =================================================================================================
# Foreign-flow recovery (isolated store only)
# =================================================================================================


def _ff_query(ticker: str, target_session: str, cursor: str | None) -> dict[str, Any]:
    from dnse_foreign_trading_raw import request_query

    return request_query(ticker, target_session, cursor=cursor)


def acquire_foreign_flow(
    *, plan: Mapping[str, Any], layout: RecoveryLayout, writer: RecoveryWriter, fetcher: Fetcher,
    api_key: str, api_secret: str, pacer: Pacer, counters: RunCounters,
    now_iso: Callable[[], str] = lambda: vn_now().isoformat(),
) -> dict[str, Any]:
    """Complete each cursor chain to its terminal page; only a verified complete chain normalizes.

    Raw pages are retained and hashed under the state root. The normalized VALUE observation is
    written only into the ISOLATED recovery runtime root's foreign-flow store -- never the
    production current foreign-flow store.
    """
    ff = plan["foreign_flow"]
    target = plan["target_session"]
    stop: str | None = None
    chains: dict[str, dict[str, Any]] = {}
    for ticker in ff["cohort"]:
        existing = _load_json(layout.ff_journal_path(ticker))
        chain = dict(existing) if isinstance(existing, Mapping) else {
            "contract_version": JOURNAL_CONTRACT, "operating_mode": OPERATING_MODE, "ticker": ticker,
            "target_session": target, "capability": "foreign_trading", "pages": [], "state": PENDING,
            "terminal_cursor_reached": False, "failure": None, "attempts": 0,
        }
        counters.ff_calls += int(chain.get("attempts", 0))
        chains[ticker] = chain
    for ticker, chain in chains.items():
        if chain["state"] in (TERMINAL, STOPPED_CONFLICT, "FAILED"):
            # Re-verify retained page bytes on resume.
            for page in chain["pages"]:
                problem = _verify_retained_attempt(layout, page)
                if problem:
                    chain["state"], chain["failure"] = STOPPED_CONFLICT, problem
                    writer.write_json_atomic(layout.ff_journal_path(ticker), chain)
                    break
            continue
        if stop is not None:
            continue
        transient_attempts = 0
        pending_delay = 0.0
        while True:
            pages = chain["pages"]
            if pages and not pages[-1].get("next_cursor"):
                chain["state"], chain["terminal_cursor_reached"] = TERMINAL, True
                break
            if len(pages) >= ff["max_pages_per_ticker"]:
                chain["state"], chain["failure"] = "FAILED", "NON_TERMINAL_PAGE_LIMIT_REACHED"
                break
            if counters.ff_calls >= ff["call_budget"]:
                stop = RUN_STOPPED_BUDGET
                break
            cursor = pages[-1]["next_cursor"] if pages else None
            page_index = len(pages)
            raw_path = layout.ff_raw_path(ticker, page_index)
            orphan = _load_json(raw_path) if raw_path.is_file() else None
            if isinstance(orphan, Mapping) and orphan.get("page_cursor") == cursor and orphan.get("ok"):
                response = {"ok": True, "http_status": orphan.get("http_status"), "body": orphan.get("body"),
                            "endpoint": orphan.get("endpoint"), "query_sent": (orphan.get("requested_range") or {}).get("query")}
                raw_sha = sha256_text(raw_path.read_text(encoding="utf-8"))
                acquired_at = orphan.get("acquired_at")
            else:
                pacer.wait_turn(pending_delay)
                pending_delay = 0.0
                started_at = now_iso()
                query = _ff_query(ticker, target, cursor)
                response = dict(fetcher("foreign_trading", api_key=api_key, api_secret=api_secret, symbol=ticker, query=query))
                response.setdefault("query_sent", query)
                response.setdefault("endpoint", f"/price/{ticker}/foreign-trading")
                counters.ff_calls += 1
                chain["attempts"] = int(chain.get("attempts", 0)) + 1
                acquired_at = now_iso()
                verdict = classify_ohlc_response(response, target) if not response.get("ok") else {"disposition": None}
                if verdict["disposition"] == AUTH_FAILED:
                    stop = RUN_STOPPED_AUTH
                    break
                if verdict["disposition"] == RATE_LIMITED:
                    counters.consecutive_429 += 1
                    if counters.consecutive_429 >= plan["controls"]["stop_after_consecutive_429"]:
                        stop = RUN_STOPPED_RATE_LIMIT
                        break
                    ra = response.get("retry_after_seconds")
                    pending_delay = min(float(ra), plan["controls"]["retry_after_cap_seconds"]) if ra is not None else 0.0
                    continue
                counters.consecutive_429 = 0
                if verdict["disposition"] == TRANSPORT_FAILURE:
                    transient_attempts += 1
                    if transient_attempts < plan["controls"]["max_attempts_per_ticker"]:
                        continue
                    chain["state"], chain["failure"] = "FAILED", "TRANSPORT_FAILURE_RETRIES_EXHAUSTED"
                    break
                if verdict["disposition"] is not None:
                    chain["state"], chain["failure"] = "FAILED", f"{verdict['disposition']}:{verdict.get('reason')}"
                    break
                record = build_raw_record(
                    ticker=ticker, target_session=target, request_identity=f"dnse_foreign_trading:{ticker}:{target}:page{page_index}",
                    attempt=1, response=response, started_at=started_at, acquired_at=acquired_at, capability="foreign_trading",
                )
                record["page_index"], record["page_cursor"] = page_index, cursor
                try:
                    raw_sha = writer.write_once(raw_path, raw_record_text(record))
                except RawPayloadConflict:
                    chain["state"], chain["failure"] = STOPPED_CONFLICT, "CONFLICTING_RETAINED_RAW_PAGE"
                    break
            body = response.get("body") if isinstance(response.get("body"), Mapping) else {}
            next_cursor = body.get("nextPageToken")
            pages.append({
                "page_index": page_index, "page_cursor": cursor, "raw_path": layout.rel(raw_path),
                "raw_sha256": raw_sha, "acquired_at": acquired_at,
                "record_count": len(body.get("foreigners") or []) if isinstance(body.get("foreigners"), list) else None,
                "next_cursor": next_cursor if isinstance(next_cursor, str) and next_cursor else None,
            })
            writer.write_json_atomic(layout.ff_journal_path(ticker), chain)
        writer.write_json_atomic(layout.ff_journal_path(ticker), chain)
    return {"status": stop or ("COMPLETE" if all(c["state"] in (TERMINAL, "FAILED", STOPPED_CONFLICT) for c in chains.values()) else "INCOMPLETE"),
            "chains": chains, "counters": counters.as_dict()}


def normalize_foreign_flow(
    *, plan: Mapping[str, Any], layout: RecoveryLayout, writer: RecoveryWriter,
) -> dict[str, Any]:
    """VALUE-only normalization of every COMPLETE chain into the isolated recovery store."""
    from current_foreign_flow_retention import normalize_exact_raw_sequence, write_exact_value_observation
    from dnse_foreign_flow_store import observation_path

    target = plan["target_session"]
    records: dict[str, Any] = {}
    for ticker in plan["foreign_flow"]["cohort"]:
        chain = _load_json(layout.ff_journal_path(ticker))
        if not isinstance(chain, Mapping):
            records[ticker] = {"status": "NOT_ATTEMPTED", "value": None}
            continue
        if chain.get("state") != TERMINAL or not chain.get("terminal_cursor_reached"):
            records[ticker] = {"status": "NON_TERMINAL_CHAIN_NOT_NORMALIZED", "chain_state": chain.get("state"),
                               "failure": chain.get("failure"), "pages": len(chain.get("pages") or []), "value": None}
            continue
        pages = []
        problem = None
        for page in chain["pages"]:
            problem = _verify_retained_attempt(layout, page)
            if problem:
                break
            raw = _load_json(layout.state_root / page["raw_path"])
            pages.append({
                "instrument": ticker, "source_event_time": target, "raw_payload": raw.get("body"),
                "provenance": {"endpoint": raw.get("endpoint"), "page_index": page["page_index"],
                               "page_cursor": page["page_cursor"],
                               "request_parameters": (raw.get("requested_range") or {}).get("query")},
            })
        if problem:
            records[ticker] = {"status": "RAW_PAGE_VERIFICATION_FAILED", "failure": problem, "value": None}
            continue
        try:
            observation = normalize_exact_raw_sequence(ticker=ticker, reference_session=target, pages=pages)
        except ValueError as exc:
            records[ticker] = {"status": "CHAIN_NOT_NORMALIZABLE", "failure": str(exc), "value": None}
            continue
        writer.guard(observation_path(layout.runtime_root, ticker))
        write_exact_value_observation(layout.runtime_root, ticker, observation)
        records[ticker] = {
            "status": "COMPLETE_CHAIN_VALUE_NORMALIZED",
            "session_date": observation.get("session_date"),
            "foreign_buy_value": observation.get("foreign_buy_value"),
            "foreign_sell_value": observation.get("foreign_sell_value"),
            "foreign_net_value": observation.get("foreign_net_value"),
            "value_unit": observation.get("value_unit"),
            "pages": len(chain["pages"]),
            "raw_page_sha256": [p["raw_sha256"] for p in chain["pages"]],
            "isolated_store": "RECOVERY_RUNTIME_ROOT_ONLY",
        }
    payload = {
        "schema_version": "1.0.0", "contract_version": FOREIGN_FLOW_CONTRACT, **HARD_LABELS,
        "recovery_replay": {"target_session": target},
        "target_session": target,
        "temporal_claim": "RETROSPECTIVE_VALUE_ONLY",
        "authority": "DNSE_RETROSPECTIVE_VALUE_ONLY",
        "volume_authority": "ABSOLUTE_UNIT_AND_COMPOSITION_UNQUALIFIED_NOT_EMITTED",
        "liquidity_sizing_implication": "NONE",
        "production_current_foreign_flow_store": "NOT_WRITTEN",
        "cohort": list(plan["foreign_flow"]["cohort"]),
        "complete_count": sum(1 for r in records.values() if r["status"] == "COMPLETE_CHAIN_VALUE_NORMALIZED"),
        "records": records,
    }
    return _identity(payload, prefix="recovery_foreign_flow_value")


# =================================================================================================
# Reconstruction (descriptive only)
# =================================================================================================


def _parse_rows(raw: Mapping[str, Any], target_session: str) -> list[dict[str, Any]]:
    from mva_exact_session_snapshot import _observation_rows

    body = raw.get("body")
    if not isinstance(body, Mapping):
        return []
    rows, _problem = _observation_rows(
        body, requested_session=target_session, query=(raw.get("requested_range") or {}).get("query") or {},
        retrieved_at=str(raw.get("acquired_at")),
    )
    for row in rows:
        row["price_basis"] = PRICE_BASIS
    return rows


def _ticker_descriptors(rows: list[dict[str, Any]], target: str) -> dict[str, Any]:
    import session_bar_integrity
    import tactical_reference_window as window

    integrity = session_bar_integrity.resolve_session_bars(rows, as_of_session=target)
    if integrity["status"] == session_bar_integrity.CONFLICTING_DUPLICATE_REFUSED:
        return {"status": "REFUSED_CONFLICTING_DUPLICATE_SESSION_BAR",
                "integrity": session_bar_integrity.integrity_summary(integrity)}
    clean = sorted((r for r in integrity["observations"] if r["session"] <= target), key=lambda r: r["session"])
    today = [r for r in clean if r["session"] == target]
    if len(today) != 1:
        return {"status": "EXACT_SESSION_BAR_UNAVAILABLE"}
    bar = today[0]
    prior = [r for r in clean if r["session"] < target]
    prev = prior[-1] if prior else None
    out: dict[str, Any] = {
        "status": "DESCRIBED",
        "session_bar": {k: bar.get(k) for k in ("open", "high", "low", "close", "volume")},
        "price_unit": bar.get("price_unit"),
        "price_basis": PRICE_BASIS,
        "prior_session": prev["session"] if prev else None,
        "session_return": (bar["close"] / prev["close"] - 1) if prev and prev.get("close") else None,
    }
    volumes = [r["volume"] for r in prior[-20:] if isinstance(r.get("volume"), (int, float))]
    mean_vol = statistics.mean(volumes) if len(volumes) == 20 else None
    out["relative_volume_20"] = {
        "value": (bar["volume"] / mean_vol) if mean_vol else None,
        "semantics": "SAME_PROVIDER_DIMENSIONLESS_RATIO_NO_ABSOLUTE_LIQUIDITY_AUTHORITY",
        "status": "AVAILABLE" if mean_vol else "INSUFFICIENT_PRIOR_20_SESSIONS",
    }
    reference = window.reference_values(clean, as_of_session=target)
    technical = {
        "status": reference["status"] if reference.get("last_session") == target else "MISSING",
        "ma_20": reference.get("ma_20") if reference.get("last_session") == target else None,
        "momentum_20d": reference.get("momentum_20d") if reference.get("last_session") == target else None,
        "blockers": reference.get("blockers"),
        "window_first_session": reference.get("first_session"),
        "convention": reference.get("convention"),
    }
    if technical["ma_20"] is not None:
        technical["close_vs_ma20"] = "ABOVE" if bar["close"] > technical["ma_20"] else ("BELOW" if bar["close"] < technical["ma_20"] else "AT")
    out["technical_context_latest_20"] = technical
    if integrity["status"] != session_bar_integrity.UNIQUE:
        out["integrity"] = session_bar_integrity.integrity_summary(integrity)
    return out


def _distribution(tickers: Iterable[str], overlay: Mapping[str, Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ticker in tickers:
        value = (overlay.get(ticker) or {}).get(key) or "UNLABELLED"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def build_quality_report(plan: Mapping[str, Any], journals: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    tickers = plan["acquisition_attempt_cohort"]["tickers"]
    overlay = (plan.get("metadata_overlay") or {}).get("records") or {}
    by: dict[str, list[str]] = {d: [] for d in DISPOSITIONS}
    conflicts = []
    for ticker in tickers:
        journal = journals.get(ticker) or {}
        disposition = journal.get("disposition") or NOT_ATTEMPTED
        if journal.get("state") == STOPPED_CONFLICT:
            conflicts.append({"ticker": ticker, "conflict": journal.get("conflict")})
            disposition = UNKNOWN
        by.setdefault(disposition, []).append(ticker)
    attempted = [t for t in tickers if (journals.get(t) or {}).get("attempts")]
    exact = by[EXACT_SESSION_OBSERVED]
    missing = [t for t in tickers if t not in set(exact)]
    known = sum(len(by[d]) for d in KNOWN_DISPOSITIONS)
    payload = {
        "schema_version": "1.0.0", "contract_version": QUALITY_CONTRACT, **HARD_LABELS,
        "recovery_replay": {"target_session": plan["target_session"]},
        "target_session": plan["target_session"],
        "plan_identity": plan.get("artifact_identity"),
        "candidate_count": len(tickers),
        "attempted_count": len(attempted),
        "exact_session_count": len(exact),
        "exact_over_attempted_ratio": round(len(exact) / len(attempted), 6) if attempted else None,
        "provider_rejected_count": len(by[PROVIDER_REJECTED]),
        "prior_session_only_count": len(by[PRIOR_SESSION_ONLY]),
        "no_history_count": len(by[NO_HISTORY]),
        "transport_failure_count": len(by[TRANSPORT_FAILURE]),
        "rate_limit_count": len(by[RATE_LIMITED]),
        "unknown_count": len(by[UNKNOWN]),
        "not_attempted_count": len(by[NOT_ATTEMPTED]),
        "raw_payload_conflicts": conflicts,
        "known_disposition_count": known,
        "unknown_or_unresolved_disposition_count": len(tickers) - known,
        "disposition_tickers": {k: v for k, v in by.items()},
        "exchange_distribution": {
            "label": OVERLAY_LABEL, "known_as_of_target_session": False,
            "observed": _distribution(exact, overlay, "exchange"),
            "missing": _distribution(missing, overlay, "exchange"),
        },
        "industry_distribution": {
            "label": OVERLAY_LABEL, "known_as_of_target_session": False,
            "observed": _distribution(exact, overlay, "industry"),
            "missing": _distribution(missing, overlay, "industry"),
        },
        "ordinary_daily_safety_floor_comparison": {
            "floor": ORDINARY_DAILY_COVERAGE_FLOOR,
            "exact_over_candidates": round(len(exact) / len(tickers), 6) if tickers else None,
            "at_or_above_floor": (len(exact) / len(tickers) >= ORDINARY_DAILY_COVERAGE_FLOOR) if tickers else False,
            "semantics": "ORDINARY_DAILY_ACQUISITION_SAFETY_FLOOR_COMPARISON_ONLY_NOT_PROOF_OF_MARKET_COMPLETENESS",
        },
        "healthy_market_threshold": "NONE_DEFINED",
    }
    return _identity(payload, prefix="recovery_acquisition_quality")


def build_reconstruction(
    *, plan: Mapping[str, Any], layout: RecoveryLayout, journals: Mapping[str, Mapping[str, Any]],
    quality: Mapping[str, Any], foreign_flow: Mapping[str, Any] | None, acquisition_status: str,
) -> dict[str, Any]:
    target = plan["target_session"]
    overlay = (plan.get("metadata_overlay") or {}).get("records") or {}
    exact_tickers = sorted(t for t, j in journals.items() if j.get("state") == TERMINAL and j.get("disposition") == EXACT_SESSION_OBSERVED)
    per_ticker: dict[str, Any] = {}
    acquired_times = []
    exclusions: dict[str, str] = {}
    for ticker in exact_tickers:
        last = journals[ticker]["attempts"][-1]
        problem = _verify_retained_attempt(layout, last)
        if problem:
            exclusions[ticker] = problem
            continue
        raw = _load_json(layout.state_root / last["raw_path"])
        acquired_times.append(str(raw.get("acquired_at")))
        described = _ticker_descriptors(_parse_rows(raw, target), target)
        described["raw_sha256"] = last["raw_sha256"]
        described["acquired_at"] = raw.get("acquired_at")
        per_ticker[ticker] = described
    descriptive = sorted(t for t, d in per_ticker.items() if d.get("status") == "DESCRIBED" and d.get("session_return") is not None)
    for ticker, d in per_ticker.items():
        if ticker not in descriptive:
            exclusions[ticker] = d.get("status") if d.get("status") != "DESCRIBED" else "NO_PRIOR_SESSION_CLOSE"
    for ticker in plan["acquisition_attempt_cohort"]["tickers"]:
        if ticker not in per_ticker and ticker not in exclusions:
            exclusions[ticker] = "NOT_EXACT_SESSION_OBSERVED:" + str((journals.get(ticker) or {}).get("disposition") or NOT_ATTEMPTED)
    returns = [per_ticker[t]["session_return"] for t in descriptive]
    adv = sum(1 for r in returns if r > 0)
    dec = sum(1 for r in returns if r < 0)
    ma_known = [t for t in descriptive if per_ticker[t]["technical_context_latest_20"].get("close_vs_ma20")]
    above = sum(1 for t in ma_known if per_ticker[t]["technical_context_latest_20"]["close_vs_ma20"] == "ABOVE")
    sector: dict[str, list[float]] = {}
    for t in descriptive:
        sector.setdefault((overlay.get(t) or {}).get("industry") or "UNLABELLED", []).append(per_ticker[t]["session_return"])
    sector_descriptors = {
        name: {"count": len(vals), "median_session_return": statistics.median(vals),
               "advancers": sum(1 for v in vals if v > 0), "decliners": sum(1 for v in vals if v < 0)}
        for name, vals in sorted(sector.items())
    }
    flow_price = None
    if foreign_flow is not None:
        observer = {}
        for ticker, record in (foreign_flow.get("records") or {}).items():
            desc = per_ticker.get(ticker) or {}
            net = record.get("foreign_net_value")
            ret = desc.get("session_return")
            if record.get("status") != "COMPLETE_CHAIN_VALUE_NORMALIZED" or net is None or ret is None:
                observer[ticker] = {"status": "NOT_EVALUABLE"}
                continue
            flow_sign = "NET_BUY" if net > 0 else ("NET_SELL" if net < 0 else "FLAT")
            price_sign = "UP" if ret > 0 else ("DOWN" if ret < 0 else "FLAT")
            observer[ticker] = {"status": "DESCRIBED", "flow_sign": flow_sign, "price_sign": price_sign,
                                "same_direction": (flow_sign, price_sign) in {("NET_BUY", "UP"), ("NET_SELL", "DOWN")}}
        flow_price = {
            "semantics": "RETROSPECTIVE_DESCRIPTIVE_OBSERVER_ONLY_ASSOCIATION_NOT_CAUSATION",
            "is_actionable": False, "records": observer,
        }
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": RECONSTRUCTION_CONTRACT,
        **HARD_LABELS,
        "recovery_replay": {"target_session": target, "plan_identity": plan.get("artifact_identity"),
                            "acquisition_status": acquisition_status},
        "target_session": target,
        "not_built_forbidden_in_recovery_replay": list(FORBIDDEN_PRODUCTS),
        "decision_semantics": "NO_DECISION_PRODUCT_NOT_WHAT_STOCK_LOOKUP_WOULD_HAVE_DECIDED_ON_TARGET_SESSION",
        "acquisition_time_semantics": {
            "acquired_retrospectively": True,
            "acquired_at_min": min(acquired_times) if acquired_times else None,
            "acquired_at_max": max(acquired_times) if acquired_times else None,
            "claims_acquisition_on_target_session": False,
        },
        "price_basis": PRICE_BASIS,
        "authority_boundary": dict(AUTHORITY_BOUNDARY),
        "cohorts": {
            "ACQUISITION_ATTEMPT_COHORT": {"count": quality["candidate_count"], "is_market_denominator": False,
                                            "source_kind": plan["acquisition_attempt_cohort"]["source_kind"]},
            "EXACT_SESSION_OBSERVED_COHORT": {"count": len(exact_tickers)},
            "DESCRIPTIVE_ANALYSIS_COHORT": {
                "count": len(descriptive),
                "definition": "EXACT_SESSION_OBSERVED_WITH_RETAINED_PRIOR_CLOSE_AND_CLEAN_SESSION_BARS",
            },
            "QUALIFIED_ELIGIBILITY_COHORT": "NOT_ESTABLISHED_ACTIVE_UNIVERSE_UNKNOWN_NOT_PROMOTED",
            "denominator_exclusions": dict(sorted(exclusions.items())),
            "imputation": "NONE",
        },
        "quality_identity": quality.get("artifact_identity"),
        "descriptive_breadth": {
            "cohort": "DESCRIPTIVE_ANALYSIS_COHORT", "denominator": len(descriptive),
            "advancers": adv, "decliners": dec, "unchanged": len(returns) - adv - dec,
            "median_session_return": statistics.median(returns) if returns else None,
            "close_above_ma20_count": above, "ma20_evaluable_count": len(ma_known),
            "semantics": "DESCRIPTIVE_OVER_REPORTED_OBSERVED_COHORT_NOT_OFFICIAL_MARKET_BREADTH",
        },
        "sector_descriptors": {"label": OVERLAY_LABEL, "known_as_of_target_session": False, "by_industry": sector_descriptors},
        "per_ticker": per_ticker,
        "foreign_flow": None if foreign_flow is None else {
            "artifact_identity": foreign_flow.get("artifact_identity"),
            "temporal_claim": "RETROSPECTIVE_VALUE_ONLY", "authority": "DNSE_RETROSPECTIVE_VALUE_ONLY",
            "is_actionable": False, "complete_count": foreign_flow.get("complete_count"),
        },
        "flow_price_observer": flow_price,
        "overlays": {
            "label_for_any_non_session_locked_artifact": OVERLAY_LABEL,
            "metadata_exchange_industry": {"label": OVERLAY_LABEL, "known_as_of_target_session": False},
            "official_universe": {"status": "NOT_ATTACHED",
                                  "note": "RETAINED_OFFICIAL_UNIVERSE_ARTIFACTS_ARE_NOT_TARGET_SESSION_PIT_SNAPSHOTS"},
            "fundamental_valuation_catalyst_financial": {"status": "NOT_ATTACHED_WITHHELD_TEMPORAL_INPUTS_UNPROVEN"},
            "known_as_of_target_session_claims": [],
        },
    }
    assert_no_forbidden_products(artifact)
    return _identity(artifact, prefix="recovery_session_market_reconstruction")


def assert_no_forbidden_products(payload: Any, path: str = "$") -> None:
    """Refuse any decision/publication product or Friday-knowledge claim inside a recovery artifact."""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            text = str(key)
            if text in FORBIDDEN_OUTPUT_KEYS or text.startswith("KNOWN_AS_OF_"):
                raise RecoveryPlanError(f"RECOVERY_ARTIFACT_CONTAINS_FORBIDDEN_PRODUCT:{path}.{text}")
            assert_no_forbidden_products(value, f"{path}.{text}")
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            if isinstance(item, str) and item.startswith("KNOWN_AS_OF_"):
                raise RecoveryPlanError(f"RECOVERY_ARTIFACT_CLAIMS_TARGET_SESSION_KNOWLEDGE:{path}[{index}]")
            assert_no_forbidden_products(item, f"{path}[{index}]")
    elif isinstance(payload, str) and payload.startswith("KNOWN_AS_OF_"):
        raise RecoveryPlanError(f"RECOVERY_ARTIFACT_CLAIMS_TARGET_SESSION_KNOWLEDGE:{path}")


def classify_overlay(artifact: Mapping[str, Any], *, target_session: str) -> dict[str, Any]:
    """Temporal label for any retained/current artifact a later research layer may attach.

    Only an artifact whose own contract carries an explicit, session-locked knowledge time equal to
    ``target_session`` (``knowledge_time_session`` + ``knowledge_time_proven is True``) could ever
    be anything but an overlay -- and even then this function reports it; it never emits a
    ``KNOWN_AS_OF_*`` label itself. Everything else, including a retained official-universe artifact
    observed on another date, is ``CURRENT_RESEARCH_OVERLAY_ACQUIRED_OR_RETAINED_LATER``.
    """
    proven = artifact.get("knowledge_time_proven") is True and artifact.get("knowledge_time_session") == target_session
    return {
        "label": "SESSION_LOCKED_KNOWLEDGE_TIME_PROVEN_BY_OWN_CONTRACT" if proven else OVERLAY_LABEL,
        "known_as_of_target_session": bool(proven),
        "artifact_identity": artifact.get("artifact_identity"),
        "observed_at": artifact.get("observed_at") or artifact.get("official_snapshot_observed_at"),
        "active_universe_authority": "UNKNOWN_NOT_PROMOTED",
    }
