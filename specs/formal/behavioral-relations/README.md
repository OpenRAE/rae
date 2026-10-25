# Behavioral-Relation Taxonomy And Claim Discipline

Classification: FM2, relation and assurance semantics.

## Scope And Authority

This specification governs the meaning of RAES claims about validation,
conformance, realization, comparison, refinement, equivalence, participant
visibility, multi-agent interaction, and empirical adequacy. It prevents a
weaker observation from being reported as a stronger behavioral result.

The machine-readable authority is
`contracts/concept-authority/behavioral-relations-v1.json`, contract
`behavioral-relations/v1`, taxonomy `raes-behavioral-relations`. Its revision
is recorded in the catalog. Relation identifiers, formal dimensions, claim-surface defaults,
bibliography coordinates, assurance status, and worked transition systems are
normative there. ADR-081, ADR-095, ADR-099, and ADR-100 govern the
architecture. This document is the normative reader-facing formalization of
that catalog.

Revision `rev6` adds
`divergence-preserving-branching-bisimulation` and the bounded
participant-crossing claim surface. Revision `rev5` added one-sided possibilistic
`participant-predicate-opacity`, mandatory revisioned relation-parameter
profiles for that relation, and independent checker, model-check, runtime,
backend-declaration, backend-realization, and backend-conformance assurance
states. Revision `rev4` added `bounded-but-for-necessity` for finite, matched,
intervention-backed counterfactual comparison. Revision `rev3` made SEM-230
`policy-noninterference` reactive over adaptive low participant strategies and
exact state cuts, and added `io-alternating-refinement` for actionable backend
participant semantics. The JSON contract remains `behavioral-relations/v1`
because the revisioned catalog identity governs the additive vocabulary.
Revision `rev7` added the closed participant-opacity profile and bounded
checker. Revision `rev8` adds exact finite-state participant-opacity
model-check evidence. Revisions `rev1` through `rev7` are historical taxonomy
identities. Consumers bind the exact taxonomy revision selected by their
profile and load its retained catalog; the crossing profiles below bind `rev8`.

The taxonomy defines claim vocabulary and proof obligations. It does not add a
model checker, theorem prover, stochastic simulator, game solver, scheduler,
or runtime engine. A relation whose definition is present but whose assurance
record is `future` or `deliberately-unproved` remains unproved.

## Core Objects

Let a labelled transition system be

```text
L = (S, A, H, ->, I)
```

where `S` is a state set, `A` is the action-label set, `H` is the set of hidden
actions, `->` is a labelled transition relation, and `I` is an initial-state
set. A relation definition MUST say when this signature is applicable. A
non-transition predicate MUST explicitly record why the signature is not
applicable rather than silently borrowing transition-system language.

An observation projection is a revisioned function

```text
pi[p, policy, revision] : concrete history -> participant-visible history
```

with an identified subject, redaction scope, order treatment, and simultaneity
treatment. Two histories are never compared “from the participant view” unless
all of those coordinates are fixed. Projection equality is not access to
hidden global state and does not imply future knowledge or strategic power.

A claim quantifies separately over states, traces, schedulers, strategies,
environments, and observations. “All” on one axis says nothing about an omitted
axis. A finite case set therefore cannot satisfy a universal quantifier merely
because every executed case passed.

## Relation Families

The following identifiers are distinct. A consumer MUST use the exact catalog
identifier rather than an artifact-local synonym.

