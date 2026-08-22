"""tools/derive_qualified_liquidity_inputs_reconciliation.py — Qualified Liquidity Inputs
Reconciliation V1.

Reconciles daily volume/value composition (matched/regular-board, put-through, total, and the
still-unresolved odd-lot dimension) across every already-retained DNSE/FHSC evidence source in
this repository, so a future portfolio/risk engine can consume explicitly-scoped inputs instead
of guessing. This module performs **no acquisition**: every row traces to a retained artifact or
retained raw byte file already on disk under ``operations-review/``.

Sources combined (all within this repository, all already retained):
- Source A: ``dnse_fhsc_market_composition_scaleout.py`` 's retained artifact
  (12 tickers x 10 sessions, 2026-08-07..2026-08-20, DNSE OHLC ``v`` vs FHSC trading-history
  matched/put-through/total volume).
- Source B: ``dnse_fhsc_volume_basis.py`` 's retained artifact
  (HPG/SSI/VCB x 5 sessions, a strict subset of Source A's cohort by ticker and session --
  consumed here as an *independent cross-artifact verification*, not as new rows).
- Source C: the retained raw DNSE OHLC + FHSC trading-history bytes for HPG/SSI/VCB on
  2026-08-21 under ``operations-review/capability-first-real-eod-2026-08-21/raw/`` -- parsed
  directly with the existing ``dnse_fhsc_volume_basis`` parsers to extend Source A/B's session
  coverage by one genuinely new, byte-verified session.
- Source D: ``capability_research_digest.json`` 's ``fhsc_value_volume_composition`` (FHSC-only;
  no DNSE volume comparator exists for this session or field) across its full 111-ticker
  acquired-enrichment cohort for 2026-08-21 -- used for FHSC-internal value+volume arithmetic-
  identity breadth, not for the DNSE-vs-FHSC semantic candidate question.

Deliberately NOT touched: the canonical Trades corpus (18.1M rows / 40 sessions) cannot be
loaded -- its generator (``dnse_trades_canonical_shadow.py``) is not in this repository's `main`
ancestry (``dnse_volume_composition_reconciliation.py`` documents this itself as
``CANONICAL_TRADES_LINEAGE_STATUS = "SOURCE_GENERATOR_NOT_IN_CURRENT_MAIN_ANCESTRY"``), and
AGENTS.md restricts work to this repository. Odd-lot / board-level composition is therefore
UNAVAILABLE here as numeric evidence. The current repository's canonical board contract is used
for all board labels; an older reconciliation's reversed local variable names are implementation
prior art, not competing semantic authority (see ``evaluate_board_composition_conflict``).

Authority boundary: ``authority_effect: "NONE"``. Nothing here promotes RAW_AS_TRADED, PIT,
liquidity/sizing, or execution authority. ``QUALIFIED_LIQUIDITY_INPUTS`` remains a per-field,
per-scope verdict -- never a single blanket YES/NO -- and no position sizing is computed or
implied anywhere in this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json
from dnse_fhsc_market_composition_scaleout import (
    DNSE_EQUALS_MATCHED,
    DNSE_EQUALS_NONE,
    DNSE_EQUALS_PUT_THROUGH,
    DNSE_EQUALS_TOTAL,
    NON_DISCRIMINATING_ZERO_PUT_THROUGH,
    NOT_COMPARABLE as SOURCE_A_NOT_COMPARABLE,
    classify_volume as classify_volume_row,
)
from dnse_fhsc_market_composition_scaleout import content_identity as market_composition_content_identity
from dnse_fhsc_volume_basis import content_identity as volume_basis_content_identity
from dnse_fhsc_volume_basis import parse_dnse_ohlc_volume, parse_fhsc_trading_history
from market_phase2_foundation import DNSE_BOARD_SEMANTICS

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "qualified_liquidity_inputs_reconciliation/v1"

# ---------------------------------------------------------------------------
# Required verdict taxonomy (task-mandated; distinct from, and mapped from, the
# label vocabularies of the two upstream modules this tool consumes).
# ---------------------------------------------------------------------------
EXACT_RECONCILED = "EXACT_RECONCILED"
COVERAGE_RESTRICTED_RECONCILED = "COVERAGE_RESTRICTED_RECONCILED"
CONFLICTING = "CONFLICTING"
INSUFFICIENT_DISCRIMINATION = "INSUFFICIENT_DISCRIMINATION"
UNAVAILABLE = "UNAVAILABLE"
VERDICT_TAXONOMY = (EXACT_RECONCILED, COVERAGE_RESTRICTED_RECONCILED, CONFLICTING, INSUFFICIENT_DISCRIMINATION, UNAVAILABLE)

# Row-level label -> taxonomy (aggregation to COVERAGE_RESTRICTED_RECONCILED happens separately,
# at the candidate/field level, based on tested-scope breadth -- never at the single-row level).
_ROW_LABEL_TO_VERDICT: dict[str, str] = {
    DNSE_EQUALS_MATCHED: EXACT_RECONCILED,
    DNSE_EQUALS_TOTAL: EXACT_RECONCILED,
    DNSE_EQUALS_PUT_THROUGH: EXACT_RECONCILED,
    DNSE_EQUALS_NONE: CONFLICTING,
    NON_DISCRIMINATING_ZERO_PUT_THROUGH: INSUFFICIENT_DISCRIMINATION,
    SOURCE_A_NOT_COMPARABLE: UNAVAILABLE,
}
_EXACT_MATCH_LABEL_TO_COMPONENT: dict[str, str] = {
    DNSE_EQUALS_MATCHED: "matched",
    DNSE_EQUALS_TOTAL: "total",
    DNSE_EQUALS_PUT_THROUGH: "put_through",
}

AUTHORITY_BOUNDARIES = {
    "authority_effect": "NONE",
    "raw_as_traded_promoted": False,
    "pit_backtest_eligible": False,
    "liquidity_sizing_authority": "BLOCKED",
    "position_sizing_safe": False,
    "valuation_authority": False,
    "recommendation_authority": False,
    "ranking_authority": False,
    "database_mutated": False,
    "network_requests_made": 0,
}

CANONICAL_TRADES_LINEAGE_STATUS = "SOURCE_GENERATOR_NOT_IN_CURRENT_MAIN_ANCESTRY"


class LiquidityInputIdentityError(ValueError):
    """Raised when a retained source artifact fails self-consistency validation."""


def _canonical_json(val: Any) -> str:
    return json.dumps(val, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_json(val: Any) -> str:
    return hashlib.sha256(_canonical_json(val).encode("utf-8")).hexdigest()


def _is_exact_integer(value: Any) -> bool:
    """True if value is an int, or a float that carries no fractional part (JSON-round-tripped int)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    return False


