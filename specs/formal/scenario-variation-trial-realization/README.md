# Scenario Variation And Trial Realization Invariants

Status: normative design invariant set with delivered SCE-002 contract,
compiler, realization, and focused-test coverage

Classification: FM2 (semantic graph / constraint)

Requirements: SCE-002, SCE-006, SCE-007, DSL-101, DSL-103, EXP-706, EXP-718, EXP-719,
EXP-720, EXP-736, RUN-300, RUN-301

Decisions: ADR-084 and accepted ADR-070

## Scope

This specification constrains the path from a composed SDL scenario family to
an admitted trial plan, an instantiated scenario, and existing archival
experiment provenance. It fixes identity, phase ordering, selection,
random-stream, secrecy, admission, backend, scheduling, and late-binding
properties.

The formal model in this file is not itself executable. Its SCE-002 delivered
slices include the bounded SDL family and experiment-selection contracts,
admitted-trial-plan and trial-compilation contracts, deterministic compilation
and sealed-entry realization, and focused compiler/realization tests. The work
previously tracked by #274 and #788 through #791 is therefore implementation
evidence, not pending coverage. It remains distinct from backend behavioral
equivalence, availability, hidden-state reconstruction, and exact replay
claims, which this specification does not make.

## Model

Let:

- `A` be a normalized authored scenario family;
- `C(A) = F` be trusted deterministic composition yielding an admitted expanded
  family `F`;
- `V(F)` be the finite map of stable variation-point identities to bounded
  domains and typed targets;
- `E` be an admitted experiment specification that references `F`;
- `Q(E)` be the finite set of unique logical trial coordinates required by its
  allocation/selection policies;
- `N(E)` be the explicit stable randomness namespace carried by the experiment's
  stochastic control, independent of the aggregate identity/digest of `E`;
- `M(q, v)` mean selection `v` is a member of all family domains and closed
  cross-point constraints for coordinate `q`;
- `B` be the selected apparatus manifests, capability declarations, and
  accepted realization-envelope evidence;
- `R_B(F, v)` mean the selected scenario is realizable under `B`;
- `G` be the exact compiler, identity, canonicalization, and random-stream
  profiles;
- `T(F, E, B, G) = P` be trial compilation and admission;
- `P[q]` be the immutable plan entry at logical coordinate `q`;
- `I(F, P[q]) = S_q` be public SDL selection/instantiation/admission yielding
  instantiated scenario `S_q`;
- `H` be authorized runtime facts and secret references;
- `L(S_q, H)` be late binding into explicitly compiled run-local sinks; and
- `Run(P[q])` be the archival experiment run produced if execution of entry
  `q` starts.

Every named transform is partial. Undefined means failure with bounded
diagnostics and no output artifact at the next boundary.

## Phase And Authority Invariants

### SVR-001 — Composition precedes selection

For every admitted plan:

```text
T(F, E, B, G) is defined => exists A such that C(A) = F
```

No policy, random draw, backend, scheduler, or runtime fact participates in
`C`. All imports, namespaces, locks, trust checks, and digests are resolved
before any variation point is selected.

### SVR-002 — Canonical symbols are selection-independent

For every declaration or variation point `x` and valid selections `v1` and
`v2`:

```text
canonical_id(x, v1) = canonical_id(x, v2) = canonical_id(x)
```

The id contains no selected value, source/cache path, run id, worker id,
backend id, or schedule position.

### SVR-003 — One authority per plane

SDL owns family domains and typed targets; experiment contracts own selection,
factors, allocation, and stochastic intent; the processor owns trial
compilation/admission and realization orchestration; runtime owns typed
late-bound facts; backends own realization within admitted envelopes;
schedulers own placement/isolation; experiment run/study contracts own archival
provenance. No artifact from one plane may be interpreted as authority for
another.

### SVR-004 — Closed phase progression

The only supported progression is:

```text
A -> F -> E-bound design -> P -> S_q -> compiled/planned forms
  -> run-local bindings/operations -> Run(P[q])
```

An operational artifact cannot move backward and edit an earlier artifact.
Every exchange artifact is closed for its phase.

## Family And Selection Invariants

### SVR-005 — Closed, bounded variation kinds

Every point belongs to the versioned closed set:

```text
{parameter, governed-reference, alternative, subset, order, logical-timing}
```

