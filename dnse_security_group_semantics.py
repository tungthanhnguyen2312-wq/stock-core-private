"""Deterministic, evidence-scoped refinement of DNSE UNKNOWN_SECURITY_GROUP records into a more
specific instrument class -- only where the record's own retained raw_security_group_id and/or
name field directly evidence that class.

This module never modifies dnse_instrument_universe.py (the production security-master
classifier) or its EQUITY/UNKNOWN_SECURITY_GROUP output; it is a strictly additive, optional
downstream refinement over already-classified, already-retained records. It performs no network
or database access and accepts no live input -- every mapping below was established by directly
inspecting each raw_security_group_id code's own populated `name` field(s) in the retained
2026-08-12 DNSE security-master snapshot
(operations-review/dnse-market-data-lake-v2-20260812/.../universe/5c61b853....parquet); see
docs/dnse_security_group_semantics_contract.md for the full evidence record and exact counts.

EVIDENCE METHOD, PER CODE (never ticker/symbol pattern, frequency, or guess)
    A code is mapped here only when every member's own populated `name` field, where present,
    consistently and unambiguously names the same instrument class in first-party Vietnamese text
    (e.g. "Chung quyen" = covered warrant; "HDTL" = futures contract). Once a code is mapped,
    every record sharing that exact code is reclassified -- generalizing from a representative
    sample to the whole code is the same evidentiary method
    dnse_instrument_universe.py's own "ST" -> EQUITY mapping already uses (10 named examples),
    not a new or looser standard.

A code with mixed, absent, or ambiguous name evidence (e.g. "MF", whose named members mix a
generic "Quy dau tu" (investment fund) phrasing with "Quy ETF" (ETF fund) phrasing for what
should be one consistent class) is deliberately left UNKNOWN_SECURITY_GROUP -- see the contract
doc. The no-securityGroupId population (market indices) is handled separately below, since there
is no code to generalize from; every one of its 6 members was individually confirmed.
"""
from __future__ import annotations

from typing import Any, Mapping

from dnse_instrument_universe import BOND, DERIVATIVE, ETF, UNKNOWN_SECURITY_GROUP, WARRANT

INDEX = "INDEX"

RULE_VERSION = "dnse_security_group_semantics/v1"

#: Evidence: retained 2026-08-12 DNSE security-master snapshot. "named"/"total" are exact counts
#: of records with a populated `name` field vs. the code's full population, both inspected in
#: full (not sampled) at qualification time. See the contract doc for representative name text.
EVIDENCE_BY_SECURITY_GROUP_CODE: dict[str, dict[str, Any]] = {
    "EW": {"instrument_class": WARRANT, "named": 697, "total": 1346},
    "BS": {"instrument_class": BOND, "named": 67, "total": 203},
    "EF": {"instrument_class": ETF, "named": 21, "total": 21},
    "FU": {"instrument_class": DERIVATIVE, "named": 8, "total": 8},
}

_INDEX_NAME_PREFIX = "Chỉ số"


def refine_instrument_class(*, raw_security_group_id: str | None, name: str | None,
                             current_instrument_class: str | None) -> dict[str, Any]:
    """Return a refinement decision for one already-classified DNSE record.

    Never overrides a class other than UNKNOWN_SECURITY_GROUP; never invents a class beyond
    EVIDENCE_BY_SECURITY_GROUP_CODE plus the no-code/index case. A code with no entry here, or a
    no-code record whose name does not itself confirm an index, is returned unchanged.
    """
    if current_instrument_class != UNKNOWN_SECURITY_GROUP:
        return {"instrument_class": current_instrument_class,
                "refinement_basis": "not_unknown_security_group", "rule_version": RULE_VERSION}

    code = (raw_security_group_id or "").strip()
    if not code:
        if name is not None and name.strip().startswith(_INDEX_NAME_PREFIX):
            return {"instrument_class": INDEX,
                    "refinement_basis": "security_group_id_absent_name_confirms_index",
                    "rule_version": RULE_VERSION}
        return {"instrument_class": UNKNOWN_SECURITY_GROUP,
                "refinement_basis": "security_group_id_absent_no_index_name_evidence",
                "rule_version": RULE_VERSION}

    evidence = EVIDENCE_BY_SECURITY_GROUP_CODE.get(code)
    if evidence is None:
        return {"instrument_class": UNKNOWN_SECURITY_GROUP,
                "refinement_basis": "security_group_id_not_yet_evidenced", "rule_version": RULE_VERSION}
    return {
        "instrument_class": evidence["instrument_class"],
        "refinement_basis": f"security_group_id_{code}_name_evidence_generalized",
        "rule_version": RULE_VERSION,
        "evidence_named_count": evidence["named"],
        "evidence_total_count": evidence["total"],
    }


def refine_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Apply refinement to one dnse_instrument_universe.normalize_instrument_record()-shaped
    record. Returns a new dict; the input is never mutated. Every field is preserved verbatim
    except `instrument_class`, plus one new `security_group_refinement` provenance field."""
    decision = refine_instrument_class(
        raw_security_group_id=record.get("raw_security_group_id"),
        name=record.get("name"),
        current_instrument_class=record.get("instrument_class"),
    )
    updated = dict(record)
    updated["instrument_class"] = decision["instrument_class"]
    updated["security_group_refinement"] = decision
    return updated


def refine_records(records: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Apply refine_record to every record; order and length are preserved."""
    return [refine_record(record) for record in records]


def refinement_summary(refined_records: list[Mapping[str, Any]]) -> dict[str, int]:
    """Deterministic count of the resulting instrument_class distribution -- for reporting only,
    never itself an input to reconciliation."""
    counts: dict[str, int] = {}
    for record in refined_records:
        cls = record.get("instrument_class") or "UNKNOWN"
        counts[cls] = counts.get(cls, 0) + 1
    return dict(sorted(counts.items()))
