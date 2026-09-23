# Modular Participant Control and Extensible Dynamic IFC

Issue #1354 and ADR-113 publish [IFC profile variability and publication](ifc-profile-variability.md).
The amendment separates authored requirements, exact profile expressibility
and evidenced realization, preserving this document's original revision and
implementation boundary. It adds no registered owner-aware profile or runtime
support; its migration contract governs future adoption.

Authority revision: `sem-235/rev1`. Publication owner: SEM-235, issue #1070.
Incumbent authorities: SEM-230 and SEM-233. Classification: FM3.

This is the formal semantic publication of
[ADR-108](../../../docs/decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md)
and `participant-control-composition/rev1`, accepted by #1068 at
[`ebb70a34b8e7d1cc8964c443841ae57e12ed1014`](https://github.com/OpenRAE/rae/commit/ebb70a34b8e7d1cc8964c443841ae57e12ed1014).
The [PC-01–PC-15 architectural clauses at that revision](https://github.com/OpenRAE/rae/blob/ebb70a34b8e7d1cc8964c443841ae57e12ed1014/docs/research/modular-participant-control/composition.md)
are incorporated as requirements. MPC-01–MPC-15 below give their formal
publication correspondence in the same order. Profile revision, semantic
publication, wire-contract version and implementation support are independent.
Terms here do not introduce wire fields or a callable provider protocol.

Issue #1352 publishes the separately identified
[applicability and evaluation amendment](control-applicability-and-evaluation.md),
clarifying MPC-01–03 and MPC-05–11. Use its CA-01–CA-09 relations for the revised
interpretation. The clauses below retain the original `sem-235/rev1` publication
and evidence scope; historical evaluations are not reinterpreted by this link.

## MPC-01 — Selection and identity

An admitted composition B is a finite set of profile-instance bindings and a
finite set S of typed result slots. A binding pins profile id, revision and
content digest; mechanism instance and revision; protocol revision; installed
implementation artifact/version/digest; configuration digest; authority;
applicability; state/memory scope; limitations; evidence; and finite bounds.
A profile selects mechanisms; a mechanism resolves results; an IFC domain
defines labels; a policy relates results to a sink. These identities MUST NOT
substitute for one another.

Applicability is a closed relation over admitted participant, episode,
direction, crossing/subject kind, sink and phase references. Unresolved
applicability prevents admission; it is not false applicability. Overlapping
applicable profiles conjoin. Exact complete binding, state scope and inputs
are necessary for shared-instance deduplication; retain every selecting
profile. Empty optional selection leaves all incumbent gates intact. A required
selection absent from B prevents apparatus admission.

Changing any pinned coordinate requires a recorded new admitted binding at a
new cut. A pre-admitted alternative still requires an explicit selection
transition, effective-support validation and disclosed weakening. No transition
edits historical bindings, removes another profile's mandatory obligation by
implication, or upgrades earlier evidence.

## MPC-02 — Resolution boundary

Resolution is a relation from an immutable admitted context and pinned inputs
to typed results and, where needed, a proposed next provider-state reference.
It has no participant/world effect. Proposed state is speculative until the
decision's atomic commit; conflict discards it. Independent providers cannot
mutate each other's inputs. A monitor's external computation is itself an
admitted apparatus operation with disclosure and resource controls.

Backend/operator construction binds installed providers. Scenario or
participant content cannot name imports, paths, URLs, commands or configuration
expressions that install or execute code. A digest establishes identity, not
trust. Coverage of explicit, implicit/control, native and external flows is
declared and evidenced independently of interface presence.

## MPC-03 — Exact context and typed satisfaction

Let K contain run, apparatus binding, participant, episode, subject, crossing,
direction, sink/audience/destination, controller, authority, policy revisions,
state cut, expected history heads, provider-state references, trigger root,
predecessor references, memory scope and governed time/order point.
Equality of K means equality of every applicable coordinate, including pinned
revisions and digests; a timestamp or participant id alone is insufficient.

Each slot s has an instance, kind, mandatory/advisory role and typed dependency
references. Kinds are IFC fact, deterministic decision, advisory assessment
and typed effect request. Resolution status is independently one of resolved,
missing, unknown, unsupported, stale, failed or weakened. A resolved decision
is permit, deny, withhold or abstain. Invalid bindings are rejected, never
coerced to resolved. Conflict belongs to composition/commit; applied belongs
to realization. Neither is a label or provider permission.

Define valid(s,r,K) iff r names s's exact instance/profile/input bindings,
kind and K, has resolved status, carries the required safe provenance/evidence,
and satisfies its owning payload relation. Fact validity is not permission.
Decision satisfaction additionally requires permit. Request validity does not
mean that its operation has been authorized or applied.

## MPC-04 — Dynamic IFC and the first non-security domain

A domain D publishes a closed carrier L, canonical encoding, partial order
≤, total conservative join ⊔, source/default relation, propagation relation,
sink policy, memory/reset scope, permitted release relations and limitations.
For a,b,c in L, ⊔ is closed, associative, commutative, idempotent and monotone,
and a ≤ a⊔b and b ≤ a⊔b. The general contract requires an upper bound, not
an additional least-upper-bound theorem. A failure is outside L. An unknown
token or revision cannot extend L; comparison across domains/revisions is
unsupported without a published mapping carrying authority, provenance and loss.

For every derived value v, let Inputs(v,K) contain every possible data, retained
memory, context, argument-selection and declared control dependency. Unless an
authorized published release/non-influence relation applies:

```text
label(v,K) ≥ join { label(x,K) : x in Inputs(v,K) }
provenance(v) includes every input identity and derivation basis
identity(v) is fresh; historical input identities and labels are immutable
```

Missing input coverage is not an empty known set and cannot yield bottom.
Opaque computation carries all possible inputs. Parsing, editing, masking,
handoff, routing and episode reset do not establish non-influence. A reset may
change the governed memory scope only with its owning reset authority and
evidence that the retained dependencies are absent; prior delivery remains
historical knowledge under SEM-230's selected memory relation.

### Published semantic profile: teaching-influence/rev1

Domain identity: `teaching-influence-domain/rev1`. It is a non-security IFC
domain, with the exact closed token universe T = {coached-hint, worked-example}.
L = P(T), order is subset, join is union, bottom is {}, top is T. Canonical
encoding orders these two semantic references lexically, without duplicates.
These are semantic encodings, not a newly published JSON contract.

The admitted source relation assigns coached-hint to a governed hint source,
worked-example to a governed example source, and {} only to an explicitly
known uninfluenced source. Missing/unresolved source classification is unknown.
No source resolver may infer {} from absent data. Derivation unions all known
input, memory and control influence. Unknown input makes the result unknown.
The profile retains participant memory across episodes unless the above reset
relation establishes no retained influence. Revision 1 permits no influence
removal: its release relation is empty. New removal semantics require a new
governed revision; a trusted teacher or changed episode is insufficient.

For a known label, the practice-action and teaching-observation sinks impose
no additional IFC refusal. Mandatory propagation remains required and ordinary
authority, projection, resource and action gates still apply. Other sinks
require their own admitted policy; unknown labels never satisfy propagation.
The admitted hint-followup/1 rule consumes the propagation fact and requests
a subsequent inject from a pinned reflection-prompt artifact when coached-hint
is present. The rule has teaching authority, explicit addressee/visibility,
one firing per root, two total effects, depth two, finite fan-out, finite
resolution/retry limits and a governed expiry. The inject retains source and
trigger-control influence. This profile makes no confidentiality, integrity,
learning-outcome or noninterference claim.

### Incumbent security profile

`sem-233/rev1` and `participant-boundary-flow-policy-v1@rev1` keep the exact
[published two-coordinate algebra](adversarial-flow-control.md#exact-revision-1-flow-algebra):
P(C) × P(I), independent obligation coordinates and componentwise union.
Their unresolved-state obligations, coordinate-specific declassification and
endorsement, immutable provenance, and final-sink predicates remain unchanged.
The reusable machinery is revision binding, conservative propagation,
typed resolution, exact-cut conjunction and independent effect admission.
Teaching tokens are not a third security coordinate or a relabeling of history.
Known attacker influence may satisfy an intentionally permissive observation
sink without endorsement. The same label can fail a later action sink.

## MPC-05 — Dependency and conjunction relation

The slot/rule dependency graph is finite and acyclic. Every edge names a
declared output kind and required input slot. Undeclared edges, type mismatch,
ambiguous bindings, cycles and later facts are inadmissible. Independent
results bind one K; deterministic rules consume pinned predecessor results.
Recorded stochastic assessments are inputs: composition determinism does not
imply repeatability of provider sampling.

Let G(K) conjoin incumbent authentication, authorization, action admission,
capability, crossing, projection and final-sink predicates. Then:

```text
eligible(K) = G(K)
  and every applicable mandatory result slot is valid and satisfied at K
  and every mandatory dependency is satisfied
  and every required predecessor effect is realized and freshly revalidated
  and the requested effect plan is supported and conflict-free
release(K) = eligible(K) and expected-head atomic commit succeeds
```

A mandatory fact slot requires a fact, not a permit; a mandatory decision slot
requires permit, not a fact. Mandatory abstain is unsatisfied. Every blocker
is retained in canonical instance/slot order. Sorting is serialization only.
Empty mandatory decision sets cannot overcome false G(K).

## MPC-06 — Failure and advisory interpretation

| State | Required consequence |
| --- | --- |
| Mandatory deny | Refuse the affected parent and retain safe denial evidence. |
| Mandatory withhold | No release now; retain pending subject and resumption/expiry condition. |
| Mandatory abstain, missing, unknown, unsupported or failed | No release; retain each unsatisfied slot and exact status. |
| Stale K/history or commit conflict | No dispatch; bounded resolution at a fresh K, never reuse the old permit. |
| Weakened mandatory support | No release under the requested binding; any admitted alternative has its own effective identity and claim limits. |
| Missing, failed or abstaining optional advice | Record lost advice; it grants no permission and discharges no mandatory slot. |
| Resolved advisory permit, deny or score | Evidence without direct grant or veto. Only an admitted rule can request an independently gated effect. |
| Malformed/mismatched optional result | Discard its contribution, record failure; dependent mandatory obligations remain unsatisfied. |

A claimed guarantee that needs an assessment must make the needed input slot
mandatory, even if the assessment is heuristic. Marking it advisory cannot
hide that dependency. An admitted review rule specifies its threshold revision,
authority, visibility, missing-state behavior and expiry.

## MPC-07 — Effect compatibility

A request names one closed effect kind, subject/result type, target/sink,
rule revision, authority, phase (required predecessor or subsequent), causal
references and bounded parameters/artifact references. Complete equal
canonical content under one logical key deduplicates. Different content under
that key conflicts; different rule identities remain separate requests.

All mandatory rules conjoin. Permit cannot override deny or withhold.
Different replacements of the same proposal, routes to different destinations,
handoffs to different controllers or incompatible lifecycle outcomes conflict.
A transform chain must declare finite dependency edges through fresh subjects;
ordering two incompatible replacements of the same original does not repair
the conflict. The replaced proposal is withheld and never also dispatched.

Delay constraints in one admitted clock intersect: [a,b] ∩ [c,d] =
[max(a,c),min(b,d)], admissible only when the lower endpoint is no greater
than the upper. An unresolved cross-clock relation or empty intersection
conflicts. Authority/resource expiry still applies at the eventual release.
Effects sharing subject, authority, lifecycle, time, resource or sink state
require explicit compatible ordering and fresh validation. Disjoint effects
may be unordered only with declared and evidenced independence. Shutdown
cannot precede an operation requiring that target to remain live. No lexical,
specificity or provider-arrival winner is selected.

## MPC-08 — Authority and participant visibility

Effect authority is the intersection of current controller/principal authority,
admitted rule scope, target capability and ordinary operation/sink policy.
Authentication, authorization, admission, approval, declassification,
endorsement, transformation, handoff and execution remain distinct. No result
widens that intersection. A separately authorized audit/review may be requested
for a denied parent only when its admitted rule allows that disposition.

Use SEM-230 participant/audience projection for sources, derived values,
decisions, reasons, control transitions, audit and receipts. Existence and timing
of an inject, withhold or review may disclose a condition. Supervisor visibility
does not imply subject visibility. Safe evidence consists of bounded,
digest-bound references and closed coarse reasons, never raw rejected values,
hidden objectives, prompts, credentials or backend-private state. Digesting
sensitive low-entropy content is not sufficient redaction.

## MPC-09 — Typed effects and existing owners

| Effect | Binding and semantic owner |
| --- | --- |
| permit / deny | API-423 exact crossing/action disposition; permit is not execution. |
| withhold | SEM-226/API-423 intentional non-release, pending subject and fresh later cut. |
| transform | API-423 derivation or API-409 trusted edit; fresh representation/proposal with lineage and re-entry. |
| mask | SEM-226/API-423 participant-relative derived projection; no implicit declassification. |
| inject | Fresh DSL-111 occurrence, DSL-142 addressee/delivery and API-423 disclosure; API-409 for directions/control changes. |
| delay | API-421/RUN-308 governed clock, bounded window/expiry and revalidation. |
| route | Existing target/crossing destination refs, fresh candidate and destination admission; SEM-234 for a mixed-backend edge. Not controller transfer. |
| audit | Existing bounded evidence/audit carrier, retention and audience policy. |
| handoff | ACT-617/API-409/RUN-310 ordered controller transition; labels survive. |
| request review | API-409 supervisory obligation, approval/denial references and expiry; approval does not execute the parent. |
| interrupt / shutdown | RUN-310/API-409 authorized lifecycle scope; distinguish participant, episode and run targets, pause, cancellation and termination. |

API-424/#1072 owns closed trigger-to-incumbent contract bindings, including
review/expiry/lifecycle alternatives absent from incumbent DTOs. Publication of
this table does not advertise those contracts or installed effect support.
Unsupported effects stay unsupported; no callbacks or open effect maps fill gaps.

## MPC-10 — Commit and final invocation

The abstract progression is received → resolved → composed → admitted →
committed → dispatched → applied/failed/indeterminate. Refusal, unsupported
state, stale cut and conflict stop before dispatch. Decision, provider next-state,
effect claim, consumed budgets and authorized intent commit atomically against
expected operation/participant history heads using the ADR-104 store authority.
Failed commit produces no prohibited backend call or participant disclosure.

Immediately before invocation, authority, capability, policy, target and history
still bind the current admitted K. A commit-bound generation fence or exclusive
dispatch lease covers final invocation; asynchronous delivery unable to retain
it re-enters final admission. Check-then-unfenced-call is not complete mediation.
Unsupported fencing cannot be claimed as implemented. Serialization, streams,
errors and evidence export are sinks. Commit, delivery and observation are
distinct; append-only realization evidence never rewrites a prior decision.

## MPC-11 — Fresh identity, phases and recovery

The logical effect key is (run, trigger root, rule id/revision, effect slot,
admitted firing epoch). A governed new trigger event establishes the epoch;
retry count, current K, transport identity, handoff and episode changes do not.
Allocate a fresh result/occurrence identity once per logical key and retain it
across replay. Attempts have fresh cut/evidence bindings, not fresh effect keys.
Complete changed canonical intent under a claimed key conflicts.

Required predecessors cause a committed parent withhold and separately admitted
operations. Realization/approval satisfies only that obligation; the parent
reevaluates all gates at a fresh K. Subsequent operations have independent
admission and outcome; failure does not undo an applied parent. All-or-nothing
plans require exact backend transaction support or are unsupported.

Applied replay returns its receipt. A committed, undispatched claim resumes
only with durable proof dispatch never started and current final admission.
Once dispatch may have begun, the result remains indeterminate until exact
backend idempotency/readback establishes absent or applied. Never blindly
repeat a non-idempotent external operation. A local commit is neither external
success nor distributed exactly-once delivery. In-memory evidence supports only
its process lifetime; restart claims require durable storage and backend proof.

## MPC-12 — Finite causal closure

Every admitted root has finite nonnegative depth, total-effect, per-rule firing,
resolution/retry and expiry bounds, plus finite fan-out. A new effect claim
atomically consumes root and per-rule budget even if realization later fails.
Duplicate keys consume no second unit. Every causal child increases depth and
inherits its root. Reset, restart, route, transform, retry and handoff cannot
reset it. Independent inputs obtain fresh roots only through ordinary input
admission and run resource limits.

Exhaustion records a bounded reason. Required effects leave the parent
withheld/refused; optional subsequent effects remain unapplied. Expiry uses the
declared clock/order authority. Diagnostics cannot recursively trigger themselves.
These bounds establish finite admitted causal work, not fairness, progress or
unbounded liveness.

## MPC-13 — Evidence and claim boundary

Evidence pins requested/effective profiles, mechanism/protocol/implementation
revisions and digests, configuration, authority, domain/policy/rule revisions,
world coverage, memory, clock/order, backend artifact, support strength, loss,
provenance and limitations. Reuse existing apparatus, claim and evidence refs.
Private mechanism state is not portable evidence.

Semantic publication, contract validity, runtime orchestration, installed
provider, backend declaration, observed realization, bounded conformance,
experimental evaluation and a separately justified theorem are different claims.
SEM-230's noninterference relations retain their exact observer, strategy,
memory, policy and quantifier scope. IFC labels, a successful inject, equal
outputs or a finite witness do not establish those relations.

## MPC-14 — Declared world and backend independence

A live source/sink belongs to the RAES world only through admitted identity,
authority, crossing, coverage and limitations. Intentional adversarial in-world
input is an experimental variable; retaining its influence can be correct
realization. Interference with an out-of-world provider, host, credential,
process, tenant or network invalidates/fails backend realization. Record that
in apparatus validity evidence rather than inventing an in-world attack.
Protection of that backend boundary remains the realization's responsibility.

Backends may independently implement different declared subsets with different
engines. Shared terms prove neither parity nor equivalence. Cross-backend
claims require their exact SEM-234/ASR-537 relation and evidence. Coverage ends
at the last enforced and observed boundary, including disclosed live variability.

## MPC-15 — Publication and bounded witnesses

[Concept placement](../../concept-authority/participant-control.md) maps these
terms to incumbent owners without a new universal ontology.
[Semantic verification](../../../docs/research/modular-participant-control/semantic-verification.md)
maps MPC clauses to worked cases, counterexamples and finite tests. The accepted
[cases A–G](https://github.com/OpenRAE/rae/blob/ebb70a34b8e7d1cc8964c443841ae57e12ed1014/docs/research/modular-participant-control/cases.md)
remain the case lineage; the verification record supplies the publication cut.

This publication supplies no production provider, backend instrumentation,
runtime orchestrator, plugin host, universal policy language, new wire schema,
external attack model, general safety/robustness result, backend equivalence,
universal noninterference, covert-channel protection or control of opaque
internals. API-424, RUN-320 and ASR-538 retain their separate delivery boundaries.