Every point has a finite member set or explicit bounded numeric interval plus a
selection/output budget. Unknown kinds, unbounded evaluation, external queries,
callbacks, templates, and arbitrary document patches are invalid.

### SVR-006 — Typed target ownership

Every point target is a closed descriptor admitted by the SDL model that owns
the target slot. No generic path language may authorize mutation. Selected
content must pass the owning value/fragment validator.

### SVR-007 — Independent branch validity

Each declared alternative/member is well-typed and semantically valid in its
declared local context. Requires/excludes/cardinality/precedence constraints
are closed finite relations. A contradictory or empty declared domain makes
the family invalid.

### SVR-008 — Selection membership

For every plan entry:

```text
q in Q(E) and P[q].selection = v => M(q, v)
```

The compiler cannot clamp, coerce, substitute, silently omit, or select an
undeclared value.

### SVR-009 — Whole-scenario admission

Local point validity is insufficient:

```text
P[q] exists => semantic_valid(I(F, P[q]))
```

Every selected combination is admitted as a whole concrete scenario. One
invalid combination prevents the requested plan from being emitted.

### SVR-010 — Experiment selection is separate from family validity

Changing an enumeration/sampling/allocation policy without changing `F` does
not change the family identity. Reusing a family in multiple experiments does
not copy its declarations into those experiment documents.

### SVR-011 — Scenario and backend membership are ordered

For every entry:

```text
P[q] exists => M(q, P[q].selection)
               and R_B(F, P[q].selection)
```

Backend realizability is checked after family membership. Backend feasibility
cannot widen, narrow, or choose the experiment selection.

## Random-Stream Invariants

### SVR-012 — Complete stochastic profile

Every stochastic selection names exact versions for generator, seed encoding,
semantic-address encoding, stream derivation, raw-bit interpretation,
distribution/sampling transformations, and failure behavior. A seed or library
default alone is not executable stochastic control. The experiment also carries
a canonical root seed and explicit randomness namespace; both are admitted
inputs rather than values inferred from the experiment document digest.

### SVR-013 — Semantic stream address

Every draw address is a pure canonical function of:

```text
(randomness namespace N(E),
 logical trial coordinate,
 policy id,
 variation-point id,
 draw purpose,
 stable local draw coordinate)
```

It contains no aggregate experiment id/digest, worker, process, thread, host,
wall-time, queue, batch, completion-order, retry, hash-order, or
backend-availability input. The exact experiment id/digest remains plan and run
provenance. Independent randomization requires an explicit namespace or seed
change.

### SVR-014 — Schedule independence

For any two execution schedules `s1` and `s2` over identical admitted inputs:

```text
bytes(T_s1(F, E, B, G)) = bytes(T_s2(F, E, B, G))
```

This includes serial/parallel, worker permutation, batch partition, completion
order, pre-seal retry, and supported cross-process/hash-seed variation.

### SVR-015 — Stream non-interference

If input `E'` retains `N(E)` and the root seed while adding or changing a draw
or unrelated metadata outside concern `c`, then every draw and selection at
addresses in unaffected concern `c` is unchanged. No mutable global stream is
shared across points, policies, or coordinates. This does not require plan
digests or run ids to survive an experiment-spec revision.

### SVR-016 — Canonical traversal preserves semantic order

Maps are traversed by canonical id. A semantically ordered SDL collection keeps
its declared or selected order. Serialization cannot sort away meaningful
order, and runtime scheduling cannot stand in for logical order.

### SVR-017 — Failure does not consume or replace randomness

Constraint exhaustion, invalid selection, apparatus rejection, worker failure,
timeout, retry, or cancellation does not advance a shared stream or trigger
resampling. The same address always denotes the same draw under the same
profile.

## Plan And Identity Invariants

### SVR-018 — Atomic plan admission

`T` returns exactly one fully admitted plan or one deterministic diagnostic set:

```text
T(F, E, B, G) = P
  iff for every q in Q(E), P[q] is valid and realizable
```

There is no partially admitted subset formed by dropping failed coordinates.

### SVR-019 — Unique stable logical coordinates

`Q(E)` contains no duplicate canonical coordinate. Coordinate identity is
experiment meaning, never list position or scheduler order.

### SVR-020 — Preallocated archival run identity

