"""The source registry gates the acquirer, at the point requests are actually made.

Until this milestone `admit()`'s only caller in the tree was the offline slice runner, which
issues no requests. `official_document_acquisition.acquire()` fetched whatever URL a spec
named — no host allowlist, no per-source document-type check, no rate rule, no approval check.
The reviewable JSON governed a JSON file.

Every test here uses a recording fetcher, so a request that should have been refused is
detectable as a call that was never made rather than as traffic that has already left.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import official_document_acquisition as acquisition  # noqa: E402
import official_source_registry as registry  # noqa: E402

HTML = b"<html><body>notice</body></html>"


class RecordingFetcher:
    """Stands in for the network. Records every URL it is asked for."""

    def __init__(self, body: bytes = HTML):
        self.urls: list[str] = []
        self.body = body

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        return 200, {"Content-Type": "text/html"}, self.body, url


def spec(**overrides) -> dict:
    base = {"ticker": "VNM", "source_id": "hose", "document_class": "corporate_action_notice",
            "reporting_period": "2026", "canonical_url": "https://www.hsx.vn/notice.html"}
    base.update(overrides)
    return base


def run(specs, *, reg=None, fetcher=None, sleeps=None, clock=None):
    fetcher = fetcher or RecordingFetcher()
    with tempfile.TemporaryDirectory() as tmp:
        result = acquisition.acquire(
            specs, Path(tmp), fetcher=fetcher,
            registry=reg if reg is not None else registry.load_registry(),
            sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
            **({"clock": clock} if clock else {}))
    return result, fetcher


class GateIsActuallyConsultedTests(unittest.TestCase):
    def test_an_admitted_request_is_fetched(self) -> None:
        result, fetcher = run([spec()])
        self.assertEqual(len(fetcher.urls), 1)
        self.assertEqual(result["outcomes"][0]["state"], "retained")

    def test_a_host_off_the_allowlist_is_never_requested(self) -> None:
        result, fetcher = run([spec(canonical_url="https://evil-hsx.vn/notice.html")])
        self.assertEqual(fetcher.urls, [], "a refused host must produce no request at all")
        self.assertEqual(result["outcomes"][0]["state"], "refused_by_source_registry")
        self.assertEqual(result["outcomes"][0]["reason"], registry.REASON_HOST_NOT_ALLOWED)

    def test_a_document_type_that_source_does_not_publish_is_never_requested(self) -> None:
        # `annual_report` is declared by issuer_ir, not by hose.
        result, fetcher = run([spec(document_class="annual_report")])
        self.assertEqual(fetcher.urls, [])
        self.assertEqual(result["outcomes"][0]["reason"], registry.REASON_DOCUMENT_TYPE)

    def test_an_unknown_source_is_never_requested(self) -> None:
        result, fetcher = run([spec(source_id="nope")])
        self.assertEqual(fetcher.urls, [])
        self.assertEqual(result["outcomes"][0]["reason"], registry.REASON_UNKNOWN_SOURCE)

    def test_a_spec_without_a_source_is_rejected_before_anything_else(self) -> None:
        result, fetcher = run([{k: v for k, v in spec().items() if k != "source_id"}])
        self.assertEqual(fetcher.urls, [])
        self.assertEqual(result["outcomes"][0]["state"], "missing_source_id")


class GovernanceStateTests(unittest.TestCase):
    def test_a_declared_but_unapproved_source_is_never_requested(self) -> None:
        reg = copy.deepcopy(registry.load_registry())
        for source in reg["sources"]:
            source["activation"] = "declared"
        result, fetcher = run([spec()], reg=reg)
        self.assertEqual(fetcher.urls, [])
        self.assertEqual(result["outcomes"][0]["reason"], registry.REASON_NOT_APPROVED)

    def test_an_unverifiable_approval_instant_stops_every_request(self) -> None:
        reg = copy.deepcopy(registry.load_registry())
        reg["approval_state"].pop(registry.APPROVAL_PROVENANCE_FIELD, None)
        result, fetcher = run([spec(), spec(ticker="HPG")], reg=reg)
        self.assertEqual(fetcher.urls, [])
        self.assertTrue(all(o["reason"] == registry.REASON_APPROVAL_TIMESTAMP
                            for o in result["outcomes"]))


class RateRuleTests(unittest.TestCase):
    def test_the_wait_is_the_declared_interval_minus_time_already_elapsed(self) -> None:
        # hose declares 10s. The first request stamps t=0; by the second, 4s have passed, so
        # the acquirer waits 6 rather than the full interval or nothing at all.
        ticks = iter([0.0, 4.0, 10.0])
        sleeps: list[float] = []
        _, fetcher = run([spec(canonical_url="https://www.hsx.vn/a.html"),
                          spec(canonical_url="https://www.hsx.vn/b.html")],
                         sleeps=sleeps, clock=lambda: next(ticks))
        self.assertEqual(len(fetcher.urls), 2, "both requests should still happen")
        self.assertEqual(sleeps, [6.0])

    def test_separate_sources_do_not_share_an_interval(self) -> None:
        sleeps: list[float] = []
        _, fetcher = run([spec(source_id="hose", canonical_url="https://www.hsx.vn/a.html"),
                          spec(source_id="hnx", canonical_url="https://www.hnx.vn/b.html")],
                         sleeps=sleeps)
        self.assertEqual(len(fetcher.urls), 2)
        self.assertEqual(sleeps, [])


class VocabularyTests(unittest.TestCase):
    """The acquirer could not even ask for the notices that carry an ex-date."""

    def test_the_registry_supplies_the_requestable_document_types(self) -> None:
        declared = acquisition.declared_document_types(registry.load_registry())
        for missing_before in ("ex_right_notice", "listing_change_notice",
                               "last_registration_date_notice"):
            self.assertIn(missing_before, declared)
            self.assertNotIn(missing_before, acquisition.DOCUMENT_CLASSES)

    def test_an_ex_right_notice_is_now_a_well_formed_request(self) -> None:
        result, fetcher = run([spec(document_class="ex_right_notice")])
        self.assertEqual(result["outcomes"][0]["state"], "retained")
        self.assertEqual(len(fetcher.urls), 1)

    def test_a_type_no_source_declares_is_still_malformed(self) -> None:
        result, fetcher = run([spec(document_class="press_release")])
        self.assertEqual(fetcher.urls, [])
        self.assertEqual(result["outcomes"][0]["state"], "unsupported_request")

    def test_bounded_official_exchange_statistics_type_is_host_scoped(self) -> None:
        result, fetcher = run([
            spec(
                document_class="official_exchange_annual_trading_statistics",
                canonical_url="https://staticfile.hsx.vn/annual-statistics.pdf",
            )
        ])
        self.assertEqual(result["outcomes"][0]["state"], "retained")
        self.assertEqual(fetcher.urls, ["https://staticfile.hsx.vn/annual-statistics.pdf"])

    def test_bounded_daily_trading_summary_type_is_host_scoped(self) -> None:
        result, fetcher = run([
            spec(
                document_class="official_exchange_daily_trading_summary",
                canonical_url="https://staticfile.hsx.vn/daily-trading-summary.pdf",
            )
        ])
        self.assertEqual(result["outcomes"][0]["state"], "retained")
        self.assertEqual(fetcher.urls, ["https://staticfile.hsx.vn/daily-trading-summary.pdf"])


if __name__ == "__main__":
    unittest.main()
