# Public Go consumer API

This reference fixes the public import boundary for [#1825](https://github.com/OpenRAE/rae/issues/1825).
The [repository split](issue-1891-runtime-repository-boundary.md) fixes ownership.
[The architecture model](../../implementations/architecture.json) records the public package map in `consumer_api`.
It names each package's public identifiers, consumers and delivery issues.
The Go declarations fix the planned interfaces.
They do not claim that the packages exist.
No product code moves in this PR.

## Module and import map

`RAE` means `github.com/OpenRAE/rae/implementations/go`.
It remains the single product module in this repository.
For example, `RAE/contract/admission` expands to `github.com/OpenRAE/rae/implementations/go/contract/admission`.
`RUNTIME` means the future approved runtime module prefix.
Its repository and module fields remain empty until #1893 records the destination and access approval.
It is not a literal Go import or permission to publish source.
The working repository name is not a fixed module path.

All package suffixes below are fixed.
Runtime packages first develop under `implementations/go/` on `go-cutover`, with the same suffixes.
#1894 replaces their module prefix during extraction.
No released `rae` product depends on those packages.
Before extraction, the `rae` product subset must already have that separation.

| Import suffix | Owner | Operations and type owners | Delivery |
| --- | --- | --- | --- |
| `base/fault` | RAE | Existing `Error`, `Category`, `CategoryOf`, `New` and error traversal | #1892 |
| `base/ingress` | RAE | Existing `Limits`, `Root`, `Parse`, errors and input bounds | #1892 |
| `base/canonjson` | RAE | Existing `JCS` and `Sorted`; retain their distinct profiles | #1892 |
| `base/digest` | RAE | Existing `SHA256` and `NewChecksum` | #1892 |
| `base/address` | RAE | Existing `Valid`, `Render`, `PlanRoot` and published grammar | #1892 |
| `base/clock` | RAE | Existing injected `Clock`, `Read`, `System` | #1892 |
| `contract/binding` | RAE | Generated published transport types and `Field[T]` | #1892 |
| `contract/validation` | RAE | Existing `New`, `Validator`, `Value`, schema checks, defaults and round trips | #1892 |
| `contract/admission` | RAE | Existing complete `Validator`, semantic contexts and materialization compiler interfaces; narrow existing artifact and realization operations | #1892; typed participant configuration boundary in #1788 |
| `contract/concept` | RAE | `AdmitBindings`, `SchemeSnapshot`, `ResolutionOutcome`, `Vocabulary` | #1781 |
| `contract/diagnostic` | RAE | Shared `Diagnostic`, `Range`, structured `Error` and fault traversal | #1782, #1783 |
| `sdl` | RAE | Bounded loading, scenario models, admission, instantiation, canonical digest, external concept subjects, artifact requirements and designation resolution | #1782–#1785 |
| `sdl/module` | RAE | `LockfileName`, `Lockfile`, `TrustPolicy`, `LoadLockfile`, `ResolveLock` | #1785 |
| `sdl/language` | RAE | `ApplyEdit`, `Edit`, `EditResult`, `Completions`, `Diagnostics`, `Format` | #1786 |
| `processor` | RAE | `Compile`, `CompileInstantiated`, `Compilation`, `RuntimeModel`, `TimeModelContract`, `ScenarioComponentOptions`, `ComponentOptions` | #1787 |
| `processor/planning` | RAE | `Plan`, `PlanWithManifest`, `Result` | #1787 |
| `processor/trial` | RAE | `Request`, `Compile`, `ScheduledEntry`, `BatchSchedule`, `PlanBatchSchedule` | #1788 |
| `processor/realization` | RAE | `ProjectConcern`, `ConcernDescriptors`, `HasRequiredObservationSupport` | #1787 |
| `processor/analysis` | RAE | `Analyze` and its existing analysis results | #1789 |
| `contract/runtime` | RAE | Shared native `ApplyResult`, typed materialization submissions and participant action handles | #1790 |
| `backend` | RAE | `Provisioner`, `Orchestrator`, `Evaluator`, `ParticipantRuntime`, `Manifest`, `LoadProfile` | #1790 |
| `backend/stub` | RAE | Portable `Manifest`, `Options` and inert implementations of the four backend interfaces | #1790 |
| `conformance` | RAE | `ValidateFixture`, `ValidateProcessor`, `ValidateModularReport`, `ModularControlEvidence`, `ModularOwnerObservation` and pure reports | #1796 |
| `command/authoring` | RAE | `Commands`, `Command`, `Streams`; retained command implementations | #1797 |
| `runtime/control` | RUNTIME | `New`, `ControlPlane`, operation submission/readback, snapshots, participant transitions and audit | #1791 |
| `runtime/provider` | RUNTIME | `Store`, `AtomicStore`, `LeaseProvider`, `OwnerLease`, `Capabilities`; injected RAE `clock.Clock` | #1792 |
| `runtime/execution` | RUNTIME | `Adapter`, `Request`, `LocalAdapter`; existing bounded execution machinery | #1793 |
| `runtime/temporal` | RUNTIME | `New`, `Adapter`, `Configuration`, `Worker`; ADR-113 composition | #1793 |
| `runtime/profile` | RUNTIME | Closed P0–P3 IDs, claims, nonclaims, capability facts, `DeclarationFor`, `Select`, `NewStoreCapabilities` | #1791, #1792 |
| `runtime/result` | RUNTIME | `AdmitResult`, `Context`; runtime-bound result enforcement | #1794, #1795 |

The model lists required entry points under `symbols`.
Existing packages keep their complete typed APIs after the move.
The list does not trim their signatures.
The existing `packages` and API snapshots continue to describe implemented code.
Declaration files have no function bodies.
They contain no product code.
See the source-bound [Go declarations](../../implementations/architecture-api/planned/) for the full contracts.
They fix each new type, field, method set and function signature.
The port issues must follow those contracts.
They record matching actual API snapshots; they do not design replacement consumer APIs.

Existing packages retain their complete API.
`existing_api_sha256` and the source layer bind that API.
The `symbols` list is an entry-point index, not permission to trim that API.

Declarations use the public RAE imports and the explicit `RUNTIME` prefix.
Only the runtime prefix changes when #1893 approves it.

Go type checking verifies imports and type references without executing proposed code.
The loader reads existing owners and all declared standard-library imports in one Go type universe.
It reuses those package objects for signatures and consumer examples.
For example, an injected `func() time.Time` must retain the same `time.Time` identity as `base/clock.Clock`.
Each declaration file has a SHA-256 commitment and a 64 KiB bound.
All declaration reads share a 4 MiB budget.

## SDL and authoring operations

The `sdl` package owns `Scenario` and `InstantiatedScenario` handles.
They retain admitted typed values and published document projections.
A serialized value or constructed zero value does not bypass semantic admission.
`Parse` accepts supplied bytes and `ParseOptions`.
`ParseSources` accepts a supplied source map, a root path and `ParseOptions`.
`ParseFile` accepts `fs.FS`, a contained root path and `ParseOptions`.
All three return an admitted `Scenario` or structured errors.
They enforce the byte, depth and import limits for the whole source graph.
They read only the supplied sources.

`Limits` retains all eleven parser controls from `_source_profile.py`.
`DefaultLimits` returns 8 MiB input bytes, 1 MiB scalar bytes, depth 128, 100,000 nodes and 256 aliases.
It permits 250,000 expanded nodes and 256 imports.
The composed graph is bounded at 500,000 nodes and 32 MiB.
Composition and namespace depth each default to 32.
Every limit must be positive; zero does not disable a limit or request defaults.
`Limits.Validate` and every parser entry point reject invalid limits.
`DefaultParseOptions` selects `sdl-yaml/v1`, rejects migration and uses those limits.
`ParseOptions` also retains the optional required semantic revision.
Unknown formats, policies and revisions return errors with structured details.
Migration keeps the existing source errors and rules for normal form.

`SourceContext` lets language services use the same source loader.
Use either `FS` or `Sources` to supply imports.
Neither permits host file access outside the supplied sources.
Without either source provider, only the root buffer is available.
`Root` is a canonical relative path within those sources.
An optional `RootBytes` overrides that root for unsaved editor content.
Imported bytes, authored pointers and source ranges retain their original paths.
All import, composition and source limits apply to the complete graph.
`ApplyEdit` and `Format` update only the root document.
Checks can still use imported declarations.

`AuthoredScenario` returns the authored fragment before import expansion, with the existing parse prerequisites.
`Validate`, `Instantiate`, `AdmitInstantiated` and `AdmitFamily` retain their separate admission stages.
`CanonicalDigest` uses the existing SDL semantic profile.
`Scenario` exposes its published document, with explicit ownership of returned mutable values.
Callers must not reconstruct RAES semantics from that projection.

`contract/diagnostic.Diagnostic` preserves code, severity, stage, source, pointer and an optional `Range`.
It also retains the existing domain, address and message fields.
Ranges retain the existing line and column conventions.
Errors preserve diagnostics through standard Go error traversal and the shared fault categories.
Message text does not control consumer behavior.
`ApplyEdit`, `Completions`, `Diagnostics` and `Format` return their existing structured results, including diagnostics and updated content where applicable.

`module.LoadLockfile` loads the supplied filesystem's lock.
`module.ResolveLock` takes a context, filesystem, source path and explicit `TrustPolicy`.
The default policy remains available but cannot become an implicit network grant.
`LockRecord` keeps the source, namespace and requested version.
It also keeps the resolved source, module ID/version and three distinct digests.
It also retains the signer identity.
`VerificationFacts` reports checks of the manifest, content, exports and signature.
It names the registry and signer key used for those checks.
`Policy` keeps signer rules and trusted keys for each registry.
It also keeps the choices for insecure HTTP and unsigned local sources.
The resolver checks pins and signatures before it calls `TrustPolicy`.
Policy approval cannot override a failed integrity check.
`ParseContext` checks the lock against the exact loaded bytes.
It calls the explicit policy for each resolved module.
It never treats a caller's lock record as verified facts.
Supplied-map parsing keeps ADR-119's rules.
Each import must be local, have a digest pin and match its own lock record.
This path never reads workspace trust files.
`ConceptSubjects` returns scenario-bound subjects.
`contract/concept.AdmitBindings` admits them against exact pinned scheme snapshots.
Subjects retain kind, owning contract, lifecycle phase, canonical reference and artifact digest.
Snapshots keep the scheme, authority, revision and source locator/digest.
They keep all current or superseded terms and their successors.
Each result gives the binding's outcome, active status and errors.
It also gives the resolved concept, when one exists.
`ResolutionOutcome.Admitted` follows the existing all-active, non-empty rule.

`sdl.ArtifactRequirements` returns typed requirements with complete owner trails and their published documents.
`ResolveRealizationDesignation` retains the scenario and field-pointer context.
The address owner renders those trails under `PlanRoot`.
Consumers do not copy address rules.

## Contracts and shared primitives

#1892 moves the nine existing packages named by the model's `existing` fields.
These are six base packages and three contract packages.
The exported `ingress.Limits` type already occurs in contract signatures.
The error, canonicalization, digest and address operations have direct consumers.
The runtime clock provider uses the existing injected `clock.Clock` identity.
This is the required public closure, not permission to publish all base helpers.

`contract/corpus` stays internal.
It retains the single embedded schema and vocabulary authority.
Other base helpers stay internal unless an implementation proves a required signature needs their identity.
Do not copy a helper or create a third contracts module.
Update generator destinations, imports, typed snapshots and owning designs together in #1892.
Keep published schema bytes and generated transport behavior unchanged.

`admission.New` constructs the complete semantic validator.
`Validator.Validate(id, data, limits, context)` returns `validation.Value` after full admission.
`CheckPortable` retains its narrower local claim.
`validation.New` and schema-only methods cannot stand in for full admission.
`Value.JSON` and `Value.Transport` return the admitted value's existing projections.
`Validator.Defaulted` retains published defaults; `Field[T]` distinguishes absent, null and supplied values.

The archive round trip uses `binding.MaterializationArchiveRecordV1`.
Its generated `Inventory` field remains `Field[json.RawMessage]`; that existing binding does not change here.
`admission.MaterializationArchive` takes this record and an optional `*binding.BackendRuntimeDescendantsV1`.
It owns insertion of the typed inventory, normalization, defaulting, serialization and admission.
`RestoreMaterializationArchive` returns the archive DTO, optional typed inventory and admitted value.
Consumers do not construct or decode the nested raw JSON themselves.
The [exact signatures](../../implementations/architecture-api/planned/rae/contract/admission.go.txt) fix both directions.
#1892 exposes this thin composition of the existing codec, defaulting and admission owners.
Its external consumer test must check supplied and omitted defaults, serialization, restored values and invalid input.

It must also reject stale context, wrong parent bindings and corrupted inventory bytes.
The inventory is admitted before inclusion in the archive.
Decode, normalization, defaulting, serialization and restored-value checks remain RAES operations.
A diagnostics-only adapter cannot replace these operations.
All materialization, snapshot and runtime DTO identities remain in RAE, including types used by the runtime repository.

The existing artifact owner supplies these narrow public operations through `contract/admission`:
`DefaultAssociatedArtifactLimits`, `AssociatedArtifactLimits`, `LoadAssociatedManifest`, `ValidateAssociatedManifest` and `AssociatedArtifactSetDigest`.
The validator takes an admitted parent context, caller-supplied readers and explicit limits.
`LoadAssociatedManifest` performs structural loading and defaulting only.
It returns `binding.AssociatedArtifactManifestV1`, which makes no full-admission claim.
`AssociatedArtifactSetDigest` takes that DTO so authors can compute the set identity before payload admission.
`ValidateAssociatedManifest` then checks the DTO against its parent and payload bytes.
Only that operation returns the fully admitted `validation.Value`.
It preserves identity, mechanism, parent, payload-size, digest and set-admission rules.
It never opens a payload locator itself.
#1892 exposes the already ported owner operations without reimplementing the #1780 semantics.

`EvaluateRealizationConstraint` exposes the existing contract owner's constraint evaluation and published relation status.
Its explicit `ConstraintLimits` preserve all bounds and defaults from `realization_structure/_models.py`.
Invalid bounds are refused; exhausted work never becomes success.
`RealizeParticipantConfiguration` takes the selected manifest and participant address.
It also takes the manifest reference/digest, overrides and owner hooks.
The native input and output keep the implementation ID, manifest version and binding owner.
Their values stay in canonical target order.
Each value keeps its target, strict scalar type and origin.
It keeps its literal or secret-reference kind and any exact control-context selection.
The owner callback returns the complete configuration in the same type.
RAE then checks that identity, target order, origins and value types stayed intact.
It also checks that secret references and control-context selections did not change.
`ParticipantControlContextValidator` checks each selected asset reference.
It cannot change that selection.
The result includes the canonical digest of the normalized configuration.
`ValidateParticipantConfigurationSelection` checks the exact join to the selected implementation.
#1788 preserves this typed callback boundary when it builds trial requests.
Callbacks and adapter-owned handles cannot be reduced to JSON.
They supply owner facts or the existing private-schema validation operation; they cannot grant whole-request admission.

`validation.Value` remains reserved for fully admitted published documents.
Native submodels use concrete structs or `admission.Fragment`, an opaque handle created by `AdmitFragment`.
The closed `FragmentProfile` set names existing native owner models.
It adds no published contract IDs or schema formats.
For example, trial input references, apparatus, execution authority and mixed binding assignments have distinct profiles.
The constructor copies and bounds the supplied document.
It checks the profile's native shape and local rules.
`Document` and construction accept native scalar, list and object roots.
Only the `RealizationValue` profile permits all bounded JSON roots; object model profiles still require objects.
Copying rejects cycles, unsupported carriers, invalid numbers and values outside the supplied limits.
`ProjectConcern` consumes and returns `RealizationValue` handles with the original root kind.
The result can be passed directly as the actual value to `EvaluateRealizationConstraint`.
That evaluator requires a `RealizationConstraint` document and returns a `RealizationConstraintEvaluation` result.
No consumer-defined wrapper is required around a scalar or collection.
It refuses unknown profiles and returns copies of its document.
Each caller checks the exact profile and all joins to its context.
A fragment handle grants no execution authority.
#1781 ports this shared construction boundary with the contract owner models.
The consuming port issues preserve their existing contextual checks.

## Processor and backend operations

`processor.Compile` takes an admitted scenario and explicit parameter values.
`CompileInstantiated` takes an admitted instantiated scenario and never instantiates it again.
Both return `Compilation`, preserving the compiled document, diagnostics and resource counts.
`TimeModelContract` returns the existing optional published time-model contract.
`planning.PlanWithManifest` admits a supplied backend manifest before planning.
`planning.Plan` retains ordinary planning with an already admitted manifest.
Compilation and planning remain separate operations and perform no execution.
Both planning functions take explicit `planning.Options`.
The snapshot is the predecessor for reconciliation; nil retains the existing empty-snapshot default.
`Scope` retains optional target, run and instantiation IDs.
Options also carry the apparatus-default resolver, per-address artifact facts, domain-profile context and processor manifest.
They retain mixed-control planning admission and the evaluation-refresh flag.
Each delegated apparatus default is resolved once and sealed into the plan's decisions.
`ExecutionPlan.Context` returns a copied record of the predecessor, scope and all selected owner facts.
It does not rerun owner callbacks when the plan is registered or inspected.
`NewMixedControlAdmission` copies an explicit host model without granting execution authority.
`ControlPlane.MixedControlPlanningAdmission` supplies that RAE-owned handle from its exact installed runtime context.
Planning consumes it without importing runtime; registration still checks the exact installed model.
#1787 must test updates/deletes against a nonempty predecessor and mismatched mixed-control context.

`trial.Request` carries the admitted family, task and experiment documents and pinned input references.
It also carries capture specifications, realization envelope, execution authority, apparatus and participant manifests, and explicit limits.
Keep realization assignments, mixed profiles, resolution contexts, mixed envelopes, source plans and mixed-composition limits.
It retains typed participant configuration validators and adapter-owned handles.
`trial.Compile` returns one admitted plan or a non-empty set of errors.
It cannot return both or neither.
Participant manifest keys retain participant address, implementation name/version and manifest version.
Apparatus keys instead retain component kind, component name/version and manifest version.
Configuration-validator keys use only the implementation name/version pair.
The trial limits retain all nine reference ceilings and their defaults from `contracts/trial_compilation.py`.
Mixed-composition limits retain all ten ceilings and defaults from `contracts/mixed_composition.py`.
Both limit types expose default constructors and positive-integer validation; compilation rejects invalid limits.
`PlanBatchSchedule` takes one complete admitted plan.
It checks the plan's integrity before it exposes any entry.
It returns the plan ID/digest, scheduling policy and entry/run IDs.
It also gives dispatch ordinals, the isolation-proof reference and admitted parallelism ceiling.
Only the plan's embedded proof can raise the default ceiling of one.
The operation remains pure.
Runtime owns allocation, effective parallelism, live dispatch and execution receipts.

Independent preflight remains available without trial compilation.
`sdl.ValidateExperimentSelectionAgainstFamily` checks family identity, variation points, domains and selection policies (#1784).
It then returns the experiment.
`admission.ValidateExperimentBindingTargets` resolves each plane through its owner (#1781).
It returns descriptors with canonical targets.
`ScenarioBindingTargetResolver` returns the canonical target, scalar type, permitted value kinds, sensitivity and binding owner.
The operation checks these facts and the selected manifests.
It refuses canonical-target collisions.
`ApparatusManifest` requires exactly one processor or backend manifest.

`ScenarioComponentOptions` takes an admitted scenario.
`CompiledComponentOptions` takes its compiled model.
Both return `ComponentOptions` or an error.
The portable stub options also preserve the separate `with_realization_envelope` flag.
The options preserve `with_orchestrator`, `with_evaluator`, `with_participant_runtime`, `with_time` and `with_observation`.
Preserve the invalid-model refusal and all defaults from `raes_runtime/registry_scenario.py`.
The selector moves to processor ownership because it only reads compilation results.
Authoring composition calls the selector, then passes the flags to `backend/stub.Manifest`.
The backend layer imports neither processor nor runtime.
Runtime uses the same selector and portable manifest implementation.
Runtime-only target factories and the temporal probe manager stay with runtime.

`backend` owns the portable protocol interfaces and manifest/profile admission.
Its declarations preserve provisioner validation/apply, orchestration/evaluation start/status/results/history/stop and participant lifecycle/admission methods.
`contract/runtime.ApplyResult` retains transient realization observations and typed materialization submissions as well as the published snapshot.
They must reach runtime admission before serialization removes transient fields.
`BindParticipantAction` constructs an opaque request from `ParticipantActionInput`, preserving its native selection, contexts, evidence and generation facts.
The constructor checks the existing manifest/selection/action-result joins and execution-scope/generation pairing.
`NativeActionExecution.Invoke` returns `NativeActionOutcome`: apply result, separate action result and optional post-state digest.
`ParticipantActionApplyResult` also preserves that separate action result.
`PreparingProvisioner` returns constructible native `RealizationPreparation`, including request/predecessor digests, operations, success and diagnostics.
`PrepareForRequest` derives those digests from the exact plan and predecessor using the existing owner rules.
Preparation is conditional selection; it establishes no observed delivery.
`ProfilePreparingProvisioner` also supplies the installed domain-profile context and read-only profile checks.
Optional autonomous and controlled participant interfaces retain binding, lifecycle control/readback and bounded concurrent action admission.
Go uses the separate `AdmitAutonomousAction` method because interface methods cannot narrow their return types.
Coordinated reset interfaces retain atomic participant/time reset behavior.
`OperationProvider` retains capabilities, check, start, observe, cancel and reconcile methods for one admitted invocation.
Runtime target composition negotiates these optional interfaces against the manifest; declarations alone establish no capability.
`ConceptSubjects` retains complete subject records, including lifecycle, contract, address and digest; it does not return only names.
Concrete backends supply native handles and credentials through those existing interfaces.
`backend/stub` supplies only portable inert doubles and the reference manifest.
Runtime owns the live registry, invocation and target assembly.
`processor/realization` retains projection, descriptors and observation-support checks.
Pure conformance uses shared contract carriers; live cases and harnesses belong to runtime.

## Runtime embedding boundary

`runtime/control.New` takes the target, provider interfaces, execution adapter, clock and existing control-plane options.
`NewTarget` admits the backend manifest and native component instances using the existing runtime registry.
The typed `Components` fields retain native backend handles and optional operation/native-action providers.
The registry rejects missing negotiated components.
It also rejects protocol mismatches.
It returns an opaque target.
Construction alone grants no operation authority.
`RegisterPlannerProducedPlan` accepts only a valid `planning.ExecutionPlan` from the planner.
It records exact phase digests and compiler context in that control plane.
It returns a `RegisteredPlan` handle.
`PlanCommand` selects a registered phase.
Runtime refuses a handle from another control plane.
It also refuses changed phase bytes or a mismatch with installed context.
`ParticipantCommand` retains native participant requests and requires exactly one command variant.
`ControlPlane.Submit` accepts the authenticated actor and a native command, optional base snapshot and idempotency key.
The owner checks the exact authoritative base snapshot and planner authorization before constructing any backend invocation binding.
Consumers never manufacture an invocation grant to submit a plan.
It returns the existing receipt, including idempotent replay behavior.
`Operation`, `Snapshot`, `TransitionParticipant` and `Audit` preserve actor-bound access and published results.
Transport authentication remains host-owned; the core still enforces actor, scope and target authority.
No constructor selects a permissive store or policy silently.
`Options` supplies typed participant outcome, crossing, information-state, control, flow, mixed and inject contexts.
It also supplies evidence resolution, materialization execution/inventory/archive contexts and bounded supervision settings.
The owner retains exact compiler-context matching and refuses unsupported combinations before admission.
`result.Context` exposes those live joins explicitly, together with the exact request, installed capabilities and predecessor.
`NewParticipantControlBinding` installs the exact selection, provider instances and trusted resolver.
It preserves v2 projection, stage state policy and contract digests.
`NewMixedControlBinding` joins the original compiled model to its live-cut owner and legacy declarations.
Directed delivery also requires that owner's `DeliveryCutResolver` interface.
`NewInjectDeliveryBinding` joins the compiled model to its content, crossing-evidence and live-cut resolver.
The constructors check the original model and refuse mismatched owner inputs.
Inject execution retains separate admission, revalidation and authenticated outcome resolution hooks.
These hooks cannot issue dispatch grants or commit state.

Live policy decisions have separate owner protocols.
`Options.CrossingPolicy` installs `CrossingResolver`.
Its `Resolve` receives the current intent and authoritative snapshot.
It returns the policy, six semantic gates, support/downgrade facts and any transformation or opacity binding.
The core still owns actor, capability and history-cut checks.
The same owner supplies historical validation facts and authenticated participant-view evidence.
These calls do not replace the admission indexes in `ParticipantContexts`.
`Options.FlowSink` installs `FlowSinkResolver`; its request binds intent, crossing, snapshot, sink kind and exact history-head references.
The result retains the published relation and trusted validation context.
`EnforceFinalSinkFlowControl` makes the selection explicit; nil preserves the reference default of true.
When enforcement is selected, an absent or failed owner never grants a permit.
Explicit false retains the existing legacy path.
The core validates and commits the exact-cut decision before an effect or disclosure.
Resolver inputs are detached copies, and callbacks retain the existing mutation/re-entry fence.

`SubmitInject` admits a typed trigger through the core and returns its operation receipt.
It retains the trigger's request key, live revalidation, actor scope and installed execution owner.
`SuperviseOperation` accepts observe, cancel or reconcile intent with stable operation/control IDs.
The core creates the control binding and bounded budget; `SubmitOperationControl` also admits a prebuilt control after exact actor and parent checks.
`ControlResponse` returns the matching typed response, or nil when none is available.
`StopAdmission` authorizes and persists the idempotent stop with its audit through the owner.
`ResolveIndeterminateOperation` retains the distinct administrative receipt and idempotency key.
Its closed disposition accepts the current stored snapshot; it never proves that an uncertain effect stopped.
These #1791 entry points retain their existing authorization and transaction checks.
Consumers need not call a backend or store directly to reach them.

Inject delivery has its own core operation and readback.
`DeliverParticipantInject` takes `ParticipantInjectApplicationV1` and returns its published delivery receipt.
It retains the application's request key, expected snapshot revision, episode, audience and live control cut.
`InjectOccurrence`, `InjectOutcome`, `InjectCorrelation`, `InjectResult`, `InjectDelivery` and `InjectCapture` return their distinct typed results.
An absent or actor-inaccessible record returns nil, as in the reference.
Delivery readback also rechecks the current audience binding and successful parent state.
`InjectArtifact` returns copied bytes and a presence flag, so a present empty artifact differs from an absent one.
`InjectCaptureResult` retains its status and optional native observation document.
The owner validates that observation through the existing observation lifecycle; a failed capture cannot carry it.
These reads grant no delivery or world-effect permission.

`ControlResolver.EffectOperation` returns a concrete `EffectOperation`, or nil for an unsupported owner.
It carries the existing inject, handoff or interrupt kind and the exact native owner inputs.
These include a status view, closed control intent, crossing evidence, inject trigger/application and participant address where required.
The resolver returns data under the callback fence; it never submits the effect itself.
`DispatchParticipantControlEffects` authorizes the drain caller before reading committed effects.
The core checks every declared target coordinate against the returned owner input and trusted context.
It retains logical-key claims, predecessor order, causal budgets and the original principal.
Owner submission and outcome readback stay separate from admitting the intent.
`EffectRealization` retains effect ID, disposition and receipt reference, plus the complete native realization binding.
Applied, failed, withheld, unsupported and indeterminate outcomes retain their distinct meanings.
`DeliverParticipantDirectedView` and `RecordParticipantControl` expose the same guarded owners for direct callers.
`DispatchParticipantCancellation` resumes the retained intent through its owner.
`ParticipantCancellationStatus` reads the outcome proved by that owner.
The status keeps the control disposition and target/control IDs.
It also keeps the backend disposition, optional cancellation effect and evidence references.
Accepted control intent does not prove that the target stopped.
Caller-supplied inputs cannot select another effect's parent claim or substitute the drain caller as its principal.

Runtime-sequence delivery starts at the owner, before the dispatcher.
`OpenRun`, `Run` and `RetireRun` manage the existing scoped run contexts.
`RunContext.AdvancePlan` preserves the fixed phase order and never re-invokes an uncertain phase.
`AdmitExperiment` takes pure `trial.RealizationInputs`, native trial services and an explicit run-store factory where durability requires it.
Replacement also requires the exact compilation request and archive owner.
Trial requests, observations, results and archive callbacks retain their native fields and typed contract children.
Services admit, configure, observe, capture, clean up, stop and verify; retry preparation remains a separately checked optional protocol.
They do not allocate runs, choose retries or drive phases.
`trial.RealizeEntry` retains the pure single-entry realization and its planner-issued plan; it imports no runtime code.

`BindSequence` accepts run/experiment kind, owned scope, execution ID, worker ID, state queue and bounded delivery timing.
A run requires its exact valid planner artifact and matching target manifest.
An experiment requires its prior admission and matching original actor/scopes.
The core derives the engine/store digest and request commitment, claims the durable decision and retains the exact native artifacts.
Only then does it return `RuntimeSequenceReference` for `Dispatcher.SubmitRuntime`.
`AdvanceSequence` checks worker identity, target, engine digest and the exact registered binding.
It advances under the original principal; constructing a reference grants no authority.
After reopening, the host must re-admit the exact artifacts before advancement.
`NewRuntimeWorker` registers the existing state-progress activity on the bound state queue, with scoped worker authority and finite capacity.
It receives no ledger credentials or mutable store.

Provider `LoadRuntimeDecisions` and `ClaimRuntimeDecision` preserve the existing closed decision registry.
`RuntimeDecision` exposes an owner-derived ID, schema version, copied canonical bytes and an optional typed sequence projection.
`DecodeRuntimeDecision` rejects unknown variants and invalid native records; providers do not copy their private schemas.
The atomic claim returns true only for a new decision, false for an identical replay and `ErrConflict` for a different value under the same ID.
Sequence decision identity binds schema version, kind, scope and execution ID.
Its committed value also binds actor/scopes, artifacts, worker, queues and timing; conflicting rebinding cannot overwrite it.
`ValidateIdenticalDecision` owns that complete comparison.
`Store.Identity` supplies the existing non-secret ledger kind and coordinate tuple for `RuntimeStoreDigest`.
Local coordinates retain the canonical database path; PostgreSQL retains host, integer port, database and user; memory identity stays process-local.
Passwords and connection strings are excluded.
Store admission and capability checks still determine which profile can use the provider.
The #1791/#1793 consumer fixtures must use real public packages.
They must execute trigger/readback/delivery and bind/submit/advance.
They must refuse stale or unauthorized delivery and distinguish absent data from empty artifact bytes.
Effect fixtures must check exact inject and handoff/cancellation coordinates without executing effects inside resolvers.
The #1792 store tests must prove identical replay and refuse conflicting bindings.
Change the worker, artifact or timing in each conflict case.
A claim must commit as one change or leave no partial write.
These are existing behavior checks for the declared interfaces, not new execution semantics.

`runtime/provider.Store` and `AtomicStore` retain existing transactional operation, receipt, snapshot and audit semantics.
`LeaseProvider` and `OwnerLease` retain process-owner admission, lock identity and conflict rules.
They do not introduce distributed fencing or lease renewal.
The [store declarations](../../implementations/architecture-api/planned/runtime/runtime/provider.go.txt) fix each read, CAS, claim, transition and terminal-commit operation.
`OperationRecord` is an opaque native handle with canonical `JSON`, receipt/status and typed claim projections.
`DecodeOperationRecord` restores it through the runtime owner's existing record checks.
External durable providers preserve the owner's encoded record.

The idempotency index key is the existing actor, operation kind and client key within the admitted target/run store.
`IdempotencyClaimIdentity` derives it.
`ValidateIdempotencyReplay` checks the full fixed context and exact fingerprint.
It also checks decision/result history commitments and legacy replay rules.
`FindByIdempotency` takes a concrete admission context.
Providers call the owner helpers under the same transaction as lookup, conflict checks and publication.
`ValidateNewClaim` checks peer claims, snapshot revision, stopped admission and current-state restrictions from its typed `ClaimState`.
No provider needs to decode private record JSON to implement claims.

`CommitInvocationTransition` compares the complete expected record with the stored record.
It then commits the next record and audit event as one change.
`ValidateInvocationTransition` retains the owner's supervision-cut checks; `RecordsEqual` supplies complete owner-defined equality.
An exact committed record/audit retry is idempotent; a different incumbent returns `ErrConflict` without partial writes.
`AdmitExecutionGeneration` atomically advances a durable non-negative generation and refuses exhaustion.
`StopEffectAdmission` persists the first stop and its audit atomically; the stop survives reopening.
Claim insertion checks that persisted stop in the same transaction.
The conflict, idempotency-conflict, admission-stop, indeterminate and stale-base errors retain distinct `errors.Is` identities and existing fault categories.
These are #1792's existing guarantees, independent of any later P3 design.

They do not copy its schema or validation.
`Capabilities` describes actual provider guarantees; an interface declaration grants none.
Store/provider implementations remain runtime-owned.
`runtime/execution.Adapter` retains bounded calls, physical-slot retention, cancellation, drain and uncertain-effect semantics.
Its deadline intervals use `time.Duration` and the existing monotonic budget, not the injected wall clock.
`runtime/temporal` composes those existing operations under ADR-113.
`Options.Distributed` accepts `execution.Dispatcher`; `temporal.Adapter` implements that interface.
The dispatcher retains worker identity, stable delivery binding, operation/runtime submission and control delivery.
`Configuration` separates workflow, effect and control queues, worker identity, namespace and bounded RPC budget.
Validation rejects duplicate queues, invalid names and invalid budgets.
`Dial` wraps the supported Temporal SDK at a host-supplied endpoint with explicit TLS and authorization settings.
`NewWorker` receives that client, configuration, backend operation provider and separately scoped effect/control `WorkerAuthority` interfaces.
It starts the existing workflow/effect/control workers with separate bounded capacities.
The worker receives no mutable store, snapshot publication method or ledger credential.
`ControlPlane.WorkerAuthority` exposes the authenticated owner service for these grants; remote adapters preserve the same protocol.
Each grant binds the exact request, worker, owner/execution generation and remaining budget, and can be consumed only once.
Redelivery, transport retries and Temporal acknowledgement never create another effect permission.

`runtime/result.AdmitResult` takes an explicit runtime context and the published result binding.
`AdmitApplyResult` accepts the native result with its transient observation and materialization inputs intact.
It checks the live operation, history and target.
It also checks ownership and execution/evidence joins.
It reuses `contract/admission` for published-contract checks and never copies the schemas or validators.
A published result that is valid as a document does not establish successful execution.

Coldlight needs coordinated service for many tenants and processes.
P3 remains an explicit nonclaim under ADR-104 and #1891.
This design exposes the existing control/provider boundaries; it does not claim that the Go port or repository split supplies P3.
`runtime/profile.DeclarationFor(P3)` returns the existing unavailable declaration and its nonclaims.
`Select(P3)` fails with `ErrProfileUnavailable`; `control.New` uses that same selection.

`NewStoreCapabilities` admits only the closed store capability values.
It returns immutable facts; `Values` returns a copy.
#1791 ports the declarations and selection, while #1792 ports provider capability checks.
[Issue #1917](https://github.com/OpenRAE/rae/issues/1917) owns the future coordinated-profile design in the runtime repository.
That work must name and verify the missing coordination guarantees before P3 becomes available.
It is separate from the existing Go launch.
Consumer readiness still requires the profile's later implementation and verification.

## Combined command composition

RAE exports this minimum composition shape in `command/authoring`:

```go
// Planned signatures; implemented by #1797.
type Streams struct {
    In io.Reader
    Out io.Writer
    Err io.Writer
}
type Command struct {
    Path []string
    Summary string
    Run func(context.Context, []string, Streams) int
}
func Commands() []Command
```

Each record identifies one retained leaf command and its existing implementation.
`Run` receives that leaf's original arguments, including flags, and returns its existing exit status.
It retains argument parsing, help, diagnostics and output behavior.
It does not call `os.Exit` or alter process streams.
Fresh metadata prevents one host from changing another host's command registry.
The host composes the shared group help from the leaf paths and summaries.
This surface needs no new CLI framework, protocol or runtime import in RAE.

Runtime publishes `RUNTIME/cmd/raes` and installs the sole `raes` binary.
It registers the returned authoring leaves and its own runtime/live-conformance leaves in one tree.
It rejects duplicate command paths before dispatch.
Keep `sdl`, `processor`, `conformance`, `semantic` and `runtime`, including their current subcommands and flags.
Keep root version/log-level behavior, result shapes and exit status 70 for unexpected failures.
The composed command corpus in #1797 verifies the complete tree, including both conformance owners.

RAE publishes `RAE/cmd/raes-mcp` and installs only `raes-mcp`.
MCP uses retained authoring services directly and keeps its current tools, inputs, outputs and diagnostics.
Neither its library nor its executable imports runtime.
Installation assets contain no second `raes` publisher.
#1897 rehearses the exact paired binary artifacts before #1804 announces cutover.

## Consumer and dependency mapping

| Consumer | Required operations and module choice | Existing delivery links |
| --- | --- | --- |
| Environment packs | RAE SDL, modules, language services, concepts, artifacts, contracts, participant configuration, compilation, trial compilation, planning, stub manifest and realization operations | [env-packs #552](https://github.com/OpenRAE/env-packs/issues/552) |
| LilRAE | RAE authoring/planning/contracts and portable backend interfaces; RUNTIME control, providers, execution and result admission for its embedded runtime manager | [#1562](https://github.com/OpenRAE/lilrae/issues/1562), [#1567–#1573](https://github.com/OpenRAE/lilrae/issues/1567), [#1575](https://github.com/OpenRAE/lilrae/issues/1575), [#1576](https://github.com/OpenRAE/lilrae/issues/1576), [#1577](https://github.com/OpenRAE/lilrae/issues/1577), [#1580](https://github.com/OpenRAE/lilrae/issues/1580) |
| Coldlight | RUNTIME control plane, durable providers, shared execution/Temporal and result admission; RAE contract bindings/admission for shared DTO identity | Maintainer consumer requirements in [#1825](https://github.com/OpenRAE/rae/issues/1825#issuecomment-6555295922) |
| Extracted runtime | Released RAE SDL, processor, contracts, portable backend/stub, pure conformance and authoring-command imports | [#1892](https://github.com/OpenRAE/rae/issues/1892), #1893–#1897 |

The environment-pack map uses its [operation map](https://github.com/OpenRAE/env-packs/blob/a533c93/docs/development/raes-operations.md) and [consumer interfaces](https://github.com/OpenRAE/env-packs/blob/a533c93/internal/raes/raes.go).
The maintainer's audit adds runtime inventory and materialization archive records to the 99-symbol map, for 101 imports.
Those are RAE contract operations, not a requirement for environment packs to run the live runtime.
No mock, Python subprocess or duplicated validator satisfies that adapter boundary.
#552 remains open until real public-package contract tests pass.

The existing LilRAE blockers map to these boundaries:

| LilRAE issue | Required public operations |
| --- | --- |
| [#1562](https://github.com/OpenRAE/lilrae/issues/1562) | Runtime stores and shared archive/evidence bindings |
| [#1567](https://github.com/OpenRAE/lilrae/issues/1567) | Portable backend interfaces, provider registration and shared runtime control |
| [#1568](https://github.com/OpenRAE/lilrae/issues/1568) | SDL sources, module admission, planning and trial compilation |
| [#1569](https://github.com/OpenRAE/lilrae/issues/1569), [#1570](https://github.com/OpenRAE/lilrae/issues/1570), [#1571](https://github.com/OpenRAE/lilrae/issues/1571) | RAE plans and portable backend protocols; existing external realization providers |
| [#1572](https://github.com/OpenRAE/lilrae/issues/1572) | Published attestation admission and runtime-bound result/evidence checks |
| [#1573](https://github.com/OpenRAE/lilrae/issues/1573) | Shared runtime control, execution and participant interfaces |
| [#1575](https://github.com/OpenRAE/lilrae/issues/1575) | Pure conformance, contract admission and backend profiles |
| [#1576](https://github.com/OpenRAE/lilrae/issues/1576) | SDL language services and shared runtime participant control |
| [#1577](https://github.com/OpenRAE/lilrae/issues/1577) | Backend protocols, shared contract bindings and runtime result admission |
| [#1580](https://github.com/OpenRAE/lilrae/issues/1580) | Real module imports, contract tests and pinned tool checks |

The public module may not depend on a consumer's `internal/raes` adapter.
Each consumer implements its own local adapter against these released interfaces.
All current GitHub blocking links remain intact.
The dependency API currently links twelve LilRAE issues and #1892 to this issue.
Environment-pack and Coldlight requirements also remain visible here even when they have no blocking edge.

## Compatibility and verification

Keep one shared Go type identity for every contract, including snapshots, receipts and materialization records.
Both modules use the same selected RAE module version in one build.
Do not copy structs, fork schemas or use a contracts-only repository.

The first joint release is the existing breaking #1804 launch.
Before it, #1892 may use a pinned repository commit or Go pseudo-version for the real consumer fixture.
Released candidates pin exact published module versions, with `GOWORK=off` and read-only resolution.
No committed local-path `replace`, sibling checkout or Python process is required.
RAE module tags have the `implementations/go/` prefix.
The approved runtime module uses the tag prefix required by its final module directory.

Follow [Go module versioning](https://go.dev/doc/modules/version-numbers).
Use a new major module path for incompatible changes after v1.
A v0 release has no upstream promise of compatibility.
This project still requires review of breaking consumer changes.
Contract schema versions and IDs retain their separate RAE authority.
After launch, runtime can release on its own.
Each release states the RAE version it supports.
The launch tests pin the pair; later releases keep ordinary external contract and conformance tests.

ARCH-015 checks planned owners, public paths and symbols.
It also checks delivery issues, consumers and public dependencies.
It rejects reverse imports, private paths and unknown dependencies.
It also rejects cycles and more than one publisher per binary.
ARCH-014 binds this design and its generated package/publisher view to the current overview.
The existing Go compiler and ARCH-001 through ARCH-014 still govern implemented code.
#1892 adds the real external consumer fixture; this design check is not proof that future packages compile.
The immutable #1891 source baseline is unchanged.
The final move inventory must bind this API map and the completed Go source.
A transfer still needs separate approval.