For each `q`, `P[q].run_id` is a deterministic function of admitted execution
intent and `q`. It is unique within `P`. If execution starts:

```text
Run(P[q]).run_id = P[q].run_id
```

No `experiment-trial-v1` or second archival trial identity is introduced.

### SVR-021 — Retry and re-execution differ

An idempotent pre-execution transport retry reuses `P[q].run_id`. A genuine
re-execution uses a new explicit replicate/execution ordinal, is admitted
again, receives a distinct run id, and may cite the source run by lineage.

### SVR-022 — Plan identity is not run identity

The plan is immutable grouped execution intent and has its own canonical
content identity. Scheduler jobs, operation ids, runtime snapshots, and plan
ids cannot be used as archival run ids.

### SVR-023 — Complete plan provenance

The plan commits to exact task/family/spec/artifact refs and digests, all
compiler/identity/RNG/canonicalization profiles, logical coordinates,
selections, factor assignments, non-secret bindings, selected apparatus
claims, and bounded admission evidence.

## Executable SCE-002 v1 profiles

This section is the normative algorithm authority for the exact profile names
carried by `admitted-trial-plan-v1`. Changing any output-affecting rule below
requires a new profile name and new conformance vectors.

### `trial-coordinate-v1`

The profile admits only the three published coordinate fields and issue #789
populates only `condition_id` and `replicate_id`. For a simple
`target_run_count = n`, the coordinates are:

```text
{replicate_id: "replicate-" + six-digit-one-based-ordinal}
```

For a structured allocation, `compared_conditions` are ordered by portable
identifier code point and each condition emits the same one-based replicate
sequence through `target_runs_per_condition`. The coordinate order is
`(condition_id, numeric replicate ordinal)`. The first profile admits ordinals
1 through 999999 and never derives a block, cohort, worker, attempt, or other
dimension from descriptive allocation strings. Unsupported dimensions or an
empty/exceeded coordinate set fail before selection.

### Canonical domain and policy order in `trial-compiler-v1`

Finite scalar enumeration uses these rules:

- exact domains emit their sole value;
- booleans emit `false`, then `true`, unless fixed to one value;
- integer intervals emit every admitted integer in ascending numeric order;
- scalar enums sort the RFC 8785 bytes of
  `{"type": semantic-json-scalar-type, "value": value}`, where the type is one
  of `null`, `boolean`, `integer`, `number`, or `string`;
- governed references and structural alternative member ids sort by portable
  identifier code point; and
- a selected order outcome preserves its declared member sequence.

A fixed root broadcasts its one outcome to every coordinate. There may be at
most one non-fixed policy root. An enumerate or product root must emit exactly
the coordinate count. Product child ids sort by portable identifier and use
ordinary left-to-right Cartesian order; fixed, enumerate, and nested product
children are supported. Equal strata join by exact `condition_id` and must
match the declared per-condition counts. Sample-with-replacement uses only the
exact pair `blake3-xof-v1` and `random-stream-profile/v1`,
`sampling-selection`, local coordinate zero, the exact trial coordinate, and
the profile's `bounded-integer` transform. Multiple non-fixed roots, an
overlapping point writer, an uncovered point, orphan/ambiguous
meaning, a cardinality disagreement, unsupported product child, collision, or
bounded-draw exhaustion fails atomically. There is no implicit zip, cycle,
padding, truncation, permutation, resampling, or backend-selected value.

### Identity profiles

Every identity hashes RFC 8785 bytes of:

```json
{
  "domain": "raes-trial-compiler-identity-v1",
  "kind": "<identity kind>",
  "projection": "<profile projection>"
}
```

using SHA-256 and renders `<kind>-<64 lowercase hex digits>`.

`trial-plan` projects, in this exact field set, the complete admitted plan
profile object, input references, admitted apparatus binding, typed execution
authority, and the ordered coordinate projections. The apparatus binding
includes the accepted realization-envelope content/configuration digests,
processor/backend manifest digests, and every participant implementation
manifest identity/version/content digest used for binding admission. The
authoring-input digest inside the references binds all selection policies and
stochastic controls.
`trial-entry` and `archival-run` each project
`{"plan_id": plan_id, "coordinate": coordinate}` and are separated by their
distinct kind. `trial-cleanup` projects `plan_entry_id`, `run_id`, and the
complete typed cleanup template. Existing entry and plan seal helpers then
compute `entry_digest` and `plan_digest`; neither digest is an identity input
to itself, and `plan_id` is not `plan_digest`.

