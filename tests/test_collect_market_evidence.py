"""Comprehensive validation suite for the capability-first EOD market evidence collector."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from typing import Any

from tools import collect_market_evidence as collector
import market_capability_taxonomy as taxonomy
import price_representation_contract as price_contract
from vn_time import VN_TZ

MOCK_SESSION = "2026-08-20"


def _sample_dnse_ohlc_payload(symbol: str, session: str = MOCK_SESSION) -> dict[str, Any]:
    # 2026-08-20 session anchor epoch in +07:00
    dt = datetime.strptime(session, "%Y-%m-%d").replace(tzinfo=VN_TZ)
    epoch = int(dt.timestamp())
    prev_epoch = epoch - 86400
    return {
        "t": [prev_epoch, epoch],
        "o": [21.00, 21.50],
        "h": [21.80, 22.00],
        "l": [20.90, 21.30],
        "c": [21.40, 21.85],
        "v": [1500000, 2500000],
    }


def _sample_dnse_foreign_payload(symbol: str) -> dict[str, Any]:
    return {
        "foreignRoomMax": 100000000,
        "foreignRoomOwned": 45000000,
        "foreignRoomAvailable": 55000000,
        "foreigners": [
            {
                "symbol": symbol,
                "buyForeignQuantity": 150000,
                "sellForeignQuantity": 50000,
                "buyForeignValue": 3277500000,
                "sellForeignValue": 1092500000,
            }
        ],
    }


def _sample_fhsc_price_history_payload(symbol: str, session: str = MOCK_SESSION) -> dict[str, Any]:
    dt = datetime.strptime(session, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    epoch = int(dt.timestamp())
    return {
        "data": {
            "symbol": symbol,
            "resolution": "1D",
            "time": [epoch],
            "open": [21500],
            "high": [22000],
            "low": [21300],
            "close": [21850],
            "volume": [2500000],
        }
    }


def _sample_fhsc_trading_history_payload(symbol: str, session: str = MOCK_SESSION) -> dict[str, Any]:
    return {
        "data": {
            "symbol": symbol,
            "resolution": "1D",
            "data": [
                {
                    "date": session,
                    "matched": {"volume": 2200000, "value": 47300000000},
                    "put_through": {"volume": 300000, "value": 6450000000},
                    "total": {"volume": 2500000, "value": 53750000000},
                }
            ],
        }
    }


def _sample_fhsc_foreign_room_payload(symbol: str, session: str = MOCK_SESSION) -> dict[str, Any]:
    return {
        "data": {
            "symbol": symbol,
            "date": session,
            "max_volume": 2089955445,
            "owned": 1969955445,
            "available": 120000000,
            "max_pct": 100,
        }
    }


def _sample_fhsc_proprietary_payload(symbol: str, session: str = MOCK_SESSION) -> dict[str, Any]:
    return {
        "data": {
            "symbol": symbol,
            "date": session,
            "buy": {
                "total": {"volume": 850000, "value": 18275000000},
            },
            "sell": {
                "total": {"volume": 320000, "value": 6880000000},
            },
            "net": {
                "total": {"volume": 530000, "value": 11395000000},
            },
        }
    }


def _sample_fhsc_order_statistics_payload(symbol: str, session: str = MOCK_SESSION) -> dict[str, Any]:
    return {
        "data": {
            "symbol": symbol,
            "date": session,
            "buy": {
                "order_count": 18422,
                "volume": 9871300,
                "avg_volume_per_order": 535.8,
            },
            "sell": {
                "order_count": 14205,
                "volume": 5285100,
                "avg_volume_per_order": 372.1,
            },
            "net_volume": 4586200,
        }
    }


def mock_fetcher_success(req: dict[str, Any], session_date: str) -> dict[str, Any]:
    source = req["source"]
    endpoint_id = req["endpoint_id"]
    symbol = req["symbol"]
    retrieval_time = "2026-08-20T18:05:00.000Z"

    if source == "DNSE":
        if endpoint_id == "ohlc":
            payload = _sample_dnse_ohlc_payload(symbol, session_date)
        elif endpoint_id == "foreign_trading":
            payload = _sample_dnse_foreign_payload(symbol)
        else:
            payload = {}
    elif source == "FHSC":
        if endpoint_id == "price_histories_chart":
            payload = _sample_fhsc_price_history_payload(symbol, session_date)
        elif endpoint_id == "trading_history":
            payload = _sample_fhsc_trading_history_payload(symbol, session_date)
        elif endpoint_id == "foreign_room":
            payload = _sample_fhsc_foreign_room_payload(symbol, session_date)
        elif endpoint_id == "proprietary_trading":
            payload = _sample_fhsc_proprietary_payload(symbol, session_date)
        elif endpoint_id == "order_statistics":
            payload = _sample_fhsc_order_statistics_payload(symbol, session_date)
        else:
            payload = {}
    else:
        return {"ok": False, "error_code": "UNKNOWN_SOURCE", "retrieval_time": retrieval_time}

    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return {
        "ok": True,
        "source": source,
        "endpoint": endpoint_id,
        "symbol": symbol,
        "http_status": 200,
        "mime_type": "application/json",
        "retrieval_time": retrieval_time,
        "raw_bytes": body_bytes,
        "payload": payload,
        "request_url": f"https://mock.{source.lower()}.com/{endpoint_id}/{symbol}",
        "request_parameters": {"symbol": symbol, "session": session_date},
    }


class OneSourceOnlyCapabilityTests(unittest.TestCase):
    """Requirement 1 & 2: Route per capability. A single-source capability must be ingestible."""

    def test_single_source_put_through_volume_from_fhsc(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["PUT_THROUGH_VOLUME_SHARES"],
                sources=["FHSC"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            self.assertEqual("1.0.0", packet["packet_schema_version"])
            self.assertEqual(1, len(packet["observations"]))
            obs = packet["observations"][0]
            self.assertEqual("FHSC", obs["source"])
            self.assertEqual("trading_history", obs["endpoint_id"])
            self.assertTrue(obs["raw_response_retained"])
            self.assertEqual(300000, obs["native_fields"]["PUT_THROUGH_VOLUME_SHARES"]["value"])
            self.assertEqual(300000, obs["canonical_fields"]["PUT_THROUGH_VOLUME_SHARES"]["value"])

    def test_single_source_foreign_buy_volume_from_dnse(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["FOREIGN_BUY_VOLUME"],
                sources=["DNSE"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            self.assertEqual(1, len(packet["observations"]))
            obs = packet["observations"][0]
            self.assertEqual("DNSE", obs["source"])
            self.assertEqual("foreign_trading", obs["endpoint_id"])
            self.assertEqual(150000, obs["canonical_fields"]["FOREIGN_BUY_VOLUME"]["value"])


class MixedSourcePacketTests(unittest.TestCase):
    """Test packet combining capabilities from DNSE and FHSC seamlessly."""

    def test_mixed_source_packet_structure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["PRICE", "VOLUME", "FOREIGN"],
                sources=["DNSE", "FHSC"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            sources_present = {obs["source"] for obs in packet["observations"]}
            self.assertEqual({"DNSE", "FHSC"}, sources_present)
            # Check manifest was created and matches packet
            manifest_file = Path(tmp_dir) / "manifest.json"
            self.assertTrue(manifest_file.exists())
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            self.assertEqual(packet["packet_identity"], manifest["packet_identity"])
            self.assertEqual(packet["packet_sha256"], manifest["packet_sha256"])


class RawPreservationAndCanonicalMappingTests(unittest.TestCase):
    """Requirement 3: Preserve native observations; canonical representations are derived."""

    def test_raw_native_and_canonical_coexist(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["PRICE"],
                sources=["DNSE"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            obs = packet["observations"][0]
            # Native preserved (thousands of VND/share)
            self.assertEqual("21.5", obs["native_fields"]["OPEN_KVND"]["value"])
            self.assertEqual("thousands_of_vnd_per_share", obs["native_fields"]["OPEN_KVND"]["unit"])
            self.assertEqual("21.85", obs["native_fields"]["CLOSE_KVND"]["value"])

            # Canonical derived (VND/share)
            self.assertEqual(Decimal("21500"), Decimal(obs["canonical_fields"]["OPEN_VND"]["value"]))
            self.assertEqual("vnd_per_share", obs["canonical_fields"]["OPEN_VND"]["unit"])
            self.assertEqual(Decimal("21850"), Decimal(obs["canonical_fields"]["CLOSE_VND"]["value"]))


class UniformOhlcContractTests(unittest.TestCase):
    """Requirement 4: Reuse Phase-1 explicit K-VND->VND contract; no magnitude heuristics."""

    def test_all_four_ohlc_fields_scaled_identically_by_contract(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["PRICE"],
                sources=["DNSE"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            obs = packet["observations"][0]
            canon = obs["canonical_fields"]
            self.assertEqual(Decimal("21500"), Decimal(canon["OPEN_VND"]["value"]))
            self.assertEqual(Decimal("22000"), Decimal(canon["HIGH_VND"]["value"]))
            self.assertEqual(Decimal("21300"), Decimal(canon["LOW_VND"]["value"]))
            self.assertEqual(Decimal("21850"), Decimal(canon["CLOSE_VND"]["value"]))
            for field in ("OPEN_VND", "HIGH_VND", "LOW_VND", "CLOSE_VND"):
                self.assertIn("contract_basis_tier", canon[field])
                self.assertEqual(price_contract.CONTRACT_BASIS_TIER, canon[field]["contract_basis_tier"])

    def test_foreign_value_not_scaled_by_kvnd_contract(self):
        # Foreign flow values are raw VND, not thousands of VND
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["FOREIGN_BUY_VALUE"],
                sources=["DNSE"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            obs = packet["observations"][0]
            self.assertEqual(3277500000, obs["native_fields"]["FOREIGN_BUY_VALUE"]["value"])
            self.assertEqual(3277500000, obs["canonical_fields"]["FOREIGN_BUY_VALUE"]["value"])
            self.assertEqual("vnd_raw_not_thousands", obs["canonical_fields"]["FOREIGN_BUY_VALUE"]["unit"])


class RequestBudgetEnforcementTests(unittest.TestCase):
    """Requirement: max-requests budget strictly enforced."""

    def test_budget_exhaustion_caps_calls_and_records_budget_exhausted(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sent_requests: list[tuple[str, str]] = []

            def counting_fetcher(req: dict[str, Any], session_date: str) -> dict[str, Any]:
                sent_requests.append((req["symbol"], req["endpoint_id"]))
                return mock_fetcher_success(req, session_date)

            # 3 symbols * 1 request = 3 planned requests, budget is 2
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG", "VCB", "SSI"],
                capabilities=["PRICE"],
                sources=["DNSE"],
                max_requests=2,
                out_dir=tmp_dir,
                fetcher=counting_fetcher,
            )
            self.assertEqual(2, packet["request_budget"]["used_requests"])
            self.assertTrue(packet["request_budget"]["budget_exhausted"])
            self.assertEqual(1, packet["request_budget"]["budget_skipped_requests"])
            self.assertEqual(0, packet["request_budget"]["provider_rate_limited_requests"])
            self.assertEqual(2, len(sent_requests))
            self.assertEqual(3, len(packet["observations"]))
            # First 2 acquired, 3rd BUDGET_EXHAUSTED
            self.assertEqual("ACQUIRED", packet["observations"][0]["status"])
            self.assertEqual("ACQUIRED", packet["observations"][1]["status"])
            skipped_observation = packet["observations"][2]
            self.assertEqual("BUDGET_EXHAUSTED", skipped_observation["status"])
            self.assertEqual(taxonomy.MISSING, skipped_observation["usability_state"])
            self.assertEqual("BUDGET_EXHAUSTED", skipped_observation["acquisition_disposition"])
            self.assertFalse(skipped_observation["request_sent"])
            self.assertEqual([], packet["rate_limit_events"])
            self.assertEqual(1, len(packet["budget_exhausted_events"]))
            self.assertNotIn("PROVIDER_RATE_LIMITED", json.dumps(packet))

            manifest = json.loads((Path(tmp_dir) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(0, manifest["summary"]["provider_rate_limited_observations"])
            self.assertEqual(1, manifest["summary"]["budget_skipped_observations"])


class Partial429RateLimitingTests(unittest.TestCase):
    """Requirement 5: HTTP 429 becomes PROVIDER_RATE_LIMITED without invalidating successes."""

    def test_partial_429_does_not_fail_unrelated_observations(self):
        def mock_fetcher_with_429(req: dict[str, Any], session_date: str) -> dict[str, Any]:
            if req["symbol"] == "VCB":
                return {
                    "ok": False,
                    "error_code": "PROVIDER_RATE_LIMITED",
                    "http_status": 429,
                    "source": req["source"],
                    "endpoint": req["endpoint_id"],
                    "symbol": req["symbol"],
                    "retrieval_time": "2026-08-20T18:05:00.000Z",
                    "raw_response_retained": False,
                }
            return mock_fetcher_success(req, session_date)

        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG", "VCB", "SSI"],
                capabilities=["PRICE"],
                sources=["DNSE"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_with_429,
            )
            self.assertEqual(1, packet["request_budget"]["provider_rate_limited_requests"])
            self.assertEqual(0, packet["request_budget"]["budget_skipped_requests"])
            self.assertEqual(1, len(packet["rate_limit_events"]))
            self.assertEqual("VCB", packet["rate_limit_events"][0]["instrument"])

            # HPG and SSI succeeded, VCB is rate-limited
            obs_map = {o["instrument"]: o for o in packet["observations"]}
            self.assertEqual("ACQUIRED", obs_map["HPG"]["status"])
            self.assertEqual("PROVIDER_RATE_LIMITED", obs_map["VCB"]["status"])
            self.assertEqual("ACQUIRED", obs_map["SSI"]["status"])


class DeterministicReplayTests(unittest.TestCase):
    """Requirement: Deterministic offline replay from retained raw evidence."""

    def test_replay_produces_identical_packet_identity(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Live run with mock
            packet1 = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["PRICE", "VOLUME"],
                sources=["DNSE"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            # 2. Replay run without fetcher
            packet2 = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["PRICE", "VOLUME"],
                sources=["DNSE"],
                out_dir=tmp_dir,
                replay_only=True,
            )
            self.assertEqual(packet1["observations"][0]["raw_sha256"], packet2["observations"][0]["raw_sha256"])
            self.assertEqual(
                packet1["observations"][0]["canonical_fields"],
                packet2["observations"][0]["canonical_fields"],
            )


class NoAuthorityEscalationTests(unittest.TestCase):
    """Requirement 7: Authority effect is strictly NONE throughout."""

    def test_authority_boundaries_are_strictly_false_and_none(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["PRICE", "VOLUME", "FOREIGN"],
                sources=["DNSE"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            bounds = packet["authority_boundaries"]
            self.assertEqual("NONE", bounds["authority_effect"])
            self.assertFalse(bounds["raw_as_traded_promoted"])
            self.assertFalse(bounds["pit_backtest_eligible"])
            self.assertEqual("BLOCKED", bounds["liquidity_sizing_authority"])
            self.assertFalse(bounds["valuation_authority"])
            self.assertFalse(bounds["recommendation_authority"])
            self.assertFalse(bounds["database_mutated"])

            for obs in packet["observations"]:
                self.assertEqual("NONE", obs["authority_effect"])


class NoSecretMaterialTests(unittest.TestCase):
    """Requirement: No secrets logged or persisted in packet, manifest, or errors."""

    def test_no_credential_keys_or_secrets_in_packet(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["PRICE"],
                sources=["DNSE"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            dumped = json.dumps(packet)
            sensitive_terms = ("x-api-key", "authorization", "secret", "signature=", "passwd")
            for term in sensitive_terms:
                self.assertNotIn(term, dumped.lower())


class RevisionDetectionTests(unittest.TestCase):
    """Requirement 8: Retain both versions and flag PROVIDER_REVISION_DETECTED on revision."""

    def test_revision_detection_flags_change_and_retains_prior(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # First collection
            packet1 = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["PRICE"],
                sources=["DNSE"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            self.assertEqual("INITIAL_OBSERVATION", packet1["observations"][0]["revision_state"])
            self.assertEqual(0, len(packet1["revision_events"]))

            # Modified payload fetcher for revision
            def mock_fetcher_revised(req: dict[str, Any], session_date: str) -> dict[str, Any]:
                res = mock_fetcher_success(req, session_date)
                payload = json.loads(res["raw_bytes"].decode("utf-8"))
                # Provider revised close price from 21.85 to 21.90
                payload["c"][-1] = 21.90
                res["raw_bytes"] = json.dumps(payload).encode("utf-8")
                res["payload"] = payload
                res["retrieval_time"] = "2026-08-20T19:00:00.000Z"
                return res

            # Second collection of same session
            packet2 = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["PRICE"],
                sources=["DNSE"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_revised,
                prior_packet=packet1,
            )
            self.assertEqual("PROVIDER_REVISION_DETECTED", packet2["observations"][0]["revision_state"])
            self.assertEqual(1, len(packet2["revision_events"]))
            self.assertEqual(packet1["observations"][0]["raw_sha256"], packet2["revision_events"][0]["prior_raw_sha256"])
            self.assertNotEqual(packet2["observations"][0]["raw_sha256"], packet2["revision_events"][0]["prior_raw_sha256"])

            # Verify both raw files are on disk in raw/ directory
            raw_files = list((Path(tmp_dir) / "raw").glob("*.json"))
            self.assertEqual(2, len(raw_files))


class FhscTradedValueTests(unittest.TestCase):
    """TRADED VALUE: MATCHED_TRADED_VALUE_VND, PUT_THROUGH_TRADED_VALUE_VND, TOTAL_TRADED_VALUE_VND."""

    def test_fhsc_traded_value_preserves_exact_vnd_units_and_arithmetic_identity(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["TRADED_VALUE"],
                sources=["FHSC"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            self.assertEqual(1, len(packet["observations"]))
            obs = packet["observations"][0]
            self.assertEqual("FHSC", obs["source"])
            self.assertEqual("trading_history", obs["endpoint_id"])

            native = obs["native_fields"]
            canonical = obs["canonical_fields"]

            # Exact raw VND preservation
            self.assertEqual(47300000000, native["MATCHED_TRADED_VALUE_VND"]["value"])
            self.assertEqual("vnd", native["MATCHED_TRADED_VALUE_VND"]["unit"])
            self.assertEqual(6450000000, native["PUT_THROUGH_TRADED_VALUE_VND"]["value"])
            self.assertEqual("vnd", native["PUT_THROUGH_TRADED_VALUE_VND"]["unit"])
            self.assertEqual(53750000000, native["TOTAL_TRADED_VALUE_VND"]["value"])
            self.assertEqual("vnd", native["TOTAL_TRADED_VALUE_VND"]["unit"])

            # Arithmetic identity: matched + put_through == total
            self.assertEqual(
                native["MATCHED_TRADED_VALUE_VND"]["value"] + native["PUT_THROUGH_TRADED_VALUE_VND"]["value"],
                native["TOTAL_TRADED_VALUE_VND"]["value"],
            )

            # Canonical mapping
            self.assertEqual(47300000000, canonical["MATCHED_TRADED_VALUE_VND"]["value"])
            self.assertEqual("vnd_raw_not_thousands", canonical["MATCHED_TRADED_VALUE_VND"]["unit"])
            self.assertEqual(6450000000, canonical["PUT_THROUGH_TRADED_VALUE_VND"]["value"])
            self.assertEqual(53750000000, canonical["TOTAL_TRADED_VALUE_VND"]["value"])

    def test_traded_value_routes_to_fhsc_without_dnse_comparator(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["MATCHED_TRADED_VALUE_VND"],
                sources=["DNSE", "FHSC"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            # Only FHSC provides traded value; routes to FHSC without failing on DNSE absence
            sources_present = {obs["source"] for obs in packet["observations"]}
            self.assertEqual({"FHSC"}, sources_present)
            self.assertEqual(47300000000, packet["observations"][0]["canonical_fields"]["MATCHED_TRADED_VALUE_VND"]["value"])


class FhscForeignRoomTests(unittest.TestCase):
    """FOREIGN ROOM: FOREIGN_ROOM_MAX, FOREIGN_ROOM_OWNED, FOREIGN_ROOM_AVAILABLE."""

    def test_fhsc_foreign_room_identities_remain_distinct_and_sum_to_max(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["FOREIGN_ROOM_MAX", "FOREIGN_ROOM_OWNED", "FOREIGN_ROOM_AVAILABLE"],
                sources=["FHSC"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            self.assertEqual(1, len(packet["observations"]))
            obs = packet["observations"][0]
            self.assertEqual("FHSC", obs["source"])
            self.assertEqual("foreign_room", obs["endpoint_id"])

            native = obs["native_fields"]
            canonical = obs["canonical_fields"]

            self.assertEqual(2089955445, native["FOREIGN_ROOM_MAX"]["value"])
            self.assertEqual("shares", native["FOREIGN_ROOM_MAX"]["unit"])
            self.assertEqual(1969955445, native["FOREIGN_ROOM_OWNED"]["value"])
            self.assertEqual(120000000, native["FOREIGN_ROOM_AVAILABLE"]["value"])

            # Identities are distinct and not aliased
            self.assertNotEqual(native["FOREIGN_ROOM_MAX"]["value"], native["FOREIGN_ROOM_AVAILABLE"]["value"])
            self.assertEqual(
                native["FOREIGN_ROOM_OWNED"]["value"] + native["FOREIGN_ROOM_AVAILABLE"]["value"],
                native["FOREIGN_ROOM_MAX"]["value"],
            )

            self.assertEqual(2089955445, canonical["FOREIGN_ROOM_MAX"]["value"])
            self.assertEqual(1969955445, canonical["FOREIGN_ROOM_OWNED"]["value"])
            self.assertEqual(120000000, canonical["FOREIGN_ROOM_AVAILABLE"]["value"])


class FhscProprietaryFlowTests(unittest.TestCase):
    """PROPRIETARY FLOW: buy/sell/net volume and value."""

    def test_proprietary_flow_buy_sell_net_semantics_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["PROPRIETARY"],
                sources=["FHSC"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            self.assertEqual(1, len(packet["observations"]))
            obs = packet["observations"][0]
            self.assertEqual("FHSC", obs["source"])
            self.assertEqual("proprietary_trading", obs["endpoint_id"])

            native = obs["native_fields"]
            canonical = obs["canonical_fields"]

            # Volumes (shares)
            self.assertEqual(850000, native["PROPRIETARY_BUY_VOLUME"]["value"])
            self.assertEqual(320000, native["PROPRIETARY_SELL_VOLUME"]["value"])
            self.assertEqual(530000, native["PROPRIETARY_NET_VOLUME"]["value"])
            self.assertEqual(
                native["PROPRIETARY_BUY_VOLUME"]["value"] - native["PROPRIETARY_SELL_VOLUME"]["value"],
                native["PROPRIETARY_NET_VOLUME"]["value"],
            )

            # Values (VND)
            self.assertEqual(18275000000, native["PROPRIETARY_BUY_VALUE"]["value"])
            self.assertEqual(6880000000, native["PROPRIETARY_SELL_VALUE"]["value"])
            self.assertEqual(11395000000, native["PROPRIETARY_NET_VALUE"]["value"])
            self.assertEqual(
                native["PROPRIETARY_BUY_VALUE"]["value"] - native["PROPRIETARY_SELL_VALUE"]["value"],
                native["PROPRIETARY_NET_VALUE"]["value"],
            )

            # Canonical representation units
            self.assertEqual("shares", canonical["PROPRIETARY_NET_VOLUME"]["unit"])
            self.assertEqual("vnd_raw_not_thousands", canonical["PROPRIETARY_NET_VALUE"]["unit"])

    def test_proprietary_flow_is_distinct_from_foreign_flow(self):
        # Request both PROPRIETARY and FOREIGN from FHSC + DNSE
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["PROPRIETARY", "FOREIGN"],
                sources=["DNSE", "FHSC"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            obs_endpoints = {(o["source"], o["endpoint_id"]) for o in packet["observations"]}
            self.assertIn(("FHSC", "proprietary_trading"), obs_endpoints)
            self.assertIn(("DNSE", "foreign_trading"), obs_endpoints)


class FhscMicrostructureTests(unittest.TestCase):
    """MICROSTRUCTURE: ACTIVE_BUY_ORDER_COUNT, ACTIVE_SELL_ORDER_COUNT, ACTIVE_BUY_VOLUME, ACTIVE_SELL_VOLUME, ACTIVE_NET_VOLUME."""

    def test_active_order_statistics_do_not_become_executed_volume(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["MICROSTRUCTURE"],
                sources=["FHSC"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            self.assertEqual(1, len(packet["observations"]))
            obs = packet["observations"][0]
            self.assertEqual("FHSC", obs["source"])
            self.assertEqual("order_statistics", obs["endpoint_id"])

            native = obs["native_fields"]
            canonical = obs["canonical_fields"]

            # Order counts
            self.assertEqual(18422, native["ACTIVE_BUY_ORDER_COUNT"]["value"])
            self.assertEqual("orders", native["ACTIVE_BUY_ORDER_COUNT"]["unit"])
            self.assertEqual(14205, native["ACTIVE_SELL_ORDER_COUNT"]["value"])
            self.assertEqual("orders", native["ACTIVE_SELL_ORDER_COUNT"]["unit"])

            # Active volumes (shares)
            self.assertEqual(9871300, native["ACTIVE_BUY_VOLUME"]["value"])
            self.assertEqual(5285100, native["ACTIVE_SELL_VOLUME"]["value"])
            self.assertEqual(4586200, native["ACTIVE_NET_VOLUME"]["value"])

            # Net volume arithmetic: buy.volume - sell.volume == net_volume
            self.assertEqual(
                native["ACTIVE_BUY_VOLUME"]["value"] - native["ACTIVE_SELL_VOLUME"]["value"],
                native["ACTIVE_NET_VOLUME"]["value"],
            )

            # Active volume is strictly distinct from total executed volume (e.g. 2,500,000 shares)
            self.assertNotEqual(native["ACTIVE_BUY_VOLUME"]["value"], 2500000)
            self.assertEqual(4586200, canonical["ACTIVE_NET_VOLUME"]["value"])


class FhscDateScopedSemanticsTests(unittest.TestCase):
    """FHSC historical observations must be source-labelled for the requested session."""

    def test_history_contracts_are_date_scoped_and_never_current_state_routes(self):
        expected = {
            "foreign_room": "/market/stocks/HPG/ownership/foreign-room/history",
            "proprietary_trading": "/market/stocks/HPG/trading/proprietary/history",
            "order_statistics": "/market/stocks/HPG/trading/orders/history",
        }
        for endpoint_id, expected_path in expected.items():
            with self.subTest(endpoint_id=endpoint_id):
                path, params = collector._fhsc_request_contract(endpoint_id, "HPG", MOCK_SESSION)
                self.assertEqual(expected_path, path)
                self.assertEqual({"from": MOCK_SESSION, "to": MOCK_SESSION}, params)

    def test_historical_request_rejects_unrelated_current_state_response(self):
        def current_state_fetcher(req: dict[str, Any], session_date: str) -> dict[str, Any]:
            payload = _sample_fhsc_foreign_room_payload(req["symbol"], "2026-08-21")
            return {
                "ok": True,
                "source": req["source"],
                "endpoint": req["endpoint_id"],
                "symbol": req["symbol"],
                "http_status": 200,
                "retrieval_time": "2026-08-21T10:00:00.000Z",
                "raw_bytes": json.dumps(payload).encode("utf-8"),
            }

        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["FOREIGN_ROOM_MAX"],
                sources=["FHSC"],
                out_dir=tmp_dir,
                fetcher=current_state_fetcher,
            )
            obs = packet["observations"][0]
            self.assertEqual("MISSING_REQUESTED_SESSION", obs["status"])
            self.assertEqual(taxonomy.MISSING, obs["usability_state"])
            self.assertTrue(obs["raw_response_retained"])
            self.assertEqual({}, obs["canonical_fields"])
            self.assertIsNone(obs["provider_session_date"])
            self.assertEqual("2026-08-21T10:00:00.000Z", obs["retrieved_at"])

    def test_exact_session_selection_preserves_provider_session_separately_from_retrieval(self):
        requested = _sample_fhsc_foreign_room_payload("HPG", MOCK_SESSION)["data"]
        unrelated = _sample_fhsc_foreign_room_payload("HPG", "2026-08-21")["data"]
        payload = {"data": {"items": [unrelated, requested]}}

        def history_fetcher(req: dict[str, Any], session_date: str) -> dict[str, Any]:
            return {
                "ok": True,
                "source": req["source"],
                "endpoint": req["endpoint_id"],
                "symbol": req["symbol"],
                "http_status": 200,
                "retrieval_time": "2026-08-21T10:00:00.000Z",
                "raw_bytes": json.dumps(payload).encode("utf-8"),
            }

        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["FOREIGN_ROOM_MAX"],
                sources=["FHSC"],
                out_dir=tmp_dir,
                fetcher=history_fetcher,
            )
            obs = packet["observations"][0]
            self.assertEqual("ACQUIRED", obs["status"])
            self.assertEqual(MOCK_SESSION, obs["provider_session_date"])
            self.assertEqual("2026-08-21T10:00:00.000Z", obs["retrieved_at"])
            self.assertEqual(2089955445, obs["native_fields"]["FOREIGN_ROOM_MAX"]["value"])

    def test_native_net_and_total_values_are_retained_and_arithmetic_conflicts_fail_closed(self):
        conflict_cases = (
            (
                "trading_history",
                _sample_fhsc_trading_history_payload("HPG"),
                lambda payload: payload["data"]["data"][0]["total"].update({"volume": 2500001}),
                "TOTAL_VOLUME_SHARES",
                2500001,
            ),
            (
                "foreign_room",
                _sample_fhsc_foreign_room_payload("HPG"),
                lambda payload: payload["data"].update({"max_volume": 2089955446}),
                "FOREIGN_ROOM_MAX",
                2089955446,
            ),
            (
                "proprietary_trading",
                _sample_fhsc_proprietary_payload("HPG"),
                lambda payload: payload["data"]["net"]["total"].update({"volume": 530001}),
                "PROPRIETARY_NET_VOLUME",
                530001,
            ),
            (
                "order_statistics",
                _sample_fhsc_order_statistics_payload("HPG"),
                lambda payload: payload["data"].update({"net_volume": 4586201}),
                "ACTIVE_NET_VOLUME",
                4586201,
            ),
        )

        for endpoint_id, source_payload, mutate, field, expected_native_value in conflict_cases:
            with self.subTest(endpoint_id=endpoint_id):
                payload = json.loads(json.dumps(source_payload))
                mutate(payload)
                parsed = collector.parse_raw_observation_data("FHSC", endpoint_id, payload, MOCK_SESSION, "HPG")
                self.assertEqual("CONFLICTING_ARITHMETIC", parsed["parse_status"])
                self.assertEqual(expected_native_value, parsed["native_fields"][field]["value"])
                self.assertEqual({}, parsed["canonical_fields"])


class UnsupportedFieldsIsolationTests(unittest.TestCase):
    """Ensure unsupported/missing capabilities fail closed and do not fabricate data."""

    def test_unsupported_fields_fail_closed_and_remain_missing(self):
        # FREE_FLOAT is MISSING in current scope
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = collector.collect_market_evidence(
                session_date=MOCK_SESSION,
                symbols=["HPG"],
                capabilities=["FREE_FLOAT"],
                sources=["DNSE", "FHSC"],
                out_dir=tmp_dir,
                fetcher=mock_fetcher_success,
            )
            # Planned requests is 0, missing_capabilities records FREE_FLOAT
            self.assertIn("FREE_FLOAT", packet["source_routing"]["missing_capabilities"])
            self.assertEqual(0, len(packet["observations"]))


if __name__ == "__main__":
    unittest.main()
