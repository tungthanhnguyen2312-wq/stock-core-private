"""Retired Vnstock family qualification command. No worker may be launched."""
from __future__ import annotations

import json


def main(argv: list[str] | None = None) -> int:
    print(json.dumps({
        "provider_family": "VNSTOCK_KBS_VCI",
        "state": "RETIRED_PROVIDER",
        "live_qualification": False,
        "worker_launch": "PROHIBITED",
        "reason": "ACTIVE_VNSTOCK_DEPENDENCY_RETIRED",
    }, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
