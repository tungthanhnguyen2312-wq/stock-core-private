# Source integrity regression baseline — 2026-10-11

Release: PR120 HEAD `dddadbf40853a8655f5ac0fa72ae44aaa82f4316`, merged by
the Head Lead at `498b02dd8471078a9cd627eb75241a4ed2da0de5`.
Four exact-commit post-merge CI jobs passed (run 38111216670).
Native closeout `78d3fb994b3e05310ac138b8be235cb108da2698` required a
docs reading-budget correction; no application code changed in either closeout commit.

`tests/test_official_financial_source_integrity.py` executes actual period/assurance
recognizers, fact qualifier, citation loader and ingress writer with synthetic fixtures
and temporary output paths. Baseline on `78d3fb994b3e05310ac138b8be235cb108da2698`:
**13 failed, 6 passed**. These failures are intentionally retained as pre-fix proof.
This checkpoint is incomplete implementation, not a release candidate.

Reproduced failures: two Q3 headers with annual comparative references; five incidental
or negative assurance phrases; bare audited claim; metadata-blocked extraction admitted;
unverified refresh-shaped citation admitted; conflicting citations selected by row order;
empty ingress erased prior overlay; invalid ingress replaced prior overlay.
Passing controls include clean FY2025/H1/Q2 period identity, absent reviewed evidence
rejection and read-only retained overlay shape/binding inventory.

The retained overlay has 27 rows and nine document hashes. Its SHA-256 remains
`a1f057017a9309f5c5a2a1a9ec53c3746500f9355bf45642e039ebf2608e33ff`.
Row/envelope binding is not original PDF verification. No original PDF was reopened by
this regression suite; historical contamination remains UNKNOWN. Do not rewrite history.
Prior bounded reconciliation and completed independent Claude/Grok reports are retained;
do not restart their experiments or infer a complete network-to-Daily exploit.

Next: implement a shared admission boundary using existing document metadata, retained
source qualification and assurance owners; bind the whole publication and consumer path.
Then extend adversarial proof/time/source tests and validate positive source controls,
financial/valuation/packet parity, native checks and four exact-HEAD hosted jobs.
No production refresh/Daily, Q3 authority, new source activation, or second writer.
