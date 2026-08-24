"""Retained first-party Vietnam macro observations for current descriptive use."""
from __future__ import annotations

import base64
import copy
import hashlib
import html
import re
from datetime import UTC, datetime
from typing import Any, Mapping
from urllib.request import Request, urlopen

from field_temporal_contract import stable_id

CONTRACT_VERSION = "vietnam_macro_observation/v1"
SOURCE_ID = "NSO_VIETNAM_CPI_RELEASE"
SOURCE_NAME = "National Statistics Office of Vietnam"
NSO_CPI_RELEASES = (
    "https://www.nso.gov.vn/en/data-and-statistics/2026/07/consumer-price-index-gold-price-index-and-us-dollar-price-index-in-june-2026-q2-2026-and-the-first-six-months-of-2026/",
    "https://www.nso.gov.vn/en/data-and-statistics/2026/08/consumer-price-index-gold-price-index-and-us-dollar-price-index-in-july-and-the-first-seven-months-of-2026/",
)
NSO_HOMEPAGE = "https://www.nso.gov.vn/en/homepage/"
TARGET_METRICS = (
    ("vn_cpi_yoy", "inflation", "percent_yoy"),
    ("vn_policy_rate", "domestic_rates", "percent_per_annum"),
    ("vn_usd_vnd", "fx", "vnd_per_usd"),
    ("vn_credit_growth", "credit", "percent_ytd"),
    ("vn_system_liquidity", "liquidity", "UNKNOWN"),
    ("vn_government_bond_yield", "government_bonds", "percent_per_annum"),
)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(raw: bytes) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw.decode("utf-8", errors="replace")))).strip()


def _date(value: str) -> str:
    match = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*", value)
    if not match:
        raise ValueError("UNPARSEABLE_DATE:" + value)
    day, month, year = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _raw_record(*, source_id: str, url: str, raw: bytes, content_type: str, retrieved_at: str, http_status: int) -> dict[str, Any]:
    return {"source_id": source_id, "locator": url, "retrieval_timestamp": retrieved_at, "publication_date": None, "http_status": http_status, "content_type": content_type, "payload_sha256": hashlib.sha256(raw).hexdigest(), "payload_base64": base64.b64encode(raw).decode("ascii"), "parse_status": "RETAINED_UNPARSED"}


def _parse_cpi(record: Mapping[str, Any]) -> dict[str, Any]:
    text = _text(base64.b64decode(str(record["payload_base64"])))
    period = re.search(r"Reference period:\s*(\d{1,2})\s*/\s*(\d{4})", text, re.I)
    issued = re.search(r"Date of issue:\s*(\d{1,2}/\d{1,2}/\d{4})", text, re.I)
    yoy = re.search(r"(?:CPI\)|consumer price index \(CPI\)).{0,420}?(?:rose by|increased by)\s+([0-9]+(?:\.[0-9]+)?)%\s+(?:over the same period last year|year-on-year)", text, re.I)
    if not (period and issued and yoy):
        raise ValueError("NSO_CPI_REQUIRED_PUBLICATION_METADATA_OR_YOY_CLAIM_NOT_FOUND")
    month, year = period.groups(); publication_date = _date(issued.group(1)); url = str(record["locator"])
    return {"metric_id": "vn_cpi_yoy", "value": float(yoy.group(1)), "unit": "percent_yoy", "observation_period": f"{year}-{int(month):02d}", "effective_period": f"{year}-{int(month):02d}", "publication_date": publication_date, "retrieval_timestamp": record["retrieval_timestamp"], "source_document_identity": f"{SOURCE_ID}:{publication_date}:{hashlib.sha256(url.encode()).hexdigest()[:16]}", "source_id": SOURCE_ID, "source": SOURCE_NAME, "locator": url, "raw_payload_sha256": record["payload_sha256"], "raw_content_type": record["content_type"], "parse_status": "PARSED", "semantic_qualification": "QUALIFIED_OFFICIAL_RELEASE_TEXT", "warnings": ["Monthly CPI year-on-year percentage stated in the retained NSO release.", "Publication date is date-level metadata; intraday historical-PIT timing is not asserted."], "fitness_for_use": {"current_descriptive": "QUALIFIED", "historical_pit": "DATE_LEVEL_QUALIFIED_AFTER_PUBLICATION_DATE", "trend_comparison": "QUALIFIED_WITH_SAME_METRIC_PREDECESSOR", "regime_input": "QUALIFIED"}}


