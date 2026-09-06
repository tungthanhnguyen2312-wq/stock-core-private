# Stock Lookup — Producer Architecture & Governance

**Stock Lookup** is actively developed, evidence-first open-source infrastructure for deterministic quantitative analytics and auditable financial intelligence on Vietnamese equities (HOSE, HNX, UPCoM). It is not an AI stock-prediction application.

The platform enforces strict computational determinism, immutable provenance tracking, and explicit fail-closed semantic gating. Numerical authority, risk boundaries, and financial facts are computed exclusively by pure, deterministic Python/vectorized engines; AI systems provide explanation, research synthesis, and counter-theses without altering numerical authority.

Contributions are welcome, especially reproducible bug reports, tests, documentation improvements, and bounded engineering changes. See the [MIT License](LICENSE), [CONTRIBUTING.md](CONTRIBUTING.md), and [SECURITY.md](SECURITY.md).

## Public / Open-Core Boundary

This repository is the **public MIT-licensed engineering core** of Stock Lookup. Public source does not mean that operational datasets, credentials, private portfolio state, proprietary calibration, execution configuration, or every future commercial capability are part of the public repository.

The project intentionally separates inspectable research infrastructure from sensitive or separately licensed operating assets. See [Public / Open-Core Boundary](docs/PUBLIC_OPEN_CORE_POLICY.md) and [Commercialization & Licensing Notes](docs/COMMERCIALIZATION.md).

Third-party market data and retained evidence keep their own redistribution terms; the repository's MIT License does not automatically grant rights to redistribute those external datasets.

---

## 1. Core Authority Model & Architectural Principles

1. **Evidence-First Provenance**: Every data point, financial metric, and price observation is bound to an immutable raw payload hash, request identity, provider timestamp, and schema version. Missing or unverified semantics are marked `UNKNOWN` rather than guessed.
2. **Deterministic Numerical Authority**: Calculations (OHLC aggregation, corporate action adjustments, moving averages, relative volume, volatility) are vectorized and pure. Floating point values, dates, and JSON serializations are deterministic and byte-stable.
3. **Fail-Closed Semantic Gating**: Downstream applications (strategy evaluation, portfolio sizing, valuation, backtesting) require explicit feature-level qualification. An unqualified field (e.g. unpromoted price basis or unevidenced volume unit) fails closed for dependent consumers without rejecting the underlying raw record.
4. **Separation of Concerns**:
   - **Producer (`stock-core-private`)**: Owns raw ingestion contracts, canonical reconciliation, temporal provenance, quality exception queues, and vectorized feature generation.
   - **Consumer / Dashboard**: Downstream consumer workspaces responsible for visualization, reporting, and interactive decision support.
   - **Evidence Lake (`operations-review/`)**: Retained raw captures, forensic audit logs, multi-session WebSocket recordings, and milestone closeout reports.

---

## 2. High-Level Pipeline Architecture

```
┌───────────────────────────────┐
│     Dynamic Market Universe   │ (3,250 instruments: 1,660 listed equity candidates,
└──────────────┬────────────────┘  1,590 unclassified security groups)
               │
               ▼
┌───────────────────────────────┐
│       Immutable Raw Lake      │ (Daily OHLC, trades history, foreign trading,
└──────────────┬────────────────┘  official corporate filings)
               │
               ▼
┌───────────────────────────────┐
│  Quality & Canonicalization   │ (Field-level validation, corporate-action ledger,
└──────────────┬────────────────┘  instrument master reconciliation)
               │
               ▼
┌───────────────────────────────┐
│    Temporal & PIT Boundary    │ (field_temporal_contract.py: 6 freshness states,
└──────────────┬────────────────┘  strict knowledge cutoff & price-basis gating)
               │
               ▼
┌───────────────────────────────┐
│    Vectorized Feature Store   │ (market_feature_store.py: cross-sectional & historical
└──────────────┬────────────────┘  features with bound TemporalField envelopes)
               │
               ▼
┌───────────────────────────────┐
│  Strategy & Risk Evaluation   │ (Declarative feature requirements, fail-closed
└──────────────┬────────────────┘  risk/liquidity boundaries)
               │
               ▼
┌───────────────────────────────┐
│  Human Decision / Dashboard   │ (Auditable research packets & executive summaries)
└───────────────────────────────┘
```

---

## 3. Current System Capabilities

