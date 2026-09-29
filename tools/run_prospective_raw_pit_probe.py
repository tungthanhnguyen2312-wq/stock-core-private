"""Bounded, foreground HOSE probe for PROSPECTIVE_RAW_PIT_AUTHORITY_V1 (no loop, no daemon, no retries beyond policy).

The plan is deterministic and frozen before any request is made:

* basis requests: HOSE ``tradingresult`` pages that cover documented corporate-action ex-dates
  (HPG pages 4-5 around 2026-05-25; VCB pages 2-3 around 2026-07-23);
* revision requests: page 1 for a deterministic 10-ticker cohort already retained at T0, so the same
  ticker/session can be compared at T0 versus T1.

HOSE acquisition rights are those recorded in ``official_liquidity_market_wide.ACQUISITION_RIGHTS``
(bounded foreground paced retrieval for internal research; raw bodies retained private/local, never
published). At most one retry, only for an explicit transient outcome. Consecutive-failure breaker.
No DNSE, Vnstock, KBS, VCI, FHSC call; no production DB write.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import official_exchange_trading_statistics as official  # noqa: E402
from atomic_io import atomic_write_file, atomic_write_json  # noqa: E402
from tools import run_liquidity_authority_closure as closure  # noqa: E402

HARD_REQUEST_BUDGET = 20
SPACING_SECONDS = 1.5
BREAKER = 3
TRANSIENT = frozenset({"HTTP_429", "HTTP_502", "HTTP_503", "HTTP_504", "URLError", "TimeoutError"})
BASIS_REQUESTS = (("HPG", 4), ("HPG", 5), ("VCB", 2), ("VCB", 3))
REVISION_ALWAYS = ("HPG", "VCB")
REVISION_COHORT_EXTRA = 8
OPS = ROOT / "operations-review"
DEFAULT_OUTPUT = OPS / "prospective-raw-pit-authority-v1-20260929"


def _prior_hose_tickers(prior_ledger: Path) -> list[str]:
    tickers = set()
    for line in prior_ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        url = (entry.get("request") or {}).get("url", "")
        if entry.get("outcome") == "OK" and "api.hsx.vn" in url and "pageIndex=1&" in url:
            tickers.add(url.split("tradingresult/")[1].split("?")[0])
    return sorted(tickers)


def plan(prior_ledger: Path) -> dict[str, Any]:
    retained = _prior_hose_tickers(prior_ledger)
    ranked = sorted((t for t in retained if t not in REVISION_ALWAYS), key=lambda t: hashlib.sha256(t.encode()).hexdigest())
    cohort = [*REVISION_ALWAYS, *ranked[:REVISION_COHORT_EXTRA]]
    requests = ([{"purpose": "BASIS_EVENT_WINDOW", **official.hose_request(t, page=p)} for t, p in BASIS_REQUESTS]
                + [{"purpose": "REVISION_T1_REREQUEST", **official.hose_request(t, page=1)} for t in cohort])
    if len(requests) > HARD_REQUEST_BUDGET:
        raise SystemExit("plan exceeds hard request budget")
    body = {"contract": "prospective_raw_pit_probe_plan/v1", "requests": requests, "hard_request_budget": HARD_REQUEST_BUDGET,
            "spacing_seconds": SPACING_SECONDS, "revision_cohort": cohort, "retained_hose_tickers": len(retained)}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {**body, "plan_sha256": digest}


def run(plan_doc: Mapping[str, Any], output: Path) -> dict[str, Any]:
    raw = output / "probe" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    ledger_path = output / "probe" / "request_ledger.jsonl"
    if ledger_path.exists():
        raise SystemExit(f"refusing to overwrite an existing probe ledger: {ledger_path}")
    entries, made, consecutive = [], 0, 0
    for index, request in enumerate(plan_doc["requests"]):
        if consecutive >= BREAKER:
            entries.append({"index": index, "request": request, "outcome": "NOT_ATTEMPTED_BREAKER_OPEN", "attempts": []})
            continue
        attempts = []
        for attempt in range(2):
            if made >= HARD_REQUEST_BUDGET:
                break
            started = dt.datetime.now(dt.timezone.utc).isoformat()
            status, content_type, body, error = closure._execute(request)
            made += 1
            digest = hashlib.sha256(body).hexdigest() if body else None
            if body:
                target = raw / f"{digest}.bin"
                if not target.exists():
                    atomic_write_file(target, body)
            ok = status == 200 and error is None and bool(body)
            result = {"retrieved_at": started, "http_status": status, "content_type": content_type, "bytes": len(body),
                      "sha256": digest, "outcome": "OK" if ok else (error or "EMPTY_BODY")}
            time.sleep(SPACING_SECONDS)
            if result["outcome"] in TRANSIENT and attempt == 0:
                attempts.append(result)
                continue
            break
        consecutive = 0 if result["outcome"] == "OK" else consecutive + 1
        entries.append({"index": index, "request": request, **result, "attempts": attempts})
    atomic_write_file(ledger_path, "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in entries))
    summary = {"plan_sha256": plan_doc["plan_sha256"], "http_requests_made": made, "hard_request_budget": HARD_REQUEST_BUDGET,
               "final_outcomes": dict(sorted(Counter(e["outcome"] for e in entries).items())),
               "retries_used": sum(len(e.get("attempts") or []) for e in entries),
               "ledger_sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest()}
    atomic_write_json(output / "probe" / "probe_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "probe"))
    parser.add_argument("--prior-ledger", type=Path, required=True, help="retained prior HOSE request_ledger.jsonl")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    doc = plan(args.prior_ledger)
    if args.command == "plan":
        args.output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(args.output_dir / "probe_plan.json", doc)
        print(json.dumps({"planned_requests": len(doc["requests"]), "plan_sha256": doc["plan_sha256"], "cohort": doc["revision_cohort"]}))
        return 0
    print(json.dumps(run(doc, args.output_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
