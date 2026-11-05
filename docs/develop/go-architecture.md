# Current Go architecture

This is the current system view for the Go port.
[The model](../../implementations/architecture.json) owns package placement, dependencies, build contexts and intended interfaces.
[ADR-122](../decisions/adrs/adr-122-go-architecture-model.md) owns the checking rules.
The generated view lists the code that exists now.
An empty layer is planned, not implemented.
Python remains the behavioral reference for components not yet ported.

The [runtime repository split](../decisions/issue-1891-runtime-repository-boundary.md) takes effect at the common #1804 Go launch.
`OpenRAE/rae` retains SDL, processor, canonical contracts, portable backend interfaces/stubs and pure conformance.
The planned runtime repository owns execution, control-plane/HTTP/store/worker behavior and live conformance.
Runtime imports released public `rae` APIs; `rae` product modules never import runtime.
The [complete source inventory](../decisions/issue-1891-runtime-extraction-inventory.json) pins the current baseline and mixed responsibilities.
No destination or source transfer is approved by this plan.

## Components and consumer boundary

Environment packs and LilRAE consume the relevant public language/processor/contract/backend APIs.
Coldlight embeds the shared runtime from its planned new repository owner.
[The consumer API reference](../decisions/issue-1825-public-go-api.md) names their package owners, operations, command composition and compatibility policy.
No product package is downstream-importable today.
The `public` flag is for layers.
It does not bypass Go's `internal` rule.
The tooling module is a development dependency, not the consumer product API.

```mermaid
flowchart TB
    Consumers[Environment packs / LilRAE / Coldlight]
    subgraph Host[Embedding host boundary - planned]
        Providers[Store / lease / clock providers]
        API[Consumer API - issue 1825 - planned]
    end
    subgraph RAES[OpenRAE/rae - language and contract authority]
        Transport[Authoring CLI / MCP adapters - planned]
        App[Authoring services - planned]
        SDL[SDL admission - planned]
        Contracts[Published contract admission - implemented]
        Processor[Compilation / planning / trial compilation - planned]
        Backend[Backend interfaces - planned]
        Base[Shared base primitives - implemented]
    end
    subgraph RuntimeRepo[Runtime repository - planned]
        Runtime[Shared runtime control plane - planned]
        HTTP[HTTP adapter - planned]
        CLI[Combined raes publisher - planned]
    end
    Consumers --> API
    API --> App
    Transport --> App
    App --> SDL
    App --> Processor
    CLI --> Transport
    HTTP --> Runtime
    SDL --> Contracts
    Processor --> SDL
    Runtime --> Processor
    Runtime --> Contracts
    Runtime --> Backend
    Runtime --> Providers
    Contracts --> Base
    Providers --> Temporal[Temporal execution composition - planned ADR-113]
```

Published contract admission is implemented.
It compiles the packaged schemas offline and checks family rules against explicit owner records.
Caller payloads cannot create trusted context, and validation performs no network retrieval.
The [contract design](../decisions/issue-1780-contract-validation-design.md) records its interfaces and failure controls.

Consumers need bounded SDL reads.
They also need checks, edits, errors, locks and digests.
They also include normalized contract round trips, artifact admission, compilation, planning and runtime result admission.
Diagnostics preserve code, pointer, source range, stage and severity.
Typed handles and caller validators cannot be replaced with JSON-only shims.
RAES owns semantic admission, defaults, schemas, vocabulary and address grammar.
Consumer adapters must not call Python.
They must not copy core checks.

Coldlight embeds the shared runtime selected by ADR-104 and ADR-113, using the new runtime repository's released API after cutover.
Its planned API includes actor-bound submissions, idempotent receipts, snapshots, participant transitions and audit.
It also includes store, lease and clock interfaces and Temporal execution adapters.
ADR-104's P0/P1/P2 profiles describe reference capabilities, not proof of Go delivery.
P3 coordinated multi-process, multi-tenant service remains a nonclaim.

## Data flows and protection boundaries

