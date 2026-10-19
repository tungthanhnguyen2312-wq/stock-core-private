"""Where completed-session evidence may live once code and evidence roots are split.

Single-root checkouts keep the historic answer (the Producer checkout only). With a qualified
workspace profile the canonical Daily writes its session outputs (Producer runs, tier handoffs,
exact-session snapshots) under the operation-output / retained-evidence root, while readers were
written against the checkout. This returns the ordered, de-duplicated set of governed roots a
reader may search; it never adds an arbitrary path. 2026-10-19: the first T: Daily sealed its
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
    try:
        from runtime_paths import workspace_path
        roots.append(Path(workspace_path("retained", roots[0])).resolve())
    except Exception:  # noqa: BLE001 -- an unqualified profile contributes no extra root
        pass
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique
