# Control applicability, dependency evaluation and effect decisions

Authority: SEM-235/API-424 and [ADR-111](../../../docs/decisions/adrs/adr-111-control-applicability-and-effect-decisions.md).
Semantic identity: `participant-control-applicability/rev1`. Classification: FM3.

This is the #1352 amendment to MPC-01–03 and MPC-05–11 of
[modular participant control](modular-participant-control.md). The original
`sem-235/rev1` publication remains interpretable at its historical revision.
This amendment defines semantics and contract obligations, not a new wire
schema or an installed provider protocol. Executable adoption follows the
[migration contract](../../../docs/migration/control-applicability-and-evaluation.md).
MPC-04's domains, SEM-233, visibility, fresh identity, causal bounds and the
separate admission/authority/realization boundaries remain binding.

## CA-01 — Apparatus and obligation coverage

Let B be the immutable admitted apparatus: exact profile and mechanism
instances, implementations, configurations, protocol and semantic revisions,
authorities, support requirements, state scopes and finite bounds. Let K be the
complete MPC-03 context, including B's identity, subject/crossing/sink/phase,
participant/episode, policies, input identities, expected history heads and
provider-state versions. A different sink at a different K does not change B.

Each selected required profile publishes a finite, typed obligation relation.
Its obligations are derived from the profile and admitted configuration before
looking at provider responses. Merely listing a profile or installing a
provider does not cover an obligation. For each obligation o, trusted resolution
at K produces exactly one of:

| Applicability | Required record and consequence |
| --- | --- |
| Applies | The obligation identity/revision, exact K and a complete mapping to admitted result slots and required support constraints. Missing or ambiguous coverage blocks the affected parent. |
| Proven inapplicable | The profile-owned applicability relation, exact B/K and safe evidence establishing why o does not apply. No result is required for o at this K. |
| Unresolved | An explicit unresolved record. No permission or empty-success interpretation is available. |

Coverage is a total accounting of required obligations, including those
proven inapplicable. An applicable obligation cannot have an empty discharge
set unless its published relation explicitly defines a checkable zero-result
discharge; absent data never establishes that case. The finite model uses no
such zero-result discharge. Coverage maps preserve all selecting profiles and
all conjunctions: one shared result cannot erase another owner's conditions.

The applicable invocation subset A(B,K) consists of admitted slots relevant to
this crossing plus their declared input dependencies. It refers into B; it is
not a replacement selection whose digest must equal B. Record both identities
and the derivation of A. A dependency outside its admitted input applicability
is unsatisfied, not permission to invoke elsewhere. Providers absent from A
are not failures merely because they serve a different sink. An empty A is
valid only with complete obligation accounting and satisfied incumbent gates.

No provider, no result, a resolver returning `None`, a mismatch or an exception
proves inapplicability. A new cut requires new applicability resolution. An
apparatus without modular requirements can explicitly record no modular
evaluation; this preserves all ordinary gates. An installed apparatus requiring
evaluation cannot use that disposition to hide resolution failure. A change
to B requires its own authorized admission transition, never subset filtering.

## CA-02 — Invocation and predecessor inputs

The evaluation unit is a declared **slot or finite stage of slots**, not one
unqualified call per provider. The admitted typed dependency graph is finite
and acyclic. Edges identify producer slot, result kind and revision, consumer
input and required satisfaction relation. Unknown edges, type mismatches,
duplicate identities and cycles are inadmissible. A.fact → B.assessment →
A.rule is valid when its slot graph is acyclic, even though a provider recurs.

Before invoking a stage, resolve every required predecessor and validate its
typed content, originating invocation, instance/configuration, B, K, state
version, status and evidence. The dependent invocation carries detached,
immutable predecessor results or content-bound references that resolve to
those exact results. Its output binds the invocation identity, requested slots
and complete predecessor-input identity as well as K. Sharing K alone does
not prove that the provider consumed the required result.

Only the declared disclosure-authorized projection is provided. An edge does
not authorize private provider-state access or disclosure of the whole
apparatus. Hidden shared memory, ambient result lookup and recomputing another
provider's fact are not substitutes for the declared input. Missing mandatory
input creates an explicit unsatisfied consumer result; it cannot be passed as
an empty input list and treated as a successful evaluation.

Invoke ready independent stages in any order consistent with the admitted
state/independence relation. Canonical sorting is serialization, never a winner
or causal authority. Composition consumes the recorded results, including
stochastic assessments; replay does not resample an assessment under an old
result identity. Bound stages, edges, predecessor material, result count,
bytes, attempts and external computation before invocation/iteration. Provider
construction remains operator/backend-owned; no scenario-selected code or
general workflow interpreter is introduced.

## CA-03 — Mandatory closure and optional contributions

Let R be the roots required by applicable profile obligations and mandatory
decision/rule slots. Let M be their transitive **required-input** closure in the
admitted graph. Every input in M must meet its typed satisfaction and support
relation. Admission explicitly records that closure; execution cannot silently
upgrade an optional dependency to required or drop it to preserve success.

Availability and decision authority are distinct. A mandatory fact must be a
valid fact. Required advice must be a valid assessment, even if its opinion is
negative. A mandatory decision must permit. Only an admitted decision rule
interprets advice into a parent decision. Deny/withhold cannot be supplied by
an optional advisory score itself. Mandatory abstention remains unsatisfied.

A rule evaluation records either a typed request with its trigger basis or an
explicit **not triggered** result with the evaluated basis. A resolved false
trigger discharges the evaluation obligation and creates no effect. Missing,
failed, unsupported or stale rule evaluation does not mean not triggered.

An optional contribution outside M can be absent, malformed, stale, failed or
unsupported without vetoing the parent. At its declared invocation boundary,
normalize rejection to a safe typed failure/absence record and discard its
payload, state proposal and effect requests. Preserve bounded lost-advice
evidence. Do not catch failure of the whole evaluation and relabel it optional.
Role comes from B and M, not from an untrusted result's self-description.

Optional suggestions that conflict with mandatory constraints, effects or
state are discarded with evidence; they do not block the mandatory plan.
Mutually incompatible optional suggestions are all omitted unless an admitted
deterministic rule chooses a compatible set. A rule whose requested consequence
is necessary for parent release belongs to M and requires ordinary authority.
An optional provider cannot write mandatory shared state through an undeclared
path. Invalid apparatus, forged shared context or unresolved required coverage
remains an admission failure, regardless of claimed optionality.

## CA-04 — Support is relative to the requirement

Each obligation and required input pins its required semantic coverage,
strength, admissible loss/constraints and evidence basis. Reuse API-407's
effective-support resolution and API-424's support bindings. The satisfaction
relation is evaluated at K over those dimensions; a name such as exact or
bounded, a manifest declaration or a numeric rank alone is insufficient.

Bounded support is usable when its independently resolved coverage and bounds
satisfy the already admitted requirement. For example, a published requirement
allowing an evidenced error bound of at most two units can accept a compatible
one-unit realization, while an exact requirement cannot. This example defines
no universal loss unit or strength ordering. Unknown, incomparable or
insufficient evidence leaves the obligation unsatisfied.

An authority to downgrade does not prove satisfaction. A different requirement
or weaker profile needs an explicit, separately identified effective binding,
authorization and disclosed claim limits. Other profiles' obligations remain
unchanged. Unsupported optional advice is lost advice; unsupported required
input or prerequisite prevents the release it was needed for.

## CA-05 — Scoped state and atomic evaluation commit

Provider state has its own admitted scope: mechanism instance, configuration,
authority and explicitly selected run/participant/episode sharing domain.
Profile identity and participant memory scope are not state-store keys by
themselves. A reset does not imply cleared influence or a fresh causal budget.
Sharing across participants or profiles requires explicit authority, isolation
and disclosure rules, exact state identity and common concurrency coverage.

All invocations begin from pinned immutable state versions. A next-state
reference is speculative. Shared-instance deduplication requires identical
binding, inputs/predecessors, configuration, authority and state scope, retaining
every selecting profile. Equal implementation names do not establish sharing.

Multiple updates to one state scope require an admitted serial transition
chain or a conflict. A serial edge explicitly supplies the predecessor's
tentative state as a versioned input; it is not an ambient committed mutation.
Reject an undeclared writer, a fork or unordered competing updates. Independent
state scopes may proceed independently; optional rejected contributions cannot
mutate either their own committed state or mandatory state.

The admitted transition rule distinguishes evaluation-state updates (for
example, recording an observation) from updates conditional on parent release.
A refused parent may commit the former only when explicitly authorized. It
cannot commit action-success state or discarded candidate state. All accepted
updates, the complete decision/reasons, coverage and result bindings, authorized
effect intents, logical claims and consumed budgets commit in one expected-head
and state-version transaction under the incumbent ADR-104 store authority.
Every shared scope must participate; unsupported cross-store atomicity is
unsupported support, never best-effort success.

Stale heads or failed commit publish no speculative state and dispatch nothing.
Retry resolves a fresh K within the admitted attempt budget. Commit alone
proves no world effect. Final invocation retains current authority/capability,
target/policy checks and generation fencing or an equivalent dispatch lease.

## CA-06 — Parent decisions and effect targets

