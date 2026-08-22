"""Inspect an explicit local durable prospective research-case store."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from durable_prospective_research_case_store import DurableProspectiveResearchCaseStore


def run(store_root: str | Path) -> dict:
    store = DurableProspectiveResearchCaseStore(store_root)
    return {"live_readiness": store.live_readiness(), "learning_ledger": store.build_learning_ledger()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-root", required=True)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.store_root), ensure_ascii=False, indent=2, sort_keys=True))
