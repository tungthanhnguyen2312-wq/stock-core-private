"""Build the current corporate-event research context from retained artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_corporate_event_context import build_artifact, load_supplemental_retained_events, replay


DEFAULT_OFFICIAL_UNIVERSE = ROOT / "operations-review/current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json"
DEFAULT_EVENT_CONTEXT = ROOT / "operations-review/current-official-event-context-integration-v1-20260824/current_official_event_context_artifact.json"
DEFAULT_OUTPUT = ROOT / "operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-official-universe-artifact", default=str(DEFAULT_OFFICIAL_UNIVERSE))
    parser.add_argument("--current-official-event-context-artifact", default=str(DEFAULT_EVENT_CONTEXT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    event_context = _load(Path(args.current_official_event_context_artifact))
    session = str(event_context["research_session"])
    artifact = build_artifact(
        official_universe=_load(Path(args.current_official_universe_artifact)),
        official_event_context=event_context,
        supplemental_events=load_supplemental_retained_events(ROOT, session),
        research_session=session,
    )
    replay(artifact)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])
    print(json.dumps(artifact["coverage"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
