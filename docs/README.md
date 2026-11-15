# Developer documentation

Hosted reader documentation lives only under [`docs/public/`](public/index.md).
The rest of `docs/` contains developer, design, research, migration, audit, and
working records that remain visible in the repository.

To use RAES, complete the [quickstart](public/quickstart.md). To explore
research questions, read the [research context](public/research.md). To cite
RAES, use the [citation guide](public/citation.md).

## Find your way around the repository

- [`docs/public/`](public/index.md) for hosted reader documentation;
- this index for developer and working records;
- [`specs/`](../specs/) for normative specifications;
- [`contracts/`](../contracts/) for published schemas and fixtures;
- [`examples/`](../examples/) for authored scenarios and reusable patterns;
- [`implementations/python/`](../implementations/python/) for the reference
  implementation.

[CONTRIBUTING.md](../CONTRIBUTING.md) covers checkout setup, local checks, and
pull requests.

## Work on the repository

These pages help you do a task:

- [Development workflow](DEVELOPMENT_WORKFLOW.md)
- [Repository design tools](develop/ground-control-design-checks.md)
- [Merge queue settings](develop/merge-queue.md)
- [Development container](explain/development-container.md)
- [Release process](explain/releasing.md)
- [Revised control migration](migration/revised-control.md)

## Look up repository rules

These pages give exact facts:

- [Coding standards](explain/reference/coding-standards.md)
- [Documentation style guide](explain/reference/documentation-style-guide.md)
- [Current control semantics and support](explain/reference/revised-control-semantics.md)
- [Executable control examples](examples/revised-control.md)

## Understand the design

These pages give reasons and relationships:

- [Architecture decisions](decisions/adrs/README.md)
- [Developer package and artifact architecture](decisions/package-artifacts/README.md)
- [Current design-review follow-ups to historical ADRs](research/language-extensibility/adr-follow-ups.md)

## Inspect working records

- [Decision and preflight notes](decisions/index.md)
- [Research records and current questions](research/index.md)
- [Modular participant-control architecture and delivery graph](research/modular-participant-control/index.md)
- [Issue 1198 language extensibility design review](research/language-extensibility/design-review.md)
- [Issue 215 participant identity and actor/target audit](research/participant-identity/audit.md)
- [Clarified design intent: open scopes and backend responsibility](research/language-extensibility/design-intent.md)
- [Migration records](migration/README.md)
- [Requirement reference](requirements/README.md)
- [Governance records](governance/README.md)
- [Asset inventory methodology and evidence](raes/inventory/index.md)
- [Formal specification introduction](specs/formal.md)
- [Lessons](lessons/README.md)
- [Commit authorship anomaly](development/authorship-anomaly-2026-07.md)

Files outside `docs/public/` are not copied, included, or indexed by the hosted
Sphinx build.
