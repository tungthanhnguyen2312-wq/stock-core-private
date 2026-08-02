# Point-in-time share-transition bridge

`share_transition_bridge.resolve_share_transition` consumes only qualified,
hash- and citation-bearing common-outstanding share identities. Share-changing
events require direct completion evidence, an effective date, and a directly
reported resulting share count. Ratios are retained as lineage but are never
used alone to manufacture an outstanding-share identity.
Both opening and resulting identities must use share units and issuer scope.

The resolver separates `latest_qualified_historical_shares_outstanding` from
`current_shares`. A current identity is emitted only when explicit evidence
coverage reaches the requested target date and no conflicting, incomplete, or
unsupported event exists. Cash dividends cannot alter shares. Issued shares,
listed shares, and registered shares cannot substitute for common outstanding
shares when treasury treatment is unknown. Market-value readiness is always
false in this contract; price qualification is independent.
