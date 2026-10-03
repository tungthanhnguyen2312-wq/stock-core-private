"""Explicit retained replay / compatibility entry; never registers a T0 snapshot."""
import argparse
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from volume_and_flow_retained_v2 import collect
from flow_price_divergence_shadow import write_immutable


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("source-root","runtime-root","feature-batch","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--feature-batch-sha256",required=True)
    parser.add_argument("--session",required=True)
    parser.add_argument("--allow-v1-bridge",action="store_true")
    args=parser.parse_args()
    target=args.output.resolve()
    if (target==args.feature_batch.resolve() or any(target.is_relative_to(p.resolve()) for p in
        (args.source_root/"operations-review",args.source_root/"config",args.source_root/"data",args.runtime_root))):
        raise ValueError("REPLAY_OUTPUT_MUST_BE_SEPARATE_FROM_RETAINED_EVIDENCE")
    artifact,_=collect(source_root=args.source_root,runtime_root=args.runtime_root,session=args.session,
        feature_batch=args.feature_batch,feature_batch_sha256=args.feature_batch_sha256,allow_legacy_bridge=args.allow_v1_bridge)
    write_immutable(args.output,artifact)
    print(artifact["contract_version"],artifact["artifact_identity"])


if __name__=="__main__":main()
