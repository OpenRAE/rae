# Developer documentation

Hosted reader documentation lives only under [`docs/public/`](public/index.md).
The rest of `docs/` contains developer, design, research, migration, audit, and
working records that remain visible in the repository.

## Work on the repository

- [Development workflow](DEVELOPMENT_WORKFLOW.md)
- [Coding standards](explain/reference/coding-standards.md)
- [Documentation style guide](explain/reference/documentation-style-guide.md)
- [Release process](explain/releasing.md)
- [Architecture decisions](decisions/adrs/README.md)
- [Developer package and artifact architecture](decisions/package-artifacts/README.md)
- [Current design-review follow-ups to historical ADRs](research/language-extensibility/adr-follow-ups.md)

## Inspect working records

- [Decision and preflight notes](decisions/index.md)
- [Research records](research/)
- [Modular participant-control architecture and delivery graph](research/modular-participant-control/index.md)
- [Issue 1198 language extensibility design review](research/language-extensibility/design-review.md)
- [Clarified design intent: open scopes and backend responsibility](research/language-extensibility/design-intent.md)
- [Migration records](migration/README.md)
- [Lessons](lessons/README.md)
- [Commit authorship anomaly](development/authorship-anomaly-2026-07.md)

Files outside `docs/public/` are not copied, included, or indexed by the hosted
Sphinx build.
