"""Explicit test tiers: hermetic core, retained-evidence verification, provider runtime.

Stock Lookup's test suite mixes three kinds of tests that need different environments:

* **Hermetic core tier** -- unit, synthetic-contract and tracked-fixture tests. They run from a
  clean GitHub clone with only the core dependencies (``requirements.txt`` +
  ``requirements-test.txt`` under ``constraints.txt``). This is every test that carries neither
  marker below.
* **Retained-evidence tier** -- ``@pytest.mark.retained_evidence("<repo-relative path>", ...)``.
  The test replays governed local retained evidence (``operations-review/``, ``data/``) that is
  gitignored and therefore absent from a clean clone. The marker names every evidence path the
  test needs, so the dependency is declared rather than discovered by a ``FileNotFoundError``.
* **Provider-runtime tier** -- ``@pytest.mark.provider_runtime("<module>", ...)``. The test
  needs a real optional provider package from ``requirements-providers.txt`` (``vnstock`` /
  ``vnai``) to be importable.

Missing retained evidence is governed by ``STOCKLOOKUP_RETAINED_EVIDENCE_POLICY``:

* ``strict`` (default, the owner's local acceptance workflow) -- a missing path fails the test
  with ``RETAINED_EVIDENCE_REQUIRED`` naming the path. Nothing is silently skipped.
* ``skip-if-absent`` (clean-clone CI) -- a missing path skips the test with
  ``RETAINED_EVIDENCE_ABSENT`` naming the path. A test whose evidence *is* present still runs
  with its full, unchanged assertions.

A missing provider module is governed by ``STOCKLOOKUP_PROVIDER_RUNTIME_POLICY`` with the same two
values; its default is ``skip-if-absent`` because provider packages are optional dependencies
(see ``requirements-providers.txt``). ``strict`` turns an absent provider into
``PROVIDER_RUNTIME_REQUIRED``.

Hermetic CI deselects both tiers with ``-m "not retained_evidence and not provider_runtime"``
and separately runs ``-m retained_evidence`` under ``skip-if-absent`` so every evidence-dependent
test is still collected and reported with its explicit reason.

``tests/conftest.py`` re-exports the hooks below; this module is also usable directly as a
plugin (``-p _test_tiers``), which is how its own tests exercise it in isolation.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path, PurePosixPath

import pytest

RETAINED_EVIDENCE_MARKER = "retained_evidence"
PROVIDER_RUNTIME_MARKER = "provider_runtime"

RETAINED_EVIDENCE_POLICY_ENV = "STOCKLOOKUP_RETAINED_EVIDENCE_POLICY"
PROVIDER_RUNTIME_POLICY_ENV = "STOCKLOOKUP_PROVIDER_RUNTIME_POLICY"

POLICY_STRICT = "strict"
POLICY_SKIP_IF_ABSENT = "skip-if-absent"
_POLICIES = (POLICY_STRICT, POLICY_SKIP_IF_ABSENT)

# Optional provider packages that the hermetic tier must never need (requirements-providers.txt).
PROVIDER_RUNTIME_MODULES = ("vnstock", "vnai")


def resolve_policy(env_name: str, default: str) -> str:
    value = os.getenv(env_name, "").strip().lower() or default
    if value not in _POLICIES:
        raise pytest.UsageError(f"{env_name}={value!r} is not one of {', '.join(_POLICIES)}")
    return value


def validate_evidence_path(raw: object) -> str:
    """Accept only a repository-relative POSIX path that stays inside the repository."""
    if not isinstance(raw, str) or not raw.strip():
        raise pytest.UsageError(f"retained_evidence path must be a non-empty string, got {raw!r}")
    if "\\" in raw:
        raise pytest.UsageError(f"retained_evidence path must use '/' separators: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise pytest.UsageError(f"retained_evidence path must be repository-relative: {raw!r}")
    return path.as_posix()


def missing_evidence(root: Path, relative_paths: tuple[str, ...]) -> list[str]:
    return [rel for rel in relative_paths if not (root / rel).exists()]


def provider_module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ImportError:  # includes the CI provider-import block
        return False


def _marker_args(item: pytest.Item, name: str) -> tuple[str, ...]:
    args: list[str] = []
    for marker in item.iter_markers(name=name):
        args.extend(marker.args)
    return tuple(args)


def pytest_configure(config: pytest.Config) -> None:
    # Fail fast on a mistyped policy instead of at the first tiered test.
    resolve_policy(RETAINED_EVIDENCE_POLICY_ENV, POLICY_STRICT)
    resolve_policy(PROVIDER_RUNTIME_POLICY_ENV, POLICY_SKIP_IF_ABSENT)
    config.addinivalue_line(
        "markers",
        f"{RETAINED_EVIDENCE_MARKER}(*paths): retained-evidence tier; needs the named "
        "repository-relative governed evidence paths (see tests/_test_tiers.py)",
    )
    config.addinivalue_line(
        "markers",
        f"{PROVIDER_RUNTIME_MARKER}(*modules): provider-runtime tier; needs the named optional "
        "provider modules from requirements-providers.txt (see tests/_test_tiers.py)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Reject a malformed tier marker at collection, before any test runs."""
    for item in items:
        if item.get_closest_marker(RETAINED_EVIDENCE_MARKER) is not None:
            raw_paths = _marker_args(item, RETAINED_EVIDENCE_MARKER)
            if not raw_paths:
                raise pytest.UsageError(f"{item.nodeid}: @pytest.mark.{RETAINED_EVIDENCE_MARKER} must name its evidence paths")
            for raw in raw_paths:
                validate_evidence_path(raw)
        if item.get_closest_marker(PROVIDER_RUNTIME_MARKER) is not None and not _marker_args(item, PROVIDER_RUNTIME_MARKER):
            raise pytest.UsageError(f"{item.nodeid}: @pytest.mark.{PROVIDER_RUNTIME_MARKER} must name its modules")


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker(RETAINED_EVIDENCE_MARKER) is not None:
        paths = tuple(validate_evidence_path(raw) for raw in _marker_args(item, RETAINED_EVIDENCE_MARKER))
        absent = missing_evidence(Path(item.config.rootpath), paths)
        if absent:
            policy = resolve_policy(RETAINED_EVIDENCE_POLICY_ENV, POLICY_STRICT)
            listed = ", ".join(absent)
            if policy == POLICY_SKIP_IF_ABSENT:
                pytest.skip(f"RETAINED_EVIDENCE_ABSENT: {listed} (retained-evidence tier; policy={policy})")
            pytest.fail(
                f"RETAINED_EVIDENCE_REQUIRED: {listed} is missing. This test belongs to the "
                f"retained-evidence tier; restore the governed evidence, or on a clean clone deselect "
                f"it with -m 'not {RETAINED_EVIDENCE_MARKER}' or set "
                f"{RETAINED_EVIDENCE_POLICY_ENV}={POLICY_SKIP_IF_ABSENT}.",
                pytrace=False,
            )

    if item.get_closest_marker(PROVIDER_RUNTIME_MARKER) is not None:
        modules = _marker_args(item, PROVIDER_RUNTIME_MARKER)
        absent = [name for name in modules if not provider_module_available(name)]
        if absent:
            policy = resolve_policy(PROVIDER_RUNTIME_POLICY_ENV, POLICY_SKIP_IF_ABSENT)
            listed = ", ".join(absent)
            if policy == POLICY_SKIP_IF_ABSENT:
                pytest.skip(f"PROVIDER_RUNTIME_ABSENT: {listed} (provider-runtime tier; see requirements-providers.txt)")
            pytest.fail(f"PROVIDER_RUNTIME_REQUIRED: {listed} is not importable (requirements-providers.txt)", pytrace=False)
