"""Incremental, hash-stated store for market-wide canonical financial facts.

LAYOUT (beneath the runtime root -- generated runtime data, never the source repo)

    data/canonical-financial-facts/
        facts/<TICKER>.jsonl.gz        one deterministic shard per ticker
        ingest_state.json              per-ticker source hashes + shard hashes
        coverage_report.json           deterministic market-wide coverage
        coverage_by_metric.csv         status counts, one row per canonical metric
        unresolved_metric_queue.jsonl  metrics needing review -- never whole tickers
        conflict_queue.jsonl           every conflict, with both disagreeing values

WHY THIS SITS BESIDE THE RAW STORE RATHER THAN INSIDE IT
    Layer 1's defining property is that a mapping rule discovered next month must apply to
    bytes already on disk without re-fetching the universe. Writing canonical facts back into
    the observation shards would destroy exactly that: every mapper change would rewrite the
    retained evidence. The two stores are separate, and this one is disposable -- deleting it
    loses nothing that cannot be rebuilt from the raw shards.

INCREMENTAL CONTRACT
    A ticker is rebuilt when its `inputs_fingerprint` changes. That fingerprint covers the
    source shard's SHA-256 **and** the mapper, resolver and schema versions **and** the
    applicability inputs, for the reason `raw_financial_store` documents: keying on source
    bytes alone would leave every shard looking `unchanged` after a mapping change, so the
    store would keep serving facts built by a mapper that no longer exists.

DETERMINISM
    Same shards and same versions produce byte-identical outputs. `generated_at` is the only
    clock-dependent field and is excluded from `state_fingerprint`.

THE QUEUES ARE PER METRIC, NEVER PER TICKER
    A ticker with 11 clean metrics and one conflicted one is not a broken ticker. Only the
    conflicted metric enters the queue, carrying its own reason and both disagreeing values,
    so review effort scales with genuine exceptions rather than with universe size.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from atomic_io import atomic_write_file, atomic_write_json
from canonical_financial_facts import (
    CONTRACT_VERSION,
    MAPPER_VERSION,
    METRIC_REGISTRY,
    SCHEMA_VERSION as FACT_SCHEMA_VERSION,
    STATUS_CONFLICTED,
    STATUS_NOT_APPLICABLE,
    STATUS_PARTIAL,
    STATUS_PROVIDER_REPORTED,
    STATUS_QUALIFIED,
    STATUS_UNAVAILABLE,
    SUPPORTED_STATUSES,
    build_facts,
)
from canonical_financial_resolvers import VERSION as RESOLVER_VERSION
from financial_entity_applicability import (
    VERSION as APPLICABILITY_VERSION,
    evaluate_ticker,
    load_entity_profiles,
)
from semantic_evidence_bridge import financial_identity_is_stock_metric
from raw_financial_store import (
    load_state as load_raw_state,
    observations_root,
    read_shard,
    state_index as raw_state_index,
)
from statement_taxonomy_classifier import classify_statement_taxonomy

STORE_SCHEMA_VERSION = "1.0.0"

STORE_RELATIVE = Path("data") / "canonical-financial-facts"
FACTS_RELATIVE = STORE_RELATIVE / "facts"
STATE_FILENAME = "ingest_state.json"
COVERAGE_FILENAME = "coverage_report.json"
COVERAGE_CSV_FILENAME = "coverage_by_metric.csv"
UNRESOLVED_FILENAME = "unresolved_metric_queue.jsonl"
CONFLICT_FILENAME = "conflict_queue.jsonl"

_SHARD_SUFFIX = ".jsonl.gz"

#: Statuses that mean "a human could resolve this with more evidence". `not_applicable` is
#: deliberately absent: it is a verdict, and queueing it would invite someone to go looking
#: for a bank's EBITDA.
UNRESOLVED_STATUSES = (STATUS_PARTIAL, STATUS_CONFLICTED, STATUS_UNAVAILABLE)


def store_root(runtime_root: Path | str) -> Path:
    return Path(runtime_root) / STORE_RELATIVE


def facts_root(runtime_root: Path | str) -> Path:
    return Path(runtime_root) / FACTS_RELATIVE


def state_path(runtime_root: Path | str) -> Path:
    return store_root(runtime_root) / STATE_FILENAME


def shard_path(runtime_root: Path | str, ticker: str) -> Path:
    return facts_root(runtime_root) / f"{ticker.upper()}{_SHARD_SUFFIX}"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fact_lines(facts: Iterable[Mapping[str, Any]]) -> str:
    return "".join(_canonical_json(dict(fact)) + "\n" for fact in facts)


def encode_shard(facts: Iterable[Mapping[str, Any]]) -> bytes:
    body = fact_lines(facts).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, compresslevel=9) as handle:
        handle.write(body)
    return buffer.getvalue()


def decode_shard(raw: bytes) -> list[dict[str, Any]]:
    text = gzip.decompress(raw).decode("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def read_facts(runtime_root: Path | str, ticker: str) -> list[dict[str, Any]]:
    path = shard_path(runtime_root, ticker)
    if not path.exists():
        return []
    return decode_shard(path.read_bytes())


def load_official_citations(runtime_root: Path | str) -> dict[tuple, dict[str, Any]]:
    """Independently qualified official values, keyed by (ticker, canonical metric, period).

    These are the only route to `qualified`, because they are the only place a currency and
    an absolute unit scale are actually evidenced. Read-only: this module never writes to
    `data/official-evidence/`, which `evidence_promotion.py` alone may do.

    The retained citations are annual (`2024`) while every retained provider payload is
    quarterly, so a naive key match never fires. For a **stock** metric the two periods name
    the same instant -- a balance sheet dated 31 December 2024 is both the FY2024 year-end
    and the 2024-Q4 period end -- so an annual citation is additionally keyed to `YYYY-Q4`.
    That equivalence does not hold for a **flow** metric: FY2024 revenue is not Q4 revenue,
    and no such alias is emitted. The distinction is taken from the metric registry's own
    statement family rather than from a hand-maintained list.

    The alias is not a convenience. It is what lets an independently audited figure confirm a
    provider value: HPG's provider-reported 2024-Q4 `undistributed_earnings` is
    49,599,124,109,203, matching the audited FY2024 citation digit for digit, which is what
    evidences VND and unit scale for that fact.
    """
    stock_metrics = {metric for metric, definition in METRIC_REGISTRY.items()
                     if definition["statement"] == "balance_sheet"}
    root = Path(runtime_root) / "data" / "official-evidence"
    mapping = {
        "profit_before_tax": "profit_before_tax",
        "interest_expense": "interest_expense",
        "depreciation_and_amortization": "depreciation_and_amortization",
        "retained_earnings": "retained_earnings",
        "current_liabilities": "current_liabilities",
        "total_assets": "total_assets",
        "shareholders_equity": "shareholders_equity",
        "revenue": "revenue",
        "net_income": "net_income",
        "operating_cash_flow": "operating_cash_flow",
        "cash_and_equivalents": "cash_and_equivalents",
        "total_interest_bearing_debt": "total_interest_bearing_debt",
    }
    citations: dict[tuple, dict[str, Any]] = {}
    for name in ("ebitda_component_citations.jsonl", "financial_identity_citations.jsonl"):
        path = root / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            metric = mapping.get(str(record.get("metric") or record.get("identity_type") or ""))
            ticker = str(record.get("ticker") or "").upper()
            period = str(record.get("reporting_period") or "")
            value = record.get("value")
            if not (metric and ticker and period) or value is None:
                continue
            entry = {
                "citation_id": record.get("citation_id"),
                "evidence_id": record.get("evidence_id"),
                "value": value,
                "currency": record.get("currency") or "VND",
                "scale": record.get("scale") or "units",
            }
            citations[(ticker, metric, period)] = entry
            if (metric in stock_metrics or financial_identity_is_stock_metric(metric)) and period.isdigit():
                citations.setdefault((ticker, metric, f"{period}-Q4"),
                                     {**entry, "period_alias": "annual_year_end_is_q4_end"})
    return citations


def _applicability_for(ticker: str, observations: Sequence[Mapping[str, Any]],
                       profiles: Mapping[str, str]) -> dict[str, Any]:
    """Archetype + per-metric applicability, from the same two evidence families as layer 2."""
    balance_items = sorted({str(record["raw_item_id"]) for record in observations
                            if record["statement_family"] == "balance_sheet"})
    income_items = sorted({str(record["raw_item_id"]) for record in observations
                           if record["statement_family"] == "income_statement"})
    taxonomy = classify_statement_taxonomy(balance_items, ticker=ticker) if balance_items else None
    return evaluate_ticker(
        ticker,
        manual_entity_type=profiles.get(ticker.upper()),
        balance_sheet_taxonomy=(taxonomy or {}).get("statement_taxonomy") if taxonomy else None,
        income_statement_item_ids=income_items if income_items else None,
    )


def _inputs_fingerprint(source_sha256: str, applicability: Mapping[str, Any]) -> str:
    return _fingerprint({
        "source_shard_sha256": source_sha256,
        "fact_schema_version": FACT_SCHEMA_VERSION,
        "store_schema_version": STORE_SCHEMA_VERSION,
        "mapper_version": MAPPER_VERSION,
        "resolver_version": RESOLVER_VERSION,
        "applicability_version": APPLICABILITY_VERSION,
        "contract_version": CONTRACT_VERSION,
        "archetype": applicability.get("archetype", {}).get("template_family"),
        "issuer_entity_type": applicability.get("archetype", {}).get("issuer_entity_type"),
    })


def build_ticker_facts(runtime_root: Path | str, ticker: str, *,
                       profiles: Mapping[str, str],
                       official_citations: Mapping[tuple, Mapping[str, Any]]) -> dict[str, Any]:
    observations = read_shard(runtime_root, ticker)
    applicability = _applicability_for(ticker, observations, profiles)
    built = build_facts(ticker, observations, applicability=applicability,
                        official_citations=official_citations)
    built["applicability"] = applicability
    return built


def ingest(runtime_root: Path | str, *, generated_at: str, execute: bool = False,
           tickers: Iterable[str] | None = None) -> dict[str, Any]:
    """Build canonical facts for every ticker with a raw shard, rebuilding only what changed."""
    runtime_root = Path(runtime_root)
    raw_state = raw_state_index(load_raw_state(runtime_root))
    if not raw_state:
        return {"executed": False, "ok": False,
                "reason": "raw observation store is missing or has an unsupported schema",
                "counts": {}}

    profiles = load_entity_profiles(Path(__file__).with_name("config") / "ticker_entity_profiles.csv")
    official_citations = load_official_citations(runtime_root)
    previous = {str(record["ticker"]): dict(record)
                for record in (_load_state(runtime_root).get("tickers") or [])}
    wanted = {ticker.upper() for ticker in tickers} if tickers is not None else None

    records: list[dict[str, Any]] = []
    rebuilt: list[str] = []
    unchanged: list[str] = []
    skipped: list[str] = []
    all_facts: list[dict[str, Any]] = []

    for ticker in sorted(raw_state):
        source_path = observations_root(runtime_root) / f"{ticker}{_SHARD_SUFFIX}"
        if not source_path.exists():
            continue
        if wanted is not None and ticker not in wanted:
            if ticker in previous:
                records.append(previous[ticker])
                skipped.append(ticker)
            continue

        source_sha = str(raw_state[ticker].get("shard_sha256") or "")
        built = build_ticker_facts(runtime_root, ticker, profiles=profiles,
                                   official_citations=official_citations)
        fingerprint = _inputs_fingerprint(source_sha, built["applicability"])
        path = shard_path(runtime_root, ticker)
        prior = previous.get(ticker)
        if (prior is not None and prior.get("inputs_fingerprint") == fingerprint
                and path.exists() and _sha_file(path) == prior.get("shard_sha256")):
            records.append(prior)
            unchanged.append(ticker)
            all_facts.extend(read_facts(runtime_root, ticker))
            continue

        shard_bytes = encode_shard(built["facts"])
        if execute:
            atomic_write_file(path, shard_bytes)
        records.append(_shard_record(ticker, built, shard_bytes, fingerprint, source_sha))
        rebuilt.append(ticker)
        all_facts.extend(built["facts"])

    records.sort(key=lambda record: record["ticker"])
    state = {
        "schema_version": STORE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "store_root": str(store_root(runtime_root)),
        "fact_schema_version": FACT_SCHEMA_VERSION,
        "mapper_version": MAPPER_VERSION,
        "resolver_version": RESOLVER_VERSION,
        "contract_version": CONTRACT_VERSION,
        "ticker_count": len(records),
        "fact_count": sum(int(record["fact_count"]) for record in records),
        "official_citation_count": len(official_citations),
        "tickers": records,
    }
    state["state_fingerprint"] = _fingerprint(
        {key: value for key, value in state.items() if key != "generated_at"})

    coverage = build_coverage(all_facts, records)
    unresolved = build_unresolved_queue(all_facts)
    conflicts = build_conflict_queue(all_facts)

    if execute:
        atomic_write_json(state_path(runtime_root), state)
        atomic_write_json(store_root(runtime_root) / COVERAGE_FILENAME, coverage)
        atomic_write_file(store_root(runtime_root) / COVERAGE_CSV_FILENAME,
                          _coverage_csv(coverage).encode("utf-8"))
        atomic_write_file(store_root(runtime_root) / UNRESOLVED_FILENAME,
                          fact_lines(unresolved).encode("utf-8"))
        atomic_write_file(store_root(runtime_root) / CONFLICT_FILENAME,
                          fact_lines(conflicts).encode("utf-8"))

    return {
        "executed": execute,
        "ok": True,
        "state": state,
        "coverage": coverage,
        "rebuilt": rebuilt,
        "unchanged": unchanged,
        "skipped": skipped,
        "counts": {
            "tickers": len(records),
            "rebuilt": len(rebuilt),
            "unchanged": len(unchanged),
            "skipped": len(skipped),
            "facts": state["fact_count"],
            "unresolved_metrics": len(unresolved),
            "conflicts": len(conflicts),
        },
    }


def _load_state(runtime_root: Path | str) -> dict[str, Any]:
    path = state_path(runtime_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, Mapping) or payload.get("schema_version") != STORE_SCHEMA_VERSION:
        return {}
    return dict(payload)


def _shard_record(ticker: str, built: Mapping[str, Any], shard_bytes: bytes,
                  fingerprint: str, source_sha256: str) -> dict[str, Any]:
    archetype = built["applicability"]["archetype"]
    return {
        "ticker": ticker.upper(),
        "shard": f"{ticker.upper()}{_SHARD_SUFFIX}",
        "shard_sha256": hashlib.sha256(shard_bytes).hexdigest(),
        "shard_bytes": len(shard_bytes),
        "inputs_fingerprint": fingerprint,
        "source_shard_sha256": source_sha256,
        "fact_count": len(built["facts"]),
        "status_counts": built["status_counts"],
        "reporting_periods": built["reporting_periods"],
        "payload_dialects": built["payload_dialects"],
        "cumulative_state": built["cumulative_state"]["cumulative_state"],
        "template_family": archetype.get("template_family"),
        "issuer_entity_type": archetype.get("issuer_entity_type"),
        "archetype_authority": archetype.get("authority"),
    }


def build_coverage(facts: Sequence[Mapping[str, Any]],
                   records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Deterministic market-wide coverage. Counts and reasons only -- never a score."""
    by_metric: dict[str, dict[str, Any]] = {}
    for metric in sorted(METRIC_REGISTRY):
        by_metric[metric] = {
            "canonical_metric": metric,
            "status_counts": {status: 0 for status in SUPPORTED_STATUSES},
            "tickers_with_any_usable_period": 0,
            "by_dialect": {},
        }
    usable = {STATUS_QUALIFIED, STATUS_PROVIDER_REPORTED, STATUS_PARTIAL}
    seen: dict[str, set[str]] = {metric: set() for metric in by_metric}

    for fact in facts:
        metric = str(fact["canonical_metric"])
        entry = by_metric.get(metric)
        if entry is None:
            continue
        status = str(fact["status"])
        entry["status_counts"][status] = entry["status_counts"].get(status, 0) + 1
        dialect = str(fact.get("dialect") or "none")
        dialect_entry = entry["by_dialect"].setdefault(
            dialect, {status: 0 for status in SUPPORTED_STATUSES})
        dialect_entry[status] = dialect_entry.get(status, 0) + 1
        if status in usable:
            seen[metric].add(str(fact["ticker"]))
    for metric, tickers in seen.items():
        by_metric[metric]["tickers_with_any_usable_period"] = len(tickers)

    by_entity: dict[str, int] = {}
    by_authority: dict[str, int] = {}
    by_cumulative: dict[str, int] = {}
    dialect_mix: dict[str, int] = {}
    for record in records:
        family = str(record.get("template_family") or record.get("issuer_entity_type") or "unresolved")
        by_entity[family] = by_entity.get(family, 0) + 1
        authority = str(record.get("archetype_authority") or "unknown")
        by_authority[authority] = by_authority.get(authority, 0) + 1
        basis = str(record.get("cumulative_state") or "unknown")
        by_cumulative[basis] = by_cumulative.get(basis, 0) + 1
        for family_name, dialect in sorted((record.get("payload_dialects") or {}).items()):
            key = f"{family_name}:{dialect}"
            dialect_mix[key] = dialect_mix.get(key, 0) + 1

    totals = {status: 0 for status in SUPPORTED_STATUSES}
    for entry in by_metric.values():
        for status, count in entry["status_counts"].items():
            totals[status] = totals.get(status, 0) + count

    return {
        "schema_version": STORE_SCHEMA_VERSION,
        "mapper_version": MAPPER_VERSION,
        "resolver_version": RESOLVER_VERSION,
        "contract_version": CONTRACT_VERSION,
        "ticker_count": len(records),
        "fact_count": len(facts),
        "status_totals": totals,
        "by_metric": [by_metric[metric] for metric in sorted(by_metric)],
        "by_entity_template": dict(sorted(by_entity.items())),
        "by_archetype_authority": dict(sorted(by_authority.items())),
        "by_cumulative_state": dict(sorted(by_cumulative.items())),
        "payload_dialect_mix": dict(sorted(dialect_mix.items())),
    }