def _unavailable(metric_id: str, category: str, unit: str, retrieved_at: str) -> dict[str, Any]:
    return {"metric_id": metric_id, "value": None, "unit": unit, "observation_period": None, "effective_period": None, "publication_date": None, "retrieval_timestamp": retrieved_at, "source_document_identity": None, "source_id": None, "source": None, "locator": None, "raw_payload_sha256": None, "raw_content_type": None, "parse_status": "NOT_ATTEMPTED_WITHOUT_QUALIFIED_SOURCE_DOCUMENT", "semantic_qualification": "UNAVAILABLE", "warnings": ["NO_RETAINED_FIRST_PARTY_RELEASE_WITH_AN_EXPLICIT_CURRENT_METRIC", f"category:{category}"], "fitness_for_use": {"current_descriptive": "UNAVAILABLE", "historical_pit": "BLOCKED", "trend_comparison": "BLOCKED", "regime_input": "BLOCKED"}}


def _next_cpi_release(homepage: Mapping[str, Any] | None) -> str | None:
    if not homepage:
        return None
    text = _text(base64.b64decode(str(homepage["payload_base64"])))
    match = re.search(r"(?:Next releases|next release).{0,240}?([0-9]{1,2}/[0-9]{1,2}/2026):\s*Consumer price index", text, re.I)
    return _date(match.group(1)) if match else None


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(value)); payload.pop("artifact_identity", None); payload.pop("artifact_sha256", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": "vietnam_official_macro_evidence:" + digest}


def build(*, raw_records: list[Mapping[str, Any]], retrieved_at: str) -> dict[str, Any]:
    records = [copy.deepcopy(dict(row)) for row in raw_records]
    cpi_raw = [row for row in records if row.get("source_id") == SOURCE_ID]
    parsed: list[dict[str, Any]] = []
    failures: list[str] = []
    for row in cpi_raw:
        try:
            observation = _parse_cpi(row); parsed.append(observation); row["publication_date"] = observation["publication_date"]; row["parse_status"] = "PARSED"
        except ValueError as exc:
            row["parse_status"] = "PARSE_BLOCKED:" + str(exc); failures.append(str(exc))
    parsed.sort(key=lambda row: (str(row["observation_period"]), str(row["publication_date"])))
    revision_chains: dict[str, list[str]] = {}
    for observation in parsed:
        revision_chains.setdefault(str(observation["source_document_identity"]), []).append(str(observation["raw_payload_sha256"]))
    homepage = next((row for row in records if row.get("source_id") == "NSO_RELEASE_CALENDAR"), None)
    next_release = _next_cpi_release(homepage)
    observations: dict[str, list[dict[str, Any]]] = {"vn_cpi_yoy": parsed}
    for metric_id, category, unit in TARGET_METRICS[1:]:
        observations[metric_id] = [_unavailable(metric_id, category, unit, retrieved_at)]
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "retrieved_at": retrieved_at, "source_results": {SOURCE_ID: "PARSED" if parsed else "PARSE_BLOCKED", "NSO_RELEASE_CALENDAR": "RETAINED" if homepage else "UNAVAILABLE", "SBV_POLICY_RATE": "UNAVAILABLE", "SBV_CENTRAL_FX": "UNAVAILABLE", "SBV_CREDIT_GROWTH": "UNAVAILABLE", "SBV_SYSTEM_LIQUIDITY": "UNAVAILABLE", "HNX_GOVERNMENT_BOND_YIELD": "DISCOVERY_ONLY_NOT_RETAINED"}, "raw_payloads": records, "observations": observations, "freshness_rules": {"vn_cpi_yoy": {"rule": "CURRENT through the explicitly retained next NSO CPI release date; thereafter stale until a later retained release is parsed. No generic day threshold.", "next_expected_official_release": next_release, "status": "CURRENT" if parsed and (next_release is None or retrieved_at[:10] < next_release) else "STALE_OR_UNAVAILABLE"}, "vn_policy_rate": {"rule": "Requires a retained SBV rate publication identifying rate and effective date.", "status": "UNAVAILABLE"}, "vn_usd_vnd": {"rule": "Requires a retained SBV central/reference-rate publication for a stated business date.", "status": "UNAVAILABLE"}, "vn_credit_growth": {"rule": "Requires a retained SBV credit release stating basis and as-of date.", "status": "UNAVAILABLE"}, "vn_system_liquidity": {"rule": "Requires a retained official system-liquidity metric and its definition.", "status": "UNAVAILABLE"}, "vn_government_bond_yield": {"rule": "Requires a retained official yield series with stated tenor and aggregation.", "status": "UNAVAILABLE"}}, "revision_policy": "Each source-document byte payload is retained by SHA-256. A later distinct hash for the same source document is a new retained revision; no prior payload is overwritten.", "revision_chains": [{"source_document_identity": identity, "retained_payload_sha256": hashes, "revision_count": len(hashes) - 1} for identity, hashes in sorted(revision_chains.items())], "revisions_retained": {"release_documents": len(cpi_raw), "distinct_payload_hashes": len({row.get("payload_sha256") for row in cpi_raw}), "revision_payloads": sum(len(hashes) - 1 for hashes in revision_chains.values())}, "authority_boundary": {"current_descriptive": "CPI_ONLY", "historical_pit": "DATE_LEVEL_CPI_ONLY", "forecast_causality_sizing_execution": "NOT_EMITTED"}, "parse_failures": failures, "is_actionable": False}
    artifact.update(content_identity(artifact)); return artifact


