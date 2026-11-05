# Public Go consumer API

This reference fixes the public import boundary for [#1825](https://github.com/OpenRAE/rae/issues/1825).
The [repository split](issue-1891-runtime-repository-boundary.md) fixes ownership.
The `consumer_api` section of [the architecture model](../../implementations/architecture.json) records the package map, public identifiers, consumers and delivery issues.
These are planned interfaces, not claims that the packages exist.
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
| `sdl` | RAE | Bounded loading, scenario models, admission, instantiation, canonical digest, external concept subjects, artifact requirements and designation resolution | #1782–#1785 |
| `sdl/module` | RAE | `LockfileName`, `Lockfile`, `TrustPolicy`, `LoadLockfile`, `ResolveLock` | #1785 |
| `sdl/language` | RAE | `ApplyEdit`, `Edit`, `EditResult`, `Completions`, `Diagnostics`, `Format` | #1786 |
| `processor` | RAE | `Compile`, `CompileInstantiated`, `Compilation`, `RuntimeModel`, `TimeModelContract`, `ScenarioComponentOptions`, `ComponentOptions` | #1787 |
| `processor/planning` | RAE | `Plan`, `PlanWithManifest`, `Result` | #1787 |
| `processor/trial` | RAE | `Request`, `Compile`, `ScheduledEntry`, `BatchSchedule`, `PlanBatchSchedule` | #1788 |
| `processor/realization` | RAE | `ProjectConcern`, `ConcernDescriptors`, `HasRequiredObservationSupport` | #1787 |
| `processor/analysis` | RAE | `Analyze` and its existing analysis results | #1789 |
| `backend` | RAE | `Provisioner`, `Orchestrator`, `Evaluator`, `ParticipantRuntime`, `Manifest`, `LoadProfile` | #1790 |
| `backend/stub` | RAE | Portable `Manifest`, `Options` and inert implementations of the four backend interfaces | #1790 |
| `conformance` | RAE | `ValidateFixture`, `ValidateProcessor`, `ValidateModularReport`, `ModularControlEvidence`, `ModularOwnerObservation` and pure reports | #1796 |
| `command/authoring` | RAE | `Commands`, `Command`, `Streams`; retained command implementations | #1797 |
| `runtime/control` | RUNTIME | `New`, `ControlPlane`, operation submission/readback, snapshots, participant transitions and audit | #1791 |
| `runtime/provider` | RUNTIME | `Store`, `AtomicStore`, `LeaseProvider`, `OwnerLease`, `Capabilities`; injected RAE `clock.Clock` | #1792 |
| `runtime/execution` | RUNTIME | `Adapter`, `Request`, `LocalAdapter`; existing bounded execution machinery | #1793 |
| `runtime/temporal` | RUNTIME | `New`, `Adapter`, `Configuration`, `Worker`; ADR-113 composition | #1793 |
| `runtime/result` | RUNTIME | `AdmitResult`, `Context`; runtime-bound result enforcement | #1794, #1795 |

The model's `symbols` lists identify the required entry points.
Existing packages retain their complete typed APIs after relocation; the list does not trim their signatures.
The existing `packages` and API snapshots continue to describe implemented code.
Future implementation issues record exact Go type snapshots before their code, through ADR-122.
The following operation contracts fix the inputs, results and ownership they must preserve.

## SDL and authoring operations

The `sdl` package owns `Scenario` and `InstantiatedScenario` handles.
They retain admitted typed values and published document projections.
A serialized value or constructed zero value does not bypass semantic admission.
`Parse` accepts supplied bytes and `Limits`.
`ParseSources` accepts a supplied source map, a root path and `Limits`.
`ParseFile` accepts `fs.FS`, a contained root path and `Limits`.
All three return an admitted `Scenario` or structured errors.
They preserve composition byte, depth, import and source-containment limits.
They perform no implicit network fetch or unrestricted filesystem read.

`AuthoredScenario` returns the authored fragment before import expansion, with the existing parse prerequisites.
`Validate`, `Instantiate`, `AdmitInstantiated` and `AdmitFamily` retain their separate admission stages.
`CanonicalDigest` uses the existing SDL semantic profile.
`Scenario` exposes its published document, with explicit ownership of returned mutable values.
Callers must not reconstruct RAES semantics from that projection.

`sdl.Diagnostic` preserves code, severity, stage, source, pointer and an optional `Range`.
Ranges retain the existing line and column conventions.
Errors preserve diagnostics through standard Go error traversal and the shared fault categories.
Message text does not control consumer behavior.
`ApplyEdit`, `Completions`, `Diagnostics` and `Format` return their existing structured results, including diagnostics and updated content where applicable.

`module.LoadLockfile` loads the supplied filesystem's lock.
`module.ResolveLock` takes the filesystem, source path and explicit `TrustPolicy`.
The default policy remains available but cannot become an implicit network grant.
`ConceptSubjects` returns scenario-bound subjects.
`contract/concept.AdmitBindings` admits them against exact pinned scheme snapshots.

`sdl.ArtifactRequirements` returns typed requirements with complete owner trails and their published documents.
`ResolveRealizationDesignation` retains the scenario and field-pointer context.
The address owner renders those trails under `PlanRoot`; consumers do not copy address rules.

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

The materialization archive round trip uses `binding.MaterializationArchiveRecordV1` and the canonical runtime inventory binding.
The inventory is admitted before inclusion in the archive.
Decode, normalization, defaulting, serialization and restored-value checks remain RAES operations.
A diagnostics-only adapter cannot replace these operations.
All materialization, snapshot and runtime DTO identities remain in RAE, including types used by the runtime repository.

The existing artifact owner supplies these narrow public operations through `contract/admission`:
`DefaultAssociatedArtifactLimits`, `AssociatedArtifactLimits`, `LoadAssociatedManifest`, `ValidateAssociatedManifest` and `AssociatedArtifactSetDigest`.
The validator takes an admitted parent context, caller-supplied readers and explicit limits.
It preserves identity, mechanism, parent, payload-size, digest and set-admission rules.
It never opens a payload locator itself.
#1892 exposes the already ported owner operations without reimplementing the #1780 semantics.

`EvaluateRealizationConstraint` exposes the existing contract owner's constraint evaluation and published relation status.
`ValidateParticipantConfiguration` accepts an admitted implementation manifest, configuration and caller-supplied `ParticipantConfigurationValidator`.
#1788 preserves this typed callback boundary when it builds trial requests.
Callbacks and adapter-owned handles cannot be reduced to JSON.
They supply owner facts or the existing private-schema validation operation; they cannot grant whole-request admission.

## Processor and backend operations

`processor.Compile` takes an admitted scenario and explicit parameter values.
`CompileInstantiated` takes an admitted instantiated scenario and never instantiates it again.
Both return `Compilation`, preserving the compiled document, diagnostics and resource counts.
`TimeModelContract` returns the existing optional published time-model contract.
`planning.PlanWithManifest` admits a supplied backend manifest before planning.
`planning.Plan` retains ordinary planning with an already admitted manifest.
Compilation and planning remain separate operations and perform no execution.

`trial.Request` carries the admitted family, task and experiment documents and pinned input references.
It also carries capture specifications, realization envelope, execution authority, apparatus and participant manifests, and explicit limits.
It retains typed participant configuration validators and adapter-owned handles.
`trial.Compile` returns admitted trial plans and diagnostics.
`PlanBatchSchedule` remains pure; live dispatch and execution receipts belong to runtime.

`ScenarioComponentOptions` accepts the admitted scenario or its compiled model and returns `ComponentOptions` or an error.
The options preserve `with_orchestrator`, `with_evaluator`, `with_participant_runtime`, `with_time` and `with_observation`.
Preserve the invalid-model refusal and all defaults from `raes_runtime/registry_scenario.py`.
The selector moves to processor ownership because it only reads compilation results.
Authoring composition calls the selector, then passes the flags to `backend/stub.Manifest`.
The backend layer imports neither processor nor runtime.
Runtime uses the same selector and portable manifest implementation.
Runtime-only target factories and the temporal probe manager stay with runtime.

`backend` owns the portable protocol interfaces and manifest/profile admission.
Concrete backends supply native handles and credentials through those existing interfaces.
`backend/stub` supplies only portable inert doubles and the reference manifest.
Runtime owns the live registry, invocation and target assembly.
`processor/realization` retains projection, descriptors and observation-support checks.
Pure conformance uses shared contract carriers; live cases and harnesses belong to runtime.

## Runtime embedding boundary

`runtime/control.New` takes the target, provider interfaces, execution adapter, clock and existing control-plane options.
`ControlPlane.Submit` accepts the authenticated actor, scope, target, operation request and idempotency identity.
It returns the existing receipt, including idempotent replay behavior.
`Operation`, `Snapshot`, `TransitionParticipant` and `Audit` preserve actor-bound access and published results.
Transport authentication remains host-owned; the core still enforces actor, scope and target authority.
No constructor selects a permissive store or policy silently.

`runtime/provider.Store` and `AtomicStore` retain existing transactional operation, receipt, snapshot and audit semantics.
`LeaseProvider` and `OwnerLease` retain owner epochs, fences, renewal and conflict rules.
`Capabilities` describes actual provider guarantees; an interface declaration grants none.
Store/provider implementations remain runtime-owned.
`runtime/execution.Adapter` retains bounded calls, physical-slot retention, cancellation, drain and uncertain-effect semantics.
`runtime/temporal` composes those existing operations under ADR-113.

`runtime/result.AdmitResult` takes an explicit runtime context and the published result binding.
It checks live operation, history, target, ownership and execution/evidence joins.
It reuses `contract/admission` for published-contract checks and never copies the schemas or validators.
A published result that is valid as a document does not establish successful execution.

Coldlight needs coordinated service for many tenants and processes.
P3 remains an explicit nonclaim under ADR-104 and #1891.
This design exposes the existing control/provider boundaries; it does not claim that the Go port or repository split supplies P3.
Consumer readiness still requires the profile's separate delivery and verification.

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

The public module may not depend on a consumer's `internal/raes` adapter.
Each consumer implements its own local adapter against these released interfaces.
All current GitHub blocking links remain intact.
The dependency API currently links twelve LilRAE issues and #1892 to this issue.
Environment-pack and Coldlight requirements also remain visible here even when they have no blocking edge.

## Compatibility and verification

Keep one shared Go type identity for every contract, including snapshots, receipts and materialization records.
Both modules use the same selected RAE module version in one build.
Do not copy structs, fork schemas or use a contracts-only repository.

The first coordinated release is the existing breaking #1804 launch.
Before it, #1892 may use a pinned repository commit or Go pseudo-version for the real consumer fixture.
Released candidates pin exact published module versions, with `GOWORK=off` and read-only resolution.
No committed local-path `replace`, sibling checkout or Python process is required.
The RAE submodule uses tags with the `implementations/go/` prefix.
The approved runtime module uses the tag prefix required by its final module directory.

Follow [Go module versioning](https://go.dev/doc/modules/version-numbers).
Use a new major module path for incompatible changes after v1.
A v0 release carries no upstream compatibility guarantee; this project still requires explicit review of breaking consumer changes.
Contract schema versions and IDs retain their separate RAE authority.
Independent runtime releases declare the RAE version they support.
The launch tests pin the pair; later releases keep ordinary external contract and conformance tests.

ARCH-015 validates planned owners, public paths, symbols, delivery issues, consumers and dependency closure.
It rejects reverse imports, private paths, unknown dependencies, cycles and duplicate executable publishers.
ARCH-014 binds this design and its generated package/publisher view to the current overview.
The existing Go compiler and ARCH-001 through ARCH-014 still govern implemented code.
#1892 adds the real external consumer fixture; this design check is not proof that future packages compile.
The immutable #1891 source baseline is unchanged.
The final extraction inventory must bind this API map and the completed Go source before a separately authorized transfer.
