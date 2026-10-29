# Scenario variation and deterministic trial realization

For executable bounded replacement of failed or invalid trials, see
[trial replacement and author migration](trial-replacement-migration.md).

This reference defines the RAES path from an authored scenario family
to archival experiment provenance. It applies ADR-084.
The package and artifact boundaries come from ADR-036, ADR-053, ADR-055,
ADR-065, ADR-068, ADR-074, and ADR-078.

Issue #652 supplied this normative design.
Follow-on work has published the SCE-002 family and selection contracts.
It has also published the admitted-plan, trial compilation, realization,
and runtime-fact contracts, with focused tests.
Names here remain conceptual unless a published contract or implementation binds them.
The semantic boundaries, identities, phase order, and failure behavior remain binding.
Each implementation issue must use them.

## Scope and claims

The design covers:

- Compose an authored scenario family with deterministic rules.
- Name bounded scalar and structural variation points.
- Give the experiment ownership of selection, allocation, sampling, and stochastic controls.
- Compile and admit a trial set without dependence on the schedule.
- Use explicit SDL instantiation and derivation provenance.
- Use typed late-bound runtime facts.
- Realize the scenario through a backend within the selected envelope.
- Keep scheduling as an external consumer.
- Link to existing experiment run, study, apparatus, evidence, and lineage records.

The reference itself adds no generator, sampler, or trial compiler.
It adds no scheduler, persistence service, API, environment pack, or adaptive policy.
Follow-on work has delivered the typed run-local fact contract and in-process binding plane.
It has also delivered deterministic trial compilation and sealed-entry realization.
The remaining conceptual sketches retain their stated implementation boundaries.
The reference does not guarantee the same backend behavior or artifact availability.
It does not guarantee reconstruction of hidden state or exact replay from a seed alone.

## Terminology

**Scenario family**
: A composed SDL authoring artifact that has passed semantic admission.
  It has zero or more named variation points.
  Zero points denotes a singleton family.

**Variation point**
: A stable SDL symbol for one bounded location where a concrete scenario may differ.
  The point declares the valid domain and target kind.
  It does not choose a value.

**Selection policy**
: Intent owned by the experiment.
  It enumerates or samples values from one or more scenario family domains.
  It binds those values to logical trial coordinates.

**Logical trial coordinate**
: A stable address with meaning in the experiment.
  Its dimensions include condition, replicate, and attempt coordinate.
  It exists before scheduling.
  It is not a worker or queue index.

**Admitted trial plan**
: A closed, immutable artifact that states execution intent.
  All its trial entries are fully selected and valid.
  The apparatus can realize them.
  The plan is neither a scheduler queue nor an archival run.

**Trial realization**
: An operation owned by the processor.
  It applies one admitted entry's structural selections and scalar bindings.
  It uses the public SDL instantiation path.

**Runtime fact**
: An authorized observation or secret reference.
  It fills a compiled late-bound sink after admission.
  It cannot change scenario or experiment meaning.

**Run**
: The existing `experiment-run-v1` archival record for one execution. “Trial”
  is experiment terminology; it does not introduce a second archival root.

### Composition and the campaign boundary

SCE-002's “atomic scenarios into larger campaigns” uses ADR-053's existing composition model.
An author may write and validate a reusable SDL module as a bounded unit.
A root SDL document may import the typed exports of many such units.
Composition resolves trust, parameters, namespaces, references, and collisions.
It then produces one expanded canonical `Scenario`.
The processor and runtime never execute a nested tree of atomic scenario lifecycles.

“Campaign” is therefore an author-facing view, not a new portable root:

- one executable composed campaign is one canonical scenario assembled from
  reusable SDL modules and fragments; and
- a campaign spanning multiple executions is an experiment design and its
  admitted trial plan, archived through the existing run/study contracts.

The second form does not join runtime state to compose scenario snapshots.
It selects already composed families through experiment policies.
This preserves ADR-055's separate scenario, task, run, and study records.
A campaign object, scheduler job, or study record cannot become a second SDL lifecycle.

## The one-way pipeline

```text
authored root SDL + trusted module sources
  |
  v
normalized authored scenario family
  |  resolve imports, trust, locks, namespaces, digests
  v
semantically admitted expanded scenario family
  |  bind experiment task/spec, factors, allocation, selection/RNG profiles
  v
closed experiment design
  |  compile logical coordinates and selections; check family + apparatus
  v
admitted trial plan
  |  apply one recorded selection through public SDL instantiation
  v
admitted instantiated scenario + canonical snapshot
  |  compile and plan using existing processor/planner boundaries
  v
typed provisioning/orchestration/evaluation plans
  |  fill only declared late-bound sinks; realize through selected backend
  v
operation receipts, status, runtime snapshots, evidence
  |  seal one archival run per started trial; aggregate in study/allocation
  v
experiment run/study provenance
```

Every arrow is a partial function.
A failed transition emits bounded diagnostics.
It emits no artifact for the next phase.
Runtime observations, scheduler state, and backend refusal have no path back into experiment selection.

## Authority and phase matrix

