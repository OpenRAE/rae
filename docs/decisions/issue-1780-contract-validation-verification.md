# Contract validation evidence

This note records verification for issue #1780.
It does not replace the design or the required hosted checks.

## Design before code

The architecture preflight used baseline `ffb54d246`.
The [preflight](issue-1780-contract-validation-preflight.md) records its constraints.
The [design](issue-1780-contract-validation-design.md) declares the packages, public interfaces and trust boundaries.

| Change | Recorded before implementation |
| --- | --- |
| Shared bindings, corpus, validator and generator | [Plan at 2026-11-03 00:11:26 UTC](https://github.com/OpenRAE/rae/issues/1780#issuecomment-6591817445): the changed model passed `archcheck -design` before Go code |
| Transport round-trip interface and canonical JSON import | [Plan at 00:41:44 UTC](https://github.com/OpenRAE/rae/issues/1780#issuecomment-6592282382): model and design check preceded the interface change |
| Complete semantic admission after the scope decision | [Plan at 02:34:17 UTC](https://github.com/OpenRAE/rae/issues/1780#issuecomment-6593963677): declared `contract/admission` and passed the design check before implementation |
| Bounded private-profile checking | [Plan at 10:23:48 UTC](https://github.com/OpenRAE/rae/issues/1780#issuecomment-6601083643): declared `CheckInertSchema` and `InertLimits` before code |

These dated records establish the order of work.
The current architecture and design checks also pass.
A current passing check alone would not establish that order.

## Complete fixture inventory

The published registry has 148 entries.
The packaged fixture tree has 701 direct contract fixtures and 14 workflow fixtures.
One original unknown-selector regression is kept in addition to the contract files.
The full reference table therefore has 702 rows.

`TestFullValidationGoldenCorpus` scans the packaged tree and publication entries.
It identifies contracts by an enclosing registered ID or a unique published schema version.
That includes vectors stored outside folders named for their contract.
It compares the scanned inventory with both the recorded file inventory and the actual test rows.
It also requires an explicit classification for each workflow fixture.
The smaller 363-case CLI inventory cannot stand in for this check.

Every contract input has a separately captured Python model or contextual result.
The reference models are the actual types used to construct the published schema bundle.
The published schema gate runs before model validation to retain the approved type decision.
Contextual checks use independently supplied records and the reference family's validator.
The table pins owner input hashes and reference source hashes.
Input hashes tie each result to its exact bytes.

Existing CLI and schema golden records stay unchanged.
The test verifies those original results and input hashes through their recorded source paths.
Every row also has a separate Python Draft 2020-12 schema result.
Go compares that result independently, including rows from the admission CLI.
The original CLI result includes local admission rules.
Sixty-nine of those surface results differ from the schema-only result.
Those differences remain explicit and do not replace the original records.
A structural positive can have a negative full result when its independent parent or execution differs.
That follows the maintainer's [separate-results decision](https://github.com/OpenRAE/rae/issues/1780#issuecomment-6613269031).

The [regression crosswalk](../../specs/conformance/contract-validation-regressions.md)
links limits, error behavior, recovery and source defect cases to Go tests.

## Check order

Local feedback selects affected cases.
It includes targeted owner joins, full-reference fixture families, input and work limits,
privacy, recovery, metadata syntax, source security regressions and generator drift.
Architecture, scoped policy, custom vet, lint and changed-document checks run before publication.

The maintainer approved publication before the blocked review for this delivery.
The issue's blanket proof criteria were removed at the maintainer's direction.
The concrete binding, schema, invariant and fixture requirements remain.

The delivery sequence is:

1. Finish implementation, targeted checks and document checks.
2. Run the required pre-publish hook and publish the branch.
3. Create the synchronized PR and run hosted CI.
4. Complete review and repair its findings before readiness.
5. Require hosted CI and Sonar to pass before recording readiness.
6. Leave the merge to the maintainer.

Hosted CI owns the complete fixture corpus, full tests, race checks,
coverage, mutation tests, fuzzing and repository-wide verification.
These checks remain required even when targeted local checks pass.
No passing CI result is claimed before the candidate is published and checked.

CI retains a short-lived diagnostic coverage profile and test log even when the Go tests fail.
The diagnostic artifact cannot supply the authoritative Sonar coverage input.
The normal coverage artifact still requires the preceding checks to pass.
