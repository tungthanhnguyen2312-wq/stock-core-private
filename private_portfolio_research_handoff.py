"""Private, local-only investment-analysis handoff (PERSONAL_DECISION_INPUT_TRUTH_V1).

Materializes one deterministic ``private_portfolio_research_handoff/v1`` artifact under the
private portfolio root, containing only what an investment-analysis consumer (e.g. the owner
manually pasting/uploading it into a research chat) actually needs: confirmed current holdings,
quantity/cost basis only when reconciliation-qualified, reconciliation status, owner research
exclusions, safe account/policy context, exact private artifact identities, and freshness/as-of
state. Never written to Git, operations-review, the Dashboard, or the public Stock Lookup
AI-handoff repository -- this module is never imported by any of those paths, and nothing here
transmits the file anywhere; the owner uploads it themselves, by choice.

Read-only: never opens the owner workbook, never calls a market-data provider, never runs Daily.
It only re-projects the already-materialized private ``portfolio_snapshot/v1`` (via
``private_portfolio_context.portfolio_status``) and the owner's local research-exclusion file (via
``owner_research_exclusions``).

CURRENT_POSITION_TRUTH boundary: a ``CURRENT_POSITION_UNRESOLVED`` or ``CLOSED`` position is named
by ticker and status only -- never a quantity or cost-basis figure, which for those two states is
either unreliable or not meaningful. Owner-excluded tickers never appear in ``holdings`` at all;
they are named once, by ticker and reason, in ``owner_research_exclusions`` only, so a reader knows
never to research them without their historical position being restated as a holding.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import owner_research_exclusions as _exclusions
import private_portfolio_context as _portfolio_context

CONTRACT_VERSION = "private_portfolio_research_handoff/v1"

_AUTHORITY_BOUNDARY = {
    "private_local_only": True,
    "never_written_to_git_operations_review_dashboard_or_public_ai_handoff": True,
    "unresolved_current_position_never_reported_as_a_holding": True,
    "owner_excluded_tickers_never_included_in_holdings": True,
    "historical_ledger_untouched_by_this_module": True,
    "manual_owner_upload_only_no_automatic_transmission": True,
    "no_position_sizing_or_investment_recommendation": True,
    # PRIVATE_MULTI_BROKER_INVESTMENT_ACCOUNT_CONTEXT_V1, Section 10: this artifact is meant for
    # manual upload to an external research chat -- a real brokerage account number/alias (the
    # owner's own `investment_account_context/v1` `account_id`, which the real workbook shows can
    # literally be an account number) is never included here, only an anonymized ordinal label.
    "no_raw_broker_account_identifier_in_this_external_facing_artifact": True,
}


def _anonymized_investment_accounts_context(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    aggregate = snapshot.get("investment_accounts_portfolio_context") or {}
    if aggregate.get("status") in (None, "NOT_PROVIDED"):
        return {"status": "NOT_PROVIDED", "accounts": []}
    identities = sorted(aggregate.get("account_identities") or [], key=lambda entry: str(entry.get("account_id")))
    return {
        "status": aggregate.get("status"),
        "account_count": aggregate.get("account_count"),
        "as_of_consistency": aggregate.get("as_of_consistency"),
        "totals": aggregate.get("totals"),
        "accounts": [
            {
                "handoff_account_label": f"ACCOUNT_{index + 1}",
                "broker": entry.get("broker"),
                "account_type": entry.get("account_type"),
                "as_of_date": entry.get("as_of_date"),
            }
            for index, entry in enumerate(identities)
        ],
    }


class PrivateHandoffError(ValueError):
    pass


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(body: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in body.items() if key not in {"artifact_identity", "artifact_sha256", "generated_at"}}
    digest = hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _not_available_body(*, generated_at: str, reason: str, exclusions: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "private_portfolio_research_handoff_v1",
        "contract_version": CONTRACT_VERSION,
        "generated_at": generated_at,
        "status": "NOT_AVAILABLE",
        "reason": reason,
        "holdings": [],
        "reconciliation": None,
        "owner_research_exclusions": [dict(entry) for entry in exclusions.get("excluded_tickers") or []],
        "account_and_policy_context": None,
        "investment_accounts_context": {"status": "NOT_PROVIDED", "accounts": []},
        "freshness": None,
        "source_artifact_identities": {},
        "authority_boundary": dict(_AUTHORITY_BOUNDARY),
    }


def build_artifact(*, portfolio_root: Path | None = None) -> dict[str, Any]:
    """Read-only. Reads only already-materialized private local artifacts."""
    status = _portfolio_context.portfolio_status(portfolio_root=portfolio_root)
    exclusions = _exclusions.load_research_exclusions(portfolio_root)
    excluded = _exclusions.excluded_ticker_set(exclusions)
    generated_at = dt.datetime.now().isoformat(timespec="seconds")

    if status.get("status") not in ("READY", "RECONCILIATION_INCOMPLETE"):
        body = _not_available_body(generated_at=generated_at, reason=status.get("status", "NOT_IMPORTED"), exclusions=exclusions)
        return {**body, **_identity(body)}

    snapshot = status["snapshot"]
    holdings: list[dict[str, Any]] = []
    for row in snapshot.get("positions") or []:
        ticker = row.get("ticker")
        if not ticker or ticker in excluded:
            continue
        position_status = row.get("current_position_status") or "CURRENT_CONFIRMED"
        # CLOSED already carries a true, safe "0" quantity and a naturally-None cost basis from
        # the producer (nothing to withhold); only CURRENT_POSITION_UNRESOLVED's quantity and
        # cost-basis figures are potentially unreliable stale numbers and must be withheld here
        # even if the producer itself still computed one from the frozen pre-block state.
        unresolved = position_status == "CURRENT_POSITION_UNRESOLVED"
        holdings.append({
            "ticker": ticker,
            "current_position_status": position_status,
            "current_quantity": None if unresolved else row.get("current_quantity"),
            "current_position_cost_basis_per_share": None if unresolved else row.get("current_position_cost_basis_per_share"),
            "current_position_cost_basis_method": None if unresolved else row.get("current_position_cost_basis_method"),
            "position_episode_holding_days": None if unresolved else row.get("position_episode_holding_days"),
            "realized_pnl_status": row.get("realized_pnl_status"),
        })
    holdings.sort(key=lambda entry: entry["ticker"])

    account_fields = ((snapshot.get("account_snapshot") or {}).get("fields")) or {}
    policy_fields = ((snapshot.get("portfolio_policy") or {}).get("effective_fields")) or {}

    body = {
        "schema_version": "private_portfolio_research_handoff_v1",
        "contract_version": CONTRACT_VERSION,
        "generated_at": generated_at,
        "status": "AVAILABLE",
        "holdings": holdings,
        "reconciliation": {
            "status": (snapshot.get("reconciliation") or {}).get("status"),
            "warning_counts": (snapshot.get("reconciliation") or {}).get("warning_counts"),
            "current_position_status_counts": snapshot.get("current_position_status_counts"),
        },
        "owner_research_exclusions": [dict(entry) for entry in exclusions.get("excluded_tickers") or []],
        "account_and_policy_context": {
            "cash_available": account_fields.get("cash_available"),
            "cash_reserved": account_fields.get("cash_reserved"),
            "margin_debt": account_fields.get("margin_debt"),
            "margin_available_minimum": account_fields.get("margin_available_minimum"),
            "margin_available_maximum": account_fields.get("margin_available_maximum"),
            "annual_margin_rate_percent": account_fields.get("annual_margin_rate_percent"),
            "net_asset_value": account_fields.get("net_asset_value"),
            "effective_policy": policy_fields,
        },
        "investment_accounts_context": _anonymized_investment_accounts_context(snapshot),
        "freshness": {
            "snapshot_as_of_date": snapshot.get("snapshot_as_of_date"),
            "snapshot_as_of_basis": snapshot.get("snapshot_as_of_basis"),
            "portfolio_status": status.get("status"),
        },
        "source_artifact_identities": {
            "portfolio_snapshot_identity": snapshot.get("artifact_identity"),
            "import_manifest_identity": (status.get("manifest") or {}).get("artifact_identity"),
        },
        "authority_boundary": dict(_AUTHORITY_BOUNDARY),
    }
    return {**body, **_identity(body)}


def write_private_artifact(artifact: Mapping[str, Any], *, portfolio_root: Path | None = None) -> Path:
    root = (portfolio_root or _portfolio_context.default_portfolio_root()).expanduser().resolve()
    destination = root / "private_portfolio_research_handoff" / "private_portfolio_research_handoff_v1.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = _canon(artifact) + "\n"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def public_console_summary(artifact: Mapping[str, Any], *, destination: Path | None = None) -> dict[str, Any]:
    """Safe CLI surface: identity/status/counts only, never the actual holdings or values."""
    return {
        "status": artifact.get("status"),
        "private_portfolio_research_handoff_identity": artifact.get("artifact_identity"),
        "holding_count": len(artifact.get("holdings") or []),
        "owner_research_exclusion_count": len(artifact.get("owner_research_exclusions") or []),
        "reconciliation_status": (artifact.get("reconciliation") or {}).get("status"),
        "written_to": str(destination) if destination is not None else None,
    }
