# Scenario Variation And Deterministic Trial Realization

This reference defines the cohesive RAES path from an authored scenario family
to archival experiment provenance. It applies ADR-084 to the package and
artifact boundaries already established by ADR-036, ADR-053, ADR-055, ADR-065,
ADR-068, ADR-074, and ADR-078.

Issue #652 supplied this normative design. Follow-on work has since published
the SCE-002 family/selection, admitted-plan, trial-compilation, realization,
and runtime-fact contract surfaces, together with focused tests. Names in this
reference remain conceptual unless a published contract or implementation binds
them. The semantic boundaries, identities, phase order, and failure behavior
remain binding and are not left for each implementation issue to rediscover.

## Scope And Claims

The design covers:

- deterministic composition of an authored scenario family;
- named, bounded scalar and structural variation points;
- experiment-owned selection, allocation, sampling, and stochastic controls;
- schedule-independent compilation and admission of a trial set;
- explicit SDL instantiation and derivation provenance;
- typed late-bound runtime facts;
- backend realization within a selected envelope;
- scheduling as an external consumer; and
- linkage to the existing experiment run, study, apparatus, evidence, and
  lineage records.

The reference itself does not add a generator, sampler, trial compiler,
scheduler, persistence service, API, scenario pack, or adaptive policy. The
delivered follow-on slices include the typed run-local fact contract and
in-process binding plane, deterministic trial compilation, and sealed-entry
realization; remaining conceptual sketches retain their explicit
implementation boundaries.
It does not guarantee identical backend behavior, artifact availability,
reconstruction of hidden state, or exact replay from a seed alone.

## Terminology

**Scenario family**
: A composed, semantically admitted SDL authoring artifact with zero or more
  named variation points. Zero points denotes a singleton family.

**Variation point**
: A stable SDL symbol that declares one bounded location at which a concrete
  scenario may differ. The point declares the valid domain and target kind; it
  does not choose a value.

**Selection policy**
: Experiment-owned intent that enumerates or samples values from one or more
  scenario-family domains and binds them to logical trial coordinates.

**Logical trial coordinate**
: A stable, experiment-meaningful address such as condition, replicate, and
  attempt coordinate. It exists before scheduling and is not a worker or queue
  index.

**Admitted trial plan**
: A closed immutable execution-intent artifact containing only fully selected,
  valid, apparatus-realizable trial entries. It is neither a scheduler queue
  nor an archival run.

**Trial realization**
: The processor-owned operation that applies one admitted entry's structural
  selections and scalar bindings through the public SDL instantiation path.

**Runtime fact**
: An authorized observation or secret reference that fills a compiled
  late-bound sink after admission. It cannot change scenario or experiment
  meaning.

**Run**
: The existing `experiment-run-v1` archival record for one execution. “Trial”
  is experiment terminology; it does not introduce a second archival root.

### Composition and the campaign boundary

SCE-002's “atomic scenarios into larger campaigns” uses the existing ADR-053
composition model. A reusable SDL module may be authored and validated as a
bounded unit, and a root SDL document may import the typed exports of many such
units. Composition resolves trust, parameters, namespaces, references, and
collisions and then produces one expanded canonical `Scenario`. The processor
and runtime never execute a nested tree of atomic scenario lifecycles.

“Campaign” is therefore an author-facing view, not a new portable root:

- one executable composed campaign is one canonical scenario assembled from
  reusable SDL modules and fragments; and
- a campaign spanning multiple executions is an experiment design and its
  admitted trial plan, archived through the existing run/study contracts.

The second form does not compose scenario snapshots by concatenating runtime
state. It selects already composed families through experiment policies. This
preserves ADR-055's scenario/task/run/study separation and prevents a campaign
object, scheduler job, or study record from becoming a second SDL lifecycle.

## The One-Way Pipeline

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

Every arrow is a partial function. A failed transition emits bounded diagnostics
and no artifact for the next phase. There is no path from runtime observations,
scheduler state, or backend refusal back into experiment selection.

## Authority And Phase Matrix