The canonical coordinate projection omits absent optional fields. Map
serialization uses JCS key order. Plan entry maps are keyed by derived entry
id, not emission position. Adding a coordinate changes plan/entry/run
identities because admitted plan-wide intent changed, but it does not change
an existing stochastic address or draw under an unchanged namespace, seed,
policy, point, and coordinate.

### Failure and resource profile

The compiler consumes explicit positive limits for coordinates, materialized
domain values, product outputs, per-entry bindings/draws, diagnostic count,
and canonical plan bytes. Coordinate, finite-domain, and Cartesian-product
cardinalities are computed and rejected against those limits before their
collections are materialized. The compiler returns either one sealed plan
with no error-severity diagnostics or one canonically ordered error set with
no plan. Issue #789 emits at most one error record, which is therefore within
every admitted positive diagnostic limit. Error records use the fixed
`trial-compiler` domain, a safe JSON-pointer address, a governed code, and
fixed text containing ids/count classes only. Raw values, complete domains,
secret or entropy references, validator payloads, host paths, environments,
and tracebacks are never rendered. Caller-supplied partition traversal drives
coordinate-local admission and entry construction. The compiler visits every
bounded coordinate and reduces coordinate-local failures by address, code,
then fixed text before returning its one diagnostic; successful keyed maps are
JCS-normalized. Therefore partition order changes execution order without
changing plan bytes or failure diagnostics.

## Instantiation, Fact, And Secret Invariants

### SVR-024 — Public SDL instantiation only

`I(F, P[q])` applies only plan-recorded selections/bindings, performs no new
draw/import/query/secret read/backend callback, uses the public SDL
instantiation and admission path, and reruns whole-scenario semantic validation.
A private binder cannot mint an admitted `S_q`.

### SVR-025 — Selection provenance is snapshot identity

`S_q` carries family, plan, run, point-selection, binding, and existing
composition/instantiation provenance. Canonical snapshot identity includes that
provenance; serialization cannot discard it.

### SVR-026 — Late binding is monotone

`L(S_q, H)` may fill only a compiled declared sink after validating source,
type, scope, freshness, sensitivity, authorization, and evidence metadata. It
does not mutate `F`, `E`, `P`, `S_q`, or their identities.

### SVR-027 — Runtime facts are not selectors

No fact or observation may choose an alternative/subset/order/timing point,
change a scalar factor, alter topology, change a logical coordinate/run id,
select apparatus, or advance a random stream. Missing/invalid facts cause an
explicit runtime disposition, not fallback selection.

### SVR-028 — Secret non-disclosure and non-identity

Raw credentials and secret values are not factors, condition assignments,
random seeds, stream-address inputs, canonical ids/digests, portable plan
bindings, diagnostics, fixtures, argv, logs, or telemetry. Secret references
are resolved only at authorized run-local sinks, and secondary provenance is
redacted.

## Backend, Scheduler, And Archive Invariants

### SVR-029 — Envelope-governed realization

Every plan entry pins selected apparatus claims. Every manifest reference
resolves to exact identity/version/digest-matched concrete processor, backend,
or participant implementation content before sealing. Capability claims
derive only from those validated manifests, each selected identity passes its
kind-specific allowlist, and each selected backend binds the accepted ADR-070
realization-envelope content and configuration digests before scenario
membership/subsumption checks. A backend may choose only a realized form
permitted by that envelope and must disclose the choice.

### SVR-030 — Backend refusal is observable failure

Availability change or refusal after admission yields failure/deviation
provenance. It cannot authorize another value, backend, omitted member, clamped
configuration, or resampled trial.

### SVR-031 — Scheduler opacity

Any two valid scheduler placements/orders for the same `P` observe identical
plan entries, run ids, selections, factors, snapshots, and streams. A scheduler
may control placement, isolation, bounded parallelism, timeouts, cancellation,
and cleanup only.

