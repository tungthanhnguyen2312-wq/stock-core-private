# Ecosystem Positioning and Comparative Review

**Review date:** 2026-09-27  
**Scope:** public GitHub projects related to Vietnamese equities, market-data access, quantitative analysis, AI-assisted research, and data pipelines.

This document explains how Stock Lookup fits into the public ecosystem without claiming that GitHub can provide an exhaustive catalogue of every related project.

## 1. What can and cannot be established from GitHub

GitHub is a code-hosting and collaboration platform, not a curated application directory. A domain survey therefore needs multiple methods:

1. repository search by names, descriptions, README text, topics, and recent activity;
2. code search for concrete dependencies, imports, file names, or API usage;
3. dependency/dependent views where GitHub recognizes the package ecosystem;
4. community-curated lists and external code indexes;
5. manual architectural review of representative repositories.

No one method proves that every relevant repository has been found.

GitHub's dependency graph is useful but **not exhaustive**: dependents are reported for public repositories, depend on supported package/manifest detection, and GitHub documents dependent counts as approximate. Code search is broader, but it is still a search/indexing system rather than a complete domain taxonomy.

For current GitHub Code Search, prefer modern qualifiers such as `path:`, `repo:`, `org:`, `language:`, `content:`, boolean operators, and regular expressions. For example, a search for a dependency declaration can be narrowed with a `path:` expression rather than assuming that an older `filename:` query is exhaustive.

External tools such as Sourcegraph or OSS Insight can widen discovery and trend analysis, but they also index defined corpora and should not be described as a complete map of all GitHub software.

## 2. Corrections to common ecosystem claims

The following statements are intentionally **not** used as Stock Lookup marketing claims:

| Claim | Assessment |
|---|---|
| "GitHub has ~400 million repositories." | Directionally outdated rather than materially false. GitHub's 2025 Octoverse reported about 630M total repositories and 395M public repositories. |
| "GitHub Dependents shows every repository using a package." | False as a universal claim. It covers public dependents recognized through supported dependency metadata; counts are approximate. |
| "80% of Vietnam-stock repos are data wrappers, 15% notebooks, 5% chatbots." | Unsupported without a reproducible census and classification method. Do not quote these percentages. |
| "99% of comparable projects call providers directly." | Unsupported. Representative projects often do call provider/API layers directly, but no defensible 99% measurement was established. |
| "The ecosystem stops at connectors and hobby scripts." | False / overly dismissive. Public projects now include data-engineering pipelines, backtesting, RAG, multi-agent research systems, dashboards, and commercial-data workflow packages. |
| "Stock Lookup is unique because it uses AI/quant for Vietnamese stocks." | False. Those ideas are common. |
| "No other project has evidence governance / PIT controls." | Not established. The defensible statement is that these controls are a central, unusually explicit design priority in Stock Lookup relative to the representative repositories reviewed. |

## 3. Representative public projects reviewed

This is a **representative comparison, not a ranking**.

