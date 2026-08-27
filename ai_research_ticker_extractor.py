"""Deterministic bounded ticker extractor for one Daily Producer session/run.

Reads retained AI delivery files only. No network, no recomputation, no latest-file
inference, and no alphabetical sampling.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from field_temporal_contract import stable_id
from owner_research_focus import owner_focus_tickers

PACKET_CONTRACT = "ai_ticker_research_packet/v1"
RUNS_ROOT = Path("operations-review") / "daily-producer-runs-v1"
PRIMARY_FILENAME = "ai_research_session_bundle.json"
LOOKUP_FILENAME = "ai_research_full_universe.ndjson"
MANIFEST_FILENAME = "ai_research_bundle_manifest.json"
RUN_MANIFEST_FILENAME = "run_manifest.json"
ABSENT_STATUS = "TICKER_NOT_IN_SESSION_RESEARCH"


class TickerExtractorError(ValueError):
    """Fail-closed extractor refusal."""


def _canon(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_tickers(raw: str | list[str]) -> list[str]:
    if isinstance(raw, str):
        parts = [item.strip().upper() for item in raw.replace(";", ",").split(",")]
    else:
        parts = [str(item).strip().upper() for item in raw]
    tickers: list[str] = []
    seen: set[str] = set()
    for ticker in parts:
        if not ticker:
            continue
        if ticker in seen:
            continue
        seen.add(ticker)
        tickers.append(ticker)
    if not tickers:
        raise TickerExtractorError("REFUSE_TICKER_EXTRACT:NO_TICKERS_REQUESTED")
    return tickers


def resolve_daily_producer_run(root: Path, session: str, run_identity: str | None = None) -> Path:
    """Resolve one exact Daily Producer run directory. Never use latest-file navigation."""
    if not session or not str(session).strip():
        raise TickerExtractorError("REFUSE_TICKER_EXTRACT:EXPLICIT_SESSION_REQUIRED")
    session = str(session).strip()
    session_dir = root / RUNS_ROOT / session
    if not session_dir.is_dir():
        raise TickerExtractorError("REFUSE_TICKER_EXTRACT:SESSION_RUN_NOT_FOUND:" + session)
    run_dirs = sorted(path for path in session_dir.iterdir() if path.is_dir() and (path / RUN_MANIFEST_FILENAME).is_file())
    if not run_dirs:
        raise TickerExtractorError("REFUSE_TICKER_EXTRACT:SESSION_RUN_NOT_FOUND:" + session)
    if run_identity:
        token = run_identity.split(":", 1)[-1] if ":" in run_identity else run_identity
        matches = [path for path in run_dirs if path.name == token]
        if len(matches) != 1:
            raise TickerExtractorError("REFUSE_TICKER_EXTRACT:RUN_IDENTITY_NOT_RESOLVED:" + str(run_identity))
        return matches[0]
    if len(run_dirs) > 1:
        raise TickerExtractorError("REFUSE_TICKER_EXTRACT:AMBIGUOUS_SESSION_RUN:" + session)
    return run_dirs[0]


def _verify_delivery_file(path: Path, expected_sha: str | None) -> None:
    if not path.is_file():
        raise TickerExtractorError("REFUSE_TICKER_EXTRACT:DELIVERY_FILE_MISSING:" + path.name)
    if expected_sha and _sha(path.read_bytes()) != expected_sha:
        raise TickerExtractorError("REFUSE_TICKER_EXTRACT:DELIVERY_SELF_VERIFICATION_FAILED:" + path.name)


def _lookup_ndjson(path: Path, wanted: set[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    if not wanted or not path.is_file():
        return found
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            ticker = row.get("ticker")
            if ticker in wanted and ticker not in found:
                found[str(ticker)] = row
                if len(found) == len(wanted):
                    break
    return found


def extract_ai_research_tickers(
    root: Path,
    *,
    session: str,
    tickers: str | list[str],
    run_identity: str | None = None,
) -> dict[str, Any]:
    """Return a bounded research packet for the requested tickers of one exact run."""
    requested = parse_tickers(tickers)
    run_dir = resolve_daily_producer_run(root, session, run_identity)
    run_manifest = _load_json(run_dir / RUN_MANIFEST_FILENAME)
    resolved_session = run_manifest.get("target_market_session") or run_manifest.get("session")
    if resolved_session != session:
        raise TickerExtractorError("REFUSE_TICKER_EXTRACT:SESSION_IDENTITY_MISMATCH")
    resolved_run = run_manifest.get("run_identity") or ("daily_producer_run:" + run_dir.name)
    if run_identity:
        expected = run_identity if run_identity.startswith("daily_producer_run:") else "daily_producer_run:" + run_identity
        if resolved_run != expected and run_dir.name != (run_identity.split(":", 1)[-1]):
            raise TickerExtractorError("REFUSE_TICKER_EXTRACT:RUN_IDENTITY_MISMATCH")
    delivery_manifest = _load_json(run_dir / MANIFEST_FILENAME) if (run_dir / MANIFEST_FILENAME).is_file() else {}
    files = delivery_manifest.get("files") or {}
    primary_path = run_dir / PRIMARY_FILENAME
    lookup_path = run_dir / LOOKUP_FILENAME
    _verify_delivery_file(primary_path, (files.get(PRIMARY_FILENAME) or {}).get("sha256"))
    if lookup_path.is_file():
        _verify_delivery_file(lookup_path, (files.get(LOOKUP_FILENAME) or {}).get("sha256"))
    bundle = _load_json(primary_path)
    if bundle.get("session") != session:
        raise TickerExtractorError("REFUSE_TICKER_EXTRACT:BUNDLE_SESSION_MISMATCH")
    cards = bundle.get("ticker_research_contexts") or {}
    owner_contexts = {
        row.get("ticker"): row
        for row in (bundle.get("owner_focus_research_contexts") or [])
        if isinstance(row, Mapping) and row.get("ticker")
    }
    missing_from_primary = [ticker for ticker in requested if ticker not in cards and ticker not in owner_contexts]
    ndjson_rows = _lookup_ndjson(lookup_path, set(missing_from_primary))
    records: dict[str, Any] = {}
    present: list[str] = []
    missing: list[str] = []
    for ticker in requested:
        if ticker in cards:
            records[ticker] = {
                "ticker": ticker,
                "status": "PRESENT",
                "source": "PRIMARY_SESSION_BUNDLE",
                "card": copy_card(cards[ticker]),
            }
            present.append(ticker)
            continue
        if ticker in owner_contexts:
            records[ticker] = {
                "ticker": ticker,
                "status": owner_contexts[ticker].get("status") or "PRESENT",
                "source": "PRIMARY_SESSION_BUNDLE_OWNER_FOCUS",
                "card": copy_card(owner_contexts[ticker]),
            }
            if owner_contexts[ticker].get("status") == ABSENT_STATUS or owner_contexts[ticker].get("status") == "OWNER_FOCUS_TICKER_ABSENT_FROM_CURRENT_SESSION_RESEARCH":
                missing.append(ticker)
            else:
                present.append(ticker)
            continue
        if ticker in ndjson_rows:
            records[ticker] = {
                "ticker": ticker,
                "status": "PRESENT_FULL_UNIVERSE_LOOKUP",
                "source": "FULL_UNIVERSE_LOOKUP_ONLY",
                "card": copy_card(ndjson_rows[ticker]),
            }
            present.append(ticker)
            continue
        records[ticker] = {
            "ticker": ticker,
            "status": ABSENT_STATUS,
            "source": "NONE",
            "card": None,
            "is_actionable": False,
        }
        missing.append(ticker)
    packet: dict[str, Any] = {
        "schema_version": PACKET_CONTRACT,
        "session": session,
        "run_identity": resolved_run,
        "operation_identity": bundle.get("operation_identity") or run_manifest.get("daily_session_operation", {}).get("identity"),
        "product_identity": bundle.get("product_identity") or run_manifest.get("daily_product_identity"),
        "resolved_from": {
            "run_directory": str(run_dir.as_posix()),
            "primary_bundle": PRIMARY_FILENAME,
            "full_universe_companion": LOOKUP_FILENAME,
            "resolution": "EXACT_SESSION_AND_RUN_IDENTITY" if run_identity else "EXACT_SESSION_UNIQUE_RUN",
            "latest_file_navigation_used": False,
        },
        "source_identities": {
            "run_identity": resolved_run,
            "operation_identity": bundle.get("operation_identity"),
            "product_identity": bundle.get("product_identity"),
            "producer_head": bundle.get("producer_head") or run_manifest.get("producer_head"),
            "source_artifact_identities": copy_card(bundle.get("lineage", {}).get("input_artifacts") or delivery_manifest.get("source_artifact_identities") or {}),
        },
        "market": copy_card(bundle.get("market") or {}),
        "analysis_scope": copy_card(bundle.get("analysis_scope") or {}),
        "requested_tickers": requested,
        "records": records,
        "coverage": {
            "requested": requested,
            "present": present,
            "missing": missing,
            "owner_focus_tickers": list(owner_focus_tickers()),
        },
        "authority_boundary": {
            **copy_card(bundle.get("authority_boundary") or {}),
            "is_actionable": False,
            "entry_action_is_research_label_not_execution_instruction": True,
            "recommendation": "NOT_EMITTED",
        },
        "entry_action_is_research_label_not_execution_instruction": True,
        "is_actionable": False,
        "no_alphabetical_sampling": True,
        "no_network": True,
        "no_recomputation": True,
    }
    packet["packet_identity"] = "ai_ticker_research_packet:" + stable_id(packet)
    return packet


def copy_card(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): copy_card(item) for key, item in value.items()}
    if isinstance(value, list):
        return [copy_card(item) for item in value]
    return value


def write_packet(path: Path, packet: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canon(packet))
    return path