| Relation id | Class | What it establishes |
| --- | --- | --- |
| `structural-validity` | predicate | Closed-shape and field-constraint admission under a named schema revision. |
| `semantic-validity` | predicate | Cross-reference and semantic-invariant admission under a named semantic profile. |
| `capability-declaration` | predicate | What an apparatus declares, without proving that declaration true. |
| `profile-satisfaction` | predicate | Satisfaction of every obligation in one named profile. |
| `bounded-probe-success` | predicate | Expected results for an enumerated finite case set. |
| `bounded-but-for-necessity` | empirical | A finite matched baseline/intervention pair supports a named candidate as necessary for a named outcome under one binary criterion. |
| `canonical-artifact-identity` | predicate | Equality of canonical bytes or digest under one canonicalization profile. |
| `realization-envelope-membership` | set relation | A request lies inside one backend realization envelope. |
| `realization-envelope-subsumption` | set relation | Every request admitted by one envelope is admitted by another. |
| `trace-inclusion` | behavioral | Every projected trace on the left is admitted on the right. |
| `trace-equivalence` | behavioral | Mutual projected trace inclusion. |
| `forward-simulation` | behavioral | Each left step is matched by the right under a state relation. |
| `backward-simulation` | behavioral | The reverse directional simulation obligation. |
| `data-refinement` | behavioral | Concrete operations preserve an abstract data-type relation and observations. |
| `strong-bisimulation` | behavioral | Every labelled step is matched in both directions without hiding actions. |
| `weak-bisimulation` | behavioral | Both directions match visible steps while admitting governed hidden-action closure. |
| `divergence-preserving-branching-bisimulation` | behavioral | Both directions preserve visible branching points through finite governed tau closure and preserve explicit infinite tau behavior. |
| `participant-projected-history-equivalence` | behavioral | Two histories are equal after the same named participant projection. |
| `policy-noninterference` | behavioral | Unauthorized high variation preserves participant-visible history support sets for every adaptive low strategy under fixed memory, low-equivalence, exact-cut policy, declassification, scheduler/environment, and order assumptions. |
| `io-alternating-refinement` | behavioral | A concrete backend preserves abstract participant inputs/outputs, ownership, and declared availability obligations against quantified environment choices. |
| `epistemic-indistinguishability` | epistemic | Two worlds are indistinguishable to a named participant under an information model. |
| `participant-predicate-opacity` | epistemic | Every actual point satisfying one selected predicate has a nonsecret alternative in the named observer's information cell under one revisioned profile. |
| `alternating-strategic-equivalence` | strategic | Named coalitions preserve abilities against quantified opponent choices. |
| `probabilistic-bisimulation` | behavioral | Related states assign equal probability mass to related equivalence classes. |
| `statistical-similarity` | empirical | A declared sample-level similarity result under a named metric and uncertainty procedure. |
| `statistical-equivalence` | empirical | A declared equivalence-test result inside a predeclared margin. |
| `empirical-adequacy` | empirical | Evidence satisfies a preregistered adequacy criterion for a bounded population and purpose. |

None of these rows is an implication ladder. For example:

- `canonical-artifact-identity` does not establish execution equality;
- `bounded-probe-success` does not establish `trace-inclusion`;
- `trace-equivalence` does not preserve branching structure and does not
  establish `strong-bisimulation`;
- `participant-projected-history-equivalence` does not establish
  `policy-noninterference`, `epistemic-indistinguishability`, or
  `alternating-strategic-equivalence`;
- finite leakage cases or equal sampled projections do not establish
  `policy-noninterference`;
- one equal projected-history pair does not establish
  `participant-predicate-opacity`, and opacity of one predicate does not
  establish `policy-noninterference`;
- `statistical-equivalence` does not establish any behavioral equivalence;
- `profile-satisfaction` does not establish `empirical-adequacy`.

## Required Formal Dimensions

Every relation entry MUST state all of the following, even when a dimension is
outside scope:

1. left and right carrier types and initial-state treatment;
2. labels, transition relation, observable actions, hidden actions, and
   stuttering treatment;
3. observation-projection applicability and revision;
4. direction and quantification over states, traces, schedulers, strategies,
   environments, and observations;
5. treatment of nondeterminism, concurrency, probability, time, and partial
   order;
6. the preserved property and the proof obligation;
7. evidence that may support the relation and explicit nonclaims;
8. definition, checker, implementation, bounded-test, model-check, proof,
   runtime-enforcement, backend-declaration, backend-realization, and
   backend-conformance assurance states; and
9. revision-pinned primary-source references.

Missing dimensions are not defaults. They are an incomplete claim.

## Claim Binding

A consumer claim is a `BehavioralClaimBindingModel`. It MUST carry:

```text
(taxonomy_id, taxonomy_revision, relation_id,
 subject, left_carrier_ref?, right_carrier_ref?,
 observation_projection_ref?, observation_projection_revision?,
 relation_parameter_profile_ref?, relation_parameter_profile_revision?,
 quantifier_scope, evidence_scope, evidence_boundary,
 assurance_axis?, assurance_status, evidence_refs[], limitations[],
 explicit_non_claims[])
```