| Plane | Named authority | Input artifact | Immutable output artifact | Admission and identity rule | Provenance carried forward |
| --- | --- | --- | --- | --- | --- |
| 1. Module composition | `raes.composition` and `module_registry` | Normalized root SDL, locked imports, trust policy, verified module bytes | Expanded scenario family | Resolve the full declaration graph before selection. Preserve qualified canonical symbols. Selected values never change module or declaration identity. | Carry import preorder and namespace. Carry requested and resolved source identities and versions. Include content, manifest, and export digests. Retain signer attribution and bindings. |
| 2. Scenario-family declaration | SDL models and `SemanticValidator` | Normalized/composed family with a keyed map of variation points | Semantically admitted expanded scenario family | Each point has a stable, qualified ID. Its kind is closed. Its domain is bounded. Its target is typed. Its alternatives are locally valid. The family does not set experiment allocation. | Carry the family semantic digest. Include point, domain, and profile versions. Retain source locations and expansion evidence. |
| 3. Experiment design | `experiment-authoring-input-v1` and experiment-core validators | Task/family refs, factors, allocation, selection policies, stochastic controls, apparatus intent | Closed experiment spec | Policies target existing point IDs. Factors and conditions remain experiment concepts. Refs and digests pin the family and task. Descriptive legacy randomization fields cannot execute by convention. | Carry spec identity and digest. Include task and family refs. Include factor and condition IDs. Retain policy/control IDs and versions, and the randomness namespace. Include requested apparatus and capture refs. |
| 4. Trial-set compilation and admission | `raes_processor` using neutral DTOs from `raes_contracts` | Admitted experiment spec, exact family/task bytes, apparatus manifests/accepted envelopes, compiler/identity/RNG profiles | One canonical admitted trial plan | Use a pure, deterministic function of admitted inputs. Preallocate one archival `run_id` per logical coordinate. Emit no plan if any selected entry is invalid, impossible, duplicate, or unrealizable. | Carry all input refs and digests. Include profiles, coordinates, run IDs, selections, and factor assignments. Retain stochastic controls and stream addresses. Include apparatus bindings and bounded admission evidence. |
| 5. SDL instantiation | Public `raes` selection/instantiation/admission APIs, orchestrated by `raes_processor` | One plan entry and the exact expanded family it pins | Admitted `InstantiatedScenario` and canonical snapshot | Apply only recorded selections and bindings. Make no new draw, import, query, or fallback. Use no private binder. Rerun semantic validation of the whole scenario. | Carry existing expansion and instantiation evidence. Add point selections and trial-plan/run linkage. |
| 6. Runtime fact binding | `raes_runtime` over compiled slots and neutral fact DTOs | Admitted compiled plans, authorized observations and secret references | Run-local bound operation/action input and binding event evidence | Fill only a declared sink. Match its type, source, scope, freshness, and sensitivity. Never mutate the plan, snapshot, factors, topology, choices, run ID, or streams. | Carry the slot ID and safe fact/source ref. Include scope, freshness, and sensitivity. Retain authorization/evidence refs and the binding outcome. Include no raw secret. |
| 7. Backend realization | Existing planner, manifest, realization-envelope, and backend protocols | Admitted plans plus selected apparatus/envelope/manifests | Existing backend plans, operation receipts/status, runtime snapshots, and realized-form disclosures | Realize only within the selected envelope and capabilities. Backend refusal is a failure or deviation. It never permits resampling. | Carry manifest, envelope, and configuration refs and digests. Include realized forms, transformations, and omissions. Retain operation IDs and receipts. |
| 8. Trial orchestration, execution, and scheduling | `raes_processor` and `raes_runtime` own orchestration and execution. External schedulers, including APTL for SCE-006, own placement, isolation, timeouts, and cleanup only. | Admitted plan entries and execution/isolation policy | Existing execution receipts/state; external queue/placement state and dispatch decisions, outside scenario identity | RAE uses the existing single-scenario lifecycle. External scheduling may order, delay, pause, and retry transport. It may use bounded parallelism after isolation proof. It cannot select, instantiate, randomize, compare, or score. | Carry dispatch order. Include instance, lock, and storage allocation. Retain timeouts, clean-state/cleanup evidence, and the retry reason. |
| 9. Archival provenance | `ExperimentRunModel`, `ExperimentStudyModel`, evidence and cross-artifact validators | Sealed execution/evidence plus plan/snapshot refs | One run per started trial and study/allocation records | The preallocated plan-entry `run_id` becomes the archival `run_id`. A genuine re-execution receives a new admitted ID. Live state is not the run record. | Carry actual parameters and stochastic and apparatus facts. Include the scenario snapshot and realized forms. Retain evidence and deviations. Include lineage to the plan, spec, task, and source run where applicable. |

### Why the admitted plan is a separate artifact

The experiment spec states the intended design.
The admitted plan describes a concrete finite set of trial entries.
Each entry has been selected and validated.
Each has been shown realizable against pinned apparatus claims.
A scheduler queue states where and when work may run.
A run states what happened.
Combining any two would give mutable operational state authority over scientific intent or archival truth.

The plan is immutable and content-addressed.
Operational state refers to it.
Operational state never edits it.

## Scenario-family variation model

### Placement and identity

The SDL authoring model gains one optional `variation_points` registry.
It is a keyed map.
The registry takes part in module composition and namespace rewriting under ADR-053.
Each key is the point's local ID.
It agrees with any repeated ID field, as the existing keyed-object convention requires.
Imported points receive the module namespace, as other declarations do.

A point id identifies the semantic location of variation. It does not include:

- a selected value or alternative;
- a source filename or line number;
- a module cache path;
- a trial, worker, process, or backend id; or
- a hash of any selected value.

The scenario family semantic digest covers the declared point, domain, alternatives, and constraints.
A change to any of these changes that digest.
Selecting a member does not rename the point or any declaration.

### Closed point kinds

The first version admits the following semantic kinds:

| Kind | Meaning | Required bound | Selection result |
| --- | --- | --- | --- |
| Parameter | Select a JSON scalar for an existing typed SDL variable. | Use an exact, finite enum, boolean, or bounded numeric domain. It must match the variable. | Use the existing root or module-local parameter binding. |
| Governed reference | Select one declared reference under a named authority and revision/digest. | Use a finite set of allowed references. | Bind the typed reference. Resolve its referent through the owning registry. |
| Alternative | Select exactly one labeled typed fragment for one model-declared structural slot. | Use finite keyed alternatives. The set must not be empty. | Record the selected alternative ID and its typed content. |
| Subset | Select labeled typed members for one model-declared collection slot. | Use finite members and minimum/maximum cardinality. Typed requires/excludes are optional. | The selected member set has canonical keys. Semantic list order is separate. |
| Order | Choose a total order of declared semantic item IDs. | Use a finite item set with a precedence DAG. Fixed positions are optional. | Use an ordered tuple of item IDs. It must satisfy every edge. |
| Logical timing | Select a logical duration, offset, cadence, window, or declared timing profile. | Use exact/enum/bounded numeric values or a governed timing profile. State the unit/time domain explicitly. | Use a concrete logical timing value/profile. This is never host wall time. |

The SCE-002 examples use these semantics without special cases.
Attack-order variation uses an `order` point.
Target selection uses a bounded `subset` or `governed-reference` point, based on target ownership.
Timing variation uses a `logical-timing` point.
The experiment chooses among these authored possibilities.
The SDL declaration, runtime, backend, and scheduler do not draw on their own.

These kinds form a closed discriminated union.
A future kind requires a versioned contract extension.
It also requires a semantic validator, provenance form, and property tests.
An unknown kind fails closed.

### Typed targets, not document patches

Every point names a target descriptor owned by an SDL model.
The descriptor states the target kind, owning declaration, and slot.
It also states the expected value or fragment type.
It is not an RFC 6901 pointer, JSONPath expression, or YAML path.
It is not a template, callback, or arbitrary field name.