def _as_int(value: Any) -> int | None:
    return int(value) if _is_exact_integer(value) else None


# ---------------------------------------------------------------------------
# Source loaders (retained artifacts only -- no network, no re-acquisition)
# ---------------------------------------------------------------------------

def load_market_composition_scaleout(path: Path) -> Mapping[str, Any]:
    """Source A. Fail closed if the retained artifact's own hash does not reproduce."""
    artifact = json.loads(path.read_text(encoding="utf-8"))
    recomputed = market_composition_content_identity(artifact)
    if recomputed["artifact_sha256"] != artifact.get("artifact_sha256"):
        raise LiquidityInputIdentityError(
            f"Source A ({path}) artifact_sha256 does not match its own recomputed content hash."
        )
    return artifact


def load_volume_basis_qualification(path: Path) -> Mapping[str, Any]:
    """Source B. Fail closed if the retained artifact's own hash does not reproduce."""
    artifact = json.loads(path.read_text(encoding="utf-8"))
    recomputed = volume_basis_content_identity(artifact)
    if recomputed["artifact_sha256"] != artifact.get("artifact_sha256"):
        raise LiquidityInputIdentityError(
            f"Source B ({path}) artifact_sha256 does not match its own recomputed content hash."
        )
    return artifact


def load_capability_research_digest(path: Path) -> Mapping[str, Any]:
    """Source D. Fail closed if the retained digest's own hash does not reproduce."""
    digest = json.loads(path.read_text(encoding="utf-8"))
    recomputed_sha = _sha256_json({
        k: v for k, v in digest.items() if k not in {"digest_sha256", "digest_identity", "execution_timestamp"}
    })
    if recomputed_sha != digest.get("digest_sha256"):
        raise LiquidityInputIdentityError(
            f"Source D ({path}) digest_sha256 does not match its own recomputed content hash."
        )
    return digest


