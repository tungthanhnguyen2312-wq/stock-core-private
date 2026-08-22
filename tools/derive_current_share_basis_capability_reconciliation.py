"""Build a deterministic, read-only current-share capability reconciliation artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_share_basis_capability_reconciliation import build_reconciliation

P3F4 = ROOT / "operations-review" / "p3f4-generic-current-share-authority-20260820" / "p3f4_generic_current_share_authority_artifact.json"
P3F5 = ROOT / "operations-review" / "p3f5-current-share-promotion-review-20260820" / "p3f5_current_share_promotion_review_artifact.json"
P3F6 = ROOT / "operations-review" / "p3f6-mva-provider-share-proxy-20260820" / "p3f6_mva_provider_share_proxy_artifact.json"
RETAINED_ARTIFACT = ROOT / "operations-review" / "current-share-basis-capability-reconciliation-v1-20260822" / "current_share_basis_capability_reconciliation_artifact.json"


def build() -> dict:
    return build_reconciliation(*(json.loads(path.read_text(encoding="utf-8")) for path in (P3F4, P3F5, P3F6)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    artifact = build()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "current_share_basis_capability_reconciliation_artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Artifact identity: {artifact['artifact_identity']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