The owning model decides which slots are variable. A structural alternative is
a typed child accepted by that slot's ordinary validator.
A subset member is a typed keyed child.
An order point addresses stable IDs in an explicitly order-sensitive collection.
The model that owns the semantics thus keeps target authorization.

For node and runtime inventory targets, see the
[issue #1625 preflight](../../decisions/issue-1625-structural-variation-preflight.md).
It covers deployment ownership, stable IDs, write conflicts and shared checks.
For declaration presence and resource consumer targets, see the
[issue #1733 preflight](../../decisions/issue-1733-dependent-declaration-variation-preflight.md).
The supported slots are defined in `specs/sdl/variation-points.md`.

Implementations reuse or extract ADR-070's `DomainDescriptor` primitives when their value semantics fit.
These cover exact, enum, boolean, bounded-number, governed-reference, and acyclic-record values.
Experiment selection does not reuse `RealizationEnvelopeModel`, `EnvelopeBinding`, or `WitnessPolicy`.
It does not reuse backend posture or witness generation.
ADR-070 is accepted and owns only the realizability relation.
Its witness seed is not experiment randomness.

The reusable domain algebra belongs in a dependency-neutral `raes_contracts` leaf.
That leaf imports neither SDL models nor schema-bundle machinery.
Realization envelopes and scenario family declarations consume the same closed domain types and membership helpers.
They may also re-export them.
They must not copy the discriminated union or fork its validation.
An SDL variation model must not depend on `RealizationEnvelopeModel`.
Those choices would create competing schemas and an SDL/contracts import cycle.

Variation declarations use the existing SDL phase and admission spine.
They are authoring or expanded declarations.
They take part in the parser's mapping scopes and declaration index.
They also use the composition symbol table and namespace rewriting.
The canonical family digest, language tools, and published authoring schema include them.
They are absent from `InstantiatedScenario`.

Selection evidence extends the existing `InstantiationProvenance`.
It does not create a parallel provenance record, resolver, or binder.
It creates no parallel semantic validator or SDL exception hierarchy.
An explicit governed-reference or late-bound target kind authorizes credential selection.
The runtime secret-name classifier remains advisory under ADR-057.
It does not replace that typed boundary.

Until the recorded-selection integration lands, public instantiation must reject a non-empty variation registry.
It must not silently discard the registry.
Absent or empty registries retain the existing singleton-family behavior.

### Structural validity and combination constraints

Authoring validation checks every alternative and member in its typed local context.
It checks all target and reference IDs.
It also checks cardinality bounds, timing units, and precedence edges.
Cross-point restrictions use only closed relations:

- selection A requires one of a finite set of selections at point B;
- selection A excludes a finite set of selections at point B;
- subset cardinality constraints; and
- order precedence/fixed-position constraints.

There is no general Boolean expression language or arithmetic predicate.
There is no external query or executable callback.
Cycles or contradictions that make a declared domain empty are authoring errors.
Local validity does not prove every cross-product combination valid.
The trial compiler validates each whole selected scenario.
If a requested coordinate selects an invalid combination, the entire requested admitted plan fails.

### Order and time are semantic only when declared

An `order` or `logical-timing` point changes scenario meaning only at its typed target.
Worker launch order and queue latency are apparatus or scheduler facts.
So are backend provisioning duration, retry backoff, batch placement, and host time.
These facts cannot satisfy or alter an SDL variation point.

## Experiment selection and allocation

SDL declares what values and structures are valid. The experiment spec
declares which valid points form the study.

Every executable selection policy has a stable ID and closed kind.
It declares a purpose: controlled factor, nuisance variation, or fixed configuration, as admitted by its kind.
It has one qualified variation-point target, or named policy dimensions for a Cartesian product.
Its output bound is positive and finite.
That bound is checked against the run allocation.

The policy includes factor/condition mappings where selections are experimental treatments.
When allocation is stratified, the policy has exact balance semantics.
When it makes random choices, it has a stochastic profile reference.

The current authoring contract admits fixed selection and exhaustive enumeration.
It admits Cartesian product and equal stratification.
It also admits bounded uniform sampling with replacement.
Deterministic policies need no stochastic control.
Uniform sampling resolves exactly one executable sampling/randomization control.
It uses the accepted profile's bounded-integer transform.
Weighted choice, sampling without replacement, permutation, and t-way coverage fail closed until exact versioned transforms are accepted.
Neither a free-form seed nor a library default supplies those semantics.

Scenario validity domains and experiment selection policies stay separate.
They never form one object.
Many experiments can reuse a domain.
Two experiments can select different subsets without changing the scenario family digest.

Secret selections cannot be factor levels or condition assignments.
Neither can hidden answers, benchmark-only truth, or raw credentials.
A scenario may declare a secret late-binding slot or governed secret-reference policy.
The experiment plan carries no secret value.
It carries no secret-derived identity.

IP addresses, other address-like inputs, and typed paths use existing SDL `Variable` binding.
Their declared allowed-value constraints still apply.
Credential-shaped inputs use parameters only as governed secret references or declared late-bound secret-reference sinks.
They never use public credential values.
IP, credential, and path variation thus share one selection spine.
The secret boundary remains in force.

Exercise variety comes from admitting multiple explicit selections over the
same stable family. Randomness alone does not show that an exercise prevents rote memorization.
A study must state its coverage or sampling claim.
The study must preserve the selected conditions and outcomes needed to test that claim.

## Random-stream and reproducibility contract

### Profile contents

A random seed is data, not a complete algorithm. Every executable stochastic
policy references an accepted random-stream profile that fixes:

1. generator algorithm and version;
2. seed type, size, and canonical byte encoding;
3. canonical semantic-address encoding;
4. key/stream derivation function and domain-separation labels;
5. raw-bit interpretation;
6. bounded-integer, real, weighted-choice, permutation, subset, and distribution
   transformation versions used by the policy;
7. rejection, tie, precision, and exhaustion behavior; and
8. the compatibility promise for the complete profile.

Changing any element creates a new profile id. An existing profile's output is
immutable. A library default, package version range, `random.seed()` call, or
free-text algorithm name is not a profile.

The experiment's stochastic control combines the profile with a canonical root seed.
It also includes an explicit, stable randomness namespace.
The namespace does not derive from the experiment-spec ID, revision, or content digest.
Keeping the namespace and seed across a controlled revision requests common random numbers at unchanged semantic addresses.
An independent randomization mints a new namespace or changes the seed.
Copying an experiment mints a new namespace by default.
Deliberate reuse is recorded as provenance.

### Semantic addresses

For each draw purpose, the compiler derives a stream address from immutable
semantic coordinates:

```text
StreamAddress = (
  randomness_namespace,
  logical_trial_coordinate,
  selection_policy_id,
  variation_point_id,
  draw_purpose,
  local_draw_coordinate
)
```

`local_draw_coordinate` is a stable semantic member ID or explicit draw index.
It is not “the next call.”
Canonical maps are traversed by canonical identifier.
Lists retain their declared or selected order when that order is part of SDL meaning.

Worker, process, thread, and host IDs are forbidden inputs.
So are wall time, queue position, batch number, and completion order.
Map or hash iteration order, retry count, and backend availability are also forbidden.
The aggregate experiment-spec identity and digest are forbidden inputs too.
The compiler may evaluate addresses in any order or in parallel.
The plan still pins the exact experiment ID and digest as provenance.

### Non-interference and permutation operations

Each concern receives its own derived stream.
Adding a draw to policy A cannot change policy B or another point.
Adding a trial coordinate under the same namespace cannot change draw outcomes at existing coordinates.
It cannot change their selection bindings either.
The plan digest and run IDs allocated in advance may still change.
This occurs when the run-identity profile commits to a revised experiment spec.

Random order and subset operations use stable member-addressed priorities with canonical-ID tie breaking.
They may instead use another profile-defined, schedule-independent transform.
They are not a shared in-place shuffle.
Their result does not depend on prior draws or collection iteration order.

### Required reproducibility witnesses

An implementation cannot claim conformance until the same admitted inputs
produce plans with the same bytes under:

- one worker and many workers;
- forward and reversed worker assignment;
- different batch partitions and completion orders;
- retries before plan sealing;
- different process hash seeds;
- serialization/deserialization between phases; and
- repeated execution in separate processes on supported platforms.

It must also prove stream non-interference.
The witness adds an unrelated point or draw, or changes unrelated experiment metadata.
It retains the namespace.
Draws and selections must remain unchanged at every unaffected address.

These properties establish deterministic plan construction. They do not prove
the same runtime behavior or exact replay of hidden backend state.

## Trial identity and admitted plan semantics

### Stable coordinates and run ids

Allocation first creates a set of unique logical coordinates.
A coordinate is a closed tuple.
The allocation profile names its dimensions.
Examples are condition ID, block ID, replicate index, and explicit execution ordinal.
The profile sets the tuple's canonical form.
The tuple is not a list position.

The run-identity profile deterministically derives a `run_id` from:

- the admitted experiment-spec identity;
- the pinned task and scenario family identities;
- the logical coordinate;
- the trial-compiler and identity-profile ids; and
- any plan-wide input whose change makes this a different execution intent.

Recompiling the same admitted inputs yields the same run IDs.
An idempotent transport retry before execution reuses them.
A genuine re-execution after a trial starts is new scientific intent.
It uses a new explicit execution ordinal or replicate coordinate.
It is admitted again and receives a new run ID.
It may cite the source run through existing lineage.

### Plan admission is atomic

Let `F` be the admitted expanded family.
Let `E` be the admitted experiment spec.
Let `A` be the pinned apparatus claims.
Let `P` be the compiler/identity/random profiles.
Conceptually:

```text
compile_and_admit(F, E, A, P) -> AdmittedTrialPlan | DiagnosticSet
```

The same canonical inputs yield the same bytes or the same ordered diagnostics.
The function stages entries internally.
It validates every entry.
It checks plan-wide uniqueness and budgets.
It seals one plan only after all entries pass.
It never drops failed coordinates to emit a “valid subset.”

The plan has its own content identity.
That identity is not a run ID.
The plan groups the immutable intended executions.
Each entry has a run ID allocated in advance.
That is the entry's archival identity if it starts.

### Minimum plan contents

The admitted plan records:

- plan schema/profile and canonical digest;
- compiler, coordinate, run-identity, canonicalization, and random-stream
  profile ids;
- exact refs and digests for experiment spec, task, expanded scenario family,
  capture specs, and required associated artifacts;
- selected apparatus intent plus pinned manifest, capability, realization
  envelope, and material-configuration refs/digests;
- explicit cardinality and compilation-budget facts;
- a canonically ordered/keyed collection of entries;
- each entry's logical coordinate and run id allocated in advance;
- factor, condition, block, cohort, and replicate assignments;
- every structural selection and non-secret scalar/reference binding;
- stochastic control, namespace, root-seed, profile, policy, semantic-address,
  and selected-outcome provenance;
- selection-to-instantiation provenance expectations;
- safe admission decisions and diagnostic counts; and
- any disclosed limitation on reproducibility, comparability, or realized-form
  freedom.

The plan contains no queue state, worker assignment, or mutable status.
It contains no live snapshots, backend-private objects, or raw evidence.
It contains no secret values, environment dumps, or result summaries.

### Mixed-composition admission

An entry has one closed realization binding.
Legacy entries retain the exact single-realizer apparatus binding and `trial-compiler-v1` identity bytes.
A composition-bound entry instead names one digest-pinned `mixed-participant-composition-profile-v1` input.
It uses the governed `trial-compiler-mixed-composition-v1` identity domain.
Every canonical trial coordinate has exactly one explicit assignment.
Apparatus availability, scheduler placement, retry state, map order, and ambient configuration cannot select or replace it.

Before sealing, the compiler recomputes the provenance-free selected-scenario snapshot for that coordinate.
It resolves the profile through the existing trusted composition context.
Admission checks exact component manifests and envelopes.
It checks provider-local API-407 feature support and allocation effect coverage.
It also checks authority and policy joins, clocks and mappings, and evidence.
The checks cover bounded nested profiles and cleanup/isolation resources for all phases.

One failed coordinate or component rejects the complete plan.
The profile remains the sole owner of its finite phase schedule.
The batch scheduler still schedules whole trial entries only.

A linked alternative realization carries one exact, already-sealed source plan/entry/run tuple.
The source must bind the same authoring input, task, scenario family, and admitted selected snapshot.
The target receives new plan, entry, run, and digest identities.
The compiler never fetches or walks an unbounded lineage graph.

### Failure taxonomy

At minimum, implementations distinguish:

- family/point/target invalid;
- policy target or factor unbound;
- domain empty or constraint unsatisfiable;
- allocation cardinality/budget exceeded;
- unsupported or malformed compiler/RNG/identity profile;
- duplicate logical coordinate or derived run id;
- selected whole scenario semantically invalid;
- selected point outside its family domain;
- selected apparatus or envelope unavailable/incompatible;
- selection not a member of the selected backend envelope;
- required artifact/digest/trust evidence missing; and
- canonicalization or sealing failure.

Diagnostics identify the safe stage, code, canonical ids/paths, profile, and counts.
They do not render selected/supplied values or allowed domains.
They do not render secret or fact refs, raw documents, backend objects, or tracebacks.

## Explicit SDL instantiation

Trial realization is processor orchestration over public SDL APIs. For one plan
entry it:

1. verifies that the family digest and plan/entry identities match;
2. applies the recorded structural selection to model-declared targets;
3. supplies the recorded scalar bindings to the existing variable mechanism;
4. constructs no authoring identity from a selected value;
5. performs no random draw, import resolution, external query, secret read, or
   backend callback;
6. creates the closed instantiated representation;
7. admits it with the ordinary whole scenario semantic validator; and
8. emits the existing canonical instantiated snapshot.

Selection may use a private transient selected-expanded value internally.
That value is not an exchange contract or compiler input.
It cannot bypass `instantiate_scenario()` / `admit_instantiated_scenario()`.

The owning implementation issue extends `InstantiationProvenance` to carry the plan ID, run ID, and canonical selection records.
It retains the authored digest, bindings, imports, and capability constraints.
It also retains explicitness and realization designations.
The instantiated snapshot digest thus commits to the selected scenario and its derivation evidence.

## Runtime fact binding

Runtime fact binding is deliberately narrower than pre-run parameterization.
A compiled late-bound slot declares a stable slot ID and compiled owning address.
It states the accepted scalar/reference type.
It names the allowed fact source kinds and scopes.
It states the required sensitivity class and disclosure behavior.

The slot declares its freshness/expiry rule.
It states whether absence blocks, fails, or leaves an operation inapplicable.
It also names the exact run-local operation/action field that may receive the value.

A fact or secret-reference carrier declares its source, type, and scope.
It declares observation time/freshness, sensitivity, and authorization context.
It may include evidence references.
Binding succeeds only when all slot constraints hold.

Facts may specialize a run-local operation input.
Examples are a discovered host, session, credential handle, or tool result.
They cannot:

- add/remove/rename topology or declarations;
- choose an SDL alternative, subset, order, or timing point;
- alter factors, condition assignment, logical coordinate, run id, plan id, or
  snapshot identity;
- advance or replace a random stream;
- select another backend or apparatus; or
- retroactively rewrite an experiment or archival record.

Raw credentials and secret values are resolved only at the authorized sink.
The portable plan and binding evidence record slot/source identities and redaction/loss disclosures.
They record no secret material.
Missing, stale, wrong-scope, wrong-type, or unauthorized facts produce an explicit runtime disposition.
No fallback value or scenario resampling is permitted.

### Executable fact-binding surface

The reference implementation exposes this boundary through the closed
`runtime-fact-binding-plane-v1` contract and
`raes_runtime.runtime_fact_bindings.RuntimeFactBindingPlane`.

- `RuntimeFactDeclarationModel` fixes portable type and source before values arrive.
  It also fixes sensitivity, visibility, and authority semantics.
- `RuntimeFactVersionModel` is append-only and run-scoped. Version ids cannot be
  replaced and per-fact sequence numbers are contiguous.
- `RuntimeFactSinkModel` targets only an `input.*` field on a compiled
  `participant.action-contract.*` address. It records allowed sources, scopes,
  sensitivities, freshness, authority, audience, and absence behavior.
- `RuntimeFactBindingAdmission` supplies compiled sinks, candidate facts, authority references, and request time.
  These come from trusted control-plane state for one exact action instance.
  The caller-facing request cannot supply or replace those decisions.
- `bind_action_inputs()` resolves one visible current candidate per admitted sink as of the trusted admission time.
  Later observations cannot flow backward into an earlier action.
  It records a value-free binding event tied to the action instance and fact version.
  The event is also tied to evidence and provenance.
  Its result never returns action values.
- Participant and workflow projections are explicit visibility-filtered views.
  Secret-backed projections contain neither the secret reference nor its value.
  Protected secret resolution and sink-type validation occur synchronously inside the injected trusted dispatcher.
  That dispatcher sends values directly to the action adapter.
  It returns no unwrap-capable carrier.

Binding is deny-first.
Unadmitted requests return no fact metadata.
Candidates outside the scope are filtered before absence or ambiguity is reported.
Missing, stale, and ambiguous outcomes are distinct.
So are unauthorized, unsupported, wrong-type, wrong-scope, unavailable-secret, and dispatch-failed outcomes.
A missing fact also honors the compiled sink's `block`, `fail`, or `inapplicable` action disposition.

An action instance may already have binding history.
It then cannot be rebound under the same run, participant, and episode identity.

The published conformance corpus under
`contracts/fixtures/participant-runtime/runtime-fact-binding-plane-v1/`
covers positive, failure, secret, cross-participant, and cross-backend portable cases.
Aggregate validation also checks events and projections against the referenced immutable version.
They must reproduce its sensitivity and scope where applicable.
They must also reproduce its evidence, provenance, value/redaction posture, and compiled sink policy.

## Realization and scheduling

### Realization is proof against a selected envelope

The processor first proves membership in the scenario family domain.
It then checks the selected instance or requested family against the selected backend realization envelope and manifest capabilities.
These are different proofs.

Open or constrained realization choices still follow accepted ADR-070 envelope semantics.
Existing manifest and realized-form disclosures still apply.
An experiment may require comparability across runs.
It may then tighten apparatus intent or make the realized form a recorded factor.
A backend default is never an experiment selection.

A pinned backend or envelope may become unavailable or refuse a previously admitted point.
Execution then records failure or deviation.
It does not silently substitute a backend, clamp a value, or omit a member.
It does not ask the randomizer for another trial.

### Scheduler authority is intentionally small

A scheduler consumes sealed entries and may:

- choose dispatch order without changing logical order;
- delay, pause, resume, or cancel under policy;
- apply a transport retry with the same idempotency key before execution;
- allocate an isolated range instance, ports, storage, and control-plane locks;
- enforce bounded timeouts and cleanup; and
- select bounded parallelism only when SCE-006 isolation proof permits it.

A scheduler may not compose SDL or resolve imports.
It may not select variation points or call the randomizer.
It may not instantiate a different scenario, create run IDs, or decide factors.
It may not evaluate scientific results or implement a private comparison/scoring engine.
APTL and any other scheduler use this same handoff.

The portable handoff for clean-state requirements, cleanup obligations,
execution-attempt receipts, backend capability, and serial-by-default isolation
proof is specified in
{download}`cleanup-contracts.md <../../../specs/formal/scenario-variation-trial-realization/cleanup-contracts.md>`.
Those contracts describe admitted intent and evidence.
They introduce no scheduler queue or second scenario lifecycle.

## Conceptual contract sketches

The following shapes are review aids, not published schemas.
They bind ownership and relationships.
The contract implementation issues set exact field spelling and version numbers.

### SDL variation point

```yaml
variation_point:
  variation_point_id: stable-local-symbol
  kind: parameter | governed-reference | alternative | subset | order | logical-timing
  target: <closed descriptor owned by the target SDL model>
  domain: <named bounded value domain, where applicable>
  alternatives_or_members: <keyed typed children, where applicable>
  cardinality_or_precedence: <closed kind-specific constraints>
  requires: <finite typed selection relations>
  excludes: <finite typed selection relations>
```

### Experiment selection policy

```yaml
selection_policy:
  policy_id: stable-symbol
  policy_profile: versioned closed kind
  point_refs: [qualified-variation-point-id]
  expansion: explicit | enumerate | zip | product | sample | stratify | coverage
  output_bound: finite-positive-integer
  factor_bindings: <existing experiment factor/condition ids>
  stochastic_control_ref: <required only for stochastic policies>
  logical_coordinate_profile: versioned-profile
```

### Experiment stochastic control

```yaml
stochastic_control:
  control_id: stable-symbol
  randomness_namespace: stable-experiment-owned-id
  root_seed: canonical-non-secret-value
  random_stream_profile_ref: immutable-versioned-id
  namespace_reuse: explicit-provenance
```

The namespace and seed are experiment data.
The referenced profile defines how their bytes are encoded and transformed.
Neither field is inferred from a document digest, process environment, or library default.

### Random-stream profile

```yaml
random_stream_profile:
  profile_id: immutable-versioned-id
  generator: {algorithm: governed-id, version: exact-version}
  seed_encoding: exact-profile
  address_encoding: exact-profile
  stream_derivation: exact-profile
  transformations:
    bounded_integer: exact-version
    weighted_choice: exact-version
    permutation: exact-version
    subset: exact-version
  failure_semantics: exact-version
```

### Admitted plan and entry

```yaml
admitted_trial_plan:
  plan_identity: <profile + canonical digest>
  input_refs_and_digests: <experiment, task, family, artifacts>
  compiler_and_identity_profiles: <exact versions>
  stochastic_controls: <namespace + seed + exact random-stream profile>
  apparatus_bindings: <intent + pinned manifests/envelopes/configuration>
  entries:
    <logical-coordinate-key>:
      run_id: <preallocated archival run identity>
      allocation_assignments: <condition/factor/block/replicate>
      structural_selections: <point id -> selected member ids>
      parameter_bindings: <non-secret point id -> typed value/ref>
      stochastic_provenance: <policy, address, selected outcome>
      expected_instantiation_provenance: <plan/run/family linkage>
  admission: <bounded success facts and limitations>
```

### Runtime fact binding

```yaml
fact_binding_event:
  run_id: <existing run identity>
  slot_id: <compiled late-bound slot>
  fact_source_ref: <safe reference or redacted handle>
  type_scope_freshness_sensitivity: <validated metadata>
  authorization_and_evidence_refs: <safe refs>
  disposition: bound | absent | stale | unauthorized | invalid
  value: <present only on the protected run-local carrier; never duplicated>
```

### Trial realization and archival reconciliation

`raes_processor.trial_realization.realize_admitted_trial_entry` is the
schedule-independent bridge from one sealed plan entry to the existing
single scenario path.
It revalidates the complete admitted plan.
It joins the entry to its exact task, processor/backend manifests, and realization envelope.
It then calls the ordinary SDL selector and runtime compiler/planner.
Its public processor-plan projections are provisioning, orchestration, and evaluation references bound by digest.
The internal execution plan is not a portable authority.

That bridge rejects composition-bound entries before backend selection.
Mixed runtime coordination and phase transition commits belong to the separately versioned runtime coordination boundary.
So do provider handoff and live dispatch.
Admission does not silently choose a component.
It does not claim that mixed execution occurred.

The instantiated scenario carries the plan, entry, coordinate, selected members, and parameter-binding lineage.
It does not copy protected runtime fact values.
An `experiment-run-v1` may add `trial_provenance` to bind its run ID allocated in advance to that entry.
The field also binds it to the canonical instantiated-scenario digest and three processor-plan projections.
It binds it to one or more distinct execution attempts too.
Cleanup receipts remain the authority for attempt outcome and clean-state evidence.

`validate_admitted_trial_run`, `reconcile_admitted_trial_plan`, and `validate_admitted_trial_study` perform the cross-contract joins.
Plan-wide reconciliation permits unattempted entries and retries.
It rejects duplicate attempt or receipt identities.
It permits at most one archival run for an entry.
Scheduling, runtime fact evaluation, and analysis/scoring remain outside this seam.

### Adaptive-difficulty policy and intervention provenance

Declare adaptive difficulty in the experiment run plan.
Do not declare it in mutable SDL or backend configuration.
A difficulty registry names complete variants by reference.
It supplies policy-local ordering and defines fixed, adaptive, and scaffolded policies.
Its default policy must be fixed.
Each study allocation condition explicitly records the condition.
For a non-fixed condition, it also records the policy ID.

An adaptive policy names a digest-bound evaluator profile.
It declares admitted observation roles with versioned, digest-bound source definitions.
It also declares ordered threshold rules and a closed action allowlist.
It states cadence, cooldown, and intervention limits.
The policy states its guardrails and validity effect.
The reference resolver supports `adaptive-threshold-v1@1.0.0`.
It consumes one exact state cut and the exact source definition admitted by the policy.
It also consumes an evidence instance independently bound by version and digest.
It returns a sealed decision without dispatching the action.

Support matches the complete profile ID, version, and published `ADAPTIVE_THRESHOLD_PROFILE_DIGEST`.
Substituted evaluator digests, source definitions, and other profiles fail closed or remain visible unsupported outcomes.

The run archives policy decisions separately from intervention outcomes:

1. A decision records the exact cut, policy identity, and evidence references.
   It records observation source roles and cuts, the trigger, and selected action.
   It also records affected semantic references, history heads, disposition, and the declared validity effect.
2. An intervention records the outcome of an owning scaffold, inject, participant control, workflow action, or follow-up admission.
   It states whether this was attempted, realized, denied, unsupported, or failed.
   It also records occurrence/evidence references.
3. Participant delivery, participant observation, and measured downstream effect remain in their existing carriers.
   Selection alone proves none of them.

Use an in-run scaffold or action only when that carrier was already admitted for the run.
If difficulty changes the scenario family variant, create a follow-up trial through normal selection and admission.
The follow-up has a new coordinate and run ID.
It links to the source.
The source snapshot, history, factors, random streams, and identity never change.

For analysis, fixed, adaptive, and scaffolded runs are different treatments.
The run records its comparison disposition and validity disclosure.
A study with a non-fixed condition includes an analysis plan and validity notes.
This permits policy-effect comparisons.
It does not present adaptive participants as if they received the same fixed treatment.

Before admission, `validate_experiment_difficulty_against_spec()` checks the run against the canonical authoring-input digest.
It also checks the task, allocated condition, and exact policy snapshot.

The analysis plan should name the estimand and measurement or calibration basis.
It should record the assigned policy and realized path.
It should explain stopping, cooldown, and missing-intervention handling.
It should state whether follow-up runs use independent or intentionally common random streams.
These records make the analysis auditable.
They do not prove a universal difficulty scale or competence.
They do not prove causal identification, policy optimality, or training benefit.
The literature and simulation transfer is documented in
[`lineage.md`](../sdl/lineage.md#adaptive-difficulty-sequential-intervention-and-simulation-experiments).

## Compatibility and migration

### SDL documents

- A current static SDL document has no variation points.
  It denotes a singleton family.
  Its composition, instantiation, compiled meaning, and identifiers do not change.
- A current variable-only SDL document keeps the same `Variable` and substitution-token syntax.
  Its binding and default semantics stay the same.
  So do its `InstantiationProvenance` semantics.
  A future parameter variation point targets that existing variable.
  It does not add a second substitution language.
- Existing module documents retain ADR-053 resolution and namespace behavior.
  Composition completes before points are selected.
- Structural variation is opt-in and versioned.
  Consumers that lack its published schema/profile reject it cleanly.
  They do not ignore points.

### Experiment documents

- Existing `experiment-authoring-input-v1` documents remain valid authoring
  artifacts.
- Current free-text `allocation_method`, `randomization_unit`, and `replication_policy` remain declarations/provenance.
  So do stopping rules, red-variant selections, seeds, and stochastic-control descriptions.
  They do not become executable selection semantics by convention.
- To compile trials, an experiment migrates to typed selection policies and coordinate/identity profiles.
  It also migrates to accepted random-stream profiles.
  A compatibility adapter may translate a narrowly recognized legacy form only under a named migration profile.
  It must emit the typed result for review.
- Existing task, capture-spec, factor, and allocation concepts are extended at their owning boundaries.
  So are apparatus-intent, run, study, evidence, and measure concepts.
  They are not copied into a new trial family.

### Runs and studies

- `experiment-run-v1` remains the only archival record for one execution.
- `experiment-study-v1` remains the authority for factors, compared
  conditions, allocation, replication, stopping, and analysis.
- Existing run/study records need no migration merely because a producer uses an admitted plan.
  Plan-aware run records use the optional typed `trial_provenance` field.
  The cross-contract validators reconcile those runs with admitted entries and attempts.
  They also reconcile cleanup receipts and study allocation.
- Live operation state, runtime snapshots, scheduler jobs, and plan entries
  never masquerade as archival runs.

### Domain reuse

ADR-070 is accepted by this change.
Its closed value-domain primitives and membership/subsumption relation have landed.
So have its contract carriage, posture semantics, and honesty conformance.
Those neutral `raes_contracts`/SDL primitives may be reused.
`WitnessPolicy.seed` is not randomness.
Backend posture is never scenario or experiment selection.

## Consumer boundaries

| Consumer | What it may contribute | Required handoff | What it may not own |
| --- | --- | --- | --- |
| SCE-001 ATT&CK coverage | Revision-pinned technique inventory, coverage targets, environment-pack evidence | Valid authored families and/or experiment selection objectives | SDL semantics, hidden candidate execution, or a coverage claim based only on generated count |
| SCE-003 adaptive difficulty | Policy, observations, trigger, intervention, and validity disclosure | Run event/intervention provenance; a new admitted coordinate for a derived follow-up trial | Retroactive factor/topology/identity/stream mutation |
| SCE-004 goal/tool flexibility | Goal, success criteria, tool/affordance set, decision-surface policy, typed fact sinks | Ordinary SDL/participant semantics and runtime fact bindings | Hidden scenario selection through tool choice or observations |
| SCE-005 ATT&CK/CTI generation | Revision-pinned inputs, mappings, candidate rationale, confidence and gaps | Candidate SDL that passes ordinary trust, validation, and admission | Direct execution of CTI, bypass of semantic validation, or backend-directed repair |
| SCE-006/APTL scheduling | Isolation/capacity policy, placement, bounded parallelism, timeouts, cleanup | Sealed admitted entries over the existing single scenario execution path | A second lifecycle, randomizer, run-id allocator, comparison, or scoring engine |

## Requirement and follow-on trace map

### Scenario requirements

| Requirement | Relationship to this spine | Owning implementation issue(s) |
| --- | --- | --- |
| SCE-001 | Consumes revision-pinned coverage sets and admitted scenario candidates; coverage remains separate from trial validity | #783; generation support also depends on #786 and #654 |
| SCE-002 | Owns the full family/selection/plan/instantiation semantics defined here | #656, #274, #786, #787, #788, #789, #790, #791 |
| SCE-003 | Consumes baseline plan/run identity and records adaptation as intervention or a newly admitted follow-up | #784 after #790 |
| SCE-004 | Uses goal/decision semantics and typed late-bound facts without becoming a selector | #657, #791, #653 |
| SCE-005 | Produces candidate SDL from ATT&CK/CTI, then uses normal validation/admission | #660, #786, #654 |
| SCE-006 | Consumes admitted plans and proves clean-state isolation; owns no SDL/randomization semantics | #658, #788, #789, #790, #785 |

### Existing requirements

| Requirements | Preserved or extended boundary |
| --- | --- |
| DSL-101, DSL-102 | Selected values never change stable declaration ids; imported point/target refs remain qualified and unambiguous |
| DSL-103 | Module composition, namespace isolation, integrity, and locks complete before selection |
| DSL-104, DSL-115 | Scenario meaning stays backend-neutral; specificity/domain declarations remain distinct from backend realization |
| DSL-105 | One typed SDL parse/normalization path; no second template or evaluation language |
| EXP-701, EXP-702 | Tasks reference scenario families; experiment procedure remains separate from scenario meaning |
| EXP-703, EXP-720 | One started trial becomes one canonical archival run with the run id allocated in advance |
| EXP-704, EXP-721, EXP-722 | Apparatus intent, compatibility, selected envelopes/manifests, and realized forms stay explicit and distinct |
| EXP-705, EXP-706, EXP-719 | Factors, conditions, allocation, repetition, and controlled variation remain study/experiment semantics |
| EXP-710, EXP-712 | Plan, snapshot, run, evidence, and result lineage support bounded reproducibility/replay claims |
| EXP-718 | Owns accepted RNG/stream profiles, controlled randomness, and seed preservation |
| EXP-736 | The authoring input is the pre-run design consumed by trial compilation, not the admitted plan or run |
| RUN-300, RUN-301 | The existing lifecycle and explicit pre-compilation instantiation remain authoritative |
| RUN-302, RUN-303 | Typed compilation and planning consume only admitted instantiated scenarios and preserve dependency/order meaning |
| RUN-304 | Live execution state remains separate from plans and archival runs |
| RUN-309 | Reproducible participant context/history may cite the plan and streams but cannot redefine them |

### Native issue dependency sequence

The milestone uses GitHub's native blocked-by graph rather than an umbrella
issue. The design issue gates the existing/follow-on chain:

```text
#652
  -> #656 -> #786 -> #787 -> #788 -> #789 -> #790 -> #785
          |       |                                -> #784
          |       -> #654
          |
  -> #274 --------+
  -> #658 ---------------------> #788
  -> #657 -> #791 -> #653
  -> #660
  -> #783
```

The chain is contract-first.
Family declarations and executable selection/RNG policy land before batch scheduling or adaptation.
So do the plan contract, compiler/admission, and realization/run integration.

## Security, reliability, and scale

### Security gates

1. SDL input uses the existing gates.
   These cover bounded YAML/profile, duplicate keys, canonical keys, and closed models.
   They include semantic, composition, lock, digest, and signature checks.
   They also cover cycles, collisions, and path confinement.
2. Experiment and plan inputs use closed `ContractModel` shapes and published schemas.
   They use bounded parsing and the owning cross-artifact validators.
   Later remote ingress must not expose raw Pydantic/YAML errors.
3. Any API reuses strict control-plane authentication and verified identity.
   It reuses role/target authorization, request-size bounds, and idempotency fingerprints.
   It also reuses append-only audit events.
4. Secret material is neither a factor nor an identity input.
   It never appears in plan bytes, snapshots, diagnostics, or fixtures.
   It never appears in argv, logs, or telemetry.
5. Ambient environment variables cannot influence selection.
   Neither can process-global RNG state, mutable parameter stores, or backend defaults.
6. Selection/binding stays in-process over typed DTOs or bounded files/stdin.
   No raw plan, parameter/fact map, secret ref, or credential enters process argv.
   None enters shell interpolation or `shell=True`.
7. Manifest capability, compatibility, and target conformance remain mandatory backend admission gates.
   Accepted realization-envelope membership remains a mandatory gate too.
8. Errors and logs expose only safe IDs, digests, profiles, stages, counts, and durations.
   Raw documents, selected values, domains, and facts stay off secondary surfaces.
   So do evidence bodies, backend objects, environment dumps, and tracebacks.
9. Immutable plans are candidates for an artifact service.
   They are not `RuntimeSnapshot.metadata` or operation-detail blobs.
   They are not tags, audit blobs, or a mutable per-target parameter database.
10. Artifact dereference and secret resolution need separate authorization.
    Fact reads, plan reads, and execution are separately authorized too.

### Reliability and determinism

- All transforms are pure with respect to admitted inputs and explicit profiles.
- Plan sealing is atomic. Retries are idempotent.
- Duplicate coordinates/IDs and missing refs fail before dispatch.
  So do profile drift and artifact digest mismatch.
- Backend or scheduler failure never advances selection streams.
- Disclose actual realized forms, deviations, cleanup, and evidence loss.
  Do not rewrite them as intended state.

### Resource bounds and scalability

Every implementation enforces the declared budgets.
These bound source bytes, imports, variation points, and alternatives/members.
They also bound constraint edges, numeric/sample cardinality, and trial count.
Per-entry bindings, plan bytes, diagnostics, and artifact dereferences have declared budgets too.

The compiler must not materialize an unbounded or accidental Cartesian product.
It may evaluate independent logical coordinates in parallel.
It may cache pure subresults by input/profile digest.
Internal partitioning is invisible in the canonical output.
Large plans may use bounded staging or content-addressed chunks.
The portable admitted plan remains one sealed logical artifact.
Its entry order is deterministic and its admission is all-or-nothing.

## Verification contract for follow-on work

The implementation issues inherit these minimum evidence obligations:

- Supply positive and negative contract fixtures for every closed union/profile.
- Test whole scenario semantics for every point/target kind.
- Test selection membership, contradictions, and exhaustion.
- Test plan atomicity, uniqueness, budgets, and redaction of diagnostics.
- Test equal bytes for serial, parallel, reordered, batched, retried, and cross-process cases.
- Test stream non-interference. Run differential tests for map/hash order.
- Prove apparatus envelope membership/subsumption and refusal without resampling.
- Prove public SDL instantiation/admission equivalence after serialization.
- Test secret/fact authorization, type/scope/freshness, and non-retroactivity.
- Validate run/study/plan/snapshot lineage across artifacts.
- Prove scheduler conformance. Dispatch order and bounded parallelism must not change plan entries or selection provenance.

Issues #786 and #787 now provide executable family-declaration and selection-authoring coverage.
This includes published schemas and contextual family admission.
It includes positive/negative fixtures and unit tests.
Trial-coordinate compilation and selected-scenario instantiation/provenance remain assigned to their follow-on issues.
So do runtime fact binding and the property/differential witnesses above.
SCE-002 remains DRAFT until that remaining evidence lands.
