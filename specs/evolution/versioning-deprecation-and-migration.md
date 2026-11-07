# Versioning, deprecation, and migration governance

This specification sets the rules for RAES ecosystem evolution.
It implements the joint design for GOV-901, GOV-902, and GOV-903.

## Scope

This policy governs ecosystem surfaces owned by this repository.
It covers their versions, compatibility claims, deprecation records, removal
rules, and migration guidance.

It creates no shared runtime version registry or migration service across packages.
It adds no API endpoint, database table, or exception hierarchy.
Each surface keeps its existing authority, checker, schema, validator, or adapter boundary.

## Terms

**Version identifier** means a value local to one surface.
It names a release, lineage, payload shape, source artifact, or domain artifact.

**Producer** means the surface that supplies an artifact.
It writes, publishes, emits, or serves it.

**Consumer** means the surface that depends on the artifact.
It reads, imports, validates, executes, or otherwise uses it.

**Backward compatibility** concerns a named surface and dimension.
A newer consumer accepts older producer output and preserves its meaning.

**Forward compatibility** concerns a named surface and dimension.
An older consumer accepts newer producer output and handles it safely.

**Full compatibility** concerns a named surface and dimension.
Both backward and forward compatibility hold.

**Structural acceptance** concerns an artifact's syntactic or schema shape.
The consumer accepts that shape.

**Semantic equivalence** concerns input that is accepted.
It preserves the same RAES meaning.

**Behavioral compatibility** concerns runtime, CLI, API, validation, or conformance behavior.
That behavior stays within the documented contract.

**Operational interoperability** means components can work together across separate releases.
They follow documented admission, capability, and deployment rules.

## Surface-class matrix

Each surface class owns its version meaning.
It also owns its compatibility rule.

| Surface class | Authority | Identifier syntax | Compatibility relation | Lifecycle record | Migration evidence |
|---|---|---|---|---|---|
| Python distribution | `implementations/python/pyproject.toml`, release-please config, Git tag, PyPI artifact | SemVer package version and matching `vX.Y.Z` tag | Consumer code imports installed package APIs for the documented release | Release PR, GitHub Release, generated `CHANGELOG.md` | Release notes and package/API docs |
| Published JSON Schema | ADR-061, `contracts/schema-publication-manifest.json`, and `contracts/schema-publication/` | Contract id such as `backend-manifest-v2`; wire discriminator such as `backend-manifest/v2` | Schema lineage and stability-specific structural compatibility | Per-contract identity, schema path, and `stability`; Git schema history; independent removal tombstones | Schema diff, fixtures, checker output, and contract docs |
| Closed contract DTO and wire envelope | `raes_contracts.versions`, contract models, manifest authority | Exact discriminator such as `workflow-step-state/v1` | Exact payload-shape selection by owning reader | Contract ADR/spec and release notes | Reader validation tests and conformance fixtures |
| Processor/backend support declaration | Manifest models and manifest authority allowlists | Exact governed contract ids, not version ranges | Declared support for named counterpart contract ids | Manifest contract lineage and conformance result | Manifest update, fixture, and conformance report |
| Apparatus or implementation identity | Processor, backend, and participant manifests | Product/component identity version string | Operational interoperability declared by manifest capability blocks | Manifest release and conformance profile | Backend/processor/participant conformance evidence |
| SDL scenario and module | SDL spec, module registry, lockfile, trust policy | Scenario/module version and import version constraint | Import constraint satisfaction plus registry, digest, signature, and semantic validation | SDL/module documentation and release notes | Migration note or deterministic source rewrite |
| Experiment task, run, study, evidence, or domain artifact | Owning experiment-core spec and contract | Domain-specific artifact version | Domain semantic or provenance compatibility | Owning ADR/spec and contract lineage | Domain fixtures, replay/evidence checks, or migration note |
| ADR | ADR-000 and ADR-059 | ADR number plus status | Citable accepted content, not runtime compatibility | Status, pin, amendment row, or supersession | New ADR or recorded amendment |
| Ground Control requirement | Ground Control requirement graph | Requirement UID and status | Traceability/workflow state, not artifact compatibility | Requirement status and IMPLEMENTS/TESTS/DOCUMENTS links | Post-merge traceability reconciliation |

A new surface class extends this table.
It also extends its owning checker or documentation.
It does not create a central runtime registry by default.

## Compatibility claims

A compatibility claim is valid only when it names:

- the surface class;
- producer and consumer;
- direction: backward, forward, or full;
- dimension: structural, semantic, behavioral, or operational;
- version or lineage range under discussion; and
- verification evidence.

A bare statement that a change is "compatible" is incomplete.

Structural acceptance is not semantic compatibility.
A JSON Schema can accept an object without proof that it preserves SDL meaning.
Acceptance also does not prove conformance behavior or runtime interoperability.

