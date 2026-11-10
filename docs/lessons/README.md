# Integration lessons

Use this how-to guide to record a dated integration finding.
A finding describes what happened when a backend used RAES contracts.
It is reference evidence, not a new architecture decision.
Use the [ADR index](../decisions/adrs/README.md) for decisions and their status.
This directory currently contains this guide; it has no dated finding entries.

RAES owns its portable contracts and reference implementation.
The integrating backend owns its native effects and backend-specific evidence.
APTL was the first consumer considered by this convention.
Use an explicit repository link for any corresponding backend record.

## When to write an entry

Write an entry when integration reveals a contract, profile, fixture, runtime, or coordination problem.
This includes these cases:

- A contract is ambiguous, incomplete, or promises a check that conformance does not enforce.
  Examples include `backend-manifest-v2`, runtime envelopes, plan contracts, and snapshot models.
- A profile requires too much or too little from a backend.
  Profiles include `provisioning-only`, `orchestration-capable`, `orchestration-evaluation`, and `full-remote-control-plane`.
- A fixture accepts a nonconformant backend or rejects a conformant backend.
- A reference implementation assumption does not hold for the integrating backend.
  Relevant packages include `raes_processor`, `raes_backend_stubs`, and `raes_conformance`.
- `RuntimeTarget` or `RuntimeManager` needs an API change for the backend's lifecycle, capabilities, or failure modes.
- Coordination exposes a problem with names, schema versions, dependency pins, or release cadence.

Record the expected result, observed result, source revision, and evidence limits.
Keep routine implementation details in their delivery issue.
A later correction does not replace the original observation.

## Convention

Create one Markdown file per finding, named `YYYY-MM-DD-<short-slug>.md`.
Use a lowercase noun phrase with hyphens for the slug.

Each entry's frontmatter:

```markdown
---
date: 2026-05-19
side: RAES | APTL | both
sibling_entry: <link to the matching entry in the sibling repo, if any>
follow_ups:
  - <repo>#<issue> — one-line description
adr_impact:
  - ADR-NNN — amendment / supersede / new ADR
contract_impact:
  - backend-manifest-v2 / runtime-snapshot-v1 / etc. — what changed or
    needs to change
profile_impact:
  - provisioning-only / orchestration-capable / etc. — capability profile
    affected, if any
---
```

Body sections (use the ones that apply, omit the rest):

- **Context** — what the backend was trying to do.
- **What we expected** — the contract surface's apparent promise, the ADR's
  claim, or the conformance suite's assumption going in.
- **What we found** — the actual behavior or shape from the integrating
  backend.
- **Decision** — what landed in the current PR. Use one of: `fix-in-raes`,
  `fix-in-backend`, `cross-repo-coordination`, `accept`, `escalate`. Do
  not use `defer` — record a `follow_ups` issue instead.
- **Why this side** — explain why the selected repository owns the correction.
  Prefer a correction to the portable contract when the evidence shows a contract defect.
  Explain any evidence that changes this choice.
- **Follow-ups** — issues opened on each side, with cross-references.

## Cross-repo symmetry

Use `sibling_entry` to link corresponding findings when the other repository has one.
A finding can apply to only one repository.
Do not invent a matching record.
Keep each repository's observation and corrective action distinct.

<a id="why-not-an-adr"></a>

## Decision records

ADRs explain decisions and their consequences.
Lessons preserve observations from integration.
A finding can lead to an amendment or a new ADR.
Keep the observation as a dated reference after that decision changes.

<a id="why-not-issue-threads"></a>

## Issue threads

An issue tracks corrective work and discussion.
A lesson keeps the finding beside the code at its source revision.
Link the delivery issues and their results from the finding.

<a id="relationship-to-the-reference-backend"></a>

## Backend ownership

The historical convention names `raes_backend_stubs` as the reference Python backend.
Use [ADR-115](../decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md) for the current concrete-backend ownership decision.
Record portable contract findings on the RAES side.
Record backend-specific adaptation and native-effect findings in the backend repository.
Cross-link the records when both apply.
