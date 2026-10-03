"""Explicit bounded index recovery; never reconstructs or modifies T0 evidence."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prospective_t0_seal_index import recover

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot",required=True,type=Path)
    parser.add_argument("--index-created-at",required=True)
    parser.add_argument("--replay-diagnostic",action="store_true")
    args=parser.parse_args()
    print(recover(args.snapshot,created_at=args.index_created_at,diagnostic=args.replay_diagnostic))
