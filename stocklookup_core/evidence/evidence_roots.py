"""Where completed-session evidence may live once code and evidence roots are split.

Single-root checkouts keep the historic answer (the Producer checkout only). With a qualified
workspace profile the canonical Daily writes its session outputs (Producer runs, tier handoffs,
exact-session snapshots) under the operation-output / retained-evidence root, while readers were
written against the checkout. This returns the ordered, de-duplicated set of governed roots a
reader may search; it never adds an arbitrary path. The owner Daily binds both variables from
the qualified workspace profile (``runtime_paths.workspace_environment``) before any phase runs;
this core module deliberately does not import that root-level resolver. 2026-10-19: the first T: Daily sealed its
Producer run under retained evidence and the runtime release then found ``count=0``.
"""
from __future__ import annotations

import os
from pathlib import Path

OPERATION_OUTPUT_ROOT_ENV = "STOCK_LOOKUP_OPERATION_OUTPUT_ROOT"
RETAINED_EVIDENCE_ROOT_ENV = "STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT"


def governed_evidence_roots(producer_root: str | os.PathLike[str]) -> list[Path]:
    roots = [Path(producer_root).resolve()]
    for name in (OPERATION_OUTPUT_ROOT_ENV, RETAINED_EVIDENCE_ROOT_ENV):
        value = os.environ.get(name, "").strip()
        if value:
            roots.append(Path(value).expanduser().resolve())
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def resolve_existing_evidence_file(producer_root: str | os.PathLike[str], path: str | os.PathLike[str]) -> Path:
    """First governed root that already holds this evidence file.

    An absolute path that exists is returned unchanged (the completed-session
    registry already records some inputs that way). A checkout-relative path is
    searched in ``governed_evidence_roots`` order, checkout first. A missing
    file stays on the checkout path so the caller still fail-closes.
    """
    producer = Path(producer_root).resolve()
    candidate = Path(path)
    if candidate.is_absolute() and candidate.is_file():
        return candidate
    if candidate.is_absolute():
        try:
            relative = candidate.resolve().relative_to(producer)
        except ValueError:
            return candidate
    else:
        relative = candidate
    for base in governed_evidence_roots(producer):
        found = base / relative
        if found.is_file():
            return found
    return producer / relative
