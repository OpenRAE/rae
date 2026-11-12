# ADR-063: Reference Emulation Backend

## Status

superseded by ADR-115

## Date

2026-06-20

## Classification

Classification: FM0
Required artifacts: ADR, unit tests
Waivers: none

The reference emulation backend is a concrete implementation of existing
backend contracts whose correctness is established structurally and verified by
unit tests plus the existing backend-conformance runner. It introduces no new
semantic, graph, or stateful reasoning that would warrant a higher level; the
RUN-311 episode-state invariants and SEM-218 realization gate it relies on are
already formalized and gated elsewhere, and this backend consumes them rather
than redefining them.

## Context

[ADR-004](adr-004-sdl-runtime-layer.md) defines the
compile/plan/execute runtime and requires every backend to provide explicit
domain protocols plus a `BackendManifest`.
[ADR-036](adr-036-sdl-processor-runtime-module-boundaries.md) assigns package
ownership: `aces_runtime` owns live control, `aces_backend_protocols` owns
backend declarations, `aces_backend_stubs` owns the non-normative in-memory
stub, and `aces_contracts` owns neutral DTOs. The repository has shipped the
manifest, registry, conformance, and SEM-218 realization seams, and an in-memory
stub that exercises them — but no concrete backend that realizes plans against
real infrastructure.

RUN-314 (issue #197) closes that gap with a repository-owned **reference
emulation backend** that realizes provisioning plans against a container
substrate while remaining a faithful, conformant implementation of the existing
backend contracts. The architecture preflight note
(`docs/decisions/issue-197-run-314-reference-emulation-backend-preflight.md`)
records the binding guardrails: reuse existing seams, never add new
manifest/schema/profile/fixture/vocabulary/exception/store authority, keep
emulator-native facts out of portable artifacts, and route apply/control through
`RuntimeManager` / `RuntimeControlPlane`.

## Decision

Add a new implementation package
`implementations/python/packages/aces_reference_backend/` that implements the
four `aces_backend_protocols.protocols` roles (Provisioner, Orchestrator,
Evaluator, ParticipantRuntime) and registers on the existing `BackendRegistry`
descriptor seam under the name `reference-emulation`.

### 1. Place in the ADR-004 / ADR-036 boundary

The reference backend is implementation-side code. It consumes
`aces_backend_protocols`, `aces_contracts`, and the public runtime registry
seam; core packages do not import it, and no implementation logic lives in the
compatibility-only `implementations/python/src/aces/` tree. It is not a new
processor, runtime manager, conformance authority, schema authority, or
experiment archive. It publishes identity/capability through the standard
`BackendManifest` with the `reference-emulation` identity, declaring only the
evidence-backed contract ids, concept bindings, realization-support
declaration, and capability terms the conformance runner actually exercises (the
same evidence set the stub declares). The in-memory stub stays non-normative and
is used in tests only as a comparison oracle; this backend does not import or
subclass it.

### 2. Driver abstraction

Plan interpretation is split from realization. A pure
`interpret_provisioning_plan(plan) -> Realization` maps node/network/placement
resources into portable, secret-free specs (`NetworkSpec` / `ContainerSpec`)
plus diagnostics for unsupported or malformed resources. A `DeploymentDriver`
protocol is the host-process boundary; two drivers ship:

- `InProcessDriver` (default): hermetic, records ops and synthesizes portable
  handles, no subprocess and no runtime — safe in CI and in the default
  conformance/apply path.
- `OciDeploymentDriver`: realizes against a real container runtime
  (docker/podman). The next reasonable variation (provider, workspace, network
  namespace, image source, resource limits) is selected through the registry
  descriptor `**config` seam without rewriting `RuntimeManager`,
  `RuntimeControlPlane`, conformance, or manifest rendering.

### 3. Opt-in Docker conformance

Real-container realization is verified by a `@pytest.mark.docker` integration
test that provisions a container through the control plane, confirms the
realized inventory, tears it down, and runs `run_target_conformance` against the
OCI driver. The `docker` marker is excluded from the default hermetic suite and
the test self-skips when no runtime is present. A dedicated `integration_docker`
nox session and a non-blocking, runtime-gated CI job run it; the canonical
`verify` graph stays hermetic and never depends on a container runtime.

### 4. Portable-fact / provenance boundary

Snapshot, result, and history payloads carry only portable ACES facts — the
same shape the stub produces. Container/VM/network ids, daemon inspect payloads,
host paths, environment, argv, tokens, credentials, SSH keys, and backend-native
reprs never reach manifests, snapshots, diagnostics, conformance reports, or
examples; the portable surface is references, digests, and classification
labels. Real realization is a **driver side effect**: the provisioner preserves
planned payloads honestly into snapshot entries, and SEM-218 provenance flows
through the existing `_call_backend_apply` gate
(`RuntimeManager(target).apply(plan)` fills
`RuntimeSnapshot.realization_provenance`) rather than by mutating the portable
snapshot. Public failures are `Diagnostic` / `OperationReceipt` /
`OperationStatus` only; there is no backend-specific exception hierarchy, log
channel, or raw traceback. The OCI driver uses fixed argv (never `shell=True`),
a closed runtime allowlist, bounded timeouts, and structured handling that keeps
native stdout/stderr out of every returned handle and diagnostic. Because a plan
author controls the container image (via `node.source`) and `run` pulls and
executes it, the driver enforces an operator image-trust policy: only the
configured `default_image`, an explicit `allowed_images` entry, or a
digest-pinned ref is realized, so plan submission cannot become arbitrary-image
code execution. Realization is transactional at the driver boundary — a partial
failure rolls back the resources that did succeed, and a failed teardown stays
tracked for retry — and a container is attached to every network its plan
declared, so realized topology matches the plan rather than silently landing on
the runtime default network.

### 5. APTL as a downstream consumer

The split between pure interpretation and a driver protocol mirrors the pattern
APTL already uses to consume ACES provisioning plans. APTL remains a downstream
consumer of ACES contracts; this backend lifts the interpret/driver **pattern**
without depending on APTL, and APTL continues to depend on ACES, never the
reverse.

## Consequences

**Positive**

- The repository now ships a concrete, conformant backend that realizes plans
  against real infrastructure, proving the manifest/registry/conformance/SEM-218
  seams end to end with a non-stub implementation.
- The driver abstraction lets the same backend run hermetically (default) or
  against a real container runtime (opt-in) without changing the runtime,
  control plane, or conformance surfaces.

**Negative / costs**

- A second full backend implementation now tracks the portable result/history
  envelope shapes; drift from the contracts is caught by the shared conformance
  runner the backend must keep passing.

**Risks**

- The opt-in Docker path depends on a host container runtime; it is gated and
  self-skipping so it can never make the hermetic verification graph flaky.

## Alternatives Considered

- **Promote the in-memory stub into the reference backend.** Rejected: ADR-036
  keeps the stub non-normative, and a container-backed backend has materially
  different realization behavior. The stub stays a test oracle.
- **Add Docker/Podman-specific SDL syntax or runtime fields.** Rejected: the
  existing runtime surfaces already carry the portable facts; emulator selection
  is driver configuration through the registry seam, not new authored syntax.
- **Add a backend-specific exception hierarchy / log channel.** Rejected: public
  failures must remain `Diagnostic` / `OperationReceipt` / `OperationStatus` so
  the control plane and conformance runner see a uniform error envelope.
