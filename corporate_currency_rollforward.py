"""One-invocation selection of non-voting current corporate knowledge.

No consumer calls acquire. The frozen market selection is carried separately and
never inferred from the current overlay. Canonical orchestration owns invocation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import official_corporate_event_incremental_acquisition as acquisition
from official_acquisition_budget import AcquisitionBudget

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


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
    attempt = acquisition._load(manifest_path)
    prior = acquisition.latest_successful_session(root)
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
        return verified, result, raw, known

    try:
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