```mermaid
flowchart LR
    Documents[Untrusted documents and imports]
    Requests[Untrusted requests and identities]
    subgraph Host[Host authority boundary - planned]
        Auth[Authentication and route authority]
        Secrets[Native credentials and resources]
    end
    subgraph Core[rae language and contract authority]
        Ingress[Bounded ingress - implemented primitive]
        Admission[Contract admission implemented / SDL admission planned]
        Plan[Compilation and planning - planned]
    end
    subgraph RuntimeRepo[Runtime repository - existing protection boundary preserved]
        Policy[Actor / scope / target policy - planned]
        Runtime[Shared operation runtime - planned]
    end
    Documents -->|bounded supplied bytes| Ingress
    Ingress -->|parsed values| Admission
    Requests -->|credentials and operation request| Auth
    Auth -->|authenticated principal| Policy
    Admission -->|validated scenario values| Plan
    Plan -->|admitted execution plan| Runtime
    Policy -->|actor-bound operation| Runtime
    Runtime -->|atomic state and receipts| Store[(Authoritative provider store - planned)]
    Runtime -->|admitted effects| Backend[Injected backend - planned]
    Secrets -->|host-owned handles| Backend
    Backend -->|observed result| Runtime
    Runtime -->|admitted results and audit| Evidence[(Evidence and audit - planned)]
    Runtime -->|value-free events| Logs[(Operational logs - planned)]
```

| Asset / threat | Boundary and control | Evidence / verification |
| --- | --- | --- |
| Source containment and parser exhaustion | Bounded supplied sources; strict ingress before semantic admission | Base ingress tests; published contracts; #1782/#1785 remain planned |
| Cross-actor operations | Transport authenticates; core binds actor, scope, target and idempotency | ADR-104; future runtime conformance tests |
| Confused transport authority | One route authority; invalid bearer credentials cannot fall back to proxy headers | ADR-104; reference security configuration and route tests |
| Uncertain effects and corrupt state | Backend admission, atomic terminal commits, CAS and leases | ADR-104 and ADR-113; Go runtime remains planned |
| Secret disclosure | Logical secret references; native credentials stay in the host | ADR-115 and ADR-116; future adapter redaction tests |
| Audit confusion | Operational logs carry no values and cannot replace evidence or audit | ADR-066 and ADR-116 |
| Architectural drift | Exact typed API, package graph, design commitments and source-bound view checks | ADR-122; arch and archcheck negative tests |

Snapshots prove structural consistency. They do not prove semantic equivalence or service readiness.
Review checks these trust explanations whenever bound evidence changes.

## Ownership and reuse

| Concern | Canonical owner / reuse decision |
| --- | --- |
| Strict bounded JSON | `base/ingress.Parse`; standard encoding/json alone does not enforce the published ingress policy |
| Canonical bytes | `base/canonjson`; JCS and sorted Python JSON are distinct compatibility profiles |
| Digests | `base/digest`; reuse crypto/sha256, not local digest wrappers in each slice |
| Random streams | `base/randstream`; admitted BLAKE3 adapter preserves profiles and seek behavior |
| Addresses and pointers | `base/address` and `base/jsonpointer`; published grammars remain authoritative |
| URI safety | `base/urisafety`; standard URL parsing plus documented Unicode and error-precedence compatibility |
| Clock and timestamp policies | `base/clock` and `base/timestamp`; inject wall-clock reads and reuse the four named grammars |
| Errors and logging | `base/fault` and `base/logrecord`; value-free codes and bounded log records through standard error wrapping and log/slog |
| Graphs | `base/graph`; shared iterative cycle, ordering and component operations |
| Versions and scalar domains | `base/softwareversion` and `base/domain`; closed typed descriptors and bounded comparisons |
| Snapshot values | `base/value`; bounded closed JSON values without foreign callbacks |
| Secret reference identities | `base/secretref`; bounded inert identities, with no secret resolution |
| Contract admission and defaults | `contract/admission` and `contract/validation`; published schemas, full family rules and explicit trusted context |
| Operation and persistence semantics | Planned runtime layer; transports and embedders share the same core |
| Architecture checks | Tooling `arch`; standard Go types and existing model/findings, no product-internal imports |

These primitive owners stay in `rae`.
The model's `consumer_api` section declares the planned public imports.
#1892 moves the required existing packages; later port issues implement their named interfaces.
The model's `public` flag does not override Go `internal` visibility.
Pure conformance, authoring services and MCP remain in `rae`; live conformance, execution services, HTTP and combined `raes` publication belong with runtime.
The current model graph below still describes this checkout before extraction.
Its layer descriptions and bound split decision define future ownership.
The generated consumer tables show the public package plan and the sole executable publishers.
No moved package is claimed as delivered.

