"""One bounded probe of the VCI price board, then offline composition analysis.

Exactly one live request, to one ticker, on an endpoint this repository's own production
code already calls (`meta_sync.py`, `blacklist_sync.py`). Nothing is retried, no redirect
is followed off the provider host, and every later run reads the retained payload.

    python tools/run_vci_composition_probe.py --execute
    python tools/run_vci_composition_probe.py --offline
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import vci_direct_basis_pilot as pilot  # noqa: E402
import vci_volume_composition as composition  # noqa: E402

EVIDENCE_DIR = ROOT / "operations-review" / "vci-volume-composition-20260804"
TICKER = "VCB"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://trading.vietcap.com.vn/",
    "Origin": "https://trading.vietcap.com.vn",
}


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (bytes, bytearray)):
        path.write_bytes(payload)
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def probe(session) -> dict:
    record = composition.assert_probe_permitted(
        "https://trading.vietcap.com.vn/api/price/symbols/getList"
    )
    payload = {"symbols": [TICKER]}
    transport = pilot.acquire(
        endpoint=record["endpoint"], payload=payload, session=session, headers=HEADERS
    )
    body = transport["raw_body"]
    digest = pilot.response_sha256(body)
    name = f"vci_price_board_{TICKER}_{transport['retrieved_at'].replace(':','').replace('-','')}_{digest[:16]}.raw.json"
    _write(EVIDENCE_DIR / "raw" / name, body)
    parsed = json.loads(body.decode("utf-8"))
    observation = {
        "provider": pilot.PROVIDER,
        "source_authority": pilot.SOURCE_AUTHORITY,
        "surface_id": record["surface_id"],
        "endpoint": record["endpoint"],
        "endpoint_provenance": record["observed_in"],
        "method": "POST",
        "request_parameters": payload,
        "request_headers_redacted": pilot.redact_headers(HEADERS),
        "response_headers_redacted": transport["response_headers_redacted"],
        "retrieved_at": transport["retrieved_at"],
        "http_status": transport["http_status"],
        "redirect_count": transport["redirect_count"],
        "retry_count": transport["retry_count"],
        "raw_response_sha256": digest,
        "response_schema_fingerprint": pilot.schema_fingerprint(parsed),
        "raw_artifact": name,
        "ticker": TICKER,
    }
    _write(EVIDENCE_DIR / "probe_observation.json", observation)
    return observation


def load_probe() -> dict | None:
    path = EVIDENCE_DIR / "probe_observation.json"
    if not path.exists():
        return None
    observation = json.loads(path.read_text(encoding="utf-8"))
    body = (EVIDENCE_DIR / "raw" / observation["raw_artifact"]).read_bytes()
    if pilot.response_sha256(body) != observation["raw_response_sha256"]:
        raise composition.CompositionError("probe_artifact_hash_drift")
    observation["_payload"] = json.loads(body.decode("utf-8"))
    return observation


def field_inventory(payload) -> dict:
    """Enumerate every field the board actually returned, grouped as the provider groups them."""
    rows = payload if isinstance(payload, list) else [payload]
    groups: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for group_name, group in row.items():
            bucket = groups.setdefault(group_name, {"fields": {}, "scalar": None})
            if isinstance(group, dict):
                for key, value in group.items():
                    bucket["fields"][key] = type(value).__name__
            elif isinstance(group, list):
                bucket["fields"]["<list>"] = f"len={len(group)}"
            else:
                bucket["scalar"] = type(group).__name__
    return groups


COMPOSITION_TOKENS = (
    "putthrough", "put_through", "thoathuan", "negotiat", "block",
    "oddlot", "odd_lot", "lo_le", "aution", "auction", "ato", "atc",
    "total", "matched", "board", "method", "deal",
)


def scan_for_composition_fields(groups: dict) -> dict:
    hits = []
    for group_name, bucket in groups.items():
        for field in bucket["fields"]:
            lowered = field.lower()
            for token in COMPOSITION_TOKENS:
                if token in lowered:
                    hits.append({"group": group_name, "field": field, "matched_token": token})
                    break
    return {
        "tokens_searched": list(COMPOSITION_TOKENS),
        "name_hits": hits,
        "name_hit_count": len(hits),
        "note": (
            "A name hit is a lead, never a qualification. Each is classified against a "
            "retained first-party definition before it can move any dimension."
        ),
    }


RETAINED_TAPE = (
    ROOT / "operations-review" / "vci-intraday-pagination-20260804"
    / "run-03-vcb-complete-segment" / "pages"
)


def ato_reconciliation(payload) -> dict:
    """Relate the board's ATO fields to the retained tape, entirely offline.

    Four quantities have to agree, not one: the board's ATO volume and price, the tape's
    first trade of the session, and the board's `firstTimeMatchPrice` instant. Volume
    alone would be a coincidence worth distrusting.
    """
    rows = payload if isinstance(payload, list) else [payload]
    match = rows[0].get("matchPrice", {}) if rows and isinstance(rows[0], dict) else {}
    board_volume = match.get("matchVolumeATO")
    board_price = match.get("matchPriceATO")
    first_match_iso = match.get("firstTimeMatchPrice")

    trades = {}
    for page in sorted(RETAINED_TAPE.glob("page_*.raw.json")):
        for row in json.loads(page.read_text(encoding="utf-8")):
            trades[row["id"]] = row
    if not trades:
        return {"available": False, "reason": "retained_tape_absent"}

    ordered = sorted(trades.values(), key=lambda r: (int(float(r["truncTime"])), int(r["id"])))
    first = ordered[0]
    first_epoch = int(float(first["truncTime"]))
    at_first_instant = [r for r in ordered if int(float(r["truncTime"])) == first_epoch]

    from datetime import datetime, timezone
    pinned_epoch = None
    if first_match_iso:
        pinned_epoch = int(
            datetime.fromisoformat(str(first_match_iso).replace("Z", "+00:00"))
            .replace(tzinfo=timezone.utc).timestamp()
        )

    tape_volume = sum(float(r["matchVol"]) for r in at_first_instant)
    tape_prices = sorted({float(r["matchPrice"]) for r in at_first_instant})
    volume_agrees = board_volume is not None and abs(float(board_volume) - tape_volume) < 0.5
    price_agrees = board_price is not None and tape_prices == [float(board_price)]
    starts_session = abs(float(first["accumulatedVolume"]) - float(first["matchVol"])) < 0.5
    referent_pinned = pinned_epoch is not None and pinned_epoch == first_epoch

    return {
        "available": True,
        "board_matchVolumeATO": board_volume,
        "board_matchPriceATO": board_price,
        "board_firstTimeMatchPrice": first_match_iso,
        "board_matchVolumeATC": match.get("matchVolumeATC"),
        "board_session": match.get("session"),
        "tape_first_instant_epoch": first_epoch,
        "tape_trades_at_first_instant": len(at_first_instant),
        "tape_volume_at_first_instant": tape_volume,
        "tape_prices_at_first_instant": tape_prices,
        "volume_agrees": volume_agrees,
        "price_agrees": price_agrees,
        "is_first_trade_of_session": starts_session,
        "referent_pinned": referent_pinned,
        "all_agree": bool(volume_agrees and price_agrees and starts_session and referent_pinned),
        "conclusion": (
            "The opening-auction batch is the accumulator's first entry, so ATO volume is "
            "inside accumulatedVolume and therefore inside daily v."
            if volume_agrees and price_agrees and starts_session and referent_pinned
            else "No agreement; nothing is claimed."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--execute", action="store_true")
    group.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    if args.execute:
        if (EVIDENCE_DIR / "probe_observation.json").exists():
            print("[refused] a probe is already retained; this milestone allows one")
            return 1
        probe(requests.Session())

    observation = load_probe()
    if observation is None:
        print("[offline] no retained probe")
        return 1

    groups = field_inventory(observation["_payload"])
    scan = scan_for_composition_fields(groups)

    # Every candidate field is classified against retained first-party evidence. None
    # exists: no VCI application text, tooltip, schema description or public field
    # dictionary is retained in this environment, and third-party or wrapper documentation
    # is not admissible authority for provider semantics.
    classified = [
        composition.classify_field_semantics(
            field_name=hit["field"], first_party_definition=None, definition_kind=None
        )
        for hit in scan["name_hits"]
    ]

    ato = ato_reconciliation(observation["_payload"])
    ato_fields = [
        composition.classify_field_semantics(field_name="matchVolumeATO", first_party_definition=None),
        composition.classify_field_semantics(field_name="matchPriceATO", first_party_definition=None),
    ]
    dimension_verdicts = {
        "matched_trade_inclusion": composition.qualify_dimension(
            dimension="matched_trade_inclusion", explicit_definition=None, demonstrated_relationship=None
        ),
        "negotiated_inclusion": composition.qualify_dimension(
            dimension="negotiated_inclusion", explicit_definition=None, demonstrated_relationship=None
        ),
        "odd_lot_inclusion": composition.qualify_dimension(
            dimension="odd_lot_inclusion", explicit_definition=None, demonstrated_relationship=None
        ),
        "opening_auction_inclusion": composition.qualify_dimension(
            dimension="opening_auction_inclusion",
            explicit_definition=None,
            demonstrated_relationship={
                "component_fields": ato_fields,
                "reconciles": ato["all_agree"],
                # firstTimeMatchPrice independently pins the same instant, so the match is
                # not merely a number agreeing with a suggestive name.
                "referent_pinned_by_independent_field": ato["referent_pinned"],
                "evidence": ato,
            },
        ),
        # The closing auction had not occurred at the retained morning snapshot
        # (matchVolumeATC = 0), so there is nothing to reconcile and nothing to claim.
        "closing_auction_inclusion": composition.qualify_dimension(
            dimension="closing_auction_inclusion", explicit_definition=None, demonstrated_relationship=None
        ),
    }

    contract = composition.assert_fail_closed(
        composition.composition_contract(
            provider_internal_volume_reconciled=True,
            dimension_verdicts=dimension_verdicts,
            unit="shares",
            corporate_action_adjustment=composition.price_adjustment_does_not_imply_volume_adjustment(
                price_basis="empirically_event_adjusted",
                retained_volume_evidence_determines_adjustment=False,
            ),
            exhausted_dimensions={
                # 96 fields across three groups on every observable surface; not one names
                # or separates a put-through, negotiated, block or odd-lot quantity.
                "negotiated_inclusion": "unavailable_from_observed_vci_surfaces",
                "odd_lot_inclusion": "unavailable_from_observed_vci_surfaces",
                "matched_trade_inclusion": "unavailable_from_observed_vci_surfaces",
                # Not exhausted -- simply not observable from a morning snapshot. A board
                # read after 14:45 ICT would carry matchVolumeATC and could settle it.
                "closing_auction_inclusion": "not_observable_from_the_retained_morning_snapshot",
            },
            surfaces_examined=[
                {k: v for k, v in s.items() if k != "fields"} for s in composition.CANDIDATE_SURFACES
            ],
        )
    )

    summary = {
        "schema_version": composition.VERSION,
        "probe": {k: v for k, v in observation.items() if k != "_payload"},
        "price_board_groups": groups,
        "composition_name_scan": scan,
        "field_semantics": classified,
        "opening_auction_reconciliation": ato,
        "first_party_definitions_retained": [],
        "first_party_definition_search": {
            "searched": [
                "retained VCI raw payloads (18 distinct field names, commit 9887c1c)",
                "vnstock 4.0.4 VCI adapter constants and docstrings",
                "this probe's payload",
            ],
            "found": 0,
            "note": (
                "Wrapper docstrings and third-party articles are not admissible as VCI "
                "field semantics; open-source adapter code proves request shape only."
            ),
        },
        "volume_contract": contract,
        "liquidity_eligibility": composition.liquidity_eligibility(contract),
    }
    _write(EVIDENCE_DIR / "composition_summary.json", summary)
    print(json.dumps({
        "groups": {g: len(b["fields"]) for g, b in groups.items()},
        "name_hits": scan["name_hits"],
        "market_scope": contract["market_scope"],
        "state": contract["state"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