| Project | Publicly stated focus | Relation to Stock Lookup |
|---|---|---|
| [vnstock](https://github.com/thinh-vu/vnstock) | Broad Python access and normalization for Vietnam financial-market data from third-party sources. | Stronger as a general access library; Stock Lookup should not position itself as a replacement data SDK. |
| [VietFin](https://github.com/vietfin/vietfin) | Python wrapper over public brokerage APIs, inspired by OpenBB-style data access. | Similar at the data-access boundary; different from Stock Lookup's governed evidence-to-decision objective. |
| [vnquant](https://github.com/phamdinhkhanh/vnquant) | Vietnam market data, financial reports, visualization and quantitative research support. | Overlap in data/technical research; Stock Lookup places more emphasis on provenance, temporal qualification and downstream use gates. |
| [Vietnam Stock Analysis Pipeline](https://github.com/thinh661/Vietnam_Stock_Analysis_Pipeline) | Data engineering with ingestion, Airflow, MinIO/Trino and Superset. | Demonstrates that serious VN-stock data pipelines exist publicly; its focus is ETL/storage/visualization rather than evidence-authority semantics. |
| [TradingAgent-VN](https://github.com/meth04/TradingAgent-VN) | Multi-agent analysis, Financial RAG, news, backtesting, portfolio workflows and dashboards. | Important counterexample to the claim that public VN-stock AI projects are only basic chatbots. Stock Lookup differs mainly in authority/provenance/PIT/fail-closed architecture, not in merely having agents or AI. |
| [FiinQuant Skill Package](https://github.com/FiinGroup/FiinQuant) | Skills/reference package for broad FiinQuant data, technical, portfolio and trading workflows. | Broader provider/platform workflow surface. Stock Lookup's project goal is governed independent research infrastructure, not provider-product breadth. |

Other public repositories exist and the set changes frequently.

## 4. What is genuinely differentiated in Stock Lookup

### 4.1 Evidence and provenance are part of the product contract

Stock Lookup does not treat a returned API value as automatically fit for every downstream use. Raw/retained evidence identity, source lineage, acquisition state, and semantic qualification are preserved and can block specific derived claims.

### 4.2 Temporal semantics are explicit

The system distinguishes concepts that are commonly collapsed in smaller research tools:

- session/observation date;
- acquisition time;
- knowledge-available time;
- current research versus historical reconstruction;
- point-in-time qualification;
- adjusted/retrospective versus raw-as-traded price basis.

This is especially important for backtests, historical decisions, corporate actions, and later-acquired financial evidence.

### 4.3 Fail-closed is use-specific rather than global

A field can be usable for one research purpose and blocked for another.

Examples:

- a current adjusted price can support descriptive Current Research while remaining unqualified for historical raw-as-traded backtesting;
- a descriptive liquidity proxy can support research while execution sizing remains blocked;
- a research valuation proxy can remain clearly labelled without being promoted to exact/official valuation.

The desired behavior is not "block everything until perfect." It is "use only what is qualified for the requested use."

### 4.4 Deterministic numerical authority is separated from AI

Formalizable calculations and eligibility gates are owned by deterministic code. AI can synthesize research, explain evidence, and generate counter-theses, but it is not allowed to silently fabricate financial facts, probabilities, target prices, or authority.

### 4.5 Operational modes are separate contracts

Ordinary Daily, Historical Backfill, and Recovery Replay serve different purposes. Historical reconstruction does not masquerade as evidence known during the historical session, and forensic recovery is not automatically promoted into normal production authority.

### 4.6 Governance is explicit

Source routes, feature fitness, semantic contracts, and authority changes have lifecycle/gate semantics rather than becoming trusted merely because code exists or tests pass.

## 5. What is **not** a Stock Lookup differentiator

Stock Lookup should not market the following as unique:

- fetching Vietnam equity data;
- technical indicators such as moving averages, RSI-style momentum, or relative volume;
- dashboards and screening;
- financial-statement analysis;
- AI/RAG/LLM research;
- multi-agent workflows;
- backtesting as a concept;
- portfolio optimization as a concept;
- using multiple data providers.

The differentiation is in how evidence, semantics, time, numerical authority, uncertainty and downstream eligibility are connected.

## 6. Current weaknesses and incomplete areas

The repository intentionally exposes important limitations instead of hiding them:

- `RAW_AS_TRADED` / historical PIT price authority is not fully promoted.
- Execution-grade liquidity and position sizing are not qualified.
- `ACTIVE_UNIVERSE` remains fail-closed where official listing/status evidence is insufficient.
- Exact valuation and market-wide current financial coverage remain incomplete; research proxies and exact methods must remain distinguishable.
- Some legacy supplemental KBS/VCI acquisition paths still depend on `vnstock`/`vnai`. These paths are transitional/security-gated and are not the target architecture; DNSE/Livespeed remains the primary market-data direction.
- Retained evidence and runtime artifacts make some high-value regression tests inherently different from clean-clone hermetic CI.
- The architecture is governance-heavy. That buys auditability, but it also creates integration complexity and can cause over-blocking if use-specific fitness is implemented incorrectly.

These are engineering debts or evidence ceilings, not reasons to hide valid research that remains fit for a narrower use.

## 7. Fair positioning statement

A defensible public description is:

> **Stock Lookup is an evidence-governed, deterministic research and decision-support pipeline for Vietnamese equities. Its primary differentiation is not data access or AI itself, but the explicit connection between provenance, temporal semantics, use-specific fitness, deterministic analytics, uncertainty, and human-facing research outputs.**

A description to avoid is:

> "The only serious / governed / AI-quant Vietnam stock project on GitHub."

That cannot be established from public search and is unnecessary to explain the project's value.

## 8. Re-evaluation policy

This comparison should be treated as dated research, not a permanent competitive claim. Revisit it when:

- a materially similar public project appears;
- Stock Lookup changes its product North Star;
- provider/source architecture changes;
- major authority boundaries such as PIT, valuation, liquidity, sizing, or execution are promoted.

When updating this document, compare concrete repository behavior and documented contracts rather than stars, marketing language, or superficial feature counts.
