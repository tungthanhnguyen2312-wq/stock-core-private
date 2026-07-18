import io
import json
import math
import os
import sys
import time
import sqlite3
import random
import argparse
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

try:
    import requests
except ImportError:  # Cho phép --export-web-only chạy bằng Python stdlib.
    requests = None
try:
    import pandas as pd
except ImportError:  # Cho phép --export-web-only chạy bằng Python stdlib.
    pd = None

# Console Windows mặc định cp1252 -> vỡ khi in tiếng Việt
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==========================================
# LỚP VĨ MÔ (MACRO) — chân kiềng số 4, KHÔNG đụng ohlcv/meta/metadata/news
# ==========================================
# Bảng `macro` (PK series+date) trong cùng vn_stock.db. Mỗi chuỗi 1 mã series, đơn vị
# ghi trong catalog SERIES bên dưới. Xuất macro_snapshot.csv để xem nhanh.
#
# NGUỒN (tất cả ĐÃ KIỂM CHỨNG sống 2026-07-09, đều KHÔNG cần API key):
# - FRED:  fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>  (CSV công khai, keyless)
# - Yahoo: query1.finance.yahoo.com/v8/finance/chart/<SYMBOL>   (unofficial -> CÓ THỂ GÃY,
#          nếu 429/thay đổi schema thì cân nhắc chuyển stooq.com)
# - World Bank API v2: chuỗi NĂM cho vĩ mô VN (CPI, GDP) — độ trễ ~6-12 tháng
# - vnstock explorer.misc: tỷ giá VCB + vàng SJC (chỉ có giá TỪNG NGÀY, không có lịch sử
#   -> chuỗi chỉ tích lũy từ ngày bắt đầu chạy đều)
#
# [BẪY PHẢI NHỚ]
# - Point-in-time / revision: FRED revise số cũ (nhất là CPI), World Bank cập nhật lại
#   cả chuỗi -> giá trị hôm nay tải về KHÁC giá trị đã công bố lần đầu. Backtest nghiêm túc
#   phải dùng vintage data (ALFRED), bảng này CHỈ để theo dõi bối cảnh LIVE.
# - Độ trễ công bố: CPI Mỹ ra giữa tháng sau; CPI/GDP VN từ World Bank trễ cả năm.
#   KHÔNG có API miễn phí máy đọc được cho CPI VN theo THÁNG (GSO chỉ ra thông cáo).
# - Lệch múi giờ: nến Mỹ ngày T khớp với phiên VN ngày T+1.

