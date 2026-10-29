# Runtime architecture: SDL processor runtime backend

## Shared engine and workload composition

RAE supplies the common execution engine for CTFs, experiments, product tests, and simulated enterprises.
Each workload uses SDL processing, processor plans, shared runtime execution, and injected backend services.
The admitted inputs select the needed modules.
These drive workflows, participants, time, evaluation, and cleanup.
An experiment adds selection, allocation, and run accounting to this common path.
Ordinary SDL execution needs no experiment wrapper.
The engine can keep a run open for later work.
Each run keeps its own state and results.
Finishing one run must not erase its history.
Reusing its target needs proof that the target is safe to reuse.

The public controller owns shared execution services and a fixed default run.
`open_run()` adds a fixed run context with a separate scope-bound store.
Each context uses the same engine capacity and backend ownership.
The [shared-runtime design](../../decisions/issue-1629-shared-runtime-design.md) contains component, lifecycle, and data flow diagrams.
Its [remediation plan](../../decisions/issue-1629-runtime-remediation-plan.md) records the approved ownership refactor and acceptance tests.
`admit_experiment()` installs experiment accounting inside this owner.
`advance_experiment()` drives the selected runs through the shared plan phases.

Temporal is already available for individual remote operations.
The runtime supplies operation and control workflows, scoped workers, and a PostgreSQL ledger.
[ADR-113](../../decisions/adrs/adr-113-reusable-execution-machinery.md) places this machinery under RAE's execution rules.
The `raes.run` and `raes.experiment` workflows drive the same progress functions as local callers.
Their activities call the authenticated `/runtime/progress` state endpoint.
Workflow payloads contain references and status; artifact owners retain plans and evidence.
Temporal supplies durable progress and delivery.
RAE still owns admission, run state, retry permission, and verified outcomes.
Local execution needs no Temporal service, and the coordinated P3 profile remains unavailable.
The sections below describe the existing processor and runtime path.

## Existing execution path

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
matter. SDL can define timelines, deadlines, timeouts, and episode budgets.
Execution also depends on the chosen clock, time domain, pacing, and synchronization rules.
The runtime and backend must establish the requested order of work.
These choices affect experiment validity.
Declare them and keep them in run provenance when comparing realizations.

Autonomous participant execution follows the same separation. Compilation
preserves exact action-to-target-service bindings; planning admits those
relations against the backend manifest; and the runtime owns a typed,
generation-fenced execution-service scope. Native calls may overlap within a
finite admitted bound, but portable snapshot/history commits are serialized
with revision checks. Shared-clock pause, resume, and reset coordinate service
readiness and generation, while pacing loss is published as degraded,
not-ready state with an explicit deviation reference.

Under the repository's [coding standards](../reference/coding-standards.md),
this layer is where `FM2` and `FM3` work becomes most relevant. Formal work here targets the typed runtime model, plans, and execution contracts.
It preserves meaning through validation, compile, plan, and backend execution.
Raw YAML is outside that formal target.

This layer also draws from a different precedent set than the author-facing SDL
surface. OCR and CACAO still matter, but the strongest implementation models
here come from mature workflow and distributed-runtime systems:

- AWS Step Functions, Argo Workflows, and W3C SCXML for explicit control-flow
  semantics
- Kubernetes, Temporal, and OpenC2 for portable execution-state and
  language-neutral contract boundaries

## Package boundary

RAE is the shared product runtime driving the backends; backend ownership of
concrete realization does not imply a separate scenario runtime per backend.
The [operation supervision decision](../../decisions/issue-1348-operation-lifecycle.md)
defines how authored guarantees, contextual refusal, cancellation and recovery
compose. The runtime now bounds external calls and drain through shared execution adapters.
A timed-out call keeps its physical slot until it exits.
Durability does not imply interruption or permission to resume effects.
Operational budgets remain separate from authored scenario clocks.
Physical-OT protections apply only when the authored requirements select them.

```text
raes                -> parse + instantiate + SDL-language semantics
raes_processor          -> compile + plan + support/contract semantics
raes_runtime            -> live control + manager + control-plane APIs
raes_backend_protocols  -> backend capability/protocol declarations
raes_backend_stubs      -> non-normative in-memory target implementations
```

ADR-036 enforces this boundary through `tools/check_repo_policy.py`.
The full policy gate scans each Python package root.
The pre-commit gate checks the staged files against the same rules.

