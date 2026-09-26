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
PARTIAL_DIAGNOSTIC_CONTRACT = "recovery_partial_diagnostic/v1"
PLAN_CONTRACT = "recovery_acquisition_plan/v1"
JOURNAL_CONTRACT = "recovery_acquisition_journal/v1"
RAW_CONTRACT = "recovery_raw_provider_response/v2"  # envelope contract; exact bytes live beside it
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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

    @staticmethod
    def _durable_replace(tmp: Path, target: Path, data: bytes) -> None:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)

    def write_json_atomic(self, path: Path, payload: Any) -> str:
        """Mutable derived state (journals, run state, reports) -- never raw evidence."""
        target = self._check(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        self._durable_replace(target.with_name(target.name + ".tmp"), target, data)
        self.writes.append(str(target))
        return sha256_bytes(data)

    def write_bytes_once(self, path: Path, data: bytes) -> tuple[str, int]:
        """Write-once exact bytes, fsynced, then re-read and verified (length + SHA-256).

        Identical existing bytes are a no-op; different existing bytes are a conflict and are never
        overwritten. Returns ``(sha256, length)`` of the bytes as retained on disk.
        """
        target = self._check(path)
        expected_sha, expected_len = sha256_bytes(data), len(data)
        if target.exists():
            existing = target.read_bytes()
            if existing != data:
                raise RawPayloadConflict(str(target))
            return expected_sha, expected_len
        target.parent.mkdir(parents=True, exist_ok=True)
        self._durable_replace(target.with_name(target.name + ".tmp"), target, data)
        retained = target.read_bytes()
        if len(retained) != expected_len or sha256_bytes(retained) != expected_sha:
            raise RawRetentionError("RETAINED_BYTES_VERIFICATION_FAILED:" + str(target))
        self.writes.append(str(target))
        return expected_sha, expected_len

    def retire(self, path: Path, suffix: str) -> Path | None:
        """Move a derived output aside (never raw evidence) so it cannot be read as current."""
        target = self._check(path)
        if not target.exists():
            return None
        destination = self._check(target.with_name(f"{target.name}.retired-{suffix}"))
        os.replace(target, destination)
        self.writes.append(str(destination))
        return destination

    def guard(self, path: Path) -> Path:
        """Assert a path a delegated writer (e.g. the isolated foreign-flow store) will use."""
        return self._check(path)


class RawPayloadConflict(RuntimeError):
    """The same deterministic request identity already retained different bytes."""


class RawRetentionError(RuntimeError):
    """Exact raw bytes could not be retained/verified (or the fetch adapter did not supply them)."""


class RawIntegrityError(ValueError):
    """Retained raw evidence failed an invariant; it is never adopted as evidence."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


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

    def raw_stem(self, ticker: str, request_identity: str, attempt: int) -> Path:
        token = request_identity.split(":", 1)[-1]
        return self.state_root / "raw" / "dnse_ohlc" / ticker.upper() / f"{token}__attempt{attempt:02d}"

    def ff_journal_path(self, ticker: str) -> Path:
        return self.state_root / "journal" / "dnse_foreign_trading" / f"{ticker.upper()}.json"

    def ff_raw_stem(self, ticker: str, page_index: int) -> Path:
        return self.state_root / "raw" / "dnse_foreign_trading" / ticker.upper() / f"page_{page_index:04d}"

    @property
    def reconstruction_path(self) -> Path:
        """Written ONLY for an overall COMPLETE acquisition (a completion claim)."""
        return self.output_root / "recovery_session_market_reconstruction.json"

    @property
    def partial_diagnostic_path(self) -> Path:
        """Written for every non-COMPLETE run; never a completed reconstruction."""
        return self.output_root / "recovery_partial_diagnostic.json"

    @property
    def quality_path(self) -> Path:
        return self.output_root / "recovery_acquisition_quality.json"

    @property
    def foreign_flow_path(self) -> Path:
        return self.output_root / "recovery_foreign_flow_value.json"

    def rel(self, path: Path) -> str:
        return _resolved(path).relative_to(self.state_root).as_posix()


def body_path(stem: Path) -> Path:
    return stem.with_name(stem.name + ".body")


def envelope_path(stem: Path) -> Path:
    return stem.with_name(stem.name + ".envelope.json")


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


RAW_ENVELOPE_CONTRACT = "recovery_raw_provider_response/v2"
RAW_COMPLETION_MARKER = "RAW_BODY_BYTES_DURABLY_WRITTEN_AND_VERIFIED"
CHAIN_CONTRACT = "recovery_foreign_flow_chain/v1"


def build_envelope(
    *, capability: str, ticker: str, target_session: str, request_identity: str, attempt: int,
    response: Mapping[str, Any], query: Mapping[str, Any], endpoint: str, started_at: str, acquired_at: str,
    body_file: str | None, body_sha256: str | None, body_length: int | None,
    page_index: int | None = None, page_cursor: str | None = None,
) -> dict[str, Any]:
    """Metadata envelope for one retained response. It never contains or regenerates the body: the
    exact provider bytes live in their own ``.body`` file, identified by SHA-256 and length."""
    return {
        "contract_version": RAW_ENVELOPE_CONTRACT,
        "operating_mode": OPERATING_MODE,
        "provider": "DNSE",
        "capability": capability,
        "endpoint": endpoint,
        "provider_interface_version": response.get("provider_interface_version"),
        "ticker": ticker,
        "target_session": target_session,
        "request_identity": request_identity,
        "attempt": attempt,
        "page_index": page_index,
        "page_cursor": page_cursor,
        "requested_range": {
            "query": dict(query),
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
        "content_type": response.get("content_type"),
        "elapsed_ms": response.get("elapsed_ms"),
        "body_present": body_file is not None,
        "body_file": body_file,
        "body_sha256": body_sha256,
        "body_length": body_length,
        "body_hash_scope": "EXACT_HTTP_RESPONSE_BODY_BYTES_AS_RECEIVED",
        "price_basis": PRICE_BASIS if capability == "ohlc" else None,
        "completion_marker": RAW_COMPLETION_MARKER,
    }


def retain_response(
    writer: "RecoveryWriter", stem: Path, *, capability: str, ticker: str, target_session: str,
    request_identity: str, attempt: int, response: Mapping[str, Any], query: Mapping[str, Any], endpoint: str,
    started_at: str, acquired_at: str, page_index: int | None = None, page_cursor: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Raw-retention contract, in order:
    1. write the exact response body bytes immutably (fsync + close);
    2. compute SHA-256 from the retained bytes and verify written length/hash;
    3. write the envelope carrying the completion marker (also write-once, fsynced).
    Parsing/classification happens only afterwards, from the retained bytes
    (``load_verified_attempt``). A response with an HTTP status but no exact bytes is refused.
    """
    raw = response.get("raw_bytes")
    if raw is None and response.get("http_status") is not None:
        raise RawRetentionError("FETCH_ADAPTER_DID_NOT_RETURN_EXACT_RESPONSE_BYTES")
    if raw is not None and not isinstance(raw, (bytes, bytearray)):
        raise RawRetentionError("FETCH_ADAPTER_RAW_BYTES_NOT_BYTES")
    body_file = body_sha = body_len = None
    if raw is not None:
        target = body_path(stem)
        body_sha, body_len = writer.write_bytes_once(target, bytes(raw))
        body_file = target.name
    envelope = build_envelope(
        capability=capability, ticker=ticker, target_session=target_session, request_identity=request_identity,
        attempt=attempt, response=response, query=query, endpoint=endpoint, started_at=started_at,
        acquired_at=acquired_at, body_file=body_file, body_sha256=body_sha, body_length=body_len,
        page_index=page_index, page_cursor=page_cursor,
    )
    data = (json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    envelope_sha, _ = writer.write_bytes_once(envelope_path(stem), data)
    return envelope, envelope_sha


def load_verified_attempt(
    stem: Path, *, expected: Mapping[str, Any], journal_envelope_sha256: str | None = None,
    journal_body_sha256: str | None = None,
) -> tuple[dict[str, Any], Any]:
    """Return ``(envelope, parsed_body)`` only when EVERY retained-evidence invariant holds.

    Checked: envelope present and parseable; contract version; durable completion marker; exact
    frozen request identity, target session, symbol, capability, endpoint and request parameters;
    HTTP/provider status metadata; ``acquired_at``; exact body file present with the recorded length
    and SHA-256 (from the bytes); optional journal hashes; and a body that parses under the response
    contract where parsing is required. Anything else raises ``RawIntegrityError`` -- the attempt is
    never adopted as evidence and never degraded to an ``UNKNOWN`` disposition.
    """
    env_path, b_path = envelope_path(stem), body_path(stem)
    if not env_path.is_file():
        raise RawIntegrityError("ORPHAN_BODY_WITHOUT_COMPLETED_ENVELOPE" if b_path.exists() else "RAW_ENVELOPE_MISSING")
    env_bytes = env_path.read_bytes()
    if journal_envelope_sha256 is not None and sha256_bytes(env_bytes) != journal_envelope_sha256:
        raise RawIntegrityError("RETAINED_ENVELOPE_HASH_MISMATCH")
    try:
        envelope = json.loads(env_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RawIntegrityError("RAW_ENVELOPE_MALFORMED") from exc
    if not isinstance(envelope, Mapping):
        raise RawIntegrityError("RAW_ENVELOPE_MALFORMED")
    if envelope.get("contract_version") != RAW_ENVELOPE_CONTRACT:
        raise RawIntegrityError("RAW_ENVELOPE_CONTRACT_MISMATCH")
    if envelope.get("completion_marker") != RAW_COMPLETION_MARKER:
        raise RawIntegrityError("RAW_COMPLETION_MARKER_MISSING")
    for key in ("request_identity", "target_session", "ticker", "capability", "endpoint", "page_index", "page_cursor"):
        if key in expected and envelope.get(key) != expected[key]:
            raise RawIntegrityError(f"RAW_ENVELOPE_{key.upper()}_MISMATCH")
    if "query" in expected and (envelope.get("requested_range") or {}).get("query") != dict(expected["query"]):
        raise RawIntegrityError("RAW_ENVELOPE_REQUEST_PARAMETERS_MISMATCH")
    if not isinstance(envelope.get("acquired_at"), str) or not envelope["acquired_at"]:
        raise RawIntegrityError("RAW_ENVELOPE_ACQUIRED_AT_MISSING")
    status = envelope.get("http_status")
    if status is None:
        if envelope.get("ok") or not str(envelope.get("error_code") or "").startswith("request_failed_"):
            raise RawIntegrityError("RAW_ENVELOPE_STATUS_METADATA_INCONSISTENT")
        if envelope.get("body_present"):
            raise RawIntegrityError("RAW_ENVELOPE_STATUS_METADATA_INCONSISTENT")
        return dict(envelope), None
    if isinstance(status, bool) or not isinstance(status, int):
        raise RawIntegrityError("RAW_ENVELOPE_STATUS_METADATA_INCONSISTENT")
    if not envelope.get("body_present") or envelope.get("body_file") != b_path.name:
        raise RawIntegrityError("RAW_BODY_NOT_RECORDED")
    if not b_path.is_file():
        raise RawIntegrityError("RAW_BODY_FILE_MISSING")
    data = b_path.read_bytes()
    if not isinstance(envelope.get("body_length"), int) or len(data) != envelope["body_length"]:
        raise RawIntegrityError("RAW_BODY_LENGTH_MISMATCH_TRUNCATED_OR_EXTENDED")
    digest = sha256_bytes(data)
    if digest != envelope.get("body_sha256"):
        raise RawIntegrityError("RAW_BODY_HASH_MISMATCH")
    if journal_body_sha256 is not None and digest != journal_body_sha256:
        raise RawIntegrityError("RETAINED_RAW_HASH_MISMATCH")
    parsed: Any = None
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        parsed = None
        if envelope.get("ok"):
            raise RawIntegrityError("RAW_BODY_MALFORMED_UNDER_RESPONSE_CONTRACT")
    if envelope.get("ok") and not isinstance(parsed, Mapping):
        raise RawIntegrityError("RAW_BODY_MALFORMED_UNDER_RESPONSE_CONTRACT")
    return dict(envelope), parsed


def response_from_retained(envelope: Mapping[str, Any], parsed: Any) -> dict[str, Any]:
    """The classification input, rebuilt ONLY from the verified envelope + bytes-parsed body."""
    return {"ok": envelope.get("ok"), "http_status": envelope.get("http_status"),
            "error_code": envelope.get("error_code"), "retry_after_seconds": envelope.get("retry_after_seconds"),
            "body": parsed}


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# =================================================================================================
# Run-state model
# =================================================================================================
# Ticker states. "Terminal" is never a synonym for "successful".
TICKER_PENDING = "PENDING"
TICKER_RETRYABLE = "RETRYABLE_PENDING"
TICKER_CLASSIFIED = "CLASSIFIED_TERMINAL"            # a valid, deterministic disposition
TICKER_UNRESOLVED = "UNRESOLVED_TERMINAL"            # UNKNOWN / exhausted transient -- a defect outcome
TICKER_INTEGRITY = "BLOCKED_INTEGRITY"               # raw conflict / invalid orphan / unverifiable raw
VALID_CLASSIFIED_DISPOSITIONS = frozenset({EXACT_SESSION_OBSERVED, PRIOR_SESSION_ONLY, PROVIDER_REJECTED, NO_HISTORY})

# Overall acquisition states.
RUN_COMPLETE = "COMPLETE"
RUN_PARTIAL_RETRYABLE = "PARTIAL_RETRYABLE"          # rerunning the identical command can progress
RUN_PARTIAL_UNRESOLVED = "PARTIAL_UNRESOLVED"        # defect outcomes a rerun will not change
RUN_BLOCKED_INTEGRITY = "BLOCKED_INTEGRITY"          # retained evidence failed an invariant
RUN_BLOCKED_AUTH = "BLOCKED_AUTH"
RUN_STATUSES = (RUN_COMPLETE, RUN_PARTIAL_RETRYABLE, RUN_PARTIAL_UNRESOLVED, RUN_BLOCKED_INTEGRITY, RUN_BLOCKED_AUTH)
EXIT_CODES = {RUN_COMPLETE: 0, RUN_PARTIAL_RETRYABLE: 3, RUN_PARTIAL_UNRESOLVED: 4,
              RUN_BLOCKED_INTEGRITY: 5, RUN_BLOCKED_AUTH: 6}
# Stop reasons (why network acquisition stopped early this run).
STOP_RATE_LIMIT = "STOPPED_FOR_REVIEW_CONSECUTIVE_RATE_LIMIT"
STOP_AUTH = "STOPPED_AUTHENTICATION_FAILURE"
STOP_BUDGET = "STOPPED_CALL_BUDGET_EXHAUSTED"
STOP_INTEGRITY = "STOPPED_RAW_RETENTION_FAILURE"
# Conflict-resolution contract: an integrity-blocked ticker/chain is NEVER auto-resolved, re-requested
# or overwritten by a rerun. Its retained bytes stay as evidence. The only resolution is an explicit
# owner decision to start a NEW recovery under fresh, empty isolated roots (the blocked state root is
# kept for review).
CONFLICT_RESOLUTION_CONTRACT = "NEVER_AUTO_RESOLVED_OWNER_STARTS_FRESH_ISOLATED_ROOTS_BLOCKED_STATE_RETAINED"

# Back-compat aliases used by the CLI summary.
RUN_STOPPED_RATE_LIMIT = STOP_RATE_LIMIT
RUN_STOPPED_AUTH = STOP_AUTH
RUN_STOPPED_BUDGET = STOP_BUDGET


def overall_status(
    plan: Mapping[str, Any], journals: Mapping[str, Mapping[str, Any]],
    chains: Mapping[str, Mapping[str, Any]] | None = None, stop_reason: str | None = None,
) -> dict[str, Any]:
    """Deterministic overall state. COMPLETE only when every candidate (and every foreign-flow chain)
    reached a valid classified outcome with verified evidence and nothing stopped acquisition."""
    counts: dict[str, int] = {}
    integrity, unresolved, pending = [], [], []
    for ticker in plan["acquisition_attempt_cohort"]["tickers"]:
        journal = journals.get(ticker) or {}
        state = journal.get("state") or TICKER_PENDING
        counts[state] = counts.get(state, 0) + 1
        if state == TICKER_INTEGRITY:
            integrity.append({"ticker": ticker, "code": journal.get("conflict")})
        elif state == TICKER_UNRESOLVED:
            unresolved.append({"ticker": ticker, "disposition": journal.get("disposition")})
        elif state != TICKER_CLASSIFIED:
            pending.append(ticker)
    ff_integrity, ff_unresolved, ff_pending = [], [], []
    for ticker in (plan.get("foreign_flow") or {}).get("cohort") or []:
        chain = (chains or {}).get(ticker) or {}
        state = chain.get("state") or TICKER_PENDING
        if state == TICKER_INTEGRITY:
            ff_integrity.append({"ticker": ticker, "code": chain.get("failure")})
        elif state == TICKER_UNRESOLVED:
            ff_unresolved.append({"ticker": ticker, "failure": chain.get("failure")})
        elif state not in (FF_COMPLETE, TICKER_CLASSIFIED):
            ff_pending.append(ticker)
    if integrity or ff_integrity or stop_reason == STOP_INTEGRITY:
        status = RUN_BLOCKED_INTEGRITY
    elif stop_reason == STOP_AUTH:
        status = RUN_BLOCKED_AUTH
    elif pending or ff_pending or stop_reason in (STOP_RATE_LIMIT, STOP_BUDGET):
        status = RUN_PARTIAL_RETRYABLE
    elif unresolved or ff_unresolved:
        status = RUN_PARTIAL_UNRESOLVED
    else:
        status = RUN_COMPLETE
    return {
        "status": status, "complete": status == RUN_COMPLETE, "stop_reason": stop_reason,
        "ticker_state_counts": dict(sorted(counts.items())),
        "integrity_blocked": integrity, "unresolved": unresolved, "not_classified": pending,
        "foreign_flow": {"integrity_blocked": ff_integrity, "unresolved": ff_unresolved, "not_complete": ff_pending},
        "conflict_resolution_contract": CONFLICT_RESOLUTION_CONTRACT,
    }


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


def governed_recovery_fetcher() -> Fetcher:
    """The existing governed DNSE fetch boundary, asked to retain the exact response bytes."""
    from dnse_bulk_market_data import fetch_capability_raw

    def fetch(capability: str, **kwargs: Any) -> Mapping[str, Any]:
        return fetch_capability_raw(capability, retain_raw_bytes=True, **kwargs)

    return fetch


def _new_journal(ticker: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    target = plan["target_session"]
    identity = ohlc_request_identity(ticker, target)
    return {
        "contract_version": JOURNAL_CONTRACT, "operating_mode": OPERATING_MODE,
        "ticker": ticker, "target_session": target, "request_identity": identity,
        "request_range": ohlc_request_query(ticker, target),
        "attempts": [], "state": TICKER_PENDING, "disposition": NOT_ATTEMPTED,
        "retry_state": {"transient_retries_used": 0, "exhausted": False},
        "conflict": None,
    }


def _ohlc_expected(journal: Mapping[str, Any], attempt: int) -> dict[str, Any]:
    return {"request_identity": journal["request_identity"], "target_session": journal["target_session"],
            "ticker": journal["ticker"], "capability": "ohlc", "endpoint": "/price/ohlc",
            "query": journal["request_range"]}


def _attempt_record(layout: RecoveryLayout, stem: Path, envelope: Mapping[str, Any], envelope_sha: str,
                    verdict: Mapping[str, Any], *, network_call: bool, adopted: bool) -> dict[str, Any]:
    return {
        "attempt": envelope.get("attempt"), "network_call": network_call, "recovered_from_orphan_raw": adopted,
        "acquired_at": envelope.get("acquired_at"), "http_status": envelope.get("http_status"),
        "error_code": envelope.get("error_code"), "retry_after_seconds": envelope.get("retry_after_seconds"),
        "raw_stem": layout.rel(stem), "envelope_sha256": envelope_sha,
        "body_sha256": envelope.get("body_sha256"), "body_length": envelope.get("body_length"),
        "disposition": verdict["disposition"], "reason": verdict.get("reason"),
        "session_counts": verdict.get("session_counts"),
    }


def _block(journal: dict[str, Any], code: str) -> None:
    journal["state"], journal["disposition"], journal["conflict"] = TICKER_INTEGRITY, UNKNOWN, code


def verify_journal_attempt(layout: RecoveryLayout, journal: Mapping[str, Any], attempt: Mapping[str, Any]) -> tuple[dict[str, Any], Any]:
    return load_verified_attempt(
        layout.state_root / attempt["raw_stem"], expected=_ohlc_expected(journal, attempt["attempt"]),
        journal_envelope_sha256=attempt.get("envelope_sha256"), journal_body_sha256=attempt.get("body_sha256"),
    )


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

    journals: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        existing = _load_json(layout.journal_path(ticker))
        journals[ticker] = dict(existing) if isinstance(existing, Mapping) else _new_journal(ticker, plan)
        counters.calls += sum(1 for a in journals[ticker].get("attempts", []) if a.get("network_call"))
        counters.transient_retries += int((journals[ticker].get("retry_state") or {}).get("transient_retries_used", 0))

    for ticker in tickers:
        journal = journals[ticker]
        if journal.get("request_identity") != ohlc_request_identity(ticker, target):
            _block(journal, "JOURNAL_REQUEST_IDENTITY_MISMATCH")
            writer.write_json_atomic(layout.journal_path(ticker), journal)
            continue
        if journal["state"] == TICKER_INTEGRITY:
            continue  # never auto-resolved (CONFLICT_RESOLUTION_CONTRACT)
        if journal["state"] in (TICKER_CLASSIFIED, TICKER_UNRESOLVED):
            last = (journal.get("attempts") or [None])[-1]
            try:
                if last is None:
                    raise RawIntegrityError("TERMINAL_JOURNAL_WITHOUT_ATTEMPT")
                verify_journal_attempt(layout, journal, last)
                reused_without_network += 1
            except RawIntegrityError as exc:
                _block(journal, exc.code)
                writer.write_json_atomic(layout.journal_path(ticker), journal)
            continue
        if stop is not None:
            continue
        while journal["state"] in (TICKER_PENDING, TICKER_RETRYABLE):
            attempt_no = len(journal["attempts"]) + 1
            stem = layout.raw_stem(ticker, journal["request_identity"], attempt_no)
            expected = _ohlc_expected(journal, attempt_no)
            adopted = envelope_path(stem).exists() or body_path(stem).exists()
            if adopted:
                # An orphan from a crash: adopted only if EVERY invariant holds; otherwise the ticker
                # is integrity-blocked (never an UNKNOWN that lets the run finish).
                try:
                    envelope, parsed = load_verified_attempt(stem, expected=expected)
                    if envelope.get("attempt") != attempt_no:
                        raise RawIntegrityError("RAW_ENVELOPE_ATTEMPT_MISMATCH")
                except RawIntegrityError as exc:
                    _block(journal, "INVALID_ORPHAN:" + exc.code)
                    break
                envelope_sha = sha256_bytes(envelope_path(stem).read_bytes())
                counters.calls += 1  # the crashed process really spent this call
                network_call = True
            else:
                if counters.calls >= controls["call_budget"]:
                    stop = STOP_BUDGET
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
                counters.calls += 1
                network_calls_this_run += 1
                network_call = True
                acquired_at = now_iso()
                try:
                    _, envelope_sha = retain_response(
                        writer, stem, capability="ohlc", ticker=ticker, target_session=target,
                        request_identity=journal["request_identity"], attempt=attempt_no, response=response,
                        query=query, endpoint="/price/ohlc", started_at=started_at, acquired_at=acquired_at,
                    )
                    # Parse/classify ONLY from the retained, re-verified bytes.
                    envelope, parsed = load_verified_attempt(stem, expected=expected, journal_envelope_sha256=envelope_sha)
                except RawPayloadConflict:
                    _block(journal, "CONFLICTING_RETAINED_RAW_PAYLOAD")
                    break
                except (RawRetentionError, RawIntegrityError) as exc:
                    _block(journal, "RAW_RETENTION_FAILED:" + str(exc))
                    stop = STOP_INTEGRITY
                    break
            verdict = classify_ohlc_response(response_from_retained(envelope, parsed), target)
            disposition = verdict["disposition"]
            journal["attempts"].append(_attempt_record(layout, stem, envelope, envelope_sha, verdict,
                                                       network_call=network_call, adopted=adopted))
            if disposition == RATE_LIMITED:
                counters.consecutive_429 += 1
            else:
                counters.consecutive_429 = 0
            if disposition == AUTH_FAILED:
                journal["state"], journal["disposition"] = TICKER_PENDING, NOT_ATTEMPTED
                stop = STOP_AUTH
                break
            if disposition in RETRYABLE:
                if counters.consecutive_429 >= controls["stop_after_consecutive_429"]:
                    journal["state"], journal["disposition"] = TICKER_RETRYABLE, disposition
                    stop = STOP_RATE_LIMIT
                    break
                if attempt_no < controls["max_attempts_per_ticker"] and counters.transient_retries < controls["max_transient_retries"]:
                    counters.transient_retries += 1
                    journal["retry_state"]["transient_retries_used"] += 1
                    journal["state"], journal["disposition"] = TICKER_RETRYABLE, disposition
                    writer.write_json_atomic(layout.journal_path(ticker), journal)
                    continue
                journal["retry_state"]["exhausted"] = True
                journal["state"], journal["disposition"] = TICKER_UNRESOLVED, disposition
                break
            journal["state"] = TICKER_CLASSIFIED if disposition in VALID_CLASSIFIED_DISPOSITIONS else TICKER_UNRESOLVED
            journal["disposition"] = disposition
            journal["provider_session_disposition"] = verdict
            break
        writer.write_json_atomic(layout.journal_path(ticker), journal)
        if progress:
            progress(f"{ticker}:{journal['disposition']}:{journal['state']}")

    return {
        "stop_reason": stop, "network_calls_this_run": network_calls_this_run,
        "reused_without_network": reused_without_network, "counters": counters.as_dict(),
        "journals": journals,
    }


# =================================================================================================
# Foreign-flow recovery (isolated store only)
# =================================================================================================

FF_PENDING = "PENDING"
FF_COMPLETE = "COMPLETE_TERMINAL_CURSOR"


def _ff_query(ticker: str, target_session: str, cursor: str | None) -> dict[str, Any]:
    from dnse_foreign_trading_raw import request_query

    return request_query(ticker, target_session, cursor=cursor)


def chain_sha256(page_body_sha256: Sequence[str]) -> str:
    """The one canonical chain-hash algorithm (``recovery_foreign_flow_chain/v1``):
    SHA-256 of ``canonical_json({"chain_contract": CHAIN_CONTRACT, "page_sha256": [ordered page body
    SHA-256 list]})`` -- sorted keys, no whitespace, UTF-8. Order-sensitive and length-sensitive."""
    return sha256_text(canonical_json({"chain_contract": CHAIN_CONTRACT, "page_sha256": list(page_body_sha256)}))


def _refresh_chain_identity(chain: dict[str, Any]) -> None:
    pages = chain.get("pages") or []
    hashes = [p.get("body_sha256") for p in pages]
    times = [p.get("acquired_at") for p in pages if p.get("acquired_at")]
    chain["chain_identity"] = {
        "chain_contract": CHAIN_CONTRACT,
        "page_sha256": hashes,
        "chain_sha256": chain_sha256(hashes),
        "page_count": len(pages),
        "terminal_cursor_reached": bool(chain.get("terminal_cursor_reached")),
        "request_identity": {"ticker": chain.get("ticker"), "target_session": chain.get("target_session"),
                             "capability": "foreign_trading", "request_scope": chain.get("request_scope")},
        "acquired_at_min": min(times) if times else None,
        "acquired_at_max": max(times) if times else None,
    }


def _ff_expected(chain: Mapping[str, Any], page_index: int, cursor: str | None) -> dict[str, Any]:
    ticker = chain["ticker"]
    return {"request_identity": f"dnse_foreign_trading:{ticker}:{chain['target_session']}:page{page_index}",
            "target_session": chain["target_session"], "ticker": ticker, "capability": "foreign_trading",
            "endpoint": f"/price/{ticker}/foreign-trading", "page_index": page_index, "page_cursor": cursor,
            "query": _ff_query(ticker, chain["target_session"], cursor)}


def verify_chain(layout: RecoveryLayout, chain: Mapping[str, Any]) -> list[tuple[dict[str, Any], Any]]:
    """Re-verify every retained page (bytes, hashes, lineage) and the chain hash; raise on any defect."""
    verified = []
    for index, page in enumerate(chain.get("pages") or []):
        if page.get("page_index") != index:
            raise RawIntegrityError("CHAIN_PAGE_INDEX_GAP")
        envelope, parsed = load_verified_attempt(
            layout.state_root / page["raw_stem"], expected=_ff_expected(chain, index, page.get("page_cursor")),
            journal_envelope_sha256=page.get("envelope_sha256"), journal_body_sha256=page.get("body_sha256"),
        )
        verified.append((envelope, parsed))
    recorded = (chain.get("chain_identity") or {}).get("chain_sha256")
    if recorded != chain_sha256([p.get("body_sha256") for p in chain.get("pages") or []]):
        raise RawIntegrityError("CHAIN_SHA256_MISMATCH")
    return verified


def acquire_foreign_flow(
    *, plan: Mapping[str, Any], layout: RecoveryLayout, writer: RecoveryWriter, fetcher: Fetcher,
    api_key: str, api_secret: str, pacer: Pacer, counters: RunCounters,
    now_iso: Callable[[], str] = lambda: vn_now().isoformat(),
) -> dict[str, Any]:
    """Complete each cursor chain to its terminal page. Raw page bytes are retained and hashed and
    every chain (complete or not) carries a ``chain_sha256``. Only a verified complete chain may
    later normalize to VALUE (``normalize_foreign_flow``)."""
    ff = plan["foreign_flow"]
    target = plan["target_session"]
    stop: str | None = None
    chains: dict[str, dict[str, Any]] = {}
    for ticker in ff["cohort"]:
        existing = _load_json(layout.ff_journal_path(ticker))
        chain = dict(existing) if isinstance(existing, Mapping) else {
            "contract_version": JOURNAL_CONTRACT, "operating_mode": OPERATING_MODE, "ticker": ticker,
            "target_session": target, "capability": "foreign_trading", "pages": [], "state": FF_PENDING,
            "terminal_cursor_reached": False, "failure": None, "attempts": 0,
            "request_scope": {k: v for k, v in _ff_query(ticker, target, None).items() if k != "nextPageToken"},
        }
        counters.ff_calls += int(chain.get("attempts", 0))
        chains[ticker] = chain
    for ticker, chain in chains.items():
        if chain["state"] == TICKER_INTEGRITY:
            continue
        if chain["state"] in (FF_COMPLETE, TICKER_CLASSIFIED, TICKER_UNRESOLVED):
            try:
                verify_chain(layout, chain)
            except RawIntegrityError as exc:
                chain["state"], chain["failure"] = TICKER_INTEGRITY, exc.code
                writer.write_json_atomic(layout.ff_journal_path(ticker), chain)
            continue
        if stop is not None:
            continue
        transient_attempts = 0
        pending_delay = 0.0
        while True:
            pages = chain["pages"]
            if pages and not pages[-1].get("next_cursor"):
                chain["state"], chain["terminal_cursor_reached"] = FF_COMPLETE, True
                break
            if len(pages) >= ff["max_pages_per_ticker"]:
                chain["state"], chain["failure"] = TICKER_UNRESOLVED, "NON_TERMINAL_PAGE_LIMIT_REACHED"
                break
            cursor = pages[-1]["next_cursor"] if pages else None
            page_index = len(pages)
            stem = layout.ff_raw_stem(ticker, page_index)
            expected = _ff_expected(chain, page_index, cursor)
            if envelope_path(stem).exists() or body_path(stem).exists():
                try:
                    envelope, parsed = load_verified_attempt(stem, expected=expected)
                except RawIntegrityError as exc:
                    chain["state"], chain["failure"] = TICKER_INTEGRITY, "INVALID_ORPHAN:" + exc.code
                    break
                envelope_sha = sha256_bytes(envelope_path(stem).read_bytes())
                if not envelope.get("ok"):
                    chain["state"], chain["failure"] = TICKER_INTEGRITY, "ORPHAN_PAGE_NOT_A_SUCCESS_RESPONSE"
                    break
            else:
                if counters.ff_calls >= ff["call_budget"]:
                    stop = STOP_BUDGET
                    break
                pacer.wait_turn(pending_delay)
                pending_delay = 0.0
                started_at = now_iso()
                query = expected["query"]
                response = dict(fetcher("foreign_trading", api_key=api_key, api_secret=api_secret, symbol=ticker, query=query))
                counters.ff_calls += 1
                chain["attempts"] = int(chain.get("attempts", 0)) + 1
                acquired_at = now_iso()
                if not response.get("ok"):
                    verdict = classify_ohlc_response(response, target)
                    if verdict["disposition"] == AUTH_FAILED:
                        stop = STOP_AUTH
                        break
                    if verdict["disposition"] == RATE_LIMITED:
                        counters.consecutive_429 += 1
                        if counters.consecutive_429 >= plan["controls"]["stop_after_consecutive_429"]:
                            stop = STOP_RATE_LIMIT
                            break
                        ra = response.get("retry_after_seconds")
                        pending_delay = min(float(ra), plan["controls"]["retry_after_cap_seconds"]) if ra is not None else 0.0
                        continue
                    counters.consecutive_429 = 0
                    if verdict["disposition"] == TRANSPORT_FAILURE:
                        transient_attempts += 1
                        if transient_attempts < plan["controls"]["max_attempts_per_ticker"]:
                            continue
                        chain["state"], chain["failure"] = TICKER_UNRESOLVED, "TRANSPORT_FAILURE_RETRIES_EXHAUSTED"
                        break
                    if verdict["disposition"] == PROVIDER_REJECTED and page_index == 0:
                        chain["state"], chain["failure"] = TICKER_CLASSIFIED, f"{PROVIDER_REJECTED}:{verdict.get('reason')}"
                    else:
                        chain["state"], chain["failure"] = TICKER_UNRESOLVED, f"NON_TERMINAL_{verdict['disposition']}:{verdict.get('reason')}"
                    break
                counters.consecutive_429 = 0
                try:
                    _, envelope_sha = retain_response(
                        writer, stem, capability="foreign_trading", ticker=ticker, target_session=target,
                        request_identity=expected["request_identity"], attempt=1, response=response, query=query,
                        endpoint=expected["endpoint"], started_at=started_at, acquired_at=acquired_at,
                        page_index=page_index, page_cursor=cursor,
                    )
                    envelope, parsed = load_verified_attempt(stem, expected=expected, journal_envelope_sha256=envelope_sha)
                except RawPayloadConflict:
                    chain["state"], chain["failure"] = TICKER_INTEGRITY, "CONFLICTING_RETAINED_RAW_PAGE"
                    break
                except (RawRetentionError, RawIntegrityError) as exc:
                    chain["state"], chain["failure"] = TICKER_INTEGRITY, "RAW_RETENTION_FAILED:" + str(exc)
                    stop = STOP_INTEGRITY
                    break
            next_cursor = parsed.get("nextPageToken") if isinstance(parsed, Mapping) else None
            pages.append({
                "page_index": page_index, "page_cursor": cursor, "raw_stem": layout.rel(stem),
                "envelope_sha256": envelope_sha, "body_sha256": envelope.get("body_sha256"),
                "body_length": envelope.get("body_length"), "acquired_at": envelope.get("acquired_at"),
                "record_count": len(parsed.get("foreigners") or []) if isinstance(parsed.get("foreigners"), list) else None,
                "next_cursor": next_cursor if isinstance(next_cursor, str) and next_cursor else None,
            })
            _refresh_chain_identity(chain)
            writer.write_json_atomic(layout.ff_journal_path(ticker), chain)
        _refresh_chain_identity(chain)
        writer.write_json_atomic(layout.ff_journal_path(ticker), chain)
    return {"stop_reason": stop, "chains": chains, "counters": counters.as_dict()}


def load_chains(plan: Mapping[str, Any], layout: RecoveryLayout) -> dict[str, dict[str, Any]]:
    out = {}
    for ticker in (plan.get("foreign_flow") or {}).get("cohort") or []:
        chain = _load_json(layout.ff_journal_path(ticker))
        out[ticker] = dict(chain) if isinstance(chain, Mapping) else {"ticker": ticker, "state": FF_PENDING, "pages": []}
    return out


def normalize_foreign_flow(
    *, plan: Mapping[str, Any], layout: RecoveryLayout, writer: RecoveryWriter,
) -> dict[str, Any]:
    """VALUE-only normalization of every verified COMPLETE chain into the isolated recovery store."""
    from current_foreign_flow_retention import normalize_exact_raw_sequence, write_exact_value_observation
    from dnse_foreign_flow_store import observation_path

    target = plan["target_session"]
    records: dict[str, Any] = {}
    for ticker, chain in load_chains(plan, layout).items():
        identity = chain.get("chain_identity")
        base = {"chain_identity": identity, "value": None}
        if not chain.get("pages") and chain.get("state") == FF_PENDING:
            records[ticker] = {**base, "status": "NOT_ATTEMPTED"}
            continue
        try:
            verified = verify_chain(layout, chain)
        except RawIntegrityError as exc:
            records[ticker] = {**base, "status": "CHAIN_INTEGRITY_FAILED", "failure": exc.code}
            continue
        if chain.get("state") != FF_COMPLETE or not chain.get("terminal_cursor_reached"):
            records[ticker] = {**base, "status": "NON_TERMINAL_CHAIN_NOT_NORMALIZED", "chain_state": chain.get("state"),
                               "failure": chain.get("failure"), "pages": len(chain.get("pages") or [])}
            continue
        pages = [{
            "instrument": ticker, "source_event_time": target, "raw_payload": parsed,
            "provenance": {"endpoint": envelope.get("endpoint"), "page_index": envelope.get("page_index"),
                           "page_cursor": envelope.get("page_cursor"),
                           "request_parameters": (envelope.get("requested_range") or {}).get("query")},
        } for envelope, parsed in verified]
        try:
            observation = normalize_exact_raw_sequence(ticker=ticker, reference_session=target, pages=pages)
        except ValueError as exc:
            records[ticker] = {**base, "status": "CHAIN_NOT_NORMALIZABLE", "failure": str(exc)}
            continue
        writer.guard(observation_path(layout.runtime_root, ticker))
        write_exact_value_observation(layout.runtime_root, ticker, observation)
        records[ticker] = {
            "chain_identity": identity,
            "status": "COMPLETE_CHAIN_VALUE_NORMALIZED",
            "session_date": observation.get("session_date"),
            "foreign_buy_value": observation.get("foreign_buy_value"),
            "foreign_sell_value": observation.get("foreign_sell_value"),
            "foreign_net_value": observation.get("foreign_net_value"),
            "value_unit": observation.get("value_unit"),
            "pages": len(chain["pages"]),
            "isolated_store": "RECOVERY_RUNTIME_ROOT_ONLY",
        }
    payload = {
        "schema_version": "1.0.0", "contract_version": FOREIGN_FLOW_CONTRACT, **HARD_LABELS,
        "recovery_replay": {"target_session": target},
        "target_session": target,
        "temporal_claim": "RETROSPECTIVE_VALUE_ONLY",
        "authority": "DNSE_RETROSPECTIVE_VALUE_ONLY",
        "chain_hash_algorithm": CHAIN_CONTRACT + ": sha256(canonical_json({chain_contract, page_sha256[ordered]}))",
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


def _parse_rows(envelope: Mapping[str, Any], body: Any, target_session: str) -> list[dict[str, Any]]:
    """Rows parsed from the verified, retained exact bytes (``body`` = their JSON decoding)."""
    from mva_exact_session_snapshot import _observation_rows

    if not isinstance(body, Mapping):
        return []
    rows, _problem = _observation_rows(
        body, requested_session=target_session, query=(envelope.get("requested_range") or {}).get("query") or {},
        retrieved_at=str(envelope.get("acquired_at")),
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


def build_quality_report(
    plan: Mapping[str, Any], journals: Mapping[str, Mapping[str, Any]], run_status: Mapping[str, Any],
) -> dict[str, Any]:
    tickers = plan["acquisition_attempt_cohort"]["tickers"]
    overlay = (plan.get("metadata_overlay") or {}).get("records") or {}
    by: dict[str, list[str]] = {d: [] for d in DISPOSITIONS}
    conflicts = []
    for ticker in tickers:
        journal = journals.get(ticker) or {}
        disposition = journal.get("disposition") or NOT_ATTEMPTED
        if journal.get("state") == TICKER_INTEGRITY:
            conflicts.append({"ticker": ticker, "conflict": journal.get("conflict")})
            disposition = UNKNOWN
        elif journal.get("state") in (TICKER_PENDING, TICKER_RETRYABLE, None):
            disposition = NOT_ATTEMPTED if not journal.get("attempts") else disposition
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
        "acquisition_status": run_status["status"],
        "acquisition_complete": run_status["complete"],
        "run_status": dict(run_status),
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
    quality: Mapping[str, Any], foreign_flow: Mapping[str, Any] | None, run_status: Mapping[str, Any],
) -> dict[str, Any]:
    """The completed reconstruction for an overall COMPLETE run; otherwise an explicitly partial
    diagnostic that makes no completion claim (``reconstruction_complete = false``)."""
    target = plan["target_session"]
    complete = run_status.get("status") == RUN_COMPLETE
    overlay = (plan.get("metadata_overlay") or {}).get("records") or {}
    exact_tickers = sorted(t for t, j in journals.items()
                           if j.get("state") == TICKER_CLASSIFIED and j.get("disposition") == EXACT_SESSION_OBSERVED)
    per_ticker: dict[str, Any] = {}
    acquired_times = []
    exclusions: dict[str, str] = {}
    for ticker in exact_tickers:
        last = journals[ticker]["attempts"][-1]
        try:
            envelope, body = verify_journal_attempt(layout, journals[ticker], last)
        except RawIntegrityError as exc:
            exclusions[ticker] = "RAW_INTEGRITY:" + exc.code
            continue
        acquired_times.append(str(envelope.get("acquired_at")))
        described = _ticker_descriptors(_parse_rows(envelope, body, target), target)
        described["body_sha256"] = envelope.get("body_sha256")
        described["acquired_at"] = envelope.get("acquired_at")
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
        "contract_version": RECONSTRUCTION_CONTRACT if complete else PARTIAL_DIAGNOSTIC_CONTRACT,
        **HARD_LABELS,
        "recovery_replay": {"target_session": target, "plan_identity": plan.get("artifact_identity"),
                            "acquisition_status": run_status.get("status")},
        "reconstruction_complete": complete,
        "artifact_kind": "COMPLETED_SESSION_MARKET_RECONSTRUCTION" if complete
        else "PARTIAL_DIAGNOSTIC_NOT_A_COMPLETED_RECONSTRUCTION",
        "run_status": dict(run_status),
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
    return _identity(artifact, prefix="recovery_session_market_reconstruction" if complete else "recovery_partial_diagnostic")


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
