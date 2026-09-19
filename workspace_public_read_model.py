"""workspace_index/v1 + workspace_detail_shard/v1: the public two-layer read model for the
Dashboard's Investment Decision Workspace product surface.

Pure, presentation-only reshaping of an already-validated ``investment_decision_workspace_
projection/v1`` artifact (see ``investment_decision_workspace_projection.py`` /
``publish_dashboard.py::validate_workspace_projection``). No new analytical computation, no
requalification: every value here is copied verbatim from the source artifact.

Why this exists: the source artifact's per-ticker "cards" carry full diagnostic detail
(method_diagnostics, financial_analysis.compact, feature_fitness maps, ...) needed only when a
reader opens one ticker's detail. Serving all of it to every page load made the public payload
a single ~95MB JSON file -- a Git/GitHub-Pages release-size concern, not an analytical one. This
module splits that one artifact into:

* an INDEX (``workspace_index/v1``): one small "thin card" per ticker with only the fields the
  existing list/table/filter/search views (`assets/js/investment-workspace.js`,
  `assets/js/screener-master.js`, `assets/js/signals-product.js`) actually read, plus a
  deterministic ``detail_shard`` reference.
* DETAIL SHARDS (``workspace_detail_shard/v1``), one per deterministic bucket: the full,
  unmodified per-ticker card, grouped by the ticker's first letter (A-Z; any ticker not starting
  with an ASCII letter buckets under ``_``). For today's all-alphabetic 3-letter VN ticker
  universe this yields on the order of 20-26 shards -- within the "roughly 16-32 deterministic
  shards" target -- without an arbitrary/opaque hashing scheme.

Both documents carry the source artifact's own session (`as_of_session`) and content identity
(`artifact_identity`) so a consumer can prove an index and a shard came from the same publish
(see ``publish_dashboard.py``'s post-write binding verification) rather than silently combining
an index from one session with a shard from another.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

INDEX_CONTRACT_VERSION = "workspace_index/v1"
SHARD_CONTRACT_VERSION = "workspace_detail_shard/v1"
_FALLBACK_SHARD_KEY = "_"


def shard_key_for_ticker(ticker: str) -> str:
    """Deterministic bucket for one ticker: its first ASCII letter, upper-cased.

    A ticker that does not start with an ASCII letter (none exist in the current universe, but
    this must never raise or silently drop a record) buckets under ``_`` rather than being
    dropped or crashing the whole publish.
    """
    first = (ticker or "")[:1].upper()
    return first if "A" <= first <= "Z" else _FALLBACK_SHARD_KEY


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_of(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _thin_card(ticker: str, card: Mapping[str, Any], shard_key: str) -> dict[str, Any]:
    """The list/filter/search-relevant subset of one full card, at the SAME field paths the
    full card uses. This is what makes every existing pure rendering/filter function in
    investment-workspace.js (FILTERS' `test`, `renderRow`, `analysisRecord`, ...) work
    unmodified against either an index thin-card or a full detail-shard card.
    """
    tactical = card.get("tactical") or {}
    fundamental = card.get("fundamental") or {}
    valuation = card.get("valuation") or {}
    liquidity = card.get("liquidity") or {}
    catalyst = card.get("catalyst") or {}
    lineage = card.get("lineage") or {}
    why = card.get("why") or {}
    counter_thesis = card.get("counter_thesis") or {}
    reference_trigger = card.get("reference_trigger") or {}
    invalidation = card.get("invalidation") or {}
    invalidation_technical = invalidation.get("technical") or {}
    invalidation_fundamental = invalidation.get("fundamental") or {}
    confirmation = card.get("confirmation") or {}
    market_sector = card.get("market_sector") or {}
    signal_velocity = card.get("signal_velocity") or {}
    flow_price = card.get("flow_price") or {}
    official_scope = card.get("official_research_scope")

    return {
        "ticker": ticker,
        "sector": card.get("sector"),
        "as_of_session": card.get("as_of_session"),
        "research_stance": card.get("research_stance"),
        "research_stance_readiness": card.get("research_stance_readiness"),
        "entry_state": card.get("entry_state"),
        "entry_action": card.get("entry_action"),
        "setup_tags": list(card.get("setup_tags") or []),
        # Never populated by any Producer today (repo-wide: no price/session-move field is
        # joined onto this card) -- carried through as-is so a future price join needs no
        # index-shape change, and so `retainedPrice()`'s existing candidate list keeps working.
        "current_price": card.get("current_price"),
        "price": card.get("price"),
        "tactical": {
            "primary_entry_state": tactical.get("primary_entry_state"),
            "current_price": tactical.get("current_price"),
        },
        "fundamental": {"state": fundamental.get("state"), "trajectory": fundamental.get("trajectory")},
        "valuation": {
            "relative_research_state": valuation.get("relative_research_state"),
            "earnings_state": valuation.get("earnings_state"),
            "usable_relative_method_count": valuation.get("usable_relative_method_count"),
        },
        "liquidity": {"readiness": liquidity.get("readiness")},
        "catalyst": {"status": catalyst.get("status")},
        "lineage": {"per_axis_freshness": dict(lineage.get("per_axis_freshness") or {})},
        # Capped at 3: no list/summary view ever reads past compactReasons()'s max limit of 3.
        "why": {"deterministic_reasons": list((why.get("deterministic_reasons") or [])[:3])},
        "counter_thesis": {"key_counter_thesis": list((counter_thesis.get("key_counter_thesis") or [])[:3])},
        "reference_trigger": dict(reference_trigger),
        "invalidation": {
            "technical": {
                "boundary_type": invalidation_technical.get("boundary_type"),
                "status": invalidation_technical.get("status"),
                "semantic": invalidation_technical.get("semantic"),
            },
            "fundamental": {"status": invalidation_fundamental.get("status")},
        },
        "confirmation": {
            "status": confirmation.get("status"),
            "confirmation_trigger_state": confirmation.get("confirmation_trigger_state"),
        },
        "market_sector": {
            "breadth_regime": market_sector.get("breadth_regime"),
            "sector_relative_context": market_sector.get("sector_relative_context"),
        },
        "signal_velocity": {
            "overall_transition_state": signal_velocity.get("overall_transition_state"),
            "evidence_quality": signal_velocity.get("evidence_quality"),
        },
        "flow_price": {
            "relationship": flow_price.get("relationship"),
            "cohort_membership": flow_price.get("cohort_membership"),
            "evidence_quality": flow_price.get("evidence_quality"),
        },
        "official_research_scope": (
            {"scope_bucket": official_scope.get("scope_bucket")} if isinstance(official_scope, Mapping) else None
        ),
        "detail_shard": shard_key,
    }


def build_public_read_model(payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Split one validated workspace artifact into (index_document, {shard_key: shard_document}).

    Pure: no I/O, no randomness. Every ticker in ``payload["cards"]`` appears in exactly one
    shard and exactly once in the index -- callers can assert
    ``sum(len(s["tickers"]) for s in shards.values()) == len(payload["cards"])`` for a
    zero-silent-drop guarantee across the split itself.
    """
    cards = payload.get("cards")
    if not isinstance(cards, Mapping) or not cards:
        raise ValueError("WORKSPACE_READ_MODEL_SOURCE_CARDS_MISSING")

    as_of_session = payload.get("as_of_session")
    artifact_identity = payload.get("artifact_identity")

    shards: dict[str, dict[str, Any]] = {}
    index_cards: dict[str, Any] = {}
    for ticker in sorted(cards):
        card = cards[ticker]
        key = shard_key_for_ticker(ticker)
        shards.setdefault(key, {}).setdefault("tickers", {})[ticker] = card
        index_cards[ticker] = _thin_card(ticker, card, key)

    shard_manifest: dict[str, Any] = {}
    finished_shards: dict[str, dict[str, Any]] = {}
    for key in sorted(shards):
        tickers = shards[key]["tickers"]
        shard_doc = {
            "schema_version": "1.0.0",
            "contract_version": SHARD_CONTRACT_VERSION,
            "as_of_session": as_of_session,
            "source_artifact_identity": artifact_identity,
            "shard_key": key,
            "ticker_count": len(tickers),
            "tickers": tickers,
        }
        finished_shards[key] = shard_doc
        shard_manifest[key] = {
            "path": f"data/workspace_detail/{key}.json",
            "ticker_count": len(tickers),
            "sha256": _sha256_of(shard_doc),
        }

    index_document: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": INDEX_CONTRACT_VERSION,
        "as_of_session": as_of_session,
        "source_artifact_identity": artifact_identity,
        "source_contract_version": payload.get("contract_version"),
        "milestone": payload.get("milestone"),
        "coverage": payload.get("coverage") or {},
        "official_scope_coverage": payload.get("official_scope_coverage"),
        "blocked_outputs": payload.get("blocked_outputs") or {},
        "authority_effect": payload.get("authority_effect"),
        # Global (not per-ticker) provenance for the whole publish -- tiny (a handful of source
        # artifact identities), and read by the ticker-detail drawer's "Dữ liệu" disclosure for
        # every ticker alike, so it belongs on the index exactly once, not inside each shard.
        "source_artifacts": payload.get("source_artifacts") or {},
        "display_metric_catalog": payload.get("display_metric_catalog") or {},
        "shard_manifest": shard_manifest,
        "cards": index_cards,
    }
    return index_document, finished_shards
