# ADR-036: SDL, Processor, Runtime Module Boundaries

## Status

accepted

## Date

2026-05-26

## Context

ADR-008 established the processor as the semantics-bearing middle layer, but
the Python package boundary drifted: `aces_processor` also contained the live
runtime manager, control plane, control-plane HTTP adapter, operation store,
security policy, and backend registry. That made the package name lie about
ownership, encouraged authoring tools to reach into runtime internals, and left
future runtime work without a clear import boundary.

ADR-015 added SDL/processor layering and a file-size cap, but it explicitly
left the risk that a later top-level package such as `aces_runtime` would need
its own policy. Issue #410 is that follow-up.

## Decision

Split the current implementation into these owning packages:

- `aces_sdl` owns the SDL language model, parsing, instantiation, and
  SDL-language semantic helpers.
- `aces_processor` owns SDL processing: validation-facing semantic diagnostics,
  support determination, manifests, compilation, planning, reconciliation
  semantics, and compiled processor runtime model dataclasses.
- `aces_runtime` owns live runtime control: `RuntimeManager`,
  `RuntimeControlPlane`, `RuntimeTarget`, `BackendRegistry`, control-plane API,
  security, persistence, operation history/audit, backend invocation, runtime
  snapshots, participant episode control, and backend result validation at the
  execution boundary.
- `aces_contracts` owns neutral cross-package DTOs and enums used at backend
  and runtime boundaries, including diagnostics, planning/result envelopes,
  runtime snapshots, workflow result contracts, evaluation result contracts,
  and participant episode contracts. Runtime/backend protocols consume these
  contracts without importing processor implementation modules.
- `aces_backend_protocols` owns backend capability and protocol declarations.
  It must not import processor/runtime implementation modules; protocol methods
  must use typed neutral contract DTOs rather than `Any` for public call
  signatures.
- `aces_backend_stubs` owns non-normative in-memory backend implementations.
  Stubs implement the backend protocol surface using `aces_contracts` DTOs and
  must not import processor implementation modules.
- `aces_cli` and `aces_mcp` are authoring/orchestration surfaces that consume
  SDL and processor APIs. They must not own semantic truth or call runtime
  internals.

This ADR supersedes:

- the part of ADR-008 that placed execution-facing runtime control inside the
  processor package
- the ADR-010 section 3 ownership statement that listed
  runtime/control-plane behavior under `aces_processor`

It does not change ADR-008's decision that processor artifacts are the
compiled, semantics-bearing middle layer, and it does not change ADR-009/ADR-010
compatibility policy: owning-package shims are not preserved. The only
compatibility shim layer is the legacy `aces.*` namespace.

Runtime may consume public processor APIs and shared contracts. It may not
import processor private modules or SDL semantic implementation modules.
Backends remain behind runtime/backend protocol interfaces; authoring surfaces
do not import runtime internals.

## Enforcement

Add a required `module_boundaries` block to `tools/policy/adr_policy.yaml` and
enforce it in `tools/policy/repo_policy.py`. The checker validates that the
block exists, that module roots resolve to existing in-repository directories,
that every first-party package root under `module_boundaries.package_coverage_roots`
has a declared module boundary, and then rejects:

- imports from packages that the owner explicitly forbids
- imports of private modules such as `aces_processor._private`
- imports from packages that are only allowed through named public prefixes
- `Any` in public backend protocol method signatures, so backend APIs keep
  proof-grade DTO types from `aces_contracts`

The file-local gate checks the selected changed paths. The full policy gate
scans every Python file under every configured module root, so pre-commit and
CI cannot hide a latent boundary violation behind an unrelated changed file.

## Consequences

### Positive

- Runtime control has a package name that matches its responsibility.
- Processor code can evolve as pure SDL processing without depending on live
  runtime control.
- Authoring surfaces have an explicit boundary: they call SDL/processor APIs,
  not runtime internals.
- Backend protocol signatures are typed against neutral shared contracts
  without reintroducing an import edge to processor implementation modules.
- The policy gate catches accidental boundary regressions during normal PR
  review and full verification.

### Negative

- Direct imports from removed owning-package paths such as
  `aces_processor.manager` are no longer supported.
- Documentation and tests must distinguish processor model contracts from
  runtime live-control APIs.

### Risks

- The policy is still in-repository code and configuration, so deliberate
  weakening is a review concern rather than a cryptographic enforcement
  mechanism. The config is fail-closed to prevent accidental opt-out.
- `aces_processor.models` still contains participant behavior and compiled
  processor runtime-model types. Runtime-facing DTOs have moved to
  `aces_contracts`, and remaining splits must preserve the compatibility
  re-exports used by existing callers.
