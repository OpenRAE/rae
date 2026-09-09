# Runtime Architecture: SDL -> Processor -> Runtime -> Backend

This document describes the processor and runtime path that turns authored SDL
into executable backend operations for a realized agentic environment. The
authored scenario, compiled plans, backend realization, participant execution,
observations, and evidence remain distinct phases; a realized environment is
not identical to its SDL document. This is an SDL-native architecture built
for the SDL itself and its backend contracts. See
[ADR-004](../../decisions/adrs/adr-004-sdl-runtime-layer.md) and
[ADR-036](../../decisions/adrs/adr-036-sdl-processor-runtime-module-boundaries.md)
for the decision records.

In the broader ecosystem architecture, this document focuses on the
processor-runtime-backend path that is currently implemented in code. It does
not attempt to fully specify every other apparatus surface. In particular, the
ecosystem distinguishes:

- authored scenario meaning in SDL
- the processor that instantiates, compiles, plans, and determines support
- the runtime that coordinates live execution against a target
- the backend that realizes deployable or simulated target operations
- optional participant implementations that consume participant contracts
- live runtime state
- archival run, evidence, and provenance records

The compile -> plan -> execute stack described here is therefore one important
subset of the overall architecture rather than the whole experiment apparatus.

Time is one of the clearest examples of why those broader apparatus boundaries
matter. The authored SDL may express timelines, deadlines, timeouts, or
episode-local budgets, but the realized execution still depends on apparatus
choices such as clock authority, time domain, pacing policy, synchronization
strategy, and the ordering guarantees that the runtime/backend can actually
honor. Those choices are not just incidental implementation details: they
shape experiment validity and must be declared and preserved as part of run
provenance when different realizations are compared.

Autonomous participant execution follows the same separation. Compilation
preserves exact action-to-target-service bindings; planning admits those
relations against the backend manifest; and the runtime owns a typed,
generation-fenced execution-service scope. Native calls may overlap within a
finite admitted bound, but portable snapshot/history commits are serialized
with revision checks. Shared-clock pause, resume, and reset coordinate service
readiness and generation, while pacing loss is published as degraded,
not-ready state with an explicit deviation reference.

Under the repository's [coding standards](../reference/coding-standards.md),
this layer is where `FM2` and `FM3` work becomes most relevant. The
formalization target here is not raw YAML, but the typed runtime model,
processor plans, and execution contracts that preserve semantic meaning across
validation, compilation, planning, and backend execution.

This layer also draws from a different precedent set than the author-facing SDL
surface. OCR and CACAO still matter, but the strongest implementation models
here come from mature workflow and distributed-runtime systems:

- AWS Step Functions, Argo Workflows, and W3C SCXML for explicit control-flow
  semantics
- Kubernetes, Temporal, and OpenC2 for portable execution-state and
  language-neutral contract boundaries

## Package Boundary

```text
raes                -> parse + instantiate + SDL-language semantics
raes_processor          -> compile + plan + support/contract semantics
raes_runtime            -> live control + manager + control-plane APIs
raes_backend_protocols  -> backend capability/protocol declarations
raes_backend_stubs      -> non-normative in-memory target implementations
```

ADR-036 backs this package boundary with `tools/check_repo_policy.py`: the
full policy gate scans every Python file under each configured package root,
and the pre-commit gate runs the same architecture-as-code check against
staged changes.

## Runtime Stages

### 1. Instantiate + Compile

`instantiate_scenario(raw_scenario, parameters=None, profile=None)` is the
repo-owned concretization pass that runs before compilation.

It:

- validates the normalized/expanded authoring input
- applies explicit parameter values
- applies SDL variable defaults
- rejects unresolved `${var}` placeholders
- rebuilds a closed `InstantiatedScenario` with portable binding/import,
  capability, and explicitness evidence
- removes `variables`, `imports`, and `module` from the concrete shape
- reruns semantic validation after substitution

`compile_runtime_model(scenario)` then lowers the admitted instantiated scenario
into runtime objects. A direct or JSON-deserialized `InstantiatedScenario`
passes `admit_instantiated_scenario()` first; compiler callers cannot disable
that semantic gate.

