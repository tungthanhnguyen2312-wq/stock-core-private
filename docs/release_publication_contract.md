# Release publication contract

How one verified exact-session artifact set reaches the Dashboard that people actually
read, and what the publisher refuses to do on the way there.

See [`exact_session_bundle_contract.md`](exact_session_bundle_contract.md) for how the
artifact set is produced and proved, and
[`statement_taxonomy_sidecar_contract.md`](statement_taxonomy_sidecar_contract.md) for the
sidecar's authority level. This document only covers publication.

## The serving topology

| | |
|---|---|
| Source (runtime root) | `dashboard-runtime` — where the export writes, and where local evidence, `vn_stock.db` and the untracked data stores live. Routinely on a feature branch with unrelated generated-artifact drift. |
| Destination (served checkout) | `C:\Projects\StockLookup\market-dashboard` — the only live Dashboard publication checkout: a **normal clone** of `tungthanhnguyen2312-wq/market-dashboard` on **`main`**. |
| Authoritative branch | `main`. GitHub Pages is configured `source.branch = main`, `build_type = workflow`. |
| Serving pipeline | push to `main` → `.github/workflows/dashboard-ci.yml` (*Dashboard CI*) → on success `deploy-pages.yml` (`workflow_run`) checks out the validated SHA and deploys the whole repo root. |
| Served origin | <https://tungthanhnguyen2312-wq.github.io/market-dashboard/> |

Live release refuses any other web checkout, including `worktrees/market-dashboard-main`,
`publish/market-dashboard-main`, and `dashboard-runtime`. `dashboard-runtime` is DATA/RUNTIME
only. Publisher authority is only:

- `stock-core-private/tools/release_orchestrator.py`
- `stock-core-private/publish_dashboard.py`
- `stock-core-private/tools/publish_release.py`

A Dashboard checkout is a **target**, never a publisher. `web_dir/publish_dashboard.py` is
not live authority. Validation, `git add`, commit, and push must use the same canonical checkout.

## Current Workspace product projection

`data/investment_decision_workspace.json` is the required current Dashboard product asset. It is
not a Dashboard-generated report and is not inferred from `analysis_latest.json` or candle files.
The Producer publisher accepts `--workspace-projection-source <path>` (otherwise the canonical
runtime path), validates `investment_decision_workspace_dashboard_projection/v1`, a matching
market session, a non-empty producer identity, card denominator equality, and the explicit
zero-silent-drop assertion, then copies the verified bytes atomically into the served checkout.
The asset is included in the served-file allowlist. A missing, malformed, stale, or incoherent
projection fails publication before any public write. Candle and sector sidecars remain optional
presentation data and cannot replace this current product contract.

## Workspace topology invariant

The canonical runtime root is `C:\Projects\StockLookup\dashboard-runtime`; the canonical
Dashboard checkout is `C:\Projects\StockLookup\market-dashboard`; and the only live
publication entrypoint is `stock-core-private/tools/release_orchestrator.py`. The runtime and
checkout must remain distinct. The Producer publisher paths fail closed if a real invocation
names another runtime or served checkout. `dashboard-runtime` may retain local runtime data and
legacy Git metadata, but is never a source/publish checkout. See
[`workspace_topology_convergence.md`](workspace_topology_convergence.md).

Permanent state vocabulary:

- A successful `git push` is **`GITHUB_SOURCE_UPDATED`**.
- **`PUBLISHED`** only after (1) local release validation PASS, (2) GitHub Dashboard CI PASS
  on the same SHA, (3) Deploy Pages PASS on the same SHA, and (4) cache-busted public
  session verification PASS.

`feature/horizontal-top-navigation` is a feature branch. It is not a deployment branch, it
is not built by Pages, and publishing onto it publishes to nobody.

Publication is therefore **both** a filesystem promotion (runtime root → served checkout)
and a git operation (commit + push to `main`). The frontend fetches
`analysis_bundle.json` from the site root at runtime; the other three artifacts are
published so the release can be verified from what was served.

## The release allowlist

```
analysis_bundle.json
bundle_manifest.json
focus_extract.json
statement_taxonomy_sidecar.json
```

Static in `tools/publish_release.py::RELEASE_ALLOWLIST`, and cross-checked against the
manifest's own `trusted_subset.expected_artifact_filenames`. Neither side can widen the
release alone: a manifest that declares a fifth trusted artifact is rejected
(`unexpected_release_file`), and an allowlisted file the manifest does not declare is
rejected (`release_set_incomplete`).

