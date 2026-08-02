"""Emit compact deterministic governance handoff from canonical files and contracts."""
from __future__ import annotations
import json, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
def _head(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
def _line(path: Path, prefix: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix): return line.split(":", 1)[1].strip()
    raise ValueError(f"missing_canonical_state:{prefix}")
def build_handoff() -> dict:
    state, roadmap = ROOT / "docs" / "STATE.md", ROOT / "docs" / "ROADMAP.md"
    contract = json.loads((ROOT / "contracts" / "price_basis.yaml").read_text(encoding="utf-8"))
    return {"producer_head": _head(ROOT), "consumer_head": _head(WORKSPACE / "ai-core-private"), "dashboard_head": _head(WORKSPACE / "dashboard-runtime"), "active_phase": _line(state, "- Active phase"), "active_milestone": _line(state, "- Active milestone"), "p0_exit_gates": [line[2:] for line in roadmap.read_text(encoding="utf-8").splitlines() if line.startswith("- Exit gates:")], "price_basis_status": contract["status"], "volume_basis_status": "unknown/unverified", "current_share_status": "unqualified", "production_state": _line(state, "- Production state")}
if __name__ == "__main__": print(json.dumps(build_handoff(), sort_keys=True))