- **Canonical Universe Hierarchy ([canonical_universe_tiers.py](canonical_universe_tiers.py))**: Deterministic instrument reconciliation (C.1) and tier classification DAG (C.2).
- **Field-Level Temporal Semantics ([field_temporal_contract.py](field_temporal_contract.py))**: Explicit freshness states (`current`, `expiring`, `stale`, `historical`, `missing`, `unknown`) and PIT qualification gating bound directly to field values.
- **Corporate Action Ledger & Multi-Event Extraction ([official_corporate_action_ledger.py](official_corporate_action_ledger.py))**: Additive and multiplicative factor trees from official filing authority (P0-A.2).
- **Vectorized Market Feature Store ([market_feature_store.py](market_feature_store.py))**: Vectorized technical and statistical feature generation with bound temporal metadata.
- **Fail-Closed Volume & Value Semantic Boundary ([market_volume_value_semantic_contract.py](market_volume_value_semantic_contract.py))**: Strict enforcement of permitted downstream uses.
- **Market-Wide Research Artifacts ([market_analysis_artifact.py](market_analysis_artifact.py))**: Deterministic cross-sectional research artifact generator across candidate universes.

---

## 4. Known Boundaries & Explicit Limitations

- **Price Basis (`RAW_AS_TRADED`)**: `NOT_PROMOTED`. Multi-session WebSocket capture (P0-A.3E Part A) is complete across Sessions 1–4, but event-window qualification (Part B) remains fail-closed pending qualified official ex-date notices. Unpromoted prices fail closed for point-in-time backtesting.
- **Liquidity & Sizing Prohibitions**: `QUALIFIED_LIQUIDITY_INPUTS = NO` and `POSITION_SIZING_IS_SAFE = NO`. Volume candidate $C_5 = 10 \times G_1$ is validated as an empirical shadow candidate (99.81%), but unit interpretation remains unevidenced. Market liquidity, market turnover, and position sizing are strictly prohibited.
- **Active Universe Qualification**: `ACTIVE_UNIVERSE` remains `UNKNOWN` (fail-closed) for all instruments pending verified exchange-mapping and listing-status official evidence.
- **Traded Value Input**: Daily traded value is `OBSERVED_ABSENT` from DNSE daily OHLC feeds; derived $p \times v$ has no independent daily anchor.

---

## 5. Authoritative Documentation Map

For development and governance, consult the following authoritative documents:

| Document | Purpose | Audience |
|----------|---------|----------|
| [docs/STATE.md](docs/STATE.md) | Current project phase, active blockers, completed gates, and immediate next action. | Human & AI Operators |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Architectural phase structure, milestone matrix, dependencies, and deferred tracks. | Human & AI Operators |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Chronological architectural decision records with formal rationales. | Human & AI Operators |
| [AGENTS.md](AGENTS.md) | Agent working rules, scope boundaries, and execution protocols. | AI Executors |
| [docs/AI_RULES.md](docs/AI_RULES.md) | Engineering safety policies, market data doctrine, and fail-closed rules. | AI Executors & Reviewers |
| [docs/PUBLIC_OPEN_CORE_POLICY.md](docs/PUBLIC_OPEN_CORE_POLICY.md) | Public/open-core boundary and assets that must stay outside the public repository. | Public, Maintainers & Contributors |
| [docs/COMMERCIALIZATION.md](docs/COMMERCIALIZATION.md) | MIT/commercialization posture, data-rights separation, and future product boundary. | Public & Maintainers |
| [LICENSE](LICENSE) | MIT Open Source License terms. | Public & Contributors |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution and maintainer guidelines. | Public & Contributors |
| [SECURITY.md](SECURITY.md) | Security vulnerability reporting protocol. | Public & Contributors |
| [docs/internal/](docs/internal/) | Consolidated AI-agent context, workspace audits, and validation reports. | Internal & AI Agents |
| [docs/archive/](docs/archive/) | Historical changelogs, manifests, and past decision archives. | Reference & Historical |
| `operations-review/` | Retained forensic reports, closeout records, and empirical validation artifacts. | Reference & Audit |

---

## 6. Development & Verification

### Prerequisites
- Python 3.11+ (Python 3.13 supported)
- Windows users: enable `core.longpaths` (`git config --global core.longpaths true`)

### Running Deterministic Unit Tests
```powershell
# Run core deterministic unit tests:
python -m pytest tests/test_market_analysis_artifact.py tests/test_field_temporal_contract.py tests/test_canonical_universe_tiers.py tests/test_market_volume_value_semantic_contract.py tests/test_official_corporate_action_pillar.py

# Verify syntax & compilation:
python -m py_compile market_analysis_artifact.py field_temporal_contract.py market_data_contracts.py market_feature_store.py

# Check git formatting:
git diff --check
```

> **Disclaimer**: Data and analysis outputs generated by this platform are for quantitative research and decision support only, not investment recommendations.
