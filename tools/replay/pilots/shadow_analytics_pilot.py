"""Phase 3A read-only Parquet/DuckDB shadow analytics pilot.

SQLite and append-only JSONL remain authoritative.  This module only copies their
selected HPG/VNM/VCB facts into a caller-supplied temporary lake and queries that
lake with DuckDB.  It has no authority-cutover or production-output path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


from evidence_registry import EvidenceRegistry
from financial_observations import canonical_records, store_path
from semantic_evidence_bridge import enrich_canonical_records, reconcile_metric_identities
from semantic_evidence_bridge import load_verified_share_basis

TICKERS = ("HPG", "VNM", "VCB")
ENTITY_TYPES = {"HPG": "corporate", "VNM": "corporate", "VCB": "bank"}
BANK_METRICS = frozenset({"loans_to_customers", "customer_deposits", "net_interest_income", "credit_loss_provisions", "total_assets", "shareholders_equity", "net_income"})
CORPORATE_METRICS = frozenset({"revenue", "gross_profit", "operating_profit", "net_income", "total_assets", "shareholders_equity", "total_debt", "operating_cash_flow", "capital_expenditure"})


class ShadowPilotError(RuntimeError):
    pass


def require_duckdb():
    try:
        import duckdb
    except ModuleNotFoundError as exc:
        raise ShadowPilotError("DuckDB is required in an isolated pilot environment") from exc
    return duckdb


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_fingerprint(rows: Iterable[dict[str, Any]]) -> str:
    """Stable content fingerprint; Parquet writer metadata is intentionally excluded."""
    normalized = [json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str) for row in rows]
    return hashlib.sha256("\n".join(sorted(normalized)).encode("utf-8")).hexdigest()


def require_isolated_lake(lake_root: Path, production_root: Path) -> Path:
    lake = lake_root.resolve()
    production = production_root.resolve()
    if lake == production or production in lake.parents or lake in production.parents:
        raise ShadowPilotError(f"lake root must be isolated from production runtime: {lake}")
    if lake.exists() and any(lake.iterdir()):
        raise ShadowPilotError(f"lake root must be new and empty: {lake}")
    return lake


def require_supported_metric(ticker: str, metric: str) -> None:
    entity = ENTITY_TYPES.get(ticker)
    allowed = BANK_METRICS if entity == "bank" else CORPORATE_METRICS if entity == "corporate" else frozenset()
    if metric not in allowed:
        raise ShadowPilotError(f"unsupported {entity or 'unknown'} metric for {ticker}: {metric}")
    if entity == "bank" and metric == "total_debt":
        raise ShadowPilotError("bank deposits must never be aliased to debt")


def _sqlite_ohlcv(db_path: Path, tickers: tuple[str, ...]) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        marks = ",".join("?" for _ in tickers)
        rows = connection.execute(
            f"SELECT ticker,date,open,high,low,close,volume,source FROM ohlcv WHERE ticker IN ({marks}) ORDER BY ticker,date",
            tickers,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def qualify_fy2024_scoped_records(records: list[dict[str, Any]], ticker: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select only bridge-verified FY2024 direct facts with explicit scope/lineage."""
    qualified, rejected = [], []
    for record in records:
        period = record.get("period_identity") or {}
        if period.get("period") != "2024" or period.get("period_type") != "annual":
            continue
        evidence, observations = record.get("evidence"), record.get("observation_ids")
        required = {
            "scope": record.get("statement_scope") in {"consolidated", "separate"},
            "currency": isinstance(record.get("currency"), str) and bool(record.get("currency")),
            "scale": record.get("unit_scale") is not None,
            "observation_identity": isinstance(observations, list) and len(observations) == 1 and bool(observations[0]),
            "citation_lineage": isinstance(evidence, dict) and bool(evidence.get("citation_id")) and bool(evidence.get("evidence_id")),
            "available": record.get("quality_state") == "available" and record.get("derivation_status") == "direct",
        }
        if not all(required.values()):
            rejected.append({"ticker": ticker, "metric": record.get("canonical_metric"), "reason": sorted(key for key, ok in required.items() if not ok)})
            continue
        if ticker == "VCB" and record.get("canonical_metric") not in {"customer_loans_net", "customer_deposits", "net_interest_income", "provision_for_credit_losses", "net_profit_attributable_to_parent", "total_assets", "total_equity"}:
            rejected.append({"ticker": ticker, "metric": record.get("canonical_metric"), "reason": ["bank_metric_not_in_bounded_allowlist"]})
            continue
        qualified.append({
            "ticker": ticker, "entity_type": ENTITY_TYPES[ticker],
            "canonical_metric": record.get("canonical_metric"), "value": record.get("value"),
            "period": "2024", "period_end": None, "statement_scope": record.get("statement_scope"),
            "currency": record.get("currency"), "unit_scale": record.get("unit_scale"),
            "source": record.get("source"), "observation_id": observations[0],
            "citation_id": evidence["citation_id"], "evidence_id": evidence["evidence_id"],
            "provenance_json": json.dumps({"source": record.get("source"), "source_field": record.get("source_field"), "source_statement": record.get("source_statement"), "observation_id": observations[0], "citation_id": evidence["citation_id"], "evidence_id": evidence["evidence_id"]}, sort_keys=True),
        })
    scopes_by_metric: dict[str, set[str]] = {}
    for item in qualified:
        scopes_by_metric.setdefault(item["canonical_metric"], set()).add(item["statement_scope"])
    conflicts = sorted(metric for metric, scopes in scopes_by_metric.items() if len(scopes) > 1)
    if conflicts:
        raise ShadowPilotError(f"conflicting FY2024 statement scopes for {ticker}: {conflicts}")
    return qualified, rejected


