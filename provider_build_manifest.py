"""Provider build approval manifest, attestation and worker launch contract.

APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1 (pre-approval foundation). Standard-library only:
the Daily parent imports it, and the provider worker imports it from its bundled sources to attest
itself before any provider package is discovered. It must never import ``vnstock``/``vnai``/
``vn_stock_pipeline``.

What an approved build is
    A tracked, owner-controlled JSON manifest (``config/provider_build_manifest.json``, contract
    ``provider_build_approval_manifest/v1.2``, schema ``config/provider_build_manifest.schema.json``)
    binding: the provider interpreter (path, SHA-256, venv, base runtime, Python build), the exact
    installed distributions and every installed file, startup hooks, the dependency lock, the
    worker source bundle and protocol, the credential mechanism and vendor rate tier, the governor
    rate, the endpoint allow-list and telemetry disposition, filesystem roots, terms acceptance,
    the owner approval and the revocation epoch. The tracked policy pins the manifest's canonical
    SHA-256 and decision id. Nothing in this module can produce or modify an approval.

The launch sequence (``authorize_provider_launch``), every step fail-closed and none executing
provider code:
    1. policy pin present and equal to the manifest's canonical digest; decision ids agree;
    2. manifest schema + contract invariants; status ``APPROVED_PINNED_BUILD``; launch authorised;
       approval complete and unexpired; requested launch mode matches (``ORDINARY_DAILY`` needs
       qualification evidence); terms acceptance resolved;
    3. revocation registry: not revoked, epoch current;
    4. credential/tier/rate binding, against the observed credential availability;
    5. static runtime attestation of the configured interpreter: path, SHA-256, links/reparse
       points, ``pyvenv.cfg`` (system site off), base runtime files, startup hooks (``.pth``,
       ``sitecustomize``/``usercustomize``), installed distributions, every installed file,
       per-distribution RECORD manifests, dependency lock membership, worker sources;
    6. an ``-I -S -B`` probe of the (hash-verified) interpreter for the exact Python build;
    7. profile-isolated worker environment, fresh scratch root, copied + re-verified worker
       bundle, launch contract.
The worker then re-attests itself (``self_attest_worker``) before any discovery: launch contract,
flags, venv/prefix, interpreter hash, Python build, ``sys.path``, startup hooks, bundle sources,
manifest digest, environment names, profile redirection, credential/tier, working directory.

Nothing here grants source, market-data or any other authority: a runtime that attests is
operationally usable, nothing more (``authority_effect = NONE_OPERATIONAL_METADATA_ONLY``).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import provider_runtime_state as runtime_contract

ROOT = Path(__file__).resolve().parent

MANIFEST_CONTRACT_VERSION = "provider_build_approval_manifest/v1.2"
MANIFEST_PATH = ROOT / "config" / "provider_build_manifest.json"
SCHEMA_PATH = ROOT / "config" / "provider_build_manifest.schema.json"
REVOCATION_REGISTRY_PATH = ROOT / "config" / "provider_revocation_registry.json"
REVOCATION_REGISTRY_CONTRACT_VERSION = "provider_revocation_registry/v1"
DEPENDENCY_LOCK_PATH = ROOT / "config" / "provider_dependency_lock.json"
DEPENDENCY_LOCK_CONTRACT_VERSION = "provider_dependency_lock/v1"
INSTALLED_TREE_CONTRACT_VERSION = "provider_installed_tree_manifest/v1"
LAUNCH_CONTRACT_VERSION = "provider_worker_launch_contract/v1"
LAUNCH_CONTRACT_ENV = "STOCKLOOKUP_PROVIDER_LAUNCH_CONTRACT"
BUNDLED_MANIFEST_RELATIVE_PATH = "config/provider_build_manifest.json"
AUTHORITY_EFFECT = "NONE_OPERATIONAL_METADATA_ONLY"

# --- vocabulary --------------------------------------------------------------------------------
STATUS_DRAFT = "DRAFT"
STATUS_APPROVED = "APPROVED_PINNED_BUILD"
STATUS_SECURITY_REVIEW_BLOCKED = "SECURITY_REVIEW_BLOCKED"
STATUS_REJECTED = "REJECTED"
STATUS_REVOKED = "REVOKED"
MANIFEST_STATUSES = (STATUS_DRAFT, STATUS_APPROVED, STATUS_SECURITY_REVIEW_BLOCKED, STATUS_REJECTED, STATUS_REVOKED)

LAUNCH_MODE_GATE_B = "QUALIFICATION_GATE_B_CONTAINED_STARTUP"
LAUNCH_MODE_GATE_C = "QUALIFICATION_GATE_C_AUTH_PROBE"
LAUNCH_MODE_GATE_D = "QUALIFICATION_GATE_D_EXACT_SESSION"
LAUNCH_MODE_GATE_E = "QUALIFICATION_GATE_E_QUALITY_LICENSE"
LAUNCH_MODE_ORDINARY_DAILY = "ORDINARY_DAILY"
LAUNCH_MODES = (LAUNCH_MODE_GATE_B, LAUNCH_MODE_GATE_C, LAUNCH_MODE_GATE_D, LAUNCH_MODE_GATE_E,
                LAUNCH_MODE_ORDINARY_DAILY)
QUALIFICATION_LAUNCH_MODES = LAUNCH_MODES[:-1]

CREDENTIAL_NONE = "NONE"
CREDENTIAL_APPROVED_ENV_NAME = "APPROVED_ENV_NAME"
CREDENTIAL_APPROVED_STATE_FILE = "APPROVED_STATE_FILE"
CREDENTIAL_UNRESOLVED = "UNRESOLVED"
CREDENTIAL_MECHANISMS = (CREDENTIAL_NONE, CREDENTIAL_APPROVED_ENV_NAME, CREDENTIAL_APPROVED_STATE_FILE)
VENDOR_CREDENTIAL_NAME = "VNSTOCK_API_KEY"
# vnai derives its local tier from key PRESENCE: env VNSTOCK_API_KEY, else
# Path.home()/.vnstock/api_key.json (dossier evidence/worker-startup-trace.json, step 9).
VENDOR_CREDENTIAL_STATE_FILE = ".vnstock/api_key.json"

TIER_GUEST = "guest"
TIER_FREE = "free"
# Reviewed vendor tier table (dossier worker-startup-trace.json; vnai 2.5.0 static source, never
# imported). Review evidence, not vendor authority: a manifest may bind limits at or below these.
REVIEWED_VENDOR_TIER_LIMITS = {
    TIER_GUEST: {"min": 20, "hour": 1200, "day": 5000},
    TIER_FREE: {"min": 60, "hour": 3600, "day": 10000},
}
MAX_FRACTION_OF_TIER_MINUTE_LIMIT = 0.75
# Owner decision 2026-09-26: absolute governor ceiling, independent of the bound tier (the free
# tier's 75% share would be 45/min). Mirrors vnstock_rate_governor.OWNER_APPROVED_GOVERNOR_CEILING_RPM.
OWNER_APPROVED_GOVERNOR_CEILING_RPM = 20

TELEMETRY_DENY = "DENY"
TELEMETRY_ALLOW = "ALLOW_OWNER_APPROVED"
TELEMETRY_UNRESOLVED = "UNRESOLVED_OWNER_DECISION_REQUIRED"

TERMS_PREPROVISIONED = "OWNER_PREPROVISIONED_IN_PROVIDER_STATE_ROOT"
TERMS_UNRESOLVED = "UNRESOLVED_LAUNCH_BLOCKED"

REVOCATION_UNAPPROVED = "UNAPPROVED"
REVOCATION_ACTIVE = "ACTIVE"
REVOCATION_REVOKED = "REVOKED"

REDIRECTED_PROFILE_NAMES = ("USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP")
DENIED_SECRET_CLASSES = (
    "OWNER_PROFILE_FILES", "OWNER_VENDOR_STATE_DOT_VNSTOCK", "STOCK_LOOKUP_SECRETS_FILE",
    "DNSE_LIVESPEED_FINHAY_FHSC_CREDENTIALS", "VENDOR_ALIAS_KEYS_VNSTOCK_DNSE_FMP_BINANCE", "SSH_GIT_NETRC",
    "BROWSER_AND_OS_CREDENTIAL_STORES", "AI_AGENT_CREDENTIALS_CODEX_CLAUDE", "PRODUCTION_RUNTIME_AND_DBS",
    "PORTFOLIO_AND_PRIVATE_RESEARCH", "RETAINED_EVIDENCE_AND_REPOSITORIES",
)
REQUIRED_FORBIDDEN_PREFIXES = ("DNSE_", "LIVESPEED_", "FINHAY_", "FHSC_")
REQUIRED_FORBIDDEN_NAMES = ("VNSTOCK_DNSE_API_KEY", "VNSTOCK_FMP_API_KEY", "VNSTOCK_BINANCE_API_KEY",
                            "FMP_API_KEY", "FMP_TOKEN", "STOCK_LOOKUP_SECRETS_FILE")
PROVIDER_DISTRIBUTIONS = ("vnstock", "vnai")

# The KBS/VCI routes the reviewed vnstock 4.0.4 quote path actually requests (dossier evidence/
# endpoint-classification.json; vnstock/explorer/kbs/quote.py:260-262, vci/quote.py:260). Lineage
# and diagnostics record these; they are NOT an approved allow-list.
KBS_HISTORY_ROUTE = "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stocks/{symbol}/data_day"
KBS_INDEX_HISTORY_ROUTE = "https://kbbuddywts.kbsec.com.vn/iis-server/investment/index/{symbol}/data_day"
VCI_HISTORY_ROUTE = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
LINEAGE_ENDPOINT_MAP = {"KBS": KBS_HISTORY_ROUTE, "VCI": VCI_HISTORY_ROUTE}

# Worker source bundle of the production worker (dossier minimal-dependency-closure.json, plus the
# three boundary modules this milestone adds). Copied into each launch's scratch bundle and
# hash-verified by the parent and again by the worker.
WORKER_ENTRYPOINT = "vnstock_worker_process.py"
WORKER_ADAPTER_MODULE = "vn_stock_pipeline"
WORKER_SOURCE_FILES = (
    "vnstock_worker_process.py", "vnstock_worker_protocol.py", "vnstock_rate_governor.py",
    "provider_build_manifest.py", "provider_worker_containment.py", "provider_execution_guard.py",
    "provider_runtime_state.py", "vn_stock_pipeline.py", "market_data_lineage.py", "runtime_paths.py",
    "vn_time.py",
)
# Import-cache stubs the worker installs before vnstock is first imported (see
# vnstock_worker_process._install_startup_stubs); the manifest must name exactly these.
WORKER_STARTUP_STUBS = ({"module": "vnstock.core.utils.upgrade", "attributes": ["migrate_to_sponsor", "update_notice"]},)

# --- reason codes ------------------------------------------------------------------------------
R_MANIFEST_ABSENT = "PROVIDER_BUILD_MANIFEST_ABSENT"
R_MANIFEST_MALFORMED = "PROVIDER_BUILD_MANIFEST_MALFORMED"
R_MANIFEST_SCHEMA_INVALID = "PROVIDER_BUILD_MANIFEST_SCHEMA_INVALID"
R_MANIFEST_CONTRACT_INVALID = "PROVIDER_BUILD_MANIFEST_CONTRACT_INVALID"
R_NOT_APPROVED = "PROVIDER_BUILD_NOT_APPROVED"
R_LAUNCH_NOT_AUTHORIZED = "PROVIDER_BUILD_LAUNCH_NOT_AUTHORIZED"
R_APPROVAL_INCOMPLETE = "PROVIDER_BUILD_APPROVAL_INCOMPLETE"
R_APPROVAL_EXPIRED = "PROVIDER_BUILD_APPROVAL_EXPIRED"
R_APPROVAL_NOT_YET_VALID = "PROVIDER_BUILD_APPROVAL_NOT_YET_VALID"
R_POLICY_PIN_ABSENT = "PROVIDER_POLICY_MANIFEST_PIN_ABSENT"
R_POLICY_DIGEST_MISMATCH = "PROVIDER_POLICY_MANIFEST_DIGEST_MISMATCH"
R_POLICY_IDENTITY_MISMATCH = "PROVIDER_POLICY_MANIFEST_IDENTITY_MISMATCH"
R_REVOKED = "PROVIDER_BUILD_REVOKED"
R_EPOCH_STALE = "PROVIDER_BUILD_REVOCATION_EPOCH_STALE"
R_REGISTRY_INVALID = "PROVIDER_REVOCATION_REGISTRY_INVALID"
R_LAUNCH_MODE_MISMATCH = "PROVIDER_LAUNCH_MODE_MISMATCH"
R_DAILY_WITHOUT_QUALIFICATION = "PROVIDER_ORDINARY_DAILY_WITHOUT_QUALIFICATION_EVIDENCE"
R_TERMS_UNRESOLVED = "PROVIDER_TERMS_ACCEPTANCE_UNRESOLVED"
R_TERMS_NOT_PREPROVISIONED = "PROVIDER_TERMS_AGREEMENT_NOT_PREPROVISIONED"
R_CREDENTIAL_CONTRACT_INVALID = "PROVIDER_CREDENTIAL_CONTRACT_INVALID"
R_CREDENTIAL_REQUIRED_ABSENT = "PROVIDER_CREDENTIAL_REQUIRED_BUT_ABSENT"
R_CREDENTIAL_PLACEHOLDER = "PROVIDER_CREDENTIAL_PLACEHOLDER_REFUSED"
R_CREDENTIAL_NOT_APPROVED_PRESENT = "PROVIDER_CREDENTIAL_NOT_APPROVED_PRESENT"
R_TIER_MISMATCH = "PROVIDER_TIER_MISMATCH"
R_RATE_BINDING_INVALID = "PROVIDER_RATE_BINDING_INVALID"
R_GOVERNOR_EXCEEDS_APPROVED = "PROVIDER_GOVERNOR_RATE_EXCEEDS_APPROVED"
R_TELEMETRY_UNRESOLVED = "PROVIDER_TELEMETRY_DISPOSITION_UNRESOLVED"
R_ENDPOINT_CONTRACT_INVALID = "PROVIDER_ENDPOINT_CONTRACT_INVALID"
R_ENVIRONMENT_CONTRACT_INVALID = "PROVIDER_ENVIRONMENT_CONTRACT_INVALID"
R_FILESYSTEM_CONTRACT_INVALID = "PROVIDER_FILESYSTEM_CONTRACT_INVALID"
R_DEPENDENCY_LOCK_MISMATCH = "PROVIDER_DEPENDENCY_LOCK_MISMATCH"
R_WORKER_CONTRACT_INVALID = "PROVIDER_WORKER_CONTRACT_INVALID"
R_INTERPRETER_PATH_MISMATCH = "PROVIDER_ATTESTATION_INTERPRETER_PATH_MISMATCH"
R_EXECUTABLE_MISSING = "PROVIDER_ATTESTATION_EXECUTABLE_MISSING"
R_EXECUTABLE_HASH_MISMATCH = "PROVIDER_ATTESTATION_EXECUTABLE_HASH_MISMATCH"
R_REPARSE_POINT = "PROVIDER_ATTESTATION_REPARSE_POINT"
R_VENV_CONFIG_MISMATCH = "PROVIDER_ATTESTATION_VENV_CONFIG_MISMATCH"
R_SYSTEM_SITE_ENABLED = "PROVIDER_ATTESTATION_SYSTEM_SITE_ENABLED"
R_BASE_RUNTIME_MISMATCH = "PROVIDER_ATTESTATION_BASE_RUNTIME_MISMATCH"
R_STARTUP_HOOK_UNEXPECTED = "PROVIDER_ATTESTATION_STARTUP_HOOK_UNEXPECTED"
R_UNEXPECTED_DISTRIBUTION = "PROVIDER_ATTESTATION_UNEXPECTED_DISTRIBUTION"
R_MISSING_DISTRIBUTION = "PROVIDER_ATTESTATION_MISSING_DISTRIBUTION"
R_DISTRIBUTION_VERSION_MISMATCH = "PROVIDER_ATTESTATION_DISTRIBUTION_VERSION_MISMATCH"
R_PACKAGE_MANIFEST_MISMATCH = "PROVIDER_ATTESTATION_PACKAGE_INSTALLED_MANIFEST_MISMATCH"
R_TREE_MANIFEST_MISMATCH = "PROVIDER_ATTESTATION_INSTALLED_TREE_MANIFEST_MISMATCH"
R_INSTALLED_FILE_MISMATCH = "PROVIDER_ATTESTATION_INSTALLED_FILE_MISMATCH"
R_WORKER_ENTRYPOINT_MISMATCH = "PROVIDER_ATTESTATION_WORKER_ENTRYPOINT_MISMATCH"
R_WORKER_SOURCE_MISMATCH = "PROVIDER_ATTESTATION_WORKER_SOURCE_MISMATCH"
R_PYTHON_BUILD_MISMATCH = "PROVIDER_ATTESTATION_PYTHON_BUILD_MISMATCH"
R_PROBE_FAILED = "PROVIDER_ATTESTATION_PROBE_FAILED"
R_CONTRACT_ABSENT = "PROVIDER_LAUNCH_CONTRACT_ABSENT"
R_CONTRACT_INVALID = "PROVIDER_LAUNCH_CONTRACT_INVALID"
R_FLAGS_MISMATCH = "PROVIDER_ATTESTATION_INTERPRETER_FLAGS_MISMATCH"
R_USER_SITE_ENABLED = "PROVIDER_ATTESTATION_USER_SITE_ENABLED"
R_VENV_MISMATCH = "PROVIDER_ATTESTATION_VENV_MISMATCH"
R_INTERPRETER_MISMATCH = "PROVIDER_ATTESTATION_INTERPRETER_MISMATCH"
R_SYS_PATH_CONTAMINATED = "PROVIDER_ATTESTATION_SYS_PATH_CONTAMINATED"
R_STARTUP_HOOK_LOADED = "PROVIDER_ATTESTATION_STARTUP_HOOK_LOADED"
R_PROTOCOL_MISMATCH = "PROVIDER_ATTESTATION_PROTOCOL_MISMATCH"
R_ENV_UNEXPECTED_NAME = "PROVIDER_ATTESTATION_ENVIRONMENT_UNEXPECTED_NAME"
R_DENIED_CREDENTIAL_PRESENT = "PROVIDER_ATTESTATION_DENIED_CREDENTIAL_PRESENT"
R_PROFILE_NOT_REDIRECTED = "PROVIDER_ATTESTATION_PROFILE_NOT_REDIRECTED"
R_CWD_MISMATCH = "PROVIDER_ATTESTATION_CWD_MISMATCH"
R_MANIFEST_DIGEST_MISMATCH = "PROVIDER_ATTESTATION_MANIFEST_DIGEST_MISMATCH"
R_PROVIDER_LOADED_EARLY = "PROVIDER_MODULE_LOADED_BEFORE_ATTESTATION"
R_STUBS_MISMATCH = "PROVIDER_ATTESTATION_STARTUP_STUBS_MISMATCH"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PLACEHOLDER_CREDENTIAL_RE = re.compile(
    r"^(?:|x+|0+|placeholder|dummy|test|testing|changeme|change[-_]?me|your[-_ ]?(?:api[-_ ]?)?key|fake|none|null|todo|tbd|<.*>)$",
    re.IGNORECASE,
)


class ProviderBuildManifestError(RuntimeError):
    """The manifest/registry/lock itself is absent, malformed or violates its contract."""

    def __init__(self, reason_code: str, failures: Sequence[Mapping[str, Any]] | None = None):
        self.reason_code = reason_code
        self.failures = [dict(item) for item in (failures or [{"code": reason_code}])]
        super().__init__(f"{reason_code}:{json.dumps(self.failures[:5], sort_keys=True, default=str)}")


class ProviderAttestationError(RuntimeError):
    """Launch refused before any provider process or provider import (never a provider outcome)."""

    def __init__(self, reason_code: str, failures: Sequence[Mapping[str, Any]]):
        self.reason_code = reason_code
        self.failures = [dict(item) for item in failures] or [{"code": reason_code}]
        super().__init__(f"{reason_code}:{json.dumps(self.failures[:5], sort_keys=True, default=str)}")

    def detail(self) -> dict[str, Any]:
        return {"attestation_failures": self.failures[:50], "failure_count": len(self.failures)}


def _failure(code: str, **detail: Any) -> dict[str, Any]:
    return {"code": code, **{key: value for key, value in detail.items() if value is not None}}


# ---------------------------------------------------------------------------------------------
# Hashing.
# ---------------------------------------------------------------------------------------------


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_identity(path: Path, relative_path: str) -> dict[str, Any]:
    return {"relative_path": relative_path, "size": path.stat().st_size, "sha256": sha256_file(path)}


def _norm(path: Any) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.match(value))


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


# ---------------------------------------------------------------------------------------------
# Minimal JSON Schema (draft 2020-12 subset) validator -- stdlib only, deterministic.
# ---------------------------------------------------------------------------------------------

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def schema_errors(instance: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    """Errors of ``instance`` against the subset of JSON Schema this repository's contracts use:
    type, const, enum, pattern, minLength, minimum, maximum, required, properties,
    additionalProperties, items, minItems, uniqueItems, anyOf, allOf, if/then/else."""
    errors: list[str] = []
    if not isinstance(schema, Mapping):
        return errors
    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_TYPE_CHECKS[name](instance) for name in types):
            return [f"{path}: expected type {types}, got {type(instance).__name__}"]
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in {schema['enum']!r}")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: does not match {schema['pattern']!r}")
    if _TYPE_CHECKS["number"](instance):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: above maximum {schema['maximum']}")
    if isinstance(instance, dict):
        for name in schema.get("required", ()):
            if name not in instance:
                errors.append(f"{path}: missing required property {name!r}")
        properties = schema.get("properties", {})
        for name, value in instance.items():
            if name in properties:
                errors.extend(schema_errors(value, properties[name], f"{path}.{name}"))
            else:
                extra = schema.get("additionalProperties", True)
                if extra is False:
                    errors.append(f"{path}: unexpected property {name!r}")
                elif isinstance(extra, Mapping):
                    errors.extend(schema_errors(value, extra, f"{path}.{name}"))
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if schema.get("uniqueItems") and len({canonical_sha256(item) for item in instance}) != len(instance):
            errors.append(f"{path}: items are not unique")
        if "items" in schema:
            for index, item in enumerate(instance):
                errors.extend(schema_errors(item, schema["items"], f"{path}[{index}]"))
    if "anyOf" in schema:
        if not any(not schema_errors(instance, option, path) for option in schema["anyOf"]):
            errors.append(f"{path}: matches no anyOf alternative")
    for option in schema.get("allOf", ()):
        errors.extend(schema_errors(instance, option, path))
    if "if" in schema:
        branch = "then" if not schema_errors(instance, schema["if"], path) else "else"
        if branch in schema:
            errors.extend(schema_errors(instance, schema[branch], path))
    return errors


def load_schema(path: Path | None = None) -> dict[str, Any]:
    return json.loads(Path(path or SCHEMA_PATH).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------
# Manifest loading and contract validation.
# ---------------------------------------------------------------------------------------------


def manifest_digest(manifest: Mapping[str, Any]) -> str:
    """Canonical SHA-256 of the manifest object (whitespace/key-order independent). The owner
    policy pins exactly this value."""
    return canonical_sha256(manifest)


def load_manifest(path: Path | str | None = None, *, schema_path: Path | None = None) -> tuple[dict[str, Any], str]:
    """``(manifest, canonical digest)``; raises ``ProviderBuildManifestError`` (fail closed)."""
    manifest_path = Path(path) if path is not None else MANIFEST_PATH
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ProviderBuildManifestError(R_MANIFEST_ABSENT, [_failure(R_MANIFEST_ABSENT, path=str(manifest_path))]) from None
    except OSError as exc:
        raise ProviderBuildManifestError(R_MANIFEST_ABSENT, [_failure(R_MANIFEST_ABSENT, error=type(exc).__name__)]) from None
    try:
        manifest = json.loads(raw)
    except ValueError as exc:
        raise ProviderBuildManifestError(R_MANIFEST_MALFORMED, [_failure(R_MANIFEST_MALFORMED, error=str(exc)[:200])]) from None
    if not isinstance(manifest, dict):
        raise ProviderBuildManifestError(R_MANIFEST_MALFORMED, [_failure(R_MANIFEST_MALFORMED, error="not an object")])
    errors = schema_errors(manifest, load_schema(schema_path))
    if errors:
        raise ProviderBuildManifestError(
            R_MANIFEST_SCHEMA_INVALID, [_failure(R_MANIFEST_SCHEMA_INVALID, error=item) for item in errors[:50]],
        )
    violations = manifest_contract_violations(manifest)
    if violations:
        raise ProviderBuildManifestError(violations[0]["code"], violations)
    return manifest, manifest_digest(manifest)


def telemetry_endpoint_rule(entry: Mapping[str, Any]) -> dict[str, Any]:
    """The endpoint rule an owner-approved (``ALLOW_OWNER_APPROVED``) NETWORK telemetry entry adds."""
    return {
        "scheme": entry.get("scheme"), "host": entry.get("host"), "port": entry.get("port"),
        "method": entry.get("method"), "path_pattern": entry.get("path_pattern"),
        "purpose": f"TELEMETRY_OWNER_APPROVED:{entry.get('endpoint_ref')}", "max_redirects": 0,
    }


def _endpoint_violations(endpoints: Any, *, field_name: str) -> list[dict[str, Any]]:
    import provider_worker_containment as containment

    failures = []
    seen = set()
    for index, raw in enumerate(endpoints or []):
        try:
            rule = containment.EndpointRule.from_mapping(raw)
        except (TypeError, ValueError) as exc:
            failures.append(_failure(R_ENDPOINT_CONTRACT_INVALID, field=f"{field_name}[{index}]", error=str(exc)))
            continue
        key = (rule.host, rule.method, rule.path_pattern)
        if key in seen:
            failures.append(_failure(R_ENDPOINT_CONTRACT_INVALID, field=f"{field_name}[{index}]", error="duplicate"))
        seen.add(key)
    return failures


def rate_binding_violations(
    binding: Mapping[str, Any] | None, credential: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Credential mechanism, vendor tier and governor rate must be approved together (N3)."""
    failures: list[dict[str, Any]] = []
    credential = credential or {}
    mechanism = credential.get("mechanism")
    tier = credential.get("expected_vnai_tier")
    if mechanism not in CREDENTIAL_MECHANISMS:
        return [_failure(R_CREDENTIAL_CONTRACT_INVALID, error=f"mechanism {mechanism!r} unresolved")]
    if credential.get("fabricated_or_placeholder_key_forbidden") is not True:
        failures.append(_failure(R_CREDENTIAL_CONTRACT_INVALID, error="fabricated/placeholder keys must be forbidden"))
    if mechanism == CREDENTIAL_NONE:
        if tier != TIER_GUEST or credential.get("credential_name") is not None:
            failures.append(_failure(R_CREDENTIAL_CONTRACT_INVALID, error="mechanism NONE implies tier guest and no credential name"))
    else:
        if tier != TIER_FREE:
            failures.append(_failure(R_CREDENTIAL_CONTRACT_INVALID, error="a credential mechanism implies the free tier"))
        if not credential.get("owner_decision_id"):
            failures.append(_failure(R_CREDENTIAL_CONTRACT_INVALID, error="credential mechanism without owner decision id"))
        expected_name = VENDOR_CREDENTIAL_NAME if mechanism == CREDENTIAL_APPROVED_ENV_NAME else None
        if credential.get("credential_name") != expected_name:
            failures.append(_failure(R_CREDENTIAL_CONTRACT_INVALID, error=f"credential_name must be {expected_name!r}"))
    if not isinstance(binding, Mapping):
        return failures + [_failure(R_RATE_BINDING_INVALID, error="rate_tier_binding unresolved")]
    if binding.get("tier") != tier:
        failures.append(_failure(R_TIER_MISMATCH, error=f"rate tier {binding.get('tier')!r} != credential tier {tier!r}"))
    reviewed = REVIEWED_VENDOR_TIER_LIMITS.get(str(tier))
    limits = binding.get("tier_limits") or {}
    if reviewed is None:
        failures.append(_failure(R_RATE_BINDING_INVALID, error=f"unknown tier {tier!r}"))
        return failures
    for unit in ("min", "hour", "day"):
        value = limits.get(unit)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > reviewed[unit]:
            failures.append(_failure(R_RATE_BINDING_INVALID, error=f"tier_limits.{unit} {value!r} outside 1..{reviewed[unit]}"))
    fraction = binding.get("max_fraction_of_tier_minute_limit")
    if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or not 0 < fraction <= MAX_FRACTION_OF_TIER_MINUTE_LIMIT:
        failures.append(_failure(R_RATE_BINDING_INVALID, error=f"max fraction {fraction!r} not in (0, {MAX_FRACTION_OF_TIER_MINUTE_LIMIT}]"))
        fraction = MAX_FRACTION_OF_TIER_MINUTE_LIMIT
    rpm = binding.get("governor_effective_rpm")
    minute = limits.get("min") if isinstance(limits.get("min"), int) else reviewed["min"]
    ceiling = min(int(fraction * minute), OWNER_APPROVED_GOVERNOR_CEILING_RPM)
    if not isinstance(rpm, int) or isinstance(rpm, bool) or rpm < 1 or rpm > ceiling:
        failures.append(_failure(
            R_GOVERNOR_EXCEEDS_APPROVED,
            error=f"governor rpm {rpm!r} > min(floor({fraction} x {minute}), owner ceiling "
                  f"{OWNER_APPROVED_GOVERNOR_CEILING_RPM}) = {ceiling}",
        ))
    budget = binding.get("planned_session_request_budget")
    day = limits.get("day") if isinstance(limits.get("day"), int) else reviewed["day"]
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0 or budget > day:
        failures.append(_failure(R_RATE_BINDING_INVALID, error=f"planned session budget {budget!r} outside 0..{day}"))
    return failures


