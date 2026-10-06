# Human/AI decision evidence packet

Milestone `HUMAN_AI_DECISION_EVIDENCE_PACKET_CONVERGENCE_V2`.

Authority effect: none. No buy score, no probability, no target price, and no
delegated capital decision.

Contract: `human_ai_decision_evidence_packet/v2` in
`human_ai_decision_evidence_packet.py`.

The packet points at an existing `current_research_decision_packet` identity when
the caller supplies one. It does not copy a universe of decision rows and it does
not replace that packet.

## Sections

`market`, `stock`, `tactical`, `comparison`, `uncertainty`, `history`,
`counter_thesis`.

An absent section is `MISSING`. A present field is a fact, or a claim class from
`current_valuation_denominator_integrity` when the caller supplies a claim spec.
Missing market context does not erase a present stock field.

## Boundaries

- Python owns measurements, identities, analogue eligibility, and claim class.
- AI owns only the narration slot. Its authority is `NARRATION_ONLY`.
- Human owns the capital decision. A supplied decision value is discarded.
  The slot stays `NOT_DELEGATED`.
- The feature vector is a map of named measurements. A one-key `value` scalar
  and any buy score, recommendation, probability, target price, size, or
  composite score are rejected.
- Historical analogues keep caller order. A usable analogue must disclose
  matching method, evidence tier, sample size, regime similarity, and missing
  dimensions. Incomplete disclosure is ineligible. The packet does not sort
  analogues by outcome.

## CLI

No read-only `stocklookup packet` command was added. The packet contract does
not depend on a command surface.

## Acceptance shape

The same builder represents the nine focus labels as situations: strong
fundamentals with a weak technical field, a non-recurring earnings flag, a
capital-intensive catalyst, securities and finance-company valuation that is
not comparable, a share-basis mismatch, dilution without an ex-date, a
provision flag, and an uptrend label. Those fixtures are not live extractions
from the integrated-decision body, and they are not issuer-specific branches.
