# Trial unit

The trial unit defines one local call for one admitted trial entry.
`BackendTrialUnit.execute_trial(request)` returns a `TrialUnitResult`.
These Python interfaces define an in-process handoff.
They do not install an executor or certify a backend.
The public types are in `raes_contracts.trial_unit`.
The protocol is in `raes_backend_protocols.trial_unit`.

## Composition and ownership

An embedder constructs the adapter with an explicit `RuntimeTarget`.
The target is a dependency of the adapter, not a serialized request field.
The protocol package does not import runtime or processor implementations.
The adapter uses shared RAE processor and runtime functions.
It does not interpret SDL itself.

The processor first calls `realize_admitted_trial_entry()`.
The caller passes its three neutral processor-plan projections and instantiated SDL digest into `TrialUnitRequest`.
The request also carries the complete admitted plan, exact entry ID, and a distinct execution attempt ID.
Request construction reconstructs the complete plan before entry lookup.
The request exposes the entry's sealed participant configurations, execution controls, and referenced cleanup plan.
There is no independently editable copy of these values.

The adapter checks the selected manifests and envelope against its injected target before effects.
The provisioning and evaluation plans retain the admitted run and instantiation IDs.
The adapter checks all projections against trusted processor output before dispatch.
Projection carriage alone proves neither derivation nor execution permission.
Configured participants require explicit backend support before effects.
The adapter never repeats configuration normalization or resolves secrets in the request.

The runtime retains authored order, time, participant rules, operation admission, and result validation.
A control-plane composition uses the explicit scope `run:<entry.run_id>`.
The backend owns native effects, observations, secret delivery, and cleanup probes.
The allocator owns placement and live isolation.
The trial unit chooses no batch order, parallelism, replacement, or fresh run identity.

## Results and failure

`execution_snapshot` records validated runtime state after trial execution and before cleanup changes that state.
It is distinct from the instantiated SDL digest in the request.
The adapter preserves partial observations when execution fails.
Operation receipts acknowledge submission; they do not establish workflow completion.
Typed execution evidence accompanies the receipts and snapshot.

The cleanup receipt reports the trial outcome and cleanup status separately.
Cleanup evidence accompanies that receipt, including failed or unverified cleanup.
`validate_trial_unit_result()` checks the cleanup obligations and attempt identity against the request.
It checks receipt target/run scopes and evidence run identities.
Every cleanup evidence reference must identify a record in `cleanup_evidence`.
These checks do not resolve evidence content or prove native cessation.
The adapter uses existing runtime snapshot validators and trusted evidence resolvers before publication.
The archival producer still uses `ExperimentRunModel` and its existing cross-artifact validators.

Timeout and cancellation use the admitted controls and existing supervision machinery.
Caller timeout does not prove backend cessation.
Unknown effects retain their reservations until the runtime's release checks pass.
Cleanup retains its own obligation budgets after execution timeout.
Cleanup failure does not erase execution evidence.
A successful trial does not imply successful cleanup.
An interrupted call can have no complete result.
The runtime ledger retains authority for recovery in that case.
The caller must reconcile it before another dispatch.

## Data flow and protection

```mermaid
flowchart LR
    P["Trusted processor"] -->|"Validated plan projections and SDL digest"| U["Trial adapter"]
    A["Admitted plan owner"] -->|"Complete sealed plan and exact entry"| U
    subgraph R["Trusted in-process RAE boundary"]
        U -->|"Scoped operations and controls"| C["Shared runtime"]
        C <-->|"Operation claims and validated state"| L[("Existing runtime ledger")]
    end
    C -->|"Authorized effect and cleanup calls"| T["Injected RuntimeTarget"]
    T -->|"Untrusted observations and cleanup evidence"| C
    C -->|"Validated receipts, execution snapshot and evidence"| U
    U -->|"Trial result"| X["Existing archival producer"]
    X -->|"Validated archival run"| S[("Run archive")]
```

The plan-owner boundary protects admitted identity and configuration integrity.
Whole-plan reconstruction rejects tampered nested models before entry consumption.
The target boundary protects execution authority and observation integrity.
Runtime input, result, transition, and evidence checks remain necessary there.
The archive boundary protects provenance and evidence disclosure.
Run validators and access controls remain necessary there.

Request and result aggregates are local Python values, not new wire contracts.
Their representations omit carried configurations, plans, snapshots, and evidence.
Nested portable models retain their existing validators.
Collections have finite item bounds.
Each result collection permits at most 4096 items.
The shared runtime value limits bound both aggregates before copying.
Secrets remain non-sensitive references until an authorized backend sink resolves them.
Adapters must not log payloads, exception input, native output, or resolved secrets.
The handoff adds no network call, credential lookup, process, listener, or store.
Trusted embedders retain P0 authorization responsibilities.

## Design basis

[ADR-036](../../decisions/adrs/adr-036-sdl-processor-runtime-module-boundaries.md) defines package dependencies.
[ADR-113](../../decisions/adrs/adr-113-reusable-execution-machinery.md) retains shared runtime authority in local composition.
[ADR-115](../../decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md) assigns native realization to backend distributions.
These decisions need no amendment.
Existing policy enforces package boundaries; this interface adds no policy mechanism.
Python protocols and neutral request/result values express the architecture in code.
No published schema or operation kind changes.

The design uses Python 3.11 `typing.Protocol` and dataclasses.
The [Python documentation](https://docs.python.org/3.11/library/typing.html) explains structural typing and its runtime limits.
The [dependency injection reference](https://www.cosmicpython.com/book/chapter_13_dependency_injection.html) describes explicit composition and test doubles.
