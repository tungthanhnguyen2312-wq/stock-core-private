"""DATA_INTEGRITY_AND_TACTICAL_REFERENCE_INTEGRATION_V1 -- final bypass corrective.

Two consumers bypassed the shared session_bar_integrity contract:

1. mva_daily_research_bundle projected bars to (date, close, volume) BEFORE any duplicate decision
   and built its cohort with a last-row-wins date map, so two bars differing only in ``high`` (or in
   price-basis identity) became one accepted tactical row.
2. market_wide_historical_research_context excluded rows after T0 from the shared decision but then
   fed them into a last-wins session map, so conflicting future rows could change the T0 output
   by row order alone.

Order now enforced: full T0-eligible bars -> session_bar_integrity -> projection / calculations.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import market_wide_historical_research_context as historical_module
import mva_daily_research_bundle as bundle_module
import session_bar_integrity as integrity

T0 = "2026-09-16"
BASIS = "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED"


def _days(end: str, count: int) -> list[str]:
    d, out = date.fromisoformat(end), []
    while len(out) < count:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return list(reversed(out))


def _bar(session: str, close: float, volume: int = 1000, **extra) -> dict:
    row = {"session": session, "open": close, "high": close + 0.5, "low": close - 0.5, "close": close, "volume": volume,
           "provider": "DNSE", "dataset": "DNSE_OHLC_1D", "price_basis": BASIS,
           "transformation_identity": "identity_provider_numeric_ohlc/v1", "retrieved_at": "2026-09-16T17:03:15+07:00"}
    row.update(extra)
    return row


def _series(n: int, *, end: str = T0) -> list[dict]:
    return [_bar(day, 20.0 + (i % 7) * 0.3 + i * 0.05, 1000 + i) for i, day in enumerate(_days(end, n))]


PRIOR = _days(T0, 2)[0]


def _with_twin(rows: list[dict], session: str, **changes) -> list[dict]:
    out = []
    for row in rows:
        out.append(row)
        if row["session"] == session:
            out.append({**copy.deepcopy(row), **changes})
    return out


# ── BYPASS 1: MVA bundle ────────────────────────────────────────────────────────────────

class MvaProjectionBoundaryTests(unittest.TestCase):
    def _snapshot(self, tmp: Path, observations_by_ticker: dict[str, list[dict]]) -> Path:
        sessions = _days(T0, bundle_module.LOOKBACK_SESSIONS)
        payload = {"retained_snapshot_session": T0, "resolved_completed_session": T0, "sessions": sessions,
                   "source": {"intraday_observations_used": False}, "snapshot_identity": "p3f9_exact_session_snapshot:test",
                   "records": {t: {"status": "OBSERVED", "observations": obs} for t, obs in observations_by_ticker.items()}}
        path = tmp / "snapshot.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _root(self, tmp: Path) -> Path:
        ops = tmp / "operations-review"
        for folder, name, payload in (
            ("p3f3-operational-valuation-input-scaleout-20260820", "p3f3_operational_valuation_input_scaleout_artifact.json",
             {"valuation_session": {"valuation_session": T0}, "artifact_identity": "p3f3:test", "both_ready_matrix": []}),
            ("p3b-fundamental-research-readiness-20260820", "p3b_fundamental_research_readiness_artifact.json", {"issuer_research_readiness": []}),
            ("p3f6-mva-provider-share-proxy-20260820", "p3f6_mva_provider_share_proxy_artifact.json", {"proxy_valuation_rows": []}),
        ):
            (ops / folder).mkdir(parents=True)
            (ops / folder / name).write_text(json.dumps(payload), encoding="utf-8")
        return tmp

    def _build(self, observations_by_ticker):
        with TemporaryDirectory() as raw:
            tmp = Path(raw)
            artifact = bundle_module.build_mva_daily_research_bundle(tmp, root=self._root(tmp), snapshot_path=self._snapshot(tmp, observations_by_ticker))
        return {r["identity"]["canonical_ticker"]: r for r in artifact["records"]}, artifact

    def test_high_only_conflict_is_refused_in_both_row_orders(self) -> None:
        clean = _series(25)
        twin = _with_twin(clean, PRIOR, high=99.0)
        for rows in (twin, list(reversed(twin))):
            records, artifact = self._build({"ACG": rows, "CLN": clean})
            acg = records["ACG"]
            self.assertFalse(acg["empirical_active_cohort_member"])
            self.assertEqual(acg["market_features"]["status"], "MISSING")
            self.assertEqual(acg["market_features"]["blockers"], [integrity.REFUSAL_REASON])
            self.assertEqual(acg["market_features"]["values"], {})
            self.assertTrue(records["CLN"]["empirical_active_cohort_member"])
            self.assertEqual(artifact["market_summary"]["observed_market_candidates"], 2)

    def test_basis_identity_only_conflict_is_refused(self) -> None:
        clean = _series(25)
        records, _ = self._build({"BAS": _with_twin(clean, PRIOR, price_basis="CURRENT_DESCRIPTIVE_NOT_PROMOTED_RAW_AS_TRADED")})
        self.assertEqual(records["BAS"]["market_features"]["blockers"], [integrity.REFUSAL_REASON])
        records, _ = self._build({"TRN": _with_twin(clean, PRIOR, transformation_identity="other/v1")})
        self.assertEqual(records["TRN"]["market_features"]["blockers"], [integrity.REFUSAL_REASON])

    def test_exact_duplicate_collapses_to_the_clean_result(self) -> None:
        clean = _series(25)
        dup, _ = self._build({"EXA": _with_twin(clean, PRIOR)})
        ref, _ = self._build({"EXA": clean})
        self.assertEqual(dup["EXA"]["market_features"], ref["EXA"]["market_features"])
        self.assertEqual(dup["EXA"]["market_features"]["status"], "SHADOW_ONLY")

    def test_integrity_runs_on_full_bars_before_projection(self) -> None:
        clean = _series(25)
        with TemporaryDirectory() as raw:
            path = self._snapshot(Path(raw), {"ACG": _with_twin(clean, PRIOR, high=99.0), "CLN": clean})
            candidates, grouped, sessions, frozen, refused = bundle_module._load_snapshot_market(path)
        self.assertNotIn("ACG", grouped)
        self.assertEqual(refused["ACG"]["conflicting_fields"], {PRIOR: ["high"]})
        self.assertEqual(refused["ACG"]["reason"], integrity.REFUSAL_REASON)
        # The projected rows could not have seen the conflict: they carry no ``high``.
        self.assertEqual(set(grouped["CLN"][0]), {"date", "close", "volume", "source"})

    def test_runtime_database_path_resolves_full_rows_before_projection(self) -> None:
        clean = _series(25)
        with TemporaryDirectory() as raw:
            runtime = Path(raw)
            connection = sqlite3.connect(runtime / "vn_stock.db")
            connection.execute("CREATE TABLE metadata (ticker TEXT)")
            connection.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, source TEXT)")
            for ticker, rows in (("ACG", _with_twin(clean, PRIOR, high=99.0)), ("CLN", clean)):
                connection.execute("INSERT INTO metadata VALUES (?)", (ticker,))
                for r in rows:
                    connection.execute("INSERT INTO ohlcv VALUES (?,?,?,?,?,?,?,?)", (ticker, r["session"], r["open"], r["high"], r["low"], r["close"], r["volume"], "VCI"))
            connection.commit()
            connection.close()
            candidates, grouped, sessions, refused = bundle_module._load_runtime_market(runtime, frozen_session=T0)
        self.assertEqual(sorted(refused), ["ACG"])
        self.assertEqual(refused["ACG"]["conflicting_fields"], {PRIOR: ["high"]})
        self.assertEqual(len(grouped["CLN"]), bundle_module.LOOKBACK_SESSIONS)

    def test_cohort_never_uses_last_row_wins(self) -> None:
        sessions = _days(T0, bundle_module.LOOKBACK_SESSIONS)
        rows = [{"date": s, "close": 10.0 + i, "volume": 100} for i, s in enumerate(sessions)]
        conflicting = rows + [{"date": sessions[-2], "close": 999.0, "volume": 100}]
        for ordering in (conflicting, list(reversed(conflicting))):
            cohort = bundle_module.derive_empirical_active_cohort({"AAA": ordering}, sessions=sessions, candidate_tickers=["AAA"])
            self.assertEqual(cohort["members"], [])
            self.assertEqual(cohort["exclusions"]["AAA"]["reason"], integrity.REFUSAL_REASON)
        exact = bundle_module.derive_empirical_active_cohort({"AAA": rows + [dict(rows[-2])]}, sessions=sessions, candidate_tickers=["AAA"])
        self.assertEqual(exact["members"], ["AAA"])


# ── BYPASS 2: historical context PIT boundary ──────────────────────────────────────────

def _strip_annotation(context: dict) -> dict:
    out = copy.deepcopy(context)
    out.get("history", {}).pop("session_bar_integrity", None)
    return out


class HistoricalPitBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clean = _series(80)
        self.reference = historical_module.evaluate_historical_context(self.clean, target_session=T0)
        self.assertEqual(self.reference["as_of_session"], T0)

    def test_conflicting_future_rows_never_influence_t0_in_either_order(self) -> None:
        future = "2026-09-17"
        a, b = _bar(future, 50.0, 7000), _bar(future, 5.0, 10)
        for rows in (self.clean + [a, b], self.clean + [b, a], [b] + self.clean + [a]):
            result = historical_module.evaluate_historical_context(rows, target_session=T0)
            self.assertEqual(result, self.reference)

    def test_any_future_row_is_excluded_before_the_series_is_built(self) -> None:
        later = [_bar("2026-09-17", 99.0), _bar("2026-09-18", 1.0)]
        self.assertEqual(historical_module.evaluate_historical_context(self.clean + later, target_session=T0), self.reference)

    def test_conflict_on_or_before_t0_fails_closed_with_the_shared_reason(self) -> None:
        for session in (T0, PRIOR, self.clean[10]["session"]):
            for rows in (_with_twin(self.clean, session, close=1.0), list(reversed(_with_twin(self.clean, session, close=1.0)))):
                result = historical_module.evaluate_historical_context(rows, target_session=T0)
                self.assertEqual(result["context_status"], "MISSING")
                self.assertEqual(result["drawdown"]["reason"], integrity.REFUSAL_REASON)
                self.assertEqual(result["history"]["session_bar_integrity"]["conflicting_sessions"], [session])

    def test_exact_duplicate_is_deterministic_and_equals_the_clean_series(self) -> None:
        rows = _with_twin(self.clean, PRIOR)
        for ordering in (rows, list(reversed(rows))):
            result = historical_module.evaluate_historical_context(ordering, target_session=T0)
            self.assertEqual(_strip_annotation(result), self.reference)
            self.assertEqual(result["history"]["session_bar_integrity"]["exact_duplicate_sessions"], [PRIOR])

    def test_no_last_wins_session_map_remains(self) -> None:
        with self.assertRaises(historical_module.MarketWideHistoricalResearchContextError):
            historical_module._observation_bars([_bar(PRIOR, 1.0), _bar(PRIOR, 2.0)])


if __name__ == "__main__":
    unittest.main()
