"""Read-only validation of the generated candlestick web snapshot against local OHLCV."""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from candlestick_patterns import resample_ohlcv


JSON_PATH = ROOT / "data" / "candlestick_patterns.json"
JS_PATH = ROOT / "data" / "candlestick_patterns.js"
SAMPLE_TICKERS = ("VCB", "SSI", "HPG", "GAS", "VHM", "PAN")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    js = JS_PATH.read_text(encoding="utf-8")
    prefix = "window.CANDLESTICK_PATTERNS = "
    assert js.startswith(prefix) and js.endswith(";\n")
    assert json.loads(js[len(prefix):-2]) == payload
    assert payload["timeframes"] == ["1D", "1W", "1M"]
    assert payload["summary"]["total_patterns"] == len(payload["patterns"])

    by_key = {}
    for row in payload["patterns"]:
        assert row["timeframe"] in {"1D", "1W", "1M"}
        assert row["status"] in {"completed", "forming"}
        assert row["bars_ago"] >= 0
        assert 0 <= row["confidence_score"] <= 100
        assert row["confidence_stars"] in {0, 1, 2, 3}
        assert row["detected_at"] <= payload["scan_date"]
        if row["timeframe"] == "1D":
            assert row["status"] == "completed"
        by_key[(row["ticker"], row["timeframe"], row["pattern_key"], row["detected_at"])] = row

    placeholders = ",".join("?" for _ in SAMPLE_TICKERS)
    connection = sqlite3.connect(ROOT / "vn_stock.db")
    ohlcv_rows = connection.execute(
        f"SELECT ticker,date,open,high,low,close,volume FROM ohlcv WHERE ticker IN ({placeholders}) ORDER BY ticker,date",
        SAMPLE_TICKERS,
    ).fetchall()
    connection.close()
    ohlcv = pd.DataFrame(ohlcv_rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])
    available = set(ohlcv["ticker"])

    print(json.dumps({
        "summary": payload["summary"],
        "json_bytes": JSON_PATH.stat().st_size,
        "js_bytes": JS_PATH.stat().st_size,
        "json_js_equal": True,
        "validated_rows": len(by_key),
        "sample_tickers_available": sorted(available),
    }, ensure_ascii=False))
    for ticker in SAMPLE_TICKERS:
        print(f"\n[{ticker}]")
        ticker_ohlcv = ohlcv[ohlcv["ticker"] == ticker]
        for timeframe in ("1D", "1W", "1M"):
            aggregated = resample_ohlcv(
                ticker_ohlcv, timeframe, datetime.fromisoformat(payload["generated_at"])
            ).set_index("date")
            recent = [row for row in payload["patterns"] if row["ticker"] == ticker and row["timeframe"] == timeframe]
            checked = []
            for row in recent[:3]:
                source = aggregated.loc[pd.Timestamp(row["detected_at"])]
                assert float(source["close"]) == float(row["close"])
                assert source["period_start"].strftime("%Y-%m-%d") == row["period_start"]
                assert source["period_end"].strftime("%Y-%m-%d") == row["period_end"]
                checked.append({
                    "pattern": row["pattern_key"], "date": row["detected_at"], "bars_ago": row["bars_ago"],
                    "status": row["status"], "confidence": row["confidence_score"],
                    "ohlcv": [float(source["open"]), float(source["high"]), float(source["low"]),
                              float(source["close"]), None if pd.isna(source["volume"]) else int(source["volume"])],
                })
            print(timeframe, json.dumps(checked, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