def _financial_records(runtime_root: Path, tickers: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    entities = {ticker: ENTITY_TYPES[ticker] for ticker in tickers}
    bridged = reconcile_metric_identities(enrich_canonical_records(canonical_records(store_path(runtime_root), entities), runtime_root))
    output, rejected = [], {}
    for ticker in tickers:
        selected, rejected_rows = qualify_fy2024_scoped_records(bridged.get(ticker, []), ticker)
        output.extend(selected); rejected[ticker] = rejected_rows
    return sorted(output, key=lambda r: (r["ticker"], r["canonical_metric"], r["period"], r["statement_scope"], r["source"], r["observation_id"])), rejected

def _evidence_records(runtime_root: Path, tickers: tuple[str, ...]) -> list[dict[str, Any]]:
    registry = EvidenceRegistry(runtime_root).load()
    bad = [issue for issue in registry.issues if issue.get("reason") in {"document_hash_mismatch", "dangling_evidence", "unsupported_metric_semantics", "bank_deposits_aliased_to_debt"}]
    if bad:
        raise ShadowPilotError(f"evidence registry integrity failed: {bad}")
    rows = []
    for fact in registry.facts:
        if fact.get("ticker") not in tickers or fact.get("kind") not in {"share_basis", "qualification", "derived"}:
            continue
        raw = fact.get("raw") or {}
        rows.append({"identity": fact["identity"], "ticker": fact.get("ticker"), "entity_type": ENTITY_TYPES[fact["ticker"]],
                     "period": fact.get("period"), "metric": fact.get("metric"), "source": fact.get("source"),
                     "qualification_status": fact.get("qualification_status"), "citation_id": fact.get("citation_id"),
                     "observation_id": fact.get("observation_id"), "document_hash": fact.get("document_hash"),
                     "evidence_id": fact.get("evidence_id"), "lineage_json": json.dumps(fact.get("lineage"), sort_keys=True),
                     "value": raw.get("value")})
    return sorted(rows, key=lambda r: r["identity"])


def _share_basis_rows(runtime_root: Path, tickers: tuple[str, ...]) -> list[dict[str, Any]]:
    verified = load_verified_share_basis(runtime_root)
    rows = []
    for (ticker, identity_type, period), entry in verified["by_identity"].items():
        if ticker in tickers:
            rows.append({"ticker": ticker, "entity_type": ENTITY_TYPES[ticker], "identity_type": identity_type,
                         "reporting_period": period, "value": entry["value"], "citation_id": entry["citation_id"],
                         "evidence_id": entry["evidence_id"], "qualification_version": entry["qualification_version"],
                         "verified_at": entry.get("verified_at")})
    return sorted(rows, key=lambda r: (r["ticker"], r["identity_type"], r["reporting_period"]))


PARQUET_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "ohlcv": (("ticker", "VARCHAR"), ("date", "VARCHAR"), ("open", "DOUBLE"), ("high", "DOUBLE"),
              ("low", "DOUBLE"), ("close", "DOUBLE"), ("volume", "BIGINT"), ("source", "VARCHAR")),
    "financial_metrics": (("ticker", "VARCHAR"), ("entity_type", "VARCHAR"), ("canonical_metric", "VARCHAR"),
                          ("value", "BIGINT"), ("period", "VARCHAR"), ("period_end", "VARCHAR"),
                          ("statement_scope", "VARCHAR"), ("currency", "VARCHAR"), ("unit_scale", "BIGINT"),
                          ("source", "VARCHAR"), ("observation_id", "VARCHAR"), ("citation_id", "VARCHAR"),
                          ("evidence_id", "VARCHAR"), ("provenance_json", "VARCHAR")),
    "evidence_identities": (("identity", "VARCHAR"), ("ticker", "VARCHAR"), ("entity_type", "VARCHAR"),
                            ("period", "VARCHAR"), ("metric", "VARCHAR"), ("source", "VARCHAR"),
                            ("qualification_status", "VARCHAR"), ("citation_id", "VARCHAR"),
                            ("observation_id", "VARCHAR"), ("document_hash", "VARCHAR"), ("evidence_id", "VARCHAR"),
                            ("lineage_json", "VARCHAR"), ("value", "BIGINT")),
    "share_basis": (("ticker", "VARCHAR"), ("entity_type", "VARCHAR"), ("identity_type", "VARCHAR"),
                    ("reporting_period", "VARCHAR"), ("value", "BIGINT"), ("citation_id", "VARCHAR"),
                    ("evidence_id", "VARCHAR"), ("qualification_version", "VARCHAR"), ("verified_at", "VARCHAR")),
}


