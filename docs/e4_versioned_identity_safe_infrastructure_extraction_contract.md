# E4 versioned identity-safe infrastructure extraction

Owner admission: directive attachment `46b69cf2-8417-48dd-ae0c-839183060ef9`,
2026-10-12. Native milestone `E4_VERSIONED_IDENTITY_SAFE_INFRASTRUCTURE_EXTRACTION`;
baseline main `0061d5f8afe4275ef6cf1dd7ba44930f559d2278` (E2/E3 PR125).
Post-merge Producer CI `38181224017`: four successful jobs. Local design, edits,
tests, checkpoint/local closeout, one feature PR and CI repairs are authorized.
No merge, deployment, Daily, acquisition, production writes, historical rewrites,
source identity activation or authority promotion. No automatic successor.

## Ownership and fixed paths

`evidence/session_paths.py` owns the 49 fixed paths and construction of the event
path from an explicitly supplied directory. The 50-entry legacy function mixes
pure construction with `_latest_official_event_context_dir` discovery. Discovery
is deliberately excluded from the foundation; its full-path API requires the
selection argument, and `fixed_session_artifact_paths` omits that one entry.
No validation, resolution, glob, cache, I/O or directory creation is added. Native,
PureWindowsPath and PurePosixPath retain their supplied flavour, including relative,
drive-relative, UNC, parent/nested and malformed session strings. Historical names
and missing-input exceptions are unchanged on the fixed construction surface.

The Daily Brief reads only fixed entries and now binds this owner. Frozen Level-2,
Canonical post-close and all `cpc.level2` monkeypatch/import surfaces remain intact.
The legacy event selector still executes its original bounded discovery; no new
consumer uses that selector or changes production artifact placement. No Daily
orchestration moves into foundation.

## Bounded JSON and verification

`evidence/bounded_json.py` owns the exact existing canonical bytes, record mapping
digest, pretty record chunks and batched JSON generator. `evidence/artifact_stream.py`
owns sorted-unique bounded parsing, source hashing and streamed content
verification. Sanitization is an explicit caller-supplied function; the foundation
does not import the domain sanitizer or change its NaN-only policy.

Compact encoding uses sorted keys, `ensure_ascii=False`, separators `(',', ':')`,
`allow_nan=False`. Pretty uses indent=2 and the original permissive nonfinite behavior,
native newline translation and final newline. Mixed-key/encoding/type errors retain
their stdlib type and message. Records remain mapping/list; pretty emission and
mapping hash materialize at most one record, while compact batching retains the
original 64-KiB threshold and permits a single token exceeding it. Metadata is bounded
by its field size; this is not a promise of an absolute 64-KiB allocation ceiling.
The object reader retains its 16-MiB character member limit and duplicate/trailing
data failures. Nothing globally consolidates other canonical JSON helpers.

Integrated Decision hashing and Thesis streaming verification bind the new owners;
both retain their artifact contracts and content identities. V1 retention and the
root bounded streamer continue their original compatibility and lazy import cycle.
There is intentional side-by-side implementation at the frozen source boundary.

## Separate identities and activation boundary

V1 feedback `code_digest` hashes eleven labelled normalized-LF source hashes in its
standing order. Its terminal manifests compare input digest and code digest and
verify artifact bytes. Verification receipts separately hash three source modules.
All those source files and the existing E2/E3 frozen-source manifest remain unchanged.
The exact legacy digest is recomputed, never replaced by a hardcoded historical value.
Completed evidence, receipts, manifests and identifiers are neither copied nor edited.

`tools/qualify_e4_infrastructure.py` is an offline read-only candidate consumer. It
executes both implementations on identical synthetic fixtures and emits metadata
to stdout. V2 `e4_infrastructure_source/v2` domain-separates the source digest and
binds the eleven V1 inputs, three foundations, three migrated consumers, package
initializers and qualifier. Its closed source set and labels are explicit in code;
it is a bounded infrastructure identity, not a replacement feedback execution identity.
Missing/unknown source versions fail closed. It rejects execution against a foreign
source tree. The candidate reuse predicate rejects unversioned/V1/unknown metadata,
different code/input identity and missing fields without mutating either record.
It covers source/input matching only: artifact integrity remains an independent
prerequisite. No production writer or completion-manifest adapter calls it.

Output bytes, artifact content hash, source identity, feedback reuse and activation
are separate propositions. Byte parity cannot qualify cross-version reuse. V1 source
digest stays unchanged; V2 is explicitly distinct and is never offered to the V1
reuse pathway. Migration of frozen V1 modules/production feedback to V2 requires a
separate owner decision and its own terminal/receipt integration acceptance. That
activation is intentionally outside this admitted side-by-side development scope.

## Acceptance

Execute original V1 and candidate paths/JSON with identical synthetic fixtures;
cover Unicode, floats/nonfinite, mixed keys, exceptions, records map/list, 65535/6/7,
LF/CRLF, deterministic chunks/hashes, bounded reader failure, actual Brief joins and
Thesis sidecar outputs. Preserve all E0/E1/E2/E3 guards and frozen source hashes;
no baseline refresh, grandfathering or layout relocation change. Report graph edges,
backward/core-to-root edges, exact eager/runtime SCC membership and changed fan-in/out
using the same analyzer/settings before and after. Run hermetic CI selections with
provider import blocking; retained absence is an explicit skip, never invented data.
Local completion does not grant hosted acceptance, merge or production activation.

CI adds the E4 regression file to its existing focused selection and fetches full
history in that job so the accepted V1 Git library blobs are available. Its reviewed
normalized workflow hash is updated in the launcher manifest; Daily launch commands,
targets, Python launcher ASTs and runtime configuration remain unchanged.

[Acceptance record](e4_infrastructure_acceptance.md).
