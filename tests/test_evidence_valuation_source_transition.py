"""Closed historical transition for the two approved orchestration sources."""
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from tools import qualify_e4_infrastructure as e4
from tools.verify_retention_reader_transition import (
    VALUATION_MANIFEST, VALUATION_SOURCES, active_valuation_orchestration_identity, historical_bytes,
    legacy_source_identity,
)

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    "canonical_daily_operation.py": "a4151d55564105df60b29e49036e35ae98287366daba1dc5f96444da3b31b730",
    "canonical_post_close_pipeline.py": "db6e78370b57739888211d3c4381206daed7a542ac7123416bb0870c2427236a",
}
ACTIVE = {
    "canonical_daily_operation.py": "487a0b91b4ef8699bdacdd46111a12fb40b4731994acf8e83b80540631daf829",
    "canonical_post_close_pipeline.py": "8b7df5b9129c2f49e3c9a87eb27b62409d2b199584b60feab0e381091b194f0f",
}
V1_DIGEST = "fa79baadcca197493b9ca70067fbd153f5e8bb7f50dfb6dbc6da53f253483d46"


def _lf(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def test_two_file_transition_checks_archive_and_active_bytes():
    spec = json.loads((ROOT / VALUATION_MANIFEST).read_bytes())
    assert list(spec["sources"]) == list(VALUATION_SOURCES)
    assert spec["admitted_sources"] == list(VALUATION_SOURCES)
    assert spec["base_commit"] == "de90c6b94c7bb2377bedd7e2a1c809498d22926a"
    assert spec["release_authority"] == "NOT_GRANTED"
    frozen = json.loads((ROOT / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    for relative in VALUATION_SOURCES:
        archive = _lf(ROOT / spec["sources"][relative]["archive"])
        active = _lf(ROOT / relative)
        historical = historical_bytes(ROOT, relative)
        assert historical == archive
        assert hashlib.sha256(archive).hexdigest() == PINS[relative] == frozen[relative]
        assert hashlib.sha256(active).hexdigest() == ACTIVE[relative]
        assert hashlib.sha256(active).hexdigest() != hashlib.sha256(historical).hexdigest()
    identity = active_valuation_orchestration_identity(ROOT)
    historical_v1 = legacy_source_identity(ROOT, version="v1")["code_digest"]
    active_v1 = e4.source_identity(ROOT, version="v1")["code_digest"]
    assert identity["historical_receipt_adoption"] is False
    assert identity["release_authority"] == "NOT_GRANTED"
    assert historical_v1 == V1_DIGEST
    assert identity["execution_code_digest"] == active_v1
    assert identity["execution_code_digest"] != historical_v1
    assert identity["execution_source_version"] == "v1"
    for relative, row in identity["sources"].items():
        assert row["historical_sha256_lf"] == PINS[relative]
        assert row["active_sha256_lf"] == ACTIVE[relative]


def test_other_frozen_sources_stay_outside_this_transition():
    spec = json.loads((ROOT / VALUATION_MANIFEST).read_bytes())
    frozen = json.loads((ROOT / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    assert set(spec["sources"]).isdisjoint(set(frozen) - set(VALUATION_SOURCES))
    untouched = next(path for path in frozen if path not in VALUATION_SOURCES)
    assert hashlib.sha256(historical_bytes(ROOT, untouched)).hexdigest() == frozen[untouched]


def _copy_boundary(tmp_path: Path) -> None:
    spec = json.loads((ROOT / VALUATION_MANIFEST).read_bytes())
    paths = [VALUATION_MANIFEST, "tests/fixtures/e2e3_frozen_sources.json", *VALUATION_SOURCES]
    paths.extend(row["archive"] for row in spec["sources"].values())
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)


def test_tampered_active_source_fails_the_binding(tmp_path):
    _copy_boundary(tmp_path)
    target = tmp_path / VALUATION_SOURCES[0]
    target.write_bytes(target.read_bytes() + b"\n# tamper\n")
    with pytest.raises(ValueError, match="BINDING_INVALID"):
        historical_bytes(tmp_path, VALUATION_SOURCES[0])


def test_an_extra_source_is_outside_the_approved_scope(tmp_path):
    _copy_boundary(tmp_path)
    manifest = tmp_path / VALUATION_MANIFEST
    spec = json.loads(manifest.read_bytes())
    spec["sources"]["runtime_paths.py"] = spec["sources"][VALUATION_SOURCES[0]]
    spec["admitted_sources"].append("runtime_paths.py")
    manifest.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="SCOPE_INVALID"):
        historical_bytes(tmp_path, VALUATION_SOURCES[0])