It separates reusable definitions from bound runtime instances:

- `features` -> feature templates
- `node.features` -> node-scoped feature bindings
- `conditions` -> condition templates
- `node.conditions` -> node-scoped condition bindings
- `injects` -> first-class orchestration inject resources
- `node.injects` -> optional node-scoped inject bindings layered on top of top-level inject resources
- `nodes` + `infrastructure` -> deployable network/node resources
- orchestration and objective sections -> resolved runtime programs and graph nodes

The output is a `RuntimeModel` with canonical addresses for every runtime-owned
object.

Bound condition refs fail closed. An unqualified condition reference must
resolve to exactly one bound runtime instance; zero matches and multiple matches
are both compile-time diagnostics. Event inject refs resolve directly to
top-level inject resources and fail if the named inject does not exist.
Bound feature dependencies also fail closed: if a node-scoped feature binding
declares a dependency on another feature that is not bound on the same node,
the compiler emits a diagnostic instead of silently dropping that dependency.

Compiled workflows are not just flattened successor maps. `WorkflowRuntime`
preserves:

- `start_step`
- optional workflow timeout policy in the compiled execution contract
- per-step structured semantics (`objective`, `decision`, `switch`, `retry`, `call`, `parallel`, `join`, `end`)
- explicit call targets and ordered switch-case predicates
- explicit control edges
- external predicate dependencies
- prior-step state dependencies
- declared workflow feature usage
- a compiled `result_contract` for step-visible state
- a compiled `execution_contract` for workflow-level state/history validation

Workflow control is the flagship current `FM3` surface:

- it has explicit branching and re-entry behavior
- it defines portable execution-visible state
- it relies on reachability and visibility guarantees across multiple layers

That means workflow changes should be treated as state-machine work on the
runtime model and contracts, not merely as YAML authoring changes.

The intent is not to clone any one system. The SDL keeps its own
objective-centric workflow surface, but its semantics deliberately follow the
best-practice pattern from mature systems: explicit branching semantics,
explicit convergence rules, typed observable state, and a runtime contract that
is portable across backend implementations.

### 2. Plan

`plan(runtime_model, manifest, snapshot, target_name=None)` is also pure.

It validates semantic backend requirements and reconciles desired runtime
objects against the current `RuntimeSnapshot`.

`ExecutionPlan` is composite:

- `ProvisioningPlan` for deployable resources and bindings
- `OrchestrationPlan` for events, scripts, stories, workflows, and inject state
- `EvaluationPlan` for condition bindings and objectives

Each plan is provenance-bound to:

- an optional target name
- the backend manifest used for validation
- the base snapshot it was reconciled against

Direct planner output is unbound by default. Only `RuntimeManager.plan()` or an
explicit `target_name=` bind a plan to a concrete runtime target for apply.

Reconciliation actions are explicit:

- `CREATE`
- `UPDATE`
- `DELETE`
- `UNCHANGED`

Runtime resources carry two dependency sets:

- `ordering_dependencies`: same-domain edges used for create/start ordering and reverse delete ordering
- `refresh_dependencies`: edges whose changes force downstream `UPDATE`

Cross-domain refs participate in refresh propagation, but not startup ordering.
This keeps the fixed phase order intact while still making downstream plans
honestly react to upstream changes.
Ordering graphs must remain acyclic within each domain; the planner emits error
diagnostics and invalidates the plan if a cycle survives into runtime planning.

### Reference processor

`raes_processor.reference.run_reference_processor(scenario, backend_manifest)`
(and the `ReferenceProcessor` class) is the repository-owned reference
implementation of the processing model. It assembles the stages above into one
call — accepting SDL text, a file path, or an already-parsed scenario — and
returns a `ReferenceProcessorResult` carrying the compiled `RuntimeModel`, the
`ExecutionPlan`, and the combined compilation + planning diagnostics
(`is_valid` is false when any are errors). `ReferenceProcessor.manifest_payload()`
exposes the published processor manifest through the canonical renderer.