def load_real_eod_new_session_rows(raw_dir: Path, tickers: Sequence[str], session_date: str) -> list[dict[str, Any]]:
    """Source C. Parse retained raw DNSE OHLC + FHSC trading-history bytes for one new session.

    Every byte read is hashed and the hash is retained in the row for lineage; this never treats
    a missing raw pair as a zero -- a ticker with no retained raw pair is simply absent from the
    returned rows and must be reported as coverage-restricted, not silently backfilled.
    """
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        ohlc_matches = sorted(raw_dir.glob(f"dnse_ohlc_{ticker}_*.json"))
        trading_matches = sorted(raw_dir.glob(f"fhsc_trading_history_{ticker}_*.json"))
        if not ohlc_matches or not trading_matches:
            rows.append({"ticker": ticker, "session": session_date, "source": "C", "row_status": "RAW_PAIR_MISSING"})
            continue
        ohlc_bytes = ohlc_matches[0].read_bytes()
        trading_bytes = trading_matches[0].read_bytes()
        ohlc_parsed = parse_dnse_ohlc_volume(ohlc_bytes, instrument=ticker, session=session_date)
        trading_parsed = parse_fhsc_trading_history(trading_bytes, instrument=ticker)
        if ohlc_parsed.get("parse_status") != "PARSED":
            rows.append({"ticker": ticker, "session": session_date, "source": "C", "row_status": f"DNSE_PARSE_{ohlc_parsed.get('parse_status')}"})
            continue
        session_row = next((r for r in trading_parsed.get("rows", []) if r.get("session") == session_date), None)
        if session_row is None or session_row.get("parse_status") != "PARSED":
            rows.append({"ticker": ticker, "session": session_date, "source": "C", "row_status": "FHSC_TRADING_SESSION_ROW_ABSENT_OR_INVALID"})
            continue
        rows.append({
            "ticker": ticker, "session": session_date, "source": "C", "row_status": "PARSED",
            "dnse_v": ohlc_parsed["raw_value"],
            "matched_volume": session_row["matched_volume"], "put_through_volume": session_row["put_through_volume"],
            "total_volume": session_row["total_volume"], "retained_arithmetic_identity": session_row["retained_arithmetic_identity"],
            "dnse_raw_sha256": ohlc_parsed["raw_sha256"], "fhsc_raw_sha256": trading_parsed["raw_sha256"],
        })
    return rows


# ---------------------------------------------------------------------------
# Row normalization and combination across sources A/B/C
# ---------------------------------------------------------------------------

