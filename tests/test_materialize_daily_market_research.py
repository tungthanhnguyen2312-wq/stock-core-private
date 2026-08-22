"""Validation test suite for daily market research materialization operator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from atomic_io import AtomicWriteError
import canonical_market_evidence_integration as canonical_integration_module
import tools.materialize_daily_market_research as materializer
from tools.materialize_daily_market_research import (
    CONTRACT_VERSION,
    RUN_SCHEMA_VERSION,
    materialize_daily_market_research,
    validate_completed_bundle,
)


def sample_synthetic_session_packet(session_date: str = "2026-08-20") -> dict:
    """Build a deterministic multi-source session packet fixture."""
    return {
        "packet_schema_version": "1.0.0",
        "contract_version": "capability_first_eod_collector/v1",
        "session_date": session_date,
        "created_at": f"{session_date}T18:05:00.000Z",
        "execution_mode": "SYNTHETIC_TEST",
        "request_budget": {
            "max_requests": 50,
            "used_requests": 8,
            "rate_limited_requests": 1,
            "budget_exhausted": False,
            "planned_requests_count": 8,
        },
        "source_routing": {
            "routed_capabilities": {},
            "single_source_capabilities": ["PUT_THROUGH_VOLUME_SHARES", "MATCHED_TRADED_VALUE_VND"],
            "missing_capabilities": ["FREE_FLOAT"],
        },
        "rate_limit_events": [],
        "revision_events": [],
        "observations": [
            # 1. HPG DNSE OHLC
            {
                "session": session_date,
                "instrument": "HPG",
                "source": "DNSE",
                "endpoint_id": "ohlc",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "revision_state": "INITIAL_OBSERVATION",
                "raw_response_retained": True,
                "raw_path": "raw/dnse_ohlc_HPG_11111111.json",
                "raw_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
                "native_fields": {
                    "OPEN_KVND": {"value": "21.5", "unit": "thousands_of_vnd_per_share", "raw_field": "o"},
                    "HIGH_KVND": {"value": "22.0", "unit": "thousands_of_vnd_per_share", "raw_field": "h"},
                    "LOW_KVND": {"value": "21.3", "unit": "thousands_of_vnd_per_share", "raw_field": "l"},
                    "CLOSE_KVND": {"value": "21.85", "unit": "thousands_of_vnd_per_share", "raw_field": "c"},
                    "MATCHED_VOLUME_SHARES": {"value": 2500000, "unit": "shares", "raw_field": "v"},
                },
                "canonical_fields": {
                    "OPEN_VND": {
                        "value": "21500",
                        "unit": "vnd_per_share",
                        "derived_from": "OPEN_KVND",
                        "contract_id": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
                    },
                    "HIGH_VND": {
                        "value": "22000",
                        "unit": "vnd_per_share",
                        "derived_from": "HIGH_KVND",
                        "contract_id": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
                    },
                    "LOW_VND": {
                        "value": "21300",
                        "unit": "vnd_per_share",
                        "derived_from": "LOW_KVND",
                        "contract_id": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
                    },
                    "CLOSE_VND": {
                        "value": "21850",
                        "unit": "vnd_per_share",
                        "derived_from": "CLOSE_KVND",
                        "contract_id": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
                    },
                    "MATCHED_VOLUME_SHARES": {
                        "value": 2500000,
                        "unit": "shares",
                    },
                },
                "authority_effect": "NONE",
            },
            # 2. HPG FHSC Trading History (volume + traded value)
            {
                "session": session_date,
                "instrument": "HPG",
                "source": "FHSC",
                "endpoint_id": "trading_history",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "revision_state": "INITIAL_OBSERVATION",
                "raw_response_retained": True,
                "raw_path": "raw/fhsc_trading_history_HPG_22222222.json",
                "raw_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
                "native_fields": {
                    "MATCHED_VOLUME_SHARES": {"value": 2200000, "unit": "shares"},
                    "PUT_THROUGH_VOLUME_SHARES": {"value": 300000, "unit": "shares"},
                    "TOTAL_VOLUME_SHARES": {"value": 2500000, "unit": "shares"},
                    "MATCHED_TRADED_VALUE_VND": {"value": 47300000000, "unit": "vnd"},
                    "PUT_THROUGH_TRADED_VALUE_VND": {"value": 6450000000, "unit": "vnd"},
                    "TOTAL_TRADED_VALUE_VND": {"value": 53750000000, "unit": "vnd"},
                },
                "canonical_fields": {
                    "MATCHED_VOLUME_SHARES": {"value": 2200000, "unit": "shares"},
                    "PUT_THROUGH_VOLUME_SHARES": {"value": 300000, "unit": "shares"},
                    "TOTAL_VOLUME_SHARES": {"value": 2500000, "unit": "shares"},
                    "MATCHED_TRADED_VALUE_VND": {"value": 47300000000, "unit": "vnd_raw_not_thousands"},
                    "PUT_THROUGH_TRADED_VALUE_VND": {"value": 6450000000, "unit": "vnd_raw_not_thousands"},
                    "TOTAL_TRADED_VALUE_VND": {"value": 53750000000, "unit": "vnd_raw_not_thousands"},
                },
                "authority_effect": "NONE",
            },
            # 3. HPG FHSC Foreign Room
            {
                "session": session_date,
                "instrument": "HPG",
                "source": "FHSC",
                "endpoint_id": "foreign_room",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "raw_response_retained": True,
                "raw_path": "raw/fhsc_foreign_room_HPG_33333333.json",
                "raw_sha256": "3333333333333333333333333333333333333333333333333333333333333333",
                "native_fields": {
                    "FOREIGN_ROOM_MAX": {"value": 2089955445, "unit": "shares"},
                    "FOREIGN_ROOM_OWNED": {"value": 1969955445, "unit": "shares"},
                    "FOREIGN_ROOM_AVAILABLE": {"value": 120000000, "unit": "shares"},
                },
                "canonical_fields": {
                    "FOREIGN_ROOM_MAX": {"value": 2089955445, "unit": "shares"},
                    "FOREIGN_ROOM_OWNED": {"value": 1969955445, "unit": "shares"},
                    "FOREIGN_ROOM_AVAILABLE": {"value": 120000000, "unit": "shares"},
                },
                "authority_effect": "NONE",
            },
            # 4. HPG FHSC Proprietary Trading
            {
                "session": session_date,
                "instrument": "HPG",
                "source": "FHSC",
                "endpoint_id": "proprietary_trading",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "raw_response_retained": True,
                "raw_path": "raw/fhsc_proprietary_HPG_44444444.json",
                "raw_sha256": "4444444444444444444444444444444444444444444444444444444444444444",
                "native_fields": {
                    "PROPRIETARY_BUY_VOLUME": {"value": 850000, "unit": "shares"},
                    "PROPRIETARY_SELL_VOLUME": {"value": 320000, "unit": "shares"},
                    "PROPRIETARY_NET_VOLUME": {"value": 530000, "unit": "shares"},
                    "PROPRIETARY_BUY_VALUE": {"value": 18275000000, "unit": "vnd"},
                    "PROPRIETARY_SELL_VALUE": {"value": 6880000000, "unit": "vnd"},
                    "PROPRIETARY_NET_VALUE": {"value": 11395000000, "unit": "vnd"},
                },
                "canonical_fields": {
                    "PROPRIETARY_BUY_VOLUME": {"value": 850000, "unit": "shares"},
                    "PROPRIETARY_SELL_VOLUME": {"value": 320000, "unit": "shares"},
                    "PROPRIETARY_NET_VOLUME": {"value": 530000, "unit": "shares"},
                    "PROPRIETARY_BUY_VALUE": {"value": 18275000000, "unit": "vnd_raw_not_thousands"},
                    "PROPRIETARY_SELL_VALUE": {"value": 6880000000, "unit": "vnd_raw_not_thousands"},
                    "PROPRIETARY_NET_VALUE": {"value": 11395000000, "unit": "vnd_raw_not_thousands"},
                },
                "authority_effect": "NONE",
            },
            # 5. HPG FHSC Order Statistics
            {
                "session": session_date,
                "instrument": "HPG",
                "source": "FHSC",
                "endpoint_id": "order_statistics",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "raw_response_retained": True,
                "raw_path": "raw/fhsc_orders_HPG_55555555.json",
                "raw_sha256": "5555555555555555555555555555555555555555555555555555555555555555",
                "native_fields": {
                    "ACTIVE_BUY_ORDER_COUNT": {"value": 18422, "unit": "orders"},
                    "ACTIVE_SELL_ORDER_COUNT": {"value": 14205, "unit": "orders"},
                    "ACTIVE_BUY_VOLUME": {"value": 9871300, "unit": "shares"},
                    "ACTIVE_SELL_VOLUME": {"value": 5285100, "unit": "shares"},
                    "ACTIVE_NET_VOLUME": {"value": 4586200, "unit": "shares"},
                },
                "canonical_fields": {
                    "ACTIVE_BUY_ORDER_COUNT": {"value": 18422, "unit": "orders"},
                    "ACTIVE_SELL_ORDER_COUNT": {"value": 14205, "unit": "orders"},
                    "ACTIVE_BUY_VOLUME": {"value": 9871300, "unit": "shares"},
                    "ACTIVE_SELL_VOLUME": {"value": 5285100, "unit": "shares"},
                    "ACTIVE_NET_VOLUME": {"value": 4586200, "unit": "shares"},
                },
                "authority_effect": "NONE",
            },
            # 6. VCB Missing Requested Session
            {
                "session": session_date,
                "instrument": "VCB",
                "source": "DNSE",
                "endpoint_id": "ohlc",
                "status": "MISSING_REQUESTED_SESSION",
                "usability_state": "MISSING",
                "raw_response_retained": False,
                "authority_effect": "NONE",
            },
            # 7. SSI Provider Rate Limited (DNSE) & Budget Exhausted (FHSC)
            {
                "session": session_date,
                "instrument": "SSI",
                "source": "DNSE",
                "endpoint_id": "ohlc",
                "status": "PROVIDER_RATE_LIMITED",
                "usability_state": "PROVIDER_RATE_LIMITED",
                "raw_response_retained": False,
            },
            {
                "session": session_date,
                "instrument": "SSI",
                "source": "FHSC",
                "endpoint_id": "trading_history",
                "status": "BUDGET_EXHAUSTED",
                "usability_state": "BUDGET_EXHAUSTED",
                "raw_response_retained": False,
            },
            # 8. VNM Conflicting volume arithmetic
            {
                "session": session_date,
                "instrument": "VNM",
                "source": "FHSC",
                "endpoint_id": "trading_history",
                "status": "ACQUIRED",
                "usability_state": "RESEARCH_USABLE",
                "raw_response_retained": True,
                "raw_path": "raw/conflict_vnm.json",
                "raw_sha256": "vnm_conflict_sha",
                "native_fields": {
                    "MATCHED_VOLUME_SHARES": {"value": 2000000, "unit": "shares"},
                    "PUT_THROUGH_VOLUME_SHARES": {"value": 300000, "unit": "shares"},
                    "TOTAL_VOLUME_SHARES": {"value": 10000000, "unit": "shares"},
                },
                "canonical_fields": {
                    "TOTAL_VOLUME_SHARES": {"value": 10000000, "unit": "shares"},
                },
            },
        ],
        "authority_boundaries": {
            "authority_effect": "NONE",
            "raw_as_traded_promoted": False,
            "pit_backtest_eligible": False,
            "liquidity_sizing_authority": "BLOCKED",
            "valuation_authority": False,
            "recommendation_authority": False,
            "database_mutated": False,
        },
        "packet_sha256": "8888888888888888888888888888888888888888888888888888888888888888",
        "packet_identity": "capability_first_eod_packet:8888888888888888888888888888888888888888888888888888888888888888",
    }


class MaterializeDailyMarketResearchTests(unittest.TestCase):
    """Validation test suite proving daily market research materialization workflow."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.session_date = "2026-08-20"
        self.packet = sample_synthetic_session_packet(self.session_date)
        self.packet_file = self.temp_dir / "session_packet.json"
        self.packet_file.write_text(json.dumps(self.packet, indent=2), encoding="utf-8")
        self.out_dir = self.temp_dir / "materialized_output"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _completed_run_dir(self) -> Path:
        session_root = self.out_dir / f"daily-market-research-{self.session_date}"
        candidates = sorted(path for path in session_root.glob("run-*") if path.is_dir())
        self.assertEqual(1, len(candidates))
        return candidates[0]

    def _session_root(self) -> Path:
        return self.out_dir / f"daily-market-research-{self.session_date}"

    # 1. Exact-session packet materializes successfully
    def test_exact_session_packet_materializes_successfully(self):
        manifest = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        self.assertEqual("MATERIALIZATION_SUCCESS", manifest["disposition"])
        self.assertEqual(self.session_date, manifest["requested_session_date"])
        self.assertEqual(RUN_SCHEMA_VERSION, manifest["run_schema_version"])
        self.assertEqual(CONTRACT_VERSION, manifest["contract_version"])

        # Check output files exist
        bundle_dir = self._completed_run_dir()
        self.assertTrue((bundle_dir / "market_research_artifact.json").is_file())
        self.assertTrue((bundle_dir / "canonical_integration.json").is_file())
        self.assertTrue((bundle_dir / "run_manifest.json").is_file())
        self.assertTrue((bundle_dir / "completion_record.json").is_file())

    # 2. Wrong-session packet fails closed
    def test_wrong_session_packet_fails_closed(self):
        manifest = materialize_daily_market_research(
            session_date="2026-08-21",  # Requested 21, but packet has 20
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        self.assertEqual("EXACT_SESSION_MISMATCH", manifest["disposition"])
        self.assertIn("Requested session date '2026-08-21' does not match packet session date '2026-08-20'", manifest["error_reason"])
        self.assertEqual("NONE", manifest["authority_effect"])

    # 3. Canonical integration identity is carried into output
    def test_canonical_integration_identity_carried_into_output(self):
        manifest = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        integration_json = json.loads((self._completed_run_dir() / "canonical_integration.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["canonical_integration_identity"], integration_json["integration_identity"])
        self.assertEqual(manifest["canonical_integration_sha256"], integration_json["integration_sha256"])

    # 4. Research artifact identity is carried into manifest
    def test_research_artifact_identity_carried_into_manifest(self):
        manifest = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        artifact_json = json.loads((self._completed_run_dir() / "market_research_artifact.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["research_artifact_identity"], artifact_json["artifact_id"])
        self.assertEqual(manifest["research_artifact_content_hash"], artifact_json["content_hash"])

    # 5. DNSE and FHSC-only capabilities both survive
    def test_dnse_and_fhsc_only_capabilities_both_survive(self):
        manifest = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        self.assertIn("DNSE", manifest["sources_represented"])
        self.assertIn("FHSC", manifest["sources_represented"])
        self.assertIn("PRICE", manifest["capabilities_represented"])
        self.assertIn("TRADED_VALUE", manifest["capabilities_represented"])
        self.assertIn("FOREIGN", manifest["capabilities_represented"])
        self.assertIn("PROPRIETARY", manifest["capabilities_represented"])
        self.assertIn("MICROSTRUCTURE", manifest["capabilities_represented"])

        artifact_json = json.loads((self._completed_run_dir() / "market_research_artifact.json").read_text(encoding="utf-8"))
        hpg_rec = next(r for r in artifact_json["records"] if r["instrument_identity"]["symbol"] == "HPG")
        evidence = hpg_rec["canonical_market_evidence"]
        self.assertIn("DNSE", evidence["prices"])
        self.assertIn("FHSC", evidence["traded_values"])
        self.assertIn("FHSC", evidence["foreign_room"])

    # 6. Provenance is retained
    def test_provenance_is_retained(self):
        materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        artifact_json = json.loads((self._completed_run_dir() / "market_research_artifact.json").read_text(encoding="utf-8"))
        hpg_rec = next(r for r in artifact_json["records"] if r["instrument_identity"]["symbol"] == "HPG")
        close_entry = hpg_rec["canonical_market_evidence"]["prices"]["DNSE"]["CLOSE_VND"]
        self.assertEqual("1111111111111111111111111111111111111111111111111111111111111111", close_entry["raw_sha256"])
        self.assertEqual("DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1", close_entry["contract_id"])
        self.assertEqual("21.85", close_entry["provider_native_value"])

    # 7. Missing requested session remains missing
    def test_missing_requested_session_remains_missing(self):
        manifest = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        self.assertEqual(1, manifest["missing_observations_count"])

        artifact_json = json.loads((self._completed_run_dir() / "market_research_artifact.json").read_text(encoding="utf-8"))
        vcb_rec = next(r for r in artifact_json["records"] if r["instrument_identity"]["symbol"] == "VCB")
        unacquired = vcb_rec["canonical_market_evidence"]["unacquired_capabilities"]
        self.assertEqual(1, len(unacquired))
        self.assertEqual("MISSING_REQUESTED_SESSION", unacquired[0]["status"])

    # 8. Provider rate-limit and local budget exhaustion remain distinct
    def test_rate_limit_and_budget_exhaustion_distinct(self):
        manifest = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        self.assertEqual(1, manifest["rate_limited_observations_count"])
        self.assertEqual(1, manifest["budget_exhausted_observations_count"])

        artifact_json = json.loads((self._completed_run_dir() / "market_research_artifact.json").read_text(encoding="utf-8"))
        ssi_rec = next(r for r in artifact_json["records"] if r["instrument_identity"]["symbol"] == "SSI")
        unacquired = ssi_rec["canonical_market_evidence"]["unacquired_capabilities"]
        statuses = {u["source"]: u["status"] for u in unacquired}
        self.assertEqual("PROVIDER_RATE_LIMITED", statuses["DNSE"])
        self.assertEqual("BUDGET_EXHAUSTED", statuses["FHSC"])

    # 9. Conflict remains fail-closed
    def test_conflict_remains_fail_closed(self):
        manifest = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        self.assertTrue(manifest["conflicting_observations_count"] >= 1)

        artifact_json = json.loads((self._completed_run_dir() / "market_research_artifact.json").read_text(encoding="utf-8"))
        vnm_rec = next(r for r in artifact_json["records"] if r["instrument_identity"]["symbol"] == "VNM")
        evidence = vnm_rec["canonical_market_evidence"]
        self.assertTrue(len(evidence["conflicts"]) >= 1)
        tot_vol = evidence["volumes"]["FHSC"]["TOTAL_VOLUME_SHARES"]
        self.assertIsNone(tot_vol["value"])
        self.assertFalse(tot_vol["is_usable"])

    # 10. Partial/staging output is not promoted on validation failure
    def test_partial_staging_not_promoted_on_failure(self):
        # Corrupt packet json file
        bad_packet_file = self.temp_dir / "corrupted_packet.json"
        bad_packet_file.write_text("{ incomplete json ...", encoding="utf-8")
        manifest = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=bad_packet_file,
            out_dir=self.out_dir,
        )
        self.assertEqual("MALFORMED_PACKET_JSON", manifest["disposition"])
        session_root = self.out_dir / f"daily-market-research-{self.session_date}"
        self.assertFalse(any(session_root.glob("run-*")))

    # 11. Identical retained input produces identical deterministic output identities
    def test_identical_input_produces_identical_deterministic_identities(self):
        manifest1 = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        bundle_dir = Path(manifest1["run_directory"])
        original_bytes = {
            filename: (bundle_dir / filename).read_bytes()
            for filename in ("canonical_integration.json", "market_research_artifact.json", "run_manifest.json", "completion_record.json")
        }
        manifest2 = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        self.assertTrue(manifest2["is_idempotent_replay"])
        self.assertEqual(manifest1["materialization_identity"], manifest2["materialization_identity"])
        self.assertEqual(manifest1["research_artifact_content_hash"], manifest2["research_artifact_content_hash"])
        self.assertEqual(manifest1["research_artifact_identity"], manifest2["research_artifact_identity"])
        self.assertEqual(manifest1["canonical_integration_sha256"], manifest2["canonical_integration_sha256"])
        self.assertEqual(original_bytes, {
            filename: (bundle_dir / filename).read_bytes()
            for filename in original_bytes
        })

    # 12. Changed retained input does not overwrite prior version silently
    def test_changed_retained_input_produces_distinct_identity(self):
        manifest1 = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        first_bundle = Path(manifest1["run_directory"])
        first_bundle_bytes = {
            filename: (first_bundle / filename).read_bytes()
            for filename in ("canonical_integration.json", "market_research_artifact.json", "run_manifest.json", "completion_record.json")
        }
        # Modify observation price
        modified_packet = dict(self.packet)
        obs_copy = [dict(o) for o in self.packet["observations"]]
        obs_copy[0] = dict(obs_copy[0])
        obs_copy[0]["canonical_fields"] = dict(obs_copy[0]["canonical_fields"])
        obs_copy[0]["canonical_fields"]["CLOSE_VND"] = {
            "value": "22500",
            "unit": "vnd_per_share",
            "contract_id": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
        }
        modified_packet["observations"] = obs_copy
        modified_packet["packet_sha256"] = "9999999999999999999999999999999999999999999999999999999999999999"

        manifest2 = materialize_daily_market_research(
            session_date=self.session_date,
            raw_packet_dict=modified_packet,
            out_dir=self.out_dir,
        )
        self.assertNotEqual(manifest1["research_artifact_content_hash"], manifest2["research_artifact_content_hash"])
        self.assertNotEqual(manifest1["source_packet_sha256"], manifest2["source_packet_sha256"])
        self.assertNotEqual(manifest1["materialization_identity"], manifest2["materialization_identity"])
        self.assertTrue(first_bundle.is_dir())
        self.assertEqual(2, len([path for path in self._session_root().glob("run-*") if path.is_dir()]))
        self.assertEqual(first_bundle_bytes, {
            filename: (first_bundle / filename).read_bytes()
            for filename in first_bundle_bytes
        })

    # 13. Prohibited authority uses remain blocked
    def test_prohibited_authority_uses_fail_closed(self):
        prohibited_uses = ("liquidity_sizing", "valuation", "raw_as_traded_pit_backtest", "recommendation_authority")
        for p_use in prohibited_uses:
            manifest = materialize_daily_market_research(
                session_date=self.session_date,
                packet_path=self.packet_file,
                out_dir=self.out_dir,
                permitted_use=p_use,
            )
            self.assertEqual("PROHIBITED_USE_REJECTED", manifest["artifact_status"])

    # 14. No secrets appear in output
    def test_no_secrets_appear_in_output(self):
        materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        sensitive_patterns = ("api_key", "x-fh-apikey", "authorization", "secret", "passwd")
        for filename in ("market_research_artifact.json", "canonical_integration.json", "run_manifest.json", "completion_record.json"):
            content = (self._completed_run_dir() / filename).read_text(encoding="utf-8").lower()
            for pat in sensitive_patterns:
                self.assertNotIn(pat, content)

    def test_failure_after_first_or_second_component_never_promotes_final_bundle(self):
        original_write = materializer.atomic_write_json
        for fail_on_call in (2, 3):
            with self.subTest(fail_on_call=fail_on_call):
                calls = 0

                def fail_after_component(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == fail_on_call:
                        raise AtomicWriteError("simulated_staging_write_failure")
                    return original_write(*args, **kwargs)

                with patch.object(materializer, "atomic_write_json", side_effect=fail_after_component):
                    with self.assertRaises(AtomicWriteError):
                        materialize_daily_market_research(
                            session_date=self.session_date,
                            packet_path=self.packet_file,
                            out_dir=self.out_dir,
                        )
                self.assertFalse(any(self._session_root().glob("run-*")))
                self.assertTrue(any(self._session_root().glob(".*.staging-*")))
                shutil.rmtree(self._session_root(), ignore_errors=True)

    def test_success_promotes_complete_bundle_and_completion_inventory_validates_it(self):
        manifest = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        bundle_dir = Path(manifest["run_directory"])
        self.assertEqual(set(("canonical_integration.json", "market_research_artifact.json", "run_manifest.json", "completion_record.json")), {
            path.name for path in bundle_dir.iterdir() if path.is_file()
        })
        self.assertFalse(any(self._session_root().glob(".*.staging-*")))
        validated = validate_completed_bundle(bundle_dir, expected_materialization_identity=manifest["materialization_identity"])
        completion = json.loads((bundle_dir / "completion_record.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["manifest_content_identity"], validated["manifest_content_identity"])
        self.assertEqual(
            completion["file_inventory"]["run_manifest.json"]["sha256"],
            hashlib.sha256((bundle_dir / "run_manifest.json").read_bytes()).hexdigest(),
        )

    def test_incomplete_staging_directory_is_non_authoritative(self):
        interrupted = self._session_root() / ".interrupted.staging-operator"
        interrupted.mkdir(parents=True)
        (interrupted / "canonical_integration.json").write_text("{}", encoding="utf-8")
        manifest = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        self.assertTrue(interrupted.is_dir())
        self.assertEqual(manifest["materialization_identity"], validate_completed_bundle(Path(manifest["run_directory"]))["materialization_identity"])
        self.assertEqual(1, len([path for path in self._session_root().glob("run-*") if path.is_dir()]))

    def test_manifest_content_identity_is_non_recursive(self):
        manifest = materialize_daily_market_research(
            session_date=self.session_date,
            packet_path=self.packet_file,
            out_dir=self.out_dir,
        )
        stored = json.loads((Path(manifest["run_directory"]) / "run_manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("manifest_sha256", stored)
        self.assertIn("manifest_content_identity", stored)
        self.assertEqual(stored["manifest_content_identity"], validate_completed_bundle(Path(manifest["run_directory"]))["manifest_content_identity"])


if __name__ == "__main__":
    unittest.main()