| Plane | Named authority | Input artifact | Immutable output artifact | Admission and identity rule | Provenance carried forward |
| --- | --- | --- | --- | --- | --- |
| 1. Module composition | `raes.composition` and `module_registry` | Normalized root SDL, locked imports, trust policy, verified module bytes | Expanded scenario family | Resolve the complete declaration graph before selection; preserve qualified canonical symbols; selected values never influence module or declaration identity | Import preorder, namespace, requested and resolved source identities, versions, content/manifest/export digests, signer attribution, bindings |
| 2. Scenario-family declaration | SDL models and `SemanticValidator` | Normalized/composed family with a keyed map of variation points | Semantically admitted expanded scenario family | Every point has a stable qualified id, a closed kind, a bounded domain, a typed target, and locally valid alternatives; the family is not experiment allocation | Family semantic digest, point/domain/profile versions, source locations, expansion evidence |
| 3. Experiment design | `experiment-authoring-input-v1` and experiment-core validators | Task/family refs, factors, allocation, selection policies, stochastic controls, apparatus intent | Closed experiment specification | Policies target existing point ids; factors and conditions remain experiment concepts; refs/digests pin the family and task; descriptive legacy randomization fields cannot execute by convention | Spec identity/digest, task/family refs, factor and condition ids, policy/control ids and versions, randomness namespace, requested apparatus and capture refs |
| 4. Trial-set compilation and admission | `raes_processor` using neutral DTOs from `raes_contracts` | Admitted experiment spec, exact family/task bytes, apparatus manifests/accepted envelopes, compiler/identity/RNG profiles | One canonical admitted trial plan | Pure deterministic function of admitted inputs; preallocate one archival `run_id` per logical coordinate; emit no plan if any selected entry is invalid, impossible, duplicate, or unrealizable | All input refs/digests, profiles, coordinates, run ids, selections, factor assignments, stochastic controls and stream addresses, apparatus bindings, bounded admission evidence |
| 5. SDL instantiation | Public `raes` selection/instantiation/admission APIs, orchestrated by `raes_processor` | One plan entry and the exact expanded family it pins | Admitted `InstantiatedScenario` and canonical snapshot | Apply only recorded selections/bindings; no new draw, import, query, fallback, or private binder; rerun whole-scenario semantic validation | Existing expansion/instantiation evidence plus point selections and trial-plan/run linkage |
| 6. Runtime fact binding | `raes_runtime` over compiled slots and neutral fact DTOs | Admitted compiled plans, authorized observations and secret references | Run-local bound operation/action input and binding event evidence | Fill only a declared sink with matching type/source/scope/freshness/sensitivity; never mutate the plan, snapshot, factors, topology, choices, run id, or streams | Slot id, safe fact/source ref, scope, freshness, sensitivity, authorization/evidence refs, binding outcome; no raw secret |
| 7. Backend realization | Existing planner, manifest, realization-envelope, and backend protocols | Admitted plans plus selected apparatus/envelope/manifests | Existing backend plans, operation receipts/status, runtime snapshots, and realized-form disclosures | Realize only within the selected envelope and capabilities; backend refusal is failure/deviation, never permission to resample | Manifest/envelope/configuration refs/digests, realized forms, transformations, omissions, operation ids, receipts |
| 8. Orchestration and scheduling | External scheduler, including APTL for SCE-006 | Admitted plan entries and execution/isolation policy | Queue/placement state and dispatch decisions, outside scenario identity | May order, delay, pause, retry transport, and use bounded parallelism after isolation proof; cannot select, instantiate, randomize, compare, or score | Dispatch order, instance/lock/storage allocation, timeouts, clean-state/cleanup evidence, retry reason |
| 9. Archival provenance | `ExperimentRunModel`, `ExperimentStudyModel`, evidence and cross-artifact validators | Sealed execution/evidence plus plan/snapshot refs | One run per started trial and study/allocation records | The preallocated plan-entry `run_id` becomes the archival `run_id`; a genuine re-execution receives a new admitted id; live state is not the run record | Actual parameters/stochastic/apparatus facts, scenario snapshot, realized forms, evidence, deviations, lineage to plan/spec/task and source run where applicable |

### Why the admitted plan is a separate artifact

The experiment specification states intended design. The admitted plan states
that a concrete finite set of trial entries has been selected, validated, and
shown realizable against pinned apparatus claims. A scheduler queue states
where and when work may run. A run states what happened. Combining any two of
those would make a mutable operational concern authoritative for scientific
intent or archival truth.

The plan is therefore immutable and content-addressed. Operational state refers
to it; operational state never edits it.

## Scenario-Family Variation Model

### Placement and identity

The SDL authoring model gains one optional, keyed `variation_points` registry.
The registry participates in module composition and namespace rewriting under
ADR-053. Each key is the point's local id and agrees with any repeated id field,
following the existing keyed-object convention. Imported points receive the
module namespace exactly as other declarations do.

A point id identifies the semantic location of variation. It does not include:

- a selected value or alternative;
- a source filename or line number;
- a module cache path;
- a trial, worker, process, or backend id; or
- a hash of any selected value.

Changing the declared point, domain, alternatives, or constraints changes the
scenario-family semantic digest. Selecting a member does not rename the point
or any declaration.

### Closed point kinds

The first version admits the following semantic kinds:

| Kind | Meaning | Required bound | Selection result |
| --- | --- | --- | --- |
| Parameter | Select a JSON scalar for an existing typed SDL variable | Exact, finite enum, boolean, or bounded numeric domain compatible with the variable | Existing root or module-local parameter binding |
| Governed reference | Select one declared reference under a named authority and revision/digest | Finite allowed reference set | Typed reference binding; referent is resolved through the owning registry |
| Alternative | Select exactly one labeled typed fragment for one model-declared structural slot | Non-empty finite keyed alternatives | Selected alternative id and its typed content |
| Subset | Select a set of labeled typed members for one model-declared collection slot | Finite members plus minimum/maximum cardinality; optional typed requires/excludes | Canonically keyed selected member set; semantic list order is separate |
| Order | Choose a total order of declared semantic item ids | Finite item set plus a precedence DAG and optional fixed positions | Ordered tuple of item ids satisfying every edge |
| Logical timing | Select a logical duration, offset, cadence, window, or declared timing profile | Exact/enum/bounded numeric or governed timing profile; explicit unit/time domain | Concrete logical timing value/profile, never host wall time |