def manifest_contract_violations(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Invariants every manifest satisfies whatever its status (beyond the JSON schema)."""
    failures: list[dict[str, Any]] = []
    status = manifest.get("status")
    if manifest.get("authority_effect") != AUTHORITY_EFFECT:
        failures.append(_failure(R_MANIFEST_CONTRACT_INVALID, error="authority_effect must be NONE_OPERATIONAL_METADATA_ONLY"))
    if status != STATUS_APPROVED and manifest.get("launch_authorized") is not False:
        failures.append(_failure(R_MANIFEST_CONTRACT_INVALID, error="only an APPROVED_PINNED_BUILD may authorise launch"))
    if status != STATUS_APPROVED and manifest.get("approval") is not None:
        failures.append(_failure(R_MANIFEST_CONTRACT_INVALID, error="approval values populated on an unapproved manifest"))
    network = manifest.get("network") or {}
    failures += _endpoint_violations(network.get("endpoints"), field_name="network.endpoints")
    candidates = network.get("review_candidate_endpoints") or []
    for index, item in enumerate(candidates):
        if item.get("state") != "REVIEW_CANDIDATE_NOT_APPROVED":
            failures.append(_failure(R_ENDPOINT_CONTRACT_INVALID, field=f"network.review_candidate_endpoints[{index}]",
                                     error="a review candidate is never an approved endpoint"))
    environment = manifest.get("environment") or {}
    allowed = [str(name).upper() for name in environment.get("allowed_names") or []]
    credential_names = [str(name).upper() for name in environment.get("credential_names") or []]
    for name in allowed:
        if runtime_contract.is_denied_family(name) or name.startswith("FHSC_") or name in REQUIRED_FORBIDDEN_NAMES:
            failures.append(_failure(R_ENVIRONMENT_CONTRACT_INVALID, error=f"denied name allowed: {name}"))
        if runtime_contract.is_secret_shaped(name) and name not in credential_names:
            failures.append(_failure(R_ENVIRONMENT_CONTRACT_INVALID, error=f"secret-shaped name allowed: {name}"))
        if name in REDIRECTED_PROFILE_NAMES or name == "TMPDIR":
            failures.append(_failure(R_ENVIRONMENT_CONTRACT_INVALID, error=f"profile name {name} must be redirected, not allowed"))
    for name in credential_names:
        if name != VENDOR_CREDENTIAL_NAME:
            failures.append(_failure(R_ENVIRONMENT_CONTRACT_INVALID, error=f"credential name {name} not the vendor credential"))
    for prefix in REQUIRED_FORBIDDEN_PREFIXES:
        if prefix not in (environment.get("forbidden_prefixes") or []):
            failures.append(_failure(R_ENVIRONMENT_CONTRACT_INVALID, error=f"forbidden prefix {prefix} missing"))
    for name in REQUIRED_FORBIDDEN_NAMES:
        if name not in (environment.get("forbidden_names") or []):
            failures.append(_failure(R_ENVIRONMENT_CONTRACT_INVALID, error=f"forbidden name {name} missing"))
    if sorted(environment.get("denied_secret_classes") or []) != sorted(DENIED_SECRET_CLASSES):
        failures.append(_failure(R_ENVIRONMENT_CONTRACT_INVALID, error="denied_secret_classes must name all eleven classes"))
    if sorted((environment.get("redirected_profile_names") or {}).keys()) != sorted(REDIRECTED_PROFILE_NAMES):
        failures.append(_failure(R_ENVIRONMENT_CONTRACT_INVALID, error="redirected_profile_names must cover every profile name"))
    worker = manifest.get("worker") or {}
    if worker.get("lineage_endpoint_map") != LINEAGE_ENDPOINT_MAP:
        failures.append(_failure(R_WORKER_CONTRACT_INVALID, error="lineage_endpoint_map must record the reviewed routes"))
    sources = {item.get("relative_path") for item in worker.get("source_files") or []}
    if worker.get("entrypoint") not in sources:
        failures.append(_failure(R_WORKER_CONTRACT_INVALID, error="entrypoint is not a bound source file"))
    if list(worker.get("argv_flags") or []) != list(runtime_contract.WORKER_INTERPRETER_FLAGS):
        failures.append(_failure(R_WORKER_CONTRACT_INVALID, error="argv_flags differ from the governed worker flags"))
    if [dict(item) for item in worker.get("startup_stubs") or []] != [dict(item) for item in WORKER_STARTUP_STUBS]:
        failures.append(_failure(R_STUBS_MISMATCH, error="startup_stubs differ from the worker's stub set"))
    if status == STATUS_APPROVED:
        failures += rate_binding_violations(manifest.get("rate_tier_binding"), manifest.get("vendor_credential"))
        for index, entry in enumerate(manifest.get("telemetry_disposition") or []):
            if entry.get("decision") not in (TELEMETRY_DENY, TELEMETRY_ALLOW):
                failures.append(_failure(R_TELEMETRY_UNRESOLVED, field=f"telemetry_disposition[{index}]"))
            elif entry.get("decision") == TELEMETRY_ALLOW and entry.get("layer") == "NETWORK":
                failures += _endpoint_violations([telemetry_endpoint_rule(entry)], field_name=f"telemetry_disposition[{index}]")
            elif entry.get("decision") == TELEMETRY_ALLOW:
                failures.append(_failure(R_TELEMETRY_UNRESOLVED, field=f"telemetry_disposition[{index}]",
                                         error="only a NETWORK telemetry route can be owner-allowed; processes are always denied"))
        filesystem = manifest.get("filesystem") or {}
        state_root, scratch = filesystem.get("provider_state_root"), filesystem.get("provider_scratch_base")
        if not (isinstance(state_root, str) and os.path.isabs(state_root) and isinstance(scratch, str) and os.path.isabs(scratch)):
            failures.append(_failure(R_FILESYSTEM_CONTRACT_INVALID, error="state root and scratch base must be absolute"))
        elif _norm(state_root) == _norm(scratch) or _norm(scratch).startswith(_norm(state_root) + os.sep) \
                or _norm(state_root).startswith(_norm(scratch) + os.sep):
            failures.append(_failure(R_FILESYSTEM_CONTRACT_INVALID, error="state root and scratch base must not overlap"))
        packages = {str(item.get("name")).lower() for item in manifest.get("packages") or []}
        for name in PROVIDER_DISTRIBUTIONS:
            if name not in packages:
                failures.append(_failure(R_MISSING_DISTRIBUTION, error=f"approved build lacks {name}"))
    return failures


# ---------------------------------------------------------------------------------------------
# Revocation registry.
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RevocationStatus:
    revoked: bool
    reason_code: str | None
    epoch: int | None
    registry_epoch: int | None
    reason: str | None = None
    revoked_at_utc: str | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "revoked": self.revoked, "reason_code": self.reason_code, "manifest_epoch": self.epoch,
            "registry_epoch": self.registry_epoch, "reason": self.reason, "revoked_at_utc": self.revoked_at_utc,
        }


def load_revocation_registry(path: Path | str | None = None) -> dict[str, Any]:
    registry_path = Path(path) if path is not None else REVOCATION_REGISTRY_PATH
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProviderBuildManifestError(R_REGISTRY_INVALID, [_failure(R_REGISTRY_INVALID, error=type(exc).__name__)]) from None
    problems = []
    if not isinstance(payload, dict) or payload.get("contract_version") != REVOCATION_REGISTRY_CONTRACT_VERSION:
        problems.append("contract_version")
    else:
        epoch = payload.get("current_epoch")
        if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
            problems.append("current_epoch")
        if not isinstance(payload.get("builds"), dict):
            problems.append("builds")
        if not isinstance(payload.get("revoked_manifest_sha256"), list) or not all(
                _is_sha256(item) for item in payload.get("revoked_manifest_sha256") or []):
            problems.append("revoked_manifest_sha256")
        for build_id, entry in (payload.get("builds") or {}).items():
            if not isinstance(entry, dict) or entry.get("state") not in (REVOCATION_ACTIVE, REVOCATION_REVOKED):
                problems.append(f"builds.{build_id}")
    if problems:
        raise ProviderBuildManifestError(R_REGISTRY_INVALID, [_failure(R_REGISTRY_INVALID, field=item) for item in problems])
    return payload


def revocation_status(manifest: Mapping[str, Any], digest: str, registry: Mapping[str, Any]) -> RevocationStatus:
    revocation = manifest.get("revocation") or {}
    epoch = revocation.get("epoch")
    registry_epoch = registry.get("current_epoch")
    entry = (registry.get("builds") or {}).get(manifest.get("build_id")) or {}
    if revocation.get("state") == REVOCATION_REVOKED or entry.get("state") == REVOCATION_REVOKED \
            or digest in (registry.get("revoked_manifest_sha256") or []):
        return RevocationStatus(True, R_REVOKED, epoch, registry_epoch,
                                reason=entry.get("reason") or revocation.get("reason"),
                                revoked_at_utc=entry.get("revoked_at_utc") or revocation.get("revoked_at_utc"))
    if revocation.get("state") != REVOCATION_ACTIVE:
        return RevocationStatus(True, R_NOT_APPROVED, epoch, registry_epoch, reason="revocation state not ACTIVE")
    if epoch != registry_epoch or entry.get("epoch", epoch) != epoch:
        return RevocationStatus(True, R_EPOCH_STALE, epoch, registry_epoch,
                                reason=entry.get("reason") or "manifest epoch is not the registry's current epoch",
                                revoked_at_utc=entry.get("revoked_at_utc"))
    return RevocationStatus(False, None, epoch, registry_epoch)


class RevocationMonitor:
    """Cheap, foreground re-check of the registry at each controlled boundary (no polling, no
    thread): re-parses only when the file's size/mtime changed."""

    def __init__(self, manifest: Mapping[str, Any], digest: str, registry_path: Path | str):
        self._manifest = dict(manifest)
        self._digest = digest
        self._path = Path(registry_path)
        self._stamp: tuple[int, int] | None = None
        self._status: RevocationStatus | None = None

    def check(self) -> RevocationStatus:
        try:
            info = self._path.stat()
            stamp = (info.st_size, info.st_mtime_ns)
        except OSError:
            return RevocationStatus(True, R_REGISTRY_INVALID, self._manifest.get("revocation", {}).get("epoch"), None,
                                    reason="revocation registry unreadable")
        if stamp != self._stamp or self._status is None:
            try:
                registry = load_revocation_registry(self._path)
                self._status = revocation_status(self._manifest, self._digest, registry)
            except ProviderBuildManifestError as exc:
                self._status = RevocationStatus(True, R_REGISTRY_INVALID, self._manifest.get("revocation", {}).get("epoch"),
                                                None, reason=exc.reason_code)
            self._stamp = stamp
        return self._status


# ---------------------------------------------------------------------------------------------
# Dependency lock.
# ---------------------------------------------------------------------------------------------


def load_dependency_lock(path: Path | str | None = None) -> tuple[dict[str, Any], str]:
    lock_path = Path(path) if path is not None else DEPENDENCY_LOCK_PATH
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProviderBuildManifestError(R_DEPENDENCY_LOCK_MISMATCH, [_failure(R_DEPENDENCY_LOCK_MISMATCH, error=type(exc).__name__)]) from None
    violations = dependency_lock_violations(payload)
    if violations:
        raise ProviderBuildManifestError(R_DEPENDENCY_LOCK_MISMATCH, violations)
    return payload, canonical_sha256(payload)


def dependency_lock_violations(lock: Any) -> list[dict[str, Any]]:
    """Structural invariants of the provider dependency lock (config/provider_dependency_lock.json)."""
    if not isinstance(lock, dict) or lock.get("contract_version") != DEPENDENCY_LOCK_CONTRACT_VERSION:
        return [_failure(R_DEPENDENCY_LOCK_MISMATCH, error="contract_version")]
    failures = []
    candidates = lock.get("candidate_closure") or {}
    entries = candidates.get("packages") or []
    names = [str(item.get("name")) for item in entries]
    if len(set(names)) != len(names):
        failures.append(_failure(R_DEPENDENCY_LOCK_MISMATCH, error="duplicate package"))
    for item in entries:
        if not (item.get("version") and item.get("artifact_filename") and _is_sha256(item.get("artifact_sha256"))):
            failures.append(_failure(R_DEPENDENCY_LOCK_MISMATCH, error=f"incomplete pin {item.get('name')}"))
    count = candidates.get("count")
    if count != len(entries):
        failures.append(_failure(R_DEPENDENCY_LOCK_MISMATCH, error="count"))
    minimal = set((lock.get("runtime_minimal_hypothesis") or {}).get("packages") or [])
    unnecessary = set((lock.get("unnecessary_for_governed_worker") or {}).get("packages") or [])
    known = set(names)
    if not minimal <= known or not unnecessary <= known:
        failures.append(_failure(R_DEPENDENCY_LOCK_MISMATCH, error="subsets must be within the candidate closure"))
    if minimal & unnecessary:
        failures.append(_failure(R_DEPENDENCY_LOCK_MISMATCH, error="a package is both minimal and unnecessary"))
    if (minimal | unnecessary) != known:
        failures.append(_failure(R_DEPENDENCY_LOCK_MISMATCH, error="minimal + unnecessary must partition the candidate closure"))
    not_required = lock.get("not_required_for_governed_worker") or {}
    for key in ("anthropic", "core_requirements_txt", "plotting_chart_stack", "notebook_ipython_ui"):
        if key not in not_required:
            failures.append(_failure(R_DEPENDENCY_LOCK_MISMATCH, error=f"not-required record missing {key}"))
    if "anthropic" in known:
        failures.append(_failure(R_DEPENDENCY_LOCK_MISMATCH, error="anthropic is not a provider-worker dependency"))
    return failures


# ---------------------------------------------------------------------------------------------
# Installed-tree identity (parent static attestation; also used to describe a candidate runtime).
# ---------------------------------------------------------------------------------------------

_FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _is_link(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


def _walk_tree(root: Path) -> Iterable[tuple[Path, bool]]:
    """``(path, is_link)`` for every file and link below ``root``; never follows a link."""
    stack = [root]
    while stack:
        current = stack.pop()
        with os.scandir(current) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                if _is_link(path):
                    yield path, True
                elif entry.is_dir(follow_symlinks=False):
                    stack.append(path)
                else:
                    yield path, False


def _posix_relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def build_installed_tree_manifest(venv_root: Path | str) -> dict[str, Any]:
    """Every file under the venv root: size + SHA-256, and every link with its resolved target."""
    root = Path(venv_root)
    files, links = [], []
    for path, is_link in _walk_tree(root):
        relative = _posix_relative(path, root)
        if is_link:
            links.append({"relative_path": relative, "resolved_target": os.path.realpath(path)})
        else:
            files.append(file_identity(path, relative))
    return {
        "contract_version": INSTALLED_TREE_CONTRACT_VERSION, "root": "VENV_ROOT",
        "files": sorted(files, key=lambda item: item["relative_path"]),
        "links": sorted(links, key=lambda item: item["relative_path"]),
    }


def _read_metadata(dist_info: Path) -> tuple[str | None, str | None]:
    metadata = dist_info / "METADATA"
    if not metadata.is_file():
        metadata = dist_info / "PKG-INFO"
    name = version = None
    try:
        for line in metadata.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                break
            if line.startswith("Name:") and name is None:
                name = line.split(":", 1)[1].strip()
            elif line.startswith("Version:") and version is None:
                version = line.split(":", 1)[1].strip()
    except OSError:
        return None, None
    return name, version


def canonical_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", str(name)).lower()


def installed_distributions(site_dir: Path) -> dict[str, dict[str, Any]]:
    """``{canonical name: {name, version, dist_info}}`` for every ``*.dist-info``/``*.egg-info``."""
    result: dict[str, dict[str, Any]] = {}
    if not site_dir.is_dir():
        return result
    for entry in sorted(site_dir.iterdir(), key=lambda item: item.name):
        if entry.suffix in (".dist-info", ".egg-info") and entry.is_dir():
            name, version = _read_metadata(entry)
            key = canonical_distribution_name(name or entry.name.split("-", 1)[0])
            result[key] = {"name": name, "version": version, "dist_info": entry.name}
    return result


def distribution_installed_manifest(site_dir: Path, dist_info: str) -> dict[str, Any]:
    """Every RECORD-listed file of one distribution with its actual SHA-256 (``None`` = missing)."""
    record = site_dir / dist_info / "RECORD"
    entries = []
    try:
        rows = list(csv.reader(io.StringIO(record.read_text(encoding="utf-8"))))
    except OSError:
        rows = []
    for row in rows:
        if not row or not row[0]:
            continue
        relative = row[0].replace("\\", "/")
        path = (site_dir / relative).resolve()
        entries.append({"path": relative, "sha256": sha256_file(path) if path.is_file() else None})
    return {"dist_info": dist_info, "files": sorted(entries, key=lambda item: item["path"])}


def distribution_manifest_sha256(site_dir: Path, dist_info: str) -> str:
    return canonical_sha256(distribution_installed_manifest(site_dir, dist_info))


def _site_dirs(venv_root: Path, relative_dirs: Sequence[str]) -> list[Path]:
    return [(venv_root / relative).resolve() if relative != "." else venv_root.resolve() for relative in relative_dirs]


def startup_hook_inventory(venv_root: Path, relative_site_dirs: Sequence[str]) -> list[dict[str, Any]]:
    """Every ``.pth`` file and ``sitecustomize``/``usercustomize`` module in the venv's site dirs."""
    hooks = []
    for site_dir in _site_dirs(venv_root, relative_site_dirs):
        if not site_dir.is_dir():
            continue
        for entry in sorted(site_dir.iterdir(), key=lambda item: item.name):
            lowered = entry.name.lower()
            if entry.is_file() and (lowered.endswith(".pth") or lowered in ("sitecustomize.py", "usercustomize.py")):
                hooks.append(file_identity(entry, _posix_relative(entry, venv_root.resolve())))
            elif entry.is_dir() and lowered in ("sitecustomize", "usercustomize"):
                hooks.append({"relative_path": _posix_relative(entry, venv_root.resolve()), "size": -1, "sha256": "DIRECTORY"})
    return sorted(hooks, key=lambda item: item["relative_path"])


def _read_pyvenv_cfg(venv_root: Path) -> dict[str, str]:
    values = {}
    for line in (venv_root / "pyvenv.cfg").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip().lower()] = value.strip()
    return values


_PROBE_SOURCE = (
    "import json, platform, struct, sys\n"
    "print(json.dumps({'executable': sys.executable, 'python_version': platform.python_version(),"
    " 'python_build': sys.version, 'implementation': sys.implementation.name,"
    " 'pointer_bits': struct.calcsize('P') * 8, 'platform': sys.platform,"
    " 'base_prefix': sys.base_prefix}, sort_keys=True))\n"
)


def probe_interpreter(executable: str, *, env: Mapping[str, str] | None = None, timeout: float = 20.0) -> dict[str, Any]:
    """Run the (already hash-verified) interpreter isolated (``-I -S -B``): no site, no user site,
    no ``PYTHON*`` variables, no bytecode writes, no provider discovery. Returns build identity."""
    completed = subprocess.run(
        [executable, "-I", "-S", "-B", "-c", _PROBE_SOURCE], capture_output=True, text=True,
        timeout=timeout, env=dict(env) if env is not None else {}, check=False,
    )
    if completed.returncode != 0:
        raise ProviderAttestationError(R_PROBE_FAILED, [_failure(R_PROBE_FAILED, returncode=completed.returncode,
                                                                 stderr=completed.stderr[-300:])])
    try:
        return json.loads(completed.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise ProviderAttestationError(R_PROBE_FAILED, [_failure(R_PROBE_FAILED, error="unparseable probe output")]) from None


def describe_provider_runtime(
    executable: str, *, site_dirs: Sequence[str] | None = None, probe_env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Describe an EXISTING candidate provider interpreter for owner review (never approves).

    Returns ``{"runtime": {...}, "packages": [...], "installed_tree_manifest": {...}}`` -- the
    runtime-bound manifest sections. Installs nothing and imports no provider package.
    """
    exe = Path(os.path.abspath(executable))
    probe = probe_interpreter(str(exe), env=probe_env)
    venv_root = exe.parent.parent
    cfg = _read_pyvenv_cfg(venv_root)
    base_prefix = Path(probe["base_prefix"])
    if os.name == "nt":
        base_executable = Path(cfg.get("home", "")) / "python.exe"
        relative_site_dirs = list(site_dirs or [".", "Lib/site-packages"])
    else:
        base_executable = Path(os.path.realpath(exe))
        version = "python" + ".".join(probe["python_version"].split(".")[:2])
        relative_site_dirs = list(site_dirs or [f"lib/{version}/site-packages"])
    base_files = []
    for candidate in sorted(base_prefix.glob("python3*.dll")) if os.name == "nt" else []:
        base_files.append(file_identity(candidate, _posix_relative(candidate, base_prefix)))
    tree = build_installed_tree_manifest(venv_root)
    packages = []
    for site_dir in _site_dirs(venv_root, relative_site_dirs):
        for key, dist in installed_distributions(site_dir).items():
            packages.append({
                "name": key, "version": dist["version"], "dist_info": dist["dist_info"],
                "site_dir": _posix_relative(site_dir, venv_root.resolve()) if site_dir != venv_root.resolve() else ".",
                "installed_manifest_sha256": distribution_manifest_sha256(site_dir, dist["dist_info"]),
            })
    runtime = {
        "executable_path": str(exe), "executable_sha256": sha256_file(exe),
        "executable_realpath": os.path.realpath(exe),
        "python_version": probe["python_version"], "python_build": probe["python_build"],
        "implementation": probe["implementation"], "pointer_bits": probe["pointer_bits"], "platform": probe["platform"],
        "venv_root": str(venv_root), "venv_config_sha256": sha256_file(venv_root / "pyvenv.cfg"),
        "include_system_site_packages": cfg.get("include-system-site-packages", "false").lower() == "true",
        "user_site_enabled": False,
        "base_prefix": str(base_prefix), "base_executable_path": str(base_executable),
        "base_executable_sha256": sha256_file(base_executable), "base_runtime_files": base_files,
        "site_dirs": relative_site_dirs,
        "startup_hook_files": startup_hook_inventory(venv_root, relative_site_dirs),
        "installed_tree_manifest": {"path": None, "sha256": canonical_sha256(tree), "file_count": len(tree["files"])},
    }
    return {"runtime": runtime, "packages": sorted(packages, key=lambda item: item["name"]), "installed_tree_manifest": tree}


def _resolve_relative(path_value: str, base: Path) -> Path:
    candidate = Path(path_value)
    return candidate if candidate.is_absolute() else (base / candidate)


def attest_runtime_static(
    manifest: Mapping[str, Any], *, configured_executable: str, manifest_dir: Path,
    producer_root: Path = ROOT, worker_script: Path | None = None,
) -> list[dict[str, Any]]:
    """Static attestation of the configured provider interpreter against the manifest.

    Reads and hashes files only; executes nothing. Returns every failure (empty = attested).
    """
    runtime = manifest.get("runtime") or {}
    failures: list[dict[str, Any]] = []
    exe = Path(os.path.abspath(configured_executable))
    if _norm(exe) != _norm(runtime.get("executable_path", "")):
        return [_failure(R_INTERPRETER_PATH_MISMATCH, configured=str(exe), bound=runtime.get("executable_path"))]
    if not exe.is_file():
        return [_failure(R_EXECUTABLE_MISSING, path=str(exe))]
    venv_root = Path(runtime.get("venv_root", ""))
    if _is_link(exe):
        if os.name == "nt" or _norm(os.path.realpath(exe)) != _norm(runtime.get("executable_realpath", "")):
            failures.append(_failure(R_REPARSE_POINT, path=str(exe), resolved=os.path.realpath(exe)))
    elif _norm(os.path.realpath(exe)) != _norm(runtime.get("executable_realpath", "")):
        failures.append(_failure(R_INTERPRETER_PATH_MISMATCH, resolved=os.path.realpath(exe)))
    if sha256_file(exe) != runtime.get("executable_sha256"):
        failures.append(_failure(R_EXECUTABLE_HASH_MISMATCH, path=str(exe)))
    if not _norm(exe).startswith(_norm(venv_root) + os.sep):
        failures.append(_failure(R_VENV_CONFIG_MISMATCH, error="executable outside the bound venv root"))
    for directory in (venv_root, *_site_dirs(venv_root, runtime.get("site_dirs") or [])):
        if _is_link(directory):
            failures.append(_failure(R_REPARSE_POINT, path=str(directory)))
    cfg_path = venv_root / "pyvenv.cfg"
    if not cfg_path.is_file() or sha256_file(cfg_path) != runtime.get("venv_config_sha256"):
        failures.append(_failure(R_VENV_CONFIG_MISMATCH, path=str(cfg_path)))
    else:
        cfg = _read_pyvenv_cfg(venv_root)
        if cfg.get("include-system-site-packages", "false").lower() != "false" or runtime.get("include_system_site_packages"):
            failures.append(_failure(R_SYSTEM_SITE_ENABLED))
    base_executable = Path(runtime.get("base_executable_path", ""))
    if not base_executable.is_file() or sha256_file(base_executable) != runtime.get("base_executable_sha256"):
        failures.append(_failure(R_BASE_RUNTIME_MISMATCH, path=str(base_executable)))
    base_prefix = Path(runtime.get("base_prefix", ""))
    for item in runtime.get("base_runtime_files") or []:
        path = base_prefix / item["relative_path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            failures.append(_failure(R_BASE_RUNTIME_MISMATCH, path=item["relative_path"]))
    if failures:
        return failures  # an unverified interpreter's tree is not worth walking
    hooks = startup_hook_inventory(venv_root, runtime.get("site_dirs") or [])
    bound_hooks = sorted([dict(item) for item in runtime.get("startup_hook_files") or []], key=lambda item: item["relative_path"])
    if hooks != bound_hooks:
        observed = {item["relative_path"]: item for item in hooks}
        bound = {item["relative_path"]: item for item in bound_hooks}
        for name in sorted(set(observed) | set(bound)):
            if observed.get(name) != bound.get(name):
                failures.append(_failure(R_STARTUP_HOOK_UNEXPECTED, path=name,
                                         state="UNBOUND" if name not in bound else ("MISSING" if name not in observed else "HASH_MISMATCH")))
    installed: dict[str, dict[str, Any]] = {}
    site_dir_of: dict[str, Path] = {}
    for site_dir in _site_dirs(venv_root, runtime.get("site_dirs") or []):
        for key, dist in installed_distributions(site_dir).items():
            installed[key] = dist
            site_dir_of[key] = site_dir
    bound_packages = {canonical_distribution_name(item["name"]): item for item in manifest.get("packages") or []}
    for key in sorted(set(installed) - set(bound_packages)):
        failures.append(_failure(R_UNEXPECTED_DISTRIBUTION, name=key, version=installed[key]["version"]))
    for key in sorted(set(bound_packages) - set(installed)):
        failures.append(_failure(R_MISSING_DISTRIBUTION, name=key))
    for key in sorted(set(bound_packages) & set(installed)):
        bound = bound_packages[key]
        if installed[key]["version"] != bound.get("version"):
            failures.append(_failure(R_DISTRIBUTION_VERSION_MISMATCH, name=key, installed=installed[key]["version"],
                                     bound=bound.get("version")))
        elif distribution_manifest_sha256(site_dir_of[key], installed[key]["dist_info"]) != bound.get("installed_manifest_sha256"):
            failures.append(_failure(R_PACKAGE_MANIFEST_MISMATCH, name=key))
    tree_ref = runtime.get("installed_tree_manifest") or {}
    tree_path = _resolve_relative(str(tree_ref.get("path") or ""), manifest_dir) if tree_ref.get("path") else None
    try:
        bound_tree = json.loads(tree_path.read_text(encoding="utf-8")) if tree_path else None
    except (OSError, ValueError):
        bound_tree = None
    if bound_tree is None or canonical_sha256(bound_tree) != tree_ref.get("sha256"):
        failures.append(_failure(R_TREE_MANIFEST_MISMATCH, path=str(tree_path) if tree_path else None))
    else:
        observed_tree = build_installed_tree_manifest(venv_root)
        for kind in ("files", "links"):
            observed = {item["relative_path"]: item for item in observed_tree[kind]}
            bound = {item["relative_path"]: item for item in bound_tree.get(kind) or []}
            for name in sorted(set(observed) | set(bound)):
                if observed.get(name) != bound.get(name):
                    failures.append(_failure(R_INSTALLED_FILE_MISMATCH, path=name,
                                             state="UNEXPECTED" if name not in bound else ("MISSING" if name not in observed else "CHANGED")))
                    if len(failures) > 200:
                        return failures
        for item in observed_tree["links"]:
            target = _norm(item["resolved_target"])
            internal = target.startswith(_norm(venv_root) + os.sep)
            if os.name == "nt" or not (internal or target == _norm(runtime.get("executable_realpath", ""))):
                failures.append(_failure(R_REPARSE_POINT, path=item["relative_path"]))
    failures += _dependency_lock_membership(manifest, manifest_dir)
    failures += worker_source_violations(manifest, producer_root=producer_root, worker_script=worker_script)
    return failures


def _dependency_lock_membership(manifest: Mapping[str, Any], manifest_dir: Path) -> list[dict[str, Any]]:
    ref = manifest.get("dependency_lock") or {}
    path = _resolve_relative(str(ref.get("path") or ""), manifest_dir) if ref.get("path") else None
    try:
        lock, digest = load_dependency_lock(path) if path else (None, None)
    except ProviderBuildManifestError as exc:
        return exc.failures
    if lock is None or digest != ref.get("sha256"):
        return [_failure(R_DEPENDENCY_LOCK_MISMATCH, error="lock digest mismatch")]
    closure = {canonical_distribution_name(item["name"]): item for item in lock["candidate_closure"]["packages"]}
    selected = ref.get("selected_closure")
    if selected == "RUNTIME_MINIMAL_HYPOTHESIS":
        allowed = {canonical_distribution_name(name) for name in lock["runtime_minimal_hypothesis"]["packages"]}
        closure = {key: value for key, value in closure.items() if key in allowed}
    failures = []
    for item in manifest.get("packages") or []:
        key = canonical_distribution_name(item["name"])
        pin = closure.get(key)
        if pin is None or pin.get("version") != item.get("version") or pin.get("artifact_sha256") != item.get("artifact_sha256"):
            failures.append(_failure(R_DEPENDENCY_LOCK_MISMATCH, name=key))
    return failures


def worker_source_violations(
    manifest: Mapping[str, Any], *, producer_root: Path = ROOT, worker_script: Path | None = None,
) -> list[dict[str, Any]]:
    worker = manifest.get("worker") or {}
    failures = []
    if worker_script is not None:
        try:
            relative = Path(os.path.abspath(worker_script)).relative_to(Path(os.path.abspath(producer_root))).as_posix()
        except ValueError:
            relative = None
        if relative != worker.get("entrypoint"):
            failures.append(_failure(R_WORKER_ENTRYPOINT_MISMATCH, requested=str(worker_script), bound=worker.get("entrypoint")))
    for item in worker.get("source_files") or []:
        path = producer_root / item["relative_path"]
        if not path.is_file() or file_identity(path, item["relative_path"]) != dict(item):
            failures.append(_failure(R_WORKER_SOURCE_MISMATCH, path=item["relative_path"]))
    return failures


# ---------------------------------------------------------------------------------------------
# Environment isolation (owner-profile redirection) and filesystem roots.
# ---------------------------------------------------------------------------------------------


def _is_filesystem_root(path: str) -> bool:
    absolute = os.path.abspath(path)
    return os.path.dirname(absolute) == absolute


def owner_denied_roots(parent_environ: Mapping[str, str], *, producer_root: Path = ROOT) -> list[str]:
    """Roots the worker must never read: the owner profile (as seen by the parent environment AND
    this process), its vendor/Stock Lookup state, the producer checkout, the runtime root and the
    secrets file. A filesystem root is never listed (it would deny the interpreter itself)."""
    candidates: list[str] = []
    upper = {str(key).upper(): str(value) for key, value in parent_environ.items()}
    for name in ("USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA"):
        if upper.get(name):
            candidates.append(upper[name])
    if upper.get("HOMEDRIVE") and upper.get("HOMEPATH"):
        candidates.append(upper["HOMEDRIVE"] + upper["HOMEPATH"])
    candidates.append(os.path.expanduser("~"))
    for name in ("STOCK_LOOKUP_RUNTIME_ROOT", "STOCK_LOOKUP_SECRETS_FILE"):
        if upper.get(name):
            candidates.append(upper[name])
    candidates.append(str(producer_root))
    roots: list[str] = []
    for item in candidates:
        if not item or not os.path.isabs(item) or _is_filesystem_root(item):
            continue
        absolute = os.path.abspath(item)
        if _norm(absolute) not in {_norm(root) for root in roots}:
            roots.append(absolute)
    return roots


def build_isolated_worker_environment(
    parent_environ: Mapping[str, str], *, allowed_names: Iterable[str], credential_names: Iterable[str],
    state_root: Path, scratch_tmp: Path, contract_path: Path, extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The worker environment: manifest-allowed operating-system names only, the approved
    credential (if any), and profile/temp names CONSTRUCTED from the provider state/scratch roots --
    never the owner's ``USERPROFILE``/``HOME``/``APPDATA``/``LOCALAPPDATA``/``TEMP``."""
    allowed = {str(name).upper() for name in allowed_names}
    credentials = tuple(str(name).upper() for name in credential_names)
    base = runtime_contract.build_provider_environment(parent_environ, allowed_provider_env=credentials)
    environment = {name: value for name, value in base.items() if name.upper() in allowed or name.upper() in credentials}
    for name, value in (extra or {}).items():
        if name.upper() not in allowed:
            raise runtime_contract.ProviderRuntimeContractError(f"PROVIDER_ENV_EXTRA_NOT_IN_MANIFEST:{name}")
        environment.update(runtime_contract.build_provider_environment({}, extra={name: value}))
    state = os.path.abspath(state_root)
    drive, tail = os.path.splitdrive(state)
    redirected = {
        "USERPROFILE": state, "HOME": state, "HOMEDRIVE": drive, "HOMEPATH": tail or os.sep,
        "APPDATA": os.path.join(state, "AppData", "Roaming"), "LOCALAPPDATA": os.path.join(state, "AppData", "Local"),
        "TEMP": os.path.abspath(scratch_tmp), "TMP": os.path.abspath(scratch_tmp), "TMPDIR": os.path.abspath(scratch_tmp),
    }
    for name in list(environment):
        if name.upper() in redirected:
            del environment[name]
    environment.update(redirected)
    environment[LAUNCH_CONTRACT_ENV] = os.path.abspath(contract_path)
    return environment


def observed_credential_tier(environment: Mapping[str, str], state_root: Path) -> tuple[str, list[str]]:
    """The tier vnai would derive from key PRESENCE in this environment/state root. Never reads the
    key value from the state file (existence only)."""
    sources = []
    if any(str(name).upper() == VENDOR_CREDENTIAL_NAME and str(value) for name, value in environment.items()):
        sources.append("ENV")
    if (Path(state_root) / VENDOR_CREDENTIAL_STATE_FILE).exists():
        sources.append("STATE_FILE")
    return (TIER_FREE if sources else TIER_GUEST), sources


def credential_launch_violations(
    manifest: Mapping[str, Any], *, parent_environ: Mapping[str, str], state_root: Path,
    configured_governor_rpm: int | None = None,
) -> list[dict[str, Any]]:
    """Launch-time check of the approved credential mechanism against what is actually available."""
    credential = manifest.get("vendor_credential") or {}
    binding = manifest.get("rate_tier_binding") or {}
    failures = rate_binding_violations(binding, credential)
    if failures:
        return failures
    mechanism = credential["mechanism"]
    upper = {str(name).upper(): str(value) for name, value in parent_environ.items()}
    state_file = Path(state_root) / VENDOR_CREDENTIAL_STATE_FILE
    if mechanism == CREDENTIAL_APPROVED_ENV_NAME:
        value = upper.get(VENDOR_CREDENTIAL_NAME, "")
        if not value.strip():
            failures.append(_failure(R_CREDENTIAL_REQUIRED_ABSENT, name=VENDOR_CREDENTIAL_NAME))
        elif _PLACEHOLDER_CREDENTIAL_RE.match(value.strip()):
            failures.append(_failure(R_CREDENTIAL_PLACEHOLDER, name=VENDOR_CREDENTIAL_NAME))
        if state_file.exists():
            failures.append(_failure(R_CREDENTIAL_NOT_APPROVED_PRESENT, source="STATE_FILE"))
    elif mechanism == CREDENTIAL_APPROVED_STATE_FILE:
        if not state_file.is_file() or state_file.stat().st_size == 0:
            failures.append(_failure(R_CREDENTIAL_REQUIRED_ABSENT, source="STATE_FILE"))
    else:  # NONE -> guest: no key may be discoverable, neither forwarded nor in the state root
        if state_file.exists():
            failures.append(_failure(R_TIER_MISMATCH, error="guest tier but a key file exists in the provider state root"))
    if configured_governor_rpm is not None and configured_governor_rpm > binding["governor_effective_rpm"]:
        failures.append(_failure(R_GOVERNOR_EXCEEDS_APPROVED, configured=configured_governor_rpm,
                                 approved=binding["governor_effective_rpm"]))
    return failures


# ---------------------------------------------------------------------------------------------
# Launch authorization (parent) -- the only way to obtain a spawnable provider launch.
# ---------------------------------------------------------------------------------------------

_LAUNCH_ISSUER = object()


@dataclass(frozen=True)
class ProviderLaunchAuthorization:
    """An attested, single-use provider worker launch. Only ``authorize_provider_launch`` makes one."""

    build_id: str
    manifest_sha256: str
    manifest: Mapping[str, Any]
    launch_id: str
    launch_mode: str
    revocation_epoch: int
    registry_path: str
    interpreter: str
    argv: tuple[str, ...]
    worker_script: str
    bundle_root: str
    scratch_root: str
    state_root: str
    cwd: str
    environment: Mapping[str, str]
    contract_path: str
    governor_rpm: int
    tier: str
    policy: runtime_contract.ProviderPolicy
    attestation: Mapping[str, Any]
    _issuer: object = field(default=None, repr=False, compare=False)
    _state: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def issued_by_attestation(self) -> bool:
        return self._issuer is _LAUNCH_ISSUER

    def consume(self) -> None:
        """Single use: one attested launch spawns exactly one worker process."""
        if self._state.get("consumed"):
            raise runtime_contract.ProviderRuntimeContractError("PROVIDER_LAUNCH_AUTHORIZATION_ALREADY_USED")
        self._state["consumed"] = True

    def revocation_monitor(self) -> RevocationMonitor:
        return RevocationMonitor(self.manifest, self.manifest_sha256, self.registry_path)

    def identity(self) -> dict[str, Any]:
        return {
            "build_id": self.build_id, "manifest_sha256": self.manifest_sha256, "launch_id": self.launch_id,
            "launch_mode": self.launch_mode, "revocation_epoch": self.revocation_epoch, "tier": self.tier,
            "governor_effective_rpm": self.governor_rpm, "authority_effect": AUTHORITY_EFFECT,
        }

    def cleanup(self) -> None:
        """Delete this launch's scratch root (bundle, contract, temp). The state root persists."""
        shutil.rmtree(self.scratch_root, ignore_errors=True)


def _approval_violations(manifest: Mapping[str, Any], policy: runtime_contract.ProviderPolicy, digest: str,
                         now: datetime, launch_mode: str) -> list[dict[str, Any]]:
    failures = []
    if manifest.get("status") != STATUS_APPROVED:
        failures.append(_failure(R_NOT_APPROVED, status=manifest.get("status")))
    if manifest.get("launch_authorized") is not True:
        failures.append(_failure(R_LAUNCH_NOT_AUTHORIZED))
    if manifest.get("provider_family") != policy.provider_family:
        failures.append(_failure(R_POLICY_IDENTITY_MISMATCH, error="provider family"))
    approval = manifest.get("approval") or {}
    required = ("owner_id", "decision_id", "policy_decision_id", "approved_at_utc", "expires_at_utc", "evidence_bundle_sha256")
    if any(not approval.get(key) for key in required):
        failures.append(_failure(R_APPROVAL_INCOMPLETE))
    else:
        approved_at, expires_at = _parse_utc(approval["approved_at_utc"]), _parse_utc(approval["expires_at_utc"])
        if approved_at is None or expires_at is None:
            failures.append(_failure(R_APPROVAL_INCOMPLETE, error="timestamps"))
        elif now < approved_at:
            failures.append(_failure(R_APPROVAL_NOT_YET_VALID))
        elif now >= expires_at:
            failures.append(_failure(R_APPROVAL_EXPIRED, expires_at_utc=approval["expires_at_utc"]))
        if policy.decision_id != approval.get("policy_decision_id"):
            failures.append(_failure(R_POLICY_IDENTITY_MISMATCH, error="policy decision id"))
    mode = (manifest.get("launch_mode") or {}).get("mode")
    if mode != launch_mode:
        failures.append(_failure(R_LAUNCH_MODE_MISMATCH, requested=launch_mode, bound=mode))
    if launch_mode == LAUNCH_MODE_ORDINARY_DAILY and not _is_sha256(manifest.get("qualification_evidence_sha256")):
        failures.append(_failure(R_DAILY_WITHOUT_QUALIFICATION))
    terms = manifest.get("terms_acceptance") or {}
    if terms.get("agreement_file_policy") != TERMS_PREPROVISIONED or not terms.get("owner_decision_id") \
            or not _is_sha256(terms.get("terms_text_sha256")):
        failures.append(_failure(R_TERMS_UNRESOLVED))
    return failures


def authorize_provider_launch(
    *,
    policy: runtime_contract.ProviderPolicy,
    configured_executable: str,
    parent_environ: Mapping[str, str],
    launch_mode: str = LAUNCH_MODE_ORDINARY_DAILY,
    manifest_path: Path | str | None = None,
    registry_path: Path | str | None = None,
    worker_script: Path | str | None = None,
    extra_env: Mapping[str, str] | None = None,
    producer_root: Path = ROOT,
    now: datetime | None = None,
    configured_governor_rpm: int | None = None,
    schema_path: Path | None = None,
    probe_timeout: float = 20.0,
) -> ProviderLaunchAuthorization:
    """Verify everything that can be verified without running provider code, then stage the launch.

    Raises ``ProviderBuildManifestError``/``ProviderAttestationError`` (never spawns, never falls
    back, never installs, never widens egress). Must be called only after the owner policy allows
    launch (``open_provider_runtime`` checks that first).
    """
    if launch_mode not in LAUNCH_MODES:
        raise ProviderAttestationError(R_LAUNCH_MODE_MISMATCH, [_failure(R_LAUNCH_MODE_MISMATCH, requested=launch_mode)])
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    pinned_path = manifest_path if manifest_path is not None else (
        _resolve_relative(policy.approved_manifest_path, producer_root) if policy.approved_manifest_path else None)
    if pinned_path is None or not _is_sha256(policy.approved_manifest_sha256) or not policy.decision_id:
        raise ProviderAttestationError(R_POLICY_PIN_ABSENT, [_failure(R_POLICY_PIN_ABSENT)])
    manifest, digest = load_manifest(pinned_path, schema_path=schema_path)
    if digest != policy.approved_manifest_sha256:
        raise ProviderAttestationError(R_POLICY_DIGEST_MISMATCH, [_failure(R_POLICY_DIGEST_MISMATCH, manifest=digest,
                                                                           pinned=policy.approved_manifest_sha256)])
    failures = _approval_violations(manifest, policy, digest, now, launch_mode)
    if failures:
        raise ProviderAttestationError(failures[0]["code"], failures)
    registry_file = Path(registry_path) if registry_path is not None else REVOCATION_REGISTRY_PATH
    status = revocation_status(manifest, digest, load_revocation_registry(registry_file))
    if status.revoked:
        raise ProviderAttestationError(status.reason_code or R_REVOKED, [_failure(status.reason_code or R_REVOKED, **status.to_record())])
    filesystem = manifest["filesystem"]
    state_root = Path(filesystem["provider_state_root"])
    failures = credential_launch_violations(manifest, parent_environ=parent_environ, state_root=state_root,
                                            configured_governor_rpm=configured_governor_rpm)
    terms_file = state_root / str((manifest.get("terms_acceptance") or {}).get("agreement_file_relative_path") or "")
    if not terms_file.is_file():
        failures.append(_failure(R_TERMS_NOT_PREPROVISIONED, path=str(terms_file)))
    if failures:
        raise ProviderAttestationError(failures[0]["code"], failures)
    manifest_dir = Path(pinned_path).resolve().parent
    script = Path(worker_script) if worker_script is not None else producer_root / manifest["worker"]["entrypoint"]
    failures = attest_runtime_static(manifest, configured_executable=configured_executable, manifest_dir=manifest_dir,
                                     producer_root=producer_root, worker_script=script)
    if failures:
        raise ProviderAttestationError(failures[0]["code"], failures)

    launch_id = uuid.uuid4().hex
    scratch_root = Path(filesystem["provider_scratch_base"]) / f"launch-{launch_id}"
    bundle_root, scratch_tmp, cwd = scratch_root / "bundle", scratch_root / "tmp", scratch_root / "cwd"
    contract_path = scratch_root / "launch_contract.json"
    credential = manifest["vendor_credential"]
    credential_names = [VENDOR_CREDENTIAL_NAME] if credential["mechanism"] == CREDENTIAL_APPROVED_ENV_NAME else []
    environment = build_isolated_worker_environment(
        parent_environ, allowed_names=manifest["environment"]["allowed_names"], credential_names=credential_names,
        state_root=state_root, scratch_tmp=scratch_tmp, contract_path=contract_path, extra=extra_env,
    )
    runtime = manifest["runtime"]
    probe_env = {name: value for name, value in environment.items() if name != LAUNCH_CONTRACT_ENV}
    try:
        probe = probe_interpreter(configured_executable, env=probe_env, timeout=probe_timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderAttestationError(R_PROBE_FAILED, [_failure(R_PROBE_FAILED, error=type(exc).__name__)]) from None
    for key in ("python_version", "python_build", "implementation", "pointer_bits", "platform"):
        if probe.get(key) != runtime.get(key):
            raise ProviderAttestationError(R_PYTHON_BUILD_MISMATCH, [_failure(R_PYTHON_BUILD_MISMATCH, field=key)])

    for directory in (state_root, state_root / "AppData" / "Roaming", state_root / "AppData" / "Local"):
        directory.mkdir(parents=True, exist_ok=True)
    scratch_root.mkdir(parents=True, exist_ok=False)
    for directory in (bundle_root, scratch_tmp, cwd):
        directory.mkdir()
    try:
        for item in manifest["worker"]["source_files"]:
            target = bundle_root / item["relative_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(producer_root / item["relative_path"], target)
            if file_identity(target, item["relative_path"]) != dict(item):
                raise ProviderAttestationError(R_WORKER_SOURCE_MISMATCH, [_failure(R_WORKER_SOURCE_MISMATCH, path=item["relative_path"])])
        bundled_manifest = bundle_root / BUNDLED_MANIFEST_RELATIVE_PATH
        bundled_manifest.parent.mkdir(parents=True, exist_ok=True)
        bundled_manifest.write_bytes(canonical_json_bytes(manifest))
        denied = owner_denied_roots(parent_environ, producer_root=producer_root)
        read_only = [runtime["venv_root"], runtime["base_prefix"], str(bundle_root)]
        writable = [str(state_root), str(scratch_root)]
        entrypoint = bundle_root / manifest["worker"]["entrypoint"]
        rate = manifest["rate_tier_binding"]
        contract = {
            "contract_version": LAUNCH_CONTRACT_VERSION, "launch_id": launch_id, "build_id": manifest["build_id"],
            "manifest_sha256": digest, "manifest_bundle_path": BUNDLED_MANIFEST_RELATIVE_PATH,
            "provider_family": manifest["provider_family"], "launch_mode": launch_mode,
            "revocation_epoch": status.epoch,
            "interpreter": {
                "executable_path": runtime["executable_path"], "executable_sha256": runtime["executable_sha256"],
                "venv_root": runtime["venv_root"], "base_prefix": runtime["base_prefix"],
                "python_version": runtime["python_version"], "python_build": runtime["python_build"],
                "implementation": runtime["implementation"], "pointer_bits": runtime["pointer_bits"],
                "platform": runtime["platform"], "site_dirs": runtime["site_dirs"],
                "startup_hook_files": runtime["startup_hook_files"],
            },
            "worker": {
                "entrypoint": manifest["worker"]["entrypoint"], "adapter_module": manifest["worker"]["adapter_module"],
                "protocol_version": manifest["worker"]["protocol_version"], "argv_flags": manifest["worker"]["argv_flags"],
                "source_files": manifest["worker"]["source_files"], "startup_stubs": manifest["worker"]["startup_stubs"],
                "lineage_endpoint_map": manifest["worker"]["lineage_endpoint_map"],
            },
            "roots": {
                "bundle_root": str(bundle_root), "scratch_root": str(scratch_root), "cwd": str(cwd),
                "state_root": str(state_root), "denied_roots": denied, "read_only_roots": read_only,
                "writable_roots": writable,
            },
            "network": {
                "endpoints": [dict(item) for item in manifest["network"]["endpoints"]]
                + [telemetry_endpoint_rule(item) for item in manifest["telemetry_disposition"]
                   if item.get("decision") == TELEMETRY_ALLOW and item.get("layer") == "NETWORK"],
                "egress_gateway": manifest["network"].get("egress_gateway"),
                "expected_denied_hosts": sorted({str(item["host"]).lower() for item in manifest["telemetry_disposition"]
                                                 if item.get("decision") == TELEMETRY_DENY and item.get("layer") == "NETWORK"}),
                "expected_denied_processes": sorted({str(item["process"]).lower() for item in manifest["telemetry_disposition"]
                                                     if item.get("decision") == TELEMETRY_DENY and item.get("layer") == "PROCESS"}),
            },
            "credential": {"mechanism": credential["mechanism"], "credential_name": credential.get("credential_name"),
                           "expected_tier": credential["expected_vnai_tier"]},
            "rate": {"governor_effective_rpm": rate["governor_effective_rpm"], "tier_limits": rate["tier_limits"],
                     "planned_session_request_budget": rate["planned_session_request_budget"]},
            "environment": {"allowed_names": sorted({*(str(n).upper() for n in manifest["environment"]["allowed_names"]),
                                                     *credential_names, *REDIRECTED_PROFILE_NAMES, "TMPDIR", LAUNCH_CONTRACT_ENV})},
            "terms_agreement_relative_path": manifest["terms_acceptance"].get("agreement_file_relative_path"),
            "authority_effect": AUTHORITY_EFFECT,
        }
        contract_path.write_bytes(canonical_json_bytes(contract))
    except BaseException:
        shutil.rmtree(scratch_root, ignore_errors=True)
        raise
    argv = (configured_executable, *runtime_contract.WORKER_INTERPRETER_FLAGS, str(entrypoint))
    return ProviderLaunchAuthorization(
        build_id=manifest["build_id"], manifest_sha256=digest, manifest=manifest, launch_id=launch_id,
        launch_mode=launch_mode, revocation_epoch=int(status.epoch or 0), registry_path=str(registry_file),
        interpreter=configured_executable, argv=argv, worker_script=str(entrypoint), bundle_root=str(bundle_root),
        scratch_root=str(scratch_root), state_root=str(state_root), cwd=str(cwd), environment=environment,
        contract_path=str(contract_path), governor_rpm=int(rate["governor_effective_rpm"]),
        tier=credential["expected_vnai_tier"], policy=policy,
        attestation={"static_checks": "PASS", "probe": probe, "denied_roots": denied, "manifest_sha256": digest},
        _issuer=_LAUNCH_ISSUER,
    )


# ---------------------------------------------------------------------------------------------
# Worker self-attestation (runs inside the provider worker, before any provider discovery).
# ---------------------------------------------------------------------------------------------


def read_launch_contract(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    environ = os.environ if environ is None else environ
    raw_path = environ.get(LAUNCH_CONTRACT_ENV)
    if not raw_path:
        raise ProviderAttestationError(R_CONTRACT_ABSENT, [_failure(R_CONTRACT_ABSENT)])
    try:
        contract = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProviderAttestationError(R_CONTRACT_INVALID, [_failure(R_CONTRACT_INVALID, error=type(exc).__name__)]) from None
    if not isinstance(contract, dict) or contract.get("contract_version") != LAUNCH_CONTRACT_VERSION:
        raise ProviderAttestationError(R_CONTRACT_INVALID, [_failure(R_CONTRACT_INVALID, error="contract_version")])
    return contract


def _forms(path: Any) -> set[str]:
    text = os.fspath(path)
    return {os.path.normcase(os.path.abspath(text)), os.path.normcase(os.path.realpath(text))}


def _under(path: Any, root: Any) -> bool:
    """``path`` equals or lies below ``root``, comparing both absolute and resolved forms."""
    if not path or not root:
        return False
    return any(candidate == base or candidate.startswith(base.rstrip("\\/") + os.sep)
               for candidate in _forms(path) for base in _forms(root))


def _same_path(left: Any, right: Any) -> bool:
    return bool(left) and bool(right) and bool(_forms(left) & _forms(right))


def self_attest_worker(
    contract: Mapping[str, Any], *, protocol_version: str, entrypoint_file: str,
) -> list[dict[str, Any]]:
    """Every in-worker check; empty list = attested. Stdlib only, no provider discovery."""
    import platform
    import site
    import struct

    failures: list[dict[str, Any]] = []
    interpreter = contract.get("interpreter") or {}
    worker = contract.get("worker") or {}
    roots = contract.get("roots") or {}
    flags = sys.flags
    if not (flags.no_user_site and flags.ignore_environment and flags.dont_write_bytecode and flags.utf8_mode):
        failures.append(_failure(R_FLAGS_MISMATCH, no_user_site=flags.no_user_site, ignore_environment=flags.ignore_environment,
                                 dont_write_bytecode=flags.dont_write_bytecode, utf8_mode=flags.utf8_mode))
    if site.ENABLE_USER_SITE:
        failures.append(_failure(R_USER_SITE_ENABLED))
    if not _same_path(sys.prefix, interpreter.get("venv_root")) or not _same_path(sys.base_prefix, interpreter.get("base_prefix")) \
            or sys.prefix == sys.base_prefix:
        failures.append(_failure(R_VENV_MISMATCH, prefix=sys.prefix, base_prefix=sys.base_prefix))
    executable = sys.executable or ""
    if not _same_path(executable, interpreter.get("executable_path")) or not os.path.isfile(executable) \
            or sha256_file(executable) != interpreter.get("executable_sha256"):
        failures.append(_failure(R_INTERPRETER_MISMATCH, executable=executable))
    observed_build = {"python_version": platform.python_version(), "python_build": sys.version,
                      "implementation": sys.implementation.name, "pointer_bits": struct.calcsize("P") * 8,
                      "platform": sys.platform}
    for key, value in observed_build.items():
        if interpreter.get(key) != value:
            failures.append(_failure(R_PYTHON_BUILD_MISMATCH, field=key))
    allowed_path_roots = [roots.get("bundle_root", ""), interpreter.get("base_prefix", ""), interpreter.get("venv_root", "")]
    for entry in sys.path:
        if not entry or not any(root and _under(entry, root) for root in allowed_path_roots):
            failures.append(_failure(R_SYS_PATH_CONTAMINATED, entry=entry))
    venv_root = Path(interpreter.get("venv_root", "."))
    expected_site = sorted(os.path.normcase(os.path.realpath(path)) for path in _site_dirs(venv_root, interpreter.get("site_dirs") or []))
    if sorted(os.path.normcase(os.path.realpath(path)) for path in site.getsitepackages()) != expected_site:
        failures.append(_failure(R_VENV_MISMATCH, error="site directories"))
    hooks = startup_hook_inventory(venv_root, interpreter.get("site_dirs") or [])
    if hooks != sorted([dict(item) for item in interpreter.get("startup_hook_files") or []], key=lambda item: item["relative_path"]):
        failures.append(_failure(R_STARTUP_HOOK_UNEXPECTED))
    approved_hook_modules = {Path(item["relative_path"]).stem.lower() for item in interpreter.get("startup_hook_files") or []}
    for module in ("sitecustomize", "usercustomize"):
        if module in sys.modules and module not in approved_hook_modules:
            failures.append(_failure(R_STARTUP_HOOK_LOADED, module=module))
    if worker.get("protocol_version") != protocol_version:
        failures.append(_failure(R_PROTOCOL_MISMATCH, bound=worker.get("protocol_version"), running=protocol_version))
    bundle_root = Path(roots.get("bundle_root", "."))
    if not _same_path(entrypoint_file, bundle_root / str(worker.get("entrypoint"))):
        failures.append(_failure(R_WORKER_ENTRYPOINT_MISMATCH, running=entrypoint_file))
    for item in worker.get("source_files") or []:
        path = bundle_root / item["relative_path"]
        if not path.is_file() or file_identity(path, item["relative_path"]) != dict(item):
            failures.append(_failure(R_WORKER_SOURCE_MISMATCH, path=item["relative_path"]))
    bundled_manifest = bundle_root / str(contract.get("manifest_bundle_path"))
    try:
        if manifest_digest(json.loads(bundled_manifest.read_text(encoding="utf-8"))) != contract.get("manifest_sha256"):
            failures.append(_failure(R_MANIFEST_DIGEST_MISMATCH))
    except (OSError, ValueError):
        failures.append(_failure(R_MANIFEST_DIGEST_MISMATCH, error="bundled manifest unreadable"))
    allowed_names = {str(name).upper() for name in (contract.get("environment") or {}).get("allowed_names") or []}
    for name in sorted(os.environ):
        upper = name.upper()
        if runtime_contract.is_denied_family(upper) or upper.startswith("FHSC_") or upper in REQUIRED_FORBIDDEN_NAMES:
            failures.append(_failure(R_DENIED_CREDENTIAL_PRESENT, name=name))
        elif upper not in allowed_names:
            failures.append(_failure(R_ENV_UNEXPECTED_NAME, name=name))
    state_root, scratch_root = roots.get("state_root", ""), roots.get("scratch_root", "")
    for name in ("USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA"):
        if not _under(os.environ.get(name, ""), state_root):
            failures.append(_failure(R_PROFILE_NOT_REDIRECTED, name=name))
    for name in ("TEMP", "TMP"):
        if not _under(os.environ.get(name, ""), scratch_root):
            failures.append(_failure(R_PROFILE_NOT_REDIRECTED, name=name))
    if not _under(str(Path.home()), state_root):
        failures.append(_failure(R_PROFILE_NOT_REDIRECTED, name="Path.home()"))
    for root in roots.get("denied_roots") or []:
        if _under(str(Path.home()), root) and not _under(str(Path.home()), state_root):
            failures.append(_failure(R_PROFILE_NOT_REDIRECTED, denied_root=root))
    credential = contract.get("credential") or {}
    tier, sources = observed_credential_tier(os.environ, Path(state_root))
    if tier != credential.get("expected_tier"):
        failures.append(_failure(R_TIER_MISMATCH, expected=credential.get("expected_tier"), observed=tier, sources=sources))
    if credential.get("mechanism") == CREDENTIAL_NONE and sources:
        failures.append(_failure(R_CREDENTIAL_NOT_APPROVED_PRESENT, sources=sources))
    if not _same_path(os.getcwd(), roots.get("cwd")):
        failures.append(_failure(R_CWD_MISMATCH, cwd=os.getcwd()))
    loaded = sorted(name for name in sys.modules if name.split(".", 1)[0] in PROVIDER_DISTRIBUTIONS)
    if loaded:
        failures.append(_failure(R_PROVIDER_LOADED_EARLY, modules=loaded[:10]))
    return failures


def worker_containment_from_contract(contract: Mapping[str, Any]):
    """The ``provider_worker_containment.WorkerContainment`` the launch contract describes."""
    import provider_worker_containment as containment

    network = contract.get("network") or {}
    roots = contract.get("roots") or {}
    return containment.WorkerContainment(
        egress=containment.EgressPolicy.from_endpoints(network.get("endpoints") or [], gateway=network.get("egress_gateway")),
        filesystem=containment.FilesystemPolicy(
            denied_roots=tuple(roots.get("denied_roots") or ()), read_only_roots=tuple(roots.get("read_only_roots") or ()),
            writable_roots=tuple(roots.get("writable_roots") or ()),
        ),
        expected_network_denials=network.get("expected_denied_hosts") or (),
        expected_process_denials=network.get("expected_denied_processes") or (),
    )


def refresh_draft_identities(
    *, manifest_path: Path | str | None = None, lock_path: Path | str | None = None, producer_root: Path = ROOT,
) -> dict[str, Any]:
    """Rewrite worker-source hashes and the dependency-lock digest on the tracked DRAFT manifest.

    Refuses to run against any non-DRAFT / launch-authorised file. Never inserts an approval.
    """
    path = Path(manifest_path) if manifest_path is not None else MANIFEST_PATH
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProviderBuildManifestError(R_MANIFEST_MALFORMED, [_failure(R_MANIFEST_MALFORMED, error=type(exc).__name__)]) from None
    if not isinstance(manifest, dict) or manifest.get("status") != STATUS_DRAFT or manifest.get("launch_authorized") is not False:
        raise ProviderBuildManifestError(
            R_MANIFEST_CONTRACT_INVALID,
            [_failure(R_MANIFEST_CONTRACT_INVALID, error="refresh is only defined for a DRAFT, launch_authorized=false manifest")],
        )
    worker = dict(manifest.get("worker") or {})
    worker["source_files"] = [file_identity(producer_root / relative, relative) for relative in WORKER_SOURCE_FILES]
    worker["entrypoint"] = WORKER_ENTRYPOINT
    worker["adapter_module"] = WORKER_ADAPTER_MODULE
    worker["startup_stubs"] = [dict(item) for item in WORKER_STARTUP_STUBS]
    worker["lineage_endpoint_map"] = dict(LINEAGE_ENDPOINT_MAP)
    manifest["worker"] = worker
    lock, digest = load_dependency_lock(Path(lock_path) if lock_path is not None else producer_root / "config" / "provider_dependency_lock.json")
    ref = dict(manifest.get("dependency_lock") or {})
    ref["path"] = ref.get("path") or "config/provider_dependency_lock.json"
    ref["selected_closure"] = ref.get("selected_closure") or "UNRESOLVED"
    ref["sha256"] = digest
    manifest["dependency_lock"] = ref
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "path": str(path), "status": STATUS_DRAFT, "launch_authorized": False,
        "worker_source_files": worker["source_files"], "dependency_lock_sha256": digest,
        "lock_package_count": (lock.get("candidate_closure") or {}).get("count"),
    }
