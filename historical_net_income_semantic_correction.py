"""Append-only semantic correction for four frozen Class-A net-income identities.

Canonical registry (canonical_financial_facts.METRIC_REGISTRY):

* ``net_income`` = total profit after tax (ordinary consolidated line 60 + explicit label)
* ``attributable_net_income`` = profit after tax attributable to owners of the parent
  (ordinary consolidated line 61 + explicit parent-attributable label)

Line number alone is not identity. Label/code conflict fails closed. Values are never
copied between the two metrics. Historical retained rows are not rewritten; the original
incorrect ``net_income`` facts remain visible as superseded provenance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from official_financial_ocr_table_evidence import row_label_supports_metric
from official_legacy_precedence import compare_official_and_legacy


MILESTONE_ID = "HISTORICAL_NET_INCOME_SEMANTIC_CORRECTION_OVERLAY_V1"
CONTRACT_VERSION = "historical_net_income_semantic_correction/v1"
CORRECTION_KIND = "SEMANTIC_METRIC_RELABEL"
PUBLIC_DIR = "derived/financial-evidence-currency-refresh-v1"
PUBLIC_REPORT = "historical_net_income_semantic_correction_report.json"
PUBLIC_CORRECTIONS = "semantic_metric_relabel_corrections.jsonl"
PUBLIC_FACTS = "semantic_metric_relabel_facts.jsonl"
FINANCIAL_V2_PIN = "2026-09-05.1"
SUPERSEDED = "SUPERSEDED"
CURRENT_AUTHORITATIVE = "CURRENT_AUTHORITATIVE"
UNAVAILABLE = "UNAVAILABLE"
SEMANTIC_IDENTITY_UNRESOLVED = "SEMANTIC_IDENTITY_UNRESOLVED"
TOTAL_NET_INCOME_REQUIRED = "TOTAL_NET_INCOME_REQUIRED"
PARENT_ATTRIBUTABLE_INCOME_REQUIRED = "PARENT_ATTRIBUTABLE_INCOME_REQUIRED"
SEMANTIC_INTENT_UNRESOLVED = "SEMANTIC_INTENT_UNRESOLVED"
COMPATIBILITY_ALIAS = "parent_attributable_net_income"
SEMANTIC_CORRECTION_EXACT_KEY_CONFLICT = "SEMANTIC_CORRECTION_EXACT_KEY_CONFLICT"
SEMANTIC_CORRECTION_EVIDENCE_IDENTITY_MISMATCH = "SEMANTIC_CORRECTION_EVIDENCE_IDENTITY_MISMATCH"
REQUIRED_FACT_FIELDS = (
    "ticker", "canonical_metric", "reporting_period", "statement_scope",
    "document_sha256", "citation_id", "value", "qualification_state",
    "authority_state", "correction_kind", "ingress_contract",
)
REQUIRED_CORRECTION_FIELDS = (
    "contract_version", "correction_kind", "ticker", "reporting_period",
    "statement_scope", "document_sha256", "qualification_state",
    "old_metric", "new_metric", "supersedes_fact_identity",
)


class SemanticCorrectionArtifactError(ValueError):
    """Present semantic-correction artifact is unreadable, schema-invalid, or identity-corrupt.

    Missing artifact is expected absence and is not this error. A Python constant is not
    qualified evidence and never authorizes a current-authority row by itself.
    """


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def fact_identity(*, ticker: str, metric: str, reporting_period: str, statement_scope: str,
                  document_sha256: str, citation_id: str, value: int, source_page: int | None,
                  line_code: str | None) -> dict[str, Any]:
    return {
        "ticker": ticker, "metric": metric, "reporting_period": reporting_period,
        "statement_scope": statement_scope, "document_sha256": document_sha256,
        "citation_id": citation_id, "value": value, "source_page": source_page, "line_code": line_code,
    }


def correction_id_for(payload: Mapping[str, Any]) -> str:
    """Byte-identical for the same evidence identity. No wall-clock fields."""
    return _hash({
        "contract_version": CONTRACT_VERSION, "correction_kind": CORRECTION_KIND,
        "document_sha256": payload["document_sha256"], "citation_id": payload["citation_id"],
        "ticker": payload["ticker"], "reporting_period": payload["reporting_period"],
        "statement_scope": payload["statement_scope"], "old_metric": payload["old_metric"],
        "new_metric": payload["new_metric"], "source_page": payload["source_page"],
        "line_code": payload["line_code"], "evidence_identity": payload["evidence_identity"],
    })


def _line(metric: str, *, value: int, page: int, line_code: str, label: str, citation_id: str | None = None) -> dict[str, Any]:
    qualified = row_label_supports_metric(metric, label) and bool(line_code)
    identity_ok = (metric, line_code) not in {("net_income", "61"), ("attributable_net_income", "60")}
    return {
        "canonical_metric": metric, "value": value, "source_page": page, "line_code": line_code,
        "row_label": label, "citation_id": citation_id,
        "label_qualifies": bool(qualified and identity_ok),
        "identity_conflict": not identity_ok,
    }


# Frozen Class-A identities. Values and evidence hashes are retained-evidence constants.
CLASS_A: tuple[dict[str, Any], ...] = (
    {
        "ticker": "HPG", "reporting_period": "2022", "statement_scope": "consolidated",
        "currency": "VND", "unit_scale": 1, "document_sha256": "4fb8f8e0f8dd5dc429533e548e4cfd045c9a81f9d26a51a5e3cf1cee53498074",
        "knowledge_available_at": "2026-08-20T18:30:00Z",
        "wrong": _line("net_income", value=8_483_510_554_031, page=107, line_code="61",
                       label="Shareholders of the parent company",
                       citation_id="1f33cabb35a9a4bc7fc6c0eed7c89a80fda8258d61f8d4241669712cc9d94220"),
        "line60": _line("net_income", value=8_444_429_054_516, page=106, line_code="60",
                        label="Net profit after tax",
                        citation_id="0131580c5ea79faa60fdd920f4c4762b42b4c1a3791a61d034573e94995cd126"),
        "line61": _line("attributable_net_income", value=8_483_510_554_031, page=107, line_code="61",
                        label="Shareholders of the parent company",
                        citation_id="1f33cabb35a9a4bc7fc6c0eed7c89a80fda8258d61f8d4241669712cc9d94220"),
        "historical_correction_version": "hpg_parent_attributable_net_income_semantic_correction/v1",
    },
    {
        "ticker": "HPG", "reporting_period": "2023", "statement_scope": "consolidated",
        "currency": "VND", "unit_scale": 1, "document_sha256": "44919df68306d2389509d5701369c70966f3669fb5b2ce20f609b28322cfef0e",
        "knowledge_available_at": "2026-08-20T18:30:00Z",
        "wrong": _line("net_income", value=6_835_064_334_356, page=89, line_code="61",
                       label="Shareholders of the parent company",
                       citation_id="d49913fd44b2f7e2fe5accc17d0ab766b363d075e7b15069aed9d00b2c4dc573"),
        "line60": _line("net_income", value=6_800_388_315_081, page=88, line_code="60",
                        label="Net profit after tax",
                        citation_id="265e679db80277ffea7450b811c47a00248cf574ceb2097011176ebc2d7a281d"),
        "line61": _line("attributable_net_income", value=6_835_064_334_356, page=89, line_code="61",
                        label="Shareholders of the parent company",
                        citation_id="d49913fd44b2f7e2fe5accc17d0ab766b363d075e7b15069aed9d00b2c4dc573"),
        "historical_correction_version": "hpg_parent_attributable_net_income_semantic_correction/v1",
    },
    {
        "ticker": "FPT", "reporting_period": "2025", "statement_scope": "consolidated",
        "currency": "VND", "unit_scale": 1, "document_sha256": "630f61f6ef9f07d5c593c3bf8f65bad1d56ecbb091921296ed5c4e830ea070a4",
        "knowledge_available_at": "2026-08-11T13:22:53.383431Z",
        "wrong": _line("net_income", value=9_376_127_629_501, page=12, line_code="61",
                       label="Phan b6é cho: cong Cô déng cua ty me",
                       citation_id="23e62e0a7052a02074658ca29db41c13f06fd046ea73a41c253222ea725cd805"),
        "line60": _line("net_income", value=11_232_339_450_734, page=12, line_code="60",
                        label="Loi nhuan sau thué TNDN", citation_id=None),
        "line61": _line("attributable_net_income", value=9_376_127_629_501, page=12, line_code="61",
                        label="Phan b6é cho: cong Cô déng cua ty me",
                        citation_id="23e62e0a7052a02074658ca29db41c13f06fd046ea73a41c253222ea725cd805"),
        "historical_correction_version": None,
    },
    {
        "ticker": "GAS", "reporting_period": "2025", "statement_scope": "consolidated",
        "currency": "VND", "unit_scale": 1, "document_sha256": "b1cfb676ad81cabb6a0ebcd4b9955f33c9644964ef894c985228694a2d5aef6c",
        "knowledge_available_at": "2026-08-19T15:10:56.219426Z",
        "wrong": _line("net_income", value=11_414_339_911_686, page=11, line_code="61",
                       label="Lợi nhuận sau thuế của cổ đông Công ty mẹ",
                       citation_id="c22cc1d5b66b7391e1ab8c724ec2793f895e9def4dc86c960942ad3da28be5bc"),
        "line60": _line("net_income", value=11_571_631_226_008, page=11, line_code="60",
                        label="Lợi nhuận sau thuế thu nhập doanh nghiệp", citation_id=None),
        "line61": _line("attributable_net_income", value=11_414_339_911_686, page=11, line_code="61",
                        label="Lợi nhuận sau thuế của cổ đông Công ty mẹ",
                        citation_id="c22cc1d5b66b7391e1ab8c724ec2793f895e9def4dc86c960942ad3da28be5bc"),
        "historical_correction_version": None,
    },
)

CLASS_D_UNRESOLVED: tuple[dict[str, str], ...] = (
    {"ticker": "PVD", "reporting_period": "2022", "reason": SEMANTIC_IDENTITY_UNRESOLVED},
    {"ticker": "PVD", "reporting_period": "2023", "reason": SEMANTIC_IDENTITY_UNRESOLVED},
    {"ticker": "VNM", "reporting_period": "2024", "reason": SEMANTIC_IDENTITY_UNRESOLVED},
    {"ticker": "AAA", "reporting_period": "2024", "reason": SEMANTIC_IDENTITY_UNRESOLVED},
    {"ticker": "VRE", "reporting_period": "2025", "reason": SEMANTIC_IDENTITY_UNRESOLVED},
)


def canonicalize_metric_name(metric: str) -> str:
    """Map dead contract vocabulary onto the canonical registry id."""
    if metric == COMPATIBILITY_ALIAS:
        return "attributable_net_income"
    return metric


def _citation_for(row: Mapping[str, Any], *, ticker: str, period: str, scope: str, document_sha256: str) -> str:
    if row.get("citation_id"):
        return str(row["citation_id"])
    return _hash({
        "document_sha256": document_sha256, "ticker": ticker, "reporting_period": period,
        "statement_scope": scope, "canonical_metric": row["canonical_metric"],
        "value": row["value"], "source_page": row["source_page"], "line_code": row["line_code"],
        "row_label": row["row_label"],
    })


def _class_a_by_wrong_value() -> dict[tuple[str, str, int], dict[str, Any]]:
    return {(row["ticker"], row["reporting_period"], int(row["wrong"]["value"])): row for row in CLASS_A}


def is_wrong_class_a_net_income(fact: Mapping[str, Any]) -> dict[str, Any] | None:
    ticker = str(fact.get("ticker") or fact.get("issuer_identity") or "")
    if isinstance(fact.get("issuer_identity"), Mapping):
        ticker = str(fact["issuer_identity"].get("ticker") or ticker)
    ticker = ticker.upper()
    period = str(fact.get("reporting_period") or "")
    metric = canonicalize_metric_name(str(fact.get("canonical_metric") or fact.get("metric") or ""))
    if metric != "net_income":
        return None
    lineage = fact.get("source_lineage") if isinstance(fact.get("source_lineage"), Mapping) else {}
    value = fact.get("value")
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    matched = _class_a_by_wrong_value().get((ticker, period, number))
    if matched is None:
        return None
    line_code = str(lineage.get("line_code") or fact.get("line_code") or fact.get("line_item_code") or "")
    if line_code and line_code != "61":
        return None
    return matched


def build_correction_record(entry: Mapping[str, Any], *, new_metric: str, new_row: Mapping[str, Any] | None) -> dict[str, Any]:
    wrong = entry["wrong"]
    document_sha256 = entry["document_sha256"]
    new_citation = _citation_for(new_row, ticker=entry["ticker"], period=entry["reporting_period"],
                                 scope=entry["statement_scope"], document_sha256=document_sha256) if new_row else None
    evidence_identity = {
        "document_sha256": document_sha256, "wrong_citation_id": wrong["citation_id"],
        "wrong_value": wrong["value"], "wrong_line_code": wrong["line_code"],
        "wrong_source_page": wrong["source_page"], "wrong_row_label": wrong["row_label"],
    }
    payload = {
        "document_sha256": document_sha256, "citation_id": wrong["citation_id"],
        "ticker": entry["ticker"], "reporting_period": entry["reporting_period"],
        "statement_scope": entry["statement_scope"], "old_metric": "net_income",
        "new_metric": new_metric, "source_page": (new_row or wrong)["source_page"],
        "line_code": (new_row or wrong)["line_code"], "evidence_identity": evidence_identity,
    }
    identifier = correction_id_for(payload)
    qualified = bool(new_row and new_row.get("label_qualifies") and not new_row.get("identity_conflict"))
    return {
        "contract_version": CONTRACT_VERSION, "milestone_id": MILESTONE_ID,
        "correction_kind": CORRECTION_KIND, "correction_id": identifier,
        "append_only": True, "historical_rows_rewritten": False,
        "ticker": entry["ticker"], "reporting_period": entry["reporting_period"],
        "statement_scope": entry["statement_scope"], "currency": entry["currency"],
        "unit_scale": entry["unit_scale"], "document_sha256": document_sha256,
        "old_metric": "net_income", "new_metric": new_metric,
        "old_value": wrong["value"], "new_value": None if not qualified else new_row["value"],
        "supersedes_fact_identity": fact_identity(
            ticker=entry["ticker"], metric="net_income", reporting_period=entry["reporting_period"],
            statement_scope=entry["statement_scope"], document_sha256=document_sha256,
            citation_id=str(wrong["citation_id"]), value=int(wrong["value"]),
            source_page=wrong["source_page"], line_code=wrong["line_code"],
        ),
        "superseding_fact_identity": None if not qualified else fact_identity(
            ticker=entry["ticker"], metric=new_metric, reporting_period=entry["reporting_period"],
            statement_scope=entry["statement_scope"], document_sha256=document_sha256,
            citation_id=str(new_citation), value=int(new_row["value"]),
            source_page=new_row["source_page"], line_code=new_row["line_code"],
        ),
        "source_page": (new_row or wrong)["source_page"], "line_code": (new_row or wrong)["line_code"],
        "row_label": (new_row or wrong)["row_label"],
        "evidence_lineage": {
            "document_sha256": document_sha256,
            "historical_correction_version": entry.get("historical_correction_version"),
            "wrong_citation_id": wrong["citation_id"],
            "line60_citation_id": _citation_for(entry["line60"], ticker=entry["ticker"], period=entry["reporting_period"],
                                                scope=entry["statement_scope"], document_sha256=document_sha256),
            "line61_citation_id": _citation_for(entry["line61"], ticker=entry["ticker"], period=entry["reporting_period"],
                                                scope=entry["statement_scope"], document_sha256=document_sha256),
        },
        "knowledge_available_at": entry["knowledge_available_at"],
        "effective_time": entry["knowledge_available_at"],
        "qualification_state": CURRENT_AUTHORITATIVE if qualified else UNAVAILABLE,
        "line60_available": bool(entry["line60"]["label_qualifies"]),
        "line61_available": bool(entry["line61"]["label_qualifies"]),
    }


def build_all_correction_records() -> list[dict[str, Any]]:
    records = []
    for entry in CLASS_A:
        records.append(build_correction_record(entry, new_metric="attributable_net_income", new_row=entry["line61"]))
        records.append(build_correction_record(entry, new_metric="net_income", new_row=entry["line60"]))
    records.sort(key=lambda row: (row["ticker"], row["reporting_period"], row["new_metric"]))
    return records


def current_authority_fact_rows() -> list[dict[str, Any]]:
    """Qualified current-authority facts emitted by the overlay. Never copies values across metrics."""
    rows: list[dict[str, Any]] = []
    for entry in CLASS_A:
        for spec in (entry["line60"], entry["line61"]):
            if not spec["label_qualifies"] or spec["identity_conflict"]:
                continue
            citation_id = _citation_for(spec, ticker=entry["ticker"], period=entry["reporting_period"],
                                        scope=entry["statement_scope"], document_sha256=entry["document_sha256"])
            rows.append({
                "ticker": entry["ticker"], "canonical_metric": spec["canonical_metric"],
                "reporting_period": entry["reporting_period"], "period_type": "annual",
                "period_start": f"{entry['reporting_period']}-01-01", "period_end": f"{entry['reporting_period']}-12-31",
                "statement_scope": entry["statement_scope"], "statement_family": "income_statement",
                "temporal_nature": "duration", "currency": entry["currency"], "unit_scale": entry["unit_scale"],
                "already_normalized": True, "value": spec["value"], "normalized_value": spec["value"],
                "qualification_state": "QUALIFIED", "blockers": [],
                "document_sha256": entry["document_sha256"], "citation_id": citation_id,
                "source_page": spec["source_page"], "line_code": spec["line_code"], "row_label": spec["row_label"],
                "knowledge_available_at": entry["knowledge_available_at"],
                "observed_at": entry["knowledge_available_at"],
                "correction_kind": CORRECTION_KIND, "ingress_contract": CONTRACT_VERSION,
                "authority_state": CURRENT_AUTHORITATIVE,
            })
    rows.sort(key=lambda row: (row["ticker"], row["reporting_period"], row["canonical_metric"]))
    return rows


def _authorized_fact_contract() -> dict[tuple[str, str, str], dict[str, Any]]:
    """Frozen CLASS_A reference used only to validate a loaded artifact. Never an authority source."""
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in CLASS_A:
        for spec in (entry["line60"], entry["line61"]):
            if not spec["label_qualifies"] or spec["identity_conflict"]:
                continue
            citation_id = _citation_for(
                spec, ticker=entry["ticker"], period=entry["reporting_period"],
                scope=entry["statement_scope"], document_sha256=entry["document_sha256"],
            )
            index[(entry["ticker"], spec["canonical_metric"], entry["reporting_period"])] = {
                "ticker": entry["ticker"],
                "canonical_metric": spec["canonical_metric"],
                "reporting_period": entry["reporting_period"],
                "statement_scope": entry["statement_scope"],
                "document_sha256": entry["document_sha256"],
                "citation_id": citation_id,
                "value": int(spec["value"]),
                "source_page": spec["source_page"],
                "line_code": spec["line_code"],
            }
    return index


def _authorized_wrong_identity() -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (entry["ticker"], entry["reporting_period"]): {
            "ticker": entry["ticker"],
            "metric": "net_income",
            "reporting_period": entry["reporting_period"],
            "statement_scope": entry["statement_scope"],
            "document_sha256": entry["document_sha256"],
            "citation_id": entry["wrong"]["citation_id"],
            "value": int(entry["wrong"]["value"]),
            "source_page": entry["wrong"]["source_page"],
            "line_code": entry["wrong"]["line_code"],
        }
        for entry in CLASS_A
    }


def _parse_jsonl_objects(path: Path, *, label: str) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SemanticCorrectionArtifactError(f"SEMANTIC_CORRECTION_ARTIFACT_UNREADABLE:{label}:{path}") from exc
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SemanticCorrectionArtifactError(
                f"SEMANTIC_CORRECTION_ARTIFACT_MALFORMED_JSON:{label}:line={index}"
            ) from exc
        if not isinstance(record, dict):
            raise SemanticCorrectionArtifactError(
                f"SEMANTIC_CORRECTION_ARTIFACT_SCHEMA_ERROR:{label}:line={index}:not_object"
            )
        rows.append(record)
    return rows


def _require_fields(record: Mapping[str, Any], fields: Sequence[str], *, label: str, index: int) -> None:
    missing = [field for field in fields if record.get(field) in (None, "")]
    if missing:
        raise SemanticCorrectionArtifactError(
            f"SEMANTIC_CORRECTION_ARTIFACT_SCHEMA_ERROR:{label}:line={index}:missing={','.join(missing)}"
        )


def _validate_loaded_fact(record: Mapping[str, Any], *, index: int,
                          contract: Mapping[tuple[str, str, str], Mapping[str, Any]]) -> dict[str, Any]:
    _require_fields(record, REQUIRED_FACT_FIELDS, label="facts", index=index)
    ticker = str(record["ticker"]).upper()
    metric = canonicalize_metric_name(str(record["canonical_metric"]))
    period = str(record["reporting_period"])
    if str(record.get("ingress_contract") or "") != CONTRACT_VERSION:
        raise SemanticCorrectionArtifactError(
            f"SEMANTIC_CORRECTION_CONTRACT_VERSION_MISMATCH:facts:line={index}"
        )
    if str(record.get("correction_kind") or "") != CORRECTION_KIND:
        raise SemanticCorrectionArtifactError(
            f"SEMANTIC_CORRECTION_KIND_MISMATCH:facts:line={index}"
        )
    qualification = str(record.get("qualification_state") or "")
    authority = str(record.get("authority_state") or "")
    if qualification != "QUALIFIED" or authority != CURRENT_AUTHORITATIVE:
        raise SemanticCorrectionArtifactError(
            f"SEMANTIC_CORRECTION_ARTIFACT_SCHEMA_ERROR:facts:line={index}:not_current_authority"
        )
    expected = contract.get((ticker, metric, period))
    if expected is None:
        raise SemanticCorrectionArtifactError(
            f"{SEMANTIC_CORRECTION_EVIDENCE_IDENTITY_MISMATCH}:facts:line={index}:unauthorized_key"
        )
    try:
        value = int(record.get("value"))
    except (TypeError, ValueError) as exc:
        raise SemanticCorrectionArtifactError(
            f"SEMANTIC_CORRECTION_ARTIFACT_SCHEMA_ERROR:facts:line={index}:value"
        ) from exc
    if (
        str(record.get("statement_scope") or "") != expected["statement_scope"]
        or str(record.get("document_sha256") or "") != expected["document_sha256"]
        or str(record.get("citation_id") or "") != expected["citation_id"]
        or value != expected["value"]
    ):
        raise SemanticCorrectionArtifactError(
            f"{SEMANTIC_CORRECTION_EVIDENCE_IDENTITY_MISMATCH}:facts:line={index}:{ticker}:{metric}:{period}"
        )
    copied = json.loads(_canonical_json(dict(record)))
    copied["ticker"] = ticker
    copied["canonical_metric"] = metric
    copied["value"] = value
    copied["normalized_value"] = int(record.get("normalized_value") or value)
    return copied


def _validate_loaded_correction(record: Mapping[str, Any], *, index: int,
                                wrong_index: Mapping[tuple[str, str], Mapping[str, Any]],
                                fact_contract: Mapping[tuple[str, str, str], Mapping[str, Any]]) -> dict[str, Any]:
    _require_fields(record, REQUIRED_CORRECTION_FIELDS, label="corrections", index=index)
    if str(record.get("contract_version") or "") != CONTRACT_VERSION:
        raise SemanticCorrectionArtifactError(
            f"SEMANTIC_CORRECTION_CONTRACT_VERSION_MISMATCH:corrections:line={index}"
        )
    if str(record.get("correction_kind") or "") != CORRECTION_KIND:
        raise SemanticCorrectionArtifactError(
            f"SEMANTIC_CORRECTION_KIND_MISMATCH:corrections:line={index}"
        )
    ticker = str(record["ticker"]).upper()
    period = str(record["reporting_period"])
    expected_wrong = wrong_index.get((ticker, period))
    identity = record.get("supersedes_fact_identity")
    if expected_wrong is None or not isinstance(identity, Mapping):
        raise SemanticCorrectionArtifactError(
            f"{SEMANTIC_CORRECTION_EVIDENCE_IDENTITY_MISMATCH}:corrections:line={index}:supersession"
        )
    try:
        superseded_value = int(identity.get("value"))
    except (TypeError, ValueError) as exc:
        raise SemanticCorrectionArtifactError(
            f"SEMANTIC_CORRECTION_ARTIFACT_SCHEMA_ERROR:corrections:line={index}:supersedes_value"
        ) from exc
    if (
        str(identity.get("ticker") or "").upper() != expected_wrong["ticker"]
        or canonicalize_metric_name(str(identity.get("metric") or "")) != expected_wrong["metric"]
        or str(identity.get("reporting_period") or "") != expected_wrong["reporting_period"]
        or str(identity.get("statement_scope") or "") != expected_wrong["statement_scope"]
        or str(identity.get("document_sha256") or "") != expected_wrong["document_sha256"]
        or str(identity.get("citation_id") or "") != expected_wrong["citation_id"]
        or superseded_value != expected_wrong["value"]
        or str(identity.get("line_code") or "") != expected_wrong["line_code"]
        or str(record.get("document_sha256") or "") != expected_wrong["document_sha256"]
    ):
        raise SemanticCorrectionArtifactError(
            f"{SEMANTIC_CORRECTION_EVIDENCE_IDENTITY_MISMATCH}:corrections:line={index}:{ticker}:{period}"
        )
    qualification = str(record.get("qualification_state") or "")
    superseding = record.get("superseding_fact_identity")
    if qualification == CURRENT_AUTHORITATIVE:
        if not isinstance(superseding, Mapping):
            raise SemanticCorrectionArtifactError(
                f"SEMANTIC_CORRECTION_ARTIFACT_SCHEMA_ERROR:corrections:line={index}:superseding_required"
            )
        new_metric = canonicalize_metric_name(str(record.get("new_metric") or superseding.get("metric") or ""))
        expected_new = fact_contract.get((ticker, new_metric, period))
        try:
            new_value = int(superseding.get("value"))
        except (TypeError, ValueError) as exc:
            raise SemanticCorrectionArtifactError(
                f"SEMANTIC_CORRECTION_ARTIFACT_SCHEMA_ERROR:corrections:line={index}:superseding_value"
            ) from exc
        if expected_new is None or (
            str(superseding.get("document_sha256") or "") != expected_new["document_sha256"]
            or str(superseding.get("citation_id") or "") != expected_new["citation_id"]
            or new_value != expected_new["value"]
            or str(superseding.get("statement_scope") or "") != expected_new["statement_scope"]
        ):
            raise SemanticCorrectionArtifactError(
                f"{SEMANTIC_CORRECTION_EVIDENCE_IDENTITY_MISMATCH}:corrections:line={index}:superseding"
            )
    elif qualification != UNAVAILABLE:
        raise SemanticCorrectionArtifactError(
            f"SEMANTIC_CORRECTION_ARTIFACT_SCHEMA_ERROR:corrections:line={index}:qualification_state"
        )
    copied = json.loads(_canonical_json(dict(record)))
    copied["ticker"] = ticker
    return copied


def load_semantic_correction_artifacts(root: Path | str) -> dict[str, list[dict[str, Any]]]:
    """Load public semantic-correction JSONL from the supplied evidence root.

    Missing both artifacts is expected absence and returns empty lists. A present malformed
    artifact fails closed. CLASS_A is used only as a frozen validation contract.
    """
    directory = Path(root) / PUBLIC_DIR
    facts_path = directory / PUBLIC_FACTS
    corrections_path = directory / PUBLIC_CORRECTIONS
    facts_present = facts_path.is_file()
    corrections_present = corrections_path.is_file()
    if not facts_present and not corrections_present:
        return {"facts": [], "corrections": []}
    fact_contract = _authorized_fact_contract()
    wrong_index = _authorized_wrong_identity()
    facts: list[dict[str, Any]] = []
    if facts_present:
        for index, record in enumerate(_parse_jsonl_objects(facts_path, label="facts"), start=1):
            facts.append(_validate_loaded_fact(record, index=index, contract=fact_contract))
    corrections: list[dict[str, Any]] = []
    if corrections_present:
        for index, record in enumerate(_parse_jsonl_objects(corrections_path, label="corrections"), start=1):
            corrections.append(_validate_loaded_correction(
                record, index=index, wrong_index=wrong_index, fact_contract=fact_contract,
            ))
    facts.sort(key=lambda row: (row["ticker"], row["reporting_period"], row["canonical_metric"]))
    corrections.sort(key=lambda row: (row["ticker"], row["reporting_period"], row["new_metric"]))
    return {"facts": facts, "corrections": corrections}


def _mapping_value(entry: Mapping[str, Any]) -> int | None:
    try:
        return int(entry.get("value"))
    except (TypeError, ValueError):
        return None


def _compatible_evidence(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> bool:
    existing_sha = str(existing.get("document_sha256") or existing.get("evidence_id") or "")
    incoming_sha = str(incoming.get("document_sha256") or incoming.get("evidence_id") or "")
    existing_citation = str(existing.get("citation_id") or "")
    incoming_citation = str(incoming.get("citation_id") or "")
    sha_ok = (not existing_sha) or (not incoming_sha) or existing_sha == incoming_sha
    citation_ok = (not existing_citation) or (not incoming_citation) or existing_citation == incoming_citation
    return sha_ok and citation_ok


def _matches_superseded_identity(entry: Mapping[str, Any], *, ticker: str, metric: str, period: str,
                                 identity: Mapping[str, Any]) -> bool:
    if ticker != str(identity.get("ticker") or "").upper():
        return False
    if metric != canonicalize_metric_name(str(identity.get("metric") or "")):
        return False
    if period != str(identity.get("reporting_period") or ""):
        return False
    value = _mapping_value(entry)
    try:
        expected_value = int(identity.get("value"))
    except (TypeError, ValueError):
        return False
    if value != expected_value:
        return False
    document_sha = str(entry.get("document_sha256") or entry.get("evidence_id") or "")
    citation_id = str(entry.get("citation_id") or "")
    lineage = entry.get("source_lineage") if isinstance(entry.get("source_lineage"), Mapping) else {}
    if not document_sha:
        document_sha = str(lineage.get("document_sha256") or "")
    if not citation_id:
        citation_id = str(lineage.get("citation_id") or "")
    expected_sha = str(identity.get("document_sha256") or "")
    expected_citation = str(identity.get("citation_id") or "")
    if expected_sha and document_sha and document_sha != expected_sha:
        return False
    if expected_citation and citation_id and citation_id != expected_citation:
        return False
    if expected_sha and not document_sha:
        return False
    if expected_citation and not citation_id:
        return False
    line_code = str(entry.get("line_code") or lineage.get("line_code") or "")
    expected_line = str(identity.get("line_code") or "")
    if expected_line and line_code and line_code != expected_line:
        return False
    return True


def _correction_fact_to_overlay(row: Mapping[str, Any]) -> dict[str, Any]:
    citation_id = str(row.get("citation_id") or "")
    document_sha256 = str(row.get("document_sha256") or "")
    period = str(row["reporting_period"])
    return {
        "issuer_identity": row["ticker"], "ticker": row["ticker"],
        "canonical_metric": row["canonical_metric"], "value": int(row["value"]),
        "currency": row.get("currency") or "VND", "unit_scale": row.get("unit_scale") or 1,
        "reporting_period": period, "period_type": row.get("period_type") or "annual",
        "period_start": row.get("period_start") or f"{period}-01-01",
        "period_end": row.get("period_end") or f"{period}-12-31",
        "statement_scope": row.get("statement_scope") or "consolidated",
        "statement_family": row.get("statement_family") or "income_statement",
        "temporal_nature": row.get("temporal_nature") or "duration",
        "qualification_state": "QUALIFIED",
        "current_authority_state": CURRENT_AUTHORITATIVE,
        "knowledge_available_at": row.get("knowledge_available_at"),
        "observed_at": row.get("observed_at") or row.get("knowledge_available_at"),
        "document_sha256": document_sha256, "citation_id": citation_id,
        "source_lineage": {
            "document_sha256": document_sha256, "citation_id": citation_id,
            "source_page": row.get("source_page"), "line_code": row.get("line_code"),
            "raw_row_label": row.get("row_label"), "correction_kind": CORRECTION_KIND,
        },
    }


def _correction_fact_to_citation(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "citation_id": row.get("citation_id"),
        "evidence_id": row.get("document_sha256"),
        "value": int(row["value"]),
        "currency": row.get("currency") or "VND",
        "scale": row.get("unit_scale") or 1,
        "statement_scope": row.get("statement_scope"),
        "document_sha256": row.get("document_sha256"),
        "verified": True,
        "provenance": CONTRACT_VERSION,
        "canonical_metric": row["canonical_metric"],
    }


def _correction_fact_to_verified(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ticker": row["ticker"], "metric": row["canonical_metric"],
        "reporting_frequency": "annual", "reporting_period": row["reporting_period"],
        "statement_scope": row.get("statement_scope"), "currency": row.get("currency") or "VND",
        "unit_scale": row.get("unit_scale") or 1, "value": int(row["value"]),
        "evidence_id": row.get("document_sha256"), "citation_id": row.get("citation_id"),
        "document_sha256": row.get("document_sha256"),
        "verified_at": row.get("knowledge_available_at"),
        "provenance": CONTRACT_VERSION,
    }


def _merge_correction_into_mapping(
    result: dict[tuple, dict[str, Any]],
    *,
    key: tuple,
    incoming: Mapping[str, Any],
) -> None:
    existing = result.get(key)
    if existing is None:
        result[key] = dict(incoming)
        return
    existing_value = _mapping_value(existing)
    incoming_value = _mapping_value(incoming)
    if existing_value is not None and incoming_value is not None and existing_value == incoming_value:
        if _compatible_evidence(existing, incoming):
            return
    raise SemanticCorrectionArtifactError(f"{SEMANTIC_CORRECTION_EXACT_KEY_CONFLICT}:{key}")


def _vote_key(fact: Mapping[str, Any]) -> tuple[str, str, str, str]:
    ticker = str(fact.get("ticker") or "")
    if isinstance(fact.get("issuer_identity"), Mapping):
        ticker = str(fact["issuer_identity"].get("ticker") or ticker)
    elif isinstance(fact.get("issuer_identity"), str) and not ticker:
        ticker = fact["issuer_identity"]
    metric = canonicalize_metric_name(str(fact.get("canonical_metric") or fact.get("metric") or ""))
    period = str(fact.get("reporting_period") or "")
    scope = str(fact.get("statement_scope") or "")
    return (ticker.upper(), metric, period, scope)


def apply_to_facts(
    facts: Sequence[Mapping[str, Any]],
    *,
    correction_facts: Sequence[Mapping[str, Any]] | None = None,
    correction_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Mark loaded wrong identities superseded and add explicitly supplied replacements.

    Original mappings are copied, never rewritten in place. Two rows of the same
    exact current-authority key cannot both vote. CLASS_A constants are not an
    acquisition source; only ``correction_facts`` / ``correction_records`` authorize
    overlay rows.
    """
    loaded_facts = list(correction_facts or ())
    loaded_records = list(correction_records or ())
    superseded: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    seen_wrong: set[tuple[str, str]] = set()
    for fact in facts:
        copied = json.loads(_canonical_json(dict(fact)))
        ticker, metric, period, _scope = _vote_key(copied)
        matched_record = next(
            (
                record for record in loaded_records
                if isinstance(record.get("supersedes_fact_identity"), Mapping)
                and _matches_superseded_identity(
                    copied, ticker=ticker, metric=metric, period=period,
                    identity=record["supersedes_fact_identity"],
                )
            ),
            None,
        )
        if matched_record is not None:
            lineage = dict(copied.get("source_lineage") or {})
            lineage["semantic_metric_relabel"] = {
                "contract_version": CONTRACT_VERSION, "correction_kind": CORRECTION_KIND,
                "state": SUPERSEDED, "old_metric": matched_record.get("old_metric") or "net_income",
                "new_metric": matched_record.get("new_metric"),
            }
            copied["source_lineage"] = lineage
            copied["current_authority_state"] = SUPERSEDED
            copied["qualification_state"] = SUPERSEDED
            copied.setdefault("reason_codes", [])
            if "SEMANTIC_METRIC_RELABEL_SUPERSEDED" not in copied["reason_codes"]:
                copied["reason_codes"] = list(copied["reason_codes"]) + ["SEMANTIC_METRIC_RELABEL_SUPERSEDED"]
            superseded.append(copied)
            seen_wrong.add((ticker, period))
            continue
        copied["canonical_metric"] = canonicalize_metric_name(str(copied.get("canonical_metric") or copied.get("metric") or ""))
        copied.setdefault("current_authority_state", CURRENT_AUTHORITATIVE)
        current.append(copied)

    added: list[dict[str, Any]] = []
    voters: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    present_tickers = {key[0] for key in (_vote_key(fact) for fact in list(facts) + current) if key[0]}
    present_tickers.update(ticker for ticker, _period in seen_wrong)
    for fact in current:
        key = _vote_key(fact)
        if key in voters:
            raise ValueError(f"EXACT_KEY_DUPLICATE:{key}")
        voters[key] = fact
    for row in loaded_facts:
        overlay = _correction_fact_to_overlay(row)
        if overlay["ticker"] not in present_tickers:
            continue
        key = _vote_key(overlay)
        existing = voters.get(key)
        if existing is not None:
            existing_value = _mapping_value(existing)
            incoming_value = _mapping_value(overlay)
            if existing_value == incoming_value and _compatible_evidence(existing, overlay):
                continue
            raise SemanticCorrectionArtifactError(f"{SEMANTIC_CORRECTION_EXACT_KEY_CONFLICT}:{key}")
        voters[key] = overlay
        added.append(overlay)
    return {
        "current_facts": list(voters.values()),
        "superseded_facts": superseded,
        "added_facts": added,
        "stored_facts": list(facts) + added,
    }