A **parent decision** concerns the exact crossing/proposal being evaluated.
Permit means only that this decision does not block it; deny refuses it;
withhold keeps it pending with a bounded resumption/expiry condition. These
decisions are settled before release, with every mandatory reason retained.
Deny is never reduced to withhold merely because another prerequisite exists.
Permit cannot override deny/withhold or an incumbent gate.

The revised contract represents parent decisions as unscheduled decisions,
separate from executable effect requests. An old-shaped parent-targeted
permit/deny/withhold is not an independently executable operation. During an
explicit source conversion its meaning must be preserved before phase
composition; a purported instruction to deny an already released parent is
invalid. Never dispatch the parent and schedule its denial for later.

Every executable effect names its own exact typed target and owner, originating
principal/authority, rule, trigger, identity, phase and outcome prerequisites.
A decision about another target belongs to that target's admission context;
it is not permission to mutate its history from this evaluation. Effect target,
parent relationship and execution order must be represented separately.

## CA-07 — Prerequisites, consequences and order

| Relation | Parent meaning and execution condition |
| --- | --- |
| Required predecessor | Parent remains withheld until the exact prerequisite owner outcome is satisfied. Commit the withhold and independently admitted prerequisite. Reevaluate the parent at a fresh K after completion. Completion does not erase any other blocker. |
| Success-dependent consequence | Execute only after evidence of the declared parent outcome, such as application. A committed intent, dispatch attempt or accepted receipt does not establish application. Consequence failure does not undo an applied parent. |
| Independent consequence | An admitted rule may request an audit/review for specified parent dispositions, including deny/withhold. The committed decision is the trigger; the consequence has its own authority, support, target, admission and outcome. It cannot release or resurrect the parent. |

A consequence intentionally dependent on admission rather than application
must name that admission event as its prerequisite; it cannot claim a
successful realized parent. Required predecessors run only when remaining
parent blockers are exactly the prerequisites they can satisfy. Work for a
denied parent requires a separately admitted independent-consequence rule.

Check the combined graph of parent release/outcome events and effect
prerequisites, not just the provider DAG or each phase separately. A
prerequisite waiting on its own parent's success is cyclic and inadmissible.
Every prerequisite receipt binds exact logical intent, target, owner outcome
and its validity relation at the fresh cut. Stale, mismatched, failed,
unsupported and indeterminate outcomes authorize no dependent dispatch.

MPC-07's target compatibility still applies: order cannot repair conflicting
replacements, routes, handoffs or lifecycle outcomes. A shutdown cannot precede
an operation requiring that target live. A transform withholds/supersedes the
old candidate and creates a fresh candidate with lineage and ordinary gates;
it cannot both release the original and replace it. Disjoint operations may
remain unordered only with admitted independence. All-or-nothing external
plans require evidenced backend transaction support.

## CA-08 — Complete composition and evidence

Parent eligibility conjoins incumbent gates, total required coverage, every
typed satisfaction/support relation in M, conflict-free required state/effects,
and satisfied required predecessor outcomes. Release additionally requires the
atomic commit and final-invocation guards. Eligibility, authorization, committed
intent, attempted execution, application, delivery and observation stay distinct.

Preserve all contributor and safe failure records in canonical instance/slot
order, all required blockers and all discarded optional contributions. A
displayed disposition summarizes rather than deletes reasons. No response,
schema acceptance, method presence or digest proves installed capability,
authority or realization. Reuse bounded references, coarse reasons and ordinary
participant/audience projection; denial, timing and audit existence are also
potential disclosures.

Logical effect keys, allocated fresh identities, per-root/per-rule budgets,
finite depth/fan-out/retry limits and expiry retain MPC-11/12 meaning. Shared
causal roots across histories retain one authoritative consumption boundary.
Replay does not reset consumption, recompute old applicability, invoke a
provider again or dispatch an uncertain effect. An indeterminate effect needs
exact owner reconciliation; local commit is not distributed exactly-once
execution. Unpublished domains or effect variants remain unsupported.

## CA-09 — Publication and claim boundary

The [worked cases and verification map](../../../docs/research/control-applicability/cases.md)
bind each decision to bounded counterexamples. Existing SEM-235 domain,
freshness, authority, budget and recovery witnesses retain their original
scope. This publication supplies no new schema, production scheduler, provider,
storage engine, runtime adoption, external cancellation, delivery guarantee,
backend parity, unbounded liveness or noninterference proof.

Producer, protocol, reader, retained history and capability admission must adopt
the new meaning coherently under the migration contract. Semantic acceptance
amends the requirements; it does not upgrade their historical implementation
evidence into proof of the new clauses.
