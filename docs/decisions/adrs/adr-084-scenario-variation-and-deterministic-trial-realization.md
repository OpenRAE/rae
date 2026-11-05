# ADR-084: Scenario Variation And Deterministic Trial Realization

## Status

accepted

## Date

2026-07-15

## Classification

Classification: FM2

Required artifacts: primary-source research note, complete phase/authority
design, formal invariant list, contract sketches, compatibility guidance, and
requirement/follow-on trace map.

Waivers: issue #652 is design-only and adds no schema, generated artifact,
contract model, compiler, random generator, runtime behavior, scheduler, API,
or scenario content. Executable unit, typed-contract, and
property/differential evidence is tracked by #274 and #786 through #791 and is
recorded in `specs/formal/assurance-fulfillment.yaml`.

## Context

ACES already has the parts on either side of scenario variation:

- ADR-053 and ADR-078 define trusted deterministic module composition and
  closed authored, expanded, instantiated, and snapshot phases.
- SDL `Variable` declarations and `instantiate_scenario()` provide typed scalar
  binding with portable instantiation provenance.
- ADR-055, ADR-065, ADR-068, and ADR-074 define experiment tasks, authoring
  input, factors, allocation, stochastic disclosures, archival runs, studies,
  apparatus, and provenance.
- ADR-070 defines accepted bounded realization-envelope domains and
  deterministic membership/subsumption/witness relations for backend
  feasibility.

What is missing is one normative bridge between a composed family and those
experiment/runtime artifacts. Existing experiment stochastic fields are
descriptive: they do not select a generator, stream derivation, draw
transformation, or schedule-independent trial compiler. A backend realization
envelope can state what a backend can realize, but cannot choose an experimental
treatment. A scheduler can order executions, but must not become a scenario
randomizer. Runtime observations can fill operation inputs, but must not
retroactively change trial identity or factors.

Without a single decision, follow-on work could create parallel binders, run
identities, randomizers, loaders, or persistence models in SDL, experiment,
backend, runtime, and APTL code.

The supporting
[research note](../../research/scenario-variation-trial-realization/prior-art-and-design-criteria.md)
compares typed configuration languages, simulation experiment standards,
parallel random streams, cyber playbooks/CTI/range generation, and adaptive
difficulty. The complete implementation-facing architecture is
[Scenario Variation And Deterministic Trial Realization](../../explain/reference/scenario-variation-and-trial-realization.md).

## Decision

### 1. Use one one-way lifecycle with one authority per plane

ACES adopts:

```text
authored scenario family
  -> deterministic trusted composition
  -> experiment selection and allocation
  -> deterministic trial compilation and admission
  -> explicit SDL instantiation
  -> processor planning and runtime/backend execution
  -> existing experiment run/study provenance
```

Package ownership follows ADR-036:

- `aces_sdl` owns composition, scenario-family declarations, typed targets,
  selection application, instantiation, and scenario semantic admission.
- `aces_contracts` owns portable neutral DTOs and shared bounded value-domain
  primitives.
- `aces_processor` owns trial-set compilation/admission, run-id preallocation,
  and orchestration over public SDL/planner APIs.
- `aces_runtime` owns live execution and typed fact binding into compiled
  late-bound sinks.
- existing backend protocols own realization within selected manifests and
  envelopes.
- external schedulers own placement, isolation, bounded parallelism, timeouts,
  and cleanup only.
- experiment run/study/evidence contracts remain archival authority.

Every transition is partial and fail-closed. A later plane cannot rewrite an
artifact or identity from an earlier plane.

SCE-002's campaign composition does not introduce a `Campaign` runtime root.
ADR-053 remains the composition mechanism: reusable SDL modules contribute
typed exports to one root and produce one expanded canonical `Scenario` before
selection. A campaign across multiple executions is represented by the
experiment design, admitted plan, and existing run/study records. Neither form
permits nested scenario lifecycles or concatenation of mutable runtime state.

### 2. Add named, stable, bounded SDL variation points

SDL scenario-family authoring uses an optional keyed registry of variation
points. A point's canonical id participates in module namespace rewriting and
never depends on its selected value, source path, trial, worker, or backend.

The first version is a closed union:

- scalar parameter binding through existing SDL variables;
- governed reference choice;
- exactly-one typed structural alternative;
- bounded subset of typed keyed members;
- constrained order over stable semantic item ids; and
- logical timing choice with an explicit time domain/unit.

Accordingly, attack order uses an `order` point, target selection uses a bounded
`subset` or `governed-reference` point, and scenario timing uses a
`logical-timing` point. IP and typed path inputs reuse existing SDL variables;
credential inputs carry governed secret references or declared late-bound
secret-reference sinks and never expose raw secret values as selections.

Targets are closed descriptors owned by the SDL model containing the target
slot. Arbitrary JSON/YAML paths, patches, templates, expressions, callbacks,
external queries, and author code are not admitted.

Alternatives/members are locally well-typed and independently valid. Closed
requires/excludes/cardinality/precedence relations may constrain combinations.
Every selected whole scenario is revalidated during instantiation; the compiler
emits no plan if any requested combination is invalid.

### 3. Reuse bounded value-domain primitives, not backend authority

Exact, finite-enum, boolean, bounded-numeric, governed-reference, and acyclic
record/product semantics reuse the neutral `DomainDescriptor` foundation
governed by accepted ADR-070.

Scenario-family validity, experiment selection, and backend realizability are
three separate authorities:

1. SDL states which members belong to the authored family.
2. The experiment states which members/coordinates are selected.
3. The selected backend envelope states which selected instances it can
   realize.

`RealizationEnvelopeModel`, backend posture, `WitnessPolicy`, and envelope
witness generation do not become the experiment randomizer. This change
explicitly accepts ADR-070 after its contract, relation, carriage, posture, and
honesty-conformance work landed. It clarifies, but does not broaden, the
envelope expression fragment: envelopes govern backend realizability after
experiment selection.

### 4. Make selection, allocation, and stochastic intent experiment concepts

`experiment-authoring-input-v1` remains the pre-run design artifact. Typed
selection policies reference qualified variation-point ids and explicitly
state enumeration, explicit values, zip/product, sampling, stratification,
blocking, or coverage semantics, finite output/budget, factor/condition
bindings, logical-coordinate profile, and stochastic-control reference.

Free-text allocation/randomization fields and a seed are not executable by
convention. They remain descriptive until migrated to accepted typed profiles.
SDL does not gain study factors, allocation, apparatus intent, run count, or
analysis semantics.

### 5. Require versioned semantic random streams

Every executable stochastic policy names exact versions for the generator,
seed encoding, canonical semantic-address encoding, stream/key derivation,
raw-bit interpretation, distribution/sampling transformations, and failure
behavior.

Every experiment stochastic control also declares a canonical root seed and a
stable randomness namespace. The namespace is an explicit experiment-owned
identifier, not the aggregate experiment-spec identity or digest. It remains
stable across revisions only when the author intends common random numbers for
unchanged semantic addresses; an independent randomization intentionally uses
a new namespace or seed.

Draw addresses derive only from the randomness namespace, logical trial
coordinate, policy id, variation-point id, draw purpose, and stable local draw
coordinate. They never include the aggregate experiment digest, scheduling,
worker/process/thread/host identity, wall time, completion order, retry count,
map/hash iteration order, or backend availability. The exact experiment digest
remains sealed plan/run provenance but is not a stream-address input.

Each concern receives an independent stream. Adding an unrelated draw cannot
perturb another point or trial. For identical admitted inputs, serial,
parallel, worker-reversed, differently batched, retried, cross-process, and
different hash-order compilation must produce byte-identical plans.

This ADR selects the profile boundary, not a concrete PRNG. #274 selects and
publishes accepted generator/derivation/transformation profiles.

### 6. Compile and admit one immutable trial plan atomically

`aces_processor` compiles an admitted experiment spec, exact composed family,
task, required artifacts, selected apparatus manifests/envelopes, and exact
compiler/identity/RNG profiles into one closed content-addressed admitted trial
plan.

Every entry contains a unique logical coordinate, factor/condition/replicate
assignments, structural selections, non-secret scalar/reference bindings,
stochastic control/namespace/seed/profile/address/outcome provenance, pinned
apparatus claims, and the expected selection-to-instantiation linkage.