## Runtime stages

Negotiated backends also return a distinct descriptive SDL phase after
materialization hooks. The runtime admits it against the original source,
execution and complete scoped inventory, then publishes protected SDL bytes
before persisting archive references. This does not replace realization
authority, evidence acquisition or the original scenario snapshot. See
[materialization attestations](../reference/materialization-attestations.md).

### 1. Instantiate compile

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

These compiled declarations and installed plans do not establish live inject
execution. [ADR-112](../../decisions/adrs/adr-112-external-inject-triggering-and-execution.md)
defines the accepted [external occurrence contract](../../../specs/sdl/external-injects.md):
the shared runtime admits and drives an exact authored binding, and the backend
supplies per-target effect evidence. Participant disclosure, delivery and
observation remain separately authorized facts. Current bound/queued receipts
retain their original meaning; executable support requires the coordinated
[adoption boundary](external-inject-compatibility.md).

The output is a `RuntimeModel` with canonical addresses for every runtime-owned
object.

Bound condition refs fail closed. An unqualified condition reference must
resolve to exactly one bound runtime instance; zero matches and multiple matches
are both compile-time diagnostics. Event inject refs resolve directly to
top-level inject resources and fail if the named inject does not exist.
Bound feature dependencies also fail closed.
A feature binding may depend on another feature on the same node.
If that feature is absent, the compiler emits a diagnostic.
It does not drop the dependency.

Compiled workflows preserve more than successor maps. `WorkflowRuntime`
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

The SDL keeps its own objective-based workflow surface.
It follows proven patterns from mature systems.
Branches and convergence have explicit rules.
Observable state has a type.
The runtime contract works across backends.

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

`raes processor reconcile <v1> <v2> --format json` shows this process.
It plans `v1` and projects the plan into a snapshot.
It then plans `v2` against that snapshot and reports each action. The worked pair is
[`examples/scenarios/reconciliation-demo-v1.sdl.yaml`](../../../examples/scenarios/reconciliation-demo-v1.sdl.yaml)
and its `-v2` counterpart. The projected snapshot is assumed state for inspection.
It is not backend readback, a durable checkpoint, or proof of realization.
Durable snapshots belong to the runtime stores.

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
implementation of the processing model. It combines the stages above in one call.
Inputs can be SDL text, a file path, or a parsed scenario.
It returns a `ReferenceProcessorResult` with the compiled model, plan, and diagnostics.
`is_valid` is false when any diagnostic is an error. `ReferenceProcessor.manifest_payload()`
exposes the published processor manifest through the canonical renderer.

ADR-008 places the processor between SDL authoring and backend realization.
The processor's work ends at the `ExecutionPlan`.
It imports only SDL, processor, and contract layers.
It never imports `raes_runtime`.
`tools/policy/adr_policy.yaml` enforces that boundary.
The reference runtime executes the plan.
The live backend probe tests this path.
RUN-313 tests exercise each contract version declared by the processor manifest.

## Runtime snapshot

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

The broader time model is only partly materialized in current contracts. The snapshot and control-plane schemas carry timestamps and timeout state.
They do not fully describe clock authority, time domain, synchronization rules, pacing, or realized time guarantees.
Those concerns belong to the declared apparatus surface and to archival
provenance when implementations compare different realizations.

## Capability validation

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

The shared manifest envelope has rules beyond its shape:

- `compatibility` must name at least one compatible processor, backend, or
  participant implementation
- every `realization_support` declaration must name non-empty disclosure kinds
  and at least one supported exact or constraint kind
- processor capability blocks must declare non-empty SDL and feature support
- backend capability blocks must declare concrete provisioning and orchestration
  support, not empty concern shells

The stub double, reference processor, and backend conformance profiles use
the shared `v2` apparatus manifests. Legacy `v1` manifest schemas remain in the
repo as deprecated reference artifacts, not as the current conformance target.
Participant implementations use `participant-implementation-manifest-v1`
alongside the backend and processor surfaces rather than nesting inside either
one.

Capability validation operates on admitted concrete values. An authored finite domain can supply `nodes.os` or `infrastructure.count`.
Portable SDL provenance keeps that domain.
The compiler emits one typed `CompiledCapabilityConstraint`.
The planner checks the whole domain against backend limits. It does not reconstruct variable
definitions or pair private variable-spec/ref maps.

