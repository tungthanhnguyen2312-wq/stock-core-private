import os
import sys
import json
import sqlite3
import argparse
from datetime import datetime
import pandas as pd

from runtime_paths import runtime_root
from vn_time import vn_now

# Console Windows mặc định cp1252 -> vỡ khi in tiếng Việt
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==========================================
# AI ANALYZER — chân kiềng số 6: trộn dữ liệu -> gọi LLM -> báo cáo chiến lược cuối ngày
# ==========================================
# NGUYÊN TẮC PHÂN CÔNG (đừng bắt LLM làm toán):
# - PYTHON làm mọi phép tính TẤT ĐỊNH: chỉ báo, RS rating, swing SMC, lọc top N, breadth
#   (tất cả đã nằm trong vn_indicators.py/meta_sync.py — file này CHỈ chưng cất + đóng gói).
# - LLM làm phần XÁC SUẤT: đọc hiểu tin tức, liên kết macro với ngành, nhận định regime,
#   viết kế hoạch. LLM chỉ được TRÍCH số đã cho, không được sinh số mới.
# - Python VALIDATE ngược output: mã nào LLM nhắc mà không nằm trong dữ liệu gửi đi -> ảo giác.
#
# CHỐNG QUÁ TẢI TOKEN: không bao giờ gửi dữ liệu thô (ohlcv 1,9tr dòng, snapshot 1.578 dòng).
# Payload = top N mã đã lọc + breadth + macro + tiêu đề tin ≈ 6-9K token (<1% context 1M).
#
# MODEL: claude-sonnet-5 ("Claude 3.5 Sonnet" trong kế hoạch cũ ĐÃ BỊ KHAI TỬ 10/2025).
# Giá Sonnet 5: $3/1M token vào, $15/1M ra (khuyến mãi $2/$10 đến 31/08/2026)
# -> 1 báo cáo/ngày ≈ $0.05-0.08. KHÔNG gửi temperature (Sonnet 5 từ chối 400).
#
# CHẠY: python ai_analyzer.py --dry-run   # xem payload, không tốn tiền
#       python ai_analyzer.py             # gọi API thật (cần ANTHROPIC_API_KEY)

def resolve_runtime_paths(cwd=None):
    """Return mutable ai_analyzer paths under the configured runtime root."""
    root = runtime_root(cwd or os.getcwd())
    return (root, root / "vn_stock.db", root / "screen_snapshot.csv",
            root / "market_breadth.csv", root / "macro_snapshot.csv",
            root / "news_latest.csv")


(RUNTIME_ROOT, DB_PATH, SCREEN_SNAPSHOT_PATH, MARKET_BREADTH_PATH,
 MACRO_SNAPSHOT_PATH, NEWS_LATEST_PATH) = resolve_runtime_paths()
MODEL = "claude-sonnet-5"
TOP_N = 10
NEWS_PER_REGION = 20

SYSTEM_PROMPT = """Bạn là chiến lược gia đầu tư chứng khoán Việt Nam, phong cách kết hợp \
CANSLIM (xu hướng + sức mạnh tương đối + thanh khoản) và SMC (cấu trúc swing, vùng hỗ trợ). \
Người đọc là 1 nhà đầu tư cá nhân tự quản lý danh mục.

LUẬT SẮT:
1. CHỈ dùng số liệu trong dữ liệu được cung cấp. Cấm bịa số, cấm dùng kiến thức giá cả cũ trong đầu.
2. Không khuyến nghị mã nào ngoài danh sách được cung cấp.
3. Dữ liệu nào thiếu thì nói thẳng là thiếu, không đoán.
4. Nhận định phải kèm lý do trích từ dữ liệu (con số cụ thể).
5. Đây là phân tích tham khảo cá nhân, không phải khuyến nghị đầu tư công khai."""

# JSON Schema cho structured outputs — server ÉP output đúng schema này 100%
# (không hỗ trợ min/max nên mức độ dùng enum; mọi object phải có additionalProperties:false)
REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "market_regime": {"type": "string", "enum": ["risk_on", "neutral", "risk_off"]},
        "regime_reason": {"type": "string", "description": "2-3 câu, trích số liệu breadth + macro"},
        "macro_summary": {"type": "string", "description": "Tóm tắt vĩ mô thế giới + VN liên quan tới TTCK VN"},
        "news_themes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "theme": {"type": "string"},
                    "impact_vn": {"type": "string", "enum": ["positive", "negative", "mixed", "neutral"]},
                    "note": {"type": "string"}
                },
                "required": ["theme", "impact_vn", "note"],
                "additionalProperties": False
            }
        },
        "sector_view": {"type": "string", "description": "Ngành mạnh/yếu theo bảng breadth, kèm số"},
        "stock_notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "stance": {"type": "string", "enum": ["mua_tham_do", "cho_setup", "theo_doi", "tranh"]},
                    "entry_logic": {"type": "string", "description": "Logic vào lệnh theo CANSLIM/SMC, trích số"},
                    "risk_flags": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["ticker", "stance", "entry_logic", "risk_flags"],
                "additionalProperties": False
            }
        },
        "portfolio_risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "action_plan": {"type": "array", "items": {"type": "string"}, "description": "3-5 việc cụ thể cho phiên mai"}
    },
    "required": ["market_regime", "regime_reason", "macro_summary", "news_themes",
                 "sector_view", "stock_notes", "portfolio_risk", "action_plan"],
    "additionalProperties": False
}