Portable cleanup intent, receipts, clean-state claims, retry safety, backend
capability, and bounded-parallelism proof (including the governed secret-scope
isolation dimension) are defined in [cleanup-contracts.md](cleanup-contracts.md).
The `batch-execution-receipt-v1` contract is the immutable per-attempt evidence
that composes those authorities: it binds the sealed plan/entry/run identities,
a distinct execution-attempt identity, the canonical dispatch ordinal and
scheduling policy, the effective concurrency, isolation-proof and live-lease
evidence refs, the primary trial disposition, control-plane operation refs, and
the cleanup-receipt ref. Serial is the effective default; bounded parallelism is
authorized only by an isolation proof joined to the exact sealed plan plus live
lease evidence. Scheduler policy, worker management, live leasing, and range
allocation remain outside these contract semantics.

### SVR-032 — Archival separation

The admitted plan is not stored as mutable runtime state, and live operation
records are not archival runs. `ExperimentRunModel` and `ExperimentStudyModel`
remain the authorities for actual execution context, evidence, factors,
allocation, deviations, and analysis lineage.

### SVR-033 — Adaptation is an intervention

Adaptive difficulty cannot rewrite the admitted baseline. An intervention is a
run event with policy/observation/trigger/action provenance. A derived follow-up
trial has a new admitted coordinate and run id linked to its source.

### SVR-034 — Generated content re-enters normal admission

ATT&CK layers, STIX, playbooks, PDDL/planners, CTI reports, and AI generators
may produce candidates only. Candidates pass ordinary authoring, trust,
composition, semantic validation, experiment binding, and trial admission.

## Executable SCE-003 v1 Profile

Adaptive difficulty is declared in the experiment run plan as a bounded
`DifficultyPolicyRegistryModel`. The registry contains named variants that
reference existing selection/scaffold/action carriers, policy-local ordered
dimensions, immutable fixed/adaptive/scaffolded policies, and one default
policy that is always fixed.

Every allocation condition has a `difficulty_condition` with fixed as its wire
default. Adaptive and scaffolded conditions also name an exact
`difficulty_policy_id`; the id resolves the registry and its condition must
match. Variant selection references resolve only existing fixed experiment
selection policies. A difficulty variant is therefore an admitted experiment
coordinate, not an unvalidated patch or runtime preset.

The supported reference evaluator is the digest-bound
`adaptive-threshold-v1@1.0.0` profile. Resolution is pure over the policy,
exact state cut, versioned and digest-bound observation-source definitions,
evidence-bearing observation-instance references, expected decision history
head, intervention count, and idempotency identity. It enforces
freshness, run/episode/order scope, threshold priority, cadence, cooldown, and
maximum interventions, then returns one sealed decision or bounded
diagnostics. Another digest-bound evaluator remains a valid declaration but
returns `unsupported`; it never falls back to the reference profile.
`ADAPTIVE_THRESHOLD_PROFILE_DIGEST` publishes the exact supported profile
digest, and resolver support matches the complete id/version/digest tuple.

Decision history is append-only. Each `DifficultyDecisionRecordModel` binds
the policy id/version/digest, request fingerprint, prior and resulting history
heads, exact cut, source-definition and evidence-instance references, trigger,
selected action, typed affected references, disposition, time, and validity
effect. The source-definition reference must exactly match the admitted
policy; a different measure cannot be submitted under the same local
`source_id`. Observation values are transient resolver inputs and are not
copied into the archival decision.

Selected effects are separate `DifficultyInterventionRecordModel` records.
The closed affected-reference kinds are scaffold, participant inject,
participant control, workflow action, and scenario variant, and each must
match its action carrier. Effect-capable records require occurrence, evidence,
or follow-up-run provenance. A scenario-variant action is only a follow-up
trial proposal: its run reference differs from the source, and ordinary
selection, plan admission, instantiation, and realization still allocate its
coordinate and identity.

`ExperimentRunModel.difficulty_provenance` archives the exact policy snapshot,
ordered decisions, intervention outcomes, and comparison disposition. Its
records belong to the archival run and fall inside its time window. Absence of
this optional field preserves legacy fixed semantics. Study condition matching
treats fixed, adaptive, and scaffolded as distinct treatments; every non-fixed
study condition requires an analysis plan and explicit validity notes.
`validate_experiment_difficulty_against_spec()` additionally binds a run to the
canonical authoring-input digest, task, allocated condition, and exact admitted
policy snapshot.

