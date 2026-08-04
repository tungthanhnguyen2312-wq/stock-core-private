"""Contract tests for the bounded direct-VCI basis pilot.

Every fixture below is derived from a real, retained, redacted response shape. No test in
this module opens a socket: live acquisition is confined to
``vci_direct_basis_pilot.acquire`` and the runner script, neither of which is exercised
here against a real endpoint.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import vci_direct_basis_pilot as pilot

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = REPO_ROOT / "operations-review" / "vci-direct-basis-pilot-20260804"


def daily_fixture(symbol="VCB"):
    """Shape of the retained VCB gap-chart payload, three sessions across an ex-date."""
    return [
        {
            "symbol": symbol,
            "o": [56328.56, 54100, 54000],
            "h": [56626.07, 54900, 55300],
            "l": [54047.65, 52600, 53200],
            "c": [54047.65, 54000, 54100],
            "v": [9207098, 7464625, 2515532],
            "t": ["1784678400", "1784764800", "1784851200"],
            "accumulatedVolume": [9207098, 7464625, 2515532],
            "accumulatedValue": [508487.75, 398109.83, 135952.38],
            "minBatchTruncTime": "1784678400",
        }
    ]


def intraday_fixture():
    """Shape of the retained HPG matched-trade payload; every numeric is a string."""
    return [
        {
            "id": 502951720,
            "symbol": "HPG",
            "truncTime": "1785816198",
            "matchType": "b",
            "matchVol": "1700.0",
            "matchPrice": "22150.0",
            "accumulatedVolume": "9315300.0",
            "accumulatedValue": "207547.31",
        },
        {
            "id": 502951707,
            "symbol": "HPG",
            "truncTime": "1785816197",
            "matchType": "s",
            "matchVol": "100.0",
            "matchPrice": "22150.0",
            "accumulatedVolume": "9313600.0",
            "accumulatedValue": "207509.655",
        },
    ]


VCB_EVENTS = [
    {
        "ex_date": "2026-07-23",
        "kind": "cash",
        "detail": "DIV cash dividend, 450 VND/share",
        "evidence_identity": "vn_stock.db:corporate_event_records[provider=VCI,ticker=VCB,event_code=DIV,exright_date=2026-07-23]",
    }
]


class RawAndNormalizedIdentity(unittest.TestCase):
    """1. Raw provider fields and normalised fields keep distinct identities."""

    def test_raw_and_normalized_namespaces_do_not_overlap(self):
        raw_rows = pilot.parse_daily_payload(daily_fixture(), symbol="VCB")
        normalized = pilot.normalize_daily(raw_rows)
        raw_keys = set(raw_rows[0])
        normalized_keys = set(normalized["rows"][0])
        self.assertEqual(raw_keys & normalized_keys, set())
        self.assertTrue(all(key.startswith("vci.raw_") for key in raw_keys))
        self.assertTrue(all(key.startswith("vci.") for key in normalized_keys))
        # The raw value survives the normalisation step untouched.
        self.assertEqual(raw_rows[0]["vci.raw_close"], 54047.65)
        self.assertEqual(normalized["rows"][0]["vci.observed_close_vnd"], 54047.65)

    def test_scaling_and_rounding_are_declared_not_implicit(self):
        """2. Scaling and rounding transformations are explicit."""
        normalized = pilot.normalize_daily(pilot.parse_daily_payload(daily_fixture(), symbol="VCB"))
        scale = next(t for t in normalized["transformations"] if t["operation"] == "scale")
        self.assertEqual(scale["parameters"], {"factor": 1, "rounding": "none"})
        self.assertFalse(normalized["resampling_applied"])
        self.assertFalse(normalized["forward_fill_applied"])
        self.assertEqual(normalized["invented_sessions"], 0)
        self.assertEqual(normalized["transformation_code_identity"], pilot.TRANSFORMATION_CODE_IDENTITY)


class VerdictCannotBeUpgraded(unittest.TestCase):
    def base_verdict(self):
        rows = pilot.normalize_daily(pilot.parse_daily_payload(daily_fixture(), symbol="VCB"))["rows"]
        return pilot.classify_price_basis(
            lattice=pilot.lattice_profile(rows),
            boundary_date=pilot.lattice_boundary(rows),
            qualified_events=VCB_EVENTS,
        )

    def test_cross_provider_agreement_does_not_upgrade(self):
        """3. Price-basis verdicts cannot be upgraded from cross-provider agreement alone."""
        before = self.base_verdict()
        after = pilot.apply_cross_provider_agreement(
            before, agreement={"counterparty": "KBS", "sessions_compared": 9, "close_exact_matches": 9}
        )
        self.assertEqual(after["verdict"], before["verdict"])
        self.assertFalse(after["cross_provider_comparison_upgraded_verdict"])

        # Total agreement on a window that on its own says nothing must not create a verdict.
        inconclusive = pilot.classify_price_basis(
            lattice={"sessions_off_lattice": 0, "sessions_on_lattice": 3, "sessions_total": 3, "sessions": []},
            boundary_date=None,
            qualified_events=VCB_EVENTS,
        )
        upgraded = pilot.apply_cross_provider_agreement(
            inconclusive, agreement={"counterparty": "KBS", "sessions_compared": 250, "close_exact_matches": 250}
        )
        self.assertEqual(upgraded["verdict"], "inconclusive")

    def test_event_window_fit_does_not_replace_source_semantics(self):
        """4. An event-window numerical fit cannot replace source semantics."""
        inconclusive = pilot.classify_price_basis(
            lattice={"sessions_off_lattice": 0, "sessions_on_lattice": 3, "sessions_total": 3, "sessions": []},
            boundary_date=None,
            qualified_events=VCB_EVENTS,
        )
        fitted = pilot.apply_event_window_fit(
            inconclusive,
            fit={"distinct_close_ratios": [0.9917], "single_constant_factor": True, "r_squared": 1.0},
        )
        self.assertEqual(fitted["verdict"], "inconclusive")
        self.assertFalse(fitted["event_window_fit_upgraded_verdict"])

    def test_a_smooth_on_lattice_window_is_not_declared_raw(self):
        result = pilot.classify_price_basis(
            lattice={"sessions_off_lattice": 0, "sessions_on_lattice": 20, "sessions_total": 20, "sessions": []},
            boundary_date=None,
            qualified_events=VCB_EVENTS,
        )
        self.assertEqual(result["verdict"], "inconclusive")
        self.assertNotEqual(result["verdict"], "raw_unadjusted")

    def test_boundary_matching_a_qualified_event_names_the_dimension(self):
        result = self.base_verdict()
        self.assertEqual(result["verdict"], "dividend_adjusted")
        self.assertEqual(result["boundary_date"], "2026-07-23")
        self.assertTrue(result["excludes_raw_unadjusted"])

    def test_event_without_evidence_identity_is_rejected(self):
        rows = pilot.normalize_daily(pilot.parse_daily_payload(daily_fixture(), symbol="VCB"))["rows"]
        with self.assertRaises(pilot.VCIPilotError):
            pilot.classify_price_basis(
                lattice=pilot.lattice_profile(rows),
                boundary_date=pilot.lattice_boundary(rows),
                qualified_events=[{"ex_date": "2026-07-23", "kind": "cash", "evidence_identity": "  "}],
            )


class VolumeStaysUnknown(unittest.TestCase):
    def test_market_scope_stays_unknown_whatever_the_reconciliation(self):
        """5. Unknown volume-market scope remains unknown."""
        for verdict in sorted(pilot.VOLUME_RECONCILIATION_VERDICTS):
            declaration = pilot.volume_basis_declaration(
                field_identity_qualified=True,
                unit_verdict="qualified",
                adjustment_verdict="qualified",
                reconciliation={"verdict": verdict},
            )
            self.assertEqual(declaration["volume_market_scope"], "unknown")
            self.assertFalse(declaration["liquidity_actionable"])

    def test_incomplete_pagination_is_not_a_reconciliation(self):
        """6. Incomplete intraday pagination cannot be treated as a daily-volume reconciliation."""
        result = pilot.reconcile_volume(
            daily_volume=9_315_300,
            intraday_quantities=[1700, 100],
            intraday_page_size=30_000,
            intraday_rows_returned=100,
            intraday_covers_full_session=False,
        )
        self.assertEqual(result["verdict"], "intraday_sample_incomplete")

        # A capped page that happens to fill exactly must not read as complete either.
        capped = pilot.reconcile_volume(
            daily_volume=1800,
            intraday_quantities=[1700, 100],
            intraday_page_size=2,
            intraday_rows_returned=2,
            intraday_covers_full_session=True,
        )
        self.assertEqual(capped["verdict"], "intraday_sample_incomplete")

    def test_daily_exceeding_intraday_sum_needs_a_complete_sample_first(self):
        complete = pilot.reconcile_volume(
            daily_volume=5000,
            intraday_quantities=[1700, 100],
            intraday_page_size=100,
            intraday_rows_returned=2,
            intraday_covers_full_session=True,
        )
        self.assertEqual(complete["verdict"], "daily_exceeds_observed_intraday_sum")
        self.assertIn("also with any unobserved trade", complete["note"])

    def test_missing_volume_stays_missing(self):
        """7. Missing volume remains missing and is not converted to zero."""
        payload = daily_fixture()
        payload[0]["v"] = [None, 7_464_625, 2_515_532]
        raw_rows = pilot.parse_daily_payload(payload, symbol="VCB")
        self.assertIsNone(raw_rows[0]["vci.raw_volume"])
        normalized = pilot.normalize_daily(raw_rows)
        self.assertIsNone(normalized["rows"][0]["vci.observed_daily_volume"])
        self.assertEqual(
            pilot.reconcile_volume(
                daily_volume=None,
                intraday_quantities=[1],
                intraday_page_size=10,
                intraday_rows_returned=1,
                intraday_covers_full_session=True,
            )["verdict"],
            "scope_inconclusive",
        )

    def test_accumulator_consistency_qualifies_the_unit_only(self):
        rows = pilot.parse_intraday_payload(intraday_fixture(), symbol="HPG")
        consistency = pilot.intraday_accumulator_consistency(rows)
        self.assertEqual(consistency["verdict"], "accumulators_internally_consistent")
        self.assertEqual(consistency["implied_accumulated_value_scale_to_vnd"], [1_000_000])
        declaration = pilot.volume_basis_declaration(
            field_identity_qualified=True,
            unit_verdict="qualified",
            adjustment_verdict="unknown",
            reconciliation=None,
        )
        self.assertEqual(declaration["volume_unit"], "qualified")
        self.assertEqual(declaration["volume_market_scope"], "unknown")


class FailClosed(unittest.TestCase):
    """8. Malformed, empty, wrong-symbol or duplicate payloads fail closed."""

    def test_empty_and_malformed(self):
        for payload in ([], {}, None, [{}], [{"symbol": "VCB"}], "[]"):
            with self.assertRaises(pilot.VCIPilotError):
                pilot.parse_daily_payload(payload, symbol="VCB")

    def test_wrong_symbol(self):
        payload = daily_fixture(symbol="HPG")
        with self.assertRaises(pilot.VCIPilotError) as ctx:
            pilot.parse_daily_payload(payload, symbol="VCB")
        self.assertIn("symbol_mismatch", str(ctx.exception))

    def test_duplicate_and_unordered_sessions(self):
        payload = daily_fixture()
        payload[0]["t"] = ["1784678400", "1784678400", "1784851200"]
        with self.assertRaises(pilot.VCIPilotError) as ctx:
            pilot.parse_daily_payload(payload, symbol="VCB")
        self.assertIn("duplicate_session", str(ctx.exception))

        payload = daily_fixture()
        payload[0]["t"] = ["1784851200", "1784764800", "1784678400"]
        with self.assertRaises(pilot.VCIPilotError):
            pilot.parse_daily_payload(payload, symbol="VCB")

    def test_ragged_arrays_and_inconsistent_bars(self):
        payload = daily_fixture()
        payload[0]["v"] = [1, 2]
        with self.assertRaises(pilot.VCIPilotError):
            pilot.parse_daily_payload(payload, symbol="VCB")

        payload = daily_fixture()
        payload[0]["l"] = [99_999.0, 52600, 53200]
        with self.assertRaises(pilot.VCIPilotError) as ctx:
            pilot.parse_daily_payload(payload, symbol="VCB")
        self.assertIn("ohlc_inconsistent", str(ctx.exception))

    def test_zero_sessions_and_missing_price(self):
        payload = daily_fixture()
        for field in pilot._DAILY_ARRAY_FIELDS:
            payload[0][field] = []
        with self.assertRaises(pilot.VCIPilotError) as ctx:
            pilot.parse_daily_payload(payload, symbol="VCB")
        self.assertIn("zero_sessions", str(ctx.exception))

        payload = daily_fixture()
        payload[0]["c"] = [None, 54000, 54100]
        with self.assertRaises(pilot.VCIPilotError):
            pilot.parse_daily_payload(payload, symbol="VCB")

    def test_intraday_rejects_duplicates_wrong_symbol_and_fractional_quantity(self):
        rows = intraday_fixture()
        rows[1]["id"] = rows[0]["id"]
        with self.assertRaises(pilot.VCIPilotError):
            pilot.parse_intraday_payload(rows, symbol="HPG")

        rows = intraday_fixture()
        rows[0]["symbol"] = "VNM"
        with self.assertRaises(pilot.VCIPilotError):
            pilot.parse_intraday_payload(rows, symbol="HPG")

        rows = intraday_fixture()
        rows[0]["matchVol"] = "1700.5"
        with self.assertRaises(pilot.VCIPilotError):
            pilot.parse_intraday_payload(rows, symbol="HPG")

    def test_out_of_scope_ticker_and_endpoint(self):
        with self.assertRaises(pilot.VCIPilotError):
            pilot.daily_payload("FPT", to_epoch=1785542400, count_back=5)
        with self.assertRaises(pilot.VCIPilotError):
            pilot.assert_endpoint_in_scope("https://trading.vietcap.com.vn/api/chart/OHLCChart/other")
        with self.assertRaises(pilot.VCIPilotError):
            pilot.daily_payload("VCB", to_epoch=1785542400, count_back=5000)


class RedirectBoundary(unittest.TestCase):
    """9. Redirects outside the observed provider boundary are rejected."""

    def test_off_host_redirect_rejected(self):
        for location in (
            "https://evil.example.com/api/chart",
            "http://trading.vietcap.com.vn.attacker.net/api",
            "https://apipubaws.tcbs.com.vn/stock-insight",
        ):
            with self.assertRaises(pilot.VCIPilotError):
                pilot.assert_redirect_within_boundary(location)

    def test_same_host_and_relative_redirects_allowed(self):
        pilot.assert_redirect_within_boundary("https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart")
        pilot.assert_redirect_within_boundary("/api/chart/OHLCChart/gap-chart")
        pilot.assert_redirect_within_boundary(None)


class SecretsNeverPersisted(unittest.TestCase):
    """10. Secrets, cookies and sensitive headers never enter evidence artifacts."""

    def observation_kwargs(self, **overrides):
        kwargs = {
            "provider": "VCI",
            "source_authority": pilot.SOURCE_AUTHORITY,
            "endpoint": pilot.DAILY_ENDPOINT,
            "method": "POST",
            "request_parameters": {"timeFrame": "ONE_DAY", "symbols": ["VCB"], "to": 1785542400, "countBack": 25},
            "request_headers_redacted": {"Content-Type": "application/json", "Cookie": "session=abc123"},
            "retrieved_at": "2026-08-04T04:03:17Z",
            "http_status": 200,
            "redirect_count": 0,
            "retry_count": 0,
            "raw_response_sha256": "0" * 64,
            "response_schema_fingerprint": "1" * 64,
            "ticker": "VCB",
            "interval": "1D",
            "requested_date_range": ["2026-07-01", "2026-07-31"],
            "returned_date_range": ["2026-06-29", "2026-07-31"],
            "raw_field_names": ["c", "h", "l", "o", "symbol", "t", "v"],
            "normalized_field_names": ["vci.observed_close_vnd"],
            "transformations": [],
            "transformation_code_identity": pilot.TRANSFORMATION_CODE_IDENTITY,
            "qualification_verdict": "dividend_adjusted",
            "unresolved_semantic_dimensions": ["volume_market_scope"],
        }
        kwargs.update(overrides)
        return kwargs

    def test_sensitive_headers_are_redacted_in_the_record(self):
        record = pilot.build_observation(**self.observation_kwargs())
        self.assertEqual(record["request_headers_redacted"]["Cookie"], pilot.REDACTED)
        self.assertNotIn("abc123", json.dumps(record))

    def test_a_secret_smuggled_into_a_nested_field_is_rejected(self):
        with self.assertRaises(pilot.VCIPilotError):
            pilot.build_observation(
                **self.observation_kwargs(
                    request_parameters={"symbols": ["VCB"], "nested": {"authorization": "Bearer leak"}}
                )
            )

    def test_incomplete_observation_is_rejected(self):
        kwargs = self.observation_kwargs()
        del kwargs["raw_response_sha256"]
        with self.assertRaises(pilot.VCIPilotError):
            pilot.build_observation(**kwargs)

    def test_retained_evidence_artifacts_carry_no_secret(self):
        if not EVIDENCE_DIR.exists():
            self.skipTest("pilot evidence not generated in this checkout")
        for path in sorted(EVIDENCE_DIR.rglob("*.json")):
            text = path.read_text(encoding="utf-8").lower()
            for marker in ("set-cookie", "authorization", "bearer ", "api-key", "jsessionid"):
                self.assertNotIn(marker, text, f"{path.name} contains {marker!r}")


class NoLiveRequestsInTests(unittest.TestCase):
    """11. Live requests are not required for unit tests."""

    def test_acquire_is_the_only_network_surface_and_takes_an_injected_session(self):
        import inspect

        source = inspect.getsource(pilot)
        self.assertNotIn("requests.post", source)
        self.assertNotIn("import requests", source)
        self.assertIn("session", inspect.signature(pilot.acquire).parameters)

    def test_a_fake_session_drives_the_whole_path(self):
        class FakeResponse:
            status_code = 200
            headers = {"Content-Type": "application/json", "Set-Cookie": "s=1"}
            content = json.dumps(daily_fixture()).encode("utf-8")

        class FakeSession:
            def __init__(self):
                self.calls = 0

            def post(self, url, **kwargs):
                self.calls += 1
                return FakeResponse()

        session = FakeSession()
        transport = pilot.acquire(
            endpoint=pilot.DAILY_ENDPOINT,
            payload=pilot.daily_payload("VCB", to_epoch=1785542400, count_back=3),
            session=session,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(session.calls, 1)
        self.assertEqual(transport["http_status"], 200)
        self.assertEqual(transport["redirect_count"], 0)
        self.assertEqual(transport["response_headers_redacted"]["Set-Cookie"], pilot.REDACTED)


class ExistingContractsUnchanged(unittest.TestCase):
    """12/13. Production price and volume contracts and actionability gates are untouched."""

    def test_existing_price_and_volume_contracts_still_fail_closed(self):
        from price_basis_contract import qualify_price_basis, qualify_volume_basis

        price = qualify_price_basis("adjusted", verified=False)
        self.assertEqual(price["price_basis"], "unknown")
        self.assertFalse(price["is_actionable"])
        volume = qualify_volume_basis("raw_shares_traded", verified=False)
        self.assertEqual(volume["volume_basis"], "unknown")

    def test_the_vci_volume_declaration_is_unchanged_and_still_unknown(self):
        import vci_volume_basis

        declaration = vci_volume_basis.declaration()
        self.assertEqual(declaration["volume_basis"], "unknown")
        self.assertEqual(declaration["volume_unit"], "unknown")
        self.assertFalse(declaration["volume_basis_verified"])

    def test_no_verdict_opens_a_production_or_actionability_gate(self):
        for verdict in sorted(pilot.PRICE_BASIS_VERDICTS):
            eligibility = pilot.downstream_eligibility(
                price_verdict=verdict,
                volume_declaration=pilot.volume_basis_declaration(
                    field_identity_qualified=True,
                    unit_verdict="qualified",
                    adjustment_verdict="qualified",
                    reconciliation=None,
                ),
            )
            self.assertEqual(eligibility["production_gate"], "closed")
            self.assertEqual(eligibility["actionability_gate"], "closed")
            self.assertFalse(eligibility["liquidity_actionable"])
            for blocked in ("is_actionable", "ranking", "recommendations", "production_backtesting"):
                self.assertIn(blocked, eligibility["blocked_capabilities"])
            self.assertEqual(eligibility["scope"], "vci_namespaced_shadow_only")


class NoForeignUpgrade(unittest.TestCase):
    """14. A VCI qualification cannot upgrade TCBS, KBS or generic market-data fields."""

    def test_generic_fields_are_refused(self):
        for field in sorted(pilot.FORBIDDEN_GENERIC_FIELDS):
            with self.assertRaises(pilot.VCIPilotError):
                pilot.assert_no_generic_upgrade({field: "split_and_dividend_adjusted"})

    def test_foreign_provider_namespaces_are_refused(self):
        for field in ("tcbs.observed_close", "kbs.observed_close", "hose.official_close"):
            with self.assertRaises(pilot.VCIPilotError):
                pilot.assert_no_generic_upgrade({field: 1})
        pilot.assert_no_generic_upgrade({"vci.raw_close": 54047.65, "session_date": "2026-07-22"})

    def test_a_verdict_must_declare_its_own_limited_authority(self):
        with self.assertRaises(pilot.VCIPilotError):
            pilot.assert_verdict_scope({"provider": "TCBS", "source_authority": pilot.SOURCE_AUTHORITY})
        with self.assertRaises(pilot.VCIPilotError):
            pilot.assert_verdict_scope({"provider": "VCI", "source_authority": "official_developer_api"})
        with self.assertRaises(pilot.VCIPilotError):
            pilot.assert_verdict_scope(
                {"provider": "VCI", "source_authority": pilot.SOURCE_AUTHORITY, "upgrades_kbs": True}
            )
        pilot.assert_verdict_scope({"provider": "VCI", "source_authority": pilot.SOURCE_AUTHORITY})


class DeterministicReplay(unittest.TestCase):
    """15. Replaying a frozen raw payload gives deterministic output and artifact hashes."""

    def test_replay_is_byte_stable(self):
        body = json.dumps(daily_fixture(), separators=(",", ":")).encode("utf-8")
        first = pilot.response_sha256(body)
        second = pilot.response_sha256(body)
        self.assertEqual(first, second)

        parsed = json.loads(body.decode("utf-8"))
        run_a = pilot.normalize_daily(pilot.parse_daily_payload(parsed, symbol="VCB"))
        run_b = pilot.normalize_daily(pilot.parse_daily_payload(parsed, symbol="VCB"))
        self.assertEqual(
            json.dumps(run_a, sort_keys=True), json.dumps(run_b, sort_keys=True)
        )
        name_a = pilot.artifact_name("daily", "VCB", retrieved_at="2026-08-04T04:03:17Z", body_sha256=first)
        name_b = pilot.artifact_name("daily", "VCB", retrieved_at="2026-08-04T04:03:17Z", body_sha256=second)
        self.assertEqual(name_a, name_b)

    def test_a_later_observation_gets_its_own_artifact_name(self):
        sha = "a" * 64
        earlier = pilot.artifact_name("daily", "VCB", retrieved_at="2026-08-01T01:08:57Z", body_sha256=sha)
        later = pilot.artifact_name("daily", "VCB", retrieved_at="2026-08-04T04:03:17Z", body_sha256=sha)
        self.assertNotEqual(earlier, later)

    def test_schema_fingerprint_tracks_shape_not_values(self):
        payload = daily_fixture()
        same_shape = daily_fixture()
        same_shape[0]["c"] = [1.0, 2.0, 3.0]
        self.assertEqual(pilot.schema_fingerprint(payload), pilot.schema_fingerprint(same_shape))
        changed = daily_fixture()
        changed[0]["adjustedClose"] = [1.0, 2.0, 3.0]
        self.assertNotEqual(pilot.schema_fingerprint(payload), pilot.schema_fingerprint(changed))

    def test_retained_pilot_summary_replays_to_the_recorded_verdict(self):
        summary_path = EVIDENCE_DIR / "pilot_summary.json"
        if not summary_path.exists():
            self.skipTest("pilot evidence not generated in this checkout")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["price_verdict"]["verdict"], "split_and_dividend_adjusted")
        self.assertEqual(summary["price_verdict"]["provider"], "VCI")
        self.assertEqual(summary["price_verdict"]["source_authority"], pilot.SOURCE_AUTHORITY)
        self.assertEqual(summary["volume_declaration"]["volume_market_scope"], "unknown")
        self.assertFalse(summary["volume_declaration"]["liquidity_actionable"])
        self.assertEqual(summary["downstream_eligibility"]["actionability_gate"], "closed")

        for window_id in ("W1_control_no_event", "W2_cash_dividend_event", "W3_capital_event"):
            observation = json.loads(
                (EVIDENCE_DIR / f"observation_{window_id}.json").read_text(encoding="utf-8")
            )
            body = (EVIDENCE_DIR / "raw" / observation["raw_artifact"]).read_bytes()
            body_sha = pilot.response_sha256(body)
            self.assertEqual(body_sha, observation["raw_response_sha256"])
            self.assertEqual(
                pilot.artifact_name(
                    "daily",
                    observation["ticker"],
                    retrieved_at=observation["retrieved_at"],
                    body_sha256=body_sha,
                ),
                observation["raw_artifact"],
            )
            replayed = pilot.normalize_daily(
                pilot.parse_daily_payload(json.loads(body.decode("utf-8")), symbol=observation["ticker"])
            )
            self.assertEqual(replayed["returned_date_range"], observation["returned_date_range"])


class LatticeArithmetic(unittest.TestCase):
    def test_hose_bands(self):
        self.assertEqual(pilot.hose_tick_size(9_990), 10)
        self.assertEqual(pilot.hose_tick_size(23_850), 50)
        self.assertEqual(pilot.hose_tick_size(54_500), 100)
        self.assertTrue(pilot.on_tick_lattice(54_500))
        self.assertFalse(pilot.on_tick_lattice(54_047.65))
        self.assertFalse(pilot.on_tick_lattice(23_478.96))
        with self.assertRaises(pilot.VCIPilotError):
            pilot.hose_tick_size(0)

    def test_boundary_detection(self):
        rows = pilot.normalize_daily(pilot.parse_daily_payload(daily_fixture(), symbol="VCB"))["rows"]
        self.assertEqual(pilot.lattice_boundary(rows), "2026-07-23")
        all_on = [
            {
                "vci.session_date": "2026-07-24",
                "vci.observed_open_vnd": 54_000.0,
                "vci.observed_high_vnd": 55_300.0,
                "vci.observed_low_vnd": 53_200.0,
                "vci.observed_close_vnd": 54_100.0,
            }
        ]
        self.assertIsNone(pilot.lattice_boundary(all_on))

    def test_merge_is_conservative(self):
        self.assertEqual(
            pilot.merge_price_verdicts({"a": {"verdict": "inconclusive"}, "b": {"verdict": "inconclusive"}}),
            "inconclusive",
        )
        self.assertEqual(
            pilot.merge_price_verdicts(
                {"a": {"verdict": "dividend_adjusted"}, "b": {"verdict": "split_adjusted"}}
            ),
            "split_and_dividend_adjusted",
        )
        self.assertEqual(
            pilot.merge_price_verdicts(
                {"a": {"verdict": "dividend_adjusted"}, "b": {"verdict": "mixed_or_context_dependent"}}
            ),
            "mixed_or_context_dependent",
        )
        with self.assertRaises(pilot.VCIPilotError):
            pilot.merge_price_verdicts({"a": {"verdict": "adjusted"}})


class FailureClassification(unittest.TestCase):
    def test_distinct_failure_modes(self):
        self.assertEqual(pilot.classify_failure(exception=None, status=403, body=None), "access_blocked")
        self.assertEqual(pilot.classify_failure(exception=None, status=429, body=None), "rate_limited")
        self.assertEqual(pilot.classify_failure(exception=None, status=503, body=None), "source_unavailable")
        self.assertEqual(pilot.classify_failure(exception=None, status=200, body=[]), "empty_valid_response")
        self.assertEqual(
            pilot.classify_failure(
                exception=pilot.VCIPilotError("daily_payload_symbol_mismatch:XYZ"), status=None, body=None
            ),
            "symbol_unsupported",
        )
        self.assertEqual(
            pilot.classify_failure(
                exception=pilot.VCIPilotError("daily_payload_missing_arrays:v"), status=None, body=None
            ),
            "schema_changed",
        )
        self.assertEqual(
            pilot.classify_failure(
                exception=pilot.VCIPilotError("daily_payload_zero_sessions"), status=None, body=None
            ),
            "empty_valid_response",
        )


if __name__ == "__main__":
    unittest.main()
