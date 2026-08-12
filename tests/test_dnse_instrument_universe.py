from __future__ import annotations

import unittest

import pandas as pd

import dnse_instrument_universe as universe


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _instrument(symbol, *, security_group_id="ST", market_id="STO", index_name=None):
    return {
        "symbol": symbol, "securityGroupId": security_group_id, "marketId": market_id,
        "name": f"Company {symbol}", "shortName": symbol, "listedDate": "2020-01-01",
        "symbolType": "", "indexName": index_name,
    }


class ClassifyInstrumentTests(unittest.TestCase):
    def test_known_security_group_id_maps_to_equity(self):
        result = universe.classify_instrument("ST")
        self.assertEqual(universe.EQUITY, result["instrument_class"])
        self.assertEqual("empirically_observed_security_group_id", result["classification_basis"])

    def test_unknown_security_group_id_is_explicit_not_guessed(self):
        result = universe.classify_instrument("CW")
        self.assertEqual(universe.UNKNOWN_SECURITY_GROUP, result["instrument_class"])
        self.assertEqual("security_group_id_not_yet_observed", result["classification_basis"])
        self.assertEqual("CW", result["raw_security_group_id"])

    def test_missing_security_group_id_is_explicit(self):
        result = universe.classify_instrument(None)
        self.assertEqual(universe.UNKNOWN_SECURITY_GROUP, result["instrument_class"])
        self.assertEqual("security_group_id_absent", result["classification_basis"])

    def test_blank_security_group_id_is_explicit(self):
        result = universe.classify_instrument("   ")
        self.assertEqual(universe.UNKNOWN_SECURITY_GROUP, result["instrument_class"])


class NormalizeInstrumentRecordTests(unittest.TestCase):
    def test_valid_record_normalizes(self):
        record = universe.normalize_instrument_record(
            _instrument("HPG", index_name=["VN100", "VN30"]), retrieved_at="2026-08-11T10:00:00+07:00", page=1)
        self.assertEqual("HPG", record["symbol"])
        self.assertEqual("dnse:symbol:hpg", record["provider_identity"])
        self.assertEqual("STO", record["exchange_raw"])
        self.assertEqual(universe.EQUITY, record["instrument_class"])
        self.assertEqual(["VN100", "VN30"], record["index_membership"])
        self.assertEqual("unknown_not_provided_by_dataset", record["listing_status"])

    def test_missing_symbol_raises(self):
        with self.assertRaises(universe.DnseInstrumentUniverseError):
            universe.normalize_instrument_record({"marketId": "STO"}, retrieved_at="t", page=1)

    def test_non_mapping_raises(self):
        with self.assertRaises(universe.DnseInstrumentUniverseError):
            universe.normalize_instrument_record("not-a-dict", retrieved_at="t", page=1)  # type: ignore[arg-type]

    def test_symbol_is_uppercased(self):
        record = universe.normalize_instrument_record(_instrument("hpg"), retrieved_at="t", page=1)
        self.assertEqual("HPG", record["symbol"])

    def test_null_index_name_becomes_none(self):
        record = universe.normalize_instrument_record(_instrument("QNS", index_name=None), retrieved_at="t", page=1)
        self.assertIsNone(record["index_membership"])

    def test_malformed_index_name_does_not_raise(self):
        raw = _instrument("HPG")
        raw["indexName"] = "not-a-list-or-none"
        record = universe.normalize_instrument_record(raw, retrieved_at="t", page=1)
        self.assertIsNone(record["index_membership"])

    def test_unknown_security_group_is_retained_not_dropped(self):
        record = universe.normalize_instrument_record(
            _instrument("XYZ", security_group_id="CW"), retrieved_at="t", page=1)
        self.assertEqual(universe.UNKNOWN_SECURITY_GROUP, record["instrument_class"])
        self.assertEqual("CW", record["raw_security_group_id"])


class DiscoverUniverseSinglePageTests(unittest.TestCase):
    def test_single_page_below_page_size_completes(self):
        payload = {"data": [_instrument("HPG"), _instrument("VNM"), _instrument("QNS", market_id="UPX")],
                   "page": 1, "pageSize": 100, "total": 3}
        result = universe.discover_universe(
            api_key="k", api_secret="s", retrieved_at="2026-08-11T10:00:00+07:00",
            request_get=lambda *_a, **_k: _FakeResponse(200, payload),
        )
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(3, result["discovered_count"])
        self.assertEqual(1, len(result["pages_fetched"]))
        self.assertEqual({"STO": 2, "UPX": 1}, result["by_exchange_raw"])
        self.assertEqual({"EQUITY": 3}, result["by_instrument_class"])

    def test_empty_first_page_completes_with_zero_records(self):
        payload = {"data": [], "page": 1, "pageSize": 100, "total": 0}
        result = universe.discover_universe(
            api_key="k", api_secret="s", retrieved_at="t",
            request_get=lambda *_a, **_k: _FakeResponse(200, payload),
        )
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(0, result["discovered_count"])


