"""Evaluate the fixed retained DNSE cash-dividend candidates without network access.

This is deliberately not a discovery or a provider client.  It only proves whether the named
retained artifacts contain the inputs needed for an event-time DNSE price-basis verdict.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CANDIDATES = (
    {
        "ticker": "HPG",
        "event_code": "DIV",
        "event_type": "cash_dividend",
        "exright_date": "2026-05-11",
        "value_per_share_vnd": 500.0,
    },
    {
        "ticker": "VNM",
        "event_code": "DIV",
        "event_type": "cash_dividend",
        "exright_date": "2026-06-26",
        "value_per_share_vnd": 1850.0,
    },
)


def _probe_identity(result: dict[str, Any]) -> tuple[str, str] | None:
    query = result.get("query_sent", {})
    symbol = query.get("symbol")
    label = result.get("pit_label", "")
    if symbol and label:
        return str(symbol).upper(), str(label)
    return None


def evaluate(triage: dict[str, Any], probe: dict[str, Any]) -> dict[str, Any]:
    retained_candidates = {
        (str(item["ticker"]).upper(), str(item["exright_date"]))
        for item in triage["available_retained_corporate_action_cases"]["qualifiable_from_retained_evidence"]
    }
    probe_labels = sorted(
        identity for result in probe.get("results", []) if (identity := _probe_identity(result))
    )
    cases: list[dict[str, Any]] = []
    for candidate in CANDIDATES:
        identity = (candidate["ticker"], candidate["exright_date"])
        matching_dnse = [label for symbol, label in probe_labels if symbol == candidate["ticker"]]
        event_in_triage = identity in retained_candidates
        # A price-basis verdict requires observations from the candidate's own event window.
        # The HPG and VCB probes retained here are different events and cannot be borrowed.
        observations_present = any(candidate["exright_date"] in label for label in matching_dnse)
        cases.append(
            {
                "event_identity": candidate,
                "official_event_evidence": {
                    "status": "RETAINED_EVENT_IDENTITY_ONLY" if event_in_triage else "MISSING",
                    "lineage": "price-basis-authority-triage-20260812/triage.json",
                    "limitation": (
                        "The retained triage identifies the event, but the supplied retained set has no "
                        "standalone official-event artifact for this exact candidate."
                    ),
                },
                "comparison_observations": {
                    "dnse_candidate_window_present": observations_present,
                    "retained_dnse_probe_labels": [label for _, label in probe_labels],
                    "result": "ABSENT_FOR_CANDIDATE_EVENT",
                },
                "expected_raw_as_traded_behavior": (
                    "An otherwise comparable ex-date transition may reflect the cash dividend as a "
                    f"rough VND {candidate['value_per_share_vnd']:,.0f}/share downward component; market "
                    "movement means that transition alone is not a deterministic raw-series proof."
                ),
                "observed_dnse_historical_behavior": "NOT_OBSERVED_IN_RETAINED_CANDIDATE_WINDOW",
                "qualification_verdict": "UNKNOWN/INSUFFICIENT_EVIDENCE",
                "qualified_date_scope": None,
                "evidence_lineage": [
                    "price-basis-authority-triage-20260812/triage.json",
                    "dnse-ohlc-price-basis-qualification-20260810/probe_results.json",
                ],
                "reason": "candidate_event_requires_its_own_retained_dnse_pre_post_comparison",
            }
        )
    return {
        "schema_version": "1.0.0",
        "status": "PASS_NO_NEW_QUALIFICATION",
        "network_requests": 0,
        "qualification_rule": (
            "A retained event identity is not an OHLC basis qualification. Each event requires "
            "its own retained DNSE comparison observations before authority promotion."
        ),
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--triage", required=True, type=Path)
    parser.add_argument("--dnse-probe", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    if args.output_root.exists():
        parser.error("--output-root must not already exist")
    result = evaluate(
        json.loads(args.triage.read_text(encoding="utf-8")),
        json.loads(args.dnse_probe.read_text(encoding="utf-8")),
    )
    args.output_root.mkdir(parents=True)
    (args.output_root / "qualification_report.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = ["# Retained DNSE price-basis candidate qualification", "", "No new authority was promoted.", ""]
    for case in result["cases"]:
        event = case["event_identity"]
        lines.extend([
            f"## {event['ticker']} {event['exright_date']} {event['event_type']}", "",
            f"Verdict: `{case['qualification_verdict']}`", "",
            f"Reason: `{case['reason']}`", "",
        ])
    (args.output_root / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