Per ADR-008 the processor is the semantics-bearing layer between SDL authoring
and backend realization, so the reference processor's responsibility ends at the
`ExecutionPlan`: it imports only the SDL/processor/contract layers and never
`raes_runtime` (the one-directional boundary enforced by
`tools/policy/adr_policy.yaml`). End-to-end execution is realized by composing
its plan with the reference runtime (`RuntimeManager` / `RuntimeControlPlane`);
the backend-conformance live probe drives exactly this composition, and the
RUN-313 tests use it to prove every contract version the processor manifest
declares is exercised end to end.

## Runtime Snapshot

`RuntimeSnapshot` is the typed state model used by the planner and manager. Each
entry records:

- canonical address
- domain
- resource type
- resolved payload
- ordering dependencies
- refresh dependencies
- current status

This gives the planner and manager a typed state model instead of an untyped
`resources/status` map.

The broader time model is only partly materialized in current contracts. The
implemented snapshot and control-plane schemas carry timestamps and
timeout-related state, but they do not fully represent clock authority, time
domain, synchronization policy, pacing mode, or realized temporal guarantees.
Those concerns belong to the declared apparatus surface and to archival
provenance when implementations compare different realizations.

## Capability Validation

Backends and processors publish a shared apparatus-manifest envelope with:

- `identity`
- `supported_contract_versions`
- `compatibility`
- `realization_support`
- `constraints`
- `capabilities`

Backend manifests preserve nested concern blocks inside `capabilities`:

- `provisioner`
- `orchestrator`
- zero or one `evaluator`

Processor manifests preserve processor-specific capability blocks inside `capabilities`:

- `supported_sdl_versions`
- `supported_features`

At the ecosystem level, backend manifests are only one declaration surface.
The reference processor publishes the same shared envelope with processor-specific capabilities.
Participant-implementation manifests are a distinct apparatus surface. They
publish `participant-implementation-manifest-v1`, which declares implementation
identity, implementation kind, supported participant contracts, supported
decision-surface modes, tool and affordance expectations, compatibility,
concept bindings, and constraints.

Validation is semantic, not section-only. Current checks include:

- node types
- OS families
- total deployable node count
- ACL usage
- content types
- account features
- orchestration/workflow usage
- fine-grained workflow feature usage (`decision`, `retry`, `parallel` barriers, failure transitions)
- workflow predicate assertion refs
- workflow predicate prior-step state refs and state-predicate subfeatures (`outcome-matching`, `attempt-counts`)
- objective usage

`OrchestratorCapabilities` expose both coarse workflow support and fine-grained workflow semantics:

- `supports_workflows`
- `supports_assertion_refs`
- `supported_workflow_features`
- `supported_workflow_state_predicates`

Both the backend and processor manifest surfaces also carry explicit
`realization_support` declarations. These make constrained realization and its
required disclosures visible in the machine-readable apparatus boundary rather
than leaving them implied by docs or implementation code.

The shared manifest envelope is enforced as a concrete declaration surface,
not just a shape:

- `compatibility` must name at least one compatible processor, backend, or
  participant implementation
- every `realization_support` declaration must name non-empty disclosure kinds
  and at least one supported exact or constraint kind
- processor capability blocks must declare non-empty SDL and feature support
- backend capability blocks must declare concrete provisioning and orchestration
  support, not empty concern shells

The reference backend, reference processor, and backend conformance profiles use
the shared `v2` apparatus manifests. Legacy `v1` manifest schemas remain in the
repo as deprecated reference artifacts, not as the current conformance target.
Participant implementations use `participant-implementation-manifest-v1`
alongside the backend and processor surfaces rather than nesting inside either
one.

Capability validation operates on admitted concrete values. Where
`nodes.os` or `infrastructure.count` was selected from an authored finite
domain, portable SDL provenance carries that domain and the compiler lowers it
to one typed `CompiledCapabilityConstraint`; the planner validates the whole
declared domain against backend limits. It does not reconstruct variable
definitions or pair private variable-spec/ref maps.

## Runtime Target Lifecycle

Targets must provide an explicit manifest. The registry separates capability
inspection from instantiation, and `create()` uses the manifest returned by
`manifest()` as its single source of truth:

