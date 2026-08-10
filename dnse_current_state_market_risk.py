"""DNSE current-state beta/correlation: HPG vs VNINDEX vertical slice.

SCOPE -- CURRENT-STATE ONLY, NEVER POINT-IN-TIME
    This module computes a *current-state* beta and Pearson correlation
    between a DNSE-evidenced stock's adjusted returns
    (``dnse_current_state_price_analytics.py``) and DNSE's evidenced
    VNINDEX current-state benchmark returns
    (``dnse_index_return_series_capability.py``). Every result carries
    ``analysis_time_semantics = ANALYSIS_TIME_SEMANTICS`` and
    ``pit_backtest_eligible = False`` verbatim. This module never imports,
    and is never imported by, ``point_in_time_market_risk.py`` /
    ``point_in_time_benchmark.py`` / ``risk_liquidity.py`` -- it is a
    separate thin current-state adapter, not the point-in-time market-risk
    pipeline, and must never be called that.

MATH CONTRACT -- REUSED, NOT REINVENTED
    Same convention already established by
    ``point_in_time_market_risk.calculate_point_in_time_beta_and_correlation``:
    sample covariance and sample variance (n - 1 denominator), Pearson
    correlation = Cov / sqrt(Var_stock * Var_benchmark), beta = Cov /
    Var_benchmark, and the same +/-1.000001 floating-point clamp tolerance
    plus 1e-12 near-zero-variance tolerance. That module's own
    ``REQUIRED_WINDOW_LENGTH = 60`` is a *rolling-window* parameter for its
    own trailing time-series output shape (one beta value per calculation
    date, each needing 60 trailing pairs) -- it is not a general "minimum
    observations to compute one non-rolling correlation" law, and no such
    general minimum exists elsewhere in this project. This module therefore
    implements only the minimal mathematical-validity floor documented at
    ``MIN_PAIRED_OBSERVATIONS`` below (the point at which the n - 1
    denominator is defined at all), and never describes a short window as
    statistically strong -- see ``STANDING_WARNINGS``.

INPUT GATES -- BOTH SIDES DNSE, BOTH SIDES EVIDENCE-BOUNDED
    Stock side must be ``dnse_current_state_price_analytics``-qualified
    (ticker-scoped, currently HPG/VCB -- VCB is evidence-valid but outside
    the Stock Lookup production universe, see that module). Benchmark side
    must be ``dnse_index_return_series_capability``-qualified (currently
    VNINDEX only). No fallback provider mixing: a stock report and
    benchmark series from two different sources are rejected even if each
    is individually qualified.

SESSION ALIGNMENT
    Exact-date inner join only. No forward fill, no interpolation, no
    nearest-date matching. Every dropped, unmatched session is reported,
    never hidden.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import dnse_current_state_price_analytics as price_analytics
import dnse_index_return_series_capability as index_capability

VERSION = "1.0.0"

# Step 3's mandatory semantics, carried verbatim on every result this module
# produces -- fixed constants, never derived from input flags.
ANALYSIS_TIME_SEMANTICS = (
    "current_state_using_retrospectively_adjusted_stock_history_and_current_benchmark_history"
)
PIT_BACKTEST_ELIGIBLE = False

# Step 6: the minimal *mathematical* validity floor. Sample covariance and
# sample variance use an (n - 1) denominator, defined only for n >= 2. This
# is a floor on when the formula is defined at all, not a judgment about
# when the result is a reliable investment signal -- see
# SAMPLE_ADEQUACY_MATHEMATICALLY_COMPUTABLE below and the module docstring's
# note on why point_in_time_market_risk.REQUIRED_WINDOW_LENGTH (60) is not
# reused as this threshold.
MIN_PAIRED_OBSERVATIONS = 2

# Reused verbatim from point_in_time_market_risk.py's own tolerances.
ZERO_VARIANCE_TOLERANCE = 1e-12
_CORRELATION_CLAMP_TOLERANCE = 1.000001

SAMPLE_ADEQUACY_MATHEMATICALLY_COMPUTABLE = "MATHEMATICALLY_COMPUTABLE"
SAMPLE_ADEQUACY_INSUFFICIENT = "INSUFFICIENT_FOR_COMPUTATION"
SAMPLE_ADEQUACY_INVALID_INPUT = "INVALID_INPUT_NON_FINITE_RETURN_DETECTED"

STATUS_QUALIFIED = "CURRENT_STATE_BETA_CORRELATION_QUALIFIED"
STATUS_NOT_QUALIFIED = "CURRENT_STATE_BETA_CORRELATION_NOT_QUALIFIED"

# Step 12's mandatory standing warnings -- always present, regardless of
# qualification outcome, so a caller can never receive a qualified result
# without also receiving these limits alongside it.
STANDING_WARNINGS = (
    "short_observation_window_statistical_confidence_is_limited",
    "mathematically_computable_is_not_the_same_claim_as_statistically_strong",
    "descriptive_current_state_statistic_only_not_a_recommendation_or_risk_grade",
    "correlation_and_beta_are_not_evidence_of_causation",
    "current_state_only_no_point_in_time_or_backtest_authority",
    "not_wired_into_production_bundle_ranking_or_publication",
)


class DnseCurrentStateMarketRiskError(ValueError):
    """Fail-closed rejection for an out-of-contract call into this module."""


# --------------------------------------------------------------------- Step 4 input gates

def _stock_input_gate(stock_report: Mapping[str, Any]) -> tuple[bool, str | None]:
    """True only when the stock side is DNSE-price-analytics-qualified with a
    complete adjusted-return series and explicit PIT=false.

    ``stock_price_contract`` carries a single ``price_basis``/
    ``price_basis_contract_version`` pair for the whole report by
    construction -- ``dnse_current_state_price_analytics.py`` has no
    per-observation price-basis field to drift, so "same price-basis
    contract across observations" is a structural guarantee, not something
    this gate re-derives.
    """
    eligibility = stock_report.get("eligibility") or {}
    if not eligibility.get("eligible_for_current_state_price_analytics"):
        return False, "stock_ticker_not_qualified_for_dnse_current_state_price_analytics"
    if (stock_report.get("coverage") or {}).get("status") != "complete":
        return False, "stock_side_session_coverage_incomplete"
    returns = stock_report.get("returns") or {}
    if returns.get("status") != "complete":
        return False, "stock_side_adjusted_return_series_not_complete"
    if stock_report.get("pit_backtest_eligible") is not False:
        return False, "stock_side_pit_backtest_eligible_flag_not_explicitly_false"
    if stock_report.get("analysis_time_semantics") != price_analytics.ANALYSIS_TIME_SEMANTICS:
        return False, "stock_side_analysis_time_semantics_unexpected"
    return True, None


def _benchmark_input_gate(benchmark_series: Mapping[str, Any]) -> tuple[bool, str | None]:
    """True only when the benchmark side is DNSE-index-return-series-qualified,
    exactly identified, with valid session semantics and explicit PIT=false."""
    eligibility = benchmark_series.get("eligibility") or {}
    if not eligibility.get("eligible_for_current_state_return_series"):
        return False, "benchmark_not_qualified_for_dnse_current_state_return_series"
    if benchmark_series.get("benchmark_id") not in index_capability.EVIDENCE_QUALIFIED_BENCHMARKS:
        return False, "benchmark_identity_not_in_evidence_qualified_benchmark_set"
    if (benchmark_series.get("coverage") or {}).get("status") != "complete":
        return False, "benchmark_side_session_coverage_incomplete"
    if not benchmark_series.get("current_state_qualified"):
        return False, "benchmark_side_not_current_state_qualified"
    if benchmark_series.get("pit_backtest_eligible") is not False:
        return False, "benchmark_side_pit_backtest_eligible_flag_not_explicitly_false"
    if benchmark_series.get("analysis_time_semantics") != index_capability.ANALYSIS_TIME_SEMANTICS:
        return False, "benchmark_side_analysis_time_semantics_unexpected"
    return True, None


# --------------------------------------------------------------------- Step 5 session alignment

def align_current_state_returns(
    stock_returns: Sequence[Mapping[str, Any]],
    benchmark_returns: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Exact-date inner join of two already-independently-contiguous return
    series. No forward fill, no interpolation, no nearest-date matching --
    a session date present on only one side is dropped and reported, never
    filled. Fails closed (status ``rejected``) on a duplicate or
    non-ascending ``session_date`` on either side -- a defensive,
    independent check, not a re-trust of the upstream series' own
    contiguity guarantee.
    """
    stock_dates = [r["session_date"] for r in stock_returns]
    bmk_dates = [r["session_date"] for r in benchmark_returns]

    base = {
        "aligned_pairs": [],
        "stock_return_count": len(stock_returns),
        "benchmark_return_count": len(benchmark_returns),
        "paired_return_count": 0,
        "dropped_stock_sessions": [],
        "dropped_benchmark_sessions": [],
    }

    if len(set(stock_dates)) != len(stock_dates):
        return {**base, "status": "rejected", "reason": "duplicate_session_date_on_stock_side"}
    if len(set(bmk_dates)) != len(bmk_dates):
        return {**base, "status": "rejected", "reason": "duplicate_session_date_on_benchmark_side"}
    if stock_dates != sorted(stock_dates):
        return {**base, "status": "rejected", "reason": "stock_side_sessions_not_in_ascending_order"}
    if bmk_dates != sorted(bmk_dates):
        return {**base, "status": "rejected", "reason": "benchmark_side_sessions_not_in_ascending_order"}

    stock_by_date = {r["session_date"]: r for r in stock_returns}
    bmk_by_date = {r["session_date"]: r for r in benchmark_returns}
    common_dates = sorted(set(stock_by_date) & set(bmk_by_date))
    dropped_stock = sorted(set(stock_by_date) - set(bmk_by_date))
    dropped_bmk = sorted(set(bmk_by_date) - set(stock_by_date))

    aligned_pairs = [
        {
            "session_date": d,
            "stock_return": stock_by_date[d]["simple_return"],
            "benchmark_return": bmk_by_date[d]["simple_return"],
        }
        for d in common_dates
    ]

    return {
        **base,
        "status": "aligned",
        "reason": None,
        "aligned_pairs": aligned_pairs,
        "paired_return_count": len(aligned_pairs),
        "dropped_stock_sessions": dropped_stock,
        "dropped_benchmark_sessions": dropped_bmk,
    }


