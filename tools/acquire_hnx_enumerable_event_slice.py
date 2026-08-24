"""Acquire a declared contiguous HNX event-page slice in the foreground.

This helper has no retries, sleeps, timers, workers, or background execution.
It is intentionally small enough for an operator to invoke one bounded slice at
a time when an HTTP surface has a server-enforced page size.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from hnx_enumerable_universe_kllh_event_disclosure_scaleout import BASE, RIGHTS, fetch, retain, _content, _total

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--market', choices=sorted(RIGHTS), required=True)
    parser.add_argument('--first-page', type=int, required=True)
    parser.add_argument('--last-page', type=int, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    if args.first_page < 1 or args.last_page < args.first_page or args.last_page - args.first_page > 29:
        raise ValueError('DECLARED_SLICE_MUST_BE_1_TO_30_CONTIGUOUS_PAGES')
    endpoint = RIGHTS[args.market][1]
    body_base = {'pAction': '0', 'pNhomTin': '', 'pTieuDeTin': '', 'pMaChungKhoan': '', 'pFromDate': '', 'pToDate': '', 'pOrderBy': '', 'pNumRecord': '1000'}
    expected_total = None
    for page in range(args.first_page, args.last_page + 1):
        body = {**body_base, 'pNumPage': str(page)}
        response = fetch(BASE + endpoint, body=body)
        if response['http_status'] != 200: raise ValueError(f'SOURCE_FETCH_FAILED:{args.market}:{page}')
        total = _total(_content(response['data']))
        if expected_total is None: expected_total = total
        elif expected_total != total: raise ValueError(f'SOURCE_TOTAL_CHANGED:{args.market}:{page}')
        retain(response=response, destination=args.destination, surface=f'{args.market.lower()}_rights', page=page, request_body=body)
    print(f'{args.market} pages={args.first_page}-{args.last_page} total={expected_total}')
if __name__ == '__main__': main()
