"""One-invocation selection of non-voting current corporate knowledge.

No consumer calls acquire. The frozen market selection is carried separately and
never inferred from the current overlay. Canonical orchestration owns invocation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import copy
from pathlib import Path
from zoneinfo import ZoneInfo

import official_corporate_event_incremental_acquisition as acquisition
from official_acquisition_budget import AcquisitionBudget

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def context_known_by(context: dict, cutoff: datetime) -> bool:
    """All retained event observations must exist by an explicit aware cutoff.

    Acquisition start and the directory date are not knowledge-time proof.
    Missing observation time fails closed; absent publication time is not inferred.
    """
    if cutoff.tzinfo is None:
        raise ValueError("KNOWLEDGE_TIME_MUST_BE_TIMEZONE_AWARE")
    events = context.get("all_current_universe_event_records")
    if not isinstance(events, list):
        return False
    excluded = context.get("excluded_noncurrent_or_official_only_event_records", [])
    if not isinstance(excluded, list):
        return False
    events = events + excluded
    for event in events:
        if not isinstance(event, dict):
            return False
        observed = event.get("official_observed_at")
        if not observed:
            return False
        for value in (observed, event.get("published_at")):
            if value is None:
                continue
            try:
                stamp = datetime.fromisoformat(value)
            except (TypeError, ValueError):
                return False
            if stamp.tzinfo is None or stamp > cutoff:
                return False
    return True


def current_product_projection(frozen_product: dict, overlay: dict) -> dict:
    """Add explanatory knowledge to a separate current product, never its T0.

    The frozen product is copied intact, including action posture and source
    identities. The current projection gets a distinct identity and temporal lane.
    """
    from current_official_event_context import _verify
    _verify(overlay, "CURRENT_CORPORATE_KNOWLEDGE_OVERLAY")
    if overlay.get("historical_use_allowed") is not False or overlay.get("non_voting") is not True:
        raise ValueError("CURRENT_OVERLAY_AUTHORITY_BOUNDARY_INVALID")
    target = (overlay.get("receipt") or {}).get("target_market_session")
    product_session = frozen_product.get("as_of_session") or frozen_product.get("session")
    if product_session != target:
        raise ValueError("CURRENT_OVERLAY_MARKET_SESSION_MISMATCH")
    product = copy.deepcopy(frozen_product)
    product["frozen_market_session_product_identity"] = frozen_product.get("artifact_identity")
    product["temporal_lane"] = "FROZEN_MARKET_SESSION_DECISION_PLUS_CURRENT_KNOWLEDGE_CORPORATE_OVERLAY"
    product["current_corporate_knowledge_overlay"] = copy.deepcopy(overlay)
    records = ((overlay.get("official_event_context") or {}).get("records") or {})
    for ticker, card in (product.get("cards") or {}).items():
        card["current_corporate_knowledge"] = {
            "source_overlay_identity": overlay["artifact_identity"],
            "knowledge_observed_at": (overlay.get("receipt") or {}).get("knowledge_observed_at"),
            "freshness_state": (overlay.get("receipt") or {}).get("freshness_state"),
            "events": copy.deepcopy((records.get(ticker) or {}).get("events") or []),
            "forward_driver_context": copy.deepcopy((overlay.get("forward_driver_contexts") or {}).get(ticker)),
            "status": ("UNAVAILABLE" if overlay.get("official_event_context") is None else
                       "AVAILABLE" if ticker in records else "NO_RETAINED_EVENT_CONTEXT"),
            "non_voting": True, "historical_use_allowed": False,
        }
    product.pop("artifact_identity", None)
    product.pop("artifact_sha256", None)
    if product.get("contract_version") == "investment_decision_workspace_projection/v1":
        from investment_decision_workspace_projection import content_identity
    elif product.get("contract_version") == "daily_integrated_decision_brief/v1":
        from daily_integrated_decision_brief import content_identity
    else:
        raise ValueError("CURRENT_OVERLAY_PRODUCT_CONTRACT_UNSUPPORTED")
    product.update(content_identity(product))
    return product


@dataclass(frozen=True)
class CorporateCurrencyRollforwardResult:
    """Immutable captured bytes prevent a downstream second latest/path lookup."""
    receipt_bytes: bytes
    current_context_bytes: bytes | None
    frozen_market_selection_bytes: bytes | None

    def receipt(self):
        return json.loads(self.receipt_bytes)

    def current_context(self):
        return json.loads(self.current_context_bytes) if self.current_context_bytes else None

    def bind_frozen_market_selection(self, selection: dict | None, failure_reason: str | None = None):
        receipt = self.receipt()
        if receipt.get("frozen_market_context") == selection and failure_reason is None:
            return self
        receipt["frozen_market_context"] = selection
        if failure_reason is not None:
            receipt["frozen_market_selection_failure"] = failure_reason
        return CorporateCurrencyRollforwardResult(_bytes(receipt), self.current_context_bytes,
                                                  _bytes(selection) if selection else None)


def rollforward(root: Path, *, target_market_session: str, observed_at: datetime,
                allow_acquisition: bool, frozen_market_selection: dict | None = None,
                prior_descriptive_max_age_days: int | None = None,
                acquire_fn=None, materialize_fn=None, verify_fn=None) -> CorporateCurrencyRollforwardResult:
    """One explicit attempt, or verified same-day reuse. No loop until success.

    Prior fallback requires an explicit caller-governed age allowance. None means
    fallback is disabled; this module invents no default corporate freshness rule.
    Injected acquisition seams are for offline tests, not a second fetch engine.
    """
    if observed_at.tzinfo is None:
        raise ValueError("KNOWLEDGE_TIME_MUST_BE_TIMEZONE_AWARE")
    datetime.strptime(target_market_session, "%Y-%m-%d")
    if prior_descriptive_max_age_days is not None and prior_descriptive_max_age_days < 0:
        raise ValueError("INVALID_PRIOR_DESCRIPTIVE_AGE_POLICY")
    observed = observed_at.astimezone(VN)
    civil = observed.date().isoformat()
    acquire_fn = acquire_fn or acquisition.acquire
    materialize_fn = materialize_fn or acquisition.materialize_current_official_event_context
    verify_fn = verify_fn or acquisition.verify_successful_acquisition
    manifest_path = root / acquisition.SESSIONS_RELATIVE / civil / acquisition.ATTEMPT_FILENAME
    attempt = None
    prior = None
    budget = AcquisitionBudget()
    selected = None
    context_bytes = None
    failure = None
    action = "REUSED_CURRENT_SUCCESS"
    attempted = False
    integrity = "NOT_SELECTED"
    receipt = dict(contract_version="corporate_currency_rollforward/v1",
                   target_market_session=target_market_session,
                   knowledge_observed_at=observed.isoformat(), acquisition_civil_date=civil,
                   selection_lane="CURRENT_RESEARCH_KNOWLEDGE_OVERLAY",
                   frozen_market_context=frozen_market_selection,
                   historical_use_allowed=False, authority_effect="NONE / CURRENT_RESEARCH_EVIDENCE_ONLY",
                   prior_descriptive_max_age_days=prior_descriptive_max_age_days)

    def select(candidate):
        verified = verify_fn(root, candidate["acquisition_session"])
        known = datetime.fromisoformat(candidate["acquired_at"])
        if known.tzinfo is None or known > observed:
            raise ValueError("FUTURE_OR_UNQUALIFIED_KNOWLEDGE_TIME")
        result = materialize_fn(root, acquisition_session=candidate["acquisition_session"])
        path = (root / result["output_path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("CONTEXT_PATH_OUTSIDE_RETAINED_ROOT")
        raw = path.read_bytes()
        context = json.loads(raw)
        if context.get("artifact_identity") != result["artifact_identity"]:
            raise ValueError("SELECTED_CONTEXT_IDENTITY_MISMATCH")
        import current_official_event_context
        current_official_event_context.replay(context)
        if not context_known_by(context, observed):
            raise ValueError("FUTURE_OR_UNQUALIFIED_EVENT_KNOWLEDGE_TIME")
        return verified, result, raw, known

    try:
        attempt = acquisition._load(manifest_path)
        prior = acquisition.latest_successful_session(root)
        if not attempt or attempt.get("disposition") != acquisition.SUCCESS:
            if not allow_acquisition:
                raise ValueError("CURRENT_ACQUISITION_DISABLED")
            # Never backdate a live acquisition from an injected/historical observation clock.
            if acquire_fn is acquisition.acquire and civil != acquisition.vn_today():
                raise ValueError("LIVE_ACQUISITION_CIVIL_DATE_MISMATCH")
            attempted = True
            window = ((observed.date()-timedelta(days=30)).isoformat(),
                      (observed.date()+timedelta(days=14)).isoformat())
            attempt = acquire_fn(root, session=civil, budget=budget, hnx_rights_window=window)
            if acquire_fn is acquisition.acquire:
                observed = datetime.fromisoformat(acquisition.vn_now_iso()).astimezone(VN)
                receipt["knowledge_observed_at"] = observed.isoformat()
            action = "ACQUIRED_CURRENT_SUCCESS"
        if attempt.get("disposition") != acquisition.SUCCESS:
            raise ValueError(attempt.get("error_message") or "ACQUISITION_FAILED")
        selected = select(attempt)
        integrity = "VERIFIED"
        if action == "REUSED_CURRENT_SUCCESS" and not selected[1].get("materialization_reused"):
            action = "RECOVERED_MATERIALIZATION_FROM_RETAINED_SUCCESS"
    except Exception as exc:
        failure = str(exc)
        action = "REFRESH_FAILED_NO_USABLE_CURRENT_CONTEXT"
        # Corrupt same-date SUCCESS never triggers refetch or a silent alternate selection.
        retained_success = bool(attempt and attempt.get("disposition") == acquisition.SUCCESS)
        integrity = "FAILED" if retained_success else "NOT_SELECTED"
        if not retained_success and prior and prior.get("acquisition_session") != civil:
            try:
                known = datetime.fromisoformat(prior["acquired_at"])
                age = (observed-known).total_seconds()/86400
                if prior_descriptive_max_age_days is not None and 0 <= age <= prior_descriptive_max_age_days:
                    selected = select(prior)
                    action = "REFRESH_FAILED_REUSED_PRIOR_CURRENT_RESEARCH"
                    integrity = "VERIFIED_PRIOR"
            except Exception as prior_error:
                failure += ";PRIOR_INTEGRITY_FAILURE:" + str(prior_error)
    usage = (attempt or {}).get("budget_usage") or budget.report()
    receipt.update(refresh_action=action, acquisition_attempted=attempted, failure_reason=failure,
                   integrity_verification=integrity,
                   budget_policy_identity="sha256:"+hashlib.sha256(_bytes(usage.get("limits", {}))).hexdigest(),
                   request_count=usage.get("request_count", 0), retained_byte_count=usage.get("downloaded_bytes", 0),
                   page_count=sum(r.get("page") is not None for r in usage.get("requests", [])),
                   previous_success_identity=("sha256:"+hashlib.sha256(_bytes(prior)).hexdigest()) if prior else None,
                   refresh_attempt_identity=("sha256:"+hashlib.sha256(_bytes(attempt)).hexdigest()) if attempt else None,
                   refresh_attempt_path=(acquisition.SESSIONS_RELATIVE / civil / acquisition.ATTEMPT_FILENAME).as_posix() if attempt else None,
                   acquisition_attempt_identity=None, acquisition_attempt_path=None, acquired_at=None,
                   current_research_context=None, selected_acquisition_session=None,
                   freshness_state="UNAVAILABLE", source_age_seconds=None)
    if selected:
        verified, result, context_bytes, known = selected
        selected_attempt = verified["attempt"]
        receipt.update(selected_acquisition_session=selected_attempt["acquisition_session"],
                       acquisition_attempt_identity=verified["attempt_identity"],
                       acquisition_attempt_path=(acquisition.SESSIONS_RELATIVE / selected_attempt["acquisition_session"] / acquisition.ATTEMPT_FILENAME).as_posix(),
                       current_research_context=dict(path=result["output_path"], artifact_identity=result["artifact_identity"],
                                                     bytes_sha256=hashlib.sha256(context_bytes).hexdigest()),
                       acquired_at=known.isoformat(), source_age_seconds=(observed-known).total_seconds(),
                       freshness_state="CURRENT_CIVIL_DATE" if known.astimezone(VN).date() == observed.date() else "PRIOR_DESCRIPTIVE_STALE")
    return CorporateCurrencyRollforwardResult(_bytes(receipt), context_bytes,
                                              _bytes(frozen_market_selection) if frozen_market_selection else None)
