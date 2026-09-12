# Participant-control composition contract

Architecture revision: `participant-control-composition/rev1`.
Decision: [ADR-108](../../decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md).
Owner: SEM-235; contract, runtime, and assurance owners: API-424, RUN-320, ASR-538.
The numbered clauses bind downstream design. Names below are semantic
alternatives, not newly published JSON fields or an importable provider API.

## PC-01 — Exact selection and applicability

An admitted apparatus binds a finite set of profile instances. Each pins a
profile id/revision/content digest, mechanism id/revision, provider protocol
revision, implementation artifact/version/digest, configuration digest,
authority scope, evidence and limitation refs. A profile can select multiple
mechanisms; multiple profiles can select different roles for the same mechanism.
A shared instance is deduplicated only when its complete binding, state scope,
and input set are identical. All selecting profiles remain in the evidence.

Each binding has a closed applicability predicate over admitted participant,
episode, direction, crossing/subject kind, sink, and phase refs. Overlaps
conjoin; specificity, source order, names, and provider arrival time confer no
priority. Unresolved applicability is an error, not non-applicability. An empty
optional selection makes no mechanism claim; incumbent authority, admission,
capability, and crossing gates still apply. An unsatisfied required selection
prevents apparatus admission.

Changing profiles, configuration, provider version, authority, or limitations
requires a new admitted binding at an explicit cut. Historical bindings and
decisions remain immutable. No profile may silently remove another's mandatory
constraint. A pre-admitted alternative can be selected only through a recorded
selection transition identifying the exact effective profile and weakening;
if that alternative lacks mandatory support, the transition fails.

## PC-02 — Provider responsibility and protocol

The public provider protocol shall resolve a typed, immutable context and
return a typed result. RAES owns its revision and conformance; backends own
implementation, installation, lifecycle, instrumentation, and trust. Runtime
construction binds already admitted provider instances to opaque stable ids.
Neither a scenario nor a participant can designate executable code via an
import, path, URL, shell expression, environment value, or configuration blob.
An implementation digest identifies what ran; it is not a trust decision.

Resolution has no participant/world effect and cannot mutate the authoritative
cut. Stateful tracking uses a versioned provider-state/input snapshot and
proposes its next state reference for the same commit as the decision. Speculative
updates are discarded on conflict. A monitor's computation or external model
call is a separately admitted apparatus operation with its own disclosure and
resource controls; opaque monitor internals never become portable state.
Backends must disclose unobservable or unsupported propagation, including
implicit/control flow and native or external paths. Importability or method
presence establishes no support.

## PC-03 — Exact context and result kinds

Resolve at context `K = (run, apparatus binding, participant, episode, subject,
crossing, direction, sink/audience/destination, controller, authority, policy
revisions, state cut, expected history heads, provider-state refs, trigger root,
predecessor refs, memory scope, governed time/order point)`.

All contributing results bind the same applicable K, selected instance,
profile, input refs, safe evidence, provenance and limitations. Results have
closed payload alternatives: resolved IFC fact, deterministic constraint
decision, advisory assessment, or typed effect request. A provider may return
a bounded collection of these alternatives; it may not supply an executable
continuation. Each mandatory role has its own result slot, so a fact cannot
accidentally satisfy a decision slot.

Resolution status is separate from the payload: resolved, missing, unknown,
unsupported, stale, failed, or weakened. An unrecognized revision or malformed
binding is unsupported or invalid; it is never coerced to resolved. A decision
payload is permit, deny, withhold, or abstain. Applied is a later realization
status, never a provider's authority to execute. Conflict is a composition or
commit result, not a label. Every contributor and every blocking reason is
retained in canonical instance/slot order even when several reasons block.

## PC-04 — Extensible dynamic IFC domains

An IFC profile pins a domain artifact `D`, order `<=D`, conservative join `joinD`,
source resolver and default, propagation/derivation rules, sink-policy relation,
memory/reset scope, allowed release relations, and coverage limitations. The
domain carrier and canonical encoding must be closed and revisioned. The join
is total within that carrier, closed, associative, commutative, idempotent,
monotone and an upper bound. Unsupported joins are explicit failure results
outside the carrier. Empty known inputs can yield a declared bottom; absent
input coverage cannot.

The first general domain example is a finite powerset of declared experimental
influence refs with subset order and union join. A later domain requires
published algebra, source/sink semantics, fixtures and compatible closed
contracts. Arbitrary strings or keys supplied at runtime do not extend it.
Order means accumulated obligations or influence under that domain, not a
universal trust ranking. Non-IFC mechanisms keep their own state and decisions.

