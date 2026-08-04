"""One bounded, governed announcement-index discovery pilot for a single ticker.

Acquires exactly ONE official announcement index page through the governed acquisition path,
parses candidate links out of the stored artifact, runs them through the canonical discovery
ledger, and STOPS. It never acquires a candidate: `official_document_discovery.retain()` is
deliberately not called from here.

The entry URL is not invented. It must be an official navigation link observed in a retained
first-party artifact, and `--observed-in` records where, in the run report.

Usage:
  python tools/run_official_listing_discovery.py --ticker VNM --source-id vsdc \
      --listing-url https://vsd.vn/en/alc/6 \
      --observed-in operations-review/vnm-2024-cash-dividend-official-evidence/vsdc-record-date-notice.html \
      --destination <dir>                      # preflight only, no network
  ... --execute                                # performs the single acquisition

Exit codes: 0 success · 1 refused, failed, or nothing acquired · 2 bad invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from official_document_acquisition import (  # noqa: E402
    MANIFEST, acquire, canonical_url, declared_document_types,
)
from official_document_discovery import discover  # noqa: E402
from official_listing_page_parser import (  # noqa: E402
    listing_pages, parse_index_page, parsed_summary, review_queue,
)
from official_source_registry import (  # noqa: E402
    ADMITTED, admit, all_index_document_types, approval_instant_verdict, index_document_types,
    load_registry, source_index,
)


def preflight(registry, *, source_id: str, listing_url: str, document_class: str) -> dict:
    source = source_index(registry).get(source_id) or {}
    decision = admit(source_id, listing_url, document_class, registry=registry)
    return {
        "approval_instant": approval_instant_verdict(registry),
        "admission": decision,
        "is_index_type": document_class in all_index_document_types(registry),
        "source_index_types": sorted(index_document_types(source)),
        "min_request_interval_seconds": source.get("min_request_interval_seconds"),
        "max_redirects": (registry.get("global_policy") or {}).get("max_redirects"),
        "requestable_types": sorted(declared_document_types(registry)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--listing-url", required=True)
    parser.add_argument("--observed-in", required=True,
                        help="repository artifact the entry URL was observed in")
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--document-class", default="announcement_index_page")
    parser.add_argument("--reporting-period", default="2026")
    parser.add_argument("--execute", action="store_true",
                        help="perform the single governed acquisition")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    registry = load_registry()
    try:
        listing_url = canonical_url(args.listing_url)
    except ValueError:
        print(f"unusable listing url: {args.listing_url}", file=sys.stderr)
        return 2
    observed_in = ROOT / args.observed_in
    if not observed_in.is_file():
        print(f"entry-URL provenance artifact not found: {args.observed_in}", file=sys.stderr)
        return 2

    checks = preflight(registry, source_id=args.source_id, listing_url=listing_url,
                       document_class=args.document_class)
    report = {"ticker": args.ticker.upper(), "listing_url": listing_url,
              "observed_in": args.observed_in, "preflight": checks}

    if checks["approval_instant"]["verdict"] != "verified":
        report["state"] = "blocked_by_governance"
    elif checks["admission"]["decision"] != ADMITTED:
        report["state"] = "refused_by_source_registry"
    elif not checks["is_index_type"]:
        report["state"] = "document_class_is_not_an_index_type"
    elif not args.execute:
        report["state"] = "preflight_only_no_network"
    else:
        spec = {"ticker": args.ticker.upper(), "source_id": args.source_id,
                "document_class": args.document_class,
                "reporting_period": args.reporting_period, "canonical_url": listing_url}
        result = acquire([spec], args.destination, registry=registry)
        report["acquisition"] = result
        outcome = (result.get("outcomes") or [{}])[0]
        report["state"] = outcome.get("state", "unknown")
        if outcome.get("state") in {"retained", "cached_valid"}:
            records = json.loads((Path(args.destination) / MANIFEST).read_text(encoding="utf-8"))
            record = next(r for r in records["records"]
                          if r["document_id"] == outcome["document_id"])
            stored = Path(args.destination) / record["relative_path"]
            report["stored_artifact"] = {"document_id": record["document_id"],
                                         "sha256": record["sha256"],
                                         "content_length": record["content_length"],
                                         "content_type": record["content_type"],
                                         "relative_path": record["relative_path"],
                                         "final_url": record["final_url"]}
            parsed = parse_index_page(stored.read_bytes(), listing_url=listing_url,
                                      source_id=args.source_id, ticker=args.ticker,
                                      registry=registry)
            found = discover(listing_pages(parsed), records["records"], registry)
            report["parse_summary"] = parsed_summary(parsed)
            report["review_queue"] = review_queue(parsed)
            report["discovery_ledger_sha256"] = found["ledger_sha256"]
            report["discovery_states"] = sorted(
                {str(row.get("state")) for row in found["ledger"]})
            report["accepted_requests"] = found["accepted_requests"]
            report["rejected_links"] = parsed["rejected_links"]

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"[listing-discovery] {report['state']}")
        print(f"  ticker                : {report['ticker']}")
        print(f"  listing url           : {listing_url}")
        print(f"  url observed in       : {args.observed_in}")
        print(f"  approval instant      : {checks['approval_instant']['verdict']} "
              f"({checks['approval_instant'].get('approved_at')})")
        print(f"  admission             : {checks['admission']['decision']} "
              f"({checks['admission']['reason']})")
        print(f"  index document type   : {args.document_class} "
              f"(declared for source: {checks['source_index_types']})")
        print(f"  rate interval / hops  : {checks['min_request_interval_seconds']}s / "
              f"{checks['max_redirects']}")
        if "stored_artifact" in report:
            art = report["stored_artifact"]
            print(f"  stored artifact       : {art['sha256']} "
                  f"({art['content_length']} bytes, {art['content_type']})")
            print(f"  final url             : {art['final_url']}")
            print(f"  parse summary         : {report['parse_summary']}")
            print(f"  candidates            : {len(report['review_queue'])}")
            for row in report["review_queue"]:
                print(f"    {row['review_order']:>2}. [{row['confidence']:<6}] "
                      f"{row['candidate_id']}  {row['visible_date'] or '----------'}  "
                      f"{row['inferred_document_class']}")
                print(f"        {row['visible_title'][:100]}")
                print(f"        {row['canonical_url']}")
    return 0 if report["state"] in {"retained", "cached_valid", "preflight_only_no_network"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
