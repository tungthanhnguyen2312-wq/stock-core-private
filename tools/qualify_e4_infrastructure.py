"""Offline E4 source identities and execution parity; never writes retained state.

V1 labels and LF normalization reproduce the standing feedback digest. V2 binds
that complete source set plus the candidate foundations, migrated consumers and
this qualifier, under a separate contract. This is no production reuse adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

V1_SOURCES = (
    ("prospective_decision_outcome_feedback", "prospective_decision_outcome_feedback.py"),
    ("integrated_decision_prospective_feedback", "integrated_decision_prospective_feedback.py"),
    ("prospective_decision_retention", "prospective_decision_retention.py"),
    ("prospective_decision_outcome_measurement", "prospective_decision_outcome_measurement.py"),
    ("prospective_feedback_streaming", "prospective_feedback_streaming.py"),
    ("bounded_artifact_stream", "bounded_artifact_stream.py"),
    ("session_bar_integrity", "session_bar_integrity.py"),
    ("fundamental_signal_consumption_contract", "stocklookup_core/financial/fundamental_signal_consumption_contract.py"),
    ("governed_session_chain", "governed_session_chain.py"),
    ("prospective_pit_capture_retention", "prospective_pit_capture_retention.py"),
    ("daily_session_level2_package", "daily_session_level2_package.py"),
)
V2_SOURCES = (
    "stocklookup_core/evidence/session_paths.py",
    "stocklookup_core/evidence/bounded_json.py",
    "stocklookup_core/evidence/artifact_stream.py",
    "stocklookup_core/decision/daily_integrated_decision_brief.py",
    "stocklookup_core/decision/integrated_investment_decision_product.py",
    "stocklookup_core/research/thesis_evidence_production.py",
    "stocklookup_core/__init__.py",
    "stocklookup_core/evidence/__init__.py",
    "stocklookup_core/decision/__init__.py",
    "stocklookup_core/research/__init__.py",
    "tools/qualify_e4_infrastructure.py",
)


def source_identity(root: Path, *, version: str) -> dict:
    """Read exact source inputs; missing sources raise, with no historical fallback."""
    if version not in {"v1", "v2"}:
        raise ValueError("E4_SOURCE_VERSION_UNSUPPORTED")
    digest = hashlib.sha256()
    if version == "v2":
        digest.update(b"e4_infrastructure_source/v2\0")
    sources = list(V1_SOURCES)
    if version == "v2":
        sources.extend((path, path) for path in V2_SOURCES)
    inventory = {}
    for label, relative in sources:
        content = (root / relative).read_bytes().replace(b"\r\n", b"\n")
        sha = hashlib.sha256(content)
        digest.update(label.encode() + b"\0" + sha.digest())
        inventory[label] = {"path": relative, "source_sha256_lf": sha.hexdigest()}
    return {"source_version": version, "code_digest": digest.hexdigest(),
            "contract_version": "feedback_source/v1" if version == "v1" else "e4_infrastructure_source/v2",
            "sources": inventory}


def candidate_reuse_eligible(retained: dict, candidate: dict, *, input_digest: str) -> bool:
    """Only qualified V2 candidate metadata can match; legacy/unversioned fails closed.

    Content integrity is a separate prerequisite owned by the artifact verifier.
    This predicate grants no production activation or historical V1 adoption.
    """
    return (retained.get("source_version") == candidate.get("source_version") == "v2"
            and retained.get("contract_version") == candidate.get("contract_version") == "e4_infrastructure_source/v2"
            and isinstance(candidate.get("code_digest"), str)
            and len(candidate["code_digest"]) == 64
            and all(c in "0123456789abcdef" for c in candidate["code_digest"])
            and retained.get("code_digest") == candidate["code_digest"]
            and isinstance(input_digest, str) and bool(input_digest)
            and retained.get("input_digest") == input_digest)


def qualify(root: Path) -> dict:
    """Execute frozen V1 and candidate on the same synthetic values; no file outputs."""
    import daily_session_level2_package as legacy_paths
    import prospective_decision_retention as legacy_json
    import prospective_feedback_streaming as feedback
    from stocklookup_core.evidence import bounded_json, session_paths

    # Imports above intentionally resolve this checkout. Reject a caller supplying
    # a foreign tree rather than comparing source from one tree to code from another.
    if root.resolve() != ROOT:
        raise ValueError("E4_EXECUTION_SOURCE_ROOT_MISMATCH")
    v1 = source_identity(root, version="v1")
    if v1["code_digest"] != feedback.code_digest():
        raise ValueError("E4_V1_DIGEST_CONSTRUCTION_MISMATCH")
    v2 = source_identity(root, version="v2")
    paths = legacy_paths.session_artifact_paths(Path("synthetic/relative"), "2026-10-08")
    directory = paths["official_event_context"].parent.name
    candidate_paths = session_paths.session_artifact_paths(Path("synthetic/relative"), "2026-10-08", official_event_context_dir=directory)
    if paths != candidate_paths:
        raise ValueError("E4_PATH_PARITY_FAILED")
    value = {"records": {"VNM": {"name": "Tiếng Việt", "value": -0.0}}, "session": "2026-10-08"}
    outputs = []
    for pretty in (False, True):
        before = b"".join(legacy_json._json_bytes(value, pretty=pretty))
        after = b"".join(bounded_json.json_bytes(value, pretty=pretty))
        if before != after:
            raise ValueError("E4_BYTE_PARITY_FAILED")
        outputs.append({"pretty": pretty, "bytes": len(after), "sha256": hashlib.sha256(after).hexdigest(), "byte_parity": True})
    return {"contract_version": "e4_infrastructure_qualification/v2", "v1": v1, "v2_candidate": v2,
            "paths": {key: str(path) for key, path in candidate_paths.items()}, "outputs": outputs,
            "v1_reuse_eligible_for_v2": candidate_reuse_eligible(v1, v2, input_digest="synthetic"),
            "production_v2_activation": "NOT_AUTHORIZED", "authority_effect": "NONE"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(qualify(ROOT), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
