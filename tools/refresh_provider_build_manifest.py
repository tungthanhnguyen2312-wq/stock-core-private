"""Refresh derived identities on the tracked DRAFT provider build manifest.

Rewrites worker-source hashes and the dependency-lock digest. Refuses to run unless the
manifest is still DRAFT with launch_authorized=false. Never inserts an owner approval.

    python tools/refresh_provider_build_manifest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import provider_build_manifest as build_manifest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    del argv
    result = build_manifest.refresh_draft_identities()
    print("DRAFT_MANIFEST_IDENTITIES_REFRESHED")
    print(f"path={result['path']}")
    print(f"status={result['status']}")
    print(f"launch_authorized={result['launch_authorized']}")
    print(f"dependency_lock_sha256={result['dependency_lock_sha256']}")
    print(f"worker_source_files={len(result['worker_source_files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
