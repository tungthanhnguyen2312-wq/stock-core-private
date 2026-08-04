"""Temporary SQLite/Pandas versus DuckDB/Parquet benchmark for qualified VCI price data only."""
from __future__ import annotations
import hashlib,json,sqlite3,statistics,tempfile,time,tracemalloc
from pathlib import Path
from typing import Any
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from provider_price_basis_registry import active_verdict
BASIS=active_verdict("VCI")["price_basis"]  # was a hard-coded "raw_as_quoted_no_adjustment_applied"; see provider_price_basis_registry
SCHEMA=pa.schema([("ticker",pa.string()),("date",pa.string()),("open",pa.float64()),("high",pa.float64()),("low",pa.float64()),("close",pa.float64()),("provider",pa.string()),("price_basis",pa.string())])
class BenchmarkError(RuntimeError):pass
def _hash(path:Path)->str:
 h=hashlib.sha256()
 with path.open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
 return h.hexdigest()
def _rows(frame:pd.DataFrame)->list[dict[str,Any]]:return json.loads(frame.to_json(orient="records",double_precision=15))
def export_vci_price(db:Path,target:Path)->dict[str,Any]:
 conn=sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro",uri=True)
 try:
  kbs_rows=conn.execute("SELECT COUNT(*) FROM ohlcv WHERE source='KBS'").fetchone()[0]
  frame=pd.read_sql_query("SELECT ticker,date,open,high,low,close,source FROM ohlcv WHERE source='VCI' ORDER BY ticker,date",conn)
 finally:conn.close()
 if frame.empty or set(frame["source"])!={"VCI"}:raise BenchmarkError("vci_filter_failed")
 frame=frame.rename(columns={"source":"provider"});frame["price_basis"]=BASIS;table=pa.Table.from_pandas(frame[[x.name for x in SCHEMA]],schema=SCHEMA,preserve_index=False,safe=True);pq.write_table(table,target,compression="zstd",use_dictionary=True)
 manifest={"schema_version":"1.0.0","source_database_hash":_hash(db),"provider":"VCI","price_basis":BASIS,"rows":len(frame),"kbs_rows_excluded":int(kbs_rows),"date_range":[str(frame.date.min()),str(frame.date.max())],"tickers":int(frame.ticker.nunique()),"nulls":{c:int(frame[c].isna().sum()) for c in ("open","high","low","close")},"parquet_hash":_hash(target),"parquet_size":target.stat().st_size,"schema":str(SCHEMA)};return manifest
def _sample(fn):
 tracemalloc.start();started=time.perf_counter_ns();rows=fn();elapsed=(time.perf_counter_ns()-started)/1e6;_,peak=tracemalloc.get_traced_memory();tracemalloc.stop();return {"rows":rows,"elapsed_ms":elapsed,"peak_python_bytes":peak}
def _equal(a,b):
 if len(a)!=len(b):return False,0.0
 diff=0.0
 for x,y in zip(a,b):
  if list(x)!=list(y):return False,diff
  for k in x:
   if x[k] is None or y[k] is None:
    if x[k] is not y[k]:return False,diff
   elif isinstance(x[k],float):diff=max(diff,abs(x[k]-float(y[k])));
   elif x[k]!=y[k]:return False,diff
 return diff<=1e-9,diff
