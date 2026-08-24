from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from hnx_enumerable_universe_kllh_event_disclosure_scaleout import BASE,DISCLOSURES,fetch,retain,_content,_total
DEST=ROOT/'operations-review'/'hnx-enumerable-universe-kllh-event-and-disclosure-scaleout-v1-20260824'
def main()->None:
 for market,(_,endpoint) in DISCLOSURES.items():
  body={'pNumPage':'1','pAction':'0','pNhomTin':'','pTieuDeTin':'','pMaChungKhoan':'','pFromDate':'','pToDate':'','pOrderBy':'','pNumRecord':'1000'}
  response=fetch(BASE+endpoint,body=body)
  if response['http_status']!=200:raise ValueError(f'SOURCE_FETCH_FAILED:{market}')
  capture=retain(response=response,destination=DEST,surface=f'{market.lower()}_disclosure_probe',page=1,request_body=body)
  print(market,_total(_content(response['data'])),capture['sha256'])
if __name__=='__main__':main()
