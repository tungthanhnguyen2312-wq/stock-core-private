"""Stateless CLI reader for the analyst research workbench's retained snapshot."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analyst_research_workbench import CURRENT_RETAINED_SNAPSHOT, build_current_workbench


def run(ticker: str | None = None, *, as_of: str | None = CURRENT_RETAINED_SNAPSHOT, operation: str = "GET_COHORT_RESOLUTION") -> dict:
    workbench = build_current_workbench()
    if operation == "GET_COHORT_RESOLUTION":
        return workbench.get_cohort_resolution()
    if operation == "GET_LEARNING_SUMMARY":
        return workbench.get_learning_summary()
    if ticker is None:
        raise ValueError("TICKER_REQUIRED_FOR_WORKBENCH_OPERATION")
    if operation == "GET_RESEARCH_STATE":
        return workbench.get_research_state(ticker, as_of=as_of)
    if operation == "BUILD_AI_INPUT":
        return workbench.build_ai_input(ticker, as_of=as_of)
    raise ValueError("CLI_OPERATION_NOT_STATELESS_READ_ONLY")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", default="GET_COHORT_RESOLUTION", choices=("GET_COHORT_RESOLUTION", "GET_LEARNING_SUMMARY", "GET_RESEARCH_STATE", "BUILD_AI_INPUT"))
    parser.add_argument("--ticker")
    parser.add_argument("--as-of", default=CURRENT_RETAINED_SNAPSHOT)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.ticker, as_of=arguments.as_of, operation=arguments.operation), ensure_ascii=False, indent=2, sort_keys=True))