The relation meaning remains in the catalog; the binding identifies the actual
subject and evidence. Projection coordinates are mandatory for a relation whose
catalog entry has `projection_required: true`. Universal scopes
`all-admitted-inputs`, `all-traces`, and `all-strategies` require model-check or
proof evidence. A finite or statistical record cannot carry one of those
universal scopes. A relation that declares
`relation_parameter_profile_required: true` requires the paired revisioned
profile coordinates and one explicit assurance axis.

Assurance axes are independent:

| Axis | Question |
| --- | --- |
| definition | Is the relation defined precisely? |
| checker | Does RAES implement a deciding or falsifying checker? |
| bounded test | What named finite cases exercise it? |
| model check | Was a pinned finite model exhaustively explored within declared bounds? |
| proof | Is a universal obligation independently proved? |
| runtime enforcement | Does the reference runtime mediate every declared observation channel? |
| backend declaration | Does a backend declare support with contracts and limitations? |
| backend realization | Is the named feature natively realized with provenance? |
| backend conformance | Did the named realization pass bounded adversarial cases? |

Positive bindings use axis-native assurance statuses. Definition is `defined`,
checker is `implemented`, bounded test is `tested`, model check is
`model-checked`, proof is `proved`, runtime enforcement is `enforced`, backend
declaration is `declared`, backend realization is `realized`, and backend
conformance is `conformant`. Their evidence scope must match the axis:
structural for definition/declaration, finite for bounded tests, the
same-named model-check/proof scopes, structural or finite for
checker/runtime/realization, and finite or statistical for backend
conformance. Future axes and deliberately unproved proof axes are structural
records, not positive results.

The legacy implementation aggregate must agree with explicit checker,
runtime-enforcement, and backend-realization states. The legacy proof aggregate
must agree with model checking; positive backend conformance requires a
realized or partially realized backend; and a future definition cannot carry a
positive assurance result. Catalog and claim validators reject contradictory
combinations.

“Defined” is not “implemented”, “implemented” is not “tested”, and “tested” is
not “proved”. The report truth value or study result remains separate from the
assurance status of the mechanism producing it.

## Claim Surfaces

### SDL transformations

Parse, normalize, expand, instantiate, and canonicalize stages currently carry
`structural-validity`, `semantic-validity`, and
`canonical-artifact-identity` evidence. Their evidence boundary consists of
typed phase functions, invariants, finite round-trip/canonicalization tests, and
property tests. They do not establish `data-refinement`, simulation,
`trace-equivalence`, or bisimulation.

### Backend realization

Envelope admission establishes `realization-envelope-membership`. The intended
universal soundness obligation is projection-bound `trace-inclusion`.
Actionable participant interaction also requires declared input/output
ownership and action-availability obligations, represented by
`io-alternating-refinement`; trace inclusion alone permits refusal of required
inputs. Both remain deliberately unproved in revision `rev6`. Current
conformance reports establish only `bounded-probe-success` for named fixture
and target-probe cases. Provisioning success, snapshots, witnesses, and
negative probes do not establish reverse inclusion, equivalence, simulation,
alternating refinement, or bisimulation.

### Backend comparison

A backend comparison MAY report bounded invariant equality,
`canonical-artifact-identity`, `bounded-probe-success`, or a declared empirical
relation. It MUST name the compared population, metrics, case set, environment,
and uncertainty method. Shared results, digests, or finite traces are not a
universal same-behavior result.

### Participant-visible behavior

A comparison of two participant histories uses
`participant-projected-history-equivalence` only when both histories use the
same named participant and projection-policy revision. Its evidence boundary is
the compared histories, redaction policy, order policy, simultaneity policy,
and run context. A single projected history is a record, not an equivalence
comparison.

### Participant information-flow policy

The SEM-230 claim surface uses `policy-noninterference` only when participant,
episode and memory scope, audience, exact-cut policy-decision sequence,
low-equivalence relation, adaptive low-strategy class, dynamic purge, permitted
declassification schedule, scheduler/environment classes, order model, and
observation projection are fixed. The baseline is
termination- and progress-insensitive, untimed, and set-based under
nondeterminism. Partial-order claims compare the declared visible order
relation, not one linearization. Probability measures are outside the baseline.

The executable SEM-230 cases are bounded falsification evidence. They do not
establish the universal hyperproperty, runtime enforcement, backend
realization, projected trace equivalence, simulation, refinement, bisimulation,
or epistemic indistinguishability.

### Participant predicate opacity