## Runtime target lifecycle

One `RuntimeControlPlane` instance directs the backend for the interaction.
`RuntimeManager` is a compatibility name for that same class.
The owner keeps the operation ledger, snapshot, resource claim, and lifecycle.
Apply, later evaluation, inventory, time control, and teardown use that owner.

`runtime.evaluate(execution_plan, idempotency_key="evidence-2")` evaluates later
evidence without applying provisioning or restarting orchestration.
It replans the original compiled model with `refresh_evaluation=True`.
The planner emits evaluation updates even when the declared resources are unchanged.
The refresh preserves the original run and instantiation scope.
Each fresh evaluation needs a fresh key.
An exact retry uses its original key and returns the retained receipt.

Select optional target components before construction.
`scenario_component_options()` derives the existing factory options from the compiled model.
The stub factory also accepts `scenario=` for this selection.
Required capability checks and manifest/component agreement remain in force.
Participant scheduling starts only when the scenario requires autonomous execution.

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
7. on failure, follow the authored execution policy and preserve committed state and uncertain-effect exclusion
8. for admitted teardown, stop orchestrator -> stop evaluator -> delete provisioning resources; stop dependent work if a phase fails

The [runtime migration guide](../../migration/runtime-lifetime.md) covers run scope,
fresh evaluation, and the existing failure and recovery rules.

Participant implementations do not collapse into the backend boundary. The backend owns world realization and execution services.
Participant implementations have their own identity, settings, and visible decision surface.
Keep those facts in `participant-implementation-provenance-v1`.
Do not infer them from backend state.

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

The evaluator follows the same contract rules.
Observable evaluation resources carry compiled result and execution contracts.
Backends report plain-data results and history.
The runtime checks these reports against the compiled contracts.
It rejects ad hoc result dictionaries.

Objective `window` refs remain declarative scope/refresh inputs. They can force
objective refresh when referenced orchestration state changes, but they do not
create executor ordering edges across domains.

Objective windows compile through one shared normalized semantic form. The compiler keeps resolved window refs beside the address sets.
Planner and runtime code can use these canonical identities.
They do not need to parse the SDL strings again.

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
extraction always uses the standard-library `data` filter.

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
into a dual layout. Publication fails until that legacy output is moved or removed.
The error explains this required step.
This prevents old readers from using stale root `index.json` and `blobs/` beside a new version child.

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
  exist by name alone

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
paired with a non-negative logical revision. Each snapshot write must supply the revision it observed.
Check CAS in the same lock or SQLite transaction as the snapshot, operation, and audit writes. A stale writer therefore changes none of them. An exact retry of an
already committed terminal operation returns the durable state without
incrementing its revision. A backend claim is stored before execution, and its
resulting snapshot and terminal operation record commit in one transaction.
Startup checks each unfinished record without replay.
A proven absent effect becomes `FAILED` or `CANCELLED`.
A checked, observed effect becomes `SUCCEEDED`.
An outcome that cannot be proved becomes `INDETERMINATE`. Retaining the idempotency claim prevents a retry from blindly
repeating backend effects, and resolving an indeterminate outcome creates a
linked operation instead of rewriting the original.
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
running operation. If a commit error leaves its outcome unknown, reload both durable caches.
If that reload fails, poison the runtime until restart.
Do not allow another write from stale state. Snapshot-based HTTP reads return `X-RAES-Snapshot-Revision`.
Participant view source refs bind that same state cut.
Nested reads and governed projections cannot bind the response to a later revision. A supplied base snapshot must match the state observed for the commit.
An exact retry of committed work returns its retained result.
It does not attempt a new mutation. The provider-only revision is stored beside the durable snapshot and
is not added to portable snapshot bodies, metadata, digests, or schemas.

Built-in stores use the complete crash-atomic commit capability. Existing 3.x
custom `ControlPlaneStore` adapters remain accepted when they implement the
revision-aware structural contract, including paired snapshot reads and
revision-checked snapshot writes. A centralized compatibility seam warns once
per runtime and uses lookup-then-save claims, ordered snapshot/record writes,
and per-record recovery. Stores that cannot compare and swap an observed
snapshot revision are rejected instead of synthesizing revision authority. The compatibility mode keeps legacy atomicity behavior.
It has known claim and terminal-write race and crash windows.
Its removal is scheduled for version 4.
Before upgrading, custom adapters should implement `claim_record` and both atomic terminal and recovery methods.