- `registry.manifest(name, **config)`
- `registry.create(name, **config)`

`RuntimeManager` drives lifecycle in this order:

1. compile
2. plan
3. validate provisioning apply
4. apply provisioning plan
5. start evaluator only when the evaluation plan has actionable operations
6. start orchestrator only when the orchestration plan has actionable operations
7. on failed runtime-service startup, roll back started services while keeping provisioning state
8. stop orchestrator -> stop evaluator -> delete provisioning resources

Participant implementations do not collapse into the backend boundary. The
backend remains responsible for world realization and execution services;
participant implementations are a separate apparatus concern whose identity,
configuration, and participant-visible decision surface belong in
`participant-implementation-provenance-v1` rather than being inferred from
backend state.

The orchestration runtime contract includes:

- a plain-data workflow execution-state envelope
- a plain-data workflow history stream
- a compiled `result_contract` for step-visible state
- a compiled `execution_contract` for workflow-level legality/history validation
- control-plane operations for canceling running workflows and reconciling timeout expiry
- explicit compensation status/history when a workflow declares rollback behavior

Backends report portable execution envelopes rather than backend-native object
identity. The manager validates raw backend payloads against the compiled
contracts, not against incidental planner payload structure. Compiled workflow
predicates are fully typed runtime data; orchestrators should not rely on raw
SDL `spec` to execute workflow semantics.

Python typed workflow result models remain useful internally, but only as
normalization helpers after boundary validation. They are not the backend
protocol.

This is also why semantic modeling is split across processor and runtime
contracts rather than parser code. The processor compiles backend-agnostic
guarantees such as allowed transitions, result visibility, and portability of
workflow state; the runtime validates live backend reports against those
compiled contracts.

This mirrors the contract style used by mature multi-runtime systems:

- a portable wire/data contract at the boundary
- a compiled semantic contract between definition and execution
- published machine-readable JSON Schemas under `contracts/schemas/`
- an async-style control-plane surface (`RuntimeControlPlane`) that can be
  adapted to HTTPS/JSON without changing backend semantics
- typed in-process adapters behind that boundary

The stack currently applies that pattern first to workflow results because workflow
control is the sharpest semantic surface in the SDL/runtime stack.

The evaluator side follows the same contract discipline: compiled
evaluation result/execution contracts are attached to observable evaluation
resources, backends report plain-data evaluator result envelopes and history
streams, and the manager validates those payloads against compiled contracts
instead of accepting ad hoc evaluation dictionaries.

Objective `window` refs remain declarative scope/refresh inputs. They can force
objective refresh when referenced orchestration state changes, but they do not
create executor ordering edges across domains.

Objective windows compile through one shared normalized semantic form. The
compiler preserves explicit resolved window references alongside the existing
address sets so planner/runtime code can reason from canonical reference
identities instead of reparsing raw SDL strings.

Planner FM2 semantics are explicit rather than incidental:

- `ordering` edges define create/start and delete/teardown order
- `refresh` edges define recomputation/update propagation
- refresh propagation is transitive over the refresh graph
- cross-domain refresh does not create startup ordering

Those rules are owned by `raes_processor.semantics.planner`, not by local planner
algorithm shape.

This phase is also intentionally composition-ready. Module/import expansion
happens before semantic validation and compile, so the runtime layer operates
only on canonical resolved identities rather than on source-file layout. That
same foundation is what makes namespaced reusable workflow calls portable.

Composition is registry-ready as well:

- local imports remain supported through `path:` and `source: local:...`
- reusable remote modules use `source: oci:...`
- concrete resolved imports may be pinned via `source: locked:...`
- `raes sdl resolve` writes `raes.lock.json`
- `raes sdl verify-imports` verifies lockfile, trust, digests, and signatures
- `raes sdl publish` packages a publishable SDL module as an OCI image layout

OCI acquisition bounds the compressed response and the complete decoded tar
stream before parsing any tar header. The decoded-stream limit includes PAX/GNU
metadata and padding and has both absolute and expansion-ratio ceilings. Safe
extraction requires the standard-library `data` filter; Python 3.11.0 through
3.11.3 fail closed for OCI extraction rather than using unfiltered extraction.

