"""Redirects and retries are governed by the registry, not by the responding host.

`3b4cc5f` made `acquire()` admit every request before making it, and that holds for the URL a
spec names. Two paths still stepped around it, and both are reachable without any code change
by a remote host alone:

  * a 302 off an allowlisted host was followed, retained and recorded, because
    `allow_redirects=True` delegates the next request to whatever the host replies;
  * a retry re-requested the same source after a 0.25s backoff, against a declared 10s
    minimum, because the interval was enforced once per spec rather than once per request.

Every test here uses a recording fetcher or a stubbed transport, so a request that should not
have happened is detectable as a call that was never made.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import official_document_acquisition as acquisition  # noqa: E402
import official_source_registry as registry  # noqa: E402

HTML = b"<html><body>notice</body></html>"


def spec(**overrides) -> dict:
    base = {"ticker": "VNM", "source_id": "hose", "document_class": "corporate_action_notice",
            "reporting_period": "2026", "canonical_url": "https://www.hsx.vn/notice.html"}
    base.update(overrides)
    return base


class LandingFetcher:
    """Reports a final URL that differs from the one requested, as a redirect would."""

    def __init__(self, final_url: str):
        self.urls: list[str] = []
        self.final_url = final_url

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        return 200, {"Content-Type": "text/html"}, HTML, self.final_url


class FlakyFetcher:
    """Fails `fail_times` times, then succeeds. Records every call."""

    def __init__(self, fail_times: int = 1):
        self.urls: list[str] = []
        self.fail_times = fail_times

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise TimeoutError("simulated")
        return 200, {"Content-Type": "text/html"}, HTML, url


def run(specs, *, fetcher, sleeps=None, clock=None):
    with tempfile.TemporaryDirectory() as tmp:
        return acquisition.acquire(
            specs, Path(tmp), fetcher=fetcher, registry=registry.load_registry(),
            sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
            **({"clock": clock} if clock else {}))


class RedirectLandingTests(unittest.TestCase):
    def test_bytes_from_an_unadmitted_landing_host_are_never_retained(self) -> None:
        fetcher = LandingFetcher("https://totally-unapproved.example.com/landed.html")
        result = run([spec()], fetcher=fetcher)
        outcome = result["outcomes"][0]
        self.assertEqual(outcome["state"], "redirect_refused_by_source_registry")
        self.assertEqual(outcome["reason"], registry.REASON_HOST_NOT_ALLOWED)
        self.assertNotIn("document_id", outcome, "refused bytes must not become a document")

    def test_a_redirect_within_the_allowlist_is_still_retained(self) -> None:
        fetcher = LandingFetcher("https://hsx.vn/notice.html")
        result = run([spec()], fetcher=fetcher)
        self.assertEqual(result["outcomes"][0]["state"], "retained")

    def test_the_redirect_bound_comes_from_the_registry(self) -> None:
        reg = registry.load_registry()
        self.assertEqual(acquisition._declared_max_redirects(reg),
                         reg["global_policy"]["max_redirects"])
        self.assertEqual(acquisition._declared_max_redirects({}), acquisition.MAX_REDIRECTS)


class RedirectHopAdmissionTests(unittest.TestCase):
    """`fetch_http` admits each hop *before* following it, not after landing."""

    class _Response:
        def __init__(self, status, headers, body=b"", redirect=False):
            self.status_code, self.headers, self._body = status, headers, body
            self.is_redirect = self.is_permanent_redirect = redirect

        def iter_content(self, chunk_size=1):
            yield self._body

        def close(self):
            pass

    def test_an_off_allowlist_hop_is_refused_before_it_is_requested(self) -> None:
        requested: list[str] = []

        def fake_get(url, **kwargs):
            requested.append(url)
            if len(requested) == 1:
                return self._Response(302, {"Location": "https://evil.example.com/x.html"},
                                      redirect=True)
            return self._Response(200, {"Content-Type": "text/html"}, HTML)

        original = acquisition.requests.get
        acquisition.requests.get = fake_get
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(ValueError,
                                            "redirect_refused_by_source_registry"):
                    acquisition.fetch_http(
                        "https://www.hsx.vn/notice.html",
                        temporary_path=Path(tmp) / "part",
                        admit_hop=lambda target: registry.admit(
                            "hose", target, "corporate_action_notice")["decision"]
                        == registry.ADMITTED)
        finally:
            acquisition.requests.get = original
        self.assertEqual(requested, ["https://www.hsx.vn/notice.html"],
                         "the refused hop must never be requested")


class RetryRateTests(unittest.TestCase):
    def test_a_retry_waits_out_the_declared_interval_not_the_backoff(self) -> None:
        # hose declares 10s. The first attempt stamps t=0; the retry is a second request to
        # the same host, so it waits the remaining 10 rather than a 0.25s backoff.
        ticks = iter([0.0, 0.0, 10.0])
        sleeps: list[float] = []
        fetcher = FlakyFetcher(fail_times=1)
        result = run([spec()], fetcher=fetcher, sleeps=sleeps, clock=lambda: next(ticks))
        self.assertEqual(len(fetcher.urls), 2, "the retry should still happen")
        self.assertEqual(sleeps, [10.0])
        self.assertEqual(result["outcomes"][0]["state"], "retained")

    def test_the_backoff_still_applies_when_no_interval_is_declared(self) -> None:
        sleeps: list[float] = []
        fetcher = FlakyFetcher(fail_times=1)
        with tempfile.TemporaryDirectory() as tmp:
            reg = registry.load_registry()
            for source in reg["sources"]:
                source["min_request_interval_seconds"] = 0
            acquisition.acquire([spec()], Path(tmp), fetcher=fetcher, registry=reg,
                                sleep=sleeps.append, clock=lambda: 0.0)
        self.assertEqual(sleeps, [0.25])


if __name__ == "__main__":
    unittest.main()
