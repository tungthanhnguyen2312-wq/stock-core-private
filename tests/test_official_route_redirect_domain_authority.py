"""Focused redirect-domain authority regressions for prospective route review."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bounded_official_route_evidence_enrichment import (
    CROSS_DOMAIN_REDIRECT_REQUIRES_EVIDENCE,
    ENRICHMENT_EVIDENCE_DIR,
    NO_REDIRECT_SAME_HOST,
    OFFLINE_ENRICHED_EVIDENCE_CATALOG,
    OWNER_REVIEW_READY,
    ROUTE_AUTHORITY_EVIDENCE_REQUIRED,
    SAFE_SAME_AUTHORITY_REDIRECT,
    execute_bounded_enrichment,
    review_retained_bytes,
    validate_redirect_domain_authority,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "official_source_registry.json"


def test_exact_www_canonicalization_is_safe_only_with_retained_lineage() -> None:
    forward = validate_redirect_domain_authority(
        "https://www.example.com/a", "https://example.com/a", ["https://example.com/a"],
    )
    reverse = validate_redirect_domain_authority(
        "https://example.com/a", "https://www.example.com/a", ["https://www.example.com/a"],
    )
    assert forward["redirect_authority_verdict"] == SAFE_SAME_AUTHORITY_REDIRECT
    assert reverse["redirect_authority_verdict"] == SAFE_SAME_AUTHORITY_REDIRECT
    assert forward["requested_host"] == "www.example.com"
    assert forward["final_host"] == "example.com"


def test_same_host_without_redirect_is_deterministically_safe() -> None:
    result = validate_redirect_domain_authority("https://example.com/a", "https://example.com/b", [])
    assert result["redirect_authority_verdict"] == NO_REDIRECT_SAME_HOST
    assert result["safe_same_authority"] is True


def test_cross_domain_and_non_www_subdomains_require_separate_evidence() -> None:
    pairs = [
        ("https://www.example.com", "https://unrelated.com"),
        ("https://example.com", "https://attacker.example.net"),
        ("https://issuer.example.com", "https://other.example.com"),
        ("https://issuer.example.com", "https://example.com"),
    ]
    for requested, final in pairs:
        result = validate_redirect_domain_authority(requested, final, [final])
        assert result["redirect_authority_verdict"] == CROSS_DOMAIN_REDIRECT_REQUIRES_EVIDENCE
        assert result["safe_same_authority"] is False

    chained = validate_redirect_domain_authority(
        "https://www.example.com", "https://example.com",
        ["https://attacker.example.net", "https://example.com"],
    )
    assert chained["redirect_authority_verdict"] == CROSS_DOMAIN_REDIRECT_REQUIRES_EVIDENCE


def test_cross_domain_redirect_cannot_yield_owner_review_ready() -> None:
    entry = OFFLINE_ENRICHED_EVIDENCE_CATALOG["BID"][0]
    raw = (ROOT / entry["relative_path"]).read_bytes()
    record = review_retained_bytes(
        "BID", "https://www.bidv.com.vn/vn/quan-he-nha-dau-tu",
        "https://unrelated.example/vn/quan-he-nha-dau-tu", raw,
        hashlib.sha256(raw).hexdigest(), entry["relative_path"],
        ["https://unrelated.example/vn/quan-he-nha-dau-tu"],
    )
    assert record["prospective_owner_review_status"] == ROUTE_AUTHORITY_EVIDENCE_REQUIRED
    assert record["domain_binding_verdict"] == "INVALID"


def test_retained_bid_replay_preserves_hosts_and_becomes_ready_generically() -> None:
    artifact = execute_bounded_enrichment(live_network=False)
    bid = next(record for record in artifact["records"] if record["ticker"] == "BID")
    assert bid["requested_host"] == "www.bidv.com.vn"
    assert bid["final_host"] == "bidv.com.vn"
    assert bid["redirect_chain"] == [bid["final_url"]]
    assert bid["redirect_authority_verdict"] == SAFE_SAME_AUTHORITY_REDIRECT
    assert bid["prospective_owner_review_status"] == OWNER_REVIEW_READY


def test_registry_unchanged_and_replay_deterministic() -> None:
    before = hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest()
    first = execute_bounded_enrichment(live_network=False)
    second = execute_bounded_enrichment(live_network=False)
    assert first == second
    assert hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest() == before
