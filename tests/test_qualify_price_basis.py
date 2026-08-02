from __future__ import annotations

import copy
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.qualify_price_basis import analyze_event
from export_ai_bundle import build_price_basis_contract


def rows(pre: float, post: float):
    return [{"date": f"2024-01-0{i}", "close": pre, "provider": "VCI"} for i in range(1, 4)] + [{"date": f"2024-01-0{i}", "close": post, "provider": "VCI"} for i in range(4, 7)]


def event(ratio=0.20):
    return {"canonical_event_id": "event-1", "ticker": "HPG", "event_type": "bonus_share", "ex_date": "2024-01-04", "entitlement_ratio": ratio, "qualification_state": "qualified"}


class EmpiricalPriceBasisTests(unittest.TestCase):
    def test_adjusted_and_raw_synthetic_series(self):
        self.assertEqual(analyze_event(event(), rows(100, 100))["classification"], "adjusted")
        self.assertEqual(analyze_event(event(), rows(100, 100 / 1.2))["classification"], "raw")

    def test_incomplete_evidence_and_insufficient_sessions_fail_closed(self):
        self.assertEqual(analyze_event({"ticker": "HPG"}, rows(100, 100))["status"], "excluded")
        self.assertEqual(analyze_event(event(), rows(100, 100)[:4])["status"], "excluded")

    def test_contradictory_or_ambiguous_event_is_not_classified(self):
        self.assertEqual(analyze_event(event(), rows(100, 92))["status"], "excluded")

    def test_diagnostics_are_deterministic_and_version_scoped(self):
        first = analyze_event(event(), rows(100, 100 / 1.2))
        self.assertEqual(first, analyze_event(copy.deepcopy(event()), rows(100, 100 / 1.2)))
        self.assertEqual(first["hose_price_band_allowance"], 0.07)

    def test_unverified_empirical_result_cannot_enable_bundle_price_basis(self):
        contract = build_price_basis_contract({"price_basis": "raw", "price_basis_verified": False})
        self.assertEqual(contract["price_basis"], "unknown")
        self.assertFalse(contract["price_basis_verified"])
        self.assertFalse(contract["is_actionable"])


if __name__ == "__main__":
    unittest.main()
