"""Verify the dependency-tier split and the deterministic core/test constraints.

Read-only. Checks the tracked dependency surfaces:

* ``requirements.txt``            -- CORE runtime (hermetic core / CI tier)
* ``requirements-test.txt``       -- CORE test
* ``requirements-providers.txt``  -- OPTIONAL provider runtime (vnstock/vnai, anthropic)
* ``constraints.txt``             -- exact pins for the core + test closure

    python tools/verify_dependency_tiers.py              static checks of the tracked files
    python tools/verify_dependency_tiers.py --installed  also check the active environment:
                                                         the installed core/test closure matches
                                                         constraints.txt exactly, and no provider
                                                         package is importable

Exit 0 = no violation. Each violation prints one ``CODE: detail`` line.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CORE_REQUIREMENTS = "requirements.txt"
TEST_REQUIREMENTS = "requirements-test.txt"
PROVIDER_REQUIREMENTS = "requirements-providers.txt"
CONSTRAINTS = "constraints.txt"
PROVIDER_LOCK = "config/provider_dependency_lock.json"
PROVIDER_MANIFEST = "config/provider_build_manifest.json"

# Distributions that must stay out of the core/test tier. vnai is never declared directly
# (it arrives with vnstock) but must not leak into core either.
PROVIDER_DISTRIBUTIONS = frozenset({"vnstock", "vnai", "anthropic"})
# Provider packages that currently have no installable distribution and must never be required
# by, or importable in, hermetic CI.
BLOCKED_PROVIDER_MODULES = ("vnstock", "vnai")
# Tooling that bootstraps the environment rather than belonging to the dependency closure.
_BOOTSTRAP_DISTRIBUTIONS = frozenset({"pip", "setuptools", "wheel"})

_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)$")


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _logical_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def parse_requirement_names(text: str) -> list[str]:
    """Canonical distribution names declared in a requirements file (options are rejected)."""
    names = []
    for line in _logical_lines(text):
        if line.startswith("-"):
            raise ValueError(f"requirements option lines are not supported here: {line!r}")
        match = _NAME_RE.match(line)
        if not match:
            raise ValueError(f"unparseable requirement line: {line!r}")
        names.append(canonical_name(match.group(1)))
    return names


def parse_constraints(text: str) -> dict[str, str]:
    """``{canonical name: exact version}``; every line must be an exact ``name==version`` pin."""
    pins: dict[str, str] = {}
    for line in _logical_lines(text):
        match = _PIN_RE.match(line)
        if not match:
            raise ValueError(f"constraints.txt line is not an exact name==version pin: {line!r}")
        name = canonical_name(match.group(1))
        if name in pins:
            raise ValueError(f"duplicate constraint for {name}")
        pins[name] = match.group(2)
    return pins


def static_violations(
    core_text: str, test_text: str, provider_text: str, constraints_text: str,
) -> list[str]:
    violations: list[str] = []
    try:
        core = parse_requirement_names(core_text)
        test = parse_requirement_names(test_text)
        providers = parse_requirement_names(provider_text)
        pins = parse_constraints(constraints_text)
    except ValueError as exc:
        return [f"DEPENDENCY_FILE_UNPARSEABLE: {exc}"]
    for tier, names in (("requirements.txt", core), ("requirements-test.txt", test)):
        for name in sorted(set(names) & PROVIDER_DISTRIBUTIONS):
            violations.append(f"PROVIDER_PACKAGE_IN_CORE_TIER: {name} is declared in {tier}")
        for name in names:
            if name not in pins:
                violations.append(f"CORE_REQUIREMENT_NOT_PINNED: {name} ({tier}) has no exact pin in constraints.txt")
    if "vnstock" not in providers:
        violations.append("PROVIDER_REQUIREMENT_UNDECLARED: vnstock must stay declared in requirements-providers.txt")
    for name in sorted(set(providers) - PROVIDER_DISTRIBUTIONS):
        violations.append(f"UNCLASSIFIED_PROVIDER_REQUIREMENT: {name} is not a known provider distribution")
    for name in sorted(set(pins) & PROVIDER_DISTRIBUTIONS):
        violations.append(f"PROVIDER_PACKAGE_CONSTRAINED: {name} must not be pinned in constraints.txt")
    return violations


def provider_lock_violations(root: Path) -> list[str]:
    """Candidate provider lock vs tracked DRAFT manifest vs core/provider separation."""
    sys.path.insert(0, str(root))
    import provider_build_manifest as build_manifest  # local import: this file is also imported by tests

    violations: list[str] = []
    lock_path = root / PROVIDER_LOCK
    manifest_path = root / PROVIDER_MANIFEST
    if not lock_path.is_file():
        return [f"PROVIDER_LOCK_ABSENT: {PROVIDER_LOCK} is required as a candidate contract"]
    try:
        lock, digest = build_manifest.load_dependency_lock(lock_path)
    except build_manifest.ProviderBuildManifestError as exc:
        return [f"PROVIDER_LOCK_INVALID: {exc.reason_code}"]
    if lock.get("approval_state") == "APPROVED":
        violations.append("PROVIDER_LOCK_MARKED_APPROVED: the candidate lock must not be an approval")
    names = {build_manifest.canonical_distribution_name(item["name"]) for item in lock["candidate_closure"]["packages"]}
    if "anthropic" in names:
        violations.append("PROVIDER_LOCK_CONTAINS_ANTHROPIC: anthropic is not a governed-worker dependency")
    for name in ("vnstock", "vnai"):
        if name not in names:
            violations.append(f"PROVIDER_LOCK_MISSING_PROVIDER: {name}")
    if not manifest_path.is_file():
        violations.append(f"PROVIDER_BUILD_MANIFEST_ABSENT: {PROVIDER_MANIFEST}")
        return violations
    try:
        manifest, _ = build_manifest.load_manifest(manifest_path)
    except build_manifest.ProviderBuildManifestError as exc:
        violations.append(f"PROVIDER_BUILD_MANIFEST_INVALID: {exc.reason_code}")
        return violations
    if manifest.get("status") == build_manifest.STATUS_APPROVED or manifest.get("launch_authorized") is True:
        violations.append("PROVIDER_BUILD_MANIFEST_APPROVED: tracked manifest must remain DRAFT / launch_authorized=false")
    ref = manifest.get("dependency_lock") or {}
    if ref.get("sha256") != digest:
        violations.append("PROVIDER_MANIFEST_LOCK_DIGEST_MISMATCH: refresh DRAFT worker/lock identities")
    if ref.get("path") not in (PROVIDER_LOCK, str(lock_path)):
        violations.append(f"PROVIDER_MANIFEST_LOCK_PATH_UNEXPECTED: {ref.get('path')}")
    return violations


def _requirement_closure(roots: list[str]) -> dict[str, str]:
    """Installed ``{canonical name: version}`` reachable from ``roots`` (markers evaluated)."""
    from packaging.requirements import Requirement  # installed with pytest; pinned in constraints

    closure: dict[str, str] = {}
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            closure[name] = ""
            continue
        closure[name] = dist.version
        for raw in dist.requires or ():
            req = Requirement(raw)
            if req.marker is not None and not req.marker.evaluate({"extra": ""}):
                continue
            pending.append(canonical_name(req.name))
    return closure


def installed_violations(roots: list[str], pins: dict[str, str]) -> list[str]:
    violations: list[str] = []
    for name, version in sorted(_requirement_closure(roots).items()):
        if name in _BOOTSTRAP_DISTRIBUTIONS:
            continue
        if not version:
            violations.append(f"CORE_DISTRIBUTION_NOT_INSTALLED: {name}")
        elif name not in pins:
            violations.append(f"INSTALLED_DISTRIBUTION_NOT_PINNED: {name}=={version} is in the core/test closure but not in constraints.txt")
        elif pins[name] != version:
            violations.append(f"INSTALLED_VERSION_DRIFT: {name}=={version}, constraints.txt pins {pins[name]}")
    for module in BLOCKED_PROVIDER_MODULES:
        try:
            available = importlib.util.find_spec(module) is not None
        except ImportError:  # the hermetic provider-import block
            available = False
        if available:
            violations.append(f"PROVIDER_MODULE_IMPORTABLE_IN_CORE_TIER: {module}")
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--installed", action="store_true", help="also verify the active environment")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root: Path = args.root
    texts = {
        name: (root / name).read_text(encoding="utf-8")
        for name in (CORE_REQUIREMENTS, TEST_REQUIREMENTS, PROVIDER_REQUIREMENTS, CONSTRAINTS)
    }
    violations = static_violations(
        texts[CORE_REQUIREMENTS], texts[TEST_REQUIREMENTS], texts[PROVIDER_REQUIREMENTS], texts[CONSTRAINTS],
    )
    if (root / PROVIDER_LOCK).is_file() or (root / PROVIDER_MANIFEST).is_file():
        violations.extend(provider_lock_violations(root))
    if args.installed and not violations:
        roots = parse_requirement_names(texts[CORE_REQUIREMENTS]) + parse_requirement_names(texts[TEST_REQUIREMENTS])
        violations = installed_violations(roots, parse_constraints(texts[CONSTRAINTS]))
    for line in violations:
        print(line)
    print(f"DEPENDENCY_TIERS: {'FAIL' if violations else 'PASS'} ({len(violations)} violation(s))")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
