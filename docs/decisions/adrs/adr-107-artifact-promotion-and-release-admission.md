# ADR-107: Artifact Promotion and Release Admission

## Status

accepted

Accepted with ADR-106 by the maintainer through merged PR #1229 for issue
#1168.

## Date

2026-09-05

## Classification

Classification: FM3

Required artifacts: explicit intake and release state models, immutable identity and authorization invariants, failure/recovery rules, acceptance tests and dependency graph in the linked design set.

Waivers: the present change is a design. Executable state-transition,
authorization, crash and publication tests must land with the implementation
issues. No distributed transaction, exactly-once publication, or availability
proof is asserted.

## Context

Issues #1110 and #1125 are closed with required-container and exact-SHA release
checks in the repository. Issue #684 remains open and its original proposal
predates the release-please implementation and current `raes` identity. Those
completed controls are prerequisites, not work to recreate or weaken.

An exact source SHA does not alone identify built bytes. An expiring workflow
artifact is useful for transport but insufficient as long-term release
evidence. A digest calculated by the same compromised mirror that supplies
the bytes cannot establish their approved identity.

## Decision

### Separate intake, build and publication authority

Upstream intake follows `candidate -> quarantined -> verified -> promoted`.
A failed verification never reaches promoted storage. Security revocation
changes admission status without rewriting immutable bytes or historical
evidence. Consumers require both a matching reviewed digest and an admissible
status under their profile's freshness policy.

Release work follows `resolved -> source-verified -> built -> artifact-admitted
-> publication-authorized -> PyPI-published -> GitHub-published`. Build and
verification jobs have no publication credential. The workflow graph records
failures explicitly and cannot convert a skip, absence, cancellation or
infrastructure error into admission.

### Bind the complete release identity

The admission record binds repository identity, exact source SHA, workflow
definition identity, run id and attempt, release id and tag, policy/lock hashes,
required test-image digests, test results, and every output filename, size and
digest. Wheel, sdist, SBOM and provenance refer to the same output subjects.
Installed wheel and sdist smokes run outside the checkout against the exact
admitted bytes. Both publishers rehash downloaded artifacts and reject missing,
extra, replaced or mismatched content.

The existing post-approval release/tag/SHA revalidation remains mandatory.
It is supplemented by verification of the admission record's trusted producer
and attestation subject. An artifact name, successful job name, mutable tag,
PR-produced checksum file or cache hit is never sufficient.

### Keep admission authority outside candidate code

Privileged publication uses a protected workflow definition and fixed policy
from the trusted branch. Manual dispatch must not allow an arbitrary workflow
ref, candidate script or candidate admission policy to run with publication
permissions. Candidate release code is executed only in isolated read-only
build/test jobs. The publisher validates the candidate's attested results with
the protected policy; changing that policy requires a separate reviewed
protected-branch change.

### Separate destinations and preserve bytes

Retain PyPI Trusted Publishing with a scoped GitHub environment and a separate
GitHub finalization job. The repository owns the expected publisher identity;
PyPI and GitHub enforce their credential and storage boundaries. Attestations
identify the producer and artifact, not a general guarantee that the code is
safe. The [PyPI security model](https://docs.pypi.org/trusted-publishers/security-model/)
explains the trust placed in the authorized publishing workflow.

Promotion copies original bytes, rechecks destination digests and records the
result. It never rebuilds a verified artifact under the same release identity.
Distribution storage and Actions caches do not replace repository review,
accepted trust roots or authenticated build attestations.

### Recovery and external controls

If PyPI succeeds and GitHub fails, recover GitHub publication using the same
admitted bytes. An ambiguous publication result requires a destination query
and byte/identity comparison before retry. A same-version digest mismatch is
an incident; it is never resolved with overwrite, `--clobber`, a moved tag or
a silent rebuild. If expiring workflow artifacts are gone, restore the
retained admission bundle. Without it, stop and follow a reviewed new-release
process.

Tag rulesets, environment approval, publisher registration, storage ACLs and
signing identities are external controls with an operational owner and an
audit record. GitHub issue dependencies order implementation work; they do not
themselves prevent a workflow from publishing. The workflow admission jobs and
external controls enforce publication at runtime.

## Alternatives Considered

- Source-SHA checks alone omit output identity and producer trust.
- Trusting Actions artifact names or mirror-computed checksums transfers
  authority to a transport channel without a reviewed decision.
- Rebuilding during promotion or recovery can produce different bytes from
  the same source and breaks the tested-artifact guarantee.
- One privileged build-and-publish job exposes credentials to candidate code.

## Consequences

Publication gains a durable, auditable boundary but requires retention of the
admission bundle and operational handling of partial external success. No
atomic transaction across PyPI and GitHub is claimed. Immutable distribution,
quarantine, revocation and recovery are specified in the
[architecture](../package-artifacts/architecture.md) and
[operations and acceptance plan](../package-artifacts/operations.md).

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-09-06 | #1229 | Recorded the maintainer acceptance already established by merged PR #1229 and added the ADR to the accepted-content pin manifest. |
