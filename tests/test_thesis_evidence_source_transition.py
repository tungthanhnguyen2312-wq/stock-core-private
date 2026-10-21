"""Closed historical transition for the one approved Thesis production source."""
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from tools import qualify_e4_infrastructure as e4
from tools.verify_retention_reader_transition import (
    THESIS_ARCHIVE, THESIS_MANIFEST, THESIS_SOURCE, VALUATION_MANIFEST, VALUATION_SOURCES,
    active_thesis_evidence_identity, historical_bytes, legacy_source_identity,
)

ROOT = Path(__file__).resolve().parents[1]
PRIOR = "10aea634a50e83d5e8db4951155c5a7b6f753e3f091305bf7bee1ecadc463367"
ACTIVE = "9f384915d23661497e9132091a2aaac0030e5d54bc5060caeda89094b33901c7"
HISTORICAL_V2 = "07c2a363df0e91a1dee230f0316a081249b247f7aa74bd67e04e45b1d1886567"
ACTIVE_V2 = "f9477a9193ea4444187819a9aa8200d59a9c94e2bfc418321423c7dee3b34d2c"
MIXED_V2 = "c705b386c927a49adaf97be0a711cda5b27b2432cae2aaaa098a087a58b88698"
HISTORICAL_V1 = "fa79baadcca197493b9ca70067fbd153f5e8bb7f50dfb6dbc6da53f253483d46"
EMPTY = hashlib.sha256(b"").hexdigest()


def _lf(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def _copy_file(root: Path, relative: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / relative, target)


def _copy_boundary(tmp_path: Path) -> None:
    for relative in (THESIS_SOURCE, THESIS_ARCHIVE, THESIS_MANIFEST, "tests/fixtures/e2e3_frozen_sources.json"):
        _copy_file(tmp_path, relative)


def _copy_domain(tmp_path: Path) -> None:
    storage = json.loads((ROOT / "tests/fixtures/storage_portability_source_transition_v1.json").read_bytes())
    relatives = [path for _, path in e4.V1_SOURCES]
    relatives.extend(e4.V2_SOURCES)
    relatives.extend([
        THESIS_MANIFEST, THESIS_ARCHIVE, VALUATION_MANIFEST,
        "tests/fixtures/e2e3_frozen_sources.json",
        "tests/fixtures/retention_reader_transition_v2.json",
        "tests/fixtures/retention_reader_v1.py.txt",
        "tests/fixtures/storage_portability_source_transition_v1.json",
    ])
    relatives.extend(row["archive"] for row in storage["sources"].values())
    relatives.extend(
        row["archive"] for row in json.loads((ROOT / VALUATION_MANIFEST).read_bytes())["sources"].values()
    )
    for relative in relatives:
        _copy_file(tmp_path, relative)


def test_exact_thesis_transition_keeps_historical_v2_and_hashes_active_bytes():
    spec = json.loads((ROOT / THESIS_MANIFEST).read_bytes())
    valuation = json.loads((ROOT / VALUATION_MANIFEST).read_bytes())
    assert spec["source_path"] == THESIS_SOURCE
    assert spec["base_commit"] == "de90c6b94c7bb2377bedd7e2a1c809498d22926a"
    assert spec["release_authority"] == "NOT_GRANTED"
    assert THESIS_SOURCE not in valuation["sources"]
    assert valuation["admitted_sources"] == list(VALUATION_SOURCES)
    archive = _lf(ROOT / THESIS_ARCHIVE)
    active = _lf(ROOT / THESIS_SOURCE)
    assert historical_bytes(ROOT, THESIS_SOURCE) == archive
    assert hashlib.sha256(archive).hexdigest() == PRIOR
    assert hashlib.sha256(active).hexdigest() == ACTIVE
    assert PRIOR != ACTIVE
    identity = active_thesis_evidence_identity(ROOT)
    assert identity["historical_sha256_lf"] == PRIOR
    assert identity["active_sha256_lf"] == ACTIVE
    assert identity["historical_e4_v2_digest"] == HISTORICAL_V2 == legacy_source_identity(ROOT, version="v2")["code_digest"]
    assert identity["active_e4_v2_digest"] == ACTIVE_V2 == e4.source_identity(ROOT, version="v2")["code_digest"]
    assert identity["active_e4_v2_digest"] not in {HISTORICAL_V2, MIXED_V2}
    assert identity["historical_receipt_adoption"] is False
    assert identity["release_authority"] == "NOT_GRANTED"
    assert legacy_source_identity(ROOT, version="v1")["code_digest"] == HISTORICAL_V1
    execution = e4.source_identity(ROOT, version="v2")
    historical_receipt = {
        "source_version": "v2", "contract_version": "e4_infrastructure_source/v2",
        "code_digest": HISTORICAL_V2, "input_digest": "historical-receipt",
    }
    mixed_receipt = {**historical_receipt, "code_digest": MIXED_V2}
    assert not e4.candidate_reuse_eligible(historical_receipt, execution, input_digest="historical-receipt")
    assert not e4.candidate_reuse_eligible(mixed_receipt, execution, input_digest="historical-receipt")
    current = {**execution, "input_digest": "current-execution"}
    assert e4.candidate_reuse_eligible(current, execution, input_digest="current-execution")


def test_changed_archive_byte_fails(tmp_path):
    _copy_boundary(tmp_path)
    archive = tmp_path / THESIS_ARCHIVE
    archive.write_bytes(archive.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="BINDING_INVALID"):
        historical_bytes(tmp_path, THESIS_SOURCE)


def test_changed_active_byte_fails(tmp_path):
    _copy_boundary(tmp_path)
    target = tmp_path / THESIS_SOURCE
    target.write_bytes(target.read_bytes() + b"\n# tamper\n")
    with pytest.raises(ValueError, match="BINDING_INVALID"):
        historical_bytes(tmp_path, THESIS_SOURCE)


def test_another_source_is_outside_the_allowlist(tmp_path):
    _copy_boundary(tmp_path)
    manifest = tmp_path / THESIS_MANIFEST
    spec = json.loads(manifest.read_bytes())
    spec["source_path"] = "runtime_paths.py"
    manifest.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="SCOPE_INVALID"):
        historical_bytes(tmp_path, THESIS_SOURCE)
    spec = json.loads((ROOT / THESIS_MANIFEST).read_bytes())
    spec["extra_source"] = "runtime_paths.py"
    manifest.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="SCOPE_INVALID"):
        historical_bytes(tmp_path, THESIS_SOURCE)