class DiscoverUniverseMultiPageTests(unittest.TestCase):
    def _paged_fake(self, total, page_size):
        symbols = [f"SYM{i:04d}" for i in range(total)]

        def fake_get(url, *, params, headers, timeout):
            page = int(params["page"])
            start = (page - 1) * page_size
            chunk = symbols[start:start + page_size]
            body = {"data": [_instrument(sym) for sym in chunk], "page": page,
                    "pageSize": page_size, "total": total}
            return _FakeResponse(200, body)

        return fake_get

    def test_pagination_walks_every_page_using_declared_total(self):
        result = universe.discover_universe(
            api_key="k", api_secret="s", retrieved_at="t", page_size=100,
            request_get=self._paged_fake(total=250, page_size=100),
        )
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(250, result["discovered_count"])
        self.assertEqual(3, len(result["pages_fetched"]))
        self.assertEqual(250, result["declared_total"])

    def test_pagination_terminates_on_empty_page_when_total_absent(self):
        symbols = [f"SYM{i:04d}" for i in range(120)]

        def fake_get(url, *, params, headers, timeout):
            page = int(params["page"])
            start = (page - 1) * 100
            chunk = symbols[start:start + 100]
            return _FakeResponse(200, {"data": [_instrument(s) for s in chunk], "page": page})

        result = universe.discover_universe(api_key="k", api_secret="s", retrieved_at="t",
                                           page_size=100, request_get=fake_get)
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(120, result["discovered_count"])
        # 100 (full page) + 20 (short page) + one confirmatory empty page. Without a
        # declared total this module deliberately does not treat a short page as proof
        # of "last page" -- one extra round trip is cheap; silently truncating the
        # universe on a wrong assumption is not.
        self.assertEqual(3, len(result["pages_fetched"]))
        self.assertIsNone(result["declared_total"])

    def test_max_pages_circuit_breaker_stops_a_runaway_sweep(self):
        def fake_get(url, *, params, headers, timeout):
            page = int(params["page"])
            return _FakeResponse(200, {"data": [_instrument(f"LOOP{page}")], "page": page,
                                       "pageSize": 100, "total": 999999})

        result = universe.discover_universe(api_key="k", api_secret="s", retrieved_at="t",
                                           page_size=100, max_pages=3, request_get=fake_get)
        self.assertEqual("MAX_PAGES_REACHED", result["status"])
        self.assertEqual(3, len(result["pages_fetched"]))

    def test_provider_error_mid_pagination_preserves_prior_pages(self):
        calls = {"n": 0}

        def fake_get(url, *, params, headers, timeout):
            calls["n"] += 1
            page = int(params["page"])
            if page == 1:
                return _FakeResponse(200, {"data": [_instrument("HPG")] * 100, "page": 1,
                                          "pageSize": 100, "total": 200})
            return _FakeResponse(500, {"message": "server error"})

        result = universe.discover_universe(api_key="k", api_secret="s", retrieved_at="t",
                                           page_size=100, request_get=fake_get)
        self.assertEqual("PROVIDER_ERROR_MID_PAGINATION", result["status"])
        self.assertEqual(1, result["discovered_count"])
        self.assertEqual("http_status_500", result["last_error"]["error_code"])
        self.assertEqual(2, calls["n"])

    def test_malformed_data_field_reported_and_stops_cleanly(self):
        result = universe.discover_universe(
            api_key="k", api_secret="s", retrieved_at="t",
            request_get=lambda *_a, **_k: _FakeResponse(200, {"data": "not-a-list"}),
        )
        self.assertEqual("MALFORMED_RESPONSE_MID_PAGINATION", result["status"])
        self.assertEqual(0, result["discovered_count"])

    def test_malformed_individual_record_is_skipped_not_fatal(self):
        payload = {"data": [_instrument("HPG"), {"marketId": "STO"}, _instrument("VNM")],
                   "page": 1, "pageSize": 100, "total": 3}
        result = universe.discover_universe(
            api_key="k", api_secret="s", retrieved_at="t",
            request_get=lambda *_a, **_k: _FakeResponse(200, payload),
        )
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(2, result["discovered_count"])
        self.assertEqual(1, result["malformed_record_count"])

    def test_duplicate_identity_across_pages_is_reported_and_not_double_counted(self):
        def fake_get(url, *, params, headers, timeout):
            page = int(params["page"])
            if page == 1:
                return _FakeResponse(200, {"data": [_instrument("HPG")], "page": 1,
                                          "pageSize": 1, "total": 2})
            return _FakeResponse(200, {"data": [_instrument("HPG")], "page": 2,
                                      "pageSize": 1, "total": 2})

        result = universe.discover_universe(api_key="k", api_secret="s", retrieved_at="t",
                                           page_size=1, request_get=fake_get)
        self.assertEqual(1, result["discovered_count"])
        self.assertEqual(1, result["duplicate_identity_count"])
        self.assertIn("dnse:symbol:hpg", result["duplicate_identities"])

    def test_on_page_success_callback_fires_once_per_successful_page(self):
        calls = []
        universe.discover_universe(
            api_key="k", api_secret="s", retrieved_at="t", page_size=100,
            request_get=self._paged_fake(total=250, page_size=100),
            on_page_success=lambda page, response: calls.append((page, response.get("ok"))),
        )
        self.assertEqual([(1, True), (2, True), (3, True)], calls)

    def test_on_page_success_callback_not_called_for_failed_page(self):
        calls = []

        def fake_get(url, *, params, headers, timeout):
            page = int(params["page"])
            if page == 1:
                return _FakeResponse(200, {"data": [_instrument("HPG")], "page": 1,
                                          "pageSize": 1, "total": 2})
            return _FakeResponse(500, {"message": "server error"})

        universe.discover_universe(
            api_key="k", api_secret="s", retrieved_at="t", page_size=1, request_get=fake_get,
            on_page_success=lambda page, response: calls.append(page),
        )
        self.assertEqual([1], calls)

    def test_only_page_and_limit_params_are_sent(self):
        captured = {}

        def fake_get(url, *, params, headers, timeout):
            captured.update(params)
            return _FakeResponse(200, {"data": [], "page": 1, "pageSize": 100, "total": 0})

        universe.discover_universe(api_key="k", api_secret="s", retrieved_at="t", page_size=50,
                                   request_get=fake_get)
        self.assertEqual({"page": 1, "limit": 50}, captured)


