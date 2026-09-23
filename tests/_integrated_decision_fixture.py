"""Hermetic Integrated Decision fixtures for surface tests (CURRENT_DECISION_SURFACE_CONVERGENCE_V1).

Every artifact here is produced by the real ``integrated_investment_decision_product.build_artifact``
-- never hand-assembled -- so content identity, decision identity, and the evidence-currency gate
are exactly the production ones.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

import integrated_investment_decision_product as iidp
import same_session_technical_coverage_disposition as disposition_module


def disposition_record(ticker: str, *, session: str, currency: str) -> dict[str, Any]:
    """A retained same-session technical coverage disposition record yielding ``currency``
    (``CURRENT_SESSION`` / ``LAST_TRADE_AS_OF:<date>`` / ``NO_CURRENT_EVIDENCE``)."""
    if currency == iidp.EVIDENCE_CURRENCY_CURRENT_SESSION:
        return {"ticker": ticker, "disposition": "SAME_SESSION_TECHNICAL_COVERED", "has_exact_session_bar": True,
                "is_current_session": True, "feature_as_of_session": session}
    if currency.startswith(iidp.EVIDENCE_CURRENCY_LAST_TRADE_PREFIX):
        return {"ticker": ticker, "disposition": "PROVIDER_SESSION_UNAVAILABLE", "has_exact_session_bar": False,
                "is_current_session": False, "feature_as_of_session": currency.split(":", 1)[1]}
    return {"ticker": ticker, "disposition": "PROVIDER_REJECTED_OR_INVALID_SYMBOL", "has_exact_session_bar": False,
            "is_current_session": None, "feature_as_of_session": None}


def disposition_artifact(records: Mapping[str, Mapping[str, Any]], *, session: str) -> dict[str, Any]:
    artifact = {"contract_version": iidp.EVIDENCE_CURRENCY_SOURCE_CONTRACT, "session": session, "records": dict(records)}
    artifact.update(disposition_module.content_identity(artifact))
    return artifact


def integrated_decision(
    session: str,
    tickers: Iterable[str],
    *,
    tactical_records: Mapping[str, Mapping[str, Any]] | None = None,
    financial_records: Mapping[str, Mapping[str, Any]] | None = None,
    currency_by_ticker: Mapping[str, str] | None = None,
    priority_queue: Mapping[str, Any] | None = None,
    portfolio_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    tickers = sorted(tickers)
    tactical = {t: dict((tactical_records or {}).get(t) or {"ticker": t}) for t in tickers}
    currencies = currency_by_ticker or {}
    disposition = disposition_artifact(
        {t: disposition_record(t, session=session, currency=currencies.get(t, iidp.EVIDENCE_CURRENCY_NO_CURRENT_EVIDENCE))
         for t in tickers},
        session=session,
    )
    return iidp.build_artifact(
        session=session, requested_at=f"{session}T15:00:00+07:00",
        technical_structure_artifact={"artifact_identity": "technical_structure:fixture", "records": tactical},
        financial_analysis_artifact=(
            {"artifact_identity": "financial_analysis:fixture", "records": dict(financial_records)} if financial_records else None
        ),
        technical_coverage_disposition_artifact=disposition,
        priority_queue_artifact=priority_queue,
        portfolio_artifact=portfolio_record,
    )


def minimal_integrated_record(ticker: str, session: str) -> dict[str, Any]:
    return integrated_decision(session, [ticker])["records"][ticker]
