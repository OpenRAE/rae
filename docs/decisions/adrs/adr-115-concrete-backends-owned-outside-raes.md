# ADR-115: Concrete Backends Are Owned Outside RAES

## Status

accepted

## Date

2026-10-21

## Classification

Classification: FM0
Required artifacts: ADR, unit tests (installed wheel and sdist packaging checks that prove no concrete backend ships)
Waivers: none

This decision removes implementation code and moves ownership. It adds no
semantic, graph, or stateful reasoning. The portable contracts that the removed
backends consumed keep their existing formal artifacts and gates.

## Context

[ADR-063](adr-063-reference-emulation-backend.md) added a concrete reference
emulation backend to this repository. A libvirt backend, its TechVault live
gate, and its evidence producers followed. These packages realized plans against
containers and virtual machines. They owned credentials, resource allocation,
native lifecycle, rollback, and teardown.

[ADR-036](adr-036-sdl-processor-runtime-module-boundaries.md) separates the
processor, the runtime, the backend protocols, and the stubs.
[ADR-104](adr-104-runtime-control-plane-architecture.md) separates the portable
control plane from native effects.
[ADR-113](adr-113-reusable-execution-machinery.md) allocates reusable execution
machinery across the ecosystem. These boundaries make concrete realization a
backend responsibility, not a responsibility of the language and contract
repository.

LilRAE ([OpenRAE/lilrae](https://github.com/OpenRAE/lilrae), PyPI `lilrae`) is
now an independently released personal backend. LilRAE 8.1.0 ships its own RAES
backend and pins the released RAES 6.0.1. Issue #967 removes the bundled
concrete backends from RAES. The architecture preflight
`docs/decisions/issue-967-backend-extraction-preflight.md` records the binding
guardrails.

## Decision

### 1. RAES keeps the portable surface

RAES keeps these responsibilities:

- SDL parsing, validation, and processing, including the reference processor;
- the portable runtime and control-plane contracts and their reference
  enforcement;
- the published contract corpus, the backend manifest, and the backend
  protocols;
- the installed conformance facade (`run_fixture_suite()`,
  `run_target_conformance()`, and `raes conformance backend`);
- semantic examples, dry contract fixtures, and the test doubles in
  `raes_backend_stubs`;
- the portable materialization run archive
  (`raes_operations.run_artifacts.RunMaterializationArchive`).

### 2. Backend distributions own concrete realization

A backend distribution owns concrete realization, native readiness, credentials,
resource allocation, native execution, rollback, and teardown. LilRAE owns these
responsibilities for the personal local deployment. The libvirt backend and its
TechVault live gate have no successor in this repository.

### 3. Removed surfaces

RAES removes these surfaces:

- the `raes_reference_backend` and `raes_backend_libvirt` packages;
- the backend workflows in `raes_operations` (the libvirt evidence run, the
  TechVault live gate and cleanup, and the cross-backend corpus);
- the `raes libvirt` and `raes corpus` commands;
- the reference participant-opacity harness in `raes_conformance`;
- the real-daemon harness, the container integration lanes, and the tooling
  that only those lanes used.

The public migration guide is `docs/migration/concrete-backends.md`.
`specs/evolution/deprecation-records.yaml` records the removal.

### 4. Extension seam

A backend attaches through the existing injected `RuntimeTarget`, the backend
manifest and profiles, and the conformance harness parameters. RAES adds no
backend name switch, plugin discovery, or backend-specific schema. An installed
RAES release must not import a backend, contact a daemon, read credentials, or
discover, adopt, roll back, or destroy native resources.

### 5. Evidence boundary

Fixture conformance from an installed RAES release is not live
interoperability evidence. Live LilRAE evidence is a LilRAE release gate.
Historical decision records and research captures keep their original
producers. They are not active installation instructions.

## Alternatives Considered

- **Keep the backends as optional extras.** Rejected: an optional import or
  extra keeps native lifecycle ownership in RAES and keeps the dependency and
  supply-chain surface.
- **Move the backend code into `raes_backend_stubs`.** Rejected: an in-process
  copy of a concrete backend is not a test double, and the stub name would hide
  native ownership.
- **Forward the removed commands to LilRAE.** Rejected: a command or import
  forwarder adds a dependency cycle and hidden backend discovery.
- **Remove only the reference backend.** Rejected: the libvirt backend also
  owns allocation and lifecycle. Keeping it would leave the ownership problem
  in place.

## Consequences

**Positive**

- RAES installs and tests without concrete backend code, credentials, native
  tools, or container and virtualization daemons.
- The dependency, tooling, and CI surface becomes smaller.
- Backend owners release on their own schedule and against a named RAES
  release.

**Negative / costs**

- Users of the bundled backends must move to LilRAE or another backend
  distribution. The libvirt backend has no successor.
- RAES no longer carries in-repository live realization evidence.

**Risks**

- A downstream package that imports a removed module fails when it moves to
  the release after RAES 7.0.0. The migration guide names each removed import.