def apply_to_verified_identities(
    by_key: Mapping[tuple, Mapping[str, Any]],
    *,
    correction_facts: Sequence[Mapping[str, Any]] | None = None,
    correction_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[tuple, dict[str, Any]]:
    """Pure transform: alias stale vocabulary and apply explicitly supplied correction facts.

    An empty mapping with no loaded correction artifact remains empty. CLASS_A is not
    consulted as an authority source.
    """
    loaded_facts = list(correction_facts or ())
    loaded_records = list(correction_records or ())
    result: dict[tuple, dict[str, Any]] = {}
    for key, entry in by_key.items():
        if not isinstance(key, tuple) or len(key) != 3 or not isinstance(entry, Mapping):
            continue
        ticker, metric, period = str(key[0]).upper(), canonicalize_metric_name(str(key[1])), str(key[2])
        copied = dict(entry)
        copied["metric"] = metric
        if any(
            isinstance(record.get("supersedes_fact_identity"), Mapping)
            and _matches_superseded_identity(
                copied, ticker=ticker, metric=metric, period=period,
                identity=record["supersedes_fact_identity"],
            )
            for record in loaded_records
        ):
            continue
        result[(ticker, metric, period)] = copied
        if str(key[1]) != metric:
            copied["compatibility_alias_from"] = str(key[1])
    for row in loaded_facts:
        key = (str(row["ticker"]).upper(), canonicalize_metric_name(str(row["canonical_metric"])), str(row["reporting_period"]))
        _merge_correction_into_mapping(result, key=key, incoming=_correction_fact_to_verified(row))
    return result


def apply_to_citation_mapping(
    citations: Mapping[tuple, Mapping[str, Any]],
    *,
    correction_facts: Sequence[Mapping[str, Any]] | None = None,
    correction_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[tuple, dict[str, Any]]:
    """Pure transform over the supplied citation map plus already-loaded correction facts.

    An empty mapping with no loaded correction artifact remains empty. CLASS_A is not
    consulted as an authority source.
    """
    loaded_facts = list(correction_facts or ())
    loaded_records = list(correction_records or ())
    result: dict[tuple, dict[str, Any]] = {}
    for key, entry in citations.items():
        if not isinstance(key, tuple) or len(key) < 3 or not isinstance(entry, Mapping):
            continue
        ticker, metric, period = str(key[0]).upper(), canonicalize_metric_name(str(key[1])), str(key[2])
        copied = dict(entry)
        if any(
            isinstance(record.get("supersedes_fact_identity"), Mapping)
            and _matches_superseded_identity(
                copied, ticker=ticker, metric=metric, period=period,
                identity=record["supersedes_fact_identity"],
            )
            for record in loaded_records
        ):
            continue
        result[(ticker, metric, period)] = copied
        if metric != str(key[1]):
            result[(ticker, metric, period)]["metric"] = metric
            result[(ticker, metric, period)]["canonical_metric"] = metric
    for row in loaded_facts:
        key = (str(row["ticker"]).upper(), canonicalize_metric_name(str(row["canonical_metric"])), str(row["reporting_period"]))
        _merge_correction_into_mapping(result, key=key, incoming=_correction_fact_to_citation(row))
    return result


CONSUMER_CLASSIFICATIONS: tuple[dict[str, Any], ...] = (
    {
        "consumer": "fundamental_research_readiness.py",
        "key": "corporate.net_margin",
        "classification": TOTAL_NET_INCOME_REQUIRED,
        "formula": "net_income / revenue",
        "evidence": "metric_definition_inventory net_margin formula_or_method and evaluate_issuer_fundamental_research corporate _ratio(..., 'net_income', 'revenue')",
    },
    {
        "consumer": "fundamental_research_readiness.py",
        "key": "corporate.cash_flow_to_earnings",
        "classification": TOTAL_NET_INCOME_REQUIRED,
        "formula": "operating_cash_flow / net_income",
        "evidence": "metric_definition_inventory cash_flow_to_earnings and _ratio(..., 'operating_cash_flow', 'net_income')",
    },
    {
        "consumer": "fundamental_research_readiness.py",
        "key": "corporate.cash_flow_minus_earnings",
        "classification": TOTAL_NET_INCOME_REQUIRED,
        "formula": "operating_cash_flow - net_income",
        "evidence": "metric_definition_inventory cash_flow_minus_earnings and _difference(..., 'operating_cash_flow', 'net_income')",
    },
    {
        "consumer": "fundamental_research_readiness.py",
        "key": "corporate.earnings_growth_yoy",
        "classification": TOTAL_NET_INCOME_REQUIRED,
        "formula": "(earnings_t - earnings_t-1) / abs(earnings_t-1) with corporate earnings = net_income",
        "evidence": "_earnings_metric corporate -> net_income; inventory names entity-specific parent/total identity and banks/securities use parent metrics",
    },
    {
        "consumer": "fundamental_research_readiness.py",
        "key": "corporate.return_on_assets",
        "classification": TOTAL_NET_INCOME_REQUIRED,
        "formula": "net_income / assets",
        "evidence": "_return_metric(..., 'net_income', 'total_assets') for corporate",
    },
    {
        "consumer": "fundamental_research_readiness.py",
        "key": "corporate.return_on_equity",
        "classification": TOTAL_NET_INCOME_REQUIRED,
        "formula": "net_income / shareholders_equity",
        "evidence": "_return_metric(..., 'net_income', 'shareholders_equity') for corporate",
    },
    {
        "consumer": "fundamental_research_readiness.py",
        "key": "bank.earnings",
        "classification": PARENT_ATTRIBUTABLE_INCOME_REQUIRED,
        "formula": "net_profit_parent",
        "evidence": "_earnings_metric bank -> net_profit_parent",
    },
    {
        "consumer": "fundamental_research_readiness.py",
        "key": "securities.earnings",
        "classification": PARENT_ATTRIBUTABLE_INCOME_REQUIRED,
        "formula": "profit_after_tax_parent",
        "evidence": "_earnings_metric securities -> profit_after_tax_parent",
    },
    {
        "consumer": "market_wide_current_valuation_input_scaleout.py",
        "key": "corporate.P/E",
        "classification": TOTAL_NET_INCOME_REQUIRED,
        "formula": "EARNINGS_IDENTITY_BY_ENTITY['corporate'] = net_income; parent_attributable_vs_total_earnings_kept_distinct",
        "evidence": "EARNINGS_IDENTITY_BY_ENTITY and P/E input_identities.earnings",
    },
    {
        "consumer": "market_wide_current_valuation_input_scaleout.py",
        "key": "bank.P/E",
        "classification": PARENT_ATTRIBUTABLE_INCOME_REQUIRED,
        "formula": "EARNINGS_IDENTITY_BY_ENTITY['bank'] = net_profit_parent",
        "evidence": "EARNINGS_IDENTITY_BY_ENTITY bank mapping",
    },
    {
        "consumer": "market_wide_current_valuation_input_scaleout.py",
        "key": "securities.P/E",
        "classification": PARENT_ATTRIBUTABLE_INCOME_REQUIRED,
        "formula": "EARNINGS_IDENTITY_BY_ENTITY['securities'] = profit_after_tax_parent",
        "evidence": "EARNINGS_IDENTITY_BY_ENTITY securities mapping",
    },
)


def classify_consumers() -> list[dict[str, Any]]:
    return [dict(row) for row in CONSUMER_CLASSIFICATIONS]


def unresolved_consumer_fail_closed(classification: str, *, metric: str | None) -> dict[str, Any]:
    if classification != SEMANTIC_INTENT_UNRESOLVED:
        raise ValueError("CONSUMER_NOT_UNRESOLVED")
    return {"status": "BLOCKED", "reason": SEMANTIC_INTENT_UNRESOLVED, "metric": metric, "value": None}


def precedence_official_attributable_vs_provider_net_income() -> dict[str, Any]:
    official = {
        "canonical_metric": "attributable_net_income", "reporting_period": "2025",
        "statement_scope": "consolidated", "statement_family": "income_statement",
        "qualification_state": "QUALIFIED", "currency": "VND", "unit_scale": 1,
        "value": 11_414_339_911_686, "document_sha256": CLASS_A[3]["document_sha256"],
        "citation_id": CLASS_A[3]["wrong"]["citation_id"],
    }
    legacy = {
        "canonical_metric": "net_income", "reporting_period": "2025",
        "statement_scope": "consolidated", "statement_family": "income_statement",
        "value": 11_414_339_911_686, "unit_scale": 1, "status": "provider_reported",
    }
    return compare_official_and_legacy(official, legacy)


def class_a_outcome(entry: Mapping[str, Any]) -> dict[str, Any]:
    line60 = entry["line60"]
    line61 = entry["line61"]
    return {
        "ticker": entry["ticker"], "reporting_period": entry["reporting_period"],
        "statement_scope": entry["statement_scope"], "document_sha256": entry["document_sha256"],
        "old_metric": "net_income", "old_value": entry["wrong"]["value"],
        "old_line_code": entry["wrong"]["line_code"], "old_source_page": entry["wrong"]["source_page"],
        "old_citation_id": entry["wrong"]["citation_id"],
        "net_income": {
            "available": bool(line60["label_qualifies"]),
            "value": line60["value"] if line60["label_qualifies"] else None,
            "line_code": "60", "source_page": line60["source_page"], "row_label": line60["row_label"],
            "qualification_state": "QUALIFIED" if line60["label_qualifies"] else UNAVAILABLE,
        },
        "attributable_net_income": {
            "available": bool(line61["label_qualifies"]),
            "value": line61["value"] if line61["label_qualifies"] else None,
            "line_code": "61", "source_page": line61["source_page"], "row_label": line61["row_label"],
            "qualification_state": "QUALIFIED" if line61["label_qualifies"] else UNAVAILABLE,
        },
        "superseded_identity": fact_identity(
            ticker=entry["ticker"], metric="net_income", reporting_period=entry["reporting_period"],
            statement_scope=entry["statement_scope"], document_sha256=entry["document_sha256"],
            citation_id=str(entry["wrong"]["citation_id"]), value=int(entry["wrong"]["value"]),
            source_page=entry["wrong"]["source_page"], line_code=entry["wrong"]["line_code"],
        ),
    }


def build_public_report(*, consumer_impact: Sequence[Mapping[str, Any]] | None = None,
                        daily_impact: Mapping[str, Any] | None = None,
                        financial_v2: Mapping[str, Any] | None = None,
                        unexplained_drift_count: int = 0) -> dict[str, Any]:
    outcomes = [class_a_outcome(entry) for entry in CLASS_A]
    corrections = build_all_correction_records()
    report = {
        "contract_version": CONTRACT_VERSION, "milestone_id": MILESTONE_ID,
        "correction_kind": CORRECTION_KIND, "network_used": False,
        "raw_pdf_or_image_bytes_committed": False, "historical_rows_rewritten": False,
        "canonical_semantics": {
            "net_income": "total profit after tax",
            "attributable_net_income": "profit after tax attributable to owners/shareholders of parent",
            "line_60": "net_income only with qualifying identity evidence",
            "line_61": "attributable_net_income only with qualifying identity evidence",
            "line_number_alone": "NOT_SUFFICIENT",
            "numeric_copying": "FORBIDDEN",
        },
        "frozen_class_a": outcomes,
        "class_d_unchanged": [dict(row) for row in CLASS_D_UNRESOLVED],
        "corrections": [{"correction_id": row["correction_id"], "ticker": row["ticker"],
                         "reporting_period": row["reporting_period"], "old_metric": row["old_metric"],
                         "new_metric": row["new_metric"], "qualification_state": row["qualification_state"],
                         "supersedes_fact_identity": row["supersedes_fact_identity"],
                         "superseding_fact_identity": row["superseding_fact_identity"]}
                        for row in corrections],
        "stale_vocabulary": {
            "parent_attributable_net_income": "compatibility alias mapped to attributable_net_income",
            "active_citations_using_stale_id": 0,
        },
        "consumer_classifications": classify_consumers(),
        "consumer_impact": list(consumer_impact or []),
        "precedence": {
            "provider_net_income_vs_official_attributable_net_income": precedence_official_attributable_vs_provider_net_income(),
        },
        "financial_v2": financial_v2 or {"authority_version": FINANCIAL_V2_PIN, "changed": False},
        "retained_daily": daily_impact or {},
        "unexplained_drift_count": unexplained_drift_count,
        "v1_covers": "exactly four confirmed Class-A facts",
        "corpus_wide_reconciliation": False,
    }
    report["artifact_sha256"] = _hash({k: v for k, v in report.items() if k != "artifact_sha256"})
    return report


def render_jsonl(rows: Sequence[Mapping[str, Any]]) -> str:
    return "".join(_canonical_json(row) + "\n" for row in rows)
