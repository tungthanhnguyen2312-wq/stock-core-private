# Stock Lookup — Data-First Doctrine

> **Owner doctrine authority.** This file defines the stable architectural doctrine for Stock Lookup.
> It is intentionally short and should change rarely. Operational state belongs in `docs/STATE.md`;
> milestone sequencing belongs in `docs/ROADMAP.md`; implementation decisions belong in
> `docs/DECISIONS.md`. Those files must not silently redefine this doctrine.

## 1. Mission

Stock Lookup exists to turn Vietnamese market data and official evidence into analysis that is
traceable, reproducible, and useful for investment decisions.

The project does **not** begin with models, rankings, recommendations, dashboards, or AI prose.
It begins by collecting data broadly, preserving the original evidence, understanding exactly
what each field means, and making only the uses that the evidence actually supports.

The mandatory direction is:

`ACQUIRE BROADLY → PRESERVE RAW → EXTRACT → UNDERSTAND → CANONICALIZE → LABEL FITNESS FOR USE → DETERMINISTIC ANALYSIS → AI RESEARCH → HUMAN DECISION`

Market-wide / capability-first acquisition is the default. Historical single-ticker cohorts are
regression and validation evidence, not the default ingestion workflow.

## 2. Data acquisition comes before downstream authority

Qualification may block an unsafe **use** of data; it must not unnecessarily block acquisition or
retention of useful raw evidence.

Examples:

- historical price may be retained and used for bounded descriptive research while remaining
  ineligible for point-in-time backtesting;
- provider-reported shares may be retained while authoritative outstanding-share use remains
  blocked;
- an official PDF/blob may be retained even when extraction is still pending;
- a field with unresolved semantics is preserved with provenance and marked `UNKNOWN`, not
  discarded or silently coerced.

Missing data is never converted to zero. Unknown semantics are never converted to facts.
Provider-reported values are never silently promoted to official authority.

## 3. Source topology: capability-first, not provider-parity-first

DNSE/Livespeed is the primary market-data direction. FHSC is a complementary capability source
and shadow/reference source where useful. Official issuer, exchange, VSDC, SSC, and other approved
statutory sources are the primary evidence lane for authority-sensitive corporate and financial
facts.

A provider does **not** need to expose every capability.

- If DNSE provides a capability and FHSC does not, DNSE may still be used within its qualified
  scope.
- If FHSC provides a useful capability that DNSE does not, FHSC may be ingested within its own
  source contract; absence of a DNSE comparator is not by itself a blocker.
- When DNSE and FHSC claim the same canonical semantic, their overlap should be used for
  cross-validation, mismatch detection, unit/basis checks, and semantic reconciliation.
- Cross-validation does not create authority by itself; conflicting claims remain explicit and
  fail closed for the affected use.
- Do not create artificial provider-parity requirements.

Native provider representation must be preserved. Canonical normalization is explicit and
contract-driven. For the qualified Vietnamese listed-equity DNSE/FHSC price representations used
by Stock Lookup, native K-VND/share values are normalized to canonical VND/share by the explicit
source/capability/instrument contract; never use a generic heuristic such as `price < 1000`.
Price-unit normalization is separate from adjusted/raw-as-traded/PIT qualification.

## 4. Preserve first; extract and understand second

Every useful acquisition should retain, when applicable:

- provider/source identity;
- endpoint/document URL or stable source locator;
- retrieval/observed timestamp;
- requested session/period/ticker/instrument identity;
- exact raw payload or exact source document;
- SHA-256 or equivalent content identity;
- acquisition outcome/status;
- parser/extractor version when derived records are created.

Raw evidence is immutable by default. If a provider later revises a payload, preserve the new
version and the old version; do not silently overwrite historical evidence.

For unstructured evidence such as HTML, PDF, scanned filings, notices, and attachments, the normal
flow is:

`DISCOVER/FETCH → RETAIN EXACT SOURCE → HASH/PROVENANCE → EXTRACT → SOURCE-BOUND FACTS → CANONICAL RECORDS`

A retained blob that is not yet readable is still valuable evidence and should be marked
`RAW_RETAINED / EXTRACTION_PENDING` rather than treated as absent.

## 5. Online discovery and extraction are allowed as bounded evidence tools

When online access is available and the milestone permits it, ChatGPT, Codex, Claude Code, or other
approved agents may use the web to:

- discover official issuer/VSDC/exchange/regulatory URLs;
- locate filings, notices, attachments, and historical official documents;
- inspect public provider/API documentation;
- extract candidate tables, fields, or evidence spans from retained/public documents;
- reconcile a provider field with an official/public source.