def run_benchmark(db:Path,report_path:Path)->dict[str,Any]:
 try:import duckdb
 except ImportError as exc:raise BenchmarkError("duckdb_runtime_missing") from exc
 db=db.resolve();before=_hash(db)
 with tempfile.TemporaryDirectory(prefix="qualified-vci-price-") as d:
  parquet=Path(d)/"vci_price.parquet";manifest=export_vci_price(db,parquet);conn=sqlite3.connect(f"file:{db.as_posix()}?mode=ro",uri=True);duck=duckdb.connect(":memory:")
  try:
   latest=conn.execute("SELECT MAX(date) FROM ohlcv WHERE source='VCI'").fetchone()[0];path=parquet.as_posix().replace("'","''")
   sqls={"single_ticker_date_range":("SELECT ticker,date,open,high,low,close,source AS provider,'"+BASIS+"' AS price_basis FROM ohlcv WHERE source='VCI' AND ticker='VNM' AND date BETWEEN '2024-01-01' AND '2024-12-31' ORDER BY date",f"SELECT * FROM read_parquet('{path}') WHERE ticker='VNM' AND date BETWEEN '2024-01-01' AND '2024-12-31' ORDER BY date"),"multi_ticker_price_snapshot":(f"SELECT ticker,date,close,source AS provider,'{BASIS}' AS price_basis FROM ohlcv WHERE source='VCI' AND ticker IN ('HPG','VNM','VCB') AND date='{latest}' ORDER BY ticker",f"SELECT ticker,date,close,provider,price_basis FROM read_parquet('{path}') WHERE ticker IN ('HPG','VNM','VCB') AND date='{latest}' ORDER BY ticker"),"historical_price_scan":("SELECT ticker,date,close,source AS provider,'"+BASIS+"' AS price_basis FROM ohlcv WHERE source='VCI' AND date BETWEEN '2024-01-01' AND '2024-12-31' ORDER BY ticker,date",f"SELECT ticker,date,close,provider,price_basis FROM read_parquet('{path}') WHERE date BETWEEN '2024-01-01' AND '2024-12-31' ORDER BY ticker,date"),"ticker_benchmark_alignment":("SELECT a.date,a.close AS ticker_close,b.close AS benchmark_close FROM ohlcv a JOIN ohlcv b ON a.date=b.date WHERE a.source='VCI' AND b.source='VCI' AND a.ticker='VNM' AND b.ticker='VNINDEX' AND a.date BETWEEN '2024-01-01' AND '2024-12-31' ORDER BY a.date",f"SELECT a.date,a.close AS ticker_close,b.close AS benchmark_close FROM read_parquet('{path}') a JOIN read_parquet('{path}') b ON a.date=b.date WHERE a.ticker='VNM' AND b.ticker='VNINDEX' AND a.date BETWEEN '2024-01-01' AND '2024-12-31' ORDER BY a.date"),"price_aggregation":("SELECT ticker,COUNT(*) AS rows,AVG(close) AS avg_close,MAX(high) AS max_high FROM ohlcv WHERE source='VCI' GROUP BY ticker ORDER BY ticker",f"SELECT ticker,COUNT(*) AS rows,AVG(close) AS avg_close,MAX(high) AS max_high FROM read_parquet('{path}') GROUP BY ticker ORDER BY ticker")}
   results={}
   for name,(sql,dsql) in sqls.items():
    left=lambda:_rows(pd.read_sql_query(sql,conn));right=lambda:_rows(duck.execute(dsql).fetchdf());cold_l,cold_r=_sample(left),_sample(right);warm_l=[_sample(left) for _ in range(2)];warm_r=[_sample(right) for _ in range(2)];ok,diff=_equal(cold_l["rows"],cold_r["rows"])
    if not ok:raise BenchmarkError("semantic_parity_failed:"+name)
    results[name]={"rows":len(cold_l["rows"]),"semantic_parity":True,"max_abs_numeric_difference":diff,"sqlite_pandas":{"cold_ms":cold_l["elapsed_ms"],"warm_median_ms":statistics.median(x["elapsed_ms"] for x in warm_l),"peak_python_bytes":max(x["peak_python_bytes"] for x in warm_l)},"duckdb_parquet":{"cold_ms":cold_r["elapsed_ms"],"warm_median_ms":statistics.median(x["elapsed_ms"] for x in warm_r),"peak_python_bytes":max(x["peak_python_bytes"] for x in warm_r)}}
  finally:duck.close();conn.close()
 if _hash(db)!=before:raise BenchmarkError("authority_changed")
 wins=sum(v["duckdb_parquet"]["warm_median_ms"]<=v["sqlite_pandas"]["warm_median_ms"]*.8 for v in results.values());decision="HYBRID_SQLITE_DUCKDB_PARQUET" if wins>=3 else "KEEP_SQLITE_PANDAS";report={"status":"PASS","manifest":manifest,"workloads":results,"semantic_parity":True,"storage_decision_price_only":decision,"decision_threshold":"DuckDB warm median <=80% of SQLite/Pandas in at least 3 of 5 price-only workloads","duckdb_wins":wins,"volume_workload_status":"BLOCKED_UNQUALIFIED","production_unchanged":True}
 report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8");return report