# ADR-034: Runtime Software Component Inventory

## Status

accepted

## Date

2026-05-25

## Context

Issue #395 identifies an SDL expressivity gap: a scenario node can contain
software state that is finer grained than package-manager rows in
`runtime.packages`. A single package can ship multiple binaries or bundled
libraries, software can be installed outside a package manager, and the same
component may need an application/framework/library distinction for analysis or
inventory parity.

ACES already has adjacent surfaces, but each has a narrower meaning:

- `runtime.packages` records package-manager rows.
- `runtime.applications` records participant-observable HTTP route/API/UI
  surface inventory.
- `runtime.processes` records running process observations.
- `runtime.dependency_manifests` records manifest-file observations.
- `source.build` records image build provenance.
- top-level `features` records authored scenario deployment intent.

Reusing any of those would make component identity ambiguous and would blur the
existing authored-intent, build-provenance, runtime-state, and observable-surface
boundaries.

## Decision

Add `Node.runtime.software_components` as a node-scoped runtime inventory
surface for software identity facts. Each component has a stable
`component_id`, `name`, optional `version`, bounded `component_type`, bounded
`provenance`, optional ecosystem identifiers (`purl`, `cpe`, hashes), optional
package/manifest lineage fields, and optional absolute runtime paths where the
component is present.

The surface is WHAT-IS state. It does not model invocation, capabilities,
commands, participant workflows, or scanning. It is declarative inventory only:
the SDL parser and model validators do not execute binaries, inspect host files,
query package databases, or import SBOM/scanner payloads.

The component type vocabulary may reuse SBOM-style identity categories such as
`application`, `framework`, `library`, `container`, `platform`,
`operating_system`, `device`, `device_driver`, `firmware`, `file`, and `data`.
ACES owns the SDL shape; raw CycloneDX, SPDX, package-manager, or scanner output
remains evidence/provenance input rather than the normative schema.

## Guardrails

- Keep `runtime.packages` as package-manager rows. Do not add subcomponent
  identity there.
- Keep `runtime.applications` scoped to ADR-026's HTTP route/API/UI inventory.
- Keep `runtime.processes` scoped to observed running processes.
- Keep `runtime.dependency_manifests` scoped to manifest files, not resolved
  component sets.
- Keep `source.build` scoped to artifact build provenance.
- Keep top-level `features` scoped to authored deployment intent.
- Do not name the field `cli_applications` or otherwise revive invocation
  semantics that issue #395 explicitly retracted.
- Do not add raw SBOM documents, scanner reports, command output, credentials,
  private keys, or backend-native inspect payloads to the model.

## Consequences

### Positive

- SDL can normatively declare node software identity below package-manager row
  granularity.
- Package rows, component identity, process observations, HTTP surfaces, and
  build provenance stay distinguishable.
- APTL and other inventory consumers can map observed component facts into ACES
  without converting evidence bundles into schema authority.

### Negative

- Authors may need to record both a package row and one or more software
  components for the same installed artifact when both facts matter.
- The model intentionally does not resolve component dependency graphs or import
  full SBOM documents; richer import tooling remains separate work.

### Risks

- Overly broad use of `other` or free-text provenance can erode comparability if
  inventories skip the bounded fields.
- Future references from components to packages, manifests, files, or processes
  must add semantic validation and module-reference support together, rather
  than publishing dangling string conventions.

## Software requirement refinements (issue #1205)

`runtime.software_components` remains the canonical component owner. It now
accepts independent presence and named version predicates, the existing exact
package model as a refinement, explicit package-row correspondence, and optional
pinned domain-profile constraints. `runtime.packages` remains a compatibility
shorthand with its original exact-package and APT final-state meaning. Shared
repository/trust state has one node-local identity owner; transient acquisition
uses the existing plan-profile host. Neither surface authorizes acquisition.

The normative boundary is
[software requirements](../../../specs/sdl/software-requirements.md).
The [remediation brief](../issue-1205-software-outcomes-remediation.md) records
the adjacent-surface audit, lineage, primary version-ordering sources and
alternatives. Adding manager-specific options to the old APT union, duplicating
software inventory, and putting semantics in source labels were rejected.
No product-specific backend adapter, downstream scenario dependency, installer
or implicit observation obligation is introduced. Backend realization,
declared service behavior and separately requested reporting retain their own
owners. Unsupported execution support is refused, not inferred from a profile
definition or a successfully parsed package.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-07-13 | #417 | Clarified that authored software components describe required final state; scanner, SBOM, filesystem, and process-inspection capture methods remain evidence provenance and are no longer accepted as component provenance values in SDL. |
| 2026-09-12 | #1205 | Adopted generic software refinements, exact-package compatibility, shared final repository/trust identity and independent acquisition/reporting boundaries. |
