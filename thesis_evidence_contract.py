"""Offline evidence vocabulary and invariants. No action or numerical judgment."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import re

ITEM_VERSION = "evidence_item/v1"
REGISTRY_VERSION = "thesis_adapter_registry/v1"
AUTHORITY = "NONE / OFFLINE_DETERMINISTIC_THESIS_ORGANIZATION_ONLY"
STATES = ("SUPPORTS", "OPPOSES", "NEUTRAL", "MIXED", "UNKNOWN", "NOT_APPLICABLE")
UNKNOWN_CLASSES = ("MISSING", "IMMATURE", "UNQUALIFIED", "STALE", "POLICY_NOT_AUTHORIZED",
    "PRIMARY_EVIDENCE_MISSING", "CONTEXT_ONLY", "HIGHER_TIMEFRAME_UNKNOWN", "UNRESOLVED", "AUTHORITY_LIMITED")
ROLES = ("PRIMARY", "SECONDARY", "CONTEXT")
LENSES = ("LONG_TERM_INVESTOR", "SHORT_TERM_INVESTOR")
STAGES = ("T0_SEALED", "POST_T0_ENRICHED")
VIEWS = ("T0_THESIS_VIEW", "CURRENT_RESEARCH_VIEW")
AXES = ("TECHNICAL", "VOLUME", "PARTICIPANT_FLOW", "FUNDAMENTAL", "VALUATION",
    "CORPORATE_FORWARD", "MACRO_SECTOR", "LIQUIDITY_PORTFOLIO", "EVIDENCE_QUALITY")
LENS_STATES = ("SUPPORTIVE", "NOT_CONFIRMED", "CONTESTED", "ADVERSE", "INSUFFICIENT_EVIDENCE")
FRESH = ("CURRENT_SESSION", "FRESH_COMPLETED_PERIOD", "CURRENT_REPORTING_PERIOD")
# Exact aliases and token families, including camelCase and punctuation variants.
FORBIDDEN = {"score", "weight", "confidence", "probability", "rank", "rating", "conviction", "target",
    "priorityscore", "overall", "overallscore", "overallrating", "certainty", "likelihood",
    "recommendation", "buysell", "signalstrength", "stars", "grade", "alphaestimate", "forecastreturn"}
JUDGMENT_TOKENS = {"score", "scores", "weight", "weights", "weighted", "confidence", "probability",
    "probabilities", "rank", "ranking", "rating", "conviction", "target", "certainty", "likelihood"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def seal(value, kind):
    body = {k: v for k, v in value.items() if k not in {"artifact_identity", "artifact_sha256"}}
    digest = hashlib.sha256(canonical(body).encode()).hexdigest()
    return {**body, "artifact_sha256": digest, "artifact_identity": kind + ":" + digest}


def verify_identity(value, kind):
    expected = seal(value, kind)
    if any(value.get(k) != expected[k] for k in ("artifact_identity", "artifact_sha256")):
        raise ValueError("THESIS_CONTENT_IDENTITY_INVALID:" + kind)


def scan_forbidden(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            words = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(key)).lower()
            tokens = set(re.findall(r"[a-z]+", words))
            normalized = "".join(re.findall(r"[a-z]+", words))
            if normalized in FORBIDDEN or tokens & JUDGMENT_TOKENS:
                raise ValueError("THESIS_FORBIDDEN_JUDGMENT_FIELD:" + path + "/" + str(key))
            scan_forbidden(child, path + "/" + str(key))
    elif isinstance(value, list):
        for n, child in enumerate(value): scan_forbidden(child, path + "/" + str(n))
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("THESIS_NON_FINITE_FACT:" + path)


def checked(value, vocabulary, name):
    if value not in vocabulary: raise ValueError("THESIS_UNMAPPED_VOCABULARY:" + name + ":" + str(value))
    return value


def make_item(*, ticker, session, source, axis, sub_axis, state="UNKNOWN", unknown_class="MISSING",
              role="CONTEXT", lens_roles=None, horizon="UNSPECIFIED", correlation_group=None,
              canonical_evidence_key=None, common_cause_key=None, freshness="UNAVAILABLE", basis="UNSPECIFIED",
              authority_ceiling=None, fact_eligible=False, direction_eligible=False,
              reasons=(), blockers=(), coverage=None, facts=(), relations=(), stage="POST_T0_ENRICHED",
              seal_reference=None, materiality="UNASSESSED", confirmation_pointers=(), invalidation_pointers=()):
    correlation_group = correlation_group or ticker + ":" + axis + ":" + sub_axis
    cause = common_cause_key or correlation_group
    key = canonical_evidence_key or correlation_group + ":" + horizon
    authority_ceiling=authority_ceiling or ("SEALED_RESEARCH_ONLY_NO_BACKTEST_AUTHORITY" if stage=="T0_SEALED" else "CURRENT_RESEARCH_VIEW_ONLY")
    # A fact is a typed value, not an unqualified numeric payload.
    result = dict(contract_version=ITEM_VERSION, subject={"ticker": ticker, "session": session},
        source=copy.deepcopy(source), axis=axis, sub_axis=sub_axis, role=role,
        lens_binding=lens_roles or {lens: role for lens in LENSES}, state=state,
        unknown_class=unknown_class if state == "UNKNOWN" else None,
        reason_codes=sorted(set(reasons)), blocker_codes=sorted(set(blockers)), knowledge_stage=stage,
        seal_reference=seal_reference, horizon=horizon, correlation_group=correlation_group,
        canonical_evidence_key=key, common_cause_key=cause, freshness=freshness,
        basis=copy.deepcopy(basis), authority_ceiling=authority_ceiling,
        fitness={"fact_eligible": fact_eligible, "direction_eligible": direction_eligible},
        relations=copy.deepcopy(list(relations)), confirmation_pointers=list(confirmation_pointers),
        invalidation_pointers=list(invalidation_pointers), coverage=copy.deepcopy(coverage or {}),
        factual_values=copy.deepcopy(list(facts)), facts_present=bool(facts), materiality=materiality,
        non_voting=True, is_actionable=False)
    scan_forbidden(result)
    result = seal(result, ITEM_VERSION)
    verify_item(result)
    return result


def verify_item(item):
    scan_forbidden(item)
    verify_identity(item, ITEM_VERSION)
    required={"contract_version","subject","source","axis","sub_axis","role","lens_binding","state","unknown_class",
        "reason_codes","blocker_codes","knowledge_stage","seal_reference","horizon","correlation_group","canonical_evidence_key",
        "common_cause_key","freshness","basis","authority_ceiling","fitness","relations","confirmation_pointers","invalidation_pointers",
        "coverage","factual_values","facts_present","materiality","non_voting","is_actionable","artifact_identity","artifact_sha256"}
    if set(item)!=required or set(item["source"])!={"identity","contract_version","pointer"}:
        raise ValueError("THESIS_ITEM_SCHEMA_UNSUPPORTED")
    if set(item["fitness"])!={"fact_eligible","direction_eligible"} or any(type(v)!=bool for v in item["fitness"].values()):
        raise ValueError("THESIS_FITNESS_BOOLEAN_REQUIRED")
    if any(not isinstance(item[k],str) or not item[k] for k in ("correlation_group","canonical_evidence_key","common_cause_key","horizon")):
        raise ValueError("THESIS_CORRELATION_BINDING_REQUIRED")
    checked(item.get("contract_version"), (ITEM_VERSION,), "item_version")
    checked(item.get("state"), STATES, "state")
    checked(item.get("role"), ROLES, "role")
    checked(item.get("axis"), AXES, "axis")
    checked(item.get("knowledge_stage"), STAGES, "stage")
    if set(item["lens_binding"]) != set(LENSES): raise ValueError("THESIS_LENS_BINDING_INVALID")
    for role in item["lens_binding"].values(): checked(role, ROLES, "lens_role")
    if item["state"] == "UNKNOWN": checked(item["unknown_class"], UNKNOWN_CLASSES, "unknown_class")
    elif item["unknown_class"] is not None: raise ValueError("THESIS_UNKNOWN_CLASS_ON_KNOWN_STATE")
    if not item["source"].get("contract_version") or not item["source"].get("pointer") or not item["source"].get("identity"):
        raise ValueError("THESIS_SOURCE_POINTER_REQUIRED")
    if item["non_voting"] is not True or item["is_actionable"] is not False: raise ValueError("THESIS_ACTION_BOUNDARY")
    if item["fitness"]["direction_eligible"]:
        if item["axis"] in {"VOLUME","PARTICIPANT_FLOW","CORPORATE_FORWARD","LIQUIDITY_PORTFOLIO","EVIDENCE_QUALITY"}:
            raise ValueError("THESIS_FACTS_ONLY_AXIS_CANNOT_VOTE")
        if item["sub_axis"] in {"patterns","volatility","morphology","technical_native_volume_copy"}:
            raise ValueError("THESIS_CONTEXT_PRIMITIVE_CANNOT_VOTE")
        if "RAW_AS_TRADED" in canonical(item["basis"]) and (not isinstance(item["basis"],dict) or
                (item["basis"].get("corporate_action_comparability") or {}).get("comparability") != "PIT_NORMALIZED"):
            raise ValueError("THESIS_RAW_DIRECTION_AUTHORITY_INSUFFICIENT")
        if (item["state"] not in {"SUPPORTS", "OPPOSES", "NEUTRAL", "MIXED"} or item["freshness"] not in FRESH
                or not item["fitness"]["fact_eligible"]): raise ValueError("THESIS_DIRECTION_FITNESS_INVALID")
        if item["role"] == "CONTEXT" and all(r == "CONTEXT" for r in item["lens_binding"].values()):
            raise ValueError("THESIS_CONTEXT_CANNOT_VOTE")
    if item["knowledge_stage"] == "T0_SEALED" and (not item["seal_reference"] or "RETROSPECTIVE" in canonical(item["basis"])):
        raise ValueError("THESIS_T0_SEAL_OR_BASIS_INVALID")
    for fact in item["factual_values"]:
        if set(fact) != {"name", "value", "semantic", "unit", "fitness", "source_pointer"}:
            raise ValueError("THESIS_FACT_METADATA_REQUIRED")
        if not fact["semantic"] or not fact["unit"] or not fact["source_pointer"]:
            raise ValueError("THESIS_FACT_PROVENANCE_REQUIRED")
        scan_forbidden({fact["name"]:fact["value"],fact["semantic"]:None,fact["unit"]:None})
    return item


class SealedEvidenceBindings:
    """Only the full verified snapshot establishes knowledge stage; labels never do."""
    def __init__(self, snapshot):
        import prospective_decision_retention as retention
        if not retention.validate_snapshot(snapshot): raise ValueError("THESIS_SEALED_SNAPSHOT_INVALID")
        self.identity = snapshot["snapshot_identity"]
        self.sources = set()
        for ticker, row in snapshot["records"].items():
            product = row.get("integrated_decision_at_t0") or {}
            session = row["decision_session"]
            if product.get("decision_identity"):
                self.sources.add((ticker, session, product["decision_identity"]))
            context = (product.get("contextual_technical_context") or {}).get("projection")
            if context:
                import contextual_technical_dispatch as dispatch
                dispatch.verify_context(context, ticker=ticker, session=session)
                self.sources.add((ticker, session, context["artifact_identity"]))

    def contains(self, ticker, session, identity):
        return (ticker, session, identity) in self.sources

    def verify(self, item):
        if item["knowledge_stage"] == "T0_SEALED" and (item["seal_reference"] != self.identity or not self.contains(
                item["subject"]["ticker"], item["subject"]["session"], item["source"]["identity"])):
            raise ValueError("THESIS_T0_SOURCE_NOT_SEALED")