Opaque derivations retain the join of every possible input, including retained
memory, context, argument selection and declared control dependencies. Removing
an influence needs a revisioned non-influence or release relation and evidence;
editing, masking, parsing, handoff and episode reset do not imply removal.
Each result has fresh identity and lineage. Cross-domain/revision coercion is
unsupported unless a published mapping preserves the source, relation,
authority and any loss; a mapping never rewrites the historical value.

`sem-233/rev1` remains the independent confidentiality/integrity powerset
product and existing sink predicates. Known adversarial influence can satisfy
a particular observation sink's integrity policy without being endorsed.
Missing source authority or unknown labels retain SEM-233's failure behavior.
An observation-only non-security profile cannot impersonate SEM-233 enforcement.

## PC-05 — Composition and dependencies

Admission validates a finite acyclic dependency graph of input/result slots
and rules. Every edge names an output kind and an input requirement; later
facts, undeclared edges, cycles and ambiguous revision bindings are rejected.
Independent providers see the same K and cannot modify each other's inputs.
They may execute concurrently. Dependency layers are semantic, while ordering
independent ids is only canonical serialization.

The runtime validates all contributing results, resolves dependent rules,
combines mandatory constraints, normalizes effect requests and checks their
compatibility. It never performs a provider effect while evaluating a layer.
Nondeterministic monitor results are pinned as inputs (including seed or
external assessment refs where applicable); deterministic composition means
the same admitted bindings and recorded inputs produce the same result. It
does not promise that rerunning a stochastic provider reproduces its output.

Let `G(K)` be the conjunction of incumbent admission, authorization, capability,
crossing, and final-sink gates. For applicable mandatory decision slots M:

```text
release(K) iff G(K)
  and every mandatory result slot is resolved at K
  and every decision in M is permit
  and every required predecessor effect is realized and revalidated
  and the effect plan is supported and conflict-free
  and the expected-head commit succeeds.
```

Mandatory fact slots require a valid fact, not a permit. An intentionally
observe-only IFC profile may require propagation evidence without imposing an
IFC denial predicate. A mandatory abstain is unsatisfied, never implicit
permission. Permit from any other slot cannot overcome it. An empty M cannot
overcome a false G(K).

## PC-06 — Advisory, absence, weakening and failure

| Condition | Effective consequence |
| --- | --- |
| Resolved mandatory deny | Reject the affected action/release, retain denial evidence. |
| Mandatory withhold | No release now; retain pending occurrence and explicit resumption/expiry condition. |
| Mandatory abstain, missing, unknown, unsupported or failed | No release; preserve the exact unsatisfied slot and reason. |
| Stale result or history conflict | No dispatch; bounded re-resolution at a new K, never reuse the old permit. |
| Weakened mandatory support | No release under the requested binding; only an explicitly admitted alternative may proceed, with its own claim limits. |
| Advisory result absent, failed or abstaining | Record lost advice; it cannot widen permission or satisfy a mandatory dependency. |
| Advisory permit, deny or score | Evidence only; has no direct veto or grant. An admitted deterministic rule may request an independently gated effect. |
| Malformed or mismatched optional response | Record failure for that slot; never use its facts or requests. A dependent mandatory rule remains unsatisfied. |

A profile cannot call an output advisory and secretly depend on its presence
for a claimed guarantee. If it is required by a control rule, the dependency
is a mandatory slot even if the assessment itself is heuristic. Advice may
lead an admitted rule to request withholding or review; that rule's authority,
threshold revision, visibility and failure behavior must be explicit.

## PC-07 — Deterministic effect compatibility

Each request names one closed effect kind, exact subject/result type,
target/sink, effect-rule revision, authority, phase (required predecessor or
subsequent), causal refs, and bounded parameters or existing artifact refs.
Requests for the same logical effect slot deduplicate only if their complete
canonical content matches; mismatch is conflict. Different rule identities
remain separate requests even if their content looks alike.

All rules for the same parent are conjoined. A mandatory deny prevents the
parent; mandatory withhold prevents its release until its conditions are met.
Permit cannot override either. Audit or review for a denied parent can still
be proposed as separate operations when the admitted rule explicitly permits
that disposition; they acquire no authority from the denial itself.