The SEM-231 claim surface uses `participant-predicate-opacity` only with a
revisioned relation-parameter profile. The profile fixes the observer or
coalition, selected predicate, possible-point and cut scope, complete
observation and delivery projection, retained memory, allowed adaptive
strategies, supervisor visibility, exact-cut policy and release behavior,
scheduler/environment, concurrency, partial order, time/progress, and
probability treatment.

The baseline is one-sided, possibilistic, untimed, and progress-insensitive.
It requires a nonsecret alternative in every actual secret information cell.
Supervisor approvals, denials, omissions, timing, delivery, action
availability, and changed external behavior are observations whenever the
profile exposes them.

Under matching profiles, `policy-noninterference` implies opacity for every
eligible predicate. Opacity of one predicate does not imply noninterference.
One equal projected-history pair may witness one alternative but does not
discharge the opacity quantifier. Revision `rev5` introduced and bounded-tests
this relation. Revision `rev7` adds a closed baseline profile and a
deterministic in-process checker for exact declared finite carriers. Revision
`rev8` adds a distinct explicit-state checker and one exact finite-model
result. The relation remains mathematically unproved and supplies no runtime
enforcement, backend declaration, realization, or conformance.

### Participant-crossing bisimulation

The SEM-232 design surface uses
`divergence-preserving-branching-bisimulation` only with a revisioned closed
relation-parameter profile. The profile binds independently derived left and
right LTS sources and digests, initial states, a complete quantified carrier,
the participant/audience projection, the exact visible and tau partitions,
deadlock, termination, divergence, order and model dimensions, a witness
family, assurance axis, tool and result provenance, limitations, and
nonclaims.

The first target is
`participant-crossing-dpbb-finite-v1@rev2`: the complete finite abstract
SEM-230 crossing operation versus the independently formalized API-423/RUN-319
crossing kernel. Only validation, exact-cut resolution, effective-capability
resolution, record preparation, and atomic commit are hidden. Redacted
occurrences, decisions, transformations, declassification, delivery,
observation, replay rejection, policy-cut advance, deadlock, termination, and
divergence remain visible or explicit.