The SCE-002 examples map to these semantics without special cases: attack-order
variation is an `order` point, target selection is a bounded `subset` or
`governed-reference` point according to target ownership, and timing variation
is a `logical-timing` point. The experiment chooses among these authored
possibilities; the SDL declaration, runtime, backend, and scheduler do not draw
independently.

These kinds form a closed discriminated union. A future kind requires a versioned
contract extension, semantic validator, provenance form, and property tests. An
unknown kind fails closed.

### Typed targets, not document patches

Every point names a target descriptor owned by an SDL model. A target descriptor
states the target kind, owning declaration, slot, and expected value/fragment
type. It is not an RFC 6901 pointer, JSONPath expression, YAML path, template,
callback, or arbitrary field name.

The owning model decides which slots are variable. A structural alternative is
a typed child accepted by that slot's ordinary validator; a subset member is a
typed keyed child; an order point addresses the stable ids of an explicitly
order-sensitive collection. This keeps target authorization in the model that
owns the semantics.

When exact/enum/boolean/bounded-number/governed-reference/acyclic-record value
semantics fit, implementations reuse or extract the `DomainDescriptor`
primitives introduced with ADR-070. They do not reuse
`RealizationEnvelopeModel`, `EnvelopeBinding`, `WitnessPolicy`, backend posture,
or witness generation as experiment selection. ADR-070 is accepted and owns
only the realizability relation; its witness seed is not experiment randomness.

The reusable domain algebra belongs in a dependency-neutral `raes_contracts`
leaf that does not import SDL models or schema-bundle machinery. Realization
envelopes and scenario-family declarations consume (and may re-export) those
same closed domain types and membership helpers. They must not copy the
discriminated union, fork its validation, or make an SDL variation model depend
on `RealizationEnvelopeModel`; those choices would create competing schemas and
an SDL/contracts import cycle.

Variation declarations use the existing SDL phase and admission spine. They are
authoring/expanded declarations, participate in the existing parser mapping
scopes, declaration index, composition symbol table, namespace rewriting,
canonical family digest, language tooling, and published authoring schema, and
are absent from `InstantiatedScenario`. Selection evidence extends the existing
`InstantiationProvenance`; it does not create a parallel provenance record,
resolver, binder, semantic validator, or SDL exception hierarchy. Credential
selection is authorized by an explicit governed-reference or late-bound target
kind. The runtime secret-name classifier remains advisory under ADR-057 and is
not a substitute for that typed boundary. Until the recorded-selection
integration lands, the public instantiation path must fail closed on a
non-empty variation registry rather than silently discard it; absent or empty
registries retain the existing singleton-family behavior.

### Structural validity and combination constraints

Authoring validation checks every alternative/member in its typed local
context, all target and reference ids, cardinality bounds, timing units, and
precedence edges. Cross-point restrictions use only closed relations:

- selection A requires one of a finite set of selections at point B;
- selection A excludes a finite set of selections at point B;
- subset cardinality constraints; and
- order precedence/fixed-position constraints.

There is no general Boolean expression language, arithmetic predicate, external
query, or executable callback. Cycles or contradictions that make a declared
domain empty are authoring errors. Local validity does not prove every
cross-product combination valid; the trial compiler validates each selected
whole scenario. If any requested coordinate selects an invalid combination, the
entire requested admitted plan fails.

### Order and time are semantic only when declared

An `order` or `logical-timing` point changes scenario meaning only at its typed
target. Worker launch order, queue latency, backend provisioning duration, retry
backoff, batch placement, and host time are apparatus/scheduler facts. They
cannot satisfy or alter an SDL variation point.

## Experiment Selection And Allocation

SDL declares what values and structures are valid. The experiment specification
declares which valid points form the study.

Every executable selection policy has:

- a stable policy id and closed kind;
- a declared purpose: controlled factor, nuisance variation, or fixed
  configuration, as admitted by the policy kind;
- one qualified variation-point target, or named policy dimensions for a
  Cartesian product;
- a positive finite output bound checked against the run allocation;
- factor/condition mappings where selections are experimental treatments;
- exact balance semantics when allocation is stratified; and
- a stochastic profile reference when the policy makes random choices.

The current authoring contract admits fixed selection, exhaustive enumeration,
Cartesian product, equal stratification, and bounded uniform sampling with
replacement. Deterministic policies need no stochastic control. Uniform
sampling resolves exactly one executable sampling/randomization control and
uses the accepted profile's bounded-integer transform. Weighted choice,
sampling without replacement, permutation, and t-way coverage fail closed
until versioned exact transforms for those operations are accepted; neither a
free-form seed nor a library default supplies those semantics.

Scenario validity domains and experiment selection policies never collapse into
one object. A domain can be reused by many experiments. Two experiments can
select different subsets without changing the scenario-family digest.

