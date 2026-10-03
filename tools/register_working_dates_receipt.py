"""Explicit offline registration of an original, provenance-bound calendar receipt.

This tool is never invoked by Daily or acceptance. No provider request or history
extension; the original raw file and knowledge timestamp are mandatory.
"""
import argparse
import hashlib
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import prospective_market_snapshot_contract as market
import prospective_market_evidence_retention as retention
from atomic_io import retain_immutable_bytes


def register(source, *, source_sha256, retrieved_at, documentation_sha256, documentation_known_at, destination_root):
    source=Path(source).resolve(); raw=source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=source_sha256: raise ValueError("ORIGINAL_CALENDAR_SOURCE_HASH_MISMATCH")
    result=retention.retain_working_dates_calendar(raw,retrieved_at=retrieved_at,
        documentation_sha256=documentation_sha256,documentation_retrieved_at=documentation_known_at,root=Path(destination_root))
    receipt={"contract_version":"governed_calendar_registration/v1","original_source_location":str(source),
        "original_source_sha256":source_sha256,"original_retrieved_at":retrieved_at,
        "original_documentation_sha256":documentation_sha256,"original_documentation_known_at":documentation_known_at,
        "registered_receipt_identity":result["artifact_identity"],"network_requests":0,"historical_extension":False,"authority_effect":"NONE"}
    receipt.update(market.content_identity(receipt,kind="governed_calendar_registration"))
    path=Path(destination_root)/"operations-review/prospective-calendar-evidence-v1/registrations"/(receipt["artifact_sha256"]+".json")
    retain_immutable_bytes(path,market.canonical(receipt)); return receipt


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("source","source-sha256","retrieved-at","documentation-sha256","documentation-known-at","destination-root"):
        parser.add_argument("--"+name,required=True)
    args=vars(parser.parse_args()); source=args.pop("source"); print(register(source,**args)["artifact_identity"])