# ==========================================
# CHƯNG CẤT DỮ LIỆU (toàn bộ phần tất định)
# ==========================================
def load_top_stocks(n):
    """Python chọn top N, KHÔNG để LLM chọn từ 1.578 mã: margin sạch + thanh khoản >=3 tỷ
    -> sort RS giảm dần. Trả về (df_top, set toàn bộ ticker gửi đi để validate ảo giác)."""
    s = pd.read_csv(SCREEN_SNAPSHOT_PATH)
    clean = s[s["margin_status"].isna() & (s["gtgd20_ty"] >= 3)]
    top = clean.sort_values("rs_rating", ascending=False).head(n)
    cols = ["ticker", "exchange", "industry", "close", "chg_today_pct", "rs_rating", "rsi14",
            "macd_hist", "rel_vol", "gtgd20_ty", "pct_from_52w_high", "structure",
            "dist_swing_low_pct", "pe", "pb", "roe", "foreign_room_pct", "free_float_est"]
    return top[[c for c in cols if c in top.columns]].round(2)

def load_vnindex(conn):
    """3 con số bối cảnh VNINDEX từ chính DB (Python tính, không nhờ LLM)."""
    df = pd.read_sql("SELECT date, close FROM ohlcv WHERE ticker='VNINDEX' ORDER BY date DESC LIMIT 22", conn)
    if len(df) < 22:
        return "VNINDEX: thiếu dữ liệu"
    last, prev, m1 = df["close"].iloc[0], df["close"].iloc[1], df["close"].iloc[21]
    return (f"VNINDEX {df['date'].iloc[0]}: {last:,.1f} điểm | "
            f"phiên: {(last / prev - 1) * 100:+.2f}% | 1 tháng: {(last / m1 - 1) * 100:+.2f}%")

def load_news(per_region):
    """Chỉ lấy TIÊU ĐỀ (summary tốn token mà nhiễu), mới nhất mỗi khu vực."""
    news = pd.read_csv(NEWS_LATEST_PATH)
    parts = []
    for region in ("world", "vn"):
        sub = news[news["region"] == region].head(per_region)
        lines = [f"- [{r.source}] {r.title}" for r in sub.itertuples()]
        parts.append(f"### Tin {region} ({len(lines)} tiêu đề mới nhất)\n" + "\n".join(lines))
    return "\n\n".join(parts)

def build_payload(top_n, news_n):
    """Đóng gói toàn bộ bối cảnh thành 1 chuỗi CSV/text ~6-9K token."""
    conn = sqlite3.connect(DB_PATH)
    vnindex = load_vnindex(conn)
    conn.close()
    top = load_top_stocks(top_n)
    breadth = pd.read_csv(MARKET_BREADTH_PATH)
    macro = pd.read_csv(MACRO_SNAPSHOT_PATH)
    macro["value"] = macro["value"].round(2)   # 7482.7099609375 -> 7482.71, đỡ phí token

    payload = f"""## 1. VNINDEX
{vnindex}

## 2. Độ rộng thị trường (dòng ALL = toàn thị trường, còn lại là từng ngành, tính trên mã có GD phiên gần nhất)
{breadth.to_csv(index=False)}

## 3. Vĩ mô (chg_prev/1m/1y: đơn vị %% là hiệu số điểm %%, còn lại là %% thay đổi)
{macro.to_csv(index=False)}

## 4. Top {len(top)} mã RS cao nhất (ĐÃ LỌC: margin sạch, GTGD>=3 tỷ/phiên; roe %%; foreign_room_pct = %% room ngoại còn trống)
{top.to_csv(index=False)}

## 5. Tin tức
{load_news(news_n)}

---
Dựa DUY NHẤT vào dữ liệu trên, hãy viết báo cáo chiến lược cuối ngày."""
    return payload, set(top["ticker"])

