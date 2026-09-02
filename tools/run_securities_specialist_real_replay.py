#!/usr/bin/env python3
"""Real retained-evidence replay for SECURITIES_SPECIALIST_FINANCIAL_RESEARCH_FOUNDATION_V1.

Read-only against the runtime root's `data_bctc/`. No provider calls, no store
writes. Reads retained parquet statement payloads directly via
`raw_financial_observations.extract_payload_file()` -- the same established
pattern `tools/run_gross_margin_real_replay.py` and
`tools/run_bank_specialist_real_replay.py` already use -- rather than through
the raw/canonical incremental store, whose persisted `ingest_state.json` is
stamped against an older `raw_financial_store.STORE_SCHEMA_VERSION` and
reports itself empty (a latent, unrelated staleness this milestone does not
touch or attempt to repair).

The governed securities ticker set is read from the CURRENT tracked
`entity_classification_contract` authority only (no sibling-worktree artifact).
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import entity_classification_contract as ecc  # noqa: E402
import financial_analysis_engine_v2 as engine  # noqa: E402
import raw_financial_observations as rfo  # noqa: E402
import securities_statement_capture_import as importer  # noqa: E402

DEFAULT_RUNTIME_ROOT = Path(r"C:\Projects\StockLookup\dashboard-runtime")
REQUESTED_AT = "2026-09-02T00:00:00+07:00"
STATEMENT_FAMILIES = ("balance_sheet", "income_statement")


def governed_securities_tickers() -> list[str]:
    profiles = ecc.load_layered_entity_profiles()
    return sorted(ticker for ticker, entity_type in profiles.items() if entity_type == "securities")


def load_ticker_observations(runtime_root: Path, ticker: str) -> tuple[list[dict], dict[str, bool]]:
    """Read one ticker's retained statement payloads, read-only. Returns
    (raw observations across both families, {family: file_present})."""
    source_root = runtime_root / "data_bctc"
    raw_observations: list[dict] = []
    templates: dict[str, bool] = {}
    for family in STATEMENT_FAMILIES:
        path = source_root / f"{ticker}_{family}_quarter.parquet"
        templates[family] = path.is_file()
        if templates[family]:
            raw_observations.extend(rfo.extract_payload_file(path)["observations"])
    return raw_observations, templates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    tickers = governed_securities_tickers()
    all_components: list[dict] = []
    template_coverage: dict[str, dict[str, bool]] = {}
    import_summaries: dict[str, dict[str, int]] = {}
    representative_trace: dict[str, dict] = {}

    for ticker in tickers:
        raw_observations, templates = load_ticker_observations(args.runtime_root, ticker)
        template_coverage[ticker] = templates
        imported = importer.import_raw_observations(raw_observations, retrieved_at=REQUESTED_AT)
        import_summaries[ticker] = {
            "raw_observations_seen": imported["raw_observations_seen"],
            "observations_built": imported["observations_built"],
        }
        all_components.extend(imported["observations"])

    artifact = engine.build_artifact(
        tickers=tickers, rows=[], issuer_types={ticker: "securities" for ticker in tickers},
        source_identities={"data_bctc_root": str(args.runtime_root / "data_bctc")},
        requested_at=REQUESTED_AT, securities_components=all_components,
    )

    feature_fitness = {
        feature_id: dict(sorted(Counter(
            artifact["records"][ticker]["features"][feature_id]["fitness"] for ticker in tickers).items()))
        for feature_id in engine.SECURITIES_FEATURE_IDS
    }
    state_distribution = {
        state_name: dict(sorted(Counter(
            artifact["records"][ticker]["states"][state_name] for ticker in tickers).items()))
        for state_name in engine.SECURITIES_STATE_NAMES
    }
    specialist_context_available_count = sum(
        1 for ticker in tickers
        if any(artifact["records"][ticker]["features"][fid]["fitness"] == "READY" for fid in engine.SECURITIES_FEATURE_IDS)
    )

    for representative in ("SSI", "VND", "HCM", "MBS", "VCI"):
        if representative not in tickers:
            continue
        record = artifact["records"][representative]
        representative_trace[representative] = {
            "raw_observations_seen": import_summaries[representative]["raw_observations_seen"],
            "components_built": import_summaries[representative]["observations_built"],
            "features": {
                fid: {"fitness": record["features"][fid]["fitness"], "value": record["features"][fid]["value"],
                     "method": record["features"][fid]["method"], "reason_codes": record["features"][fid]["reason_codes"]}
                for fid in engine.SECURITIES_FEATURE_IDS
            },
            "states": {sname: record["states"][sname] for sname in engine.SECURITIES_STATE_NAMES},
        }

    report = {
        "milestone": "SECURITIES_SPECIALIST_FINANCIAL_RESEARCH_FOUNDATION_V1",
        "runtime_root": str(args.runtime_root),
        "read_only": True,
        "provider_calls": 0,
        "store_writes": 0,
        "securities_ticker_count": len(tickers),
        "securities_tickers": tickers,
        "retained_specialist_template_count": sum(
            1 for ticker in tickers if all(template_coverage[ticker][family] for family in STATEMENT_FAMILIES)),
        "template_coverage_by_family": {
            family: sum(1 for ticker in tickers if template_coverage[ticker][family]) for family in STATEMENT_FAMILIES
        },
        "component_coverage_by_metric": dict(sorted(Counter(c["metric_id"] for c in all_components).items())),
        "feature_fitness": feature_fitness,
        "state_distribution": state_distribution,
        "specialist_context_available_count": specialist_context_available_count,
        "financial_v2_ticker_denominator_among_securities": artifact["coverage"]["ticker_denominator"],
        "current_research_ready_count_among_securities": sum(
            artifact["records"][ticker]["current_research_ready"] for ticker in tickers),
        "representative_trace": representative_trace,
        "production_runtime_written": False,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
