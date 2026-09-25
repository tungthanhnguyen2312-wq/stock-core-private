"""DATA_INTEGRITY_AND_TACTICAL_REFERENCE_INTEGRATION_V1 -- final MVA runtime ordering.

The runtime/database loader selected the latest 20 sessions BEFORE session_bar_integrity, so a
conflicting duplicate older than the window was sliced away and the ticker was admitted as
SHADOW_ONLY, while the snapshot path refused the same semantic input.

Order now enforced on both paths: full T0-eligible stored bars -> session_bar_integrity ->
latest-20 window -> projection. The same logical input must receive the same disposition.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import mva_daily_research_bundle as bundle_module
import session_bar_integrity as integrity

T0 = "2026-09-16"
BASIS = "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED"
COLUMNS = ("open", "high", "low", "close", "volume", "provider", "dataset", "price_basis", "transformation_identity", "retrieved_at")
STORED = 25


def _days(end: str, count: int) -> list[str]:
    d, out = date.fromisoformat(end), []
    while len(out) < count:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return list(reversed(out))


SESSIONS = _days(T0, STORED)
OLDEST = SESSIONS[0]  # session #1: outside the latest-20 window
WINDOW = SESSIONS[-bundle_module.LOOKBACK_SESSIONS:]


def _bar(session: str, close: float, volume: float) -> dict:
    return {"session": session, "open": close, "high": close + 0.5, "low": close - 0.5, "close": close, "volume": volume,
            "provider": "DNSE", "dataset": "DNSE_OHLC_1D", "price_basis": BASIS,
            "transformation_identity": "identity_provider_numeric_ohlc/v1", "retrieved_at": "2026-09-16T17:03:15+07:00"}


def _series() -> list[dict]:
    return [_bar(day, 20.0 + (i % 7) * 0.3 + i * 0.05, 1000.0 + i) for i, day in enumerate(SESSIONS)]


def _with_twin(rows: list[dict], session: str, **changes) -> list[dict]:
    out = []
    for row in rows:
        out.append(row)
        if row["session"] == session:
            out.append({**copy.deepcopy(row), **changes})
    return out


def _root(tmp: Path) -> Path:
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


def _write_runtime(runtime: Path, observations_by_ticker: dict[str, list[dict]]) -> None:
    """A stored ``ohlcv`` table WITHOUT a primary key, so duplicate (ticker, date) rows can exist."""
    connection = sqlite3.connect(runtime / "vn_stock.db")
    connection.execute("CREATE TABLE metadata (ticker TEXT)")
    connection.execute(f"CREATE TABLE ohlcv (ticker TEXT, date TEXT, {', '.join(COLUMNS)}, source TEXT)")
    for ticker, rows in observations_by_ticker.items():
        connection.execute("INSERT INTO metadata VALUES (?)", (ticker,))
        for row in rows:
            connection.execute(f"INSERT INTO ohlcv VALUES ({', '.join('?' for _ in range(len(COLUMNS) + 3))})",
                               (ticker, row["session"], *(row[c] for c in COLUMNS), "DNSE"))
    connection.commit()
    connection.close()


def _write_snapshot(tmp: Path, observations_by_ticker: dict[str, list[dict]]) -> Path:
    payload = {"retained_snapshot_session": T0, "resolved_completed_session": T0, "sessions": WINDOW,
               "source": {"intraday_observations_used": False}, "snapshot_identity": "p3f9_exact_session_snapshot:test",
               "records": {t: {"status": "OBSERVED", "observations": obs} for t, obs in observations_by_ticker.items()}}
    path = tmp / "snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _disposition(artifact: dict) -> dict:
    """The analytical disposition per ticker (not artifact bytes: the surfaces encode metadata differently)."""
    return {r["identity"]["canonical_ticker"]: {"member": r["empirical_active_cohort_member"], "status": r["market_features"]["status"],
                                                "blockers": r["market_features"].get("blockers"), "values": r["market_features"].get("values")}
            for r in artifact["records"]}


def _build_runtime(observations_by_ticker: dict[str, list[dict]]) -> dict:
    with TemporaryDirectory() as raw:
        tmp = Path(raw)
        _write_runtime(tmp, observations_by_ticker)
        return bundle_module.build_mva_daily_research_bundle(tmp, root=_root(tmp))


def _build_snapshot(observations_by_ticker: dict[str, list[dict]]) -> dict:
    with TemporaryDirectory() as raw:
        tmp = Path(raw)
        return bundle_module.build_mva_daily_research_bundle(tmp, root=_root(tmp), snapshot_path=_write_snapshot(tmp, observations_by_ticker))


def _load_runtime(observations_by_ticker: dict[str, list[dict]]):
    with TemporaryDirectory() as raw:
        tmp = Path(raw)
        _write_runtime(tmp, observations_by_ticker)
        return bundle_module._load_runtime_market(tmp, frozen_session=T0)


def _load_snapshot(observations_by_ticker: dict[str, list[dict]]):
    with TemporaryDirectory() as raw:
        return bundle_module._load_snapshot_market(_write_snapshot(Path(raw), observations_by_ticker))


CONFLICTS = {"high": {"high": 99.0},
             "price_basis": {"price_basis": "CURRENT_DESCRIPTIVE_NOT_PROMOTED_RAW_AS_TRADED"},
             "transformation_identity": {"transformation_identity": "other/v1"}}


class MvaRuntimeIntegrityOrderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clean = _series()
        self.assertNotIn(OLDEST, WINDOW)
        self.assertEqual(len(WINDOW), bundle_module.LOOKBACK_SESSIONS)

    # Probes A, B, C -- a conflict outside the selected window is refused, in either row order.
    def test_out_of_window_conflicts_are_refused_before_window_selection(self) -> None:
        for field, change in CONFLICTS.items():
            twin = _with_twin(self.clean, OLDEST, **change)
            for rows in (twin, list(reversed(twin))):
                with self.subTest(field=field, reversed=rows is not twin):
                    candidates, grouped, sessions, refused = _load_runtime({"ACG": rows, "CLN": self.clean})
                    self.assertEqual(sessions, WINDOW)
                    self.assertNotIn("ACG", grouped)
                    self.assertEqual(refused["ACG"]["reason"], integrity.REFUSAL_REASON)
                    self.assertEqual(refused["ACG"]["conflicting_sessions"], [OLDEST])
                    self.assertEqual(refused["ACG"]["conflicting_fields"], {OLDEST: [field]})
                    records = {r["identity"]["canonical_ticker"]: r for r in _build_runtime({"ACG": rows, "CLN": self.clean})["records"]}
                    self.assertFalse(records["ACG"]["empirical_active_cohort_member"])
                    self.assertEqual(records["ACG"]["market_features"], {"status": "MISSING", "values": {}, "blockers": [integrity.REFUSAL_REASON]})
                    self.assertTrue(records["CLN"]["empirical_active_cohort_member"])

    # Probe D -- an exact duplicate outside the window collapses; the window then proceeds normally.
    def test_out_of_window_exact_duplicate_collapses_deterministically(self) -> None:
        reference = _disposition(_build_runtime({"EXA": self.clean}))
        twin = _with_twin(self.clean, OLDEST)
        for rows in (twin, list(reversed(twin))):
            candidates, grouped, sessions, refused = _load_runtime({"EXA": rows})
            self.assertEqual(refused, {})
            self.assertEqual([row["date"] for row in grouped["EXA"]], WINDOW)
            self.assertEqual(_disposition(_build_runtime({"EXA": rows})), reference)
        self.assertEqual(reference["EXA"]["status"], "SHADOW_ONLY")

    # Probe E -- 25 clean sessions: latest 20 selected exactly as before.
    def test_clean_series_selects_the_latest_20_sessions(self) -> None:
        candidates, grouped, sessions, refused = _load_runtime({"CLN": self.clean})
        self.assertEqual(refused, {})
        self.assertEqual(sessions, WINDOW)
        self.assertEqual([row["date"] for row in grouped["CLN"]], WINDOW)
        self.assertEqual(set(grouped["CLN"][0]), {"date", "close", "volume", "source"})
        expected = [row["close"] for row in self.clean[-bundle_module.LOOKBACK_SESSIONS:]]
        self.assertEqual([row["close"] for row in grouped["CLN"]], expected)
        features = _disposition(_build_runtime({"CLN": self.clean}))["CLN"]
        self.assertEqual(features["values"]["ma_20"], sum(expected) / len(expected))
        self.assertEqual(features["values"]["momentum_20d"], expected[-1] / expected[0] - 1)

    def test_rows_after_t0_are_excluded_before_integrity(self) -> None:
        future = [_bar("2026-09-17", 50.0, 7000.0), _bar("2026-09-17", 5.0, 10.0)]
        candidates, grouped, sessions, refused = _load_runtime({"CLN": self.clean + future})
        self.assertEqual(refused, {})
        self.assertEqual([row["date"] for row in grouped["CLN"]], WINDOW)

    def test_ticker_without_window_rows_is_not_counted_as_observed(self) -> None:
        stale = [row for row in self.clean if row["session"] not in WINDOW]
        candidates, grouped, sessions, refused = _load_runtime({"CLN": self.clean, "OLD": stale})
        self.assertNotIn("OLD", grouped)
        self.assertEqual(refused, {})

    def test_spellings_of_one_symbol_are_resolved_as_one_series(self) -> None:
        split = {"MIX": self.clean[::2], "mix": self.clean[1::2]}
        candidates, grouped, sessions, refused = _load_runtime(split)
        self.assertEqual(refused, {})
        self.assertEqual([row["date"] for row in grouped["MIX"]], WINDOW)
        twin = {"MIX": self.clean, "mix": [{**self.clean[0], "high": 99.0}]}
        candidates, grouped, sessions, refused = _load_runtime(twin)
        self.assertNotIn("MIX", grouped)
        # The stored spelling is itself a retained field, so it is part of the conflict.
        self.assertEqual(refused["MIX"]["conflicting_fields"], {OLDEST: ["high", "ticker"]})

    # SNAPSHOT_RUNTIME_INTEGRITY_PARITY -- same logical input, same disposition and reference values.
    def test_snapshot_runtime_integrity_parity(self) -> None:
        inputs = {"CLN": self.clean,
                  "HIG": _with_twin(self.clean, OLDEST, **CONFLICTS["high"]),
                  "BAS": _with_twin(self.clean, OLDEST, **CONFLICTS["price_basis"]),
                  "TRN": _with_twin(self.clean, OLDEST, **CONFLICTS["transformation_identity"]),
                  "EXA": _with_twin(self.clean, OLDEST),
                  "INW": _with_twin(self.clean, WINDOW[-2], high=99.0)}
        for ordering in (inputs, {t: list(reversed(rows)) for t, rows in inputs.items()}):
            runtime, snapshot = _build_runtime(ordering), _build_snapshot(ordering)
            self.assertEqual(_disposition(runtime), _disposition(snapshot))
            self.assertEqual(runtime["empirical_active_cohort"]["members"], ["CLN", "EXA"])
            self.assertEqual(runtime["empirical_active_cohort"]["exclusion_reason_counts"], snapshot["empirical_active_cohort"]["exclusion_reason_counts"])
            self.assertEqual(runtime["market_summary"]["breadth"], snapshot["market_summary"]["breadth"])
            self.assertEqual(runtime["market_summary"]["observed_market_candidates"], snapshot["market_summary"]["observed_market_candidates"])
            self.assertEqual(_load_runtime(ordering)[3], _load_snapshot(ordering)[4])


if __name__ == "__main__":
    unittest.main()