The [executable rev2 authority](../participant-semantics/participant-crossing-models.md)
covers one fresh operation and retries. The separate
[#1395 multi-operation authority](../participant-semantics/participant-crossing-multi-operation-models.md)
defines `participant-crossing-multi-operation-dpbb-finite-v1@rev1`, with at most
two fresh identities, history-sensitive retry, cached-result observations and
bounded response loss. Neither construction establishes equivalence.

Revision `rev6` defines the relation, profile, and proof program. It does not
run the model check. A future positive finite result uses the `model-check`
assurance axis only when the carrier is the complete quantified finite domain,
both model constructions are independent, all mutations fail as expected, and
the exact pinned result is independently reproduced.

Formal equivalence does not establish live-runtime realization, backend
conformance, whole-runtime equivalence, policy noninterference, or predicate
opacity. The latter two require separate preservation theorems with matching
information-flow profiles.

### Multi-agent interaction

Current joint-action, simultaneous-move, chance, and mean-field contracts
provide structural and finite evidence only. A future strategic claim MUST use
`alternating-strategic-equivalence` and identify agents, coalitions, action
availability, opponent quantification, information sets, schedulers, objectives,
and preserved abilities. A probabilistic claim MUST use
`probabilistic-bisimulation` and supply the probability kernel and equivalence
classes. Neither relation is implemented or proved in revision `rev6`.

### Counterfactual necessity validation

The ASR-513 claim surface uses `bounded-but-for-necessity` only for one exact
candidate and outcome, one immutable baseline/intervention-world pair, one
typed and verified intervention, one revisioned binary criterion, and one
declared matching policy. A supported comparison requires baseline truth,
counterfactual falsehood, admitted per-world evidence, no undeclared semantic
difference, and independently verified reset and cleanup. Both-worlds-true
refutes the finite claim. Baseline false, unknown or unsupported truth,
unverified or collateral intervention, incomparable worlds, and residual state
cannot support it.

The comparison is finite empirical evidence. It does not establish actual,
sufficient, probabilistic, or universal causation; replay, temporal order,
correlation, shared seeds, or a failed execution are not substitutes for its
gates.

### Determinism, stability, and replay-consistency verification

The ASR-514 claim surface verifies a producer's explicit repeatability claim as
a single binary baseline-to-repetition comparison of one held-fixed subject. It
adds no relation: a determinism or replay-consistency claim over exact canonical
outputs binds the existing `canonical-artifact-identity` relation, whose two
carriers name the compared baseline and repetition artifacts, and the comparator
only decides whether the two projected outcomes are identical under one declared
observation projection, variation policy, and versioned equality criterion. A
larger set of repeated runs composes as several such pairwise cases; the binary
relation is never reinterpreted as an n-ary one. The evidence boundary is
bounded to the named pair, subject, projection, variation policy, and criterion.
A pair is admitted only when the baseline and repetition carry distinct run
identities of the same digest-held-fixed subject (ADR-068), the declared
held-fixed dimensions are held fixed with only permitted variation, and reset,
isolation, and cleanup are independently verified with no residual state.
Unequal projected outcomes refute the finite claim; indeterminate, unsupported,
withheld, incomparable, unverified, or residual evidence is inconclusive or
unsupported, never a match.

The result is finite empirical evidence for the named cohort only. It does not
establish universal determinism, statistical equivalence, trace equivalence,
bisimulation, backend equivalence, or necessity; a shared seed, a reused task
identifier, wall-clock proximity, an exit status, or a completed replay is not
substitutable for its gates. Statistical stability under controlled variation
and participant-history replay remain separate criteria bound to
`statistical-equivalence` or `participant-projected-history-equivalence`.

### Independent adequacy studies

Study and benchmark contracts bind their conclusions to
`empirical-adequacy`, `statistical-similarity`, or
`statistical-equivalence` as appropriate. The evidence boundary includes the
preregistered population, tasks, conditions, metrics or coding scheme,
uncertainty procedure, equivalence margin when applicable, falsification
criteria, missing-data handling, and limitations. Results from issue #729 will
therefore be bounded empirical evidence, not universal behavioral proof.

## Worked Counterexamples

### A passing probe is not bisimulation

Let the left system have transitions `l0 -a-> l1` and `l0 -b-> l2`. Let the
right system have only `r0 -a-> r1`. The named probe trace `[a]` passes on both
systems, so `bounded-probe-success` may hold for that case. The unmatched `b`
branch means `strong-bisimulation` does not hold. The evidence boundary is the
single `[a]` probe; it does not quantify over the untested branch.

### Hidden actions separate strong from weak matching

Let the abstract system perform `send` directly. Let the backend perform
`tau` and then `send`, where `tau` is governed as hidden. Strong matching fails
because the abstract initial state has no `tau` step. The visible trace can
still match after hidden-action closure, which is evidence relevant to
`weak-bisimulation`. A weak relation would still require the bidirectional
state-relation obligation; matching one visible trace does not prove it.

The executable versions of both examples are embedded in the revisioned
catalog and checked by `implementations/python/tests/test_behavioral_relations.py`.

### Trace inclusion is not participant-input availability

Let an abstract decision-epoch-zero state accept participant input
`select:scan`, while a concrete backend refuses every input. The concrete
projected trace set containing only the empty trace is included in the
abstract empty-trace prefix, yet the abstract input is unavailable in the
concrete state. Trace inclusion therefore cannot establish actionable
participant realization. The executable finite counterexample also checks a
hidden concrete projection step followed by `deliver:decision-epoch-0`: the
visible trace can weakly match while strong bisimulation fails. Neither finite
case proves `io-alternating-refinement`; each can falsify an incorrect
implication used in a backend claim.

## Assurance Boundary For Revision 5

Implemented and tested now:

- structural and semantic validity;
- capability declarations and profile satisfaction;
- bounded conformance probes;
- bounded binary but-for necessity comparison over admitted truth, intervention,
  matching, reset, and cleanup evidence;
- canonical artifact identity;
- realization-envelope membership and subsumption; and
- participant projection machinery and bounded projected-history comparisons;
- the SEM-230 relation definition, catalog/claim-policy validation, and bounded
  reactive-strategy counterexamples; and
- the SEM-231 opacity definition, mandatory profile and assurance-axis binding
  validation, and four finite falsification examples; and
- bounded decision-epoch-zero step-matching and participant-input-availability
  counterexamples for `io-alternating-refinement`.

Defined but deliberately unproved or only partially implemented:

- universal `trace-inclusion` and `io-alternating-refinement` for backend
  realization;
- `trace-equivalence`, forward/backward simulation, and data refinement;
- strong and weak bisimulation; and
- universal `policy-noninterference`, production policy enforcement, and
  backend realization of the SEM-230 relation; and
- any opacity checker, universal participant-predicate-opacity result,
  finite-state model check, mathematical proof, runtime enforcement, backend
  declaration, backend realization, or backend conformance.

Defined for future governed work and inappropriate to claim from current
artifacts:

- epistemic indistinguishability without a world/information model;
- alternating strategic equivalence without a game structure;
- probabilistic bisimulation without a probability kernel;
- timed or partial-order equivalence without the corresponding semantic model;
- statistical equivalence without a predeclared margin and test; and
- empirical adequacy without a preregistered population, criteria, and evidence.

## Primary Sources

The catalog records the complete title, authors, publication year and venue,
edition/version, and immutable DOI, ISBN, or primary publication URL for each
source. Revision `rev6`
uses, among others:

- Milner, *A Calculus of Communicating Systems* (1980),
  DOI `10.1007/3-540-10235-3`;
- Park, “Concurrency and Automata on Infinite Sequences” (1981),
  DOI `10.1007/BFb0017309`;
- van Glabbeek, “The Linear Time–Branching Time Spectrum” (1990),
  DOI `10.1007/BFb0039066`;
- van Glabbeek and Weijland, “Branching Time and Abstraction in Bisimulation
  Semantics” (1996), DOI `10.1145/233551.233556`;
- van Glabbeek, Luttik, and Trčka, “Branching Bisimilarity with Explicit
  Divergence” (2009), DOI `10.3233/FI-2009-109`;
- Abadi and Lamport, “The Existence of Refinement Mappings” (1991),
  DOI `10.1016/0304-3975(91)90224-P`;
- Lynch and Vaandrager, “Forward and Backward Simulations” (1995),
  DOI `10.1006/inco.1995.1134`;
- Fagin, Halpern, Moses, and Vardi, *Reasoning About Knowledge* (1995),
  ISBN `9780262061629`;
- Alur, Henzinger, Kupferman, and Vardi, “Alternating Refinement Relations”
  (1998), DOI `10.1007/BFb0055622`;
- Alur, Henzinger, and Kupferman, “Alternating-Time Temporal Logic” (2002),
  DOI `10.1145/585265.585270`;
- Larsen and Skou, “Bisimulation Through Probabilistic Testing” (1991),
  DOI `10.1016/0890-5401(91)90030-6`; and
- Wellek, *Testing Statistical Hypotheses of Equivalence and Noninferiority*,
  second edition (2010), ISBN `9781439808184`;
- Goguen and Meseguer, “Security Policies and Security Models” (1982), DOI
  `10.1109/SP.1982.10014`; and
- Sabelfeld and Sands, “Declassification: Dimensions and Principles” (2009),
  DOI `10.3233/JCS-2009-0352`.
- Lynch and Tuttle, “An Introduction to Input/Output Automata” (1989), *CWI
  Quarterly* 2(3), 219-246;
- Clarkson and Schneider, “Hyperproperties” (2010), *Journal of Computer
  Security* 18(6), 1157-1210; and
- Bohannon, Pierce, Sjöberg, Weirich, and Zdancewic, “Reactive
  Noninterference” (2009), DOI `10.1145/1653662.1653673`; and
- Halpern and Pearl, “Causes and Explanations: A Structural-Model Approach.
  Part I: Causes” (2005), DOI `10.1093/bjps/axi147`;
- Bryans, Koutny, Mazaré, and Ryan, “Opacity Generalised to Transition
  Systems” (2008), DOI `10.1007/s10207-008-0058-x`;
- Lin, “Opacity of Discrete Event Systems and its Applications” (2011), DOI
  `10.1016/j.automatica.2011.01.002`;
- Saboori and Hadjicostis, “Verification of Infinite-Step Opacity and
  Complexity Considerations” (2012), DOI `10.1109/TAC.2011.2173774`;
- Schoepe and Sabelfeld, “Understanding and Enforcing Opacity” (2015), DOI
  `10.1109/CSF.2015.41`; and
- Xie, Yin, and Li, “Opacity Enforcing Supervisory Control Using
  Nondeterministic Supervisors” (2022), DOI `10.1109/TAC.2021.3131125`.

Bibliographic prose here is an aid. The machine-readable catalog is the
revision-pinned identity surface.