DB_PATH = "vn_stock.db"
OUT_SNAPSHOT = "macro_snapshot.csv"
WEB_JSON = os.path.join("data", "macro_snapshot.json")
WEB_JS = os.path.join("data", "macro_snapshot.js")
SCHEMA_VERSION = 1
REQUEST_DELAY = 1.0
MAX_RETRY = 3
BACKOFF_BASE = 5
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Catalog: series -> (nguồn, mã nguồn, tên hiển thị, đơn vị, tần suất)
# Đơn vị bắt đầu bằng '%' -> snapshot tính HIỆU SỐ (điểm %) thay vì % thay đổi
SERIES = {
    # --- Thế giới: chuỗi chính thống từ FRED ---
    "us_fedfunds": ("fred", "FEDFUNDS",   "Lãi suất Fed Funds",        "%/năm",      "tháng"),
    "us_10y":      ("fred", "DGS10",      "Lợi suất TPCP Mỹ 10 năm",   "%/năm",      "ngày"),
    "us_cpi":      ("fred", "CPIAUCSL",   "CPI Mỹ (index 82-84=100)",  "index",      "tháng"),
    "dxy":         ("fred", "DTWEXBGS",   "USD Index (broad)",         "index",      "ngày"),
    "wti":         ("fred", "DCOILWTICO", "Dầu WTI",                   "USD/thùng",  "ngày"),
    # --- Thế giới: chỉ số thị trường từ Yahoo (unofficial) ---
    "sp500":       ("yahoo", "^GSPC",     "S&P 500",                   "điểm",       "ngày"),
    "nasdaq":      ("yahoo", "^IXIC",     "Nasdaq Composite",          "điểm",       "ngày"),
    "vix":         ("yahoo", "^VIX",      "VIX",                       "điểm",       "ngày"),
    "nikkei":      ("yahoo", "^N225",     "Nikkei 225",                "điểm",       "ngày"),
    "hsi":         ("yahoo", "^HSI",      "Hang Seng",                 "điểm",       "ngày"),
    "gold_world":  ("yahoo", "GC=F",      "Vàng thế giới",             "USD/oz",     "ngày"),
    "brent":       ("yahoo", "BZ=F",      "Dầu Brent",                 "USD/thùng",  "ngày"),
    "usdvnd_mkt":  ("yahoo", "VND=X",     "USD/VND (quốc tế)",         "đồng/USD",   "ngày"),
    # --- Việt Nam: giá trong nước từ vnstock (chỉ có hôm nay) ---
    "usdvnd_vcb":  ("vcb",   "USD",       "USD/VND (VCB bán ra)",      "đồng/USD",   "ngày"),
    "gold_sjc":    ("sjc",   "SJC-HCM",   "Vàng SJC bán ra (HCM)",     "đồng/lượng", "ngày"),
    # --- Việt Nam: chuỗi NĂM từ World Bank (trễ nhưng chính thống) ---
    "vn_cpi_yoy":  ("wb",    "FP.CPI.TOTL.ZG",    "CPI VN (YoY)",       "%/năm",     "năm"),
    "vn_gdp_yoy":  ("wb",    "NY.GDP.MKTP.KD.ZG", "Tăng trưởng GDP VN", "%/năm",     "năm"),
}

CATEGORY_BY_SERIES = {
    "us_fedfunds": "rates", "us_10y": "rates",
    "us_cpi": "inflation_growth", "vn_cpi_yoy": "inflation_growth",
    "vn_gdp_yoy": "inflation_growth",
    "dxy": "currency", "usdvnd_mkt": "currency", "usdvnd_vcb": "currency",
    "wti": "commodities", "brent": "commodities",
    "gold_world": "commodities", "gold_sjc": "commodities",
    "vix": "risk", "sp500": "markets", "nasdaq": "markets",
    "nikkei": "markets", "hsi": "markets",
}

FREQUENCY_META = {
    "ngày": {"key": "daily", "label": "Hằng ngày", "stale_after_days": 7, "series_limit": 400},
    "tuần": {"key": "weekly", "label": "Hằng tuần", "stale_after_days": 14, "series_limit": 260},
    "tháng": {"key": "monthly", "label": "Hằng tháng", "stale_after_days": 62, "series_limit": 120},
    "quý": {"key": "quarterly", "label": "Hằng quý", "stale_after_days": 150, "series_limit": 80},
    "năm": {"key": "annual", "label": "Hằng năm", "stale_after_days": 550, "series_limit": 60},
}

SOURCE_LABELS = {
    "fred": "FRED",
    "yahoo": "Yahoo Finance",
    "wb": "World Bank",
    "vcb": "Vietcombank",
    "sjc": "SJC",
}

HISTORY_NOTES = {
    "usdvnd_vcb": "Lịch sử tích lũy từ khi pipeline bắt đầu chạy đều.",
    "gold_sjc": "Lịch sử tích lũy từ khi pipeline bắt đầu chạy đều.",
}

VN_TZ = timezone(timedelta(hours=7))

