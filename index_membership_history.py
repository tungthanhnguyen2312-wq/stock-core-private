"""Read-only forward comparison of complete local index-constituent snapshots."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from index_constituents_sync import SOURCE_NAME, SOURCE_REFERENCE, resolve_group


COMPLETE_STATUS = "complete_response"
EMPTY_RESULT = {
    "added_symbols": [],
    "removed_symbols": [],
    "unchanged_count": None,
}


def _base_result(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "previous_snapshot_id": previous["snapshot_id"] if previous else None,
        "current_snapshot_id": current["snapshot_id"] if current else None,
        "previous_observed_at": previous["fetched_at"] if previous else None,
        "current_observed_at": current["fetched_at"] if current else None,
        **EMPTY_RESULT,
    }


def _snapshot(conn: sqlite3.Connection, snapshot_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT snapshot_id,source_name,requested_group,effective_provider_group,source_reference,
                  fetched_at,record_count,status,is_complete
           FROM index_constituent_snapshots WHERE snapshot_id=?""",
        (snapshot_id,),
    ).fetchone()
    if row is None:
        return None
    keys = (
        "snapshot_id", "source_name", "requested_group", "effective_provider_group", "source_reference",
        "fetched_at", "record_count", "status", "is_complete",
    )
    return dict(zip(keys, row))


def _valid_members(conn: sqlite3.Connection, snapshot: Mapping[str, Any]) -> list[str] | None:
    """Return validated symbols, or None when persisted data is incomplete/corrupt."""
    if snapshot["status"] != COMPLETE_STATUS or snapshot["is_complete"] != 1:
        return None
    rows = conn.execute(
        """SELECT source_name,requested_group,effective_provider_group,source_member_identity,symbol
           FROM index_constituent_records WHERE snapshot_id=?""",
        (snapshot["snapshot_id"],),
    ).fetchall()
    if not rows or len(rows) != snapshot["record_count"]:
        return None
    symbols: list[str] = []
    identities: set[str] = set()
    for source_name, requested_group, effective_group, identity, symbol in rows:
        if (source_name, requested_group, effective_group) != (
            snapshot["source_name"], snapshot["requested_group"], snapshot["effective_provider_group"],
        ):
            return None
        if not isinstance(identity, str) or not isinstance(symbol, str):
            return None
        symbol = symbol.strip().upper()
        if not identity.strip() or not symbol or identity in identities:
            return None
        identities.add(identity)
        symbols.append(symbol)
    if len(set(symbols)) != len(symbols):
        return None
    return symbols


def compare_snapshots(
    conn: sqlite3.Connection, previous_snapshot_id: str, current_snapshot_id: str
) -> dict[str, Any]:
    """Compare two explicit snapshots without writing history or inferring effective dates."""
    previous = _snapshot(conn, previous_snapshot_id)
    current = _snapshot(conn, current_snapshot_id)
    result = _base_result(previous, current)
    if previous is None or current is None or previous_snapshot_id == current_snapshot_id:
        return {"status": "invalid_snapshot", **result}
    scope_keys = ("source_name", "requested_group", "effective_provider_group", "source_reference")
    if any(previous[key] != current[key] for key in scope_keys):
        return {"status": "incomparable_scope", **result}
    previous_symbols = _valid_members(conn, previous)
    current_symbols = _valid_members(conn, current)
    if previous_symbols is None or current_symbols is None:
        return {"status": "invalid_snapshot", **result}
    previous_set, current_set = set(previous_symbols), set(current_symbols)
    added = sorted(current_set - previous_set)
    removed = sorted(previous_set - current_set)
    return {
        "status": "changed" if added or removed else "unchanged",
        **result,
        "added_symbols": added,
        "removed_symbols": removed,
        "unchanged_count": len(previous_set & current_set),
    }


def latest_group_change(
    conn: sqlite3.Connection,
    requested_group: str,
    *,
    source_name: str = SOURCE_NAME,
    source_reference: str = SOURCE_REFERENCE,
) -> dict[str, Any]:
    """Compare the latest two complete snapshots in one exact requested-group scope."""
    scope = resolve_group(requested_group)
    rows = conn.execute(
        """SELECT snapshot_id,source_name,requested_group,effective_provider_group,source_reference,
                  fetched_at,record_count,status,is_complete
           FROM index_constituent_snapshots
           WHERE source_name=? AND requested_group=? AND effective_provider_group=? AND source_reference=?
             AND status=? AND is_complete=1
           ORDER BY fetched_at DESC, snapshot_id DESC LIMIT 2""",
        (source_name, scope["requested_group"], scope["effective_provider_group"], source_reference,
         COMPLETE_STATUS),
    ).fetchall()
    keys = (
        "snapshot_id", "source_name", "requested_group", "effective_provider_group", "source_reference",
        "fetched_at", "record_count", "status", "is_complete",
    )
    snapshots = [dict(zip(keys, row)) for row in rows]
    if not snapshots:
        return {"status": "no_previous_snapshot", **_base_result(None, None)}
    current = snapshots[0]
    if _valid_members(conn, current) is None:
        return {"status": "invalid_snapshot", **_base_result(None, current)}
    if len(snapshots) == 1:
        return {"status": "no_previous_snapshot", **_base_result(None, current)}
    return compare_snapshots(conn, snapshots[1]["snapshot_id"], current["snapshot_id"])