class SnapshotManifestTests(unittest.TestCase):
    def _discovery_result(self):
        payload = {"data": [_instrument("HPG"), _instrument("VNM")], "page": 1, "pageSize": 100, "total": 2}
        return universe.discover_universe(
            api_key="k", api_secret="s", retrieved_at="2026-08-11T10:00:00+07:00",
            request_get=lambda *_a, **_k: _FakeResponse(200, payload),
        )

    def test_manifest_is_deterministic_regardless_of_record_order(self):
        result = self._discovery_result()
        forward = universe.snapshot_manifest(result)
        reversed_result = dict(result, records=list(reversed(result["records"])))
        backward = universe.snapshot_manifest(reversed_result)
        self.assertEqual(forward["content_hash"], backward["content_hash"])
        self.assertEqual(forward["snapshot_id"], backward["snapshot_id"])

    def test_manifest_fields_reflect_discovery_result(self):
        result = self._discovery_result()
        manifest = universe.snapshot_manifest(result)
        self.assertEqual(2, manifest["discovered_count"])
        self.assertEqual("COMPLETE", manifest["status"])
        self.assertEqual(1, manifest["pages_fetched"])


class BuildSnapshotFrameTests(unittest.TestCase):
    def test_empty_records_produce_empty_frame_with_columns(self):
        frame = universe.build_snapshot_frame([])
        self.assertIsInstance(frame, pd.DataFrame)
        self.assertEqual(0, len(frame))
        self.assertIn("symbol", frame.columns)

    def test_frame_is_sorted_by_symbol(self):
        records = [
            universe.normalize_instrument_record(_instrument("VNM"), retrieved_at="t", page=1),
            universe.normalize_instrument_record(_instrument("HPG"), retrieved_at="t", page=1),
        ]
        frame = universe.build_snapshot_frame(records)
        self.assertEqual(["HPG", "VNM"], list(frame["symbol"]))

    def test_index_membership_serialized_as_json_column(self):
        records = [universe.normalize_instrument_record(
            _instrument("HPG", index_name=["VN30"]), retrieved_at="t", page=1)]
        frame = universe.build_snapshot_frame(records)
        self.assertIn("index_membership_json", frame.columns)
        self.assertNotIn("index_membership", frame.columns)


if __name__ == "__main__":
    unittest.main()