The compiler stages and validates every requested entry before sealing the
plan. Empty/contradictory domains, budget exhaustion, duplicate coordinates or
ids, invalid selected scenarios, artifact/profile drift, or apparatus-envelope
mismatch produce deterministic bounded diagnostics and no plan. It never
clamps, substitutes, drops, falls back, or resamples a failed coordinate.

The plan is execution intent, not a scheduler queue, live operation record,
runtime snapshot, run, study, result, or evidence store.

### 7. Preallocate the existing archival run identity

Each plan entry deterministically preallocates the `run_id` that
`experiment-run-v1` will use if execution starts. The identity derives from
admitted execution intent and the logical coordinate under a versioned
identity profile.

An idempotent transport retry before execution reuses the id. A genuine
re-execution uses a new explicit replicate/execution ordinal, is admitted
again, receives a new run id, and may link to its source run. ACES does not add
`experiment-trial-v1` or a second archival trial identity.

The plan has its own content identity for the group. Plan identity, scheduler
job id, operation id, and runtime snapshot id are never run ids.

### 8. Realize entries through public SDL phase APIs

For one entry, `aces_processor` applies only its recorded structural selections
and scalar bindings to the exact family it pins, then uses the public SDL
instantiation/admission path. It performs no new draw, import, query, secret
read, backend callback, or fallback.

Instantiation provenance gains plan/run and canonical point-selection lineage
at its owning implementation issue. The canonical snapshot commits to the
selected concrete scenario and that derivation evidence. A private binder or
deserialized unchecked object cannot mint an admitted result.

### 9. Restrict runtime facts to typed late-bound sinks

Compiled late-bound slots declare a stable id, target address/type, allowed
source/scope, freshness, sensitivity, authorization/evidence expectations, and
absence behavior. Runtime facts or secret references may fill only those
run-local operation/action inputs.

Facts cannot add/remove/rename topology, choose a variation point, alter a
factor/condition, change plan/snapshot/run identity, select apparatus, or
advance/replace random streams. Missing, stale, unauthorized, wrong-type, or
wrong-scope facts produce explicit runtime dispositions, never fallback
selection.

Secret values are resolved only at authorized sinks. They are not factors,
condition assignments, seeds, stream inputs, ids/digests, plan bindings,
fixtures, diagnostics, argv, logs, or telemetry.

### 10. Keep backend realization and scheduling subordinate to admission

The selected scenario must first be a family member, then satisfy selected
manifest/capability and realization-envelope evidence. Backend-open choices
stay within the envelope and are disclosed as realized forms. Backend refusal
or availability drift is failure/deviation, not permission to pick another
trial or backend silently.

A scheduler consumes sealed entries. It may place, delay, pause, cancel, retry
transport idempotently, prove isolated bounded parallelism, enforce timeouts,
and verify clean state/cleanup. It cannot compose, select, randomize,
instantiate, allocate run ids, compare, or score. APTL uses this handoff rather
than implementing a second scenario lifecycle.

### 11. Treat adaptation and generation as governed consumers

Adaptive difficulty preserves the admitted baseline. Interventions carry
policy, observation, trigger, action, timing, and validity provenance; a
derived follow-up trial requires a new admitted coordinate/run id.

ATT&CK layers, STIX, playbooks, CTI reports, planning systems, and AI generators
may produce revision-pinned candidate SDL and mappings. Candidates re-enter the
ordinary authoring, trust, composition, semantic-validation, experiment, and
admission gates. Candidate generation is not execution authority.

## Required Boundaries

- Composition is deterministic and complete before trial selection.
- Canonical ids do not depend on selected values.
- Structural alternatives are declared, bounded, typed, and independently
  valid.
- Scenario-family domains and experiment selection policies are distinct.
- Experiment selection and backend realizability are distinct.
- Trial-plan bytes and selected values are invariant under valid scheduling and
  worker permutations.
- No failure, retry, or backend rejection consumes a shared stream or triggers
  resampling.
- Runtime facts cannot retroactively change identity, factors, topology,
  structural choices, snapshots, or streams.
- Backend choices stay within the selected realization envelope and are
  disclosed.
- One started trial is one existing archival run record.
- Schedulers consume plans without owning scenario meaning or experiment
  analysis.

## Compatibility And Migration

- Existing static SDL denotes a singleton family and remains valid.
- Existing variable-only SDL retains its substitution/binding semantics; scalar
  variation targets the existing variable mechanism.
