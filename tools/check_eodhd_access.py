"""Opt-in EODHD access check; never prints or persists credentials."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eodhd_access import credential_status, token_for_request
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');a=p.parse_args(argv); status=credential_status()
 if not a.live: print(json.dumps(status,sort_keys=True));return 0
 if not status['configured']: print(json.dumps({**status,'validation_status':'access_not_configured'},sort_keys=True));return 2
 # Network adapter intentionally awaits the separately authorized schema implementation.
 print(json.dumps({'configured':True,'source':'environment','validation_status':'live_adapter_not_implemented'},sort_keys=True));return 3
if __name__=='__main__':raise SystemExit(main())