Resolved module caches and published layouts use immutable version directories
under a logical slot plus one atomically replaced `.raes-current` pointer. A
cache hit streams a trusted expected inventory directly from the verified,
bounded tar, then re-hashes the exact extracted tree against its canonical
completion manifest. The comparison covers every path and entry type plus each
file's filtered mode, size, and digest. The cache's own writable manifest is not
its authority. A hit performs no extraction or version staging; only the
bounded decoded-tar spool may spill beyond its memory threshold. Missing,
extra, linked, mode-changed, byte-changed, or coordinated tree-plus-manifest
edits rebuild cleanly.
Publication returns the selected immutable OCI-layout version path; a failed
writer leaves the prior pointer and every extant reader path intact. Startup
repair removes incomplete stages and can repoint to a complete validated orphan
version left by process death.

For publication, the stable `<module>-<version>.oci` name is the private logical
slot, not a directly consumable OCI layout. CLI/API `layout_dir` points to the
selected immutable `versions/<id>` child, which contains the standard
`oci-layout`, `index.json`, and `blobs/` inventory. Consumers should use that
reported path rather than infer the slot. Each slot retains at most eight
complete versions: current, the immediately prior pointer target, and the
newest remaining versions. This window protects an in-flight prior reader but
is not archival retention; push or copy layouts that must outlive later
publications.

An older root-level OCI layout at the stable slot name is not silently upgraded
into a dual layout. Publication fails with instructions to move or remove that
legacy output first, preventing older consumers from continuing to read stale
root `index.json` and `blobs/` while newer consumers use a version child.

Resolution and trust happen before instantiation and semantic validation.
Planner/runtime semantics see one admitted concrete scenario; replay-relevant
resolution and binding facts remain under its typed provenance rather than in
live imports, variables, or Python-private side channels.

`RuntimeManager.apply()` requires the plan provenance to match the manager:

- plan must be target-bound
- same target name
- same manifest
- same base snapshot

This prevents applying a plan against a different runtime target or a stale
snapshot than the one it was reconciled against.

`RuntimeTarget` is self-validating at construction time:

- manifest presence and component shape must match
- required protocol methods must exist
- those methods must be invokable with the runtime's actual call shapes, not
  just be present by name

`RuntimeManager` also hardens the execution boundary at call time. Backend
exceptions and invalid lifecycle return payloads are converted into structured
runtime diagnostics instead of surfacing as unhandled crashes.

The HTTP adapter defaults to a fail-closed security configuration: no trusted
header identities and no bearer tokens are built in. Deployments that use
header identity must pass an explicit `ControlPlaneSecurityConfig`, set
`trust_proxy_identity_headers=True`, and only trust those headers behind an
authenticated proxy that strips caller-supplied identity headers.

