# Contribution quick start

Before contributing, read [CONTRIBUTING.md](../CONTRIBUTING.md), [SECURITY.md](../SECURITY.md), and the repository guardrails in [AGENTS.md](../AGENTS.md).

A useful contribution should be bounded, reproducible, and evidence-aware. Good starting points include:

- improving tests for an existing contract;
- fixing a reproducible bug with a minimal regression case;
- improving portable developer documentation;
- strengthening validation, provenance, or fail-closed behavior without widening source authority; or
- proposing a clearly scoped feature with explicit non-goals.

Do not include credentials, runtime databases, backups, generated artifacts, or machine-specific paths. If a proposed change depends on market-data semantics or point-in-time behavior that are not yet qualified, preserve the unknown state rather than guessing.