def _macro_unavailable(indicator_id: str, category: str, reason: str, retrieved_at: Any) -> dict[str, Any]:
    return {"indicator_id": indicator_id, "country_or_region": "Vietnam", "category": category, "value": None, "unit": "UNKNOWN", "observation_date": None, "released_at": None, "source": "Vietnam official macro evidence", "source_identity": "VIETNAM_OFFICIAL_MACRO:" + indicator_id, "url": None, "retrieved_at": retrieved_at, "freshness": {"status": "UNAVAILABLE"}, "revision_state": "UNKNOWN", "authority": "OFFICIAL_SOURCE_ROUTE_ATTEMPTED", "status": "UNAVAILABLE", "limitations": [reason], "previous_observation_date": None, "previous_value": None, "raw_payload_sha256": None}


def current_macro_observations(artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    cpi = list((artifact.get("observations") or {}).get("vn_cpi_yoy") or []); cpi.sort(key=lambda row: (str(row.get("observation_period")), str(row.get("publication_date"))))
    if cpi and cpi[-1].get("value") is not None:
        latest, previous = cpi[-1], cpi[-2] if len(cpi) > 1 else {}; freshness = dict((artifact.get("freshness_rules") or {}).get("vn_cpi_yoy") or {})
        rows = [{"indicator_id": "vn_cpi_yoy", "country_or_region": "Vietnam", "category": "inflation", "value": latest["value"], "unit": latest["unit"], "observation_date": latest["observation_period"], "released_at": latest["publication_date"], "source": latest["source"], "source_identity": latest["source_document_identity"], "url": latest["locator"], "retrieved_at": latest["retrieval_timestamp"], "freshness": {"frequency": "MONTHLY", "status": freshness.get("status"), "next_expected_official_release": freshness.get("next_expected_official_release"), "rule": freshness.get("rule")}, "revision_state": "RETAINED_SOURCE_DOCUMENT_REVISION", "authority": "OFFICIAL_PUBLIC_SOURCE", "status": "AVAILABLE", "limitations": latest["warnings"], "previous_observation_date": previous.get("observation_period"), "previous_value": previous.get("value"), "raw_payload_sha256": latest["raw_payload_sha256"]}]
    else:
        rows = [_macro_unavailable("vn_cpi_yoy", "inflation", "NO_PARSED_RETAINED_NSO_CPI_RELEASE", artifact.get("retrieved_at"))]
    for metric_id, category, _unit in TARGET_METRICS[1:]:
        rows.append(_macro_unavailable(metric_id, category, "NO_RETAINED_FIRST_PARTY_EXPLICIT_METRIC", artifact.get("retrieved_at")))
    return rows


def acquire(*, retrieved_at: str | None = None) -> dict[str, Any]:
    retrieved_at = retrieved_at or _now(); records: list[dict[str, Any]] = []
    for url in NSO_CPI_RELEASES:
        with urlopen(Request(url, headers={"User-Agent": "StockLookup-vietnam-official-macro-evidence/1.0"}), timeout=30) as response:
            records.append(_raw_record(source_id=SOURCE_ID, url=url, raw=response.read(), content_type=response.headers.get_content_type(), retrieved_at=retrieved_at, http_status=response.status))
    with urlopen(Request(NSO_HOMEPAGE, headers={"User-Agent": "StockLookup-vietnam-official-macro-evidence/1.0"}), timeout=30) as response:
        records.append(_raw_record(source_id="NSO_RELEASE_CALENDAR", url=NSO_HOMEPAGE, raw=response.read(), content_type=response.headers.get_content_type(), retrieved_at=retrieved_at, http_status=response.status))
    return build(raw_records=records, retrieved_at=retrieved_at)