Compatibility reasons and parity evidence:
[canonical JSON](../decisions/issue-1779-canonical-json-design.md),
[ingress and URI](../decisions/issue-1779-ingress-design.md),
[random streams](../decisions/issue-1779-random-streams-design.md), and
[parity harness](../decisions/issue-1778-parity-corpus-design.md).
The architecture check does not alter those semantics.
The [shared-primitives completion design](../decisions/issue-1779-shared-primitives-completion.md) owns the newly merged base helpers and their compatibility reasons.

## Maintenance

Each port slice changes the model before code.
Do not copy shared helpers.
Use the owner listed above.
Keep source limits in place.
Keep secrets out of logs.
It records typed APIs and updates the owning design's API commitment.
It reviews this overview when source commitments change.
`archcheck -view` prints the generated section for review; it does not overwrite the overview.
`archcheck -api` prints actual interfaces for comparison; it does not approve them.
The existing go-architecture CI job checks documentation and code changes.

<!-- go-view -->

| Layer | Status | Allowed dependencies |
| --- | --- | --- |
| `base` | implemented packages |  |
| `contract` | implemented packages | base |
| `sdl` | planned | contract, base |
| `processor` | planned | sdl, contract, base |
| `backend` | planned | contract, base |
| `runtime` | planned | backend, processor, sdl, contract, base |
| `conformance` | planned | runtime, backend, processor, sdl, contract, base |
| `app` | planned | conformance, runtime, backend, processor, sdl, contract, base |
| `adapter` | planned | app, runtime, contract, base |
| `command` | planned | adapter, base |
| `parity` | implemented packages | base, contract |
| `tooling` | implemented packages |  |

```mermaid
flowchart BT
    L0["base"]
    L1["contract"]
    L1 --> L0
    L2["sdl"]
    L2 --> L1
    L2 --> L0
    L3["processor"]
    L3 --> L2
    L3 --> L1
    L3 --> L0
    L4["backend"]
    L4 --> L1
    L4 --> L0
    L5["runtime"]
    L5 --> L4
    L5 --> L3
    L5 --> L2
    L5 --> L1
    L5 --> L0
    L6["conformance"]
    L6 --> L5
    L6 --> L4
    L6 --> L3
    L6 --> L2
    L6 --> L1
    L6 --> L0
    L7["app"]
    L7 --> L6
    L7 --> L5
    L7 --> L4
    L7 --> L3
    L7 --> L2
    L7 --> L1
    L7 --> L0
    L8["adapter"]
    L8 --> L7
    L8 --> L5
    L8 --> L1
    L8 --> L0
    L9["command"]
    L9 --> L8
    L9 --> L0
    L10["parity"]
    L10 --> L0
    L10 --> L1
    L11["tooling"]
```

