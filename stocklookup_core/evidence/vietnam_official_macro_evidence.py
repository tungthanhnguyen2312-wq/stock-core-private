"""Retained first-party Vietnam macro observations for current descriptive use."""
from __future__ import annotations

import base64
import calendar
import copy
import hashlib
import html
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any, Mapping
from urllib.request import Request, urlopen

from stocklookup_core.evidence.field_identity import stable_id

CONTRACT_VERSION = "vietnam_macro_observation/v1"
SOURCE_ID = "NSO_VIETNAM_CPI_RELEASE"
SOURCE_NAME = "National Statistics Office of Vietnam"
NSO_CPI_RELEASES = (
    "https://www.nso.gov.vn/en/data-and-statistics/2026/07/consumer-price-index-gold-price-index-and-us-dollar-price-index-in-june-2026-q2-2026-and-the-first-six-months-of-2026/",
    "https://www.nso.gov.vn/en/data-and-statistics/2026/08/consumer-price-index-gold-price-index-and-us-dollar-price-index-in-july-and-the-first-seven-months-of-2026/",
)
NSO_HOMEPAGE = "https://www.nso.gov.vn/en/homepage/"
# Only official NSO CPI release pages linked from the retained homepage are followed; nothing is inferred from a calendar.
NSO_CPI_RELEASE_LOCATOR = re.compile(r"^https://www\.nso\.gov\.vn/en/data-and-statistics/\d{4}/\d{2}/consumer-price-index-gold-price-index-and-us-dollar-price-index-in-[a-z0-9-]+/$")
# Inventory and fetch budget are separate: every matching homepage link is inventoried (bounded;
# exceeding the bound blocks currency), while at most MAX_FETCHED_DISCOVERED_RELEASES are fetched.
# An inventoried link that is not fetched is retained as NOT_FETCHED and also blocks currency.
MAX_DISCOVERY_INVENTORY = 32
MAX_FETCHED_DISCOVERED_RELEASES = 3
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
# CURRENT_NEXT_RELEASE_UNANNOUNCED ends with the month after the next expected reference period (2026-09 CPI -> 2026-11-30).
UNANNOUNCED_CEILING_MONTHS_AFTER_PERIOD = 2
# Documented NSO lead grammar: inside a sentence whose subject is the CPI, a list of clauses
# "<verb> by X% <comparator>" joined by ", " / " and " / ", and ". A clause without its own verb
# ("by X% ...") is elliptical and inherits the immediately preceding clause's verb only across
# such a bare list separator. Any other word before "by" (declined, changed, but, ...) is outside
# the grammar and blocks the whole lead rather than inheriting a sign.
_SUPPORTED_VERBS = {"rose": 1, "increased": 1, "decreased": -1, "fell": -1}
_CLAUSE = re.compile(r"(?:\b([a-z]+)\s+)?\bby\s+(-?[0-9]+(?:\.[0-9]+)?)%\s*(year[- ]on[- ]year|over the same period last year|compared (?:with|to) the same period (?:of )?last year|compared (?:with|to) the previous month|compared (?:with|to) December [0-9]{4})?", re.I)
_MOM_NOUN = re.compile(r"month-on-month (increase|decrease) of\s+(-?[0-9]+(?:\.[0-9]+)?)%", re.I)
_LIST_SEPARATOR = re.compile(r"\s*,?\s*(?:and\s*)?", re.I)
_CPI_SUBJECT = re.compile(r"consumer price index \(CPI\)|\bthe CPI\b|\bCPI\b", re.I)
_SUBJECT_TO_VERB = re.compile(r"\s*(?:in [a-z]+(?:\s+[0-9]{4})?)?\s*", re.I)
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


def _raw_record(*, source_id: str, url: str, raw: bytes, content_type: str, retrieved_at: str, http_status: int, discovered_from: Mapping[str, Any] | None = None) -> dict[str, Any]:
    record = {"source_id": source_id, "locator": url, "retrieval_timestamp": retrieved_at, "publication_date": None, "http_status": http_status, "content_type": content_type, "payload_sha256": hashlib.sha256(raw).hexdigest(), "payload_base64": base64.b64encode(raw).decode("ascii"), "parse_status": "RETAINED_UNPARSED"}
    if discovered_from is not None:
        record["discovered_from"] = dict(discovered_from)
    return record


