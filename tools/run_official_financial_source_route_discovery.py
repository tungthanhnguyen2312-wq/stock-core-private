"""Compatibility entrypoint that preserves the historical V1 artifact.

Route qualification is corrected by the evidence-binding runner; this entrypoint
must never overwrite the immutable V1 artifact with a new contract version.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_official_source_route_evidence_binding_correction import main


if __name__ == "__main__":
    main()