ADR-061 remains the authority for published JSON Schemas.
Adding optional properties or enum values can add to schema structure.
Looser constraints can also add to that structure.
Those additions do not ensure forward compatibility with older closed readers.
A PR may claim end-to-end compatibility for such a change.
It must then show reader evidence.

Without that evidence, it must limit the claim to structural schema compatibility.

For Python package versions before 1.0, release-please follows the repository's release configuration.
It may treat breaking changes as minor releases.
Consumers must not infer post-1.0 SemVer stability from a `0.y.z` package release unless a specific surface policy states it.

## Deprecation

A deprecation is a lifecycle notice for a surface that remains supported.
It does not set schema stability, ADR status, or requirement status.
It is not a semantic validation error by itself.

A complete deprecation record names:

- exact surface and identifier;
- first release, contract lineage, or documentation version carrying the
  notice;
- replacement surface or explicit no-replacement rationale;
- migration reference;
- minimum notice window or removal eligibility rule;
- verification evidence that the old surface remains supported during the
  notice window; and
- security exception, if the ordinary notice window is shortened.

Use that is deprecated but supported must remain non-fatal.
The owning channel may emit a bounded notice, advisory, warning, release-note entry, or documentation marker.
Actual removal or unsupported use fails through the owning surface's existing error envelope.
That envelope belongs to SDL, contracts, the CLI, conformance, or HTTP.

Security exceptions may shorten ordinary notice only with the required record.
The record names affected versions, impact, and mitigation.
It also names the migration path and review authority.
The word "security" does not permit breaking changes without review.

The repository keeps deprecation records in `specs/evolution/deprecation-records.yaml`.
`tools/check_deprecation_lifecycle.py` validates them.
It fails closed if any record omits a required field.
That ledger is the single reviewable surface for these notices.
It is a governance record checked in CI.
It adds no runtime lifecycle registry, migration service, or endpoint.

Each record cites its owning surface's existing authority instead of replacing it.
A published JSON Schema record may have `status: removed`.
That record references the ADR-061 schema-publication tombstone record.
It does not duplicate that tombstone.

## Removal

Removal is allowed only when a complete deprecation record reaches its removal eligibility rule.
A documented security exception also permits removal.

Published JSON Schema removal follows ADR-061.
It must leave the required manifest tombstone.
Other surface removals use their owning evidence.
This includes release notes, ADR/spec updates, fixtures, tests, conformance reports, or diagnostics.

Removal must not silently reinterpret old input as new input.
If a removed surface appears, the owning reader fails.
It gives a bounded message specific to that surface.
When available, it points to the migration reference.

## Migration

Migration guidance covers one surface and a pair of versions.
A migration record names:

- source surface and version or lineage;
- target surface and version or lineage;
- transformation type: manual, assisted, or automated;
- data preservation rules;
- ambiguous or lossy cases;
- validation command or evidence; and
- rollback or no-rollback statement.

Migration notes for readers belong under the existing documentation boundary.
An automated migrator needs a deterministic transformation.
Only then is it justified.
It must be idempotent and preserve source data.
It must report ambiguous or lossy cases.
It must fail closed rather than drop unknown fields.

Compatibility adapters stay at the owning boundary:

- SDL normalization and module composition stay in `raes`;
- contract readers stay in `raes_contracts`;
- CLI presentation stays in `raes_cli`; and
- backend/runtime layers do not reinterpret authored source to hide migration
  needs.

## Verification

Changes governed by this policy use the repository's existing gates.
A surface can use a more specific checker instead.
The gates cover these checks:

- Release classification and version bumps use the PR title guard, release-please config and release PR.
  The Git tag, GitHub Release and PyPI artifact also give evidence.
- The docs build, CLI `--version`, and control-plane OpenAPI descriptions derive versions from installed distribution metadata.
  Release-please owns this source of truth.
  Without an installed distribution, they use the PEP 440 `0.0.0+unknown` sentinel.
  A fixed release literal would falsely imply a known release.
  Version-classification tests check this behavior.
- Published schema evolution uses the schema publication checker, generated-schema parity and fixture validation.
  It also uses publication records, Git schema history and tombstones.
- ADR evolution uses the ADR index and accepted-content pin gate.
- `tools/check_deprecation_lifecycle.py` validates the deprecation and lifecycle records in `specs/evolution/deprecation-records.yaml`.
  It checks the complete-record contract and removal eligibility.
  Published schemas also need an ADR-061 `removed_schemas` tombstone reference.
- SDL/module evolution uses the parser, validator, module registry and lockfile.
  It also uses trust, signature, digest and semantic tests.
- Contract and manifest evolution uses closed DTO validation, manifest authority, fixtures, profiles and conformance checks.
- Repository completion uses `tools/check_repo_policy.py`,
  `tools/check_requirement_governance.py`, `tools/verify_all.py`, and the
  canonical nox verification graph.

These checks need no secret or credential.
They need no environment dump or private configuration.
