# Cross-project Forex idea bank

Status: `NON_AUTHORITATIVE_IDEA_BANK` / `NOT_ROADMAP` / `NOT_BACKLOG` / `NO_AUTO_PROMOTION`

This note records design lessons from a separate Forex research effort. It does
not create a roadmap milestone, a backlog item, or an authority change. Nothing
here starts work. A later owner decision is required before any item becomes a
Stock Lookup milestone.

## Lessons worth keeping as design reference

- Regime and state classification should stay explicit. A setup does not have one universal edge.
- Keep a counter-thesis next to the working thesis.
- Keep feature vectors. Do not collapse RSI, volume, breadth, valuation, and fundamentals into one universal composite score.
- Action is conditional. Separate trigger, confirmation, and invalidation.
- Track outcomes prospectively. Do not backfill a result that was not observed.
- Where the path is qualified, retain MFE and MAE, not only a terminal return.
- Review false negatives: supportive features can exist while policy stays WAIT or AVOID.
- Calibration belongs to a named evidence population. A large sample is not authority.
- Deterministic numerical operators stay separate from AI judgment.
- The human retains capital decision authority.

## Exclusions

- No automatic BUY_SCORE.
- No automatic trade execution.
- No application, PWA, or mobile promotion.
- No Markov, machine-learning, or regime-model authority without evidence.
- No lowering of PIT, RAW_AS_TRADED, or evidence standards.

## Authority

This file has no authority effect. It must not be copied into `queued_next`.