# --------------------------------------------------------------------- Steps 6-8 beta/correlation math

def compute_beta_and_correlation(pairs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Beta = Cov(stock, benchmark) / Var(benchmark); Pearson correlation =
    Cov / sqrt(Var_stock * Var_benchmark). Sample covariance/variance
    (n - 1 denominator), matching
    ``point_in_time_market_risk.calculate_point_in_time_beta_and_correlation``
    exactly. Fails closed on: fewer than ``MIN_PAIRED_OBSERVATIONS`` pairs,
    a non-finite/non-numeric input return, or near-zero benchmark variance
    (which also makes correlation undefined, since its denominator includes
    benchmark variance). Never annualizes, never infers causality.
    """
    n = len(pairs)
    if n < MIN_PAIRED_OBSERVATIONS:
        reason = (
            f"only {n} paired observation(s); sample covariance/variance needs at least "
            f"{MIN_PAIRED_OBSERVATIONS} (n - 1 denominator)"
        )
        return {
            "beta": None, "correlation": None,
            "sample_adequacy": SAMPLE_ADEQUACY_INSUFFICIENT,
            "observation_count": n, "beta_reason": reason, "correlation_reason": reason,
        }

    stock_r = [p["stock_return"] for p in pairs]
    bmk_r = [p["benchmark_return"] for p in pairs]
    if not all(
        isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
        for x in (*stock_r, *bmk_r)
    ):
        reason = "non_finite_or_non_numeric_return_value_detected_in_aligned_pairs"
        return {
            "beta": None, "correlation": None,
            "sample_adequacy": SAMPLE_ADEQUACY_INVALID_INPUT,
            "observation_count": n, "beta_reason": reason, "correlation_reason": reason,
        }

    mean_stock = sum(stock_r) / n
    mean_bmk = sum(bmk_r) / n
    cov = sum((stock_r[i] - mean_stock) * (bmk_r[i] - mean_bmk) for i in range(n)) / (n - 1)
    var_bmk = sum((x - mean_bmk) ** 2 for x in bmk_r) / (n - 1)
    var_stock = sum((x - mean_stock) ** 2 for x in stock_r) / (n - 1)

    if var_bmk <= ZERO_VARIANCE_TOLERANCE:
        reason = "zero_or_near_zero_benchmark_variance"
        return {
            "beta": None, "correlation": None,
            "sample_adequacy": SAMPLE_ADEQUACY_MATHEMATICALLY_COMPUTABLE,
            "observation_count": n, "beta_reason": reason, "correlation_reason": reason,
        }

    beta_val = cov / var_bmk

    correlation_val = None
    correlation_reason = None
    if var_stock <= ZERO_VARIANCE_TOLERANCE:
        correlation_reason = "zero_or_near_zero_stock_variance"
    else:
        raw_corr = cov / math.sqrt(var_stock * var_bmk)
        if raw_corr > 1.0 and raw_corr <= _CORRELATION_CLAMP_TOLERANCE:
            correlation_val = 1.0
        elif raw_corr < -1.0 and raw_corr >= -_CORRELATION_CLAMP_TOLERANCE:
            correlation_val = -1.0
        elif abs(raw_corr) > _CORRELATION_CLAMP_TOLERANCE:
            correlation_reason = "correlation_out_of_mathematical_range"
        else:
            correlation_val = raw_corr

    return {
        "beta": beta_val,
        "correlation": correlation_val,
        "sample_adequacy": SAMPLE_ADEQUACY_MATHEMATICALLY_COMPUTABLE,
        "observation_count": n,
        "beta_reason": None,
        "correlation_reason": correlation_reason,
    }


# --------------------------------------------------------------------- Step 3 canonical contract

def compute_current_state_beta_correlation(
    stock_report: Mapping[str, Any],
    benchmark_series: Mapping[str, Any],
) -> dict[str, Any]:
    """The canonical current-state beta/correlation contract (Step 3).

    ``stock_report`` is
    ``dnse_current_state_price_analytics.build_shadow_report()``'s output.
    ``benchmark_series`` is
    ``dnse_index_return_series_capability.build_index_return_series()``'s
    output; this function derives its returns internally via
    ``compute_returns_for_series`` rather than requiring a third argument.

    Always returns a dict; never raises for an unqualified ticker or
    benchmark -- that is an expected, common outcome carried in
    ``qualification_status``, matching the sibling contracts' own
    fail-closed-not-raise convention. ``qualification_status`` is
    ``STATUS_QUALIFIED`` only when gates, alignment, and both the beta and
    correlation values resolved to real numbers; any other outcome
    (unqualified input, rejected alignment, insufficient/invalid pairs,
    zero variance, out-of-range correlation) is ``STATUS_NOT_QUALIFIED`` --
    the per-metric ``beta``/``correlation`` sub-objects and ``coverage``
    carry the precise reason.
    """
    ticker = stock_report.get("ticker")
    benchmark_id = benchmark_series.get("benchmark_id")

    stock_ok, stock_reason = _stock_input_gate(stock_report)
    benchmark_ok, benchmark_reason = _benchmark_input_gate(benchmark_series)
    same_source = (
        stock_report.get("source") is not None
        and stock_report.get("source") == benchmark_series.get("source")
    )
    source_scope_reason = (
        None if same_source
        else "cross_provider_source_mixing_not_authorized_stock_and_benchmark_must_share_one_source"
    )
    gates_ok = stock_ok and benchmark_ok and same_source

    record: dict[str, Any] = {
        "schema_version": VERSION,
        "ticker": ticker,
        "benchmark": benchmark_id,
        "source_scope": {
            "stock_source": stock_report.get("source"),
            "benchmark_source": benchmark_series.get("source"),
            "same_source_no_fallback_mixing": same_source,
            "reason": source_scope_reason,
        },
        "stock_price_contract": {
            "price_basis": stock_report.get("price_basis"),
            "price_basis_contract_version": stock_report.get("price_basis_contract_version"),
            "qualification_scope": stock_report.get("qualification_scope"),
        },
        "benchmark_return_contract": {
            "index_level_unit": benchmark_series.get("index_level_unit"),
            "source_contract_version": benchmark_series.get("source_contract_version"),
        },
        "analysis_time_semantics": ANALYSIS_TIME_SEMANTICS,
        "pit_backtest_eligible": PIT_BACKTEST_ELIGIBLE,
        "input_gates": {
            "stock_qualified": stock_ok,
            "stock_reason": stock_reason,
            "benchmark_qualified": benchmark_ok,
            "benchmark_reason": benchmark_reason,
            "source_scope_ok": same_source,
            "source_scope_reason": source_scope_reason,
        },
        "aligned_sessions": {
            "aligned_pairs": [], "stock_return_count": 0, "benchmark_return_count": 0,
            "paired_return_count": 0, "dropped_stock_sessions": [], "dropped_benchmark_sessions": [],
            "status": "not_attempted", "reason": None,
        },
        "paired_return_count": 0,
        "beta": {"value": None, "sample_adequacy": None, "reason": None},
        "correlation": {"value": None, "sample_adequacy": None, "reason": None},
        "coverage": {
            "status": "not_qualified",
            "reason": stock_reason or benchmark_reason or source_scope_reason,
        },
        "qualification_status": STATUS_NOT_QUALIFIED,
        "warnings": list(STANDING_WARNINGS),
        "provenance": {
            "stock_provenance": stock_report.get("provenance"),
            "benchmark_provenance": benchmark_series.get("provenance"),
            "contract_module": "dnse_current_state_market_risk.py",
            "contract_version": VERSION,
        },
    }

    if not gates_ok:
        return record

    stock_returns = ((stock_report.get("returns") or {}).get("returns")) or []
    benchmark_returns = (index_capability.compute_returns_for_series(benchmark_series).get("returns")) or []

    alignment = align_current_state_returns(stock_returns, benchmark_returns)
    record["aligned_sessions"] = alignment
    record["paired_return_count"] = alignment["paired_return_count"]

    if alignment["status"] != "aligned":
        record["coverage"] = {"status": "alignment_rejected", "reason": alignment.get("reason")}
        return record

    stat = compute_beta_and_correlation(alignment["aligned_pairs"])
    record["beta"] = {
        "value": stat["beta"], "sample_adequacy": stat["sample_adequacy"], "reason": stat["beta_reason"],
    }
    record["correlation"] = {
        "value": stat["correlation"], "sample_adequacy": stat["sample_adequacy"], "reason": stat["correlation_reason"],
    }

    if stat["beta"] is None or stat["correlation"] is None:
        record["coverage"] = {
            "status": "beta_or_correlation_undefined",
            "paired_return_count": alignment["paired_return_count"],
            "minimum_required": MIN_PAIRED_OBSERVATIONS,
            "sample_adequacy": stat["sample_adequacy"],
            "reason": stat["beta_reason"] or stat["correlation_reason"],
        }
        return record

    record["coverage"] = {
        "status": "complete",
        "paired_return_count": alignment["paired_return_count"],
        "minimum_required": MIN_PAIRED_OBSERVATIONS,
        "sample_adequacy": stat["sample_adequacy"],
        "reason": None,
    }
    record["qualification_status"] = STATUS_QUALIFIED
    return record


def build_current_state_market_risk_report(
    ticker: str,
    benchmark_id: str,
    stock_raw_ohlc: Mapping[str, Any] | None,
    benchmark_raw_ohlc: Mapping[str, Any] | None,
    *,
    runtime_root: Any,
    fetch_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """End-to-end convenience wrapper: raw OHLC payloads for both sides ->
    the canonical current-state beta/correlation contract. Thin composition
    only -- all qualification and math live in the functions above and in
    the two upstream capability modules."""
    stock_report = price_analytics.build_shadow_report(
        ticker, stock_raw_ohlc, runtime_root=runtime_root, fetch_provenance=fetch_provenance,
        include_technical_indicators=False,
    )
    benchmark_series = index_capability.build_index_return_series(
        benchmark_id, benchmark_raw_ohlc, runtime_root=runtime_root, fetch_provenance=fetch_provenance,
    )
    return compute_current_state_beta_correlation(stock_report, benchmark_series)


# --------------------------------------------------------------------- offline bundle-attachment entry point

# Evidence lives in the workspace-level operations-review/ directory (a sibling
# of this repo checkout), not under STOCK_LOOKUP_RUNTIME_ROOT -- the same two
# files already retained by the DNSE current-state price-analytics and index
# return-series qualification milestones, reused here rather than re-fetched.
# This is a known, deliberate characteristic (not a network dependency): if
# that evidence is ever archived/moved, callers here fail closed (a missing
# file yields raw_ohlc=None, which flows into the normal ineligible/no-payload
# path -- see build_shadow_report / build_index_return_series), they do not
# crash and never fall back to a live DNSE fetch.
_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STOCK_EVIDENCE_PATH = (
    _WORKSPACE_ROOT / "operations-review" / "dnse-current-state-price-analytics-20260810"
    / "probe_results.json"
)
DEFAULT_BENCHMARK_EVIDENCE_PATH = (
    _WORKSPACE_ROOT / "operations-review" / "dnse-index-return-series-qualification-20260810"
    / "probe_results.json"
)


def _find_ohlc_result(evidence: Mapping[str, Any], symbol: str) -> dict[str, Any] | None:
    """The first ok `ohlc` result in `evidence` whose requested symbol matches
    `symbol` (case-insensitive). Independent, root-level copy of the same
    logic already established in `tools/dnse_current_state_market_risk_shadow.py`
    -- kept separate rather than imported so this module (and anything
    importing it, e.g. `export_ai_bundle.py`) never depends on `tools/`."""
    normalized = str(symbol).strip().upper()
    for result in evidence.get("results", []):
        if result.get("capability") != "ohlc" or not result.get("ok"):
            continue
        query_symbol = str((result.get("query_sent") or {}).get("symbol", "")).strip().upper()
        if query_symbol == normalized:
            return result
    return None


def _load_raw_ohlc_from_evidence(evidence_path: Path, symbol: str) -> dict[str, Any] | None:
    """Read-only, no network: returns the raw OHLC payload for `symbol` from a
    retained probe-evidence JSON file, or None if the file/symbol is absent."""
    if not evidence_path.exists():
        return None
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    ohlc_result = _find_ohlc_result(evidence, symbol)
    return ohlc_result.get("body_redacted") if ohlc_result else None


def build_current_state_market_risk_from_retained_evidence(
    ticker: str,
    benchmark_id: str = "VNINDEX",
    *,
    runtime_root: Any,
    stock_evidence_path: Path = DEFAULT_STOCK_EVIDENCE_PATH,
    benchmark_evidence_path: Path = DEFAULT_BENCHMARK_EVIDENCE_PATH,
) -> dict[str, Any]:
    """Offline, network-free entry point for bundle attachment (Step 8 of the
    integration milestone): reads raw OHLC directly from the two probe
    evidence files already retained by the prior DNSE qualification
    milestones -- never fetches anything live, never reads secrets.env.
    Delegates all qualification and math to
    ``build_current_state_market_risk_report`` /
    ``compute_current_state_beta_correlation`` -- nothing here recomputes a
    formula. A ticker/benchmark absent from its evidence file (e.g. every
    non-HPG production ticker) simply resolves ``raw_ohlc=None``, which the
    downstream contract already handles as an expected, fail-closed
    "no payload" case -- not an error here.
    """
    stock_raw = _load_raw_ohlc_from_evidence(stock_evidence_path, ticker)
    benchmark_raw = _load_raw_ohlc_from_evidence(benchmark_evidence_path, benchmark_id)
    return build_current_state_market_risk_report(
        ticker, benchmark_id, stock_raw, benchmark_raw, runtime_root=runtime_root,
        fetch_provenance={
            "stock_evidence_path": str(stock_evidence_path),
            "benchmark_evidence_path": str(benchmark_evidence_path),
        },
    )


def serialize(record: Mapping[str, Any]) -> str:
    """Deterministic JSON serialization -- same input always produces the
    same bytes, so a caller can hash/compare/replay a retained report."""
    return json.dumps(record, sort_keys=True, default=str)