| Package owner | Layer | Cross-layer visibility | Consumer importable | Actual dependencies |
| --- | --- | --- | --- | --- |
| `implementations/go/internal/base/address` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/canonjson` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/digest` | base | true | false |  |
| `implementations/go/internal/base/ingress` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/jsonpointer` | base | true | false |  |
| `implementations/go/internal/base/randstream` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/urisafety` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/parity` | parity | false | false | implementations/go/internal/base/address, implementations/go/internal/base/canonjson, implementations/go/internal/base/digest, implementations/go/internal/base/ingress, implementations/go/internal/base/jsonpointer, implementations/go/internal/base/randstream, implementations/go/internal/base/urisafety, implementations/go/internal/base/clock, implementations/go/internal/base/domain, implementations/go/internal/base/fault, implementations/go/internal/base/graph, implementations/go/internal/base/logrecord, implementations/go/internal/base/secretref, implementations/go/internal/base/softwareversion, implementations/go/internal/base/timestamp, implementations/go/internal/base/value, implementations/go/internal/contract/validation, implementations/go/internal/contract/admission |
| `implementations/tooling/go/arch` | tooling | false | true |  |
| `implementations/tooling/go/cmd/archcheck` | tooling | false | false | implementations/tooling/go/arch |
| `implementations/tooling/go/cmd/raesvet` | tooling | false | false | implementations/tooling/go/lint/getprefix, implementations/tooling/go/lint/gotwant, implementations/tooling/go/lint/wrapverb |
| `implementations/tooling/go/cmd/regressiontest` | tooling | false | false |  |
| `implementations/tooling/go/lint/getprefix` | tooling | false | true |  |
| `implementations/tooling/go/lint/gotwant` | tooling | false | true |  |
| `implementations/tooling/go/lint/wrapverb` | tooling | false | true |  |
| `implementations/go/internal/base/clock` | base | true | false |  |
| `implementations/go/internal/base/fault` | base | true | false |  |
| `implementations/go/internal/base/timestamp` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/softwareversion` | base | true | false | implementations/go/internal/base/canonjson, implementations/go/internal/base/digest, implementations/go/internal/base/fault |
| `implementations/go/internal/base/domain` | base | true | false | implementations/go/internal/base/softwareversion, implementations/go/internal/base/fault |
| `implementations/go/internal/base/value` | base | true | false | implementations/go/internal/base/fault, implementations/go/internal/base/canonjson |
| `implementations/go/internal/base/logrecord` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/graph` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/secretref` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/contract/corpus` | contract | true | false |  |
| `implementations/go/internal/contract/binding` | contract | true | false |  |
| `implementations/go/internal/contract/validation` | contract | true | false | implementations/go/internal/contract/corpus, implementations/go/internal/contract/binding, implementations/go/internal/base/ingress, implementations/go/internal/base/fault, implementations/go/internal/base/canonjson, implementations/go/internal/base/jsonpointer |
| `implementations/tooling/go/contractgen` | tooling | false | true |  |
| `implementations/tooling/go/cmd/contractgen` | tooling | false | false | implementations/tooling/go/contractgen |
| `implementations/go/internal/contract/admission` | contract | true | false | implementations/go/internal/contract/validation, implementations/go/internal/contract/corpus, implementations/go/internal/base/canonjson, implementations/go/internal/base/digest, implementations/go/internal/base/timestamp, implementations/go/internal/base/graph, implementations/go/internal/base/urisafety, implementations/go/internal/base/address, implementations/go/internal/base/jsonpointer, implementations/go/internal/base/value, implementations/go/internal/base/domain, implementations/go/internal/base/randstream, implementations/go/internal/base/fault, implementations/go/internal/base/ingress |

| Consumer repository owner | Module |
| --- | --- |
| rae | `github.com/OpenRAE/rae/implementations/go` |
| runtime | `RUNTIME` (approval pending #1893) |

| Planned public package | Owner | Operations / types | Public dependencies | Consumers | Delivery issues |
| --- | --- | --- | --- | --- | --- |
| `github.com/OpenRAE/rae/implementations/go/base/fault` | rae | Error, Category, CategoryOf, New |  | environment-packs, lilrae, runtime | #1892 |
| `github.com/OpenRAE/rae/implementations/go/base/ingress` | rae | Limits, Parse | rae:base/fault | environment-packs, lilrae, runtime | #1892 |
| `github.com/OpenRAE/rae/implementations/go/base/canonjson` | rae | JCS, Sorted | rae:base/fault | environment-packs, lilrae, runtime | #1892 |
| `github.com/OpenRAE/rae/implementations/go/base/digest` | rae | SHA256, NewChecksum |  | environment-packs, lilrae, runtime | #1892 |
| `github.com/OpenRAE/rae/implementations/go/base/address` | rae | Valid, Render, PlanRoot | rae:base/fault | environment-packs, lilrae, runtime | #1892 |
| `github.com/OpenRAE/rae/implementations/go/base/clock` | rae | Clock, Read, System |  | environment-packs, lilrae, runtime | #1892 |
| `github.com/OpenRAE/rae/implementations/go/contract/binding` | rae | Field, MaterializationArchiveRecordV1, RuntimeSnapshotV1, BackendManifestV2, AdmittedTrialPlanV1, BackendRuntimeDescendantsV1 |  | environment-packs, lilrae, coldlight, runtime | #1892 |
| `github.com/OpenRAE/rae/implementations/go/contract/validation` | rae | New, Validator, Value, Validator.CheckSchema, Validator.DecodeSchema, Validator.Defaulted, Value.JSON, Value.Transport | rae:base/ingress | environment-packs, lilrae, coldlight, runtime | #1892 |
| `github.com/OpenRAE/rae/implementations/go/contract/admission` | rae | New, Validator, Validator.Validate, Validator.CheckPortable, AssociatedArtifactsContext, MaterializationCompiler, MaterializationInventoryContext, SDLPhaseOwner, AssociatedArtifactLimits, DefaultAssociatedArtifactLimits, LoadAssociatedManifest, ValidateAssociatedManifest, AssociatedArtifactSetDigest, EvaluateRealizationConstraint, ParticipantConfigurationValidator, MaterializationArchive, RestoreMaterializationArchive, Fragment, FragmentProfile, ImplementationIdentity, BindingOwner, BindingValue, ControlContextAssetReference, ControlContextSelection, ConfigurationOverride, RealizedConfigurationValue, ParticipantConfiguration, ParticipantControlContextValidator, ParticipantConfigurationRequest, ParticipantManifestKey, ApparatusManifestKey, ApparatusManifest, ScenarioBindingResolution, ScenarioBindingTargetResolver, AdmitFragment, RealizeParticipantConfiguration, ValidateParticipantConfigurationSelection, ValidateExperimentBindingTargets, ConstraintLimits, DefaultConstraintLimits, ConstraintLimits.Validate | rae:base/ingress, rae:contract/binding, rae:contract/validation | environment-packs, lilrae, coldlight, runtime | #1892, #1788, #1781 |
| `github.com/OpenRAE/rae/implementations/go/contract/concept` | rae | AdmitBindings, SchemeSnapshot, ResolutionOutcome, Vocabulary, Subject, SnapshotTerm, BindingResolution, ResolutionOutcome.Admitted | rae:contract/binding, rae:contract/diagnostic | environment-packs, lilrae, runtime | #1781 |
| `github.com/OpenRAE/rae/implementations/go/contract/diagnostic` | rae | Diagnostic, Range, Error | rae:base/fault | environment-packs, lilrae, coldlight, runtime | #1782, #1783 |
| `github.com/OpenRAE/rae/implementations/go/sdl` | rae | Scenario, InstantiatedScenario, Limits, DefaultLimits, Parse, ParseSources, ParseFile, AuthoredScenario, Validate, Instantiate, AdmitInstantiated, AdmitFamily, CanonicalDigest, ConceptSubjects, ArtifactRequirements, Requirement, ResolveRealizationDesignation, MigrationPolicy, ParseOptions, SourceContext, DefaultParseOptions, ParseContext, ValidateExperimentSelectionAgainstFamily, Limits.Validate, ParseOptions.Validate | rae:contract/admission, rae:contract/binding, rae:contract/concept, rae:contract/diagnostic, rae:sdl/module | environment-packs, lilrae, runtime | #1782, #1783, #1784, #1785 |
| `github.com/OpenRAE/rae/implementations/go/sdl/module` | rae | LockfileName, Lockfile, TrustPolicy, LoadLockfile, ResolveLock, LockRecord, VerificationFacts, RegistryTrust, Policy, DefaultPolicy, Policy.AdmitModule |  | environment-packs, lilrae, runtime | #1785 |
| `github.com/OpenRAE/rae/implementations/go/sdl/language` | rae | Edit, EditResult, ApplyEdit, Completions, Diagnostics, Format | rae:contract/diagnostic, rae:sdl | environment-packs, lilrae | #1786 |
| `github.com/OpenRAE/rae/implementations/go/processor` | rae | Compilation, Compile, CompileInstantiated, RuntimeModel, TimeModelContract, ScenarioComponentOptions, ComponentOptions, CompiledComponentOptions | rae:contract/binding, rae:contract/diagnostic, rae:sdl | environment-packs, lilrae, runtime | #1787 |
| `github.com/OpenRAE/rae/implementations/go/processor/planning` | rae | Plan, Result, PlanWithManifest, ExecutionPlan, Scope, Closure, ApparatusDefaultResolver, ArtifactAvailability, MixedControlAdmission, Options, RequirementKey, PlanningContext, NewMixedControlAdmission | rae:contract/admission, rae:contract/binding, rae:contract/diagnostic, rae:contract/validation, rae:processor | environment-packs, lilrae, runtime | #1787 |
| `github.com/OpenRAE/rae/implementations/go/processor/trial` | rae | Request, Compile, PlanBatchSchedule, ScheduledEntry, BatchSchedule, ParticipantManifestKey, ApparatusManifestKey, ConfigurationValidatorKey, Limits, MixedCompositionLimits, Result, DefaultLimits, DefaultMixedCompositionLimits, Limits.Validate, MixedCompositionLimits.Validate, RealizationInputs, Realization, RealizationOptions, InstantiateEntry, RealizeEntry | rae:contract/admission, rae:contract/binding, rae:contract/diagnostic, rae:contract/validation, rae:processor/planning, rae:sdl | environment-packs, lilrae, runtime | #1788 |
| `github.com/OpenRAE/rae/implementations/go/processor/realization` | rae | ProjectConcern, ConcernDescriptors, HasRequiredObservationSupport, Descriptor | rae:contract/admission | environment-packs, lilrae, runtime | #1787 |
| `github.com/OpenRAE/rae/implementations/go/processor/analysis` | rae | Analyze, Request, Result | rae:contract/diagnostic, rae:processor | lilrae, runtime | #1789 |
| `github.com/OpenRAE/rae/implementations/go/backend` | rae | Provisioner, Orchestrator, Evaluator, ParticipantRuntime, Manifest, LoadProfile, PreparingProvisioner, TimeRuntime, AutonomousActionBinding, AutonomousParticipantRuntime, ControlledAutonomousParticipantRuntime, CoordinatedParticipantResetRuntime, CoordinatedParticipantTimeRuntime, OperationProvider, ParticipantControlProvider, ParticipantControlProviderV2, ProfilePreparingProvisioner | rae:contract/admission, rae:contract/binding, rae:contract/diagnostic, rae:contract/runtime | environment-packs, lilrae, runtime | #1790 |
| `github.com/OpenRAE/rae/implementations/go/backend/stub` | rae | Manifest, Options, Provisioner, Orchestrator, Evaluator, ParticipantRuntime, DefaultOptions, NewProvisioner, NewOrchestrator, NewEvaluator, NewParticipantRuntime | rae:backend | environment-packs, lilrae, runtime | #1790 |
| `github.com/OpenRAE/rae/implementations/go/conformance` | rae | ValidateFixture, ValidateProcessor, ValidateModularReport, ModularControlEvidence, ModularOwnerObservation | rae:contract/diagnostic, rae:processor | lilrae, runtime | #1796 |
| `github.com/OpenRAE/rae/implementations/go/command/authoring` | rae | Commands, Command, Streams |  | runtime | #1797 |
| `RUNTIME/runtime/control` | runtime | New, ControlPlane, ControlPlane.Submit, ControlPlane.Operation, ControlPlane.Snapshot, ControlPlane.TransitionParticipant, ControlPlane.Audit, Target, NewTarget, Options, Request, Identity, Authority, Components, ParticipantContexts, Supervision, PlanPhase, RegisteredPlan, Command, ParticipantCommandInput, ParticipantTransition, DefaultSupervision, PlanCommand, ParticipantCommand, ControlResolution, ControlResolver, ControlResolverV2, ControlStageBinding, ControlInstallation, ParticipantControlBinding, LiveCut, CutResolver, DeliveryCutResolver, MixedControlBinding, InjectResolution, InjectDeliveryResolver, InjectDeliveryBinding, InjectAdmission, ResolvedInjectOutcome, InjectExecutionResolver, NewParticipantControlBinding, NewMixedControlBinding, NewInjectDeliveryBinding, CrossingIntent, CrossingGates, CrossingTransformation, CrossingResolution, CrossingValidation, CrossingEvidence, ParticipantAudienceBinding, ViewEvidenceRequest, CrossingResolver, CrossingCut, FlowSinkRequest, FlowSinkResolution, FlowSinkResolver, SupervisionAction, SupervisionRequest, ResolutionDisposition, ResolutionRequest, EffectKind, EffectOperation, EffectRealization, InjectCaptureResult, RunProgress, RunContext, SequenceOptions, TrialUnitRequest, TrialUnitResult, TrialObservation, TrialConfigurationObservation, TrialExecutionObservation, TrialCaptureObservation, TrialCleanupObservation, TrialRetryObservation, TrialRuntimeServices, RetryTrialRuntimeServices, TrialArchiveOwner, ExperimentReplacement, ExperimentRequest, ExperimentProgress, AdmitTrialUnitRequest, TrialUnitRequest.RunID, TrialUnitRequest.ParticipantConfigurations, TrialUnitRequest.ExecutionControls, TrialUnitRequest.CleanupPlan, ParticipantCancellationStatus | rae:backend, rae:base/clock, rae:contract/admission, rae:contract/binding, rae:contract/runtime, rae:contract/validation, rae:processor, rae:processor/planning, rae:processor/trial, runtime:runtime/execution, runtime:runtime/profile, runtime:runtime/provider, runtime:runtime/result | coldlight, lilrae | #1791 |
| `RUNTIME/runtime/provider` | runtime | Store, AtomicStore, LeaseProvider, OwnerLease, Capabilities, SnapshotState, AuditEvent, OperationRecord, OperationAdmissionContext, ClaimIdentity, ClaimState, Transition, NewClaimBlock, ClaimOptions, TerminalCommitMode, TerminalCommit, DecodeOperationRecord, RecordsEqual, IdempotencyClaimIdentity, ValidateIdempotencyReplay, ValidateNewClaim, ValidateInvocationTransition, LedgerIdentity, SequenceDecision, RuntimeDecision, RuntimeStoreDigest, NewSequenceDecision, DecodeRuntimeDecision, ValidateIdenticalDecision | rae:contract/binding, runtime:runtime/execution, runtime:runtime/profile | coldlight, lilrae | #1792 |
| `RUNTIME/runtime/execution` | runtime | Adapter, Request, LocalAdapter, Lane, EngineReference, DeliveryBinding, RuntimeSequenceReference, Dispatcher, InvocationGrant, ControlDeliveryGrant, WorkerAuthority, NewLocal | rae:contract/binding | coldlight, lilrae | #1793 |
| `RUNTIME/runtime/temporal` | runtime | New, Adapter, Configuration, Worker, ClientOptions, Client, WorkerOptions, DefaultConfiguration, Dial, NewWorker, Configuration.Validate, RuntimeWorkerOptions, NewRuntimeWorker | rae:backend, runtime:runtime/execution | coldlight | #1793 |
| `RUNTIME/runtime/result` | runtime | AdmitResult, Context, EvidenceResolver, AdmitApplyResult | rae:contract/admission, rae:contract/binding, rae:contract/runtime, rae:contract/validation, rae:processor | lilrae, coldlight | #1794, #1795 |
| `RUNTIME/runtime/profile` | runtime | ID, P0, P1, P2, P3, Capability, Claim, Declaration, StoreCapabilities, DeclarationFor, Select, RequireCapabilities, CoreCapabilities, ErrProfileUnavailable, NewStoreCapabilities, StoreCapabilities.Values, ActorBoundary, RecoveryObservationRequirement |  | coldlight, lilrae | #1791, #1792 |
| `github.com/OpenRAE/rae/implementations/go/contract/runtime` | rae | ApplyResult, MaterializationSubmission, NewMaterializationSubmission, ParticipantActionRequest, NativeActionExecution, RealizationObservationDisclosure, ObservedOperatingSystemIdentity, ProvisionOperation, RealizationPreparation, EpisodeInitializeRequest, EpisodeResetRequest, EpisodeRestartRequest, EpisodeTerminateRequest, ParticipantActionInput, ParticipantActionApplyResult, NativeActionOutcome, PrepareForRequest, BindParticipantAction | rae:contract/admission, rae:contract/binding, rae:contract/diagnostic | lilrae, runtime | #1790 |

| Executable | Publisher | Entry point | Public composition dependencies |
| --- | --- | --- | --- |
| `raes` | runtime | `RUNTIME/cmd/raes` | rae:command/authoring, runtime:runtime/control |
| `raes-mcp` | rae | `github.com/OpenRAE/rae/implementations/go/cmd/raes-mcp` | rae:sdl/language, rae:processor, rae:contract/admission |

<!-- go-consumer d8802bf779d358c33967d4b1510bc75e38fa92a2ba1768d96ab405dfe6165286 -->

| Trust-view evidence | SHA-256 |
| --- | --- |
| `contracts/schemas/experiment-core/materialization-archive-record-v1.json` | `fb61b1d9bb70ffedf7fec94325c3751a29ef7db7f6e8bea8fc96c064d101ba90` |
| `docs/decisions/adrs/adr-036-sdl-processor-runtime-module-boundaries.md` | `8b23019d17144225d08d6a38301a62a3eb2490c122a3d2ed36a67ab0804d84fa` |
| `docs/decisions/adrs/adr-066-observability-evidence-plane-separation.md` | `938ce2443ce7bd9e5cfa151d9740610ac23fa4338efa48c3cb022c7543bab24a` |
| `docs/decisions/adrs/adr-104-runtime-control-plane-architecture.md` | `790d2c4119d2c37562aaad3d5cee3ffa4740ac150511f035f3376dd46d28e4b0` |
| `docs/decisions/adrs/adr-113-reusable-execution-machinery.md` | `6d904befc0d37d44b07ed083d297c7a0e3ba0d520d79f9ddce1999477c78e91d` |
| `docs/decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md` | `e7994a017f64937bfa48edfb8600b933e2acca330a2d5ebaef8a6ae95fcc91be` |
| `docs/decisions/adrs/adr-116-shared-exceptions-and-operational-logging.md` | `a4e20904762d23ff25162b910ab91032fdaac84b38ef727401c7fe501dde6ffa` |
| `docs/decisions/adrs/adr-122-go-architecture-model.md` | `7ddd90a8486fb218b224bcb8addeffeefc8bff7f0351c90d72400ebd413f7b63` |
| `docs/decisions/issue-1775-go-architecture-model-design.md` | `d12f71c98e4bcad11f42db41338d2d93e9d9ed21731e5e4a1b9ed6fbbba1d2c8` |
| `docs/decisions/issue-1778-parity-corpus-design.md` | `c3197d51b64c8b2684096ad8d4ed4df223457b2e811a16e68bf31e9babc15830` |
| `docs/decisions/issue-1779-canonical-json-design.md` | `c68392c70e55eabd39a1d1b287c082fc98b40aea2a50a90a43384f34aea752a3` |
| `docs/decisions/issue-1779-ingress-design.md` | `21fe1ede3a371941bd13605037cf6e378a6f442d9622dbc9fa716e952cbad281` |
| `docs/decisions/issue-1779-random-streams-design.md` | `dae79083acb2909a63a43849e9aeb0ddf4594d3e7d54d118b2a1dd54f68cdb8b` |
| `docs/decisions/issue-1779-shared-primitives-completion.md` | `6db76f93cc860d13e966bd591fc4d4c4fc3d2c27789aafe1c1bd30dcc57d657e` |
| `docs/decisions/issue-1780-contract-validation-design.md` | `ed1ba1a0d0cc07b995cacd8407799152bac9b09b1b43670d4e08ea62ad6c4aec` |
| `docs/decisions/issue-1825-public-go-api.md` | `6f264cb6dd7fef28567fcb804a56b8b94f63b883f59f4be35d0ffc41095ca721` |
| `docs/decisions/issue-1859-go-architecture-contract-design.md` | `5842d05eca8c9cfb69b01ba1edbde3ba7053bbf40a30ba60d4ab24731b2705de` |
| `docs/decisions/issue-1891-runtime-repository-boundary.md` | `e8233ecdf836dbbad4dda9ef373572dd466f1cf59ad0eeb4ab01cc9fd476e406` |
<!-- go-component base 04321896edf5f4ad742656c8b66efa4700677b2a7993485fdb6e0f940af96eda -->
<!-- go-component contract 136352fa4109d0f6e381e8d986be977d2a8c943fc760f33ced506618a76f5a69 -->
<!-- go-component sdl b21f9190711ea203ad057c5239a2e1235eb7fead04c08dfa0ad7e3b63985b737 -->
<!-- go-component processor 78be66f477d2c69c2ef04799381498b40215b3b1ea2258dba1d412c943a13c59 -->
<!-- go-component backend c8b9396a657b0605c31a1b6c6bcb84be3bebd2c8d3368d8459862b73ef6f3337 -->
<!-- go-component runtime cf99c7c0b9410724ce61471a1b2f5103e22f917f533a116f4347ed91009c14dd -->
<!-- go-component conformance d1bb0c4dff7c7cba27650b5b43d49a736f59b068e73f52acde20365c209ddf20 -->
<!-- go-component app c74e53df701bef04d311f1d77e82d7ae48b71be0dc2ff97bec7faabbb2759d48 -->
<!-- go-component adapter d770a858f7668e37ec056d6e8ed3b4420bc8130ba38173abd290748ab2478fbf -->
<!-- go-component command 5cf1c9b301f31cf79c5ae9c97d16014766f13fec5ea21eea3b0ad40ec1b28caf -->
<!-- go-component parity 9a41c3ac51ba3859b764cdf662752928546f8838075a171d48ce366c17317d71 -->
<!-- go-component tooling 0d2351108d3817df871e95364809c4029702f2ed61127b8d49a6f2bca14c7ee9 -->

<!-- /go-view -->
