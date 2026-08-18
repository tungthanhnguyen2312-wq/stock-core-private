"""Domain adapter: official financial filings, replayed from Stock Lookup's
existing governed evidence corpus.

This is the framework's first supported domain and its vertical-slice
proof driver. It is a "source adapter" in the sense the framework's
required dependency direction names explicitly: existing evidence input ->
acquisition contract -> retention/checkpoint/quarantine -> manifest/report.
It only ever reads from the governed evidence root and never writes there,
and it never fabricates a field the source manifest does not carry -
published_at, source_authority, and similar fields pass through exactly as
recorded, including when they are null.

This module performs no network call and does not recollect, requalify,
or alter the existing financial-evidence corpus in any way - see
docs/acquisition_landing_framework.md, "Acquisition vs qualification".
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from acquisition_landing_contract import AcquisitionSpec

DOMAIN = "official-financial-filings-v1"
GOVERNED_MANIFEST_FILENAME = "official_document_acquisition_manifest.json"
DEFAULT_TICKERS = ("HPG", "VNM", "VCB")


def default_governed_evidence_root(workspace_root: str | Path) -> Path:
    """The real, git-untracked evidence corpus lives inside the *primary*
    stock-core-private checkout, not inside this isolated worktree - a
    fresh git worktree does not carry another checkout's untracked files."""
    return Path(workspace_root) / "stock-core-private" / "operations-review" / "governed-official-evidence-v1"


def load_governed_records(governed_evidence_root: str | Path) -> list[dict]:
    manifest_path = Path(governed_evidence_root) / GOVERNED_MANIFEST_FILENAME
    with manifest_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload["records"]


def select_records(records: Iterable[dict], tickers: Iterable[str] = DEFAULT_TICKERS) -> list[dict]:
    wanted = {t.upper() for t in tickers}
    return [r for r in records if str(r.get("ticker", "")).upper() in wanted]


def spec_for_record(record: dict) -> AcquisitionSpec:
    return AcquisitionSpec(
        domain=DOMAIN,
        source_locator=record["canonical_url"],
        source_authority_class="existing_governed_evidence_replay",
        issuer_identity=record.get("ticker"),
        document_type=record.get("document_class"),
        acquisition_method="replay_from_governed_evidence",
        acquisition_method_version="1",
    )


def iter_replay_items(
    governed_evidence_root: str | Path, tickers: Iterable[str] = DEFAULT_TICKERS
) -> Iterator[tuple[AcquisitionSpec, dict]]:
    """Yields (AcquisitionSpec, retain_kwargs) pairs ready to hand to
    acquisition_landing_checkpoint.process_batch(). Reads document bytes
    from governed_evidence_root; never writes there."""
    governed_evidence_root = Path(governed_evidence_root)
    records = select_records(load_governed_records(governed_evidence_root), tickers)

    for record in records:
        spec = spec_for_record(record)
        source_path = governed_evidence_root / record["relative_path"]
        data = source_path.read_bytes()
        retain_kwargs = {
            "data": data,
            "declared_sha256": record.get("sha256"),
            "http_status": record.get("http_status"),
            "content_type": record.get("content_type"),
            "original_filename": Path(record["relative_path"]).name,
            "source_published_at": record.get("published_at"),
        }
        yield spec, retain_kwargs


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
