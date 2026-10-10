# Stock Lookup

**Evidence-first research and decision-support infrastructure for Vietnamese equities.**

Stock Lookup turns market data, financial evidence, corporate events, valuation context, technical structure, and risk inputs into deterministic research products for HOSE, HNX, and UPCoM securities.

It is designed around one rule:

> **Facts and numerical calculations come from retained evidence and deterministic engines. AI explains, synthesizes, challenges, and surfaces uncertainty — it does not become data authority.**

## What the project does

```text
Market / financial / corporate evidence
        ↓
Raw retention + provenance
        ↓
Canonical + temporal + fitness semantics
        ↓
Deterministic research engines
        ↓
Market / technical / fundamental / valuation / event context
        ↓
Integrated research decision + trigger / invalidation
        ↓
AI research handoff
        ↓
Human decision + Dashboard
        ↓
Prospective outcome feedback
```

The current production workflow is operated through the canonical Owner Daily path and publishes governed research artifacts to downstream AI and Dashboard consumers.

## Core principles

- **Evidence first.** Unknown, stale, proxy, blocked, and qualified states remain explicit.
- **Deterministic numerical authority.** Formalizable calculations are implemented in Python and validated with reproducible tests.
- **Feature-level fitness.** Missing authority blocks only the dependent use case; it does not invalidate unrelated research.
- **Point-in-time discipline.** Current research, historical reconstruction, and PIT/backtest authority are separate modes.
- **Sector-aware analysis.** Banks, securities firms, industrial companies, and other sectors are not forced into one financial template.
- **AI is a research layer.** AI may explain and challenge a thesis, but it may not invent financial facts, ex-dates, probabilities, or target-price authority.
- **Human approval remains final.** Research posture is not an execution order.

## Public project map

| Area | Entry point |
|---|---|
| Product direction | [docs/PRODUCT_NORTH_STAR.md](docs/PRODUCT_NORTH_STAR.md) |
| Strategic roadmap | [docs/NORTH_STAR.md](docs/NORTH_STAR.md) |
| Current operational state | [docs/ACTIVE_STATE.md](docs/ACTIVE_STATE.md) |
| Machine-readable execution state | [docs/ROADMAP_STATE.json](docs/ROADMAP_STATE.json) |
| Roadmap history / dependencies | [docs/ROADMAP.md](docs/ROADMAP.md) |
| Architecture decisions | [docs/DECISIONS.md](docs/DECISIONS.md) |
| Concrete runtime topology | [docs/SYSTEM_MAP.md](docs/SYSTEM_MAP.md) |
| Analytics & decision feature contract | [docs/ANALYTICS_AND_DECISION_FEATURE_SPEC.md](docs/ANALYTICS_AND_DECISION_FEATURE_SPEC.md) |
| CI / dependency tiers | [docs/CI_AND_DEPENDENCY_TIERS.md](docs/CI_AND_DEPENDENCY_TIERS.md) |
| Repository layout migration | [docs/REPOSITORY_LAYOUT_MIGRATION.md](docs/REPOSITORY_LAYOUT_MIGRATION.md) |
| Acquisition implementation | [stocklookup_core/acquisition/](stocklookup_core/acquisition/) |
| Official document evidence | [stocklookup_core/evidence/](stocklookup_core/evidence/) |
| Financial panels, Financial V2 and fundamental research | [stocklookup_core/financial/](stocklookup_core/financial/) |
| Valuation calculations, peers and current-input scaleout | [stocklookup_core/valuation/](stocklookup_core/valuation/) |
| Independent thesis research | [stocklookup_core/research/](stocklookup_core/research/) |

## Canonical runtime path

```text
stocklookup.ps1
  └─ stocklookup.py
      └─ Owner Daily workflow
          ├─ governed session resolution
          ├─ market-data acquisition / reuse
          ├─ canonical research materialization
          ├─ tactical + financial + valuation integration
          ├─ integrated decision products
          ├─ AI handoff publication
          └─ Dashboard release + verification
```

The authoritative module-level flow is documented in [docs/SYSTEM_MAP.md](docs/SYSTEM_MAP.md).

## Current execution boundary

The October 1, 2026 ordinary Owner Daily live-acceptance gate is complete. The production PR that closes that gate passed Producer CI and was merged to `main`.

The next roadmap priority is **Current Research Coverage & Decision Fitness**: measure which securities currently have usable price, tactical, fundamental, valuation, corporate/event, and integrated-decision context; then prioritize the gaps that materially reduce decision quality.

Higher-authority lanes such as full historical RAW_AS_TRADED, PIT backtesting, execution-grade liquidity, and live position sizing remain separate and must not block unrelated Current Research.

## Repository structure

The repository is historically flat and currently contains many top-level Python modules. That is recognized technical debt, not the target package layout.

The migration policy is **incremental and call-graph-driven**:

- no wholesale `src/` rewrite;
- no module is called legacy based on its filename;
- capability families move only when their production consumers/tests are understood;
- migration occurs alongside useful capability work, with parity validation;
- the public root is gradually reduced toward a small front-door surface.

See [docs/REPOSITORY_LAYOUT_MIGRATION.md](docs/REPOSITORY_LAYOUT_MIGRATION.md).

## Development

### Requirements

- Python 3.11+ (Python 3.13 supported)
- On Windows, long paths are recommended:
  `git config --global core.longpaths true`

### Install core + test dependencies

```bash
python -m pip install -r requirements.txt -r requirements-test.txt -c constraints.txt
```

Optional provider runtimes are intentionally separated from the hermetic core tier. See [docs/CI_AND_DEPENDENCY_TIERS.md](docs/CI_AND_DEPENDENCY_TIERS.md).

### Run focused verification

```bash
python -m pytest -q tests/test_production_call_shape_smoke.py
python -m py_compile stocklookup.py canonical_daily_operation.py daily_producer_pipeline.py
python tools/stocklookup_roadmap.py --check
```

CI contains separate structural, hermetic regression, retained-evidence, and production call-shape checks.

## Contributing

Contributions are welcome when they are reproducible and bounded. Start with:

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [AGENTS.md](AGENTS.md) for AI-agent execution rules

## License

MIT — see [LICENSE](LICENSE).

---

**Research disclaimer:** Stock Lookup produces quantitative research and decision-support outputs. It does not provide personalized investment advice or autonomous trade execution.