The local control-plane store persists snapshots, operations, idempotency
claims, and audit events in a single SQLite WAL database. Full synchronous
transactions and a unique idempotency index make concurrent same-host writers
and participant transition commits atomic. Each authoritative snapshot is
paired with a non-negative logical revision. Every snapshot-bearing mutation
must supply the revision it observed, and compare-and-swap validation happens
in the same lock or SQLite transaction as the snapshot, operation, and audit
writes. A stale writer therefore changes none of them. An exact retry of an
already committed terminal operation returns the durable state without
incrementing its revision. A backend claim is stored before execution, and its
resulting snapshot and terminal operation record commit in one transaction.
Startup marks an orphaned non-terminal record `FAILED` with
an explicit indeterminate-outcome diagnostic and never replays it; retaining
the idempotency claim prevents a retry from blindly repeating backend effects.
On first use, legacy JSON state is imported without deleting its source and is
copied to a timestamped backup. Payload digests and SQLite integrity checks
detect accidental durable-state corruption. Owned POSIX store directories are
created or migrated to `0700` and the main SQLite database to `0600`. SQLite
alone owns descriptors for the main database, WAL, shared-memory, and rollback
journal. OpenRÆ uses descriptor-free metadata inspection and path-based mode
tightening for type, owner, private-mode, and main-database same-file checks,
so an independent `close()` cannot cancel SQLite's POSIX locks. Existing opens
use URI `mode=rw`; only first creation uses
`mode=rwc`, preventing a disappeared database from being silently recreated.
The initialized database identity remains pinned for the store lifetime, and
hard-linked aliases are rejected. Unsafe symlink, reparse, type, owner, mode, or
identity changes fail closed. Snapshot revision conflicts are known non-commits:
the runtime rebuilds its derived caches and fails the caller without sealing a
running operation. If another commit error leaves its outcome uncertain, the
runtime reloads both durable caches; a failed reload poisons the runtime until
restart rather than allowing another mutation from stale state. Snapshot-derived
HTTP reads return `X-RAES-Snapshot-Revision`, and participant view source refs
bind the same pinned state cut; nested read or governed-projection work cannot
rebind the response to a later revision. An explicitly supplied operation base
snapshot must equal the authoritative content observed for the commit, while an
already committed exact idempotent retry returns before attempting a new
mutation. The provider-only revision is stored beside the durable snapshot and
is not added to portable snapshot bodies, metadata, digests, or schemas.

Built-in stores use the complete crash-atomic commit capability. Existing 3.x
custom `ControlPlaneStore` adapters remain accepted when they implement the
revision-aware structural contract, including paired snapshot reads and
revision-checked snapshot writes. A centralized compatibility seam warns once
per runtime and uses lookup-then-save claims, ordered snapshot/record writes,
and per-record recovery. Stores that cannot compare and swap an observed
snapshot revision are rejected instead of synthesizing revision authority. The
compatibility mode preserves legacy atomicity behavior but has documented claim
and terminal-write race/crash windows and is scheduled for removal in version
4; custom adapters should implement `claim_record` and both atomic
terminal/recovery methods before upgrading.

The local runtime is deliberately single-process. Its logical revision prevents
stale writes but is not a distributed ownership or availability mechanism, so a
non-blocking filesystem lease admits one `RuntimeControlPlane` owner and rejects
another, including inherited post-fork use. POSIX runtimes also hold a
store-directory guard so
unlinking or replacing the owner-file path cannot admit a second owner. Close
drains admitted composite calls, including their nested guarded work, before it
releases authority. Run one ASGI worker with reload disabled. This is a
single-host reference boundary, not a distributed queue, replication, or
multi-host availability claim.

Bearer and verified-proxy authentication require the same exact target binding.
An identity with no target, and an explicitly supplied bearer that is unknown,
revoked, or scoped to another target, is rejected; a rejected bearer never
falls back to proxy headers. Request admission is also bounded before FastAPI
parses or dispatches a body: a public ASGI wrapper checks one digits-only
`Content-Length`, then consumes at most the configured byte limit and replays
one coalesced body message. This boundary does not rely on framework-private
request caches and returns a stable `413` before a route can run.

The HTTP adapter offloads synchronous backend and store calls to AnyIO's
bounded worker pool. An application-scoped async lock serializes target
mutations without occupying a worker while requests wait; independent reads
remain responsive while a backend is slow. The pending mutation count is
bounded by `ControlPlaneSecurityConfig.max_pending_mutations` and overload
returns `503` plus `Retry-After`. This in-process execution boundary neither
replaces backend I/O timeouts nor claims durable or distributed job queuing.
Request-size rejection also offloads audit persistence; an audit-store failure
cannot admit an invalid body or replace the stable `400`/`413` response. These
pre-routing audits use a separate one-worker limiter and a bounded pending
count, so an unauthenticated rejection flood cannot consume the default AnyIO
workers required by authenticated reads; excess audit records are dropped with
an operational warning.

## Current Scope

The current runtime scope includes:

- compiler
- planner
- runtime manager
- registry
- control plane, HTTP adapter, operation store, security, and audit
- honest in-memory stubs
- tests and docs

Real Docker/cloud/simulation backends are outside this repository's current
implementation surface. Such backends would have to consume and satisfy these
contracts.