# ==========================================
# GỌI LLM (phần xác suất duy nhất của cả pipeline)
# ==========================================
def call_llm(payload, model):
    """Structured outputs (output_config.format) -> JSON hợp lệ 100%, không cần regex vớt.
    SDK tự retry 429/5xx (max_retries=2). Trả về (dict, usage)."""
    import anthropic
    client = anthropic.Anthropic()   # tự đọc ANTHROPIC_API_KEY từ môi trường
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            output_config={"format": {"type": "json_schema", "schema": REPORT_SCHEMA}},
            messages=[{"role": "user", "content": payload}],
        )
    except anthropic.AuthenticationError:
        sys.exit("[Lỗi] API key sai/thiếu. Đặt biến môi trường ANTHROPIC_API_KEY rồi chạy lại.")
    except anthropic.RateLimitError as e:
        sys.exit(f"[Lỗi] Bị rate-limit sau khi SDK đã tự retry. Chờ rồi chạy lại. ({e.message})")
    except anthropic.APIStatusError as e:
        sys.exit(f"[Lỗi] API trả {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        sys.exit("[Lỗi] Mạng đứt, không gọi được API.")

    if resp.stop_reason == "max_tokens":
        print(" [cảnh báo] Output bị cắt vì chạm max_tokens — JSON có thể thiếu trường")
    if resp.stop_reason == "refusal":
        sys.exit("[Lỗi] Model từ chối trả lời (hiếm gặp với dữ liệu tài chính).")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text), resp.usage

def validate(report, sent_tickers):
    """Chốt chặn ảo giác: mã LLM nhắc đến phải nằm trong danh sách Python đã gửi."""
    ghosts = [x["ticker"] for x in report.get("stock_notes", []) if x["ticker"] not in sent_tickers]
    if ghosts:
        print(f" [CẢNH BÁO ẢO GIÁC] LLM nhắc mã không có trong dữ liệu gửi đi: {ghosts}")
    return ghosts

def render_md(report, model):
    """Đổ JSON ra Markdown cho người đọc."""
    L = [f"# Báo cáo chiến lược cuối ngày — {vn_now():%Y-%m-%d}",
         f"_Model: {model} | Sinh tự động bởi ai_analyzer.py — tham khảo cá nhân, không phải khuyến nghị đầu tư_",
         f"\n## Regime: **{report['market_regime'].upper()}** | Rủi ro danh mục: **{report['portfolio_risk']}**",
         report["regime_reason"],
         "\n## Vĩ mô\n" + report["macro_summary"],
         "\n## Chủ đề tin tức"]
    for t in report["news_themes"]:
        L.append(f"- **{t['theme']}** ({t['impact_vn']}): {t['note']}")
    L.append("\n## Ngành\n" + report["sector_view"])
    L.append("\n## Từng mã")
    for x in report["stock_notes"]:
        L.append(f"### {x['ticker']} — `{x['stance']}`\n{x['entry_logic']}")
        if x["risk_flags"]:
            L.append("Rủi ro: " + " · ".join(x["risk_flags"]))
    L.append("\n## Kế hoạch phiên mai")
    L += [f"{i}. {a}" for i, a in enumerate(report["action_plan"], 1)]
    return "\n".join(L)

def main():
    ap = argparse.ArgumentParser(description="Trộn snapshot + macro + news, gọi Claude sinh báo cáo chiến lược JSON+Markdown")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in payload + ước tính token, KHÔNG gọi API")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--top", type=int, default=TOP_N)
    args = ap.parse_args()

    for f in (SCREEN_SNAPSHOT_PATH, MARKET_BREADTH_PATH, MACRO_SNAPSHOT_PATH, NEWS_LATEST_PATH):
        if not f.exists():
            sys.exit(f"[Lỗi] Thiếu {f} — chạy pipeline theo thứ tự trong README mục 6 trước.")

    payload, sent = build_payload(args.top, NEWS_PER_REGION)
    est = len(payload) // 3   # ước lượng thô ~3 ký tự/token cho text Việt+số
    print(f"[ai_analyzer] Payload {len(payload):,} ký tự (~{est:,} token) | {len(sent)} mã | model {args.model}")

    if args.dry_run:
        preview_path = RUNTIME_ROOT / "ai_prompt_preview.txt"
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(SYSTEM_PROMPT + "\n\n=====\n\n" + payload)
        print(f"[dry-run] Đã ghi payload -> {preview_path} (tự duyệt trước khi chạy thật)")
        return

    report, usage = call_llm(payload, args.model)
    validate(report, sent)

    stamp = vn_now().strftime("%Y%m%d")
    report_json_path = RUNTIME_ROOT / f"ai_report_{stamp}.json"
    report_md_path = RUNTIME_ROOT / f"ai_report_{stamp}.md"
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(render_md(report, args.model))
    # Giá Sonnet 5 niêm yết $3/$15 mỗi 1M token (khuyến mãi $2/$10 đến 31/08/2026)
    cost = usage.input_tokens / 1e6 * 3 + usage.output_tokens / 1e6 * 15
    print(f"[ai_analyzer] Token vào/ra: {usage.input_tokens:,}/{usage.output_tokens:,} ≈ ${cost:.3f}")
    print(f"[ai_analyzer] Đã ghi {report_json_path} + {report_md_path}")

if __name__ == "__main__":
    main()