def _fetch_failed_record(*, url: str, retrieved_at: str, error: Exception, discovered_from: Mapping[str, Any]) -> dict[str, Any]:
    return {"source_id": SOURCE_ID, "locator": url, "retrieval_timestamp": retrieved_at, "publication_date": None, "http_status": getattr(error, "code", None), "content_type": None, "payload_sha256": None, "payload_base64": None, "parse_status": "FETCH_FAILED:" + type(error).__name__, "discovered_from": dict(discovered_from)}


def discover_cpi_release_inventory(homepage: Mapping[str, Any] | None) -> tuple[list[str], bool]:
    """(Every official CPI release link in the retained homepage bytes in a deterministic order, truncated?).

    The order only makes acquisition deterministic; it is never evidence of publication period.
    """
    if not homepage or not homepage.get("payload_base64"):
        return [], False
    page = base64.b64decode(str(homepage["payload_base64"])).decode("utf-8", errors="replace")
    found = {html.unescape(href) for href in re.findall(r"href\s*=\s*[\"']([^\"']+)[\"']", page, re.I)}
    matched = sorted((url for url in found if NSO_CPI_RELEASE_LOCATOR.match(url)), reverse=True)
    return matched[:MAX_DISCOVERY_INVENTORY], len(matched) > MAX_DISCOVERY_INVENTORY


def discover_cpi_release_locators(homepage: Mapping[str, Any] | None) -> list[str]:
    return discover_cpi_release_inventory(homepage)[0]


def _not_fetched_record(*, url: str, retrieved_at: str, discovered_from: Mapping[str, Any]) -> dict[str, Any]:
    return {"source_id": SOURCE_ID, "locator": url, "retrieval_timestamp": retrieved_at, "publication_date": None, "http_status": None, "content_type": None, "payload_sha256": None, "payload_base64": None, "parse_status": "NOT_FETCHED:FETCH_BUDGET_EXCEEDED", "discovered_from": dict(discovered_from)}


def _add_months(period: str, months: int) -> str:
    year, month = (int(part) for part in period.split("-")); index = year * 12 + month - 1 + months
    return f"{index // 12}-{index % 12 + 1:02d}"


def _unannounced_ceiling(period: str) -> str:
    year, month = (int(part) for part in _add_months(period, UNANNOUNCED_CEILING_MONTHS_AFTER_PERIOD).split("-"))
    return date(year, month, calendar.monthrange(year, month)[1]).isoformat()


def _signed(direction: int, number: str) -> float:
    value = float(number)
    if direction < 0:
        if value < 0:
            raise ValueError("NSO_CPI_AMBIGUOUS_SIGN")
        return -value
    return value


def _lead_claims(segment: str) -> tuple[set[float], set[float]]:
    """(YoY values, MoM values) from CPI-subject sentences under the documented clause grammar."""
    yoy: set[float] = set(); mom: set[float] = set()
    for sentence in re.split(r"(?<=[0-9a-z%)])\.\s+", segment):
        clauses, nouns = list(_CLAUSE.finditer(sentence)), list(_MOM_NOUN.finditer(sentence))
        if not clauses and not nouns:
            continue
        subjects = list(_CPI_SUBJECT.finditer(sentence, 0, min(m.start() for m in clauses + nouns)))
        if not subjects:
            raise ValueError("NSO_CPI_CLAIM_SUBJECT_UNRESOLVED")
        for noun in nouns:
            mom.add(_signed(-1 if noun.group(1).lower() == "decrease" else 1, noun.group(2)))
        direction, previous_end = None, None
        for clause in clauses:
            word = (clause.group(1) or "").lower()
            if word in _SUPPORTED_VERBS:
                # A verb opens the chain right after the CPI subject, or continues it across a bare separator.
                gap = sentence[subjects[-1].end() if previous_end is None else previous_end:clause.start(1)]
                if not (_SUBJECT_TO_VERB if previous_end is None else _LIST_SEPARATOR).fullmatch(gap):
                    raise ValueError("NSO_CPI_CLAIM_SUBJECT_UNRESOLVED")
                direction = _SUPPORTED_VERBS[word]
            elif word in {"", "and"}:
                if direction is None or previous_end is None or not _LIST_SEPARATOR.fullmatch(sentence[previous_end:clause.start()]):
                    raise ValueError("NSO_CPI_GOVERNING_VERB_UNRESOLVED")
            else:
                raise ValueError("NSO_CPI_UNSUPPORTED_GOVERNING_VERB")
            previous_end = clause.end()
            comparator = (clause.group(3) or "").lower()
            if comparator.startswith("compared") and "december" in comparator:
                continue  # year-to-date change: inside the grammar, neither YoY nor MoM
            if comparator.endswith("previous month"):
                mom.add(_signed(direction, clause.group(2)))
            elif comparator:
                yoy.add(_signed(direction, clause.group(2)))
    return yoy, mom