def test_historical_domain_digest_mismatch_fails(tmp_path):
    _copy_domain(tmp_path)
    manifest = tmp_path / THESIS_MANIFEST
    spec = json.loads(manifest.read_bytes())
    spec["historical_e4_v2_digest"] = "0" * 64
    manifest.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="HISTORICAL_DIGEST_MISMATCH"):
        active_thesis_evidence_identity(tmp_path)


def test_active_domain_digest_mismatch_fails(tmp_path):
    _copy_domain(tmp_path)
    manifest = tmp_path / THESIS_MANIFEST
    spec = json.loads(manifest.read_bytes())
    spec["active_e4_v2_digest"] = "0" * 64
    manifest.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="ACTIVE_DIGEST_MISMATCH"):
        active_thesis_evidence_identity(tmp_path)


def test_t0_does_not_read_post_enrichment(tmp_path):
    import stocklookup_core.research.thesis_evidence_production as engine
    from test_thesis_evidence_stage2 import fixture, records
    from test_thesis_technical_v2_lineage import _write_batch
    args, _row, context, _bound, _path, _flow = fixture(tmp_path)
    _write_batch(tmp_path, {"VNM": context})
    current = engine.build(**args, stage="current")
    current_manifest = json.loads((tmp_path / current["path"]).read_bytes())
    assert current_manifest["inputs"]["sources"]["technical"]["post_t0_not_admitted_to_t0"] is True
    t0 = engine.build(**args, stage="t0", origin="SEAL_TIME")
    manifest = json.loads((tmp_path / t0["path"]).read_bytes())
    assert "technical" not in manifest["inputs"]["sources"]
    assert manifest["inputs"]["technical_context_digest"] == EMPTY
    view = records(t0, tmp_path)["VNM"]
    assert "technical" not in view["source_pointers"]
    assert view["post_items_in_t0"] == 0
