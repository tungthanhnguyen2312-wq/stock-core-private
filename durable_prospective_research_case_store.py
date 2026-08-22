"""Local append-only durable storage for prospective research cases.

The store is deliberately path-explicit and production-independent.  It stores
immutable T0 envelopes plus separate immutable update-event files, verifies
every content identity on read, and delegates all case/ledger semantics to the
existing prospective research-case contract.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from prospective_research_case_learning_ledger import append_case_update, build_learning_ledger


METHOD = "durable_prospective_research_case_store/v1"
STORE_FILENAME = "store_contract.json"


class DurableCaseStoreError(ValueError):
    """Fail-closed durable-store integrity or append error."""


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise DurableCaseStoreError("INVALID_EVENT_TIMESTAMP") from exc


def _case_identity_valid(case: Mapping[str, Any]) -> bool:
    body = dict(case)
    case_id = body.pop("case_id", None)
    content_identity = body.pop("case_content_identity", None)
    expected = "prospective_research_case:" + _hash(body)
    return case_id == expected and content_identity == expected


def _update_identity_valid(update: Mapping[str, Any]) -> bool:
    body = dict(update)
    identity = body.pop("update_identity", None)
    return identity == "prospective_case_update:" + _hash(body)


def _history_identity(history: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(history)
    result["case_history_identity"] = "prospective_case_history:" + _hash(result)
    return result


class DurableProspectiveResearchCaseStore:
    """One-writer, append-only local store.  The caller must choose its root."""

    def __init__(self, root: Path | str, *, registered_update_evidence_identities: Sequence[str] = ()) -> None:
        self.root = Path(root).resolve()
        self.cases_dir = self.root / "cases"
        self.events_dir = self.root / "events"
        self.lock_path = self.root / ".writer.lock"
        self.registered_update_evidence_identities = frozenset(registered_update_evidence_identities)
        if not all(isinstance(item, str) and item for item in self.registered_update_evidence_identities):
            raise DurableCaseStoreError("INVALID_RETAINED_UPDATE_EVIDENCE_IDENTITY")
        self.root.mkdir(parents=True, exist_ok=True)
        self.cases_dir.mkdir(exist_ok=True)
        self.events_dir.mkdir(exist_ok=True)
        self._initialize_or_verify_contract()

    def _contract(self) -> dict[str, Any]:
        payload = {
            "schema_version": "1.0.0", "contract_version": METHOD,
            "storage_boundary": "EXPLICIT_LOCAL_NON_PRODUCTION_ARTIFACT_STORE",
            "writer_model": "LOCAL_ONE_WRITER_EXCLUSIVE_LOCK",
            "case_storage": "IMMUTABLE_CONTENT_ADDRESSED_ENVELOPES",
            "event_storage": "IMMUTABLE_APPEND_ONLY_CONTENT_ADDRESSED_EVENTS",
            "authority_boundary": {"production_database": "NOT_USED", "recommendation_portfolio_execution": "NOT_EMITTED"},
        }
        payload["store_contract_identity"] = "durable_case_store_contract:" + _hash(payload)
        return payload

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DurableCaseStoreError("STORE_RECORD_UNREADABLE_OR_TAMPERED") from exc
        if not isinstance(value, dict):
            raise DurableCaseStoreError("STORE_RECORD_NOT_OBJECT")
        return value

    @staticmethod
    def _write_new_json(path: Path, payload: Mapping[str, Any]) -> None:
        data = (_canon(payload) + "\n").encode("utf-8")
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError as exc:
            raise DurableCaseStoreError("DUPLICATE_CONTENT_INSERTION") from exc
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def _initialize_or_verify_contract(self) -> None:
        contract_path = self.root / STORE_FILENAME
        expected = self._contract()
        if contract_path.exists():
            if self._read_json(contract_path) != expected:
                raise DurableCaseStoreError("STORE_CONTRACT_IDENTITY_MISMATCH")
            return
        try:
            self._write_new_json(contract_path, expected)
        except DurableCaseStoreError:
            if not contract_path.exists() or self._read_json(contract_path) != expected:
                raise

    @contextmanager
    def _writer(self) -> Iterator[None]:
        try:
            descriptor = os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError as exc:
            raise DurableCaseStoreError("STORE_WRITER_LOCKED") from exc
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write("local-one-writer\n")
                handle.flush()
                os.fsync(handle.fileno())
            yield
        finally:
            self.lock_path.unlink(missing_ok=True)

    @staticmethod
    def _case_path(case_id: str, directory: Path) -> Path:
        return directory / (hashlib.sha256(case_id.encode("utf-8")).hexdigest() + ".json")

    @staticmethod
    def _event_path(event_id: str, directory: Path) -> Path:
        return directory / (hashlib.sha256(event_id.encode("utf-8")).hexdigest() + ".json")

    def _event(self, *, case_id: str, event_type: str, observed_at: str, known_at: str, actor_or_source: str,
               evidence_references: Sequence[str], prior_event_id: str | None, payload: Mapping[str, Any], fixture: bool) -> dict[str, Any]:
        _timestamp(observed_at); _timestamp(known_at)
        body = {
            "schema_version": "1.0.0", "contract_version": METHOD + "/event", "case_id": case_id,
            "event_type": event_type, "observed_at": observed_at, "known_at": known_at,
            "actor_or_source": actor_or_source, "evidence_references": list(evidence_references),
            "prior_event_id": prior_event_id, "payload": dict(payload), "fixture": fixture,
        }
        event_id = "durable_research_case_event:" + _hash(body)
        body["event_id"] = event_id
        body["content_identity"] = event_id
        return body

    @staticmethod
    def _verify_event(event: Mapping[str, Any]) -> None:
        body = dict(event)
        event_id = body.pop("event_id", None)
        content_identity = body.pop("content_identity", None)
        expected = "durable_research_case_event:" + _hash(body)
        if event_id != expected or content_identity != expected:
            raise DurableCaseStoreError("EVENT_CONTENT_IDENTITY_INVALID")
        _timestamp(str(event.get("observed_at"))); _timestamp(str(event.get("known_at")))

    def _t0_events(self, case: Mapping[str, Any], draft: Mapping[str, Any], validation: Mapping[str, Any], human_review: Mapping[str, Any]) -> list[dict[str, Any]]:
        known_at = case["known_at"]
        created = self._event(case_id=case["case_id"], event_type="CASE_CREATED", observed_at=known_at, known_at=known_at,
                              actor_or_source="WORKBENCH_CREATE_CASE", evidence_references=case["original_evidence_ids"], prior_event_id=None,
                              payload={"case_content_identity": case["case_content_identity"], "source_decision_workflow_identity": case["source_decision_workflow_identity"],
                                       "source_ai_input_identity": case["source_ai_input_identity"]}, fixture=bool(draft.get("fixture", False)))
        validated = self._event(case_id=case["case_id"], event_type="AI_DRAFT_VALIDATED", observed_at=known_at, known_at=known_at,
                                actor_or_source="DETERMINISTIC_VALIDATOR", evidence_references=[], prior_event_id=created["event_id"],
                                payload={"draft": dict(draft), "validation": dict(validation)}, fixture=bool(draft.get("fixture", False)))
        review = self._event(case_id=case["case_id"], event_type="HUMAN_REVIEW_RECORDED", observed_at=known_at, known_at=known_at,
                             actor_or_source=str(human_review.get("reviewer", {}).get("identity") or "HUMAN_REVIEWER"),
                             evidence_references=[human_review["source_ai_input_identity"]], prior_event_id=validated["event_id"],
                             payload={"human_review": dict(human_review)}, fixture=bool(draft.get("fixture", False)))
        events = [created, validated, review]
        prior = review["event_id"]
        for edit in human_review.get("human_modifications", []):
            event = self._event(case_id=case["case_id"], event_type="HUMAN_EDIT_RECORDED", observed_at=known_at, known_at=known_at,
                                actor_or_source=str(edit.get("reviewer_identity") or "HUMAN_REVIEWER"), evidence_references=[], prior_event_id=prior,
                                payload={"human_edit": dict(edit), "human_review_identity": human_review["review_packet_identity"]}, fixture=bool(draft.get("fixture", False)))
            events.append(event); prior = event["event_id"]
        return events

    def persist_case(self, case: Mapping[str, Any], draft: Mapping[str, Any], validation: Mapping[str, Any], human_review: Mapping[str, Any]) -> dict[str, Any]:
        """Persist one immutable T0 case and all T0 provenance in one envelope."""
        if not _case_identity_valid(case):
            raise DurableCaseStoreError("CASE_CONTENT_IDENTITY_INVALID")
        if validation.get("validation_status") != "VALID" or validation.get("validation_identity") != case["ai_human_provenance"]["validation_identity"]:
            raise DurableCaseStoreError("CASE_VALIDATION_PROVENANCE_INVALID")
        if human_review.get("review_packet_identity") != case["ai_human_provenance"]["human_review_identity"]:
            raise DurableCaseStoreError("CASE_HUMAN_REVIEW_PROVENANCE_INVALID")
        events = self._t0_events(case, draft, validation, human_review)
        envelope = {
            "schema_version": "1.0.0", "contract_version": METHOD + "/case_envelope", "record_type": "IMMUTABLE_T0_CASE",
            "case": dict(case), "ai_draft": dict(draft), "validation": dict(validation), "human_review": dict(human_review),
            "initial_events": events, "storage_boundary": "LOCAL_NON_PRODUCTION_RESEARCH_CASE_RECORD",
        }
        envelope["content_identity"] = "durable_research_case_envelope:" + _hash(envelope)
        path = self._case_path(case["case_id"], self.cases_dir)
        with self._writer():
            self._write_new_json(path, envelope)
        return self.load_case_envelope(case["case_id"])

    def load_case_envelope(self, case_id: str) -> dict[str, Any]:
        path = self._case_path(case_id, self.cases_dir)
        if not path.exists():
            raise DurableCaseStoreError("CASE_NOT_FOUND")
        envelope = self._read_json(path)
        body = dict(envelope); identity = body.pop("content_identity", None)
        if identity != "durable_research_case_envelope:" + _hash(body):
            raise DurableCaseStoreError("CASE_ENVELOPE_CONTENT_IDENTITY_INVALID")
        if envelope.get("case", {}).get("case_id") != case_id or not _case_identity_valid(envelope["case"]):
            raise DurableCaseStoreError("CASE_CONTENT_IDENTITY_INVALID")
        for event in envelope.get("initial_events", []):
            self._verify_event(event)
        return envelope

    def list_case_ids(self) -> list[str]:
        identifiers = []
        for path in sorted(self.cases_dir.glob("*.json")):
            raw = self._read_json(path).get("case", {}).get("case_id")
            if isinstance(raw, str):
                self.load_case_envelope(raw)
            identifiers.append(raw)
        if any(not isinstance(case_id, str) for case_id in identifiers) or len(set(identifiers)) != len(identifiers):
            raise DurableCaseStoreError("DUPLICATE_OR_INVALID_CASE_ID")
        return sorted(identifiers)

    def _case_events(self, case_id: str) -> list[dict[str, Any]]:
        initial = list(self.load_case_envelope(case_id)["initial_events"])
        appended = []
        for path in sorted(self.events_dir.glob("*.json")):
            event = self._read_json(path)
            self._verify_event(event)
            if event.get("case_id") == case_id:
                appended.append(event)
        events = initial + appended
        by_id = {event["event_id"]: event for event in events}
        if len(by_id) != len(events):
            raise DurableCaseStoreError("DUPLICATE_EVENT_ID")
        children: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            prior = event.get("prior_event_id")
            if prior is not None and prior not in by_id:
                raise DurableCaseStoreError("EVENT_PRIOR_LINK_UNKNOWN")
            children[prior].append(event)
        if len(children[None]) != 1:
            raise DurableCaseStoreError("EVENT_CHAIN_ROOT_INVALID")
        ordered = []
        current = children[None][0]
        while True:
            ordered.append(current)
            successors = children.get(current["event_id"], [])
            if not successors:
                break
            if len(successors) != 1:
                raise DurableCaseStoreError("CONCURRENT_CONFLICTING_APPEND")
            current = successors[0]
        if len(ordered) != len(events):
            raise DurableCaseStoreError("EVENT_CHAIN_DISCONNECTED")
        return ordered

    def append_case_update(self, case_id: str, update: Mapping[str, Any], *, lifecycle_state: str) -> dict[str, Any]:
        """Append one verified later update; neither T0 nor previous events are rewritten."""
        envelope = self.load_case_envelope(case_id)
        case = envelope["case"]
        if update.get("case_id") != case_id or not _update_identity_valid(update):
            raise DurableCaseStoreError("UPDATE_CONTENT_IDENTITY_INVALID")
        fixture = bool(update.get("fixture"))
        source = str(update.get("source_evidence_identity") or "")
        if fixture:
            if update.get("evidence_kind") != "TEST_FIXTURE" or not source.startswith("fixture:"):
                raise DurableCaseStoreError("TEST_FIXTURE_EVIDENCE_IDENTITY_REQUIRED")
        elif source not in self.registered_update_evidence_identities:
            raise DurableCaseStoreError("UPDATE_EVIDENCE_IDENTITY_NOT_REGISTERED")
        events = self._case_events(case_id)
        previous_updates = [event["payload"]["update"] for event in events if event["event_type"] == "CASE_UPDATE"]
        try:
            history = append_case_update(case, previous_updates, update, lifecycle_state=lifecycle_state)
        except ValueError as exc:
            raise DurableCaseStoreError(str(exc)) from exc
        event = self._event(case_id=case_id, event_type="CASE_UPDATE", observed_at=update["observed_at"], known_at=update["known_at"],
                            actor_or_source=source, evidence_references=[source], prior_event_id=events[-1]["event_id"],
                            payload={"update": dict(update), "lifecycle_state": lifecycle_state}, fixture=fixture)
        path = self._event_path(event["event_id"], self.events_dir)
        with self._writer():
            self._write_new_json(path, event)
        return history

    def replay_case(self, case_id: str) -> dict[str, Any]:
        """Verify all records and reconstruct the same deterministic case history."""
        envelope = self.load_case_envelope(case_id)
        case = envelope["case"]
        events = self._case_events(case_id)
        updates: list[Mapping[str, Any]] = []
        lifecycle_state = case["lifecycle_state"]
        for event in events:
            if event["event_type"] == "CASE_UPDATE":
                update = event["payload"].get("update")
                if not isinstance(update, Mapping):
                    raise DurableCaseStoreError("CASE_UPDATE_PAYLOAD_INVALID")
                updates.append(update)
                lifecycle_state = event["payload"].get("lifecycle_state")
        if updates:
            try:
                history = append_case_update(case, updates[:-1], updates[-1], lifecycle_state=lifecycle_state)
            except ValueError as exc:
                raise DurableCaseStoreError(str(exc)) from exc
        else:
            history = _history_identity({
                "schema_version": "1.0.0", "contract_version": "prospective_research_case_learning_ledger/v1/case_history",
                "case": dict(case), "updates": [], "lifecycle_state": lifecycle_state,
                "authority_boundary": {"original_case_immutable": True, "updates_append_only": True,
                                       "price_movement_not_thesis_proof": True, "investment_authority": "NOT_EMITTED"},
            })
        claim_status = {claim["claim_id"]: "UNRESOLVED" for claim in case["original_claims"]}
        scenario_status: dict[str, str] = {}; catalyst_status: dict[str, str] = {}
        for update in updates:
            for relationship in update["relationships"]:
                claim_status[relationship["original_claim_id"]] = relationship["claim_outcome"]
            for item in update["scenario_updates"]:
                scenario_status[item["original_evidence_id"]] = item["state"]
            for item in update["catalyst_updates"]:
                catalyst_status[item["original_evidence_id"]] = item["state"]
        return {
            "contract_version": METHOD + "/replay", "case_id": case_id, "case": dict(case), "events": events,
            "history": history, "current_lifecycle_state": lifecycle_state, "claim_status": claim_status,
            "scenario_status": scenario_status, "catalyst_status": catalyst_status,
            "ai_human_provenance": dict(case["ai_human_provenance"]),
            "replay_identity": "durable_case_replay:" + _hash({"case_id": case_id, "history_identity": history["case_history_identity"], "events": [event["event_id"] for event in events]}),
        }

    def replay_all_histories(self) -> list[dict[str, Any]]:
        return [self.replay_case(case_id)["history"] for case_id in self.list_case_ids()]

    def build_learning_ledger(self) -> dict[str, Any]:
        histories = []
        for case_id in self.list_case_ids():
            envelope = self.load_case_envelope(case_id)
            if envelope["ai_draft"].get("fixture") or str(envelope["ai_draft"].get("draft_identity", "")).startswith("TEST_FIXTURE:"):
                continue
            histories.append(self.replay_case(case_id)["history"])
        return build_learning_ledger(histories)

    def live_readiness(self) -> dict[str, Any]:
        identifiers = self.list_case_ids()
        non_fixture_count = sum(
            not (self.load_case_envelope(case_id)["ai_draft"].get("fixture")
                 or str(self.load_case_envelope(case_id)["ai_draft"].get("draft_identity", "")).startswith("TEST_FIXTURE:"))
            for case_id in identifiers
        )
        return {
            "verdict": "DURABLE_CASE_SYSTEM_READY", "storage_boundary": "EXPLICIT_LOCAL_NON_PRODUCTION_ARTIFACT_STORE",
            "prerequisites": ["VALIDATED_AI_DRAFT", "QUALIFYING_RECORDED_HUMAN_REVIEW", "EXPLICIT_STORE_ROOT", "REGISTERED_LATER_EVIDENCE_FOR_NON_FIXTURE_UPDATES"],
            "current_durable_case_count": len(identifiers), "current_non_fixture_case_count": non_fixture_count,
            "authority_boundary": {"production_persistence": "NOT_INTRODUCED", "investment_authority": "NOT_EMITTED"},
        }