def _validate_numeric_contract(dataset: str, rows: list[dict[str, Any]]) -> None:
    """Reject values that cannot be represented exactly by the declared source schema."""
    integer_columns = {"financial_metrics": {"value", "unit_scale"}, "evidence_identities": {"value"},
                       "share_basis": {"value"}}.get(dataset, set())
    price_columns = {"open", "high", "low", "close"} if dataset == "ohlcv" else set()
    for row in rows:
        for column in integer_columns:
            value = row.get(column)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ShadowPilotError(f"{dataset}.{column} requires an exact integer source value")
        if dataset == "ohlcv":
            volume = row.get("volume")
            if volume is not None and (isinstance(volume, bool) or not isinstance(volume, int)):
                raise ShadowPilotError("ohlcv.volume requires an exact integer source value")
        for column in price_columns:
            value = row.get(column)
            if value is not None and (not isinstance(value, float) or not math.isfinite(value)):
                raise ShadowPilotError(f"ohlcv.{column} requires a finite SQLite REAL value")


def _write_partitioned(con, rows: list[dict[str, Any]], root: Path, dataset: str) -> list[Path]:
    dataset_root = root / dataset
    dataset_root.mkdir(parents=True, exist_ok=False)
    if not rows:
        raise ShadowPilotError(f"{dataset} has no qualifying rows")
    schema = PARQUET_SCHEMAS.get(dataset)
    if schema is None:
        raise ShadowPilotError(f"no explicit Parquet schema for {dataset}")
    columns = tuple(name for name, _ in schema)
    expected, actual = set(columns), set().union(*(set(row) for row in rows))
    if actual != expected or any(set(row) != expected for row in rows):
        raise ShadowPilotError(f"{dataset} row shape does not match its explicit schema")
    _validate_numeric_contract(dataset, rows)
    con.execute("DROP TABLE IF EXISTS source_rows")
    con.execute("CREATE TABLE source_rows (" + ", ".join(f'{name} {kind}' for name, kind in schema) + ")")
    placeholders = ", ".join("?" for _ in columns)
    con.executemany(f"INSERT INTO source_rows VALUES ({placeholders})", [tuple(row[name] for name in columns) for row in rows])
    files = []
    for ticker in TICKERS:
        target = dataset_root / f"ticker={ticker}" / "data.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        safe_ticker = ticker.replace("'", "''")
        safe_target = target.as_posix().replace("'", "''")
        con.execute(f"COPY (SELECT * FROM source_rows WHERE ticker = '{safe_ticker}') TO '{safe_target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        if not target.exists():
            raise ShadowPilotError(f"Parquet partition missing: {target}")
        files.append(target)
    con.execute("DROP TABLE source_rows")
    return files


def _read_parquet(con, root: Path, dataset: str) -> list[dict[str, Any]]:
    cursor = con.execute(f"SELECT * FROM read_parquet('{(root / dataset / 'ticker=*' / 'data.parquet').as_posix()}') ORDER BY ticker")
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def _normalize(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{field: row.get(field) for field in fields} for row in rows]


def _assert_parity(name: str, authority: list[dict[str, Any]], shadow: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, Any]:
    left, right = _normalize(authority, fields), _normalize(shadow, fields)
    if semantic_fingerprint(left) != semantic_fingerprint(right):
        raise ShadowPilotError(f"{name} parity mismatch")
    return {"rows": len(left), "semantic_fingerprint": semantic_fingerprint(left), "fields": list(fields)}


def _queries(con, root: Path) -> dict[str, Any]:
    ohlcv_glob = (root / "ohlcv" / "ticker=*" / "data.parquet").as_posix()
    financial_glob = (root / "financial_metrics" / "ticker=*" / "data.parquet").as_posix()
    evidence_glob = (root / "evidence_identities" / "ticker=*" / "data.parquet").as_posix()
    shares_glob = (root / "share_basis" / "ticker=*" / "data.parquet").as_posix()
    latest = con.execute(f"""SELECT ticker, canonical_metric, value, period, period_end, statement_scope
        FROM read_parquet('{financial_glob}') QUALIFY row_number() OVER
        (PARTITION BY ticker, canonical_metric, statement_scope ORDER BY period DESC)=1 ORDER BY ticker, canonical_metric""").fetchdf().to_dict("records")
    price = con.execute(f"""SELECT ticker,date,close,source FROM read_parquet('{ohlcv_glob}')
        QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY date DESC)=1 ORDER BY ticker""").fetchdf().to_dict("records")
    join = con.execute(f"""WITH p AS (SELECT ticker,close FROM read_parquet('{ohlcv_glob}') QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY date DESC)=1),
        f AS (SELECT ticker, canonical_metric, value FROM read_parquet('{financial_glob}') WHERE canonical_metric IN ('total_assets','shareholders_equity','total_equity')),
        s AS (SELECT ticker,value AS shares FROM read_parquet('{shares_glob}') WHERE identity_type='period_end_shares_outstanding')
        SELECT p.ticker,p.close,max(CASE WHEN f.canonical_metric='total_assets' THEN f.value END) AS total_assets,
        max(CASE WHEN f.canonical_metric IN ('shareholders_equity','total_equity') THEN f.value END) AS equity,max(s.shares) AS period_end_shares
        FROM p LEFT JOIN f USING(ticker) LEFT JOIN s USING(ticker) GROUP BY p.ticker,p.close ORDER BY p.ticker""").fetchdf().to_dict("records")
    evidence = con.execute(f"SELECT ticker,period,metric,document_hash,citation_id,evidence_id,lineage_json FROM read_parquet('{evidence_glob}') ORDER BY ticker,identity").fetchdf().to_dict("records")
    return {"latest_financial_metrics": latest, "historical_price_lookup": price, "valuation_input_join": join, "evidence_traceback": evidence}


def run_pilot(*, runtime_root: Path, lake_root: Path, evidence_dir: Path) -> dict[str, Any]:
    runtime_root = runtime_root.resolve()
    lake_root = require_isolated_lake(lake_root, runtime_root)
    if evidence_dir.exists():
        unexpected = {path.name for path in evidence_dir.iterdir()} - {"01_preflight.json"}
        if unexpected:
            raise ShadowPilotError(f"evidence directory must be new or preflight-only: {evidence_dir}")
    if lake_root.exists() and any(lake_root.iterdir()):
        raise ShadowPilotError(f"lake root must be new and empty: {lake_root}")
    if not (runtime_root / "vn_stock.db").is_file():
        raise ShadowPilotError("production SQLite authority is missing")
    duckdb = require_duckdb()
    lake_root.mkdir(parents=True, exist_ok=True); evidence_dir.mkdir(parents=True, exist_ok=True)
    before = {name: sha256_file(runtime_root / name) for name in ("vn_stock.db", "financial_snapshot.parquet")}
    con = duckdb.connect(":memory:")
    try:
        ohlcv = _sqlite_ohlcv(runtime_root / "vn_stock.db", TICKERS)
        financial, scope_rejections = _financial_records(runtime_root, TICKERS)
        available_tickers = sorted({row["ticker"] for row in financial})
        if not ({"VCB"} <= set(available_tickers) and set(available_tickers) & {"HPG", "VNM"}):
            raise ShadowPilotError(f"FY2024 scope qualification insufficient: available={available_tickers}")
        evidence = _evidence_records(runtime_root, TICKERS)
        shares = _share_basis_rows(runtime_root, TICKERS)
        files = {"ohlcv": _write_partitioned(con, ohlcv, lake_root, "ohlcv"),
                 "financial_metrics": _write_partitioned(con, financial, lake_root, "financial_metrics"),
                 "evidence_identities": _write_partitioned(con, evidence, lake_root, "evidence_identities"),
                 "share_basis": _write_partitioned(con, shares, lake_root, "share_basis")}
        parity = {"ohlcv": _assert_parity("ohlcv", ohlcv, _read_parquet(con, lake_root, "ohlcv"), ("ticker","date","open","high","low","close","volume","source")),
                  "financial_metrics": _assert_parity("financial_metrics", financial, _read_parquet(con, lake_root, "financial_metrics"), ("ticker","entity_type","canonical_metric","value","period","period_end","statement_scope","currency","unit_scale","source","observation_id","citation_id","evidence_id","provenance_json")),
                  "evidence_identities": _assert_parity("evidence_identities", evidence, _read_parquet(con, lake_root, "evidence_identities"), ("identity","ticker","period","metric","source","qualification_status","citation_id","document_hash","evidence_id","lineage_json")),
                  "share_basis": _assert_parity("share_basis", shares, _read_parquet(con, lake_root, "share_basis"), ("ticker","identity_type","reporting_period","value","citation_id","evidence_id"))}
        report = {"status": "pass", "tickers": list(TICKERS), "lake_root": str(lake_root), "datasets": {name: [str(p) for p in paths] for name,paths in files.items()},
                  "parity": parity, "scope_qualification": {"available_tickers": available_tickers, "rejected": scope_rejections}, "determinism": {"mode": "semantic_content", "metadata_exceptions": ["Parquet writer metadata and physical byte layout are not asserted"], "fingerprints": {name: value["semantic_fingerprint"] for name,value in parity.items()}},
                  "queries": _queries(con, lake_root), "generated_at": datetime.now(timezone.utc).isoformat(),
                  "authority": "SQLite/JSONL read-only; no cutover"}
    finally:
        con.close()
    after = {name: sha256_file(runtime_root / name) for name in before}
    report["production_unchanged"] = before == after
    if not report["production_unchanged"]: raise ShadowPilotError("production authority changed during pilot")
    (evidence_dir / "PHASE_3A_REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str)+"\n",encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Run isolated Phase 3A Parquet/DuckDB shadow pilot")
    parser.add_argument("--runtime-root",required=True,type=Path)
    parser.add_argument("--lake-root",required=True,type=Path)
    parser.add_argument("--evidence-dir",required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        report=run_pilot(runtime_root=args.runtime_root,lake_root=args.lake_root,evidence_dir=args.evidence_dir)
    except ShadowPilotError as exc:
        print(json.dumps({"status":"blocked","reason":str(exc)})); return 2
    print(json.dumps({"status":report["status"],"evidence":str(args.evidence_dir)})); return 0

if __name__=="__main__": raise SystemExit(main())
