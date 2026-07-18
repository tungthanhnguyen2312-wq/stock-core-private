"""Deterministic canonical ticker mapping for news articles."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

try:
    from source_schema_guards import guard_alias_columns
except ModuleNotFoundError:  # Loaded directly by AI ANALYZE via file location.
    _guard_spec = importlib.util.spec_from_file_location(
        "vnstock_source_schema_guards", Path(__file__).with_name("source_schema_guards.py")
    )
    if _guard_spec is None or _guard_spec.loader is None:
        raise
    _guard_module = importlib.util.module_from_spec(_guard_spec)
    _guard_spec.loader.exec_module(_guard_module)
    guard_alias_columns = _guard_module.guard_alias_columns


ROOT = Path(__file__).resolve().parent
DEFAULT_ALIASES_PATH = ROOT / "config" / "ticker_aliases.csv"
DEFAULT_CONFIG_PATH = ROOT / "config" / "news_mapping_config.json"

ALIAS_CONFIDENCE = {
    "legal_name": 1.0,
    "company_name": 0.98,
    "registered_alias": 0.95,
    "ticker": 0.92,
    "subsidiary": 0.85,
    "brand": 0.80,
}


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"\s+", " ", text).strip()


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _canonical_link(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def article_id(article: dict[str, Any]) -> str:
    explicit = str(article.get("news_id") or article.get("id") or "").strip()
    if explicit:
        return explicit
    identity = _canonical_link(article.get("link")) or "|".join([
        normalize_text(article.get("title")),
        str(article.get("published_utc") or ""),
        normalize_text(article.get("source")),
    ])
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def deduplicate_articles(articles: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output = []
    for article in articles:
        link = _canonical_link(article.get("link"))
        key = f"link:{link}" if link else "title:" + "|".join([
            normalize_text(article.get("title")),
            str(article.get("published_utc") or "")[:10],
        ])
        if key in seen:
            continue
        seen.add(key)
        clean = dict(article)
        clean["news_id"] = article_id(clean)
        output.append(clean)
    return output


@dataclass(frozen=True)
class Alias:
    ticker: str
    alias: str
    alias_type: str
    priority: int = 0
    valid_from: str = ""
    valid_to: str = ""


class TickerAliasRegistry:
    def __init__(self, aliases: Iterable[Alias] = ()) -> None:
        self.aliases = list(aliases)

    @classmethod
    def from_csv(cls, path: Path = DEFAULT_ALIASES_PATH) -> "TickerAliasRegistry":
        aliases: list[Alias] = []
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            guard_alias_columns(reader.fieldnames or [], str(path))
            for row in reader:
                aliases.append(Alias(
                    ticker=str(row.get("ticker", "")).strip().upper(),
                    alias=str(row.get("alias", "")).strip(),
                    alias_type=str(row.get("alias_type", "")).strip().lower(),
                    priority=int(row.get("priority") or 0),
                    valid_from=str(row.get("valid_from", "")).strip(),
                    valid_to=str(row.get("valid_to", "")).strip(),
                ))
        return cls(aliases)

    def add_metadata_aliases(self, metadata_rows: Iterable[dict[str, Any]]) -> None:
        """Create aliases only from explicit metadata fields that actually exist."""
        existing = {(item.ticker, normalize_text(item.alias), item.alias_type) for item in self.aliases}
        for row in metadata_rows:
            ticker = str(row.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            candidates = [
                (ticker, "ticker", 50),
                (row.get("legal_name"), "legal_name", 100),
                (row.get("company_name"), "company_name", 95),
            ]
            for raw_alias, alias_type, priority in candidates:
                alias = str(raw_alias or "").strip()
                key = (ticker, normalize_text(alias), alias_type)
                if alias and key not in existing:
                    self.aliases.append(Alias(ticker, alias, alias_type, priority))
                    existing.add(key)


def _active_for(alias: Alias, published: datetime | None) -> bool:
    date = published.date().isoformat() if published else ""
    return not (
        date and alias.valid_from and date < alias.valid_from
        or date and alias.valid_to and date > alias.valid_to
    )


def _contains_exact_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text))


def _ticker_has_financial_context(raw_text: str, ticker: str) -> bool:
    escaped = re.escape(ticker)
    patterns = [
        rf"(?:mã(?:\s+cổ\s+phiếu)?|cổ\s+phiếu|hose|hsx|hnx|upcom)\s*[:\-]?\s*{escaped}\b",
        rf"\b{escaped}\b\s*(?:\((?:hose|hsx|hnx|upcom)\)|trên\s+sàn)",
    ]
    return any(re.search(pattern, raw_text, flags=re.IGNORECASE) for pattern in patterns)


def map_article(
    article: dict[str, Any],
    registry: TickerAliasRegistry,
    *,
    mapping_version: str = "1.0.0",
    auto_accept_confidence: float = 0.90,
    candidate_confidence: float = 0.70,
) -> dict[str, list[dict[str, Any]]]:
    raw_text = " ".join(str(article.get(field) or "") for field in ("title", "summary"))
    text = normalize_text(raw_text)
    published = _parse_datetime(article.get("published_utc"))
    best: dict[str, dict[str, Any]] = {}
    for alias in registry.aliases:
        if not alias.ticker or not alias.alias or not _active_for(alias, published):
            continue
        normalized_alias = normalize_text(alias.alias)
        if alias.alias_type == "ticker":
            matched = _ticker_has_financial_context(raw_text, alias.alias.upper())
            method = "exact_ticker_financial_context"
        else:
            matched = _contains_exact_phrase(text, normalized_alias)
            method = f"exact_{alias.alias_type}"
        if not matched:
            continue
        confidence = ALIAS_CONFIDENCE.get(alias.alias_type, 0.0)
        record = {
            "news_id": article_id(article),
            "ticker": alias.ticker,
            "match_method": method,
            "matched_alias": alias.alias,
            "confidence": confidence,
            "mapping_version": mapping_version,
            "priority": alias.priority,
        }
        current = best.get(alias.ticker)
        if current is None or (confidence, alias.priority) > (current["confidence"], current["priority"]):
            best[alias.ticker] = record
    accepted = []
    candidates = []
    for record in sorted(best.values(), key=lambda item: item["ticker"]):
        if record["confidence"] >= auto_accept_confidence:
            accepted.append(record)
        elif record["confidence"] >= candidate_confidence:
            candidates.append(record)
    return {"accepted": accepted, "candidates": candidates}


def map_articles(
    articles: Iterable[dict[str, Any]],
    registry: TickerAliasRegistry,
    **kwargs: Any,
) -> dict[str, list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for article in deduplicate_articles(articles):
        result = map_article(article, registry, **kwargs)
        accepted.extend(result["accepted"])
        candidates.extend(result["candidates"])
    return {"accepted": accepted, "candidates": candidates}


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def summarize_news(
    ticker: str,
    articles: Iterable[dict[str, Any]],
    registry: TickerAliasRegistry,
    *,
    now: datetime | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = config or load_config()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = now - timedelta(days=int(settings["lookback_days"]))
    deduplicated = deduplicate_articles(articles)
    recent = [
        article for article in deduplicated
        if (published := _parse_datetime(article.get("published_utc"))) is not None and published >= cutoff
    ]
    mapping_by_news: dict[str, dict[str, list[dict[str, Any]]]] = {
        article["news_id"]: map_article(
            article, registry,
            mapping_version=settings["mapping_version"],
            auto_accept_confidence=float(settings["auto_accept_confidence"]),
            candidate_confidence=float(settings["candidate_confidence"]),
        )
        for article in recent
    }
    ticker = ticker.strip().upper()
    company_items = []
    candidate_items = []
    fallback = []
    for article in recent:
        mapping = mapping_by_news[article["news_id"]]
        accepted = [item for item in mapping["accepted"] if item["ticker"] == ticker]
        candidates = [item for item in mapping["candidates"] if item["ticker"] == ticker]
        if accepted:
            company_items.append({**article, "ticker_mapping": accepted[0]})
        elif candidates:
            candidate_items.append({**article, "ticker_mapping": candidates[0]})
        else:
            fallback.append(article)
    sector_items = [item for item in fallback if str(item.get("region", "")).lower() == "sector"]
    market_items = [item for item in fallback if item not in sector_items]
    max_company = int(settings["max_company_items"])
    max_fallback = int(settings["max_fallback_items"])
    company_items.sort(key=lambda item: str(item.get("published_utc", "")), reverse=True)
    sector_items.sort(key=lambda item: str(item.get("published_utc", "")), reverse=True)
    market_items.sort(key=lambda item: str(item.get("published_utc", "")), reverse=True)
    return {
        "status": "reported" if company_items else "no_company_specific_news",
        "company_news_count": len(company_items),
        "sector_news_count": len(sector_items),
        "market_news_count": len(market_items),
        "candidate_review_count": len(candidate_items),
        "lookback_days": int(settings["lookback_days"]),
        "cutoff": cutoff.isoformat().replace("+00:00", "Z"),
        "items": company_items[:max_company],
        "candidate_items": candidate_items[:max_company],
        "sector_items": sector_items[:max_fallback],
        "market_items": market_items[:max_fallback],
        "latest_published_utc": company_items[0].get("published_utc") if company_items else None,
        "mapping_version": settings["mapping_version"],
    }