- Existing module composition and canonical namespace behavior remain
  unchanged.
- Existing experiment authoring files remain valid. Descriptive stochastic
  fields do not execute until an explicit typed migration/profile is present.
- Existing task, run, study, apparatus, evidence, and measure contracts remain
  authoritative. Future versions add plan/selection lineage under ADR-061
  rather than weakening or duplicating those records.
- Consumers that do not support a new structural variation/profile reject it
  cleanly; they do not ignore it.

## Alternatives Considered

### Embed Jsonnet, Dhall, CUE, templates, or an expression language

Rejected. These would add another evaluator, trust model, termination/budget
surface, and diagnostic language and would allow computed unbounded structure.
ACES adopts bounded typed declarations and ordinary SDL validation instead.

### Use JSON Patch/YAML overlays for structural variants

Rejected. Path-based mutation is not semantic target authorization, can edit
identity-bearing fields, is fragile under schema evolution, and makes branch
validity difficult to review.

### Put randomization in SDL composition or instantiation

Rejected. A scenario family states validity; an experiment states selection.
Hidden draws during composition or instantiation make the selected artifact
depend on invocation context and defeat explicit provenance.

### Use one process-global or worker-local RNG

Rejected. Draw order then depends on traversal, parallelism, failures, and
retries. Semantic independently derived streams are required.

### Let the backend choose/resample a realizable point

Rejected. That makes apparatus feasibility the treatment selector and hides
selection bias. An unrealizable selected point fails admission/execution.

### Use a shared mutable parameter/fact store

Rejected. Values become time-dependent, retries observe different state,
authorization/redaction boundaries blur, and runtime discoveries can rewrite
pre-run intent. Plans are sealed; facts fill declared run-local sinks only.

### Add a trial root schema or use scheduler jobs as trials

Rejected. ADR-065/068 already establish one execution as one archival run.
Parallel roots would split identity and provenance.

### Make the trial plan itself the archival run

Rejected. A plan states admitted intent for zero or more future executions; a
run states what happened, including actual apparatus, evidence, results, and
deviations.

## Consequences

### Positive

- Follow-on SDL, experiment, processor, runtime, backend, and APTL work shares
  one lifecycle and identity model.
- Parallelism and retries cannot change the selected trial set.
- Existing composition, instantiation, run/study, apparatus, and provenance
  incumbents are extended rather than duplicated.
- Failed/unrealizable selections remain scientifically visible.
- Static and variable-only SDL remain compatible.
- Adaptive and generated scenarios enter through explicit validity/provenance
  boundaries.

### Costs

- Authors and tools must use typed point and selection profiles instead of
  arbitrary templates or free-text randomization.
- Plans carry substantial input, profile, selection, apparatus, and admission
  provenance.
- Implementations need canonicalization, budget enforcement, cross-artifact
  validation, and cross-process schedule-permutation tests.
- True re-execution requires a new explicit coordinate rather than silently
  reusing a run id.

### Risks

- Implementers may mistake ADR-070's witness seed for an RNG. The formal
  invariants and #274 profile work forbid this.
- A backend may silently substitute a realizable default. Admission and
  realized-form/deviation tests must reject or disclose it.
- “Deterministic plan” may be overstated as exact replay or backend equivalence.
  Claim boundaries remain explicit in ADR-068 and the formal specification.
- Large cross-products may exhaust resources. Every producer enforces point,
  product, trial, plan, artifact, and diagnostic budgets.
- Fact binding can leak secrets through errors or telemetry. Values remain on
  authorized run-local carriers and secondary surfaces are redacted.

## Verification And Follow-On Work

The normative invariant set is
`specs/formal/scenario-variation-trial-realization/README.md`.

Implementation is sequenced by native GitHub dependencies:

1. #656 and #786 publish bounded SDL family declarations and targets.
2. #274 and #787 publish accepted RNG/selection/allocation profiles.
3. #788 publishes the admitted trial-plan contract.
4. #789 implements deterministic compilation/admission and schedule witnesses.
5. #790 integrates public SDL instantiation and run/study provenance.
6. #791 implements typed runtime fact bindings.
7. #783, #784, #653, #654, and #785 consume the shared spine.

SCE-002 remains DRAFT until executable contract, implementation, and test
evidence is reconciled through those issues.