def _lead_cpi_segment(text: str) -> str:
    start = re.search(r"consumer price index \(CPI\)", text, re.I)
    if not start:
        raise ValueError("NSO_CPI_REQUIRED_PUBLICATION_METADATA_OR_YOY_CLAIM_NOT_FOUND")
    segment = text[start.start():start.start() + 600]
    stop = re.search(r"\ba\)\s|On average|average CPI|quarter of|gold price index|core inflation", segment, re.I)
    return segment[:stop.start()] if stop else segment


def _release_months(raw_html: str, text: str) -> set[str]:
    title = re.search(r"<title>(.*?)</title>", raw_html, re.I | re.S)
    from_title = re.search(r"price index in (" + "|".join(MONTHS) + r")\b", html.unescape(title.group(1)), re.I) if title else None
    from_lead = re.search(r"\(CPI\) in (" + "|".join(MONTHS) + r")\b", text, re.I)
    return {match.group(1).lower() for match in (from_title, from_lead) if match}


def _parse_cpi(record: Mapping[str, Any]) -> dict[str, Any]:
    raw_html = base64.b64decode(str(record["payload_base64"])).decode("utf-8", errors="replace"); text = _text(raw_html.encode("utf-8"))
    period = re.search(r"Reference period:\s*(\d{1,2})\s*/\s*(\d{4})", text, re.I)
    issued = re.search(r"Date of issue:\s*(\d{1,2}/\d{1,2}/\d{4})", text, re.I)
    if not (period and issued):
        raise ValueError("NSO_CPI_REQUIRED_PUBLICATION_METADATA_OR_YOY_CLAIM_NOT_FOUND")
    month, year = period.groups()
    if _release_months(raw_html, text) != {MONTHS[int(month) - 1]}:
        raise ValueError("NSO_CPI_TITLE_REFERENCE_PERIOD_MISMATCH")
    yoy, mom = _lead_claims(_lead_cpi_segment(text))
    if not yoy:
        raise ValueError("NSO_CPI_REQUIRED_PUBLICATION_METADATA_OR_YOY_CLAIM_NOT_FOUND")
    if len(yoy) > 1:
        raise ValueError("NSO_CPI_AMBIGUOUS_YOY_CLAIM")
    month_on_month = {"metric_id": "vn_cpi_mom", "value": next(iter(mom)) if len(mom) == 1 else None, "unit": "percent_mom", "status": "PARSED" if len(mom) == 1 else "AMBIGUOUS_NOT_EMITTED" if mom else "NOT_STATED_IN_LEAD", "regime_input": "NOT_AN_AXIS"}
    publication_date = _date(issued.group(1)); url = str(record["locator"])
    observation = {"metric_id": "vn_cpi_yoy", "value": next(iter(yoy)), "unit": "percent_yoy", "observation_period": f"{year}-{int(month):02d}", "effective_period": f"{year}-{int(month):02d}", "publication_date": publication_date, "retrieval_timestamp": record["retrieval_timestamp"], "source_document_identity": f"{SOURCE_ID}:{publication_date}:{hashlib.sha256(url.encode()).hexdigest()[:16]}", "source_id": SOURCE_ID, "source": SOURCE_NAME, "locator": url, "raw_payload_sha256": record["payload_sha256"], "raw_content_type": record["content_type"], "parse_status": "PARSED", "semantic_qualification": "QUALIFIED_OFFICIAL_RELEASE_TEXT", "month_on_month": month_on_month, "warnings": ["Monthly CPI year-on-year percentage stated in the retained NSO release.", "Publication date is date-level metadata; intraday historical-PIT timing is not asserted."], "fitness_for_use": {"current_descriptive": "QUALIFIED", "historical_pit": "DATE_LEVEL_QUALIFIED_AFTER_PUBLICATION_DATE", "trend_comparison": "QUALIFIED_WITH_SAME_METRIC_PREDECESSOR", "regime_input": "QUALIFIED"}}
    if record.get("discovered_from"):
        observation["discovered_from"] = dict(record["discovered_from"])
    return observation


