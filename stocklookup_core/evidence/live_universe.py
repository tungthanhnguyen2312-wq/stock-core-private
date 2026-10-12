"""Fail-closed current-analysis live-universe contract."""
from __future__ import annotations
import hashlib
import json
from collections import Counter
from pathlib import Path
import pandas as pd

INDEX_OR_SYNTHETIC = frozenset({"VNINDEX", "HNXINDEX", "UPCOMINDEX"})
ACTIVE_EXCHANGES = frozenset({"HSX", "HNX", "UPCOM"})
EQUITY_TYPES = frozenset({"STOCK", "EQUITY", "COMMON_STOCK"})


def _text(value) -> str | None:
    if pd.isna(value): return None
    value = str(value).strip().upper()
    return value or None


def evaluate(snapshot: pd.DataFrame, instruments: pd.DataFrame | None = None) -> pd.DataFrame:
    """Annotate snapshot rows without deleting history; only ``live`` is eligible."""
    out = snapshot.copy()
    out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
    out["latest_price_date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    reference = out["latest_price_date"].dropna().max()
    out["reference_market_date"] = reference
    out["days_stale"] = (pd.to_datetime(reference) - pd.to_datetime(out["latest_price_date"])).dt.days if reference else pd.NA
    master = pd.DataFrame(columns=["ticker", "instrument_type", "listing_exchange", "listing_source", "listing_snapshot_hash"])
    if instruments is not None and not instruments.empty:
        master = instruments.copy(); master["ticker"] = master["ticker"].astype(str).str.upper().str.strip()
        master = master.drop_duplicates("ticker", keep="last")
    out = out.merge(master, on="ticker", how="left")
    statuses, reasons = [], []
    for row in out.itertuples(index=False):
        ticker = _text(row.ticker)
        exchange = _text(getattr(row, "listing_exchange", None)) or _text(getattr(row, "exchange", None))
        instrument = _text(getattr(row, "instrument_type", None))
        date = getattr(row, "latest_price_date", None)
        if ticker in INDEX_OR_SYNTHETIC:
            status, reason = "excluded", "index_or_synthetic"
        elif instrument is None:
            status, reason = "unknown", "instrument_type_unknown"
        elif instrument not in EQUITY_TYPES:
            status, reason = "excluded", "instrument_type_not_equity"
        elif exchange == "DELISTED":
            status, reason = "excluded", "listing_inactive_or_delisted"
        elif exchange is None:
            status, reason = "unknown", "listing_status_unknown"
        elif exchange not in ACTIVE_EXCHANGES:
            status, reason = "excluded", "listing_exchange_not_active"
        elif not date:
            status, reason = "excluded", "missing_price_date"
        elif date != reference:
            status, reason = "excluded", "stale_price"
        else:
            status, reason = "live", "eligible_equity_current_session"
        statuses.append(status); reasons.append(reason)
    out["live_universe_status"] = statuses
    out["live_universe_reason"] = reasons
    out["is_live"] = out["live_universe_status"].eq("live")
    return out


def summary(frame: pd.DataFrame, *, source: str = "screen_snapshot.csv") -> dict:
    status = frame.get("live_universe_status", pd.Series(dtype=str)).fillna("unknown")
    reason = frame.get("live_universe_reason", pd.Series(dtype=str)).fillna("unknown")
    canonical = frame[[c for c in ("ticker", "live_universe_status", "live_universe_reason", "latest_price_date", "reference_market_date", "days_stale") if c in frame]].sort_values("ticker")
    raw = canonical.to_json(orient="records", date_format="iso", force_ascii=True)
    return {"live_universe_count": int((status == "live").sum()), "excluded_count": int((status != "live").sum()),
            "excluded_by_reason": dict(sorted(Counter(reason[status != "live"]).items())),
            "reference_market_date": (str(frame["reference_market_date"].dropna().max()) if "reference_market_date" in frame and frame["reference_market_date"].notna().any() else None),
            "universe_source": source, "universe_hash": hashlib.sha256(raw.encode()).hexdigest()}