The local runtime is deliberately single-process. Its logical revision prevents stale writes.
It does not grant distributed ownership or availability.
A non-blocking file lease admits one `RuntimeControlPlane` owner.
It rejects other owners, including inherited post-fork use. POSIX runtimes also hold a
store-directory guard so
unlinking or replacing the owner-file path cannot admit a second owner. Close
drains admitted composite calls, including their nested guarded work, before it
releases authority. Run one ASGI worker with reload disabled. This is a
single-host reference boundary, not a distributed queue, replication, or
multi-host availability claim.

The reference provider's operator procedures, including value-free health
probes, shutdown ordering, recovery classification, and lease-admitted local
store check/backup/restore commands, are documented in the
[Control-Plane Recovery Operations runbook](control-plane-operations.md).
Database restore does not establish equivalent external backend state.

Bearer and verified-proxy authentication require the same exact target binding.
Reject an identity with no target.
Also reject a supplied bearer that is unknown, revoked, or bound to another target.
A rejected bearer must not fall back to proxy headers. Request admission is bounded before FastAPI parses or dispatches a body.
A public ASGI wrapper checks one digits-only `Content-Length`.
It reads at most the configured byte limit.
It then replays one combined body message. This boundary does not rely on framework-private
request caches and returns a stable `413` before a route can run.

The HTTP adapter offloads synchronous backend and store calls to AnyIO's
bounded worker pool. An application-scoped async lock serializes target
mutations without occupying a worker while requests wait; independent reads
remain responsive while a backend is slow. The pending mutation count is
bounded by `ControlPlaneSecurityConfig.max_pending_mutations` and overload
returns `503` plus `Retry-After`. This in-process execution boundary neither
replaces backend I/O timeouts nor claims durable or distributed job queuing.
Request-size rejection also offloads audit persistence; an audit-store failure
cannot admit an invalid body or replace the stable `400`/`413` response. These audits use a separate one-worker limiter and a bounded queue.
A flood of rejected requests cannot consume the AnyIO workers needed for authenticated reads.
Excess audit records are dropped with an operational warning.

## Control-plane operating profiles

An embedder selects a profile explicitly through the typed
`raes_runtime.ControlPlaneProfile` API. `profile_declaration()` returns the
canonical immutable declaration for any of P0–P3, including the guarantees,
nonclaims, required capability identifiers, target/run scope, and actor
boundary. A selected profile fails construction if the store or composition
cannot supply its required facts; it never falls back to a weaker profile.
Existing callers that omit selection continue to work, but their compositions
make no named profile claim.

| Profile | Guarantee identifiers | Nonclaim identifiers |
| --- | --- | --- |
| P0 | in-process-safety, actor-scoped-idempotency, target-run-isolation, revision-cas, atomic-audit | durability, restart-recovery, multi-owner, high-availability, exactly-once-effects, multitenancy |
| P1 | in-process-safety, actor-scoped-idempotency, target-run-isolation, revision-cas, atomic-audit, durable-state, retained-idempotency, lease-admission, startup-reconciliation | multi-owner, high-availability, exactly-once-effects, multitenancy |
| P2 | in-process-safety, actor-scoped-idempotency, target-run-isolation, revision-cas, atomic-audit, durable-state, retained-idempotency, lease-admission, startup-reconciliation, authenticated-transport, actor-bound-disclosure, owner-serialized-mutation, revision-carrying-reads | multi-owner, multi-worker, tls-proxy-deployment, high-availability, exactly-once-effects, multitenancy |
| P3 | none | future-coordination |

P0 uses an in-memory store for one target and one run, with an actor supplied
by the trusted embedding process. Its audit and idempotency guarantees last
only as long as that process. P1 uses a transactional local store, one
process-bound owner lease, revision checks, atomic terminal audit, and startup
classification of interrupted operations. A backend recovery observer is
optional: when an effect cannot be established, the operation becomes
`INDETERMINATE` without automatic replay. P2 is the reference HTTP adapter
over an explicitly selected P1 core. It derives the actor from authenticated
HTTP identity and keeps P1's one-target, one-run scope. A bare core cannot
claim P2, and P3 is inspectable but unavailable pending a future coordination
decision.