### SCE-003 validity boundary

The reference resolver establishes deterministic policy conformance, not
scientific validity. In particular:

- a policy-local variant ordering is not a universal difficulty scale;
- an exact measurement definition and evidence instance do not prove
  construct validity, calibration, or competence;
- an adaptive or scaffolded path is received treatment, not a fixed baseline;
- repeated looks, stopping/cooldown rules, missing interventions, and
  path-dependent follow-ups belong in the estimand and analysis;
- retaining random-stream coordinates across alternatives creates an
  intentional correlated/common-random-number design, while changing them
  requests independent randomization; neither is inferred from run lineage;
  and
- deterministic replay proves the declared resolver result only, not policy
  optimality, causal identification, pedagogical benefit, or backend/model
  validity.

These limits apply the primary adaptive-treatment, adaptive-testing,
curriculum-learning, and simulation-experiment sources mapped in
[`lineage.md`](../../../docs/explain/sdl/lineage.md#adaptive-difficulty-sequential-intervention-and-simulation-experiments).

## Compatibility Invariants

### SVR-035 — Static SDL is a singleton family

An existing SDL document with no variation points retains its identifiers and
meaning and denotes exactly one family member.

### SVR-036 — Existing variable binding remains authoritative

Existing `Variable` declarations and substitution semantics are reused for
scalar parameterization. Structural variation does not create a second string
template or binder. IP/address and typed path inputs use those variables under
their declared constraints. Credential-shaped inputs use governed secret
references or declared late-bound secret-reference sinks; raw credentials are
never portable selection values.

### SVR-037 — Existing experiment and archive artifacts remain distinct

Existing experiment authoring documents remain valid but descriptive
randomization text cannot execute without typed profiles. Existing task, run,
study, apparatus, evidence, and measure contracts retain their authority.

### SVR-038 — Campaign composition preserves canonical roots

An executable campaign composed from reusable SDL units is exactly one expanded
canonical `Scenario` produced by `C`; it is not a tree of independently running
scenario lifecycles. A campaign across multiple executions is represented by
an experiment design and admitted plan and is archived through the existing
run/study contracts. Neither form creates a `Campaign` runtime root or derives
meaning by concatenating mutable runtime state.

## Deterministic Failure Properties

For identical invalid inputs, diagnostic records are byte-equivalent after
canonical serialization. Diagnostics are ordered by stage, safe canonical
address/id, and code. They are bounded by explicit count/size budgets and never
render supplied values, complete domains, secret/fact refs, raw artifacts,
backend-private objects, environment data, or tracebacks.

At minimum, `T` is undefined for:

- invalid/untrusted composition or digest mismatch;
- unknown point/target/policy/profile;
- empty or contradictory domain;
- selection outside a domain or closed constraint;
- unbounded/exceeded product, trial, plan, or diagnostic budget;
- duplicate coordinate or derived run id;
- invalid selected whole scenario;
- unavailable/incompatible apparatus evidence;
- realization-envelope non-membership; and
- canonicalization or sealing failure.

## Claim Boundary

These invariants support claims of deterministic scenario-family selection,
schedule-independent admitted-plan construction, explicit instantiation
provenance, and bounded archival lineage. They do not establish behavioral
equivalence between backends, validity of an adaptive benchmark, continuing
artifact availability, truth of provenance claims, recreation of hidden
backend state, cryptographic unpredictability, or exact replay from a seed.

## Assurance Fulfillment

The invariant list is delivered by this file. Issue #786 supplies the bounded
family declaration contract and tests. Issue #787 supplies the closed
experiment selection-policy registry, exact allocation/factor joins,
family-context admission validator, canonical parser hardening, published
schema, positive/negative fixtures, and unit tests. It deliberately does not
compile logical trial coordinates or instantiate selected scenarios. Issue
#789 supplies the exact v1 profiles above, SDL-owned selected-scenario
construction/admission, deterministic plan compilation, and unit/property/
thread/process determinism evidence. #274, #788, #790, and #791 complete the
associated typed contract, trial-realization, provenance, and focused-test
surfaces. The current authoritative SCE-002 requirement is ACTIVE; the dated
allocation record in `specs/formal/assurance-fulfillment.yaml` is historical
planning context rather than a statement that these artifacts remain pending.
