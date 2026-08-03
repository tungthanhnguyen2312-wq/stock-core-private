"""Bounded end-to-end official corporate-action ingestion slice (pillar B vertical slice).

Proves the whole path -- retained-document reuse, immutable hashing, typed extraction,
citation linkage, deduplication, supersession, deterministic replay, and fail-closed handling
of an absent execution field -- against real retained official evidence for HPG, with **no
network request of any kind**.

It reads the documents already retained under the 2026-07-30 owner-approved allowlist in
`operations-review/hpg-vnm-current-share-bridge-20260802/` and writes only:

    <runtime-root>/data/official-corporate-actions/document_manifest.json
    <runtime-root>/data/official-corporate-actions/documents/<TICKER>/<class>/<sha256>.<ext>
    <runtime-root>/data/official-corporate-actions/event_ledger.json
    <runtime-root>/data/official-corporate-actions/event_observations.jsonl

It never writes to `data/official-evidence/` (that boundary belongs to
`evidence_promotion.py`), never touches `vn_stock.db` or a published artifact, and derives no
production-authority adjustment factor.

Usage:
  python tools/run_official_corporate_action_slice.py --runtime-root <path>
  python tools/run_official_corporate_action_slice.py --runtime-root <path> --execute
  python tools/run_official_corporate_action_slice.py --runtime-root <path> --execute --twice

`--twice` runs the whole slice a second time over the now-retained documents and compares the
two `replay_fingerprint` values, which is the determinism claim.

Exit codes: 0 success · 1 evidence missing or replay mismatch · 2 bad invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_file, atomic_write_json  # noqa: E402
from corporate_action_events import extract_event_observation, extract_text  # noqa: E402
from official_corporate_action_ledger import build_ledger  # noqa: E402
from official_document_store import (  # noqa: E402
    adopt_retained_document,
    manifest_index,
    read_document,
    store_root,
    verify,
)
from official_source_registry import admit, load_registry, registry_summary  # noqa: E402

RETAINED_ROOT = ROOT / "operations-review" / "hpg-vnm-current-share-bridge-20260802"

#: The bounded slice. Two independent official documents describing one HPG stock dividend:
#: the issuer's own change-of-voting-shares disclosure, and the issuer-published recital of
#: HOSE notice 1475/TB-SGDHCM confirming the listing change and first trading date.
SLICE = (
    {
        "relative_path": ("documents/HPG/2026/corporate_action_notice/"
                          "8bbae21fbb3e6c11f925385ac35b290e86e3db8753188131acbbba3bad5b29b2.pdf"),
        "ticker": "HPG",
        "document_type": "corporate_action_notice",
        "source_id": "issuer_ir",
        "source_url": ("https://file.hoaphat.com.vn/hoaphat-com-vn/2026/06/"
                       "20260604-hpg-cbtt-thay-doi-luong-co-phieu-luu-hanh-do-phat-hanh-"
                       "co-phieu-tra-co-tuc-2025.pdf"),
        "source_authority": "Hoa Phat Group Joint Stock Company",
        "published_at": "2026-06-04",
        "observed_at": "2026-08-02T08:40:00Z",
    },
    {
        "relative_path": ("documents/HPG/2026/corporate_action_notice/"
                          "cb41c96ef78bed7654030e55bb06dea22d051b1c9fcf1a6cf024e9f964563c1c.html"),
        "ticker": "HPG",
        "document_type": "listing_change_notice",
        "source_id": "issuer_ir",
        "source_url": ("https://www.hoaphat.com.vn/tin-tuc/"
                       "thong-bao-ve-ngay-giao-dich-co-phieu-phat-hanh-tra-co-tuc-nam-2025-1.html"),
        "source_authority": ("Hoa Phat Group Joint Stock Company investor relations, "
                             "reciting HOSE notice 1475/TB-SGDHCM"),
        "published_at": "2026-07-07",
        "observed_at": "2026-08-02T08:10:00Z",
    },
)


def _run(runtime_root: Path, execute: bool) -> dict:
    registry = load_registry()
    adopted, admissions = [], []
    for item in SLICE:
        # The registry is consulted even though nothing is fetched: adopting bytes from a host
        # the registry would refuse should be just as visible as requesting from one.
        decision = admit(item["source_id"], item["source_url"], item["document_type"],
                         registry=registry)
        admissions.append(decision)
        result = adopt_retained_document(
            runtime_root, RETAINED_ROOT / item["relative_path"],
            ticker=item["ticker"], document_type=item["document_type"],
            source_url=item["source_url"], source_authority=item["source_authority"],
            observed_at=item["observed_at"], published_at=item["published_at"],
            execute=execute)
        adopted.append(result)

    records = manifest_index(runtime_root) if execute else {
        result["document_id"]: result["record"] for result in adopted}

    observations = []
    for result in adopted:
        record = records.get(result["document_id"], result["record"])
        if execute:
            payload = read_document(runtime_root, result["document_id"])
        else:
            payload = (RETAINED_ROOT / next(
                item["relative_path"] for item in SLICE
                if item["source_url"] == record["source_url"])).read_bytes()
        text = extract_text(payload, str(record["media_type"]))
        observations.append(extract_event_observation(record, text))

    # Deduplication is exercised, not merely claimed: the same observations are offered twice.
    ledger = build_ledger([*observations, *observations])
    return {"adopted": adopted, "admissions": admissions, "observations": observations,
            "ledger": ledger}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--twice", action="store_true",
                        help="run twice and compare replay fingerprints")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    runtime_root = args.runtime_root
    if not runtime_root.is_dir():
        print(f"runtime root not found: {runtime_root}", file=sys.stderr)
        return 2
    for item in SLICE:
        if not (RETAINED_ROOT / item["relative_path"]).is_file():
            print(f"retained evidence missing: {item['relative_path']}", file=sys.stderr)
            return 1

    first = _run(runtime_root, args.execute)
    ledger = first["ledger"]

    replay_ok = None
    if args.twice:
        second = _run(runtime_root, args.execute)
        replay_ok = second["ledger"]["replay_fingerprint"] == ledger["replay_fingerprint"]

    if args.execute:
        target = store_root(runtime_root)
        atomic_write_json(target / "event_ledger.json", ledger)
        atomic_write_file(
            target / "event_observations.jsonl",
            "".join(json.dumps(observation, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")) + "\n"
                    for observation in first["observations"]).encode("utf-8"))

    if args.json:
        print(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    mode = "EXECUTE" if args.execute else "DRY RUN"
    summary = registry_summary()
    print(f"[official-corporate-action-slice] {mode}")
    print(f"  registry approval state    : {summary['approval_state']['state']}")
    print(f"  registry sources           : {summary['source_count']} "
          f"(approved {len(summary['approved_source_ids'])})")
    print(f"  registry admissions        : "
          f"{[decision['decision'] for decision in first['admissions']]}")
    print(f"  documents adopted          : {len(first['adopted'])}")
    for result in first["adopted"]:
        record = result["record"]
        print(f"      {record['ticker']} {record['document_type']:<24s} "
              f"{record['media_type']:<16s} {record['content_sha256'][:16]} "
              f"{record['parser_status']}")
    print(f"  observations extracted     : {len(first['observations'])}")
    for observation in first["observations"]:
        print(f"      {observation['event_type']} lifecycle={observation['lifecycle_state']} "
              f"before={observation['shares_before']} issued={observation['shares_issued']} "
              f"after={observation['shares_after']} ratio={observation['stock_ratio']}")
        if observation["warnings"]:
            print(f"        warnings: {', '.join(observation['warnings'])}")
    print(f"  ledger entries             : {ledger['entry_count']} "
          f"(deduplicated {len(ledger['duplicate_observations'])} repeat observations)")
    for entry in ledger["entries"]:
        print(f"      {entry['ticker']} {entry['event_type']} "
              f"lifecycle={entry['lifecycle_state']} qualification={entry['qualification_state']}")
        print(f"        ratio={entry['stock_ratio']} before={entry['shares_before']} "
              f"issued={entry['shares_issued']} after={entry['shares_after']}")
        print(f"        corroboration: {entry['arithmetic_corroboration']['state']} "
              f"({entry['arithmetic_corroboration']['reason']}) "
              f"cross_document={entry['arithmetic_corroboration'].get('cross_document')}")
        print(f"        documents={len(entry['source_document_ids'])} "
              f"citations={sum(len(d['citations']) for d in entry['source_documents'])}")
        print(f"        adjustment_factor={entry['adjustment_factor']} "
              f"status={entry['adjustment_factor_status']}")
        if entry["adjustment_factor_blocked_by"]:
            print(f"        blocked_by: {', '.join(entry['adjustment_factor_blocked_by'])}")
    if ledger["unlinked_observations"]:
        print(f"  unlinked observations      : {len(ledger['unlinked_observations'])}")
        for item in ledger["unlinked_observations"]:
            print(f"      {item['document_id'][:16]} — {item['reason']}")
    print(f"  qualified events           : {ledger['qualified_event_count']}")
    print(f"  replay fingerprint         : {ledger['replay_fingerprint']}")
    if replay_ok is not None:
        print(f"  deterministic replay       : {'MATCH' if replay_ok else 'MISMATCH'}")
    if args.execute:
        integrity = verify(runtime_root)
        print(f"  document store verify      : ok={integrity['ok']} "
              f"checked={integrity['checked']}")
        if not integrity["ok"]:
            return 1
    return 0 if replay_ok in (None, True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
