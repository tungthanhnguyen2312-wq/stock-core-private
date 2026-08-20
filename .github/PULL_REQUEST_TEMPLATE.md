## Summary

Describe the change and the problem it solves.

## Scope

- What is intentionally changed?
- What is explicitly out of scope?

## Validation

List the focused tests, checks, or reproducible evidence used to validate the change.

## Data / authority impact

If this change touches market data, source semantics, point-in-time behavior, or analytical eligibility, state the existing authority it relies on and confirm that the change does not silently widen it. Use `UNKNOWN` / fail-closed behavior where evidence is insufficient.

## Safety checklist

- [ ] No credentials, runtime databases, backups, or generated artifacts are included.
- [ ] Relevant tests/checks pass.
- [ ] `git diff --check` passes.
- [ ] Documentation is updated only where needed.
- [ ] Any authority or production-impacting change has explicit maintainer approval.