For an in-process P0 composition, pass `profile=ControlPlaneProfile.P0` to
`RuntimeControlPlane`. For a durable local P1 composition, pass a
`LocalControlPlaneStore` and `profile=ControlPlaneProfile.P1`; construction
admits its owner lease. To serve that
core, pass `profile=ControlPlaneProfile.P2` to `create_control_plane_app()`;
the app exposes the same canonical declaration to its embedder through
`app.state.control_plane_profile`. Store providers declare facts through
`ControlPlaneStoreCapabilities`; they do not name or choose a profile.

The library owns operation bookkeeping, receipts, snapshots, participant
transitions, audit, and profile admission. The embedding application owns its
target/run selection, process lifecycle, actor source for P0/P1, and upgrade
sequence. P2 deployment owns TLS termination, trusted-proxy header stripping,
secret loading, worker configuration, service credentials, process supervision,
and backup policy. Profile metadata is in-process discovery, not a health
signal, HTTP discovery endpoint, availability promise, or tenant-multiplexing
contract.

Participant clients access a trusted host application, which may embed P0/P1
as an SDK or use the optional P2 HTTP adapter. The host keeps the SDK control-plane object or P2 identity private.
It binds each caller to a target, run, participant, exact episode, audience, and operation.
Only then may it release a governed API-408 view. SDK calls have no HTTP role gate; a P2 identity with
read access to participant views can also read the full snapshot. Neither
path authenticates the host's end user or turns a legacy view without a
configured crossing resolver into governed participant output. An
organizational host owns organizational identity and policy; a local host
applies its own caller boundary. The accepted
[route and deployment boundary](../../decisions/issue-1356-control-plane-participant-access-preflight.md)
also covers operation readback, histories, errors, caches and events.

Every served P2 route declares exactly one transport authority: public probe,
administrative read, administrative mutation or operator resolution.
`create_control_plane_app()` refuses a route with none or several, and exposes
the `(method, path)` inventory as `app.state.control_plane_route_authority`.
Participant, audience, controller and operation-actor checks follow in the
core. Every response carries `Cache-Control: no-store`. The
[deployment guide](../../public/guides/control-plane.md) covers the host's
duties.

## Current scope

The current runtime scope includes:

- compiler
- planner
- shared runtime engine and fixed run contexts
- optional experiment sequencing and result accounting
- local and Temporal progress drivers
- registry
- control plane, HTTP adapter, operation store, security, and audit
- honest in-memory stubs
- tests and docs

Real Docker/cloud/simulation backends are outside this repository's current
implementation surface. Such backends would have to consume and satisfy these
contracts.

## Optional backend operation contracts

The [operation-supervision family](../../../specs/formal/runtime-contracts/backend-operation-supervision.md)
publishes the portable backend boundary for the accepted supervision design.
It separates capability, willingness, acknowledgement, progress, control
dispositions and scoped effect evidence. RAE retains native result validation
and atomic terminal publication. The [migration guide](../reference/backend-operation-supervision.md)
explains the additive profile and the limits of legacy conversions. These
contracts do not enable a new RuntimeTarget provider or change P0–P3 guarantees.

## Complete experiment records

Every started trial remains visible through its allocated run identity and distinct attempt identities.
The existing decision store retains live progress, failures, and unresolved effects.
Run and study records preserve that history independently of scientific evidence acceptance.
Partial records state which facts are unavailable; they do not invent completion, measurements, or cleanup success.
Execution, capture, validation, and cleanup outcomes remain separate.
Scientific outcomes come from explicit evaluation facts; successful execution does not establish scientific success.
Export and archive publication do not grant permission to retry or reuse resources.
Evidence-owner failures preserve records with a separate failed-check disposition.
Proof limits do not truncate retained evidence history.
Study membership and metric eligibility share the same replacement-aware population.
Each archive write verifies the exact frozen version at the supplied destination.
The record producer and replacement archive share version ownership across retained decisions.
Both freeze candidates before external archive writes, including writes with uncertain acknowledgements.
An additional accounting version can link to an exact scientific artifact without moving its proof.
Study evaluation membership and returned validation records identify the original checked version.
The [complete accounting design](../../decisions/issue-1630-run-accounting-design.md) describes data flows, security controls, and metric populations.