Nothing else is published by this tool. In particular it never publishes
`screen_snapshot.csv`, `market_breadth.csv`, `analysis_latest.json`, `data/*.js`,
`data/*.json` or any other generated artifact, whether or not they are modified — the
publisher never enumerates the source directory, so an unrelated modified file has no path
into a release.

`publish_dashboard.py` still owns the *dashboard data layer* rebuild (screener fallback,
`build_info`, asset cache-busting). It derives its git whitelist by scanning the HTML/JS
for referenced files, which is right for that job and wrong for a release: every already
dirty generated artifact falls inside that whitelist. The two are separate on purpose.

## Atomic full-session release (`all`)

`release_orchestrator.py all --live` is one logical publication and therefore produces
either no Dashboard commit/push (when no files change) or **exactly one Dashboard commit
and one push**. It must never expose a trusted-subset-only intermediate commit.

The orchestrator first invokes `publish_release.py --live --no-git`. This retains the
static manifest-bounded release set, staging hashes, exact-session identity, Consumer
validation, undeclared-artifact rejection, and rollback evidence, but deliberately defers
Git publication. It then runs the existing frontend builder and the existing
`publish_dashboard.py --live --include-trusted-subset`. The latter adds every member of
`trusted_subset_contract.TRUSTED_SUBSET_ARTIFACTS` explicitly to its final whitelist,
re-verifies the complete subset against `bundle_manifest.json`, validates the whole-market
session surfaces and release smoke tests, and owns the sole `git add` / commit / push.

Before mutation, `all --live` fetches the canonical branch and requires `HEAD ==
origin/main`. The final Dashboard publisher fetches again and fails if it is ahead or
behind; it never pulls or merges during this transaction. If a child fails before the
final commit, the orchestrator restores the captured bytes for the original tracked
Dashboard tree and clears only its own index state. Ignored operator files (including the
local Tailwind binary) and unrelated untracked files are never enumerated or deleted.

`trusted-ai`, `whole-market`, and `cockpit` remain independently invokable groups with
their existing publication boundaries. The one-commit composition rule applies only to
`all`.

## `build_info.json` commit field

`data/build_info.json.git_commit` is the **pre-publication source HEAD** used when the
build signature and cache token are computed, not the final publication SHA. Its
`git_commit_semantics` field is fixed to `pre_publication_source_head`. Embedding the
final SHA would create a circular, nondeterministic commit: changing the file to name the
new commit would itself change that commit. The actual publication SHA is the Dashboard
Git commit reported after the one final push.

## What must hold before anything is promoted

1. **Allowlist ↔ manifest agreement** — as above.
2. **Every allowlisted file present** in the source (`required_artifact_missing`).
3. **Hash verification** — each staged artifact's sha256 equals the manifest's
   `trusted_subset.required_artifacts` entry (`manifest_hash_mismatch`).
   `bundle_manifest.json` cannot hash itself; it is the document the others are checked
   against.
4. **One session** — `analysis_bundle.reference_session_date`,
   `focus_extract.reference_session_date`, `statement_taxonomy_sidecar.session_identity`
   and `trusted_subset.session_identity` are the same value, and the manifest's declared
   `statement_taxonomy_sidecar.records_fingerprint` matches the sidecar on disk
   (`session_mismatch`).
5. **The Consumer's own validator** — `publish_release.py` imports
   `ai-core-private/builders/build_ticker_context.verify_exact_session_bundle` and runs it
   over the *staging directory*, rather than reimplementing the rules. A publisher carrying
   its own copy of the exact-session rules drifts from the validator that actually gates the
   Consumer, and then a release passes here and is rejected downstream.
6. **A clean destination index** — an index already holding someone else's work would end
   up inside the release commit no matter how narrow the publisher's own `git add` is
   (`git_index_not_clean`).

## How the promotion is atomic

* **Staging.** Every allowlisted file is copied by exact name into a fresh temporary
  directory and hash-verified there. Nothing has touched the destination yet.
* **Rollback point.** The destination's current copy of each allowlisted file is copied to
  `<runtime-root>/reports/release_rollback/<UTC timestamp>/`, each copy is re-hashed against
  the live file, and a `rollback_manifest.json` records the previous hashes and which files
  did not exist before this release.
* **Promotion.** `os.replace` per file, from staging into the destination. No content is
  generated during this step, so each file appears whole or not at all.
