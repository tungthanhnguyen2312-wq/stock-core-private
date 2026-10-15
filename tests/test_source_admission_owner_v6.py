"""V6 official-source admission owner: one implementation, historical root names."""
from __future__ import annotations

import os
import pickle
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import official_source_registry as root
import stocklookup_core.evidence.official_source_registry as owner

ROOT = Path(__file__).resolve().parents[1]
SEALED_IMPORTS = {
    "stocklookup_core/evidence/hnx_disclosure_feed_parser.py":
        "from official_source_registry import canonical_host, evidence_document_types, source_index",
    "stocklookup_core/evidence/hnx_financial_filing_scaleout.py":
        "from official_source_registry import ADMITTED, admit, load_registry",
    "stocklookup_core/evidence/official_authority_candidates.py":
        "import official_source_registry as sources",
    "stocklookup_core/evidence/official_listing_page_parser.py":
        "from official_source_registry import canonical_host, evidence_document_types, source_index",
    "official_financial_pdf_page_evidence.py":
        "from official_source_registry import load_registry",
}
RETARGETED = (
    "stocklookup_core/evidence/official_document_acquisition.py",
    "stocklookup_core/evidence/official_document_discovery.py",
    "stocklookup_core/evidence/official_document_qualification.py",
    "stocklookup_core/evidence/official_document_store.py",
    "stocklookup_core/financial/multi_period_financial_panel.py",
)


def _registry(source_overrides=None, approval=None):
    source = {
        "source_id": "example",
        "activation": "approved",
        "allowed_hosts": ["issuer.example"],
        "document_types": ["annual_report"],
        "min_request_interval_seconds": 10,
        "host_document_types": {"issuer.example": ["annual_report"]},
    }
    if source_overrides:
        source.update(source_overrides)
    state = {
        "state": "APPROVED",
        "approved_at": "2020-01-01T00:00:00Z",
        "approved_at_provenance": "owner clock UTC",
    }
    if approval:
        state.update(approval)
    return {
        "schema_version": owner.VERSION,
        "sources": [source],
        "approval_state": state,
        "global_policy": {
            "connect_timeout_seconds": 5,
            "read_timeout_seconds": 20,
            "max_attempts": 2,
            "max_response_bytes": 1000,
            "user_agent": "test",
        },
    }


def test_default_path_ignores_working_directory_and_explicit_root_is_not_config():
    expected = ROOT / "config" / "official_source_registry.json"
    assert root.registry_path() == expected
    assert owner.registry_path() == expected
    assert expected.is_file()
    explicit = root.registry_path(root=Path(r"C:\temp\custom-root"))
    assert explicit == Path(r"C:\temp\custom-root") / "official_source_registry.json"
    assert "config" not in explicit.parts[-2:]
    script = (
        "import os,sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "os.chdir(r'C:\\Users\\tungt')\n"
        "from pathlib import Path\n"
        "import official_source_registry as root\n"
        "import stocklookup_core.evidence.official_source_registry as owner\n"
        f"assert root.registry_path() == Path({str(expected)!r})\n"
        "assert owner.registry_path() == root.registry_path()\n"
        "assert root.admit is owner.admit\n"
    )
    subprocess.run([sys.executable, "-c", script], check=True, cwd=r"C:\Users\tungt")


def test_import_order_object_identity_pickle_and_module_rebind():
    assert root.admit is owner.admit
    assert root.RegistryError is owner.RegistryError
    assert root.load_registry is owner.load_registry
    assert root.admit.__module__ == "official_source_registry"
    assert root.RegistryError.__module__ == "official_source_registry"
    restored = pickle.loads(pickle.dumps(root.RegistryError("missing")))
    assert type(restored) is root.RegistryError
    assert str(restored) == "missing"
    # Rebinding one module attribute does not fork the implementation object.
    original = root.admit
    root.admit = owner.admit
    assert owner.admit is original
    root.admit = original


def test_refusal_order_and_verified_admission_are_unchanged():
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    url = "https://issuer.example/report.pdf"
    cases = [
        (_registry(), "missing", url, "annual_report", None, "unknown_source_id"),
        (_registry(source_overrides={"activation": "declared"}), "example", "not a url", "nope", None, "source_declared_but_not_owner_approved"),
        (_registry(), "example", "ftp://issuer.example/x", "annual_report", None, "url_unparseable_or_unsupported_scheme"),
        (_registry(), "example", "https://evil-issuer.example/x", "annual_report", None, "host_not_on_source_allowlist"),
        (_registry(), "example", url, "secret_filing", None, "document_type_not_declared_for_source"),
        (_registry(), "example", url, "index_page", None, "document_type_not_declared_for_source"),
        (_registry(source_overrides={"host_document_types": {"issuer.example": ["other"]}}), "example", url, "annual_report", None, "document_type_not_allowed_for_host"),
        (_registry(), "example", url, "annual_report", 1, "minimum_request_interval_not_elapsed"),
        (_registry(approval={"approved_at": "2099-01-01T00:00:00Z"}), "example", url, "annual_report", 30, "approval_instant_not_verifiable"),
        (_registry(approval={"approved_at_provenance": ""}), "example", url, "annual_report", 30, "approval_instant_not_verifiable"),
    ]
    # host-restricted type must be declared first; the previous host case uses an undeclared type.
    for registry, source_id, target, document_type, elapsed, reason in cases:
        decision = root.admit(source_id, target, document_type, registry=registry,
                              seconds_since_last_request=elapsed, now=now)
        assert decision["decision"] == "refused"
        assert decision["reason"] == reason
        assert owner.admit(source_id, target, document_type, registry=registry,
                           seconds_since_last_request=elapsed, now=now) == decision
    admitted = root.admit("example", url, "annual_report", registry=_registry(),
                          seconds_since_last_request=30, now=now)
    assert admitted["decision"] == "admitted"
    assert admitted["reason"] == "admitted_by_registry"
    assert admitted["policy"]["min_request_interval_seconds"] == 10.0
    loaded = root.load_registry()
    assert loaded["schema_version"] == "1.0.0"
    assert root.registry_summary(loaded)["source_count"] == len(loaded["sources"])


def test_root_attribute_patches_redirect_path_and_load_registry(tmp_path):
    missing = tmp_path / "official_source_registry.json"
    original_path = root.registry_path
    root.registry_path = lambda root=None: missing
    try:
        try:
            owner.load_registry()
        except root.RegistryError as exc:
            assert str(missing) in str(exc)
        else:
            raise AssertionError("root registry_path patch was not followed")
    finally:
        root.registry_path = original_path
    calls = []

    def fake(path=None):
        calls.append(path)
        return _registry()

    original_load = root.load_registry
    root.load_registry = fake
    try:
        decision = root.admit("example", "https://issuer.example/report.pdf", "annual_report",
                              seconds_since_last_request=30,
                              now=datetime(2024, 1, 1, tzinfo=timezone.utc))
    finally:
        root.load_registry = original_load
    assert calls == [None]
    assert decision["decision"] == "admitted"


def test_sealed_root_importers_remain_and_live_consumers_use_the_owner():
    for relative, snippet in SEALED_IMPORTS.items():
        assert snippet in (ROOT / relative).read_text(encoding="utf-8")
    for relative in RETARGETED:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "stocklookup_core.evidence.official_source_registry" in text
        assert "\nimport official_source_registry" not in text
        assert "\nfrom official_source_registry import" not in text
