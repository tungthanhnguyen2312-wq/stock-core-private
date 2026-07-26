# Qualified Financial Observation Retention

Runtime sidecar: `data/financial-observations/observations.jsonl` beneath the
configured `STOCK_LOOKUP_RUNTIME_ROOT` (the local Dashboard runtime in the
Phase 14B pilot). It is runtime data, intentionally untracked and outside the
Producer source repository.

Each JSONL row has a deterministic observation ID and identity key; ticker and
issuer, VCI/vnstock method/version/parameters/retrieval time, statement and
frequency/period/header, bilingual raw identity/value, unknown scope/cumulative
basis/currency/scale, schema fingerprint, response hash, qualification state,
and warnings. A repeated identical retrieval is idempotent. Changed values or
schemas receive a new observation ID and are excluded from canonical output if
their active identity conflicts.

Pilot retained 368 observations: HPG 144, PAN 144, VCB 80. Canonical projection
emitted 160 records each for HPG/PAN and 80 for VCB, retaining observation IDs.
All remain non-actionable because statement scope is explicitly unknown; this
does not change Fundamental Quality, FCFF, or Net-Net gating.