* **Post-promotion verification.** The destination is re-hashed and must equal the incoming
  set; the set of *unrelated* modified paths in the destination worktree must be identical
  before and after (`unrelated_drift_disturbed`).
* **Commit.** `git add -- <the four exact paths>`, then an assertion that the staged set is
  a subset of the allowlist. No `git add -A`, no `git add .`, no pathspec glob. The staged
  blobs are then compared byte-for-byte against the verified release
  (`git_content_normalization`) — see *End-of-line translation* below.
* **Push and remote verification.** `git push origin HEAD:<branch>`, then `ls-remote` must
  report the pushed SHA.
* **Served verification.** With `--verify-live-url`, each artifact is fetched from the
  serving origin and its sha256 compared to the incoming release, retrying until the Pages
  deployment converges or the timeout expires.

**For the reader, the atomic unit is the commit.** Pages builds one deployment from one
commit and swaps it in whole, so a reader sees the previous release or this one, never a
mixture. The filesystem step is atomic per file and fully verified before the commit
exists, which is what makes that guarantee meaningful.

Any failure at any point after the rollback point restores the complete previous artifact
set, re-verifies the restored hashes, and exits non-zero. A partial release is never left
active.

Republishing an unchanged release is a no-op: no file is rewritten (mtimes are untouched),
no rollback point is taken, and no commit is created if the release is already committed.

## End-of-line translation

`market-dashboard` is checked out with `core.autocrlf=true`. Without an override, git
rewrites every LF to CRLF on checkout, so a Windows working tree's bytes disagree with the
manifest that describes them and every hash check fails on a fresh clone. The four release
artifacts are pinned `-text` in the Dashboard repo's `.gitattributes`, and the publisher
verifies the staged blob against the verified bytes before committing, so this cannot be
reintroduced silently.

## The one supported live-publish command

This publisher (`tools/publish_release.py`) is never invoked directly by an operator. It is
reached exactly two ways, and only one of them may commit or push:

```
python stock-core-private/tools/release_orchestrator.py trusted-ai \
    [--generate] [--expected-session YYYY-MM-DD] \
    [--live] [--verify-live-url https://tungthanhnguyen2312-wq.github.io/market-dashboard]
```

**`tools/release_orchestrator.py` is the single supported live-publish authority** — for this
trusted-ai group, for the whole-market group (`whole-market`, via `publish_dashboard.py`), or
both (`all`). It holds a single-instance lock and validates the Dashboard checkout's git state
(HEAD vs. upstream, no pre-existing staged files) before calling this publisher. `--generate`
has it call `tools/operate_stocklookup.py --execute` first, to rebuild and validate this
release's trusted-ai artifacts from data already in the runtime. `--verify-live-url` is passed
through unchanged to this publisher's own `--live` re-fetch-and-compare check.

```
python stock-core-private/tools/operate_stocklookup.py \
    --runtime-root C:\Projects\StockLookup\dashboard-runtime \
    --execute \
    --publish --web-root C:\Projects\StockLookup\market-dashboard
```

`tools/operate_stocklookup.py` composes the full generate-verify-Consumer-validate chain for
the trusted-ai artifact set and remains fully supported for that role — including this
non-mutating `--publish` form, which runs the publisher in **its own dry run** to preview the
release as part of validating the chain that produced it. `--publish` requires `--web-root`,
and `--web-root` may not be the runtime root: publishing into the runtime root is exactly the
defect this argument exists to stop.

**Its own `--live` flag is retired**: passing it exits 2 with a message pointing at
`release_orchestrator.py`, so exactly one command in the repository can ever commit or push a
release. Its `post_publish_smoke` gate's live-only block (re-hashing the served checkout
against the runtime root from a second, independent process) therefore no longer runs on a
real publish either — accepted as intentionally redundant with what this publisher already
does internally before this gate ever existed (`git ls-remote` verification after push, plus
the post-`os.replace` re-hash described below), not a capability silently dropped. Use
`--verify-live-url` on `release_orchestrator.py` for the one piece of independent, live
verification (an HTTP re-fetch from the actual serving origin) that check offered and this
publisher does not already do on its own. See `docs/DECISIONS.md`'s 2026-08-08 "Publish
Orchestrator Authority Reconciliation" entry for the full reasoning, and
`operations-review/local_runbook.md` for the preflight → build → validate → publish command
sequence.

Without `--live`, both entry points run this publisher's own dry run and report the full plan
— source, destination, exact files, current and incoming hashes, excluded modified paths,
rollback source — while writing nothing.
