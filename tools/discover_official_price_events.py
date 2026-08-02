"""Bounded discovery of official corporate-action document locators.

Provider events select and deduplicate candidates only.  Search results are
locators, never evidence; acquisition and extraction remain mandatory.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit

import requests

MAX_CANDIDATES = 30
OFFICIAL_HOSTS = ("hose.vn", "hsx.vn", "vsd.vn", "hoaphat.com.vn", "vietcombank.com.vn", "vinamilk.com.vn")


def select_candidates(db_path: Path, *, as_of: str, limit: int = MAX_CANDIDATES) -> dict[str, list[dict[str, Any]]]:
    """Deterministically select non-overlapping in-coverage ISS candidates."""
    conn = sqlite3.connect(f"file:{Path(db_path).resolve().as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute("""SELECT ticker, provider_event_id, event_code, exright_date, exercise_ratio
            FROM corporate_event_records WHERE event_code='ISS' AND exright_date IS NOT NULL
            AND exercise_ratio>=0.10 AND exright_date<=? ORDER BY ticker, exright_date, exercise_ratio DESC, provider_event_id""", (as_of,)).fetchall()
    finally: conn.close()
    accepted, excluded, used = [], [], set()
    for ticker, event_id, code, ex_date, ratio in rows:
        key = (ticker, ex_date)
        item = {"ticker": ticker, "provider_event_id": event_id, "event_code": code, "candidate_ex_date": ex_date, "candidate_ratio": ratio, "exchange": "HOSE"}
        if key in used: excluded.append({**item, "reason": "overlapping_candidate_action"}); continue
        if len(accepted) >= limit: excluded.append({**item, "reason": "bounded_candidate_limit"}); continue
        used.add(key); accepted.append(item)
    return {"accepted": accepted, "excluded": excluded}


def is_official_url(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return any(host == allowed or host.endswith("." + allowed) for allowed in OFFICIAL_HOSTS)


def official_locator_results(candidate: Mapping[str, Any], search_html: str, *, discovered_at: str) -> list[dict[str, Any]]:
    """Return only official-host document/page URLs found by a bounded locator."""
    urls = re.findall(r'https?://[^"\s<>]+', search_html)
    seen, result = set(), []
    for url in urls:
        url = url.rstrip(".,)")
        if url in seen or not is_official_url(url): continue
        seen.add(url)
        result.append({"ticker": candidate["ticker"], "candidate_ex_date": candidate["candidate_ex_date"], "authority": next(host for host in OFFICIAL_HOSTS if (urlsplit(url).hostname or "").endswith(host)), "url": url, "discovery_method": "bounded_search_locator", "discovered_at": discovered_at})
    return result


def discover(candidates: Iterable[Mapping[str, Any]], *, search: Callable[[str], str], discovered_at: str) -> dict[str, Any]:
    found, failures = [], []
    for candidate in candidates:
        query = f'{candidate["ticker"]} {candidate["candidate_ex_date"]} stock dividend official disclosure'
        try: found.extend(official_locator_results(candidate, search(query), discovered_at=discovered_at))
        except Exception as exc: failures.append({"ticker": candidate["ticker"], "reason": "locator_network_error", "error": type(exc).__name__})
    return {"locators": found, "failures": failures}


def _search(query: str) -> str:
    response = requests.get("https://html.duckduckgo.com/html/", params={"q": query}, headers={"User-Agent": "StockLookupOfficialLocator/1.0"}, timeout=(5, 10))
    response.raise_for_status(); return response.text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--db", type=Path, required=True); parser.add_argument("--as-of", required=True); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--network", action="store_true")
    args = parser.parse_args(argv); selected = select_candidates(args.db, as_of=args.as_of); result = {"candidates": selected, "discovery": discover(selected["accepted"], search=_search if args.network else lambda _: "", discovered_at=f"{args.as_of}T00:00:00Z")}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"); return 0

if __name__ == "__main__": raise SystemExit(main())
