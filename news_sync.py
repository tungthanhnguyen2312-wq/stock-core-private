import re
import sys
import html
import time
import sqlite3
import random
import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
import requests
import pandas as pd

# Console Windows mặc định cp1252 -> vỡ khi in tiêu đề tiếng Việt
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==========================================
# LỚP TIN TỨC TÀI CHÍNH (thế giới + Việt Nam) — chân kiềng số 5
# ==========================================
# Bảng `news` (PK link -> tự chống trùng, chạy bao nhiêu lần/ngày cũng được).
# Parse RSS bằng xml.etree stdlib — KHÔNG thêm dependency.
#
# [BẪY PHẢI NHỚ]
# - RSS chỉ có tin TỪ BÂY GIỜ trở đi (mỗi feed giữ 10-60 tin gần nhất). KHÔNG có lịch sử:
#   muốn kho tin dày phải chạy đều (cron/Task Scheduler vài lần mỗi ngày).
# - Point-in-time: tin tức là dữ liệu thời điểm. Kho này CHỈ để đọc bối cảnh LIVE,
#   không đủ (và không sạch) để backtest tín hiệu tin tức quá khứ.
# - pubDate mỗi báo một múi giờ -> đã chuẩn hóa về UTC (cột published_utc).
#   Giờ VN = UTC + 7.
# - description của CafeF/VnExpress chứa HTML/ảnh -> đã strip tag, cắt 500 ký tự.
#
# Feed nào chết (đổi URL/dẹp RSS) sẽ chỉ in cảnh báo, không làm gãy cả phiên chạy.
# Toàn bộ feed dưới đây ĐÃ KIỂM CHỨNG sống ngày 2026-07-09.

DB_PATH = "vn_stock.db"
OUT_LATEST = "news_latest.csv"
REQUEST_DELAY = 1.0
MAX_RETRY = 3
BACKOFF_BASE = 5
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
SUMMARY_MAX = 500

FEEDS = [
    # (region, tên nguồn, url)
    ("world", "CNBC TopNews",  "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("world", "CNBC Finance",  "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
    ("world", "BBC Business",  "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("world", "MarketWatch",   "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("vn",    "VnExpress KD",  "https://vnexpress.net/rss/kinh-doanh.rss"),
    ("vn",    "CafeF CK",      "https://cafef.vn/thi-truong-chung-khoan.rss"),
    ("vn",    "VnEconomy CK",  "https://vneconomy.vn/chung-khoan.rss"),
    ("vn",    "Vietstock CK",  "https://vietstock.vn/145/chung-khoan.rss"),
]

def init_db(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS news(
        link TEXT PRIMARY KEY,
        region TEXT,            -- world | vn
        source TEXT,            -- tên feed
        title TEXT,
        summary TEXT,           -- đã strip HTML, cắt ngắn
        published_utc TEXT,     -- ISO UTC (giờ VN = +7)
        fetched TEXT)           -- thời điểm cào (giờ máy)
        """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_pub ON news(published_utc)")
    conn.commit()

def clean_text(s):
    """Strip HTML tag + entity + gộp khoảng trắng, cắt SUMMARY_MAX ký tự."""
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:SUMMARY_MAX]

def parse_pubdate(s):
    """pubDate RFC822 đủ kiểu múi giờ -> ISO UTC. Hỏng thì trả None (dùng giờ cào)."""
    try:
        return parsedate_to_datetime(s).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None

def fetch_feed(url, label):
    """GET với retry/backoff cùng phong cách các file khác. Trả None nếu chịu thua."""
    for attempt in range(1, MAX_RETRY + 1):
        try:
            r = requests.get(url, headers=UA, timeout=20)
            time.sleep(REQUEST_DELAY)
            if r.status_code == 200:
                return ET.fromstring(r.content)
            raise ConnectionError(f"HTTP {r.status_code}")
        except ET.ParseError as e:
            print(f"   [Lỗi Hệ Thống] {label}: XML hỏng ({str(e)[:50]})")
            return None
        except Exception as e:
            wait = BACKOFF_BASE * attempt + random.uniform(0, 2)
            print(f"   [Lỗi Mạng] {label}: {str(e)[:60]} - thử lại sau {wait:.1f}s ({attempt}/{MAX_RETRY})")
            time.sleep(wait)
    return None

def sync_feed(conn, region, source, url):
    root = fetch_feed(url, source)
    if root is None:
        return 0, 0
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fetched = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    for item in root.findall(".//item"):
        link = (item.findtext("link") or "").strip()
        title = clean_text(item.findtext("title"))
        if not link or not title:
            continue
        rows.append((link, region, source, title,
                     clean_text(item.findtext("description")),
                     parse_pubdate(item.findtext("pubDate")) or now_utc,
                     fetched))
    if not rows:
        return 0, 0
    before = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    conn.executemany("INSERT OR IGNORE INTO news VALUES(?,?,?,?,?,?,?)", rows)
    conn.commit()
    added = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0] - before
    return len(rows), added

def main():
    ap = argparse.ArgumentParser(description="Cào RSS tài chính thế giới + VN vào bảng `news` của vn_stock.db")
    ap.add_argument("--export", type=int, default=100, help="số tin mới nhất xuất ra news_latest.csv (mặc định 100)")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    print(f"[news_sync] Quét {len(FEEDS)} feed RSS")

    total_new = 0
    for region, source, url in FEEDS:
        n, added = sync_feed(conn, region, source, url)
        total_new += added
        print(f"  [{region:<5}] {source:<14} {n:>3} tin, {added:>3} mới")

    total = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    latest = pd.read_sql(
        "SELECT published_utc, region, source, title, link FROM news "
        "ORDER BY published_utc DESC LIMIT ?", conn, params=(args.export,))
    latest.to_csv(OUT_LATEST, index=False, encoding="utf-8-sig")
    conn.close()
    print(f"\n[news_sync] +{total_new} tin mới | kho: {total:,} tin | {args.export} tin mới nhất -> {OUT_LATEST}")

if __name__ == "__main__":
    main()