def init_db(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS macro(
        series TEXT, date TEXT, value REAL, PRIMARY KEY(series, date))""")
    conn.commit()

def http_get(url, params=None, label=""):
    """GET với retry/backoff cùng phong cách các file khác. Trả None nếu chịu thua."""
    for attempt in range(1, MAX_RETRY + 1):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=25)
            time.sleep(REQUEST_DELAY)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 502, 503, 504):
                raise ConnectionError(f"HTTP {r.status_code}")
            print(f"   [Lỗi Hệ Thống] {label}: HTTP {r.status_code}")
            return None
        except Exception as e:
            wait = BACKOFF_BASE * attempt + random.uniform(0, 2)
            print(f"   [Lỗi Mạng] {label}: {str(e)[:60]} - thử lại sau {wait:.1f}s ({attempt}/{MAX_RETRY})")
            time.sleep(wait)
    return None

def upsert(conn, series, pairs):
    """pairs = list (date 'YYYY-MM-DD', value float). Idempotent."""
    rows = [(series, d, float(v)) for d, v in pairs if pd.notna(v)]
    if not rows:
        return 0
    conn.executemany("""INSERT INTO macro VALUES(?,?,?)
        ON CONFLICT(series, date) DO UPDATE SET value=excluded.value""", rows)
    conn.commit()
    return len(rows)

# ==========================================
# FETCHERS THEO NGUỒN
# ==========================================
def fetch_fred(code):
    """fredgraph.csv trả TOÀN BỘ lịch sử (file nhỏ). FRED dùng '.' cho ngày thiếu số."""
    r = http_get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                 params={"id": code}, label=f"FRED {code}")
    if r is None:
        return []
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")  # '.' -> NaN
    df = df.dropna()
    return list(zip(df["date"].astype(str), df["value"]))

def fetch_yahoo(symbol, rng):
    """Nến ngày từ Yahoo chart API (unofficial). Ngày lấy theo UTC — với nến daily
    (timestamp = giờ mở cửa sàn) UTC-date khớp ngày giao dịch bản địa."""
    r = http_get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                 params={"range": rng, "interval": "1d"}, label=f"Yahoo {symbol}")
    if r is None:
        return []
    try:
        res = r.json()["chart"]["result"][0]
        ts = res["timestamp"]
        close = res["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        print(f"   [Lỗi Hệ Thống] Yahoo {symbol}: schema thay đổi")
        return []
    out = []
    for t, c in zip(ts, close):
        if c is not None:
            out.append((datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"), c))
    return out

def fetch_wb(code):
    """World Bank v2, chuỗi năm. date='2025' -> lưu thành '2025-12-31' cho dễ sort."""
    r = http_get(f"https://api.worldbank.org/v2/country/VN/indicator/{code}",
                 params={"format": "json", "per_page": 100}, label=f"WB {code}")
    if r is None:
        return []
    j = r.json()
    if len(j) < 2 or not j[1]:
        return []
    # WB trả MỚI -> CŨ; sort lại tăng dần để pairs[-1] đúng là điểm mới nhất
    return sorted((f"{d['date']}-12-31", d["value"]) for d in j[1] if d["value"] is not None)

def fetch_vcb_today():
    """Tỷ giá VCB bán ra hôm nay (vnstock). Giá dạng chuỗi '26,471.00' -> float."""
    from vnstock.explorer.misc.exchange_rate import vcb_exchange_rate
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        df = vcb_exchange_rate(date=today)
        time.sleep(REQUEST_DELAY)
        usd = df[df["currency_code"].astype(str).str.upper() == "USD"]
        if usd.empty:
            return []
        sell = float(str(usd["sell"].iloc[0]).replace(",", ""))
        return [(today, sell)]
    except Exception as e:
        print(f"   [Lỗi Hệ Thống] VCB: {str(e)[:60]}")
        return []

def fetch_sjc_today():
    """Giá vàng SJC bán ra (chi nhánh HCM) hôm nay, đồng/lượng."""
    from vnstock.explorer.misc.gold_price import sjc_gold_price
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        df = sjc_gold_price()
        time.sleep(REQUEST_DELAY)
        row = df[df["branch"].astype(str).str.contains("Hồ Chí Minh", na=False)]
        if row.empty:
            row = df.head(1)
        return [(today, float(row["sell_price"].iloc[0]))]
    except Exception as e:
        print(f"   [Lỗi Hệ Thống] SJC: {str(e)[:60]}")
        return []

# ==========================================
# SNAPSHOT: giá trị mới nhất + biến động mỗi chuỗi
# ==========================================
def make_snapshot(conn, generated_at=None):
    """Đơn vị '%...' -> chg = HIỆU SỐ (điểm %); còn lại -> chg = % thay đổi.
    chg_1m/chg_1y lấy giá trị GẦN NHẤT TRƯỚC mốc lùi (phòng chuỗi thưa/nghỉ lễ).

    item H (Data Contract Hardening v1.1): mỗi series còn mang freshness RIÊNG (expected_
    frequency/age_days/freshness_status/as_of/freshness_reason) — tái sử dụng nguyên
    freshness_for() (trước đây chỉ phục vụ build_web_snapshot()/data/macro_snapshot.json,
    KHÔNG tới macro_snapshot.csv — nguồn analysis_bundle.json.macro_snapshot thực sự đọc), không
    viết logic mới. Không đánh đồng freshness của cả file với freshness của từng chuỗi: mỗi
    series giữ `date` (ngày quan sát riêng, đã có từ trước) tách biệt với `as_of` (thời điểm
    pipeline này chạy, dùng để tính age_days)."""
    generated_at = generated_at or datetime.now(VN_TZ)
    as_of_iso = generated_at.isoformat(timespec="seconds")
    rows = []
    for series, (src, code, name, unit, freq) in SERIES.items():
        df = pd.read_sql("SELECT date, value FROM macro WHERE series=? ORDER BY date",
                         conn, params=(series,))
        if df.empty:
            continue
        last = df.iloc[-1]
        d_last = pd.to_datetime(last["date"])

        def chg(days):
            cutoff = (d_last - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
            prev = df[df["date"] <= cutoff]
            if prev.empty:
                return None
            pv = prev["value"].iloc[-1]
            if unit.startswith("%"):
                return round(last["value"] - pv, 2)          # điểm %
            return round((last["value"] / pv - 1) * 100, 2) if pv else None  # % thay đổi

        prev_v = df["value"].iloc[-2] if len(df) > 1 else None
        if unit.startswith("%"):
            chg_prev = round(last["value"] - prev_v, 2) if prev_v is not None else None
        else:
            chg_prev = round((last["value"] / prev_v - 1) * 100, 2) if prev_v else None

        freshness = freshness_for(last["date"], freq, generated_at)
        freq_meta = FREQUENCY_META.get(freq)
        expected_frequency = freq_meta["key"] if freq_meta else freq
        freshness_reason = None
        if freshness["status"] == "stale":
            freshness_reason = f"age_days_exceeds_stale_after_days_for_{expected_frequency}"
        elif freshness["status"] == "unknown":
            freshness_reason = "unparseable_period_date" if freq_meta else "unrecognized_frequency_label"

        rows.append({"series": series, "name": name, "unit": unit, "freq": freq,
                     "date": last["date"], "value": last["value"],
                     "chg_prev": chg_prev, "chg_1m": chg(30), "chg_1y": chg(365),
                     "expected_frequency": expected_frequency,
                     "age_days": freshness["age_days"],
                     "freshness_status": freshness["status"],
                     "as_of": as_of_iso,
                     "freshness_reason": freshness_reason})
    return pd.DataFrame(rows)


def source_url(source, code):
    """Trả link trích dẫn công khai; không đưa endpoint tải dữ liệu vào frontend."""
    if source == "fred":
        return f"https://fred.stlouisfed.org/series/{quote(code)}"
    if source == "yahoo":
        return f"https://finance.yahoo.com/quote/{quote(code, safe='=')}"
    if source == "wb":
        return f"https://data.worldbank.org/indicator/{quote(code)}?locations=VN"
    if source == "vcb":
        return "https://www.vietcombank.com.vn/vi-VN/KHCN/Cong-cu-tien-ich/Ty-gia"
    if source == "sjc":
        return "https://sjc.com.vn/"
    return None


def finite_or_none(value):
    """Chuẩn hóa scalar DB/pandas để JSON không bao giờ chứa NaN/Infinity."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def freshness_for(period, frequency, generated_at):
    meta = FREQUENCY_META.get(frequency)
    if not meta:
        return {"status": "unknown", "age_days": None, "stale_after_days": None}
    try:
        period_date = datetime.strptime(period, "%Y-%m-%d").date()
        age_days = max(0, (generated_at.date() - period_date).days)
    except (TypeError, ValueError):
        return {"status": "unknown", "age_days": None,
                "stale_after_days": meta["stale_after_days"]}
    return {
        "status": "stale" if age_days > meta["stale_after_days"] else "current",
        "age_days": age_days,
        "stale_after_days": meta["stale_after_days"],
    }


def build_web_snapshot(conn, generated_at=None, pipeline_completed_at=None):
    """Tạo object public tối thiểu từ catalog + bảng macro thật trong SQLite."""
    generated_at = generated_at or datetime.now(VN_TZ)
    pipeline_completed_at = pipeline_completed_at or generated_at
    pipeline_completed_iso = pipeline_completed_at.isoformat(timespec="seconds")
    indicators = []
    web_series = {}
    all_periods = []

    for key, (source, code, label, unit, frequency) in SERIES.items():
        freq_meta = FREQUENCY_META.get(frequency, {
            "key": "unknown", "label": frequency, "stale_after_days": None,
            "series_limit": 120,
        })
        rows = conn.execute(
            "SELECT date, value FROM macro WHERE series=? ORDER BY date DESC LIMIT ?",
            (key, freq_meta["series_limit"]),
        ).fetchall()
        rows.reverse()
        points = [
            {"date": str(date), "value": finite_or_none(value)}
            for date, value in rows if finite_or_none(value) is not None
        ]
        web_series[key] = points

        latest = points[-1] if points else None
        previous = points[-2] if len(points) > 1 else None
        value = latest["value"] if latest else None
        previous_value = previous["value"] if previous else None
        change = None
        change_pct = None
        if value is not None and previous_value is not None:
            change = value - previous_value
            if previous_value != 0:
                change_pct = change / previous_value * 100
        period = latest["date"] if latest else None
        if period:
            all_periods.append(period)

        if change is None:
            direction = "unknown"
        elif change > 0:
            direction = "up"
        elif change < 0:
            direction = "down"
        else:
            direction = "flat"

        indicators.append({
            "key": key,
            "label": label,
            "category": CATEGORY_BY_SERIES.get(key, "other"),
            "value": value,
            "previous_value": previous_value,
            "change": finite_or_none(change),
            "change_pct": finite_or_none(change_pct),
            "change_basis": "percentage_point" if unit.startswith("%") else "percent",
            "direction": direction,
            "interpretation": "unknown",
            "unit": unit,
            "period": period,
            "frequency": freq_meta["key"],
            "frequency_label": freq_meta["label"],
            "source": SOURCE_LABELS.get(source, source),
            "source_url": source_url(source, code),
            "pipeline_updated_at": pipeline_completed_iso,
            "status": "available" if value is not None else "unavailable",
            "freshness": freshness_for(period, frequency, generated_at),
            "history_points": len(points),
            "history_scope": HISTORY_NOTES.get(key),
        })

    available = sum(item["status"] == "available" for item in indicators)
    stale = sum(item["freshness"]["status"] == "stale" for item in indicators)
    generated_iso = generated_at.isoformat(timespec="seconds")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_iso,
        "pipeline_completed_at": pipeline_completed_iso,
        "published_at": None,
        "data_as_of": max(all_periods) if all_periods else None,
        "source_type": "local_pipeline",
        "update_policy": "updated_on_publish",
        "quality": {
            "catalog_count": len(SERIES),
            "available_count": available,
            "missing_count": len(SERIES) - available,
            "stale_count": stale,
            "is_partial": available < len(SERIES),
        },
        "indicators": indicators,
        "series": web_series,
        "foreign_flow": {
            "status": "unavailable",
            "reason": "Chưa có dữ liệu giao dịch khối ngoại trong snapshot.",
            "date": None,
            "net_value_billion": None,
            "buy_value_billion": None,
            "sell_value_billion": None,
            "cumulative_5d_billion": None,
            "cumulative_20d_billion": None,
            "source": None,
            "source_url": None,
            "reference_links": [
                {"label": "Sở GDCK TP.HCM (HOSE)", "url": "https://www.hsx.vn/"},
                {"label": "Thống kê Sở GDCK Hà Nội (HNX)",
                 "url": "https://hnx.vn/vi-vn/phai-sinh/thong-ke.html"},
            ],
        },
    }


