"""Isolated Bulk Acquisition Framework V1 - shared contract vocabulary.

Domain-agnostic acquisition/retention contract: the outcome vocabulary, the
acquisition-specification shape, the raw-document-record schema (see
docs/acquisition_landing_framework.md, "Manifest schema"), and the
qualification-state boundary marker. No I/O anywhere in this module.

Acquisition (this framework) and qualification (semantic/financial-fact
authority) are deliberately separate concerns: retaining raw bytes never
promotes them to evidence, observation, financial fact, feature, or
provider authority. See docs/acquisition_landing_framework.md for the full
boundary statement.
"""

from __future__ import annotations

import dataclasses
import enum
import uuid
from datetime import datetime, timezone

FRAMEWORK_VERSION = "1.0.0"
MANIFEST_SCHEMA_VERSION = "1.0.0"


class AcquisitionOutcome(str, enum.Enum):
    ACQUIRED = "ACQUIRED"
    ALREADY_PRESENT_IDENTICAL = "ALREADY_PRESENT_IDENTICAL"
    QUARANTINED = "QUARANTINED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    UNSUPPORTED = "UNSUPPORTED"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"


SUCCESS_OUTCOMES = (AcquisitionOutcome.ACQUIRED, AcquisitionOutcome.ALREADY_PRESENT_IDENTICAL)
RETRYABLE_OUTCOMES = (AcquisitionOutcome.FAILED_RETRYABLE,)
PERMANENT_FAILURE_OUTCOMES = (
    AcquisitionOutcome.FAILED_PERMANENT,
    AcquisitionOutcome.UNSUPPORTED,
    AcquisitionOutcome.BLOCKED_BY_POLICY,
)
NON_SUCCESS_OUTCOMES = (
    AcquisitionOutcome.QUARANTINED,
    *RETRYABLE_OUTCOMES,
    *PERMANENT_FAILURE_OUTCOMES,
)

# The only qualification-state value this framework may ever assign. Raw
# acquisition never qualifies its own output; a separate, later milestone
# owns promotion out of "unknown".
QUALIFICATION_STATE_UNKNOWN = "unknown"


class AcquisitionContractError(Exception):
    """Base error for acquisition-landing contract violations."""


class HashConflictError(AcquisitionContractError):
    """An on-disk blob's content no longer matches its own content-address."""


class ProtectedRootWriteError(AcquisitionContractError):
    """A write target resolved outside the allowed landing root, or inside a protected root."""


class IncompleteObservationError(AcquisitionContractError):
    """A caller tried to build a record with neither retained bytes nor a failure reason."""


def new_run_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


@dataclasses.dataclass(frozen=True)
class FetchError:
    """A source adapter's explanation for why bytes were not obtained.

    category must be one of: "retryable", "permanent", "unsupported",
    "blocked_by_policy" - the only four ways a non-quarantine failure may
    be classified. detail is a short, non-secret diagnostic string.
    """

    category: str
    detail: str

    _VALID_CATEGORIES = ("retryable", "permanent", "unsupported", "blocked_by_policy")

    def __post_init__(self) -> None:
        if self.category not in self._VALID_CATEGORIES:
            raise AcquisitionContractError(
                f"invalid FetchError category {self.category!r}; must be one of {self._VALID_CATEGORIES}"
            )

    def outcome(self) -> AcquisitionOutcome:
        return {
            "retryable": AcquisitionOutcome.FAILED_RETRYABLE,
            "permanent": AcquisitionOutcome.FAILED_PERMANENT,
            "unsupported": AcquisitionOutcome.UNSUPPORTED,
            "blocked_by_policy": AcquisitionOutcome.BLOCKED_BY_POLICY,
        }[self.category]


@dataclasses.dataclass(frozen=True)
class AcquisitionSpec:
    """What to acquire: a plain, hashable description of one desired document.

    No network or domain-specific logic lives here - this is pure
    description, produced by a source adapter (e.g.
    financial_filings_replay_adapter.py) and consumed by the retention
    layer.
    """

    domain: str
    source_locator: str
    source_authority_class: str
    issuer_identity: str | None = None
    document_type: str | None = None
    acquisition_method: str = "unspecified"
    acquisition_method_version: str = "1"

    def logical_identity_basis(self) -> str:
        return f"{self.domain}\n{self.source_locator}"


@dataclasses.dataclass(frozen=True)
class RawDocumentRecord:
    """The required raw-document contract (retained or attempted-and-failed).

    Every field this project's acquisition doctrine requires is present
    even when its value is genuinely unknown (None) - never inferred, never
    fabricated. See docs/acquisition_landing_framework.md, "Manifest
    schema".
    """

    run_id: str
    domain: str
    source_locator: str
    source_authority_class: str
    issuer_identity: str | None
    document_type: str | None
    observed_at: str
    source_published_at: str | None
    http_status: int | None
    original_filename: str | None
    content_type: str | None
    byte_size: int | None
    sha256: str | None
    storage_locator: str | None
    acquisition_method: str
    acquisition_method_version: str
    supersedes_sha256: str | None
    outcome: AcquisitionOutcome
    outcome_reason: str | None
    qualification_state: str = QUALIFICATION_STATE_UNKNOWN
    temporal_retention: dict | None = None

    def to_dict(self) -> dict:
        payload = dataclasses.asdict(self)
        payload["outcome"] = self.outcome.value
        return payload


def build_record(
    *,
    run_id: str,
    spec: AcquisitionSpec,
    observed_at: str,
    outcome: AcquisitionOutcome,
    outcome_reason: str | None = None,
    source_published_at: str | None = None,
    http_status: int | None = None,
    original_filename: str | None = None,
    content_type: str | None = None,
    byte_size: int | None = None,
    sha256: str | None = None,
    storage_locator: str | None = None,
    supersedes_sha256: str | None = None,
    temporal_retention: dict | None = None,
) -> RawDocumentRecord:
    """Single construction path for RawDocumentRecord so every caller supplies
    the same required context; refuses to build a silently-empty success."""
    if outcome in SUCCESS_OUTCOMES and sha256 is None:
        raise IncompleteObservationError(
            f"outcome {outcome.value} requires a sha256; a success record may never be empty"
        )
    if outcome not in SUCCESS_OUTCOMES and outcome_reason is None:
        raise IncompleteObservationError(f"outcome {outcome.value} requires an outcome_reason")

    return RawDocumentRecord(
        run_id=run_id,
        domain=spec.domain,
        source_locator=spec.source_locator,
        source_authority_class=spec.source_authority_class,
        issuer_identity=spec.issuer_identity,
        document_type=spec.document_type,
        observed_at=observed_at,
        source_published_at=source_published_at,
        http_status=http_status,
        original_filename=original_filename,
        content_type=content_type,
        byte_size=byte_size,
        sha256=sha256,
        storage_locator=storage_locator,
        acquisition_method=spec.acquisition_method,
        acquisition_method_version=spec.acquisition_method_version,
        supersedes_sha256=supersedes_sha256,
        outcome=outcome,
        outcome_reason=outcome_reason,
        qualification_state=QUALIFICATION_STATE_UNKNOWN,
        temporal_retention=temporal_retention,
    )
