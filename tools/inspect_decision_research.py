"""Read-only owner inspection of existing decision-intelligence projections."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import math
import re
from pathlib import Path

SOURCES = {
    "universe": ("current_universe_status_and_session_coverage_resolution/v1", "input_candidates"),
    "technical": ("same_session_technical_coverage_disposition/v1", "session"),
    "valuation": ("market_wide_current_valuation/v1", "valuation_session"),
    "intelligence": ("market_wide_current_corporate_intelligence/v1", "session"),
    "events": ("current_official_event_context/v1", "research_session"),
}


def configure_parser(sub):
    parser = sub.add_parser("research", help="Inspect explicit retained coverage/calibration; read-only, offline.")
    actions = parser.add_subparsers(dest="research_action", required=True)
    coverage = actions.add_parser("coverage", help="Full-universe coverage with optional ticker and retained panel context.")
    coverage.add_argument("--session", required=True)
    for name in SOURCES:
        coverage.add_argument("--" + name, type=Path, required=True, help="Exact retained artifact path.")
    coverage.add_argument("--ticker", action="append", default=[], help="Display focus ticker (repeatable); denominator stays complete.")
    coverage.add_argument("--panel", type=Path, help="Optional existing historical_temporal_research_panel/v1 JSON projection.")
    calibration = actions.add_parser("calibration", help="Descriptive outcome review; genuine maturity and population limits preserved.")
    calibration.add_argument("--feedback", type=Path, required=True)


def _session(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("INVALID_SESSION")
    return value


def _digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_SOURCE_KEY")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("NONFINITE_SOURCE_NUMBER")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("NONFINITE_SOURCE_NUMBER")
        return number

    with path.open(encoding="utf-8") as handle:
        body = json.load(handle, object_pairs_hook=unique, parse_constant=nonfinite, parse_float=finite_float)
    if not isinstance(body, dict):
        raise ValueError("SOURCE_NOT_AN_OBJECT")
    return body


def inspect(args):
    # Hash before and after projection: a changing file never produces a success.
    names = list(SOURCES) if args.research_action == "coverage" else ["feedback"]
    if args.research_action == "coverage" and args.panel:
        names.append("panel")
    paths = {name: getattr(args, name).resolve(strict=True) for name in names}
    before = {name: _digest(path) for name, path in paths.items()}
    if args.research_action == "coverage":
        import decision_intelligence_coverage_calibration as spine
        session = _session(args.session)
        bodies = {}
        for name, (contract, session_key) in SOURCES.items():
            body = _json(paths[name])
            if body.get("contract_version") != contract:
                raise ValueError("SOURCE_CONTRACT_MISMATCH:" + name)
            declared = body.get(session_key)
            if name == "universe":
                declared = declared.get("resolved_completed_session") if isinstance(declared, dict) else None
            if declared != session:
                raise ValueError("SOURCE_SESSION_MISMATCH:" + name)
            if name != "events":
                records = body.get("records")
                if not isinstance(records, dict) or any(not isinstance(row, dict) for row in records.values()):
                    raise ValueError("SOURCE_RECORDS_MALFORMED:" + name)
            else:
                records = body.get("all_current_universe_event_records")
                if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
                    raise ValueError("SOURCE_RECORDS_MALFORMED:events")
            bodies[name] = body
        index = spine.join_coverage_artifacts(session=session, **bodies)
        tickers = tuple(dict.fromkeys(t.strip().upper() for t in args.ticker)) or spine.FOCUS_TICKERS
        if any(not t or not t.isascii() or not t.isalnum() for t in tickers):
            raise ValueError("INVALID_TICKER")
        historical = None
        if args.panel:
            import historical_temporal_research_panel as panel
            historical = _json(paths["panel"])
            if historical.get("contract_version") != panel.CONTRACT_VERSION or not isinstance(historical.get("rows"), list):
                raise ValueError("PANEL_CONTRACT_MISMATCH")
            for row in historical["rows"]:
                if not isinstance(row, dict) or _session(row.get("session")) > session:
                    raise ValueError("PANEL_FUTURE_SESSION")
                if not isinstance(row.get("fields"), dict):
                    raise ValueError("PANEL_FIELDS_MALFORMED")
        reports = spine.focus_reports(index, historical, tickers=tickers)
        if historical is None:
            for report in reports.values():
                report["retention_limitation"] = "HISTORICAL_PANEL_NOT_SUPPLIED"
        result = {
            "contract_version": spine.CONTRACT_VERSION,
            "session": session,
            "coverage_index_identity": index["index_identity"],
            "coverage_summary": index["summary"],
            "focus": reports,
            "historical_context_supplied": historical is not None,
            "temporal_use": "CURRENT_RESEARCH_INSPECTION_NOT_PIT",
        }
    else:
        import decision_outcome_calibration_review as calibration
        import prospective_decision_outcome_feedback as feedback
        metadata = {}

        def retain_header(key, value):
            if key == "contract_version":
                metadata[key] = value

        rows = []
        for record in calibration.iter_feedback_records(paths["feedback"], on_metadata=retain_header):
            rows.extend(calibration.compact_horizons(record))
        if metadata.get("contract_version") != feedback.CONTRACT_VERSION:
            raise ValueError("SOURCE_CONTRACT_MISMATCH:feedback")
        result = calibration.review_observations(rows)
        result["temporal_use"] = "RETAINED_OUTCOME_REVIEW_NOT_DECISION_TIME"
    if before != {name: _digest(path) for name, path in paths.items()}:
        raise ValueError("SOURCE_CHANGED_DURING_INSPECTION")
    result.update(status="AVAILABLE", persisted=False, authority_effect="NONE",
                  source_references={name: {"name": path.name, "sha256": before[name]} for name, path in paths.items()},
                  source_reference_limit="BYTE_REFERENCES_ONLY_NOT_TRUST_OR_AUTHORITY_QUALIFICATION")
    return result


def run(args):
    try:
        result = inspect(args)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        # Do not expose host paths or source bodies in an error report.
        reason = str(exc).split(":", 1)[0] if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else type(exc).__name__
        if not re.fullmatch(r"[A-Z][A-Z0-9_]+", reason):
            reason = type(exc).__name__
        print(json.dumps({"status": "UNAVAILABLE", "reason": reason, "persisted": False, "authority_effect": "NONE"}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    configure_parser(sub)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