Selections that are secret, hidden answers, benchmark-only truth, or raw
credentials cannot be factor levels or condition assignments. A scenario may
declare a secret late-binding slot or governed secret-reference policy, but the
experiment plan carries no secret value and no secret-derived identity.

Address-like inputs such as IP addresses and typed path inputs continue through
existing SDL `Variable` binding with their declared allowed-value constraints.
Credential-shaped inputs are parameterized only as governed secret references
or declared late-bound secret-reference sinks, never as public credential
values. Thus IP, credential, and path variation share the same selection spine
without weakening the secret boundary.

Exercise variety comes from admitting multiple explicit selections over the
same stable family. “Prevents rote memorization” is not inferred from the mere
presence of randomness: a study must state the intended coverage or sampling
claim and preserve the selected conditions and outcomes needed to evaluate it.

## Random-Stream And Reproducibility Contract

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

The experiment's stochastic control combines that profile with a canonical
root seed and an explicit stable randomness namespace. The namespace is not
derived from the experiment-spec id, revision, or content digest. Keeping the
same namespace and seed across a controlled revision requests common random
numbers at unchanged semantic addresses; an independent randomization mints a
new namespace or changes the seed. Copying an experiment mints a new namespace
by default, and deliberate reuse is recorded as provenance.

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

`local_draw_coordinate` is a stable semantic member id or explicit draw index,
not “the next call.” Canonical maps are traversed by canonical identifier.
Lists whose order is part of SDL meaning retain their declared or selected
order.

The following are forbidden inputs: worker/process/thread/host id, wall time,
queue position, batch number, completion order, map/hash iteration order,
retry count, backend availability, and aggregate experiment-spec identity or
digest. The compiler may evaluate addresses in any order or in parallel. The
plan still pins the exact experiment id/digest as provenance.

### Non-interference and permutation operations

Each concern receives its own derived stream. Adding a draw to policy A cannot
change policy B or another point. Adding a trial coordinate under the same
namespace cannot change draw outcomes or selection bindings at existing
coordinates. The plan digest and preallocated run ids may still change when the
run-identity profile commits to a revised experiment specification.

Random order and subset operations are defined from stable member-addressed
priorities (with canonical-id tie breaking), or another profile-defined
schedule-independent transform. They are not a shared in-place shuffle whose
result depends on prior draws or collection iteration order.

### Required reproducibility witnesses

An implementation cannot claim conformance until identical admitted inputs
produce byte-identical plans under:

- one worker and many workers;
- forward and reversed worker assignment;
- different batch partitions and completion orders;
- retries before plan sealing;
- different process hash seeds;
- serialization/deserialization between phases; and
- repeated execution in separate processes on supported platforms.

It must also prove stream non-interference by adding an unrelated point/draw
or changing unrelated experiment metadata while retaining the namespace, then
observing unchanged draws and selections at every unaffected address.

These properties establish deterministic plan construction. They do not prove
identical runtime behavior or exact replay of hidden backend state.

## Trial Identity And Admitted Plan Semantics

### Stable coordinates and run ids

Allocation first creates a set of unique logical coordinates. A coordinate is a
closed tuple whose dimensions are named by the allocation profile, for example
condition id, block id, replicate index, and explicit execution ordinal. The
tuple is canonicalized by profile; it is not a list position.

The run-identity profile deterministically derives a `run_id` from:

- the admitted experiment-spec identity;
- the pinned task and scenario-family identities;
- the logical coordinate;
- the trial-compiler and identity-profile ids; and
- any plan-wide input whose change makes this a different execution intent.

Recompiling the same admitted inputs yields the same run ids. An idempotent
transport retry before execution reuses them. A genuine re-execution after a
trial starts is new scientific intent: it uses a new explicit execution
ordinal or replicate coordinate, is admitted again, and receives a new run id.
It may cite the source run through existing lineage.

### Plan admission is atomic

Let `F` be the admitted expanded family, `E` the admitted experiment spec,
`A` the pinned apparatus claims, and `P` the compiler/identity/random profiles.
Conceptually:

```text
compile_and_admit(F, E, A, P) -> AdmittedTrialPlan | DiagnosticSet
```

For the same canonical inputs, the function returns identical bytes or
identical ordered diagnostics. It stages entries internally, validates every
entry, checks plan-wide uniqueness and budgets, and seals one plan only after
all entries pass. It never emits a “valid subset” after dropping failed
coordinates.

The plan has its own content identity. That identity is not a run id. It groups
the immutable intended executions, while each entry's preallocated run id is
the archival identity if that entry starts.

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
- each entry's logical coordinate and preallocated run id;
- factor, condition, block, cohort, and replicate assignments;
- every structural selection and non-secret scalar/reference binding;
- stochastic control, namespace, root-seed, profile, policy, semantic-address,
  and selected-outcome provenance;
- selection-to-instantiation provenance expectations;
- safe admission decisions and diagnostic counts; and
- any disclosed limitation on reproducibility, comparability, or realized-form
  freedom.

It does not contain queue state, worker assignment, mutable status, live
snapshots, backend-private objects, raw evidence, secret values, environment
dumps, or result summaries.

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