Incompatible mandatory replacements (two different transforms/masks of one
subject), routes to different destinations, handoffs to different controllers,
or lifecycle outcomes conflict. No winner is selected lexically. Compatible
delay constraints intersect their declared time window/clock; an empty
intersection conflicts. Effects that consume or change the same authority,
lifecycle, subject, time, resource or sink state need an explicit dependency
order and revalidation. Disjoint effects may be unordered only when the
profile declares their independence and conformance covers it; otherwise they
conflict. Shutdown cannot be placed before an effect requiring a live target.

A transformation chain is permitted only as a finite declared dependency
chain. Each step creates a derived subject and reevaluates all applicable
mandatory gates; the old proposal is never both dispatched and replaced.
A rule cannot suppress re-entry checks by claiming that its own output is safe.

## PC-08 — Independent authority and visibility

Fact resolution, authentication, authorization, action admission, approval,
declassification, integrity endorsement, editing, handoff, and execution are
independent. Effect authority is the intersection of admitted rule scope,
current controller/principal authority, target capability, and ordinary
operation/sink policy. A label or monitor never enlarges that intersection.

Source, derived value, decision, reason, audit, control transition and receipt
each have participant/audience projection. The existence and timing of a
withhold, review or inject may itself disclose information and is governed
under SEM-220/226/230 and ADR-095. Safe evidence uses digest-bound refs and
closed coarse reasons; raw rejected payloads, hidden objectives, prompts,
credentials and backend-private state do not enter portable diagnostics.

## PC-09 — Closed effect vocabulary and incumbent owners

| Effect | Incumbent meaning and required binding |
| --- | --- |
| permit | API-423 crossing disposition; enables only its exact admitted subject and final sink. It is not execution. |
| deny | API-423 refusal/action rejection; zero prohibited parent effect, with safe reason evidence. |
| withhold | SEM-226/API-423 intentional non-release; original subject remains undisclosed. Any later attempt uses a fresh cut. |
| transform | API-423 derivation or API-409 trusted edit; fresh representation/proposal, complete lineage and ordinary admission. |
| mask | SEM-226/API-423 projection/transformation; fresh participant-relative representation, no implicit declassification. |
| inject | DSL-111 occurrence and scheduling; DSL-142 addressee/delivery and API-423 disclosure; API-409 additionally applies when directing or changing control. |
| delay | Existing scheduling/shared-time authority (API-421, RUN-308); exact clock, earliest/latest or expiry, withheld parent and revalidation. No unbounded sleep. |
| route | Existing action target or crossing destination/projection refs; fresh candidate and destination admission, not a new bus or controller change. Mixed-backend routes also require SEM-234. |
| audit | Existing bounded evidence/audit carrier, audience and retention policy; does not imply participant delivery or an independent audit channel. |
| handoff | ACT-617/API-409/RUN-310 ordered controller transition, exact authority and history; labels and obligations survive. |
| request review | API-409 supervisory obligation and approval/denial refs; API-424 must publish the closed request/expiry binding where absent. Neither request nor approval implies execution. |
| interrupt | RUN-310/API-409 cancellation/interruption and incumbent participant/workflow lifecycle, with explicit target scope; no undeclared process signal. |
| shutdown | Incumbent lifecycle termination through authorized runtime control; API-424 must distinguish its participant/episode/run target and supported semantics from pause or cancellation. |

These are architectural mappings. They do not assert that every incumbent DTO
already exposes every request. #1072 must publish closed trigger-to-incumbent
bindings, rule applicability, review/delay/lifecycle target alternatives and
their valid/invalid fixtures; #1069 must bind their execution. Unsupported
effects are reported explicitly. No arbitrary function, expression language,
native handle, free-form parameter object or universal gateway DTO fills a gap.

## PC-10 — Transition and final commit

The abstract operation states are received → resolved → composed → admitted →
committed → dispatched → applied/failed/indeterminate. Refused, unsupported,
conflict and stale attempts end before dispatch. Receipts distinguish a
committed intent from observed realization. A state transition appends evidence;
it never edits prior decisions. Provider-state refs, consumed budgets, logical
effect claims, decision and authorized effect intent join the existing atomic
operation/participant commit at the expected history heads.

Immediately before dispatch, authority, capability, destination and policy
resolution must still name the current admitted cut. A conflicting transition
invalidates the decision. A commit-bound generation fence or exclusive dispatch
lease must cover the final invocation; asynchronous delivery that cannot retain
that protection re-enters final admission. Merely checking a head and later
calling an unfenced target leaves a time-of-check/time-of-use gap. A backend
unable to enforce the claimed fence reports that exact guarantee unsupported.
A failed commit produces no backend call or
participant disclosure. Serialization, streaming, errors and evidence exports
are sinks too. Delivery is not observation, and a local write is not proof of
external realization. Snapshot/mutation authority follows ADR-104; no separate
trigger store, event history or recovery system is introduced.

