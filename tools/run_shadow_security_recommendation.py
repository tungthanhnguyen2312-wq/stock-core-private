"""Materialize deterministic shadow security recommendation packets from retained inputs."""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from shadow_security_recommendation import build_artifact

P=lambda value: ROOT/value
INPUTS={"research_cases":P("operations-review/thesis-catalyst-downside-and-dual-invalidation-v1-20260828/artifact.json"),"shadow_readiness":P("operations-review/shadow-action-readiness-v1-20260828/artifact.json"),"action_instrumentation":P("operations-review/action-instrumentation-and-invalidation-precision-v1-20260828/artifact.json"),"fundamental_invalidation":P("operations-review/fundamental-thesis-invalidation-precision-v1-20260828/artifact.json"),"risk_research":P("operations-review/current-portfolio-risk-research-v1-20260829/artifact.json"),"valuation_research":P("operations-review/current-valuation-research-proxy-and-relative-value-axis-v1-20260828/artifact.json"),"a1_temporal":P("operations-review/a1-bitemporal-semantic-contract-v1-20260828/artifact.json"),"a2_temporal":P("operations-review/a2-provider-publication-first-seen-retention-v1-20260829/artifact.json")}
OUTPUT=P("operations-review/shadow-security-recommendation-v1-20260829/artifact.json")
def run(output:Path=OUTPUT)->dict:
 a=build_artifact(**{key:json.loads(path.read_text(encoding="utf-8")) for key,path in INPUTS.items()});output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(a,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8");return a
if __name__=="__main__":
 a=run();print(a["artifact_identity"]);print(a["denominator"])