Diagnostics identify the safe stage, code, canonical ids/paths, profile, and
counts. They do not render selected/supplied values, allowed domains, secret or
fact refs, raw documents, backend objects, or tracebacks.

## Explicit SDL Instantiation

Trial realization is processor orchestration over public SDL APIs. For one plan
entry it:

1. verifies that the family digest and plan/entry identities match;
2. applies the recorded structural selection to model-declared targets;
3. supplies the recorded scalar bindings to the existing variable mechanism;
4. constructs no authoring identity from a selected value;
5. performs no random draw, import resolution, external query, secret read, or
   backend callback;
6. creates the closed instantiated representation;
7. admits it with the ordinary whole-scenario semantic validator; and
8. emits the existing canonical instantiated snapshot.

Selection may use a private transient selected-expanded value internally, but
that value is not an exchange contract, compiler input, or bypass around
`instantiate_scenario()` / `admit_instantiated_scenario()`.

`InstantiationProvenance` is extended by its owning implementation issue to
carry the plan id, run id, and canonical selection records in addition to the
existing authored digest, bindings, imports, capability constraints,
explicitness, and realization designations. The instantiated snapshot digest
therefore commits to the selected scenario and its derivation evidence.

## Runtime Fact Binding

Runtime fact binding is deliberately narrower than pre-run parameterization.
A compiled late-bound slot declares:

- stable slot id and compiled owning address;
- accepted scalar/reference type;
- allowed fact source kinds and scopes;
- required sensitivity class and disclosure behavior;
- freshness/expiry rule;
- whether absence blocks, fails, or leaves an operation inapplicable; and
- the exact run-local operation/action field that may receive the value.

A fact or secret-reference carrier declares source, type, scope, observation
time/freshness, sensitivity, authorization context, and optional evidence
references. Binding succeeds only when all slot constraints hold.

Facts may specialize a run-local operation input such as a discovered host,
session, credential handle, or tool result. They cannot:

- add/remove/rename topology or declarations;
- choose an SDL alternative, subset, order, or timing point;
- alter factors, condition assignment, logical coordinate, run id, plan id, or
  snapshot identity;
- advance or replace a random stream;
- select another backend or apparatus; or
- retroactively rewrite an experiment or archival record.

Raw credentials and secret values are resolved only at the authorized sink.
The portable plan and binding evidence record slot/source identities and
redaction/loss disclosures, not secret material. Missing, stale, wrong-scope,
wrong-type, or unauthorized facts produce an explicit runtime disposition; no
fallback value or scenario resampling is permitted.

### Executable fact-binding surface

The reference implementation exposes this boundary through the closed
`runtime-fact-binding-plane-v1` contract and
`raes_runtime.runtime_fact_bindings.RuntimeFactBindingPlane`.

- `RuntimeFactDeclarationModel` fixes portable type, source, sensitivity,
  visibility, and authority semantics before values arrive.
- `RuntimeFactVersionModel` is append-only and run-scoped. Version ids cannot be
  replaced and per-fact sequence numbers are contiguous.
- `RuntimeFactSinkModel` targets only an `input.*` field on a compiled
  `participant.action-contract.*` address. It records allowed sources, scopes,
  sensitivities, freshness, authority, audience, and absence behavior.
- `RuntimeFactBindingAdmission` supplies the compiled sinks, candidate facts,
  authority references, and request time from trusted control-plane state for
  one exact action instance. The caller-facing request cannot supply or replace
  those decisions.
- `bind_action_inputs()` resolves one visible current candidate per admitted
  sink as of the trusted admission time; later observations cannot flow
  backward into an earlier action. It records a value-free binding event tied
  to the action instance, fact version, evidence, and provenance. Its result
  never returns action values.
- Participant and workflow projections are explicit visibility-filtered views.
  Secret-backed projections contain neither the secret reference nor its value;
  protected secret resolution and sink-type validation occur synchronously
  inside the injected trusted dispatcher, which sends values directly to the
  action adapter without returning an unwrap-capable carrier.

Binding is deny-first. Unadmitted requests return no fact metadata, and
out-of-scope candidates are filtered before absence or ambiguity is reported.
Missing, stale, ambiguous, unauthorized, unsupported, wrong-type, wrong-scope,
unavailable-secret, and dispatch-failed outcomes are distinct. A
missing fact additionally honors the compiled sink's `block`, `fail`, or
`inapplicable` action disposition. Once an action instance has binding history,
it cannot be rebound under the same run, participant, and episode identity.

The published conformance corpus under
`contracts/fixtures/participant-runtime/runtime-fact-binding-plane-v1/`
covers positive, failure, secret, cross-participant, and cross-backend portable
cases. Aggregate validation also requires events and projections to reproduce
the referenced immutable version's sensitivity, scope where applicable,
evidence, provenance, value/redaction posture, and compiled sink policy.

## Backend Realization And Scheduling

### Realization is proof against a selected envelope

The processor first establishes membership in the scenario-family domain, then
checks the selected instance/requested family against the selected backend
realization envelope and manifest capabilities. Those are different proofs.

