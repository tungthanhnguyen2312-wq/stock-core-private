# Codex working rules

1. Codex is the implementation executor.
2. Read [STATE.md](STATE.md), [ROADMAP.md](ROADMAP.md), and [DECISIONS.md](DECISIONS.md) before proposing work.
3. One session is one substantial bounded milestone; avoid chains of tiny audit/design/shadow prompts.
4. A normal milestone inspects, patches, runs focused tests, performs one real/frozen validation when needed, commits, and pushes.
5. Do not reopen a passed gate without regression evidence.
6. Never treat metadata, ordering, missing data, or fallback behavior as investment signals.
7. Price basis, volume basis, and current shares are persistent blockers until explicitly qualified.
8. Do not enable valuation, ranking, recommendations, sizing, or backtesting from unqualified inputs.
8a. Undocumented is not unusable. Qualify evidence on the ladder in
    `evidence_qualification_tiers.py` and record the tier: an `empirically_deduced` verdict
    keeps descriptive and provider-scoped technical use open while liquidity, execution and
    point-in-time use stay closed. Only `documented_verified` may speak for a source.
8b. An empirical verdict carries its scope. State the tested tickers, windows and fields,
    keep `provider_methodology = unknown` unless a first-party source says otherwise, and
    never quote a verdict outside the windows that produced it.
8c. A verdict belongs to one provider. It never transfers to another provider and never
    lands on a field that does not say whose number it is. A *magnitude* anchor borrowed
    from another series is the one exception, and it carries nothing else — not composition,
    not adjustment behaviour, not authority.
8d. To test whether a source rewrites history at an event, you need a snapshot retained
    **before** that event. Two snapshots taken after it measure post-event stability only,
    and no amount of elapsed time between them changes that. Never propose re-requesting an
    already-post-event window as a substitute; check the pair with
    `kbs_empirical_basis.classify_snapshot_pair` before claiming an event-time result.
8e. A derived quantity constrains only what its algebra constrains. A ratio identity fixes
    a ratio; naming the absolute terms needs a separately identified anchor, and without one
    the answer is `unresolved`, not the plausible-looking option.
8f. A partial aggregate must say so in its own output. An operation claiming a whole window
    needs `coverage_state = complete`; otherwise rename and restructure it as
    `observed_rows_only` with its covered and excluded sessions. Never silently drop missing
    rows and present the result as complete, and never impute a missing observation.
8g. Keep the kinds of "no value" apart: field omitted, present-null, a real zero, malformed,
    and a missing row are five different facts about a source. A zero is an observation.
    Our own pipeline dropping a field is not evidence that the provider omitted it.
8h. A correlation is not a mechanism, however clean. Record it as an observed association
    with `causal_explanation = unknown` and scope it to the windows that produced it.
8i. Trace a data path before writing a contract about it. Registers of consumers, fields and
    capabilities must name things that exist and actually read what they claim to read; a
    plausible-sounding identifier is not evidence that a consumer exists. When a trace finds
    nothing, record the absence as data rather than leaving it inferred from silence.
8j. Cross-repository verdicts pass through, they do not get recomputed. The downstream side
    copies the counts, may narrow a verdict, may never widen one, and may never drop a
    required warning. Pin shared warning text to one source with a fingerprint both sides
    assert.
9. Write detailed diagnostics locally; keep final chat output compact.
10. Do not run full suites unless a real cross-cutting source regression justifies it.
11. Do not publish or deploy unless explicitly requested.
