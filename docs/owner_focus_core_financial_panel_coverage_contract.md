# Owner-Focus Core Financial Panel Coverage Contract

`owner_focus_core_financial_panel_coverage/v1` is a deterministic retained-evidence coverage artifact for exactly the governed owner-focus sequence: SSI, HPG, PAN, EVF, VNM, FPT, PVD, NVL, POW, PNJ. It consumes the current P3-F13 official panel, retained PDF corpus inventory, existing sector taxonomy, and the existing provider-research envelope. It does not acquire evidence, run OCR, alter a database/dashboard, or promote provider evidence.

The corporate panel contains only existing corporate canonical identities. SSI uses the existing securities panel. EVF is a finance-company boundary: its taxonomy is schema-supported but not real-data validated, so every core metric is explicitly `SECTOR_CONTRACT_INCOMPLETE`; it never receives the corporate panel.

Metric status separates official-qualified current/historical facts from retained-native parser gaps, image-only gaps, metadata gaps, missing documents, provider-only evidence, non-applicability, and incomplete sector contracts. Temporal readiness accepts only compatible annual facts with matching scope/currency/unit: one current level, two consecutive annual periods for YoY, and three consecutive annual periods for trend. Interim periods remain visible and are never mixed into annual readiness.

Evidence priority is lexicographic and deterministic: `P0_CURRENT_CORE_METRIC_MISSING`, `P1_CONSECUTIVE_PERIOD_GAP`, `P2_VALUATION_INPUT_BLOCKED`, `P3_CASH_FLOW_QUALITY_GAP`, `P4_SECONDARY_CORE_METRIC`, then `P5_SECTOR_CONTRACT_INCOMPLETE`; ties use owner-focus order then metric ID. This is an evidence-work queue, not an investment score, ranking, recommendation, target, probability, or sizing output.
