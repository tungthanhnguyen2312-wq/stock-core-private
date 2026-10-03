"""Offline retained-only Stage-2 build/retry/one-ticker verifier. No acquisition."""
import argparse
import json
from pathlib import Path
import sys
from contextlib import contextmanager
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


@contextmanager
def retained_only_guard():
    import socket,urllib.request,http.client,importlib.abc
    from unittest.mock import patch
    from contextlib import ExitStack
    import requests
    calls={"network":0,"provider":0,"vnstock_import":0}
    def blocked(*args,**kwargs):
        calls["network"]+=1;raise RuntimeError("THESIS_NETWORK_FORBIDDEN")
    class ProviderGuard(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,*args):
            if fullname.split(".")[0] in {"vnstock","vnai","anthropic"}:
                calls["provider"]+=1;calls["vnstock_import"]+=fullname.split(".")[0] in {"vnstock","vnai"}
                raise RuntimeError("THESIS_PROVIDER_IMPORT_FORBIDDEN")
    with ExitStack() as stack:
        for owner,name in ((socket.socket,"connect"),(socket,"create_connection"),(urllib.request,"urlopen"),
            (urllib.request.OpenerDirector,"open"),(http.client.HTTPConnection,"connect"),
            (requests.sessions.Session,"request")):
            stack.enter_context(patch.object(owner,name,blocked))
        stack.enter_context(patch.object(sys,"meta_path",[ProviderGuard(),*sys.meta_path]))
        yield calls


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session",required=True);parser.add_argument("--stage",choices=("t0","current"),required=True)
    parser.add_argument("--source-root",type=Path,required=True);parser.add_argument("--output-root",type=Path,required=True)
    for name in ("decision","technical","flow","snapshot","sealed-decision","request","result","manifest"):
        parser.add_argument("--"+name,type=Path)
    parser.add_argument("--origin",choices=("SEAL_TIME","LATE_REBUILD"),default="LATE_REBUILD")
    parser.add_argument("--diagnostic",action="store_true");parser.add_argument("--verify-ticker")
    args=parser.parse_args()
    # Explicit test/offline acquisition guard is also installed in normal child:
    # source processing is never permitted to reach provider/network surfaces.
    with retained_only_guard() as calls:
        from thesis_evidence_production import build,verify_ticker
        if args.verify_ticker:
            if not args.manifest:raise ValueError("EXPLICIT_MANIFEST_REQUIRED")
            result=verify_ticker(args.manifest,root=args.source_root,ticker=args.verify_ticker)
        else:
            request=json.loads(args.request.read_bytes()) if args.request else {}
            result=build(root=args.source_root,output_root=args.output_root,session=args.session,stage=args.stage,
                decision_path=args.decision,technical_path=args.technical,flow_path=args.flow,snapshot_path=args.snapshot,
                sealed_decision_path=args.sealed_decision,index_ref=request.get("index_ref"),snapshot_identity=request.get("snapshot_identity"),
                observer_identities=request.get("observer_identities"),origin=args.origin,diagnostic=args.diagnostic)
    if any(calls.values()):raise RuntimeError("THESIS_OFFLINE_GUARD_VIOLATION")
    result["network_provider_calls"]=calls
    if args.result:
        from atomic_io import atomic_write_json
        atomic_write_json(args.result,result)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":main()
