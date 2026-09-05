"""Canonical current Financial V2 input authority.

Financial evidence is periodic, not daily. This module is the ONE explicit, versioned,
deterministic pointer to the retained Financial V2 input chain (structured period-semantics
facts, the fundamental feature store, and entity-classification diagnostics) that
``canonical_daily_financial_v2_materialization.py`` reproduces for a decision session.

It deliberately never scans the filesystem for "the newest folder" -- the pinned directories
below are force-tracked retained evidence, present identically in every checkout (including a
fresh ``git worktree add``), and their expected artifact identities are pinned so silent
drift (evidence replaced without a deliberate authority advance) fails closed instead of
being reproduced quietly.

To advance this authority to a newer retained snapshot: add a new dated directory set and
new pinned identities, bump ``AUTHORITY_VERSION``, and update the constants below. Never
edit a resolved identity in place -- that would silently change which evidence a past
``financial_evidence_as_of_period`` claim was actually bound to.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "financial_v2_current_input_authority/v1"
#: Advanced 2026-09-05 (FINANCIAL_TEMPORAL_SEMANTIC_NORMALIZATION_AND_ANALYTICAL_PANEL_V1):
#: semantics-only advance. The 20260831 directory is preserved, untouched, as historical
#: evidence -- see that milestone's own docstring: "Never edit a resolved identity in place."
#: Only `_SEMANTICS_DIRNAME`/`_EXPECTED_SEMANTICS_IDENTITY` moved; the feature-store and
#: classification-diagnostics pins are unaffected by this milestone and stay exactly as they
#: were, still resolved against their own original 20260831/20260901 directories.
AUTHORITY_VERSION = "2026-09-05.1"

# Pinned retained evidence directories under <root>/operations-review/. Each is force-tracked
# in git (unlike ordinary gitignored operations-review/ output) specifically so this authority
# resolves identically everywhere.
_SEMANTICS_DIRNAME = "market-wide-structured-financial-period-semantics-v1-20260905"
_FEATURE_STORE_DIRNAME = "market-wide-fundamental-feature-store-v1-20260831"
_CLASSIFICATION_DIRNAME = "market-wide-financial-entity-classification-scaleout-v1-20260901"

# Pinned expected artifact identities. A mismatch means the retained evidence changed without
# this authority being deliberately advanced to a new AUTHORITY_VERSION.
#
# `_EXPECTED_SEMANTICS_IDENTITY` (verified 2026-09-05 against the tracked worktree): rebuilt
# from the same retained data_bctc raw evidence as the prior 20260831 snapshot, over the
# corpus's natural growth since then (1,492 tickers / 261,360 facts vs. 1,492 / 195,552), plus
# two additive, evidence-only changes this milestone made: (1) `canonical_financial_facts.py`
# now normalizes `observed_at` into a timezone-aware ISO-8601 string instead of a naive
# Asia/Ho_Chi_Minh string that a strict bitemporal parser silently rejected -- no new source
# timestamp is created; (2) this projection now carries explicit
# `period_duration_root_cause`/`timestamp_root_cause` fields, plus a `reported_cumulative_state`
# passthrough (previously computed internally and never exposed) that
# `market_wide_financial_analysis_v2_scaleout.build_qualified_flow_artifact`'s field adapter
# needs to activate the TTM/de-cumulation bridge safely. No period-semantic STATE, no
# statement-scope/currency/scale resolution, and no financial value changed.
_EXPECTED_SEMANTICS_IDENTITY = (
    "market_wide_structured_financial_period_semantics/v1:"
    "ca7c2a28a9dd9e00774dcd10c2b9aa993a0fc4664e551236408287c830ad4457"
)
_EXPECTED_FEATURE_STORE_IDENTITY = (
    "market_wide_fundamental_feature_store/v1:"
    "3a2c6273cf23015140e87229d3f4c5875db75d52ddb8115a564227db1e2a969e"
)
_EXPECTED_CLASSIFICATION_DIAGNOSTICS_IDENTITY = (
    "9306fa0ae7b04f04599aad41346babe6b82aee57ba2c444a89927a77863c469e"
)


class FinancialV2InputAuthorityError(ValueError):
    pass


@dataclass(frozen=True)
class FinancialV2InputAuthority:
    authority_version: str
    semantics_dir: Path
    feature_store_dir: Path
    classification_dir: Path
    semantics_artifact_path: Path
    semantics_facts_path: Path
    feature_store_artifact_path: Path
    feature_store_records_path: Path
    classification_diagnostics_path: Path
    industry_snapshot_path: Path
    expected_semantics_identity: str
    expected_feature_store_identity: str
    expected_classification_diagnostics_identity: str

    def to_manifest(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "authority_version": self.authority_version,
            "semantics_dir": self.semantics_dir.name,
            "feature_store_dir": self.feature_store_dir.name,
            "classification_dir": self.classification_dir.name,
            "expected_semantics_identity": self.expected_semantics_identity,
            "expected_feature_store_identity": self.expected_feature_store_identity,
            "expected_classification_diagnostics_identity": self.expected_classification_diagnostics_identity,
            "resolver_policy": "PINNED_VERSIONED_DIRECTORIES_NEVER_FILESYSTEM_LATEST_SCAN",
        }


def resolve(root: Path) -> FinancialV2InputAuthority:
    """Resolve the canonical current Financial V2 input authority under ``root``.

    Deterministic: always the same three pinned directories, never a directory-mtime or
    glob-newest scan. Raises ``FinancialV2InputAuthorityError`` if a required file is absent.
    The optional industry snapshot is not required here -- callers degrade to an entity-class
    peer cohort fallback when it is absent, exactly as
    ``current_research_valuation_context.attach_engine_fundamental_peers`` already does.
    """
    ops = Path(root) / "operations-review"
    semantics_dir = ops / _SEMANTICS_DIRNAME
    feature_store_dir = ops / _FEATURE_STORE_DIRNAME
    classification_dir = ops / _CLASSIFICATION_DIRNAME
    authority = FinancialV2InputAuthority(
        authority_version=AUTHORITY_VERSION,
        semantics_dir=semantics_dir,
        feature_store_dir=feature_store_dir,
        classification_dir=classification_dir,
        semantics_artifact_path=semantics_dir / "structured_financial_period_semantics_artifact.json",
        semantics_facts_path=semantics_dir / "structured_financial_period_semantics_facts.jsonl.gz",
        feature_store_artifact_path=feature_store_dir / "market_wide_fundamental_feature_store_artifact.json",
        feature_store_records_path=feature_store_dir / "market_wide_fundamental_feature_store_records.jsonl.gz",
        classification_diagnostics_path=classification_dir / "scaleout_classification_diagnostics.json",
        industry_snapshot_path=classification_dir / "exchange_industry_classification_snapshot.json",
        expected_semantics_identity=_EXPECTED_SEMANTICS_IDENTITY,
        expected_feature_store_identity=_EXPECTED_FEATURE_STORE_IDENTITY,
        expected_classification_diagnostics_identity=_EXPECTED_CLASSIFICATION_DIAGNOSTICS_IDENTITY,
    )
    required = (
        authority.semantics_artifact_path, authority.semantics_facts_path,
        authority.feature_store_artifact_path, authority.feature_store_records_path,
        authority.classification_diagnostics_path,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FinancialV2InputAuthorityError(
            "FINANCIAL_V2_INPUT_AUTHORITY_EVIDENCE_MISSING:" + ",".join(missing)
        )
    return authority


def verify_identity(*, label: str, observed: str | None, expected: str) -> None:
    """Fail closed when retained evidence content drifts from the pinned expectation."""
    if observed != expected:
        raise FinancialV2InputAuthorityError(
            f"FINANCIAL_V2_INPUT_AUTHORITY_IDENTITY_DRIFT:{label}:expected={expected}:observed={observed}"
        )