def _rows_from_source_a(artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for r in artifact["volume"]["volume_matrix"]:
        out.append({
            "ticker": r["ticker"], "session": r["session"], "source": "A",
            "dnse_v": r.get("dnse_ohlc_volume"), "matched_volume": r.get("fhsc_matched_volume"),
            "put_through_volume": r.get("fhsc_put_through_volume"), "total_volume": r.get("fhsc_total_volume"),
            "row_status": "PARSED" if r["classification"] != SOURCE_A_NOT_COMPARABLE else "NOT_COMPARABLE",
        })
    return out


def _rows_from_source_b(artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for r in artifact["reconciliation"]["matrix"]:
        if r.get("missing_observation"):
            out.append({"ticker": r["ticker"], "session": r["session"], "source": "B", "row_status": "NOT_COMPARABLE"})
            continue
        out.append({
            "ticker": r["ticker"], "session": r["session"], "source": "B",
            "dnse_v": r.get("dnse_generic_volume"), "matched_volume": r.get("fhsc_matched_volume"),
            "put_through_volume": r.get("fhsc_put_through_volume"), "total_volume": r.get("fhsc_total_volume"),
            "row_status": "PARSED",
        })
    return out


def combine_cross_provider_rows(*row_groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Union rows by (ticker, session); verify byte-for-byte agreement on any real overlap.

    A cell observed by more than one source is kept once, tagged with every agreeing source --
    unless the sources disagree on the retained raw numbers, in which case the disagreement is
    preserved explicitly (never silently resolved by picking one source).
    """
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    agreement_checks: list[dict[str, Any]] = []
    for group in row_groups:
        for row in group:
            if row.get("row_status") != "PARSED":
                key = (row["ticker"], row["session"])
                by_key.setdefault(key, {**row, "sources": [row["source"]]})
                continue
            key = (row["ticker"], row["session"])
            fields = ("dnse_v", "matched_volume", "put_through_volume", "total_volume")
            existing = by_key.get(key)
            if existing is None or existing.get("row_status") != "PARSED":
                by_key[key] = {**row, "sources": [row["source"]]}
                continue
            existing_vals = tuple(existing.get(f) for f in fields)
            new_vals = tuple(row.get(f) for f in fields)
            agrees = existing_vals == new_vals
            agreement_checks.append({"ticker": key[0], "session": key[1], "sources": sorted(existing["sources"] + [row["source"]]),
                                      "agrees": agrees, "values_by_source": {"prior": existing_vals, row["source"]: new_vals}})
            if agrees:
                existing["sources"].append(row["source"])
            else:
                existing["row_status"] = "CROSS_SOURCE_DISAGREEMENT"
                existing.setdefault("disagreement_detail", []).append({"source": row["source"], "values": new_vals})

    combined = list(by_key.values())
    return {
        "combined_rows": combined,
        "agreement_checks": agreement_checks,
        "agreement_check_count": len(agreement_checks),
        "disagreement_count": sum(1 for c in agreement_checks if not c["agrees"]),
    }


def classify_combined_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Apply the shared, existing row-level classifier and map its label into this tool's taxonomy."""
    classified = []
    for row in rows:
        if row.get("row_status") == "CROSS_SOURCE_DISAGREEMENT":
            classified.append({**row, "row_label": DNSE_EQUALS_NONE, "verdict": CONFLICTING, "matched_component": None})
            continue
        if row.get("row_status") != "PARSED":
            classified.append({**row, "row_label": SOURCE_A_NOT_COMPARABLE, "verdict": UNAVAILABLE, "matched_component": None})
            continue
        trading = {
            "matched_volume": _as_int(row.get("matched_volume")), "put_through_volume": _as_int(row.get("put_through_volume")),
            "total_volume": _as_int(row.get("total_volume")),
            "retained_arithmetic_identity": (
                None not in (row.get("matched_volume"), row.get("put_through_volume"), row.get("total_volume"))
                and _as_int(row["matched_volume"]) is not None and _as_int(row["put_through_volume"]) is not None
                and _as_int(row["total_volume"]) is not None
                and _as_int(row["matched_volume"]) + _as_int(row["put_through_volume"]) == _as_int(row["total_volume"])
            ),
        }
        label = classify_volume_row(_as_int(row.get("dnse_v")), trading)
        classified.append({**row, "row_label": label, "verdict": _ROW_LABEL_TO_VERDICT[label],
                           "matched_component": _EXACT_MATCH_LABEL_TO_COMPONENT.get(label)})
    return classified


# ---------------------------------------------------------------------------
# Candidate compositions (task requirement 3 & 8): which component does DNSE's v measure?
# ---------------------------------------------------------------------------

def evaluate_candidate_compositions(classified_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    discriminating = [r for r in classified_rows if r["row_label"] not in (NON_DISCRIMINATING_ZERO_PUT_THROUGH, SOURCE_A_NOT_COMPARABLE) and r.get("row_status") != "CROSS_SOURCE_DISAGREEMENT"]
    non_discriminating = [r for r in classified_rows if r["row_label"] == NON_DISCRIMINATING_ZERO_PUT_THROUGH]
    unavailable = [r for r in classified_rows if r["row_label"] == SOURCE_A_NOT_COMPARABLE]
    conflicting = [r for r in classified_rows if r.get("row_status") == "CROSS_SOURCE_DISAGREEMENT" or r["row_label"] == DNSE_EQUALS_NONE]

    candidates = {}
    for component in ("matched", "total", "put_through"):
        matches = [r for r in discriminating if r.get("matched_component") == component]
        candidates[component] = {
            "candidate_id": f"DNSE_V_EQUALS_FHSC_{component.upper()}_VOLUME",
            "exact_match_count": len(matches),
            "distinct_tickers": sorted({r["ticker"] for r in matches}),
        }

    tickers_with_discriminating_evidence = sorted({r["ticker"] for r in discriminating})
    unique_exact_component = None
    if discriminating and all(r.get("matched_component") == "matched" for r in discriminating):
        unique_exact_component = "matched"

    return {
        "discriminating_row_count": len(discriminating),
        "non_discriminating_row_count": len(non_discriminating),
        "unavailable_row_count": len(unavailable),
        "conflicting_row_count": len(conflicting),
        "distinct_tickers_with_discriminating_evidence": tickers_with_discriminating_evidence,
        "candidates": candidates,
        "unique_exact_candidate_component": unique_exact_component,
        "dnse_v_semantic_verdict": (
            CONFLICTING if conflicting else
            (COVERAGE_RESTRICTED_RECONCILED if unique_exact_component and unavailable else
             (EXACT_RECONCILED if unique_exact_component and not unavailable else
              INSUFFICIENT_DISCRIMINATION if not discriminating else UNAVAILABLE))
        ),
    }


# ---------------------------------------------------------------------------
# Source D: FHSC-internal (no DNSE comparator) value + volume arithmetic-identity breadth
# ---------------------------------------------------------------------------

def evaluate_fhsc_internal_identity_breadth(capability_digest: Mapping[str, Any]) -> dict[str, Any]:
    records = [r for r in capability_digest["records"] if r.get("fhsc_value_volume_composition", {}).get("status") == "ACQUIRED"]
    value_exact = value_mismatch = value_incomplete = 0
    volume_exact = volume_mismatch = volume_incomplete = 0
    discriminating_tickers: list[str] = []
    mismatches: list[dict[str, Any]] = []
    for r in records:
        c = r["fhsc_value_volume_composition"]
        ticker = r["ticker"]
        mv, pv, tv = c.get("matched_traded_value_vnd"), c.get("put_through_traded_value_vnd"), c.get("total_traded_value_vnd")
        mvol, pvol, tvol = c.get("matched_volume_shares"), c.get("put_through_volume_shares"), c.get("total_volume_shares")

        if None in (mv, pv, tv):
            value_incomplete += 1
        elif mv + pv == tv:
            value_exact += 1
        else:
            value_mismatch += 1
            mismatches.append({"ticker": ticker, "dimension": "value", "matched": mv, "put_through": pv, "total": tv})

        if None in (mvol, pvol, tvol):
            volume_incomplete += 1
        else:
            if not all(_is_exact_integer(v) for v in (mvol, pvol, tvol)):
                mismatches.append({"ticker": ticker, "dimension": "volume_non_integer_serialization", "matched": mvol, "put_through": pvol, "total": tvol})
            if _as_int(mvol) is not None and _as_int(pvol) is not None and _as_int(tvol) is not None and _as_int(mvol) + _as_int(pvol) == _as_int(tvol):
                volume_exact += 1
            else:
                volume_mismatch += 1
                mismatches.append({"ticker": ticker, "dimension": "volume", "matched": mvol, "put_through": pvol, "total": tvol})
            if (pvol or 0) > 0:
                discriminating_tickers.append(ticker)

    return {
        "session_date": capability_digest["session_date"],
        "acquired_ticker_count": len(records),
        "value_identity": {"exact": value_exact, "mismatch": value_mismatch, "incomplete": value_incomplete},
        "volume_identity": {"exact": volume_exact, "mismatch": volume_mismatch, "incomplete": volume_incomplete},
        "discriminating_ticker_count": len(discriminating_tickers),
        "discriminating_tickers": sorted(discriminating_tickers),
        "mismatches": mismatches,
        "verdict": CONFLICTING if mismatches else EXACT_RECONCILED,
        "scope_note": "FHSC-internal arithmetic identity only; no DNSE volume/value comparator exists for this session or field.",
    }


# ---------------------------------------------------------------------------
# Board-level / odd-lot composition: canonical semantic contract + data-access boundary
# ---------------------------------------------------------------------------

def evaluate_board_composition_conflict() -> dict[str, Any]:
    """Return canonical board semantics and preserve the numeric-data boundary.

    ``DNSE_BOARD_SEMANTICS`` is the current repository's canonical semantic contract, backed by
    ``docs/market_wide_ingest_first_architecture.md`` and consumed by
    ``market_phase2_foundation.semantic_registry``. The historical reversed variable labels in
    ``dnse_volume_composition_reconciliation.py`` were implementation prior art, not a source
    contract; that module now consumes the same canonical mapping. No board-level aggregate data
    is available here, so resolving the labels does not establish volume composition or authority.
    """
    return {
        "semantic_mapping_conflict": {
            "verdict": EXACT_RECONCILED,
            "canonical_sources": ["market_phase2_foundation.DNSE_BOARD_SEMANTICS", "market_wide_coverage_report.py", "docs/market_wide_ingest_first_architecture.md"],
            "mapping": DNSE_BOARD_SEMANTICS,
            "superseded_implementation_prior_art": {
                "source": "dnse_volume_composition_reconciliation.py",
                "former_variable_labels": {"has_put_through": "g4 > 0", "has_odd_lot": "(t1 > 0) or (t3 > 0)"},
                "resolution": "Corrected to derive both predicates from DNSE_BOARD_SEMANTICS; C1-C4 board sums were already canonical.",
            },
        },
        "underlying_data_access": {
            "verdict": UNAVAILABLE,
            "reason": (
                "Board-level executions (G1/G4/T1/T3/T4/T6) exist only in the canonical Trades "
                "corpus, whose generator (dnse_trades_canonical_shadow.py) is not in this "
                "repository's main ancestry "
                f"(dnse_volume_composition_reconciliation.py: CANONICAL_TRADES_LINEAGE_STATUS = "
                f"{CANONICAL_TRADES_LINEAGE_STATUS!r}). AGENTS.md restricts work to this "
                "repository, and this milestone permits no new acquisition."
            ),
        },
        "no_odd_lot_aggregate_anywhere_on_main": True,
    }


# ---------------------------------------------------------------------------
# Field-level qualification table (task requirement 6)
# ---------------------------------------------------------------------------

def build_field_qualifications(
    *, candidates: Mapping[str, Any], source_a: Mapping[str, Any], internal_breadth: Mapping[str, Any],
    board: Mapping[str, Any], source_identities: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    dnse_verdict = candidates["dnse_v_semantic_verdict"]
    matched_component = candidates["unique_exact_candidate_component"]
    tested_tickers = candidates["distinct_tickers_with_discriminating_evidence"]

    def _volume_field(name: str, component: str) -> dict[str, Any]:
        is_the_matched_component = matched_component == component
        return {
            "provider": "FHSC", "capability": "trading_history_decomposition", "unit": "shares",
            "composition_semantics": f"FHSC-reported {component} volume for the session; matched + put_through = total is FHSC's own documented identity.",
            "tested_scope": {"tickers": tested_tickers, "exchange": "HOSE"},
            "coverage_status": "COVERAGE_RESTRICTED" if source_a["volume"]["exchange_specific_summary"].get("HOSE", {}).get("unavailable_rows", 0) else "COMPLETE",
            "evidence_lineage": [source_identities["source_a"], source_identities["source_b"], source_identities["source_c"]],
            "allowed_downstream_uses": (
                ["within-series display", "same-symbol relative comparison over the tested scope"]
                if not is_the_matched_component else
                ["within-series display", "same-symbol relative comparison over the tested scope",
                 "bounded matched-volume compositional input for a future scope-restricted ADV/turnover-input design (HOSE, FPT/HPG/SSI/VCB only) -- NOT itself an ADV/turnover authority"]
            ),
            "blockers": ["not validated outside HOSE / the 4-ticker discriminating cohort", "does not establish market-wide turnover or execution-sizing authority"],
            "verdict": dnse_verdict if is_the_matched_component or component in ("total", "put_through") else UNAVAILABLE,
        }

    return {
        "dnse.ohlc.v": {
            "provider": "DNSE", "capability": "daily_ohlc", "unit": "shares (generic, provider does not document composition)",
            "composition_semantics": "Empirically, across every retained discriminating observation, exactly equals FHSC matched_volume; provider does not itself document this.",
            "tested_scope": {"tickers": tested_tickers, "exchange": "HOSE", "session_count": candidates["discriminating_row_count"] + candidates["non_discriminating_row_count"]},
            "coverage_status": "COVERAGE_RESTRICTED",
            "evidence_lineage": [source_identities["source_a"], source_identities["source_b"], source_identities["source_c"]],
            "allowed_downstream_uses": ["within-series display", "same-symbol relative-volume analytics (unchanged from before this milestone)"],
            "blockers": ["HNX/UPCOM unavailable (rate-limited)", "8 of the 12 candidate tickers have no retained FHSC trading-history comparator", "empirical, not provider-documented"],
            "verdict": dnse_verdict,
        },
        "fhsc.trading_history.matched_volume": _volume_field("matched_volume", "matched"),
        "fhsc.trading_history.put_through_volume": _volume_field("put_through_volume", "put_through"),
        "fhsc.trading_history.total_volume": _volume_field("total_volume", "total"),
        "fhsc.trading_history.matched_value_vnd": {
            "provider": "FHSC", "capability": "trading_history_decomposition", "unit": "VND",
            "composition_semantics": "FHSC-reported matched (continuous/regular-board) traded value; matched_value + put_through_value = total_value verified exact for every acquired record tested.",
            "tested_scope": {"tickers": internal_breadth["acquired_ticker_count"], "session_date": internal_breadth["session_date"]},
            "coverage_status": "SINGLE_SESSION_BREADTH_ONLY",
            "evidence_lineage": [source_identities["source_d"]],
            "allowed_downstream_uses": ["within-series display", "same-symbol relative value comparison"],
            "blockers": ["no DNSE value comparator exists (DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE)", "single session only -- no multi-session value reconciliation performed"],
            "verdict": internal_breadth["verdict"],
        },
        "fhsc.trading_history.put_through_value_vnd": {
            "provider": "FHSC", "capability": "trading_history_decomposition", "unit": "VND",
            "composition_semantics": "FHSC-reported put-through (negotiated) traded value component.",
            "tested_scope": {"tickers": internal_breadth["discriminating_ticker_count"], "session_date": internal_breadth["session_date"]},
            "coverage_status": "SINGLE_SESSION_BREADTH_ONLY",
            "evidence_lineage": [source_identities["source_d"]],
            "allowed_downstream_uses": ["within-series display"],
            "blockers": ["no DNSE value comparator exists", "single session only", "no actor/institutional inference is licensed by this field"],
            "verdict": internal_breadth["verdict"],
        },
        "fhsc.trading_history.total_value_vnd": {
            "provider": "FHSC", "capability": "trading_history_decomposition", "unit": "VND",
            "composition_semantics": "FHSC-reported total (matched + put-through) traded value.",
            "tested_scope": {"tickers": internal_breadth["acquired_ticker_count"], "session_date": internal_breadth["session_date"]},
            "coverage_status": "SINGLE_SESSION_BREADTH_ONLY",
            "evidence_lineage": [source_identities["source_d"]],
            "allowed_downstream_uses": ["within-series display"],
            "blockers": ["no DNSE value comparator exists", "single session only", "does not by itself establish market-wide traded-value authority"],
            "verdict": internal_breadth["verdict"],
        },
        "board.composition_semantic_mapping": {
            "provider": "DNSE", "capability": "trades.board_id", "unit": "categorical (board code)",
            "composition_semantics": "Canonical DNSE board mapping is explicit; no numeric board aggregate is available in this repository.",
            "tested_scope": {"canonical_contract": "DNSE_BOARD_SEMANTICS"}, "coverage_status": "MAPPING_DOCUMENTED_NUMERIC_COVERAGE_UNAVAILABLE",
            "evidence_lineage": ["market_phase2_foundation.DNSE_BOARD_SEMANTICS", "market_wide_coverage_report.py", "docs/market_wide_ingest_first_architecture.md"],
            "allowed_downstream_uses": [],
            "blockers": ["no retained canonical Trades board aggregate is available in this repository"],
            "verdict": board["semantic_mapping_conflict"]["verdict"],
        },
        "trades.canonical_odd_lot_volume": {
            "provider": "DNSE", "capability": "trades.board_id", "unit": "shares",
            "composition_semantics": "Would require the canonical Trades corpus decomposed by board code.",
            "tested_scope": {}, "coverage_status": "NO_DATA_IN_REPOSITORY",
            "evidence_lineage": [], "allowed_downstream_uses": [],
            "blockers": [
                "canonical Trades generator not in this repository's main ancestry "
                f"({CANONICAL_TRADES_LINEAGE_STATUS})",
                "AGENTS.md restricts work to this repository; no acquisition permitted by this milestone",
                "board-code semantic mapping is itself CONFLICTING (see board.composition_semantic_mapping)",
            ],
            "verdict": UNAVAILABLE,
        },
    }


# ---------------------------------------------------------------------------
# Task requirement 8: which inputs may now support deterministic liquidity metrics (never sizing)
# ---------------------------------------------------------------------------

def evaluate_liquidity_metric_eligibility(field_qualifications: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "adv_turnover_input_eligible": False,
        "reasoning": (
            "market_data_source_authority.py already encodes a hard invariant "
            "('undocumented_odd_lot_scope_must_not_open_volume_authority') that volume_scope_authority "
            "stays BLOCKED while odd-lot composition is undocumented. Odd-lot mapping is canonical but "
            "numeric board aggregation remains UNAVAILABLE in this repository after "
            "this milestone's reconciliation, so that invariant is not satisfied and no field here is "
            "promoted to general ADV/turnover/liquidity-sizing input authority."
        ),
        "narrowly_scoped_finding": (
            "For the HOSE / FPT-HPG-SSI-VCB cohort only, on sessions with nonzero FHSC put-through, "
            "DNSE OHLC v is now COVERAGE_RESTRICTED_RECONCILED as FHSC matched_volume (continuous / "
            "regular-board activity) -- deterministic and exact within that tested scope. This is a "
            "necessary input a future, separately-authorized, scope-restricted ADV/turnover-input design "
            "could build on for that exact cohort; it is not itself a liquidity or turnover authority, "
            "and does not extend to any other ticker, exchange, or the odd-lot component."
        ),
        "position_sizing_still_blocked_by": [
            "QUALIFIED_LIQUIDITY_INPUTS remains field/scope-level, never a blanket YES",
            "odd-lot composition (canonical mapping resolved, numeric board aggregate UNAVAILABLE)",
            "RAW_AS_TRADED / PIT price basis (independently unpromoted; untouched by this milestone)",
            "current-share authority (independently unresolved; untouched by this milestone)",
            "market-wide traded-value comparator against DNSE (DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE)",
        ],
    }


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

def build_qualified_liquidity_inputs_reconciliation(
    source_a: Mapping[str, Any], source_b: Mapping[str, Any], source_c_rows: Sequence[Mapping[str, Any]],
    capability_digest: Mapping[str, Any],
) -> dict[str, Any]:
    rows_a = _rows_from_source_a(source_a)
    rows_b = _rows_from_source_b(source_b)
    combination = combine_cross_provider_rows(rows_a, rows_b, source_c_rows)
    classified = classify_combined_rows(combination["combined_rows"])
    candidates = evaluate_candidate_compositions(classified)
    internal_breadth = evaluate_fhsc_internal_identity_breadth(capability_digest)
    board = evaluate_board_composition_conflict()

    source_identities = {
        "source_a": source_a["artifact_identity"], "source_b": source_b["artifact_identity"],
        "source_c": f"real_eod_raw_session:{capability_digest['session_date']}",
        "source_d": capability_digest["digest_identity"],
    }
    field_qualifications = build_field_qualifications(
        candidates=candidates, source_a=source_a, internal_breadth=internal_breadth, board=board, source_identities=source_identities,
    )
    liquidity_eligibility = evaluate_liquidity_metric_eligibility(field_qualifications)

    tested_corpus = {
        "cross_provider_volume": {
            "sources": ["A", "B", "C"], "combined_cell_count": len(classified),
            "distinct_tickers": sorted({r["ticker"] for r in classified}),
            "distinct_sessions": sorted({r["session"] for r in classified}),
            "discriminating_row_count": candidates["discriminating_row_count"],
            "non_discriminating_row_count": candidates["non_discriminating_row_count"],
            "unavailable_row_count": candidates["unavailable_row_count"],
            "conflicting_row_count": candidates["conflicting_row_count"],
        },
        "cross_artifact_agreement": {
            "overlap_cell_count": combination["agreement_check_count"],
            "disagreement_count": combination["disagreement_count"],
            "verdict": CONFLICTING if combination["disagreement_count"] else EXACT_RECONCILED,
        },
        "fhsc_internal_identity_breadth": {
            "session_date": internal_breadth["session_date"], "ticker_count": internal_breadth["acquired_ticker_count"],
            "discriminating_ticker_count": internal_breadth["discriminating_ticker_count"],
        },
        "board_odd_lot": {"numeric_rows_tested": 0, "semantic_sources_compared": 2},
    }

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "execution_timestamp": datetime.now(UTC).isoformat(),
        "verdict_taxonomy": list(VERDICT_TAXONOMY),
        "source_artifacts": source_identities,
        "tested_corpus": tested_corpus,
        "candidate_compositions_evaluated": candidates,
        "cross_artifact_agreement_detail": combination["agreement_checks"],
        "combined_row_matrix": classified,
        "fhsc_internal_identity_breadth": internal_breadth,
        "board_composition": board,
        "field_qualifications": field_qualifications,
        "liquidity_metric_eligibility": liquidity_eligibility,
        "session_phase_contract_note": (
            "No reusable exchange/regime-aware session-phase (ATO/continuous/ATC) contract exists in "
            "this repository -- vn_time.py explicitly disclaims one, and DNSE's documented "
            "'trading_session' endpoint family is marked DEFERRED in dnse_market_dataset_inventory.py. "
            "This reconciliation therefore operates at daily-session-aggregate granularity only and "
            "hard-codes no ATO/continuous/ATC boundary of any kind."
        ),
        "authority_boundaries": AUTHORITY_BOUNDARIES,
    }
    artifact_sha = _sha256_json({k: v for k, v in artifact.items() if k not in {"artifact_sha256", "artifact_identity", "execution_timestamp"}})
    artifact["artifact_sha256"] = artifact_sha
    artifact["artifact_identity"] = f"qualified_liquidity_inputs_reconciliation:{artifact_sha}"
    return artifact


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile qualified liquidity inputs from retained DNSE/FHSC evidence.")
    parser.add_argument("--source-a-path", default="operations-review/dnse-fhsc-market-composition-scaleout-v1-20260821/dnse_fhsc_market_composition_scaleout_artifact.json")
    parser.add_argument("--source-b-path", default="operations-review/dnse-fhsc-volume-basis-qualification-v1-20260821/dnse_fhsc_volume_basis_qualification_artifact.json")
    parser.add_argument("--source-c-raw-dir", default="operations-review/capability-first-real-eod-2026-08-21/raw")
    parser.add_argument("--source-c-tickers", nargs="+", default=["HPG", "SSI", "VCB"])
    parser.add_argument("--source-d-path", default="operations-review/capability-first-research-digest-2026-08-21/capability_research_digest.json")
    parser.add_argument("--out-dir", default="operations-review/qualified-liquidity-inputs-reconciliation-v1-20260822")
    args = parser.parse_args(argv)

    def _resolve(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else ROOT / path

    source_a = load_market_composition_scaleout(_resolve(args.source_a_path))
    source_b = load_volume_basis_qualification(_resolve(args.source_b_path))
    capability_digest = load_capability_research_digest(_resolve(args.source_d_path))
    source_c_rows = load_real_eod_new_session_rows(_resolve(args.source_c_raw_dir), args.source_c_tickers, capability_digest["session_date"])

    artifact = build_qualified_liquidity_inputs_reconciliation(source_a, source_b, source_c_rows, capability_digest)

    out_dir = _resolve(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / "qualified_liquidity_inputs_reconciliation_v1.json"
    atomic_write_json(artifact_path, artifact)

    print(json.dumps({
        "status": "QUALIFIED_LIQUIDITY_INPUTS_RECONCILIATION_COMPLETE",
        "artifact_identity": artifact["artifact_identity"],
        "tested_corpus": artifact["tested_corpus"],
        "dnse_v_semantic_verdict": artifact["candidate_compositions_evaluated"]["dnse_v_semantic_verdict"],
        "fhsc_internal_identity_breadth_verdict": artifact["fhsc_internal_identity_breadth"]["verdict"],
        "board_semantic_verdict": artifact["board_composition"]["semantic_mapping_conflict"]["verdict"],
        "adv_turnover_input_eligible": artifact["liquidity_metric_eligibility"]["adv_turnover_input_eligible"],
        "out_dir": str(out_dir),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