def atomic_write_text(path, content):
    """Ghi cùng thư mục rồi replace nguyên tử để không để lại artifact dở dang."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="\n", delete=False,
                dir=target.parent, prefix=f".{target.name}.", suffix=".tmp") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
            temp_name = fh.name
        os.replace(temp_name, target)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def export_web_snapshot(conn, json_path=WEB_JSON, js_path=WEB_JS, generated_at=None):
    generated_at = generated_at or datetime.now(VN_TZ)
    pipeline_completed_at = generated_at
    if os.path.exists(OUT_SNAPSHOT):
        pipeline_completed_at = datetime.fromtimestamp(os.path.getmtime(OUT_SNAPSHOT), VN_TZ)
    snapshot = build_web_snapshot(
        conn, generated_at=generated_at, pipeline_completed_at=pipeline_completed_at)
    payload = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, indent=2)
    atomic_write_text(json_path, payload + "\n")
    atomic_write_text(js_path, "window.MACRO_SNAPSHOT = " + payload + ";\n")
    return snapshot

def main():
    ap = argparse.ArgumentParser(description="Đồng bộ dữ liệu vĩ mô thế giới + VN vào bảng `macro` của vn_stock.db")
    ap.add_argument("--full", action="store_true", help="Yahoo lấy 10 năm thay vì 1 năm (lần đầu nên chạy --full)")
    ap.add_argument("--export-web-only", action="store_true",
                    help="chỉ sinh JSON/JS từ DB local, không tải dữ liệu nguồn")
    args = ap.parse_args()
    rng = "10y" if args.full else "1y"

    if not args.export_web_only and (requests is None or pd is None):
        ap.error("chế độ đồng bộ cần requests + pandas; cài requirements.txt hoặc dùng --export-web-only")

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    print(f"[macro_sync] {len(SERIES)} chuỗi | Yahoo range={rng}")

    if not args.export_web_only:
        for series, (src, code, name, unit, freq) in SERIES.items():
            if src == "fred":
                pairs = fetch_fred(code)
            elif src == "yahoo":
                pairs = fetch_yahoo(code, rng)
            elif src == "wb":
                pairs = fetch_wb(code)
            elif src == "vcb":
                pairs = fetch_vcb_today()
            elif src == "sjc":
                pairs = fetch_sjc_today()
            else:
                continue
            n = upsert(conn, series, pairs)
            last = pairs[-1] if pairs else ("-", "-")
            print(f"  {series:<12} +{n:>5} điểm | mới nhất: {last[0]} = {last[1]}")

    # item H: one shared generated_at so the CSV (macro_snapshot.csv) and the web JSON report
    # freshness as-of the same instant, instead of two calls each defaulting independently.
    generated_at = datetime.now(VN_TZ)
    if not args.export_web_only:
        snap = make_snapshot(conn, generated_at=generated_at)
        snap.to_csv(OUT_SNAPSHOT, index=False, encoding="utf-8-sig")
    web = export_web_snapshot(conn, generated_at=generated_at)
    total = conn.execute("SELECT COUNT(*) FROM macro").fetchone()[0]
    conn.close()
    if args.export_web_only:
        print(f"\n[macro_sync] Kho macro: {total:,} điểm dữ liệu | không tải nguồn, không ghi lại CSV")
    else:
        print(f"\n[macro_sync] Kho macro: {total:,} điểm dữ liệu | snapshot -> {OUT_SNAPSHOT}")
    print(f"[macro_sync] Web snapshot: {web['quality']['available_count']}/{web['quality']['catalog_count']} chuỗi | {WEB_JSON} + {WEB_JS}")

if __name__ == "__main__":
    main()
