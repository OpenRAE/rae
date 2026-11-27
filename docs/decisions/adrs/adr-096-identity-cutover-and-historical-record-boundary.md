# ADR-096: Identity Cutover and Historical-Record Boundary

## Status

accepted

## Date

2026-07-26

## Classification

Classification: FM2

Required artifacts: ADR, governed contract-migration evidence, whole-tree
verification, and regression tests.

Waivers: no compatibility alias, runtime migration service, persistence
registry, second validator family, or new exception hierarchy is introduced.

## Context

GOV-944 completes the repository identity cutover. The remaining occurrences
span published schemas, closed contract data, wire names, host-visible
artifacts, environment and workflow bindings, source identifiers, examples,
and configuration. They are not interchangeable: a schema identity, a JSON
property, an authentication header, a guest transport marker, and a prose
reference have different owners and compatibility consequences.

ADR-093 established the current project identity and hard-cut public import,
command, and distribution boundaries. It deliberately left governed contracts,
runtime artifacts, and workflow identifiers to their owning controls. ADR-009,
ADR-061, and ADR-075 already assign authority, schema evolution, and lifecycle
responsibilities; they must not be bypassed by a repository-wide text edit.

The repository has no complete-tree guard against reintroducing the retired
identity. Existing positioning checks are intentionally narrow, and the
general policy-exception mechanism is a temporary waiver channel rather than a
record of immutable history.

## Decision

RAES is the only current repository-owned identity. Every current tracked
surface uses RAES, including contract identifiers and schema URIs, wire keys
and topics, runtime artifact and filesystem names, environment and workflow
keys, generated outputs, source identifiers, configuration, examples, and
prose. The canonical published-schema URI root is
`https://raes.dev/schemas/`.

The cutover is a hard boundary. A renamed input, artifact, header, event, or
schema identity is not accepted as a fallback, alias, wrapper, redirect,
dual-read path, or compatibility mode. A surface that needs migration guidance
uses the existing lifecycle documentation and records; it does not keep a
retired runtime value alive. External owners of domains, quality-service keys,
or workflow-project identities must provision their replacement before the
repository points to it. This repository neither proves DNS ownership nor
implements an external redirect.

Published-schema changes remain governed by ADR-061 and ADR-009. The
normative checked-in schema, its reference-model source, generated bundle,
publication record, fixtures, and consumer tests change together. Renaming a
schema path or contract id is a removal plus replacement for publication
purposes: retain the existing tombstone/change-ledger evidence, even though
runtime compatibility is not retained. A property name, discriminator,
extension keyword, event topic, or header is a payload-breaking change and is
tested as such. Draft status does not make a wire rename invisible.

The repository adds one policy-time whole-tree retired-identity check. It
enumerates the tracked tree directly from Git, including hidden and generated
files, and fails closed when an inspected file, policy input, or historical
record cannot be read safely. Its matcher distinguishes standalone and
qualified identity tokens from incidental substrings. It runs in the canonical
`nox` policy/verification graph, not only on changed files or in an optional
developer command. It reports bounded path and location diagnostics through
the existing policy failure envelope.

Historical retention is narrow and explicit. An exemption is valid only for
an exact tracked record whose purpose is to preserve a dated or immutable fact,
with its record class, rationale, and content identity recorded. Directory
prefixes, globs, generic policy waivers, generated-file exclusions, and
unbounded prose exemptions are invalid. A content change invalidates the
historical exemption unless it remains a separately verified historical record.
Accepted ADR pins, release history, provenance evidence, and dated research
records may supply that evidence at their owning boundary; they do not make
all documentation historical.

## Alternatives Considered

Use the project-positioning checker. Rejected: its fixed entrypoint set proves
framing, not the absence of a retired identity throughout repository-owned
contracts and artifacts.

Use the shared policy-exception file. Rejected: expiration and path-scoped
waivers are appropriate for temporary policy debt, but not for permanent,
auditable historical facts.

Keep aliases or dual-read paths while changing current output. Rejected: that
would leave a live retired identity, create ambiguous precedence and header
smuggling risks, and contradict the required hard cut.

Create a central identity registry or migration service. Rejected: contract,
runtime, workflow, and publication owners already provide the relevant seams.
A new cross-package abstraction would conflate their validation and lifecycle
rules.

## Consequences

The implementation must use the existing contract models, schema bundle,
publication manifest, lifecycle records, policy-failure envelope, and `nox`
graph rather than parallel inventories or validators. It must preserve each
owner's existing parse, authorization, redaction, path-safety, fixed-argv, and
diagnostic behavior while changing only the identity value.

The full-tree check has one extension seam: an exact, content-bound historical
record entry. Adding a future historical class requires its owning immutable
evidence and checker validation; adding a new current surface requires no
allowlist entry and therefore fails until it uses the RAES identity. This is a
verification seam, not a runtime configuration or persistence surface.

Existing external consumers must treat renamed contract and wire values as
breaking. The repository supplies governed removal and migration evidence, but
does not claim backwards compatibility, exact data conversion, or automatic
host-state cleanup. The cutover does not alter SDL, runtime, authorization,
validation, or evidence semantics beyond their identity-bearing values.

## References

- [ADR-009](adr-009-normative-artifact-authority-and-repository-structure.md)
- [ADR-061](adr-061-published-schema-evolution-policy.md)
- [ADR-075](adr-075-ecosystem-versioning-deprecation-and-migration-governance.md)
- [ADR-093](adr-093-raes-rename-and-compatibility-boundaries.md)

## Amendments

| Date | Commit/PR | Summary |
|---|---|---|
| 2026-07-26 | #908 | Retained the existing SonarCloud project key as an exact, content-bound external-service designation; it is not a current RAES product identity or a general compatibility allowance. |
| 2026-07-27 | #908 | Corrected the canonical published-schema URI root. The root recorded above, `https://raes.dev/schemas/`, names a domain this project does not control, and neither did the retired-identity domain it replaced. The canonical root is now `https://raesystem.github.io/rae/schemas/`, which is bound to the repository's own GitHub organisation and is therefore uniquely ours to assign. `$id` remains an identifier and is not required to resolve, so no DNS or hosting obligation follows from it. |
| 2026-07-28 | #908 | Split the release-history boundary for bot-maintained files. A whole-file digest cannot hold for `CHANGELOG.md`, which release-please rewrites on every release by inserting each new section above the existing ones; the pin went stale at v2.0.0 and the gate was overridden rather than fixed. Such files are now classified `generated-release-history`, which pins the classified tail exactly and holds everything written above it to the live-tree rule of zero retired identity occurrences. Newly generated content therefore carries no historical exemption. |
| 2026-07-31 | #963 | Rebound the canonical published-schema URI root from `https://raesystem.github.io/rae/schemas/` to `https://openrae.github.io/rae/schemas/` after the GitHub organization was renamed from RAESystem to OpenRAE. The coordinated change updates normative schemas, their reference-model source, publication records, fixtures, consumer tests, and live repository links while preserving historical release records. |
| 2026-11-06 | #1929 | Historical records, operational bindings, and generated history records no longer store a content digest. An occurrence count binds each exemption, the generated head stays at zero occurrences, and the live-token rule applies everywhere else, so a record can be amended without a hand-edited digest. |
