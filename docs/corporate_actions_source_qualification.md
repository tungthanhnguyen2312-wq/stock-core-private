# Dividends and Corporate Actions Source Qualification

Audit date: 2026-07-26. Bounded read-only probes used `vnstock==4.0.4`, public
`Company(source=..., symbol=...).events()` calls, HPG, PAN and VCB.

| Source / method | Observed fields | Qualification | Limits |
|---|---|---|---|
| VCI `Company.events()` | stable non-null `id`, ticker, event code/category, titles, `public_date`, `record_date`, `exright_date`, `payout_date`, `listing_date`, `exercise_ratio`, `value_per_share`, `action_type_vi/en` | VCI provider identity; field-role preservation; cash-dividend per-share observation; title-supported stock-dividend/bonus/rights decimal ratio | 50-row cap, no public pagination/total/order guarantee, no lifecycle/execution/cancellation status, no currency/unit field, no price-adjustment evidence |
| KBS `Company.events()` | empty DataFrame for HPG/PAN/VCB | none; empty is not absence | cannot corroborate VCI or establish history/completeness |

The mapper admits only VCI `DIV` records whose title/name says cash dividend,
and VCI `ISS` records whose title/name says stock dividend, bonus issue, or
rights issue. `value_per_share` remains a source per-share amount with null
currency; `exercise_ratio` remains a provider decimal ratio only when title
text identifies that event type. Issue price, split ratio, payment completion,
and adjusted-price status remain null/unknown.

Representative VCI observations: HPG cash dividend VND-labelled title with
`value_per_share=500`, ex-date 2026-05-11, record date 2026-05-12, payout date
2026-06-03; HPG stock dividend ratio 0.10. PAN cash dividend 3,000 and stock
bonus ratio 0.20. VCB cash dividend 450 and stock bonus ratio 0.1279. Labels in
titles are not promoted to a structured currency field because the API exposes
no currency/unit attribute.