This is an **evidence acquisition/enrichment lane**, not factual authority by itself.

AI-generated text, summaries, OCR guesses, or extracted candidates become usable facts only when
they remain tied to retained source material and pass the applicable deterministic/review contract.
Never ask an AI model to invent a missing financial fact, ex-date, share count, unit, actor identity,
or probability.

Do not expose credentials or secrets to chat/web tools. Use approved local credential handling for
authenticated providers.

## 6. Extraction and semantic completeness precede sophisticated analysis

The highest-value data work is to move each capability through these states:

1. **Acquired** — useful source data has been requested and retained.
2. **Extracted** — fields/facts/events can be read from raw evidence.
3. **Semantically understood** — unit, scope, period, basis, identity, and timing are known.
4. **Canonicalized** — mapped into Stock Lookup's stable taxonomy without losing native lineage.
5. **Fitness-for-use labelled** — each downstream use is explicitly allowed, blocked, unknown, or
   not applicable.

A field may be usable for one purpose and blocked for another. Example:

- `DISPLAY = YES`
- `CURRENT_RESEARCH = YES`
- `VALUATION = YES/NO/UNKNOWN`
- `PIT_BACKTEST = NO`
- `LIQUIDITY_SIZING = NO`

Do not turn a high-level authority blocker into a global data blocker.

## 7. Deterministic engines are numerical authority

Once inputs are sufficiently understood, Python/deterministic engines own formalizable outputs:

- technical indicators and breadth;
- financial ratios and quality metrics;
- valuation formulas;
- scenario calculations when assumptions are explicit;
- risk, liquidity, sizing, leverage, and backtest metrics when their required inputs qualify.

The model layer must report blocked/missing inputs rather than impute them invisibly. Exact methods
and proxy methods must remain distinguishable.

AI may explain, compare, synthesize, challenge a thesis, identify contradictions, and generate
research questions. AI does not replace deterministic calculation or factual evidence.

## 8. AI and presentation are downstream consumers

AI research, dashboards, briefs, rankings, and recommendation surfaces are downstream consumers of
qualified data and deterministic outputs. They must not become a substitute for unfinished data
coverage, extraction, semantics, or lineage work.

Do not build another presentation/digest layer merely because an upstream artifact exists.
A new milestone should normally answer at least one of these questions:

1. Does it acquire useful data that Stock Lookup does not yet retain?
2. Does it extract more usable information from retained raw evidence?
3. Does it resolve an important semantic/canonical ambiguity?
4. Does it improve explicit fitness-for-use for a real downstream consumer?
5. Does it create a genuinely new deterministic analytical capability from already-qualified data?

If the answer to all five is no, it is not a core-priority milestone.

## 9. Data Capability Map is the roadmap lens

Before opening a new core milestone, assess the relevant capability by dimensions such as:

- source discovered;
- acquisition coverage;
- raw retained;
- extraction coverage;
- semantic confidence;
- canonical mapping;
- temporal/PIT status;
- current-research usability;
- valuation usability;
- scenario usability;
- liquidity/sizing usability;
- backtest usability;
- known blockers and exact reasons.

Roadmap work should close the highest-value gaps in this map, not merely continue the most recent
technical thread.

## 10. Operational rules that must remain true

- Preserve raw observations and provenance.
- Never fabricate missing financial data, corporate actions, probabilities, target prices, or
  actor identities.
- Keep matched, put-through, odd-lot, foreign, proprietary, and active-order concepts distinct.
- Keep issued shares, outstanding shares, treasury shares, weighted-average shares, and diluted
  shares distinct unless evidence proves the required identity.
- Keep record date, ex-date, payment date, effective date, and execution date distinct.
- Keep current descriptive use separate from historical PIT/backtest authority.
- Use `UNKNOWN`, `MISSING`, `CONFLICTING`, `NOT_APPLICABLE`, or equivalent explicit states rather
  than silent assumptions.
- Authority promotion requires explicit bounded evidence and owner approval; acquisition does not.
- Do not add another market-data provider merely to avoid solving DNSE/FHSC/official-source
  contracts unless the owner explicitly changes the source strategy.

## 11. Definition of progress

Stock Lookup progresses when more of the Vietnamese market becomes:

**retained → readable → understood → canonical → usable → analyzable → explainable**.

The goal is not to maximize the number of files, endpoints, metrics, or reports. The goal is to
maximize trustworthy, reusable information that can eventually support fundamental analysis,
Corporate Intelligence, valuation, scenarios, portfolio/risk, leverage, AI research, and human
investment decisions.
