# Technical participation relationship view

`technical_participation_relationship_view/v1`, implemented in
`technical_relationship_view.py`, is a compact deterministic V1/V2 semantic bridge.
One view represents one ticker, session and D/W/M frame. It carries technical
version, context/frame/input/canonical-bar identities, bounded source-bar identity
pointers, source, availability, basis/CA/volume/PIT/temporal fitness, clean concepts,
unknown reasons and conflicts. It never duplicates the full technical payload.
Every view is non-voting and `is_actionable=false`.

The dispatcher verifies the original technical context before building views.
The view verifier checks its content identity and alias, scope, closed vocabulary
and canonical/common-cause evidence keys. Unknown versions and unknown consumer
vocabulary fail explicitly.

## Concepts

Breakout relation describes actual price distance from the retained pivot using
the frozen owner's near band and five-percent extension threshold:

- ABOVE_PIVOT_WITHIN_EXTENDED_THRESHOLD
- ABOVE_PIVOT_BEYOND_EXTENDED_THRESHOLD
- AT_OR_BELOW_PIVOT_WITHIN_NEAR_BAND
- BELOW_PIVOT_BEYOND_NEAR_BAND
- UNKNOWN

`failed_breakout` is TRUE/FALSE/UNKNOWN; failure requires an actual prior close
above pivot followed by a close below the near band. `pivot_test` distinguishes
testing after a prior close above, testing without that prior close, not testing
and unknown. Neither a generic pivot test nor a legacy label alone proves a
retest or extension.

The remaining clean concepts are bounded range consolidation (FORMING,
ESTABLISHED, EXITED_BY_CLOSE, FAILED_BREAKOUT_CONTEXT, UNKNOWN), trend reading
(UP, DOWN, NO_CLEAN_AGREEMENT, UNKNOWN), exact-price swing relation and setup
state. Range algorithm is `BOUNDED_CLOSE_RANGE_DURATION`. The
[Technical V2 contract](contextual_technical_features_v2_contract.md) defines the
complete swing vocabulary and R0–R11 setup precedence.

`native_volume_reference` includes the exact technical primitive's ratio status,
relative median/mean values, current native volume and distribution, lookback
fitness and feature pointer. Relative states are EXPANSION, CONTRACTION, STABLE,
UNDEFINED_ZERO_REFERENCE and UNKNOWN. Its window is
`LAST_20_INCLUDING_CURRENT`, which differs from the flow producer's prior twenty
observations for each trajectory point.

## Version semantics and temporality

For V1, derive clean swings from actual retained confirmed swing prices and setup
from actual retained structure/events, trend and bounded range. Do not consume
V1 `repair_context`, participation context, breakout/retest volume labels or
supporting/contradicting lists. V1 direction RANGE maps to NO_CLEAN_AGREEMENT.
Old owner reversal labels are not evidence of new descriptive reversal.

V1 W/M period distance uses canonical civil arithmetic from the actual last
observation. Newer-period completeness is `UNKNOWN_FROM_V1` with null counts,
because it was not retained. V2 copies explicit clean concepts and actual temporal
metadata. V1-derived neutral concepts are POST_T0_ENRICHED; V2 knowledge requires
the exact technical context identity to be retained in a genuine future T0.

## Correlated evidence

`canonical_evidence_key` binds ticker/session/timeframe/canonical source bar/concept.
`common_cause_key` binds ticker/timeframe/cause family. Families are
CLOSE_SERIES_STRUCTURE, OHLC_RANGE, NATIVE_VOLUME_SERIES and FOREIGN_VALUE_SERIES.
Keys deliberately exclude technical version, allowing equivalent evidence to be
deduplicated across versions. Native technical and flow references share the same
canonical key. Derived trajectories have distinct concept keys and the same native
volume common cause. These keys provide no scoring, ranking or conflict vote.

`VOCABULARY_MANIFEST` exposes every bridge vocabulary; the flow consumer explicitly
maps every value and rejects future unmapped values. The
[combined acceptance](internal/TECHNICAL_VOLUME_FLOW_V2_MIGRATION_ACCEPTANCE.json)
records full retained view coverage and explicit V1-to-V2 compatibility. Historical
V1 contexts and snapshots remain readable through their original verifiers.