## PC-11 — Predecessors, retries and external uncertainty

A required predecessor (for example review approval) causes a committed
withhold of the parent, followed by a separately admitted predecessor
operation. When satisfied, the parent is reevaluated at a fresh K. A subsequent
inject or audit has its own admission/commit and result; its failure does not
roll back an already observed parent. Profiles requiring all-or-nothing effects
are unsupported unless an explicit backend transaction capability covers that
exact plan. Distributed exactly-once behavior is not assumed.

One logical effect key is `(run, trigger-root occurrence, rule id/revision,
effect slot, admitted firing epoch)`. The firing epoch is created by a governed
new trigger event, not by a caller retry. Fresh identity is allocated once per
logical key and retained across retry/replay. The key excludes retry attempt,
current cut and derived transport id, which would allow duplicates. A repeated
key with different canonical content is conflict; attempts bind their own cut
and history. Stale retries rerun admission, not an already claimed dispatch.

An applied key returns its existing receipt. A committed-but-undispatched key
requires durable proof that dispatch has not started before resuming. Once
dispatch may have started, recovery records indeterminate until backend
idempotency or observation proves absent or applied. Never blindly repeat a
non-idempotent external action. An in-memory store can claim this only within
its process lifetime; crash/restart claims require durable storage and the
backend's exact recovery guarantees.

## PC-12 — Bounded trigger closure

The admitted composition supplies finite nonnegative limits for causal depth,
total requested effects per root, per-rule firings, resolution attempts and
governed expiry, plus finite fan-out. Each successful effect claim atomically
consumes root/per-rule budget even if dispatch later fails. A duplicate key
consumes no second budget. Depth increases for every causal child; handoff,
episode reset, route, transformation or process restart cannot create a fresh
root for the same causal event. New independent inputs receive new roots only
through ordinary input admission and run resource limits.

At a limit, record a bounded exhaustion reason; required effects leave their
parent withheld/refused, optional subsequent effects end unapplied. Do not
silently omit a required effect or turn exhaustion into permission. Delayed
effects expire or re-enter at the declared clock/order point. An inject that
re-triggers its own rule is bounded by both depth and firing limits; output
re-entry always retains ordinary gates. Failure reporting uses the incumbent
bounded diagnostic path and cannot recursively schedule itself as a trigger.

## PC-13 — Apparatus, capability and claim coordinates

Pin requested and effective profile sets, protocol/mechanism/implementation
revisions and digests, configuration, authority, label-domain/policy/trigger
revisions, world coverage, memory, time, backend artifact, support strength,
loss, evidence and limitations. Use existing apparatus, backend manifest,
behavioral-claim and evidence refs, not embedded private mechanism state.
Portable status distinguishes semantic publication, contract validity,
runtime orchestration, installed executable provider, backend declaration,
observed realization, bounded conformance, experimental evaluation and any
separately justified theorem. None automatically implies the next.

## PC-14 — Backend independence and admitted live worlds

LilRAE and Shifter select mechanisms independently. Shared contract vocabulary
does not require the same engine, profile subset or strength. Compare behavior
only under an explicitly matched semantic/profile relation and exact evidence;
SEM-234/ASR-537 own mixed-backend and transfer claims where relevant.
An admitted live source's variability and timing limits must be represented in
apparatus/evidence. Host/provider interference outside the declared world
invalidates that apparatus realization; it is not relabeled as an in-world
attack. Claim coverage ends at the last enforceable and observed boundary.

## PC-15 — Publication and conformance obligations

#1070 publishes formal semantic clauses, domains, concept-authority placement,
lineage and falsification cases. #1072 publishes schemas, protocols and exact
compatibility/limitation fixtures. #1069 replaces the implicit resolver hook,
retains an explicitly negotiated legacy SEM-233 path where compatible, and
tests real final-sink and both supported store paths without backend-name
branches. Legacy evidence retains its old scope; it cannot be upgraded by
importing a new protocol. #1071 publishes independent conformance probes for
all claimed effects and negative combinations, including omitted mechanisms,
order permutations, changed keys, stale cuts, crashes and exhausted triggers.

Only then can backend implementation and proof establish actual mechanism
realization. #1007 evaluates declared attacks against exact evidenced profiles;
#1008 and Hub publish only those bounded results. The [delivery graph](delivery.md)
and [requirements](requirements.md) specify the authority and release gates.
