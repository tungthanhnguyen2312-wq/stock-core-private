from __future__ import annotations

import hashlib

import pytest

from official_source_route_coverage import (
    ROUTE_CAPABILITY_CHARACTERIZED, ROUTE_DISCOVERED, ROUTE_READY_FOR_OWNER_PROMOTION,
    ROUTE_TECHNICALLY_REACHABLE, RouteCoverageError, build_artifact, inspect_seed, validate_route,
)


def _fetcher(url: str):
    body = ("<html><body>Công ty Cổ phần Example Issuer "
            "<a href='/ir/annual.pdf'>Báo cáo tài chính kiểm toán</a>"
            "<a href='/ir/dividend.pdf'>Thông báo cổ tức</a></body></html>").encode()
    return 200, {"Content-Type": "text/html"}, body, url


def test_full_ownership_and_capability_route_is_ready_for_owner_review() -> None:
    route = inspect_seed({"ticker": "EXM", "issuer_id": "Công ty Cổ phần Example Issuer", "locator": "https://issuer.example/ir"}, fetcher=_fetcher)
    assert route["qualification_state"] == ROUTE_READY_FOR_OWNER_PROMOTION
    assert route["capability"]["demonstrated_evidence_categories"] == ["corporate_action_evidence", "financial_evidence"]
    assert route["ownership_evidence"]["source_sha256"] == hashlib.sha256(_fetcher("x")[2]).hexdigest()
    assert validate_route(route)["provenance"]["response_bytes"] > 0


def test_retained_payload_hash_tampering_fails_closed() -> None:
    route = inspect_seed({"ticker": "EXM", "issuer_id": "Công ty Cổ phần Example Issuer", "locator": "https://issuer.example/ir"}, fetcher=_fetcher)
    route["provenance"]["response_sha256"] = "0" * 64
    with pytest.raises(RouteCoverageError, match="retained_raw_payload_hash_mismatch"):
        validate_route(route)


def test_ambiguous_identity_cannot_imply_ownership_or_readiness() -> None:
    route = inspect_seed({"ticker": "EXM", "issuer_id": "Other Issuer", "locator": "https://issuer.example/ir"}, fetcher=_fetcher)
    assert route["qualification_state"] == ROUTE_TECHNICALLY_REACHABLE
    assert route["ownership_evidence"] is None


def test_guessed_domain_seed_is_rejected() -> None:
    with pytest.raises(RouteCoverageError, match="unguarded_or_guessed_domain_seed"):
        validate_route({"instrument_id": "EXM", "issuer_id": "Issuer", "source_family": "issuer_ir", "canonical_locator": "https://issuer.example", "qualification_state": ROUTE_DISCOVERED, "access_state": "UNKNOWN", "capability": {"characterized": False}, "seed_provenance": "guessed_from_ticker"})


def test_lifecycle_cannot_skip_evidence_or_capability() -> None:
    with pytest.raises(RouteCoverageError, match="lifecycle_state_overclaim"):
        validate_route({"instrument_id": "EXM", "issuer_id": "Issuer", "source_family": "issuer_ir", "canonical_locator": "https://issuer.example", "qualification_state": ROUTE_CAPABILITY_CHARACTERIZED, "access_state": "REACHABLE", "capability": {"characterized": False}, "seed_provenance": "retained_repository_candidate", "provenance": {"raw_payload_base64": "", "response_sha256": hashlib.sha256(b"").hexdigest()}})


def test_duplicate_normalization_and_artifact_are_deterministic() -> None:
    route = inspect_seed({"ticker": "EXM", "issuer_id": "Công ty Cổ phần Example Issuer", "locator": "https://issuer.example/ir"}, fetcher=_fetcher)
    one = build_artifact(baseline={"research_universe": 1}, routes=[route])
    two = build_artifact(baseline={"research_universe": 1}, routes=[route])
    assert one == two
    assert one["lifecycle_gate_counts"]["ROUTE_DISCOVERED"] == 1
    assert one["lifecycle_gate_counts"]["ROUTE_OWNERSHIP_PROVEN"] == 1
    assert one["lifecycle_gate_counts"]["ROUTE_TECHNICALLY_REACHABLE"] == 1
    assert one["terminal_state_counts"]["ROUTE_READY_FOR_OWNER_PROMOTION"] == 1
    with pytest.raises(RouteCoverageError, match="duplicate_route_identity"):
        build_artifact(baseline={}, routes=[route, route])


def test_source_family_separation() -> None:
    route = inspect_seed({"ticker": "EXM", "issuer_id": "Công ty Cổ phần Example Issuer", "locator": "https://issuer.example/ir"}, fetcher=_fetcher)
    route["source_family"] = "not_a_governed_source"
    with pytest.raises(RouteCoverageError, match="unsupported_source_family"):
        validate_route(route)


def test_network_failure_is_retained_as_a_discovered_route() -> None:
    def failing(_: str):
        raise OSError("unresolvable")
    route = inspect_seed({"ticker": "EXM", "issuer_id": "Issuer", "locator": "https://issuer.example/ir"}, fetcher=failing)
    assert route["qualification_state"] == ROUTE_DISCOVERED
    assert route["provenance"]["fetch_failure"] == "OSError"
