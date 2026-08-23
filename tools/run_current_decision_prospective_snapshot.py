"""Explicit offline seal of the retained 2026-08-21 current decision surface."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; OPS=ROOT/'operations-review'
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from prospective_research_learning import freeze_current_decision_surface, write_immutable
PATHS={'tactical':OPS/'watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json','triage':OPS/'full-universe-entry-candidate-triage-20260824/full_universe_entry_candidate_triage_20260824.json','fundamental':OPS/'market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json','valuation':OPS/'market-wide-current-valuation-v1-20260824/market_wide_current_valuation_artifact.json'}
OUT=OPS/'current-decision-prospective-learning-v1-20260824/current_decision_prospective_snapshot_20260821.json'
def run(): return freeze_current_decision_surface(**{k:json.loads(v.read_text(encoding='utf8')) for k,v in PATHS.items()})
if __name__=='__main__':
 a=run();write_immutable(OUT,a);print(a['snapshot_id'])
