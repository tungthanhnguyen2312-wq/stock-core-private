"""Contract test for public delivery of analysis_bundle.json."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "publish_dashboard_analysis_bundle_contract",
    ROOT / "publish_dashboard.py",
)
publisher = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(publisher)


class AnalysisBundlePublishContractTests(unittest.TestCase):
    def test_analysis_bundle_is_a_public_copy_artifact(self):
        self.assertIn(
            "analysis_bundle.json",
            publisher.COPY_ARTIFACTS,
        )
        self.assertIn(
            "analysis_bundle.json",
            publisher.SAFE_WEB_ARTIFACTS,
        )

    def test_copy_preserves_corporate_intelligence_payload(self):
        payload = {
            "tickers": {
                "AAA": {
                    "corporate_intelligence": {
                        "status": "partial",
                        "company_profile": {
                            "status": "missing",
                            "sources": [],
                        },
                        "company_subsidiaries": {
                            "status": "available",
                            "sources": [],
                        },
                        "ownership_structure": {
                            "status": "malformed",
                            "sources": [],
                        },
                        "major_shareholders": {
                            "status": "incomparable",
                            "sources": [],
                        },
                    }
                },
                "LEGACY": {},
            }
        }

        with (
            tempfile.TemporaryDirectory() as backend,
            tempfile.TemporaryDirectory() as web,
        ):
            backend_root = Path(backend)
            web_root = Path(web)

            source = backend_root / "analysis_bundle.json"
            source.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            old_backend = publisher.BACKEND_ROOT
            old_web = publisher.WEB_ROOT
            old_live = publisher.LIVE_MODE

            try:
                publisher.BACKEND_ROOT = backend_root
                publisher.WEB_ROOT = web_root
                publisher.LIVE_MODE = True

                self.assertIn(
                    "analysis_bundle.json",
                    publisher.plan_copy_artifacts(),
                )
                self.assertIn(
                    "analysis_bundle.json",
                    publisher.copy_public_artifacts(),
                )

                copied = json.loads(
                    (web_root / "analysis_bundle.json").read_text(
                        encoding="utf-8"
                    )
                )
            finally:
                publisher.BACKEND_ROOT = old_backend
                publisher.WEB_ROOT = old_web
                publisher.LIVE_MODE = old_live

        self.assertEqual(copied, payload)
        self.assertEqual(
            copied["tickers"]["AAA"]["corporate_intelligence"]["status"],
            "partial",
        )
        self.assertNotIn(
            "corporate_intelligence",
            copied["tickers"]["LEGACY"],
        )


if __name__ == "__main__":
    unittest.main()