def build_unresolved_queue(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One row per unresolved *metric*, never per ticker."""
    rows = [
        {
            "ticker": fact["ticker"],
            "canonical_metric": fact["canonical_metric"],
            "reporting_period": fact["reporting_period"],
            "status": fact["status"],
            "reason": fact["reason"],
            "warnings": fact["warnings"],
            "statement_family": fact["statement_family"],
            "dialect": fact.get("dialect"),
        }
        for fact in facts if str(fact["status"]) in UNRESOLVED_STATUSES
    ]
    rows.sort(key=lambda row: (row["ticker"], row["reporting_period"], row["canonical_metric"]))
    return rows


def build_conflict_queue(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every conflict, carrying both disagreeing values so review needs no re-derivation."""
    rows: list[dict[str, Any]] = []
    for fact in facts:
        for conflict in fact.get("conflicts") or []:
            rows.append({
                "ticker": fact["ticker"],
                "canonical_metric": fact["canonical_metric"],
                "reporting_period": fact["reporting_period"],
                "conflict_kind": conflict.get("kind"),
                "detail": {key: value for key, value in conflict.items() if key != "kind"},
                "source_observation_ids": fact.get("source_observation_ids") or [],
            })
    rows.sort(key=lambda row: (row["ticker"], row["reporting_period"],
                               row["canonical_metric"], str(row["conflict_kind"])))
    return rows


def _coverage_csv(coverage: Mapping[str, Any]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["canonical_metric", *SUPPORTED_STATUSES, "tickers_with_any_usable_period"])
    for entry in coverage["by_metric"]:
        writer.writerow([
            entry["canonical_metric"],
            *[entry["status_counts"].get(status, 0) for status in SUPPORTED_STATUSES],
            entry["tickers_with_any_usable_period"],
        ])
    return buffer.getvalue()


def verify(runtime_root: Path | str) -> dict[str, Any]:
    """Re-derive every shard in memory and compare against disk. Never writes."""
    runtime_root = Path(runtime_root)
    state = _load_state(runtime_root)
    if not state:
        return {"ok": False, "reason": "state_missing_or_unsupported_schema", "findings": []}
    profiles = load_entity_profiles(Path(__file__).with_name("config") / "ticker_entity_profiles.csv")
    official_citations = load_official_citations(runtime_root)
    findings: list[dict[str, Any]] = []
    checked = 0
    for record in state.get("tickers") or []:
        ticker = str(record["ticker"])
        path = shard_path(runtime_root, ticker)
        if not path.exists():
            findings.append({"ticker": ticker, "finding": "shard_missing"})
            continue
        actual = _sha_file(path)
        if actual != record.get("shard_sha256"):
            findings.append({"ticker": ticker, "finding": "shard_sha256_mismatch",
                             "recorded": record.get("shard_sha256"), "actual": actual})
            continue
        built = build_ticker_facts(runtime_root, ticker, profiles=profiles,
                                   official_citations=official_citations)
        if hashlib.sha256(encode_shard(built["facts"])).hexdigest() != actual:
            findings.append({"ticker": ticker, "finding": "not_byte_reproducible"})
            continue
        checked += 1
    return {"ok": not findings, "checked": checked, "findings": findings,
            "state_fingerprint": state.get("state_fingerprint")}