Open or constrained realization choices remain governed by accepted ADR-070
envelope semantics and existing manifest/realized-form disclosures. Where an
experiment requires cross-run comparability, the experiment may tighten
apparatus intent or make the realized form a recorded factor. A backend default
is never an experiment selection.

If a pinned backend/envelope becomes unavailable or refuses a previously
admitted point, execution records failure/deviation. It does not silently
substitute a backend, clamp a value, omit a member, or ask the randomizer for
another trial.

### Scheduler authority is intentionally small

A scheduler consumes sealed entries and may:

- choose dispatch order without changing logical order;
- delay, pause, resume, or cancel under policy;
- apply a transport retry with the same idempotency key before execution;
- allocate an isolated range instance, ports, storage, and control-plane locks;
- enforce bounded timeouts and cleanup; and
- select bounded parallelism only when SCE-006 isolation proof permits it.

It may not compose SDL, resolve imports, select variation points, call the
randomizer, instantiate a different scenario, create run ids, decide factors,
evaluate scientific results, or implement a private comparison/scoring engine.
APTL and any other scheduler use this same handoff.

The portable handoff for clean-state requirements, cleanup obligations,
execution-attempt receipts, backend capability, and serial-by-default isolation
proof is specified in
{download}`cleanup-contracts.md <../../../specs/formal/scenario-variation-trial-realization/cleanup-contracts.md>`.
Those contracts describe admitted intent and evidence; they do not introduce a
scheduler queue or a second scenario lifecycle.

## Conceptual Contract Sketches

The following shapes are review aids, not published schemas. They bind ownership
and relationships while leaving exact field spelling and version numbers to the
contract implementation issues.

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

The namespace and seed are experiment data. The referenced profile defines how
their bytes are encoded and transformed; neither field is inferred from a
document digest, process environment, or library default.

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
single-scenario path. It revalidates the complete admitted plan, joins the
entry to its exact task, processor/backend manifests, and realization
envelope, then calls the ordinary SDL selector and runtime compiler/planner.
Its public processor-plan projections are digest-bound as provisioning,
orchestration, and evaluation references; the internal execution plan is not
a portable authority.

The instantiated scenario carries the plan, entry, coordinate, selected
members, and parameter-binding lineage without copying protected runtime fact
values. An `experiment-run-v1` may add `trial_provenance` to bind its
preallocated run id to that entry, the canonical instantiated-scenario digest,
the three processor-plan projections, and one or more distinct execution
attempts. Cleanup receipts remain the authority for attempt outcome and
clean-state evidence.

`validate_admitted_trial_run`, `reconcile_admitted_trial_plan`, and
`validate_admitted_trial_study` perform the cross-contract joins. Plan-wide
reconciliation permits unattempted entries and retries, rejects duplicate
attempt or receipt identities, and permits at most one archival run for an
entry. Scheduling, runtime fact evaluation, and analysis/scoring remain
outside this seam.

### Adaptive-difficulty policy and intervention provenance

Declare adaptive difficulty in the experiment run plan, not in mutable SDL or
backend configuration. A difficulty registry names complete variants by
reference, supplies policy-local ordering, and defines fixed, adaptive, and
scaffolded policies. Its default policy must be fixed. Each study allocation
condition explicitly records the condition and, for a non-fixed condition, the
policy id.

An adaptive policy names a digest-bound evaluator profile, admitted observation
roles with versioned and digest-bound source definitions, ordered threshold
rules, a closed action allowlist, cadence/cooldown/intervention limits,
guardrails, and the validity effect. The reference resolver supports
`adaptive-threshold-v1@1.0.0`; it consumes one exact state cut, the exact source
definition admitted by the policy, and an independently version/digest-bound
evidence instance. It returns a sealed decision without dispatching the
action. Support matches the complete profile id, version, and published
`ADAPTIVE_THRESHOLD_PROFILE_DIGEST`; substituted evaluator digests, source
definitions, and other profiles fail closed or remain visible unsupported
outcomes.

The run archives policy decisions separately from intervention outcomes:

1. A decision records the exact cut, policy identity, evidence references,
   observation source roles and cuts, trigger, selected action, affected
   semantic references, history heads, disposition, and declared validity
   effect.
2. An intervention records whether an owning scaffold, inject, participant
   control, workflow action, or follow-up admission was attempted, realized,
   denied, unsupported, or failed, plus its occurrence/evidence references.
3. Participant delivery, participant observation, and measured downstream
   effect remain in their existing carriers; selection alone proves none of
   them.

Use an in-run scaffold or action only when that carrier was already admitted
for the run. If difficulty changes the scenario-family variant, create a
follow-up trial through normal selection and admission. The follow-up has a new
coordinate and run id and links to the source; the source snapshot, history,
factors, random streams, and identity never change.

For analysis, fixed, adaptive, and scaffolded runs are different treatments.
The run records its comparison disposition and validity disclosure, and a
study containing a non-fixed condition includes an analysis plan and validity
notes. This permits policy-effect comparisons without presenting adaptive
participants as if they received the same fixed treatment.
Before admission, `validate_experiment_difficulty_against_spec()` checks the
run against the canonical authoring-input digest, task, allocated condition,
and exact policy snapshot.