def _unavailable(metric_id: str, category: str, unit: str, retrieved_at: str) -> dict[str, Any]:
    return {"metric_id": metric_id, "value": None, "unit": unit, "observation_period": None, "effective_period": None, "publication_date": None, "retrieval_timestamp": retrieved_at, "source_document_identity": None, "source_id": None, "source": None, "locator": None, "raw_payload_sha256": None, "raw_content_type": None, "parse_status": "NOT_ATTEMPTED_WITHOUT_QUALIFIED_SOURCE_DOCUMENT", "semantic_qualification": "UNAVAILABLE", "warnings": ["NO_RETAINED_FIRST_PARTY_RELEASE_WITH_AN_EXPLICIT_CURRENT_METRIC", f"category:{category}"], "fitness_for_use": {"current_descriptive": "UNAVAILABLE", "historical_pit": "BLOCKED", "trend_comparison": "BLOCKED", "regime_input": "BLOCKED"}}


#: The bounded "Next releases" block read for calendar entries (characters after the heading).
CALENDAR_BLOCK_CHARS = 1600


def _cpi_calendar_entries(homepage: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Every NSO "Next releases" CPI entry in the bounded block, as {release_date, reference_period or None}."""
    if not homepage or not homepage.get("payload_base64"):
        return []
    text = _text(base64.b64decode(str(homepage["payload_base64"])))
    heading = re.search(r"Next releases|next release", text, re.I)
    if not heading:
        return []
    block = text[heading.end():heading.end() + CALENDAR_BLOCK_CHARS]
    dates = list(re.finditer(r"([0-9]{1,2}/[0-9]{1,2}/[0-9]{4}):", block))
    entries = []
    for index, match in enumerate(dates):
        body = block[match.end():dates[index + 1].start() if index + 1 < len(dates) else len(block)]
        if not re.match(r"\s*Consumer price index", body, re.I):
            continue
        named = re.search(r"\bin (" + "|".join(MONTHS) + r") ([0-9]{4})", body[:160], re.I)
        entries.append({"release_date": _date(match.group(1)),
                        "reference_period": f"{named.group(2)}-{MONTHS.index(named.group(1).lower()) + 1:02d}" if named else None})
    return sorted(entries, key=lambda row: (row["release_date"], str(row["reference_period"])))


def _cpi_freshness(*, parsed: list[Mapping[str, Any]], cpi_raw: list[Mapping[str, Any]], discovery: Mapping[str, Any], homepage: Mapping[str, Any] | None, retrieved_at: str) -> dict[str, Any]:
    entries = _cpi_calendar_entries(homepage); session = retrieved_at[:10]
    freshness: dict[str, Any] = {"rule": "CURRENT through the day before the earliest outstanding retained NSO CPI calendar release; thereafter stale until a later retained release is parsed. No generic day threshold. Each calendar entry already covered by a parsed release is superseded individually; CURRENT_NEXT_RELEASE_UNANNOUNCED applies only when no entry is outstanding, holds only through valid_through (end of the month after the next expected reference period, a ceiling that never extends an earlier official deadline) and never while any discovered or retained release is unqualified. Publication period is never inferred from a locator.", "next_expected_official_release": entries[0]["release_date"] if entries else None, "calendar_entries": entries, "status": "STALE_OR_UNAVAILABLE", "valid_through": None, "reason_codes": []}
    if not parsed:
        freshness["reason_codes"].append("NO_PARSED_RETAINED_NSO_CPI_RELEASE"); return freshness
    latest = parsed[-1]; ceiling = _unannounced_ceiling(str(latest["observation_period"]))
    # Any retained or discovered CPI release that is not parsed may be newer: its period is unknown,
    # whatever its locator says, so it always blocks currency.
    unresolved = sorted({str(row.get("locator")) for row in cpi_raw if row.get("parse_status") != "PARSED"}
                        | {url for url, state in discovery["locator_status"].items() if state != "PARSED"})
    covered = [e for e in entries if (e["reference_period"] is not None and e["reference_period"] <= str(latest["observation_period"]))
               or (e["reference_period"] is None and e["release_date"] <= str(latest["publication_date"]))]
    outstanding = [e for e in entries if e not in covered]
    next_release = outstanding[0]["release_date"] if outstanding else None
    freshness["next_expected_official_release"] = next_release
    if covered:
        freshness["superseded_calendar_entry"] = covered[0]; freshness["superseded_calendar_entries"] = covered
        freshness["reason_codes"].append("CALENDAR_ENTRY_ALREADY_RETAINED")
    if discovery.get("inventory_truncated"):
        freshness["reason_codes"].append("DISCOVERY_INVENTORY_LIMIT_EXCEEDED"); return freshness
    if unresolved:
        freshness["reason_codes"].append("NEWER_DISCOVERED_RELEASE_NOT_QUALIFIED"); freshness["unqualified_discovered_locators"] = unresolved
        return freshness
    if next_release:
        freshness["valid_through"] = min(ceiling, (date.fromisoformat(next_release) - timedelta(days=1)).isoformat())
        if session < next_release and session <= ceiling:
            freshness["status"] = "CURRENT"
        else:
            freshness["reason_codes"].append("NEXT_OFFICIAL_RELEASE_DUE" if session >= next_release else "FRESHNESS_CEILING_EXCEEDED")
        return freshness
    if not freshness["reason_codes"]:
        freshness["reason_codes"].append("NO_RETAINED_NEXT_CPI_CALENDAR_ENTRY")
    freshness["valid_through"] = ceiling
    if latest.get("semantic_qualification") == "QUALIFIED_OFFICIAL_RELEASE_TEXT" and session <= ceiling:
        freshness["status"] = "CURRENT_NEXT_RELEASE_UNANNOUNCED"
    else:
        freshness["reason_codes"].append("FRESHNESS_CEILING_EXCEEDED")
    return freshness


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
        if not row.get("payload_base64"):
            failures.append(str(row.get("parse_status"))); continue
        try:
            observation = _parse_cpi(row); parsed.append(observation); row["publication_date"] = observation["publication_date"]; row["parse_status"] = "PARSED"
        except ValueError as exc:
            row["parse_status"] = "PARSE_BLOCKED:" + str(exc); failures.append(str(exc))
    parsed.sort(key=lambda row: (str(row["observation_period"]), str(row["publication_date"])))
    revision_chains: dict[str, list[str]] = {}
    for observation in parsed:
        revision_chains.setdefault(str(observation["source_document_identity"]), []).append(str(observation["raw_payload_sha256"]))
    homepage = next((row for row in records if row.get("source_id") == "NSO_RELEASE_CALENDAR"), None)
    retained_status = {str(row.get("locator")): str(row.get("parse_status")).split(":")[0] for row in cpi_raw}
    discovered, truncated = discover_cpi_release_inventory(homepage)
    discovery = {"homepage_locator": homepage.get("locator") if homepage else None, "homepage_payload_sha256": homepage.get("payload_sha256") if homepage else None, "max_discovery_inventory": MAX_DISCOVERY_INVENTORY, "max_fetched_discovered_releases": MAX_FETCHED_DISCOVERED_RELEASES, "inventory_truncated": truncated, "discovered_locators": discovered, "locator_status": {url: retained_status.get(url, "DISCOVERED_NOT_RETAINED") for url in discovered}}
    observations: dict[str, list[dict[str, Any]]] = {"vn_cpi_yoy": parsed}
    for metric_id, category, unit in TARGET_METRICS[1:]:
        observations[metric_id] = [_unavailable(metric_id, category, unit, retrieved_at)]
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "retrieved_at": retrieved_at, "source_results": {SOURCE_ID: "PARSED" if parsed else "PARSE_BLOCKED", "NSO_RELEASE_CALENDAR": "RETAINED" if homepage else "UNAVAILABLE", "SBV_POLICY_RATE": "UNAVAILABLE", "SBV_CENTRAL_FX": "UNAVAILABLE", "SBV_CREDIT_GROWTH": "UNAVAILABLE", "SBV_SYSTEM_LIQUIDITY": "UNAVAILABLE", "HNX_GOVERNMENT_BOND_YIELD": "DISCOVERY_ONLY_NOT_RETAINED"}, "raw_payloads": records, "observations": observations, "release_discovery": discovery, "freshness_rules": {"vn_cpi_yoy": _cpi_freshness(parsed=parsed, cpi_raw=cpi_raw, discovery=discovery, homepage=homepage, retrieved_at=retrieved_at), "vn_policy_rate": {"rule": "Requires a retained SBV rate publication identifying rate and effective date.", "status": "UNAVAILABLE"}, "vn_usd_vnd": {"rule": "Requires a retained SBV central/reference-rate publication for a stated business date.", "status": "UNAVAILABLE"}, "vn_credit_growth": {"rule": "Requires a retained SBV credit release stating basis and as-of date.", "status": "UNAVAILABLE"}, "vn_system_liquidity": {"rule": "Requires a retained official system-liquidity metric and its definition.", "status": "UNAVAILABLE"}, "vn_government_bond_yield": {"rule": "Requires a retained official yield series with stated tenor and aggregation.", "status": "UNAVAILABLE"}}, "revision_policy": "Each source-document byte payload is retained by SHA-256. A later distinct hash for the same source document is a new retained revision; no prior payload is overwritten.", "revision_chains": [{"source_document_identity": identity, "retained_payload_sha256": hashes, "revision_count": len(hashes) - 1} for identity, hashes in sorted(revision_chains.items())], "revisions_retained": {"release_documents": len(cpi_raw), "distinct_payload_hashes": len({row.get("payload_sha256") for row in cpi_raw if row.get("payload_sha256")}), "revision_payloads": sum(len(hashes) - 1 for hashes in revision_chains.values())}, "authority_boundary": {"current_descriptive": "CPI_ONLY", "historical_pit": "DATE_LEVEL_CPI_ONLY", "forecast_causality_sizing_execution": "NOT_EMITTED"}, "parse_failures": failures, "is_actionable": False}
    artifact.update(content_identity(artifact)); return artifact


def _macro_unavailable(indicator_id: str, category: str, reason: str, retrieved_at: Any) -> dict[str, Any]:
    return {"indicator_id": indicator_id, "country_or_region": "Vietnam", "category": category, "value": None, "unit": "UNKNOWN", "observation_date": None, "released_at": None, "source": "Vietnam official macro evidence", "source_identity": "VIETNAM_OFFICIAL_MACRO:" + indicator_id, "url": None, "retrieved_at": retrieved_at, "freshness": {"status": "UNAVAILABLE"}, "revision_state": "UNKNOWN", "authority": "OFFICIAL_SOURCE_ROUTE_ATTEMPTED", "status": "UNAVAILABLE", "limitations": [reason], "previous_observation_date": None, "previous_value": None, "raw_payload_sha256": None}


def current_macro_observations(artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    cpi = list((artifact.get("observations") or {}).get("vn_cpi_yoy") or []); cpi.sort(key=lambda row: (str(row.get("observation_period")), str(row.get("publication_date"))))
    if cpi and cpi[-1].get("value") is not None:
        latest, previous = cpi[-1], cpi[-2] if len(cpi) > 1 else {}; freshness = dict((artifact.get("freshness_rules") or {}).get("vn_cpi_yoy") or {}); limitations = list(latest["warnings"])
        # Direction needs the exactly adjacent prior month; a gap is never bridged or interpolated.
        if previous and previous.get("observation_period") != _add_months(str(latest["observation_period"]), -1):
            limitations.append(f"PREDECESSOR_PERIOD_NOT_ADJACENT:{previous.get('observation_period')}->{latest['observation_period']}"); previous = {}
        rows = [{"indicator_id": "vn_cpi_yoy", "country_or_region": "Vietnam", "category": "inflation", "value": latest["value"], "unit": latest["unit"], "observation_date": latest["observation_period"], "released_at": latest["publication_date"], "source": latest["source"], "source_identity": latest["source_document_identity"], "url": latest["locator"], "retrieved_at": latest["retrieval_timestamp"], "freshness": {"frequency": "MONTHLY", "status": freshness.get("status"), "next_expected_official_release": freshness.get("next_expected_official_release"), "valid_through": freshness.get("valid_through"), "reason_codes": list(freshness.get("reason_codes") or []), "rule": freshness.get("rule")}, "revision_state": "RETAINED_SOURCE_DOCUMENT_REVISION", "authority": "OFFICIAL_PUBLIC_SOURCE", "status": "AVAILABLE", "limitations": limitations, "month_on_month": copy.deepcopy(latest.get("month_on_month")), "previous_observation_date": previous.get("observation_period"), "previous_value": previous.get("value"), "raw_payload_sha256": latest["raw_payload_sha256"]}]
    else:
        rows = [_macro_unavailable("vn_cpi_yoy", "inflation", "NO_PARSED_RETAINED_NSO_CPI_RELEASE", artifact.get("retrieved_at"))]
    for metric_id, category, _unit in TARGET_METRICS[1:]:
        rows.append(_macro_unavailable(metric_id, category, "NO_RETAINED_FIRST_PARTY_EXPLICIT_METRIC", artifact.get("retrieved_at")))
    return rows


def acquire(*, retrieved_at: str | None = None) -> dict[str, Any]:
    retrieved_at = retrieved_at or _now(); records: list[dict[str, Any]] = []; headers = {"User-Agent": "StockLookup-vietnam-official-macro-evidence/1.0"}
    with urlopen(Request(NSO_HOMEPAGE, headers=headers), timeout=30) as response:
        homepage = _raw_record(source_id="NSO_RELEASE_CALENDAR", url=NSO_HOMEPAGE, raw=response.read(), content_type=response.headers.get_content_type(), retrieved_at=retrieved_at, http_status=response.status)
    for url in NSO_CPI_RELEASES:
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            records.append(_raw_record(source_id=SOURCE_ID, url=url, raw=response.read(), content_type=response.headers.get_content_type(), retrieved_at=retrieved_at, http_status=response.status))
    provenance = {"source_id": "NSO_RELEASE_CALENDAR", "locator": NSO_HOMEPAGE, "payload_sha256": homepage["payload_sha256"]}
    fetched = 0
    for url in discover_cpi_release_locators(homepage):
        if url in NSO_CPI_RELEASES:
            continue
        if fetched >= MAX_FETCHED_DISCOVERED_RELEASES:
            records.append(_not_fetched_record(url=url, retrieved_at=retrieved_at, discovered_from=provenance)); continue
        fetched += 1
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as response:
                records.append(_raw_record(source_id=SOURCE_ID, url=url, raw=response.read(), content_type=response.headers.get_content_type(), retrieved_at=retrieved_at, http_status=response.status, discovered_from=provenance))
        except Exception as exc:  # retained as a failure; a discovered release that cannot be fetched never yields a value
            records.append(_fetch_failed_record(url=url, retrieved_at=retrieved_at, error=exc, discovered_from=provenance))
    records.append(homepage)
    return build(raw_records=records, retrieved_at=retrieved_at)
