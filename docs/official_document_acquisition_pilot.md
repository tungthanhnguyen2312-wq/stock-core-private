# Official corporate document acquisition pilot

`official_document_acquisition.py` is a Producer-only, bounded intake contract for HPG, VNM, VCB, SSI, and PAN. It accepts an explicit caller-supplied finite URL list for FY2024/FY2025 only; it does not crawl, poll, infer URLs, or write a runtime root.

Each retained version records canonical URL, issuer authority, document class, period, publication/observation dates, HTTP metadata, SHA-256, and immutable hash-addressed relative path. Repeated URL/hash pairs are skipped. Changed bytes append a new record and can name a previous `supersedes_document_id`; no prior byte or manifest record is replaced.
For governed, non-production retention, the canonical caller destination is `operations-review/governed-official-evidence-v1/` relative to the Producer repository. It is deliberately untracked, outside every runtime/database root, and is the only location where this pilot may retain downloaded PDF binaries. Its deterministic manifest and citation handoff are operational evidence, not Git-binary inputs.

The initial classes are audited annual financial statements, annual reports, AGM documents/resolutions, corporate-action notices, and amendment/supersession notices. Failure states are `unsupported_request`, `inaccessible`, `malformed`, `unsupported_document`, `needs_ocr`, and `malformed_document`; the coverage matrix marks no retained class as `missing`.

The bounded period allowlist includes 2026 so current-year HPG/VNM corporate-action
completion notices can be retained without weakening the ticker or document-class
allowlists. Retention alone never qualifies a share transition; citation, lifecycle,
effective-date, share-identity, and hash validation remain separate promotion gates.

Retained PDFs are passed only to the cited-retrieval intake handoff. Direct page citation metadata remains mandatory before deterministic retrieval can expose any passage, and acquisition never creates canonical financial observations. OCR is deliberately not implemented; textless PDFs report `needs_ocr`.

Existing source patterns: issuer IR PDFs for HPG and VNM, issuer IR / disclosure documents for VCB, and VSDC notice pages for corporate actions. A VCB historic third-party mirror is retained as weaker prior evidence and is not elevated by this acquisition contract. SSI and PAN require caller-supplied explicit official URLs before any bytes can be acquired.