For a defensible study, the analysis plan should additionally name the
estimand; measurement/calibration basis; assigned policy and realized path;
stopping, cooldown, and missing-intervention handling; and whether follow-up
runs use independent or intentionally common random streams. These records
make the analysis auditable, but they do not prove a universal difficulty
scale, competence, causal identification, policy optimality, or training
benefit. The literature and simulation transfer is documented in
[`lineage.md`](../sdl/lineage.md#adaptive-difficulty-sequential-intervention-and-simulation-experiments).

## Compatibility And Migration

### SDL documents

- A current static SDL document has no variation points and denotes a singleton
  family. Its composition, instantiation, compiled meaning, and identifiers do
  not change.
- A current variable-only SDL document keeps the same `Variable`,
  substitution-token syntax, binding, default, and `InstantiationProvenance`
  semantics. A future parameter variation point targets that existing variable
  rather than adding a second substitution language.
- Existing module documents retain ADR-053 resolution and namespace behavior.
  Composition completes before points are selected.
- Structural variation is opt-in and versioned. Consumers that do not implement
  its published schema/profile reject it cleanly; they do not ignore points.

### Experiment documents

- Existing `experiment-authoring-input-v1` documents remain valid authoring
  artifacts.
- Current free-text `allocation_method`, `randomization_unit`,
  `replication_policy`, stopping rules, red-variant selections, seeds, and
  stochastic-control descriptions remain declarations/provenance. They do not
  become executable selection semantics by convention.
- To compile trials, an experiment migrates to typed selection policies,
  coordinate/identity profiles, and accepted random-stream profiles. A
  compatibility adapter may translate a narrowly recognized legacy form only
  under a named migration profile and must emit the typed result for review.
- Existing task, capture-spec, factor, allocation, apparatus-intent, run, study,
  evidence, and measure concepts are extended at their owning boundaries rather
  than copied into a new trial family.

### Runs and studies

- `experiment-run-v1` remains the only archival record for one execution.
- `experiment-study-v1` remains the authority for factors, compared
  conditions, allocation, replication, stopping, and analysis.
- Existing run/study records need no migration merely because a producer uses
  an admitted plan. Plan-aware run records use the optional typed
  `trial_provenance` field; the cross-contract validators reconcile those runs
  with admitted entries, attempts, cleanup receipts, and study allocation.
- Live operation state, runtime snapshots, scheduler jobs, and plan entries
  never masquerade as archival runs.

### ADR-070 and domain reuse

ADR-070 is accepted by this change after its closed value-domain primitives,
membership/subsumption relation, contract carriage, posture semantics, and
honesty conformance landed. Those neutral `raes_contracts`/SDL primitives may
be reused, but `WitnessPolicy.seed` is not randomness and backend posture is
never scenario or experiment selection.

## Consumer Boundaries

| Consumer | What it may contribute | Required handoff | What it may not own |
| --- | --- | --- | --- |
| SCE-001 ATT&CK coverage | Revision-pinned technique inventory, coverage targets, scenario-pack evidence | Valid authored families and/or experiment selection objectives | SDL semantics, hidden candidate execution, or a coverage claim based only on generated count |
| SCE-003 adaptive difficulty | Policy, observations, trigger, intervention, and validity disclosure | Run event/intervention provenance; a new admitted coordinate for a derived follow-up trial | Retroactive factor/topology/identity/stream mutation |
| SCE-004 goal/tool flexibility | Goal, success criteria, tool/affordance set, decision-surface policy, typed fact sinks | Ordinary SDL/participant semantics and runtime fact bindings | Hidden scenario selection through tool choice or observations |
| SCE-005 ATT&CK/CTI generation | Revision-pinned inputs, mappings, candidate rationale, confidence and gaps | Candidate SDL that passes ordinary trust, validation, and admission | Direct execution of CTI, bypass of semantic validation, or backend-directed repair |
| SCE-006/APTL scheduling | Isolation/capacity policy, placement, bounded parallelism, timeouts, cleanup | Sealed admitted entries over the existing single-scenario execution path | A second lifecycle, randomizer, run-id allocator, comparison, or scoring engine |

## Requirement And Follow-On Trace Map

### SCE requirements

| Requirement | Relationship to this spine | Owning implementation issue(s) |
| --- | --- | --- |
| SCE-001 | Consumes revision-pinned coverage sets and admitted scenario candidates; coverage remains separate from trial validity | #783; generation support also depends on #786 and #654 |
| SCE-002 | Owns the full family/selection/plan/instantiation semantics defined here | #656, #274, #786, #787, #788, #789, #790, #791 |
| SCE-003 | Consumes baseline plan/run identity and records adaptation as intervention or a newly admitted follow-up | #784 after #790 |
| SCE-004 | Uses goal/decision semantics and typed late-bound facts without becoming a selector | #657, #791, #653 |
| SCE-005 | Produces candidate SDL from ATT&CK/CTI, then uses normal validation/admission | #660, #786, #654 |
| SCE-006 | Consumes admitted plans and proves clean-state isolation; owns no SDL/randomization semantics | #658, #788, #789, #790, #785 |

### Existing DSL, EXP, and RUN requirements

| Requirements | Preserved or extended boundary |
| --- | --- |
| DSL-101, DSL-102 | Selected values never change stable declaration ids; imported point/target refs remain qualified and unambiguous |
| DSL-103 | Module composition, namespace isolation, integrity, and locks complete before selection |
| DSL-104, DSL-115 | Scenario meaning stays backend-neutral; specificity/domain declarations remain distinct from backend realization |
| DSL-105 | One typed SDL parse/normalization path; no second template or evaluation language |
| EXP-701, EXP-702 | Tasks reference scenario families; experiment procedure remains separate from scenario meaning |
| EXP-703, EXP-720 | One started trial becomes one canonical archival run with the preallocated run id |
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

The chain is intentionally contract-first: family declarations, executable
selection/RNG policy, plan contract, compiler/admission, and realization/run
integration land before batch scheduling or adaptation.

## Security, Reliability, And Scale

### Security gates

1. SDL input uses the existing bounded YAML/profile, duplicate-key,
   canonical-key, closed-model, semantic, composition, lock, digest, signature,
   cycle, collision, and path-confinement gates.
2. Experiment and plan inputs use closed `ContractModel` shapes, published
   schemas, bounded parsing, and owning cross-artifact validators. Later remote
   ingress must not expose raw Pydantic/YAML errors.
3. Any API reuses strict control-plane authentication, verified identity,
   role/target authorization, request-size bounds, idempotency fingerprints,
   and append-only audit events.
4. Secret material is neither a factor nor identity input and never appears in
   plan bytes, snapshots, diagnostics, fixtures, argv, logs, or telemetry.
5. Ambient environment variables, process-global RNG state, mutable parameter
   stores, and backend defaults cannot influence selection.
6. Selection/binding remains in-process over typed DTOs or bounded files/stdin;
   no raw plan, parameter/fact map, secret ref, or credential is placed in
   process argv, shell interpolation, or `shell=True`.
7. Manifest capability, compatibility, target conformance, and accepted
   realization-envelope membership remain mandatory backend admission gates.
8. Errors and logs expose only safe ids, digests, profiles, stages, counts, and
   durations. Raw documents, selected values, domains, facts, evidence bodies,
   backend objects, environment dumps, and tracebacks stay off secondary
   surfaces.
9. Immutable plans are artifact-service candidates, not
   `RuntimeSnapshot.metadata`, operation-detail blobs, tags, audit blobs, or a
   mutable per-target parameter database.
10. Artifact dereference, secret resolution, fact reads, plan reads, and
    execution are separately authorized operations.

### Reliability and determinism

- All transforms are pure with respect to admitted inputs and explicit
  profiles.
- Plan sealing is atomic; retries are idempotent.
- Duplicate coordinates/ids, missing refs, profile drift, and artifact digest
  mismatch fail before dispatch.
- Backend or scheduler failure never advances selection streams.
- Actual realized forms, deviations, cleanup, and evidence loss are disclosed
  rather than rewritten as intended state.

### Resource bounds and scalability

Every implementation enforces declared budgets for source bytes, imports,
variation points, alternatives/members, constraint edges, numeric/sample
cardinality, trial count, per-entry bindings, plan bytes, diagnostics, and
artifact dereferences.

The compiler must not materialize an unbounded or accidental Cartesian product.
It may evaluate independent logical coordinates in parallel and cache pure
subresults by input/profile digest. Internal partitioning is invisible in the
canonical output. Large plans may be constructed through bounded staging or
content-addressed chunks, but the portable admitted plan remains one sealed
logical artifact with deterministic entry ordering and all-or-nothing
admission.

## Verification Contract For Follow-On Work

The implementation issues inherit these minimum evidence obligations:

- positive and negative contract fixtures for every closed union/profile;
- whole-scenario semantic tests for every point/target kind;
- selection membership and contradiction/exhaustion tests;
- plan atomicity, uniqueness, budget, and diagnostic-redaction tests;
- serial/parallel/reordered/batched/retried/cross-process byte-equivalence
  tests;
- stream non-interference and map/hash-order differential tests;
- apparatus envelope membership/subsumption and refusal-without-resampling
  properties;
- public SDL instantiation/admission equivalence after serialization;
- secret/fact authorization, type/scope/freshness, and non-retroactivity tests;
- run/study/plan/snapshot lineage cross-artifact validation; and
- scheduler conformance proving that dispatch order and bounded parallelism do
  not change plan entries or selection provenance.

Issues #786 and #787 now provide executable family-declaration and
selection-authoring coverage: published schemas, contextual family admission,
positive/negative fixtures, and unit tests. Trial-coordinate compilation,
selected-scenario instantiation/provenance, runtime fact binding, and the
property/differential witnesses above remain assigned to their follow-on
issues. SCE-002 remains DRAFT until that remaining evidence lands.
