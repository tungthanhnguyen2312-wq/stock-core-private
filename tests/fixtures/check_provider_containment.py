"""Child-process containment probe (audit hooks are process-wide and irreversible).

Reads a JSON contract on argv[1]: {"action": open|popen|run|http, "target": ..., "contract": {...}}.
Prints one JSON line with denied/allowed and the reason code. Never imports vnstock/vnai.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main() -> int:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    import provider_build_manifest as build_manifest
    import provider_worker_containment as containment

    installed = build_manifest.worker_containment_from_contract(spec["contract"])
    containment.install_worker_containment(installed)
    action = spec["action"]
    target = spec["target"]
    try:
        if action == "open":
            with open(target, encoding="utf-8") as handle:
                handle.read(1)
        elif action == "popen":
            subprocess.Popen(target if isinstance(target, list) else [target])
        elif action == "run":
            subprocess.run(target if isinstance(target, list) else [target], check=False)
        elif action == "http":
            containment.enforce_transport_policy(spec.get("method", "GET"), target)
        else:
            raise SystemExit(f"unknown action {action}")
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "denied": True, "type": type(exc).__name__,
            "reason_code": getattr(exc, "reason_code", None), "message": str(exc)[:300],
        }, sort_keys=True))
        return 0
    print(json.dumps({"denied": False, "reason_code": None}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
