"""Pinned, read-only VCI balance-sheet monetary-basis research verdict."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "provider_financial_monetary_basis_verdict/v1"
DIRECTORY = "provider-financial-monetary-basis-verdict-v1-20260927"
FILENAME = "provider_financial_monetary_basis_verdict.json"
EXPECTED_IDENTITY = (
    "provider_financial_monetary_basis_verdict/v1:"
    "d6bc37cab1c835d5d34dd2c4e6321d01994eca2601131de61473fa22fbc6492c"
)


class MonetaryBasisVerdictUnavailable(ValueError):
    pass


def resolve(root: Path) -> dict[str, Any]:
    """Read one named tracked artifact; never scan newest or read runtime facts at Daily time."""
    path = Path(root) / "operations-review" / DIRECTORY / FILENAME
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MonetaryBasisVerdictUnavailable("MONETARY_BASIS_VERDICT_UNAVAILABLE") from exc
    body = {k: v for k, v in artifact.items() if k not in {"artifact_identity", "artifact_sha256"}}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    if (artifact.get("contract_version") != CONTRACT_VERSION
            or artifact.get("artifact_sha256") != digest
            or artifact.get("artifact_identity") != EXPECTED_IDENTITY
            or artifact.get("qualified_shapes") != ["VCI:balance_sheet"]
            or (artifact.get("semantic_basis_registry") or {}).get("contracts", {}).get("VCI:balance_sheet", {}).get("verdict")
            != "PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED"
            or (artifact.get("authority_boundary") or {}).get("official_financial") is not False):
        raise MonetaryBasisVerdictUnavailable("MONETARY_BASIS_VERDICT_UNAVAILABLE")
    return artifact
