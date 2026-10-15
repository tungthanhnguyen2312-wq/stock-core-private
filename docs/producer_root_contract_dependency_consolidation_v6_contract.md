# Producer root-contract dependency consolidation V6

Owner milestone: `PRODUCER_ROOT_CONTRACT_DEPENDENCY_AND_IMPLEMENTATION_CONSOLIDATION_V6`.
Exact released base: `2b3dd7a3d5a979dc76cfec24d32662a3d2a56dc7` (V5 PR 154).
Authority effect: NONE. Source ownership and imports only.

## Choice

`official_source_registry` is a leaf admission gate. Live evidence and the
financial panel can use a package owner. Four sealed E1 debt rows and
`official_financial_pdf_page_evidence.py` must keep importing the root name.
Keeping the implementation in the root module and re-exporting it from the
package would leave those package consumers dependent on the root. That
alternative was rejected.

`stocklookup_core/evidence/official_source_registry.py` is the only
implementation. `official_source_registry.py` re-exports the same objects.
Public callables and `RegistryError` keep `__module__ == "official_source_registry"`
so pickle and historical imports resolve. The code filename is the package file.

## Path semantics

`registry_path()` with no argument still returns
`<repository>/config/official_source_registry.json`. The package file anchors
that directory with `Path(__file__).parents[2] / "config"`, which is the same
directory the root module produced with `Path(__file__).with_name("config")`.
An explicit `root` argument is that directory itself, not a nested `config`
directory. The working directory is not an input. `config/official_source_registry.json`
is not modified.

## Consumers

Retargeted to the package owner:

- `stocklookup_core/evidence/official_document_acquisition.py`
- `stocklookup_core/evidence/official_document_discovery.py`
- `stocklookup_core/evidence/official_document_qualification.py`
- `stocklookup_core/evidence/official_document_store.py`
- `stocklookup_core/financial/multi_period_financial_panel.py`

Unchanged root importers include the four sealed E1 rows:

- `stocklookup_core.evidence.hnx_disclosure_feed_parser`
- `stocklookup_core.evidence.hnx_financial_filing_scaleout`
- `stocklookup_core.evidence.official_authority_candidates`
- `stocklookup_core.evidence.official_listing_page_parser`

`admit()` refusal order, approval-instant provenance, host allowlists, document
types, and request-interval policy are unchanged. There is no second admission
authority.

## Measured graph

Against the V5 graph at released main `2b3dd7a3d5a979dc76cfec24d32662a3d2a56dc7`:

| Quantity | Before | After |
| --- | ---: | ---: |
| Root Python files | 277 | 277 |
| Tracked files, including the three new files | 2,637 | 2,640 |
| Implementation modules | 569 | 569 |
| Core-to-root pairs | 106 | 101 |
| Backward pairs | 140 | 135 |
| Raw edge rows | 4,016 | 4,023 |
| Normalized edges, excluding package-initializer targets | 2,612 | 2,613 |
| Root `official_source_registry` fan-in | 19 | 14 |
| Eager / runtime SCCs | 1 / 11 | 1 / 11 |

The five retargeted package-to-root registry edges are gone. Raw rows rise by
seven because the root re-export and the spelled package imports also record
`stocklookup_core` and `stocklookup_core.evidence` initializer edges. The one
new normalized edge is the historical root module importing the canonical owner.
Tracked files rise by the package module, this contract, and the parity test.
