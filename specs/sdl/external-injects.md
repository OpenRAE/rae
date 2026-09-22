# External inject triggering and execution

Semantic decision: external-inject-occurrence/rev1, under
[ADR-112](../../docs/decisions/adrs/adr-112-external-inject-triggering-and-execution.md).
This is the normative DSL-111/DSL-142 amendment, not a wire schema, endpoint or
claim that the current runtime/backend executes these rules.

## EI-01 — Authored intent and resolved targets

Reuse Inject, Event, Script, Story and optional Node.injects declarations.
An external trigger instantiates one authored inject, not an arbitrary command
and not an entire event. A separate admitted occurrence is needed for every
other inject in that event. Record the canonical inject address, scenario and
compiled-plan content pins, realization profile/version, source artifact
identity and integrity, target/run, concrete binding set and narrative placement
when applicable. Entities describe narrative endpoints; neither they nor an
opaque environment string identify a host, actor, participant or controller.

The request selects one admitted binding or an explicit nonempty subset of a
resolved fan-out. Each binding names a concrete realization instance and its
revision, including node-count expansion and module namespaces. Missing,
ambiguous, cross-run or stale selections refuse; never silently choose every
host or the first matching name. A top-level inject without Node.injects may
execute only when its selected realization supplies an explicit resolved target
contract, not by inferring hosts from entity names. Optional or floating source authoring remains valid, but execution requires a
resolved executable realization and immutable artifact pin; retries never
re-resolve a floating selector. A descriptive inject without such a realization
is unsupported, never a successful no-op. No source replacement,
plan mutation, arbitrary URL/path callback or expanded scope is permitted.

An event-anchored request retains that event's assertions. A scheduled placement
also retains script/story identity, window and occurrence coordinates. A direct
request with no narrative placement requires an admitted independent binding;
it cannot omit an existing binding's event/schedule preconditions to evade them.
The selected source's intrinsic preconditions also remain binding. Unknown or
unsupported assertion truth refuses; use the existing proposition/assertion
owner. No synthetic event, script, story or participant is required.

## EI-02 — Input and identities

Separate static source artifact, runtime input, produced result and disclosed
item. A realization declares a closed, bounded input contract with media/schema
identity, allowed parameters, exact scalar types, artifact trust and provenance.
Absent input contract means no runtime parameters, not an open dictionary.
Parse serialized input with existing bounded duplicate/nonfinite-rejecting
ingress before ambiguity is lost, then validate shape and contextual bindings.
Perform the same semantic checks for embedder calls and persistence readers.
Existing Inject.environment gains no shell or environment-assignment grammar.

Persist a value-free commitment to admitted intent and classified input refs;
extend the owning ephemeral exact-retry mechanism deliberately for any
sensitive input. Current account-credential helpers do not already protect
arbitrary inject payloads. Never
persist raw secret values or guessable secret digests. Loss of an ephemeral
commitment cannot be treated as equality; retain the claim and refuse an
unverifiable retry without redispatch. References/digests still need disclosure
authorization. Payloads cannot supply credentials, executable selectors or
accepted outcome evidence. Backend secret/input resolution uses existing owners.

Keep request key, operation ID, logical occurrence ID, attempt/generation,
narrative placement, delivery occurrence and observation occurrence distinct.
One accepted occurrence may select multiple concrete bindings; that does not
promise atomic world effects. Repetition uses a fresh occurrence and fresh
request key. The admitted binding defines whether an occurrence is independently
repeatable or is a uniquely identified schedule slot. A schedule slot may be
claimed only once, even with another occurrence ID or request key.

Within the ADR-104 target/run store, the retry key is (actor, operation kind,
client key). Bind its immutable commitment to occurrence ID, exact target set,
payload/source, plan/interpretation, cut/order and optional composition joins.
Exact authorized retry returns the original operation/occurrence and current
recorded outcome without a new admission or invocation. Changed content
conflicts. Independently claim occurrence identity in the run: another retry
key cannot execute an already claimed occurrence. Another actor cannot take it
over or inspect its receipt. Authorize receipt access before any lookup and
before revealing whether another actor's claim exists. Re-check current read
authorization, not original execution admissibility, for an exact retry.

## EI-03 — Trusted order, time and admission

One admitted ordering authority sequences scheduled, external and derived
requests for the same orchestration run. Its token names the scope, exact
predecessor/head and order; transport arrival, UUIDs, collection order and lock
acquisition are not semantic ordering. Ambiguous order is withheld/refused
before claim. Ordered contenders are revalidated at their turn; a stale
expected cut is rejected without substituting a new revision. Order and clock
validity are independent: resolve domain, clock, segment, tick/microstep and
explicit mappings through the shared time owner. An expired or unmappable
request cannot become valid through a smaller order number.

Admission requires authenticated principal, current mutation authorization,
exact target/run/plan and binding, applicable event/schedule assertions,
payload/source trust, selected interpretation, bounds and causal budgets,
supported installed protocol, and admitted outcome/evidence capability.
Existing inject-binding support or successful plan start is not that capability.
An audit-only principal cannot trigger. General world effects require neither
declared participants nor a participant-runtime component.

A pre-claim denial has no accepted occurrence; use bounded, redacted rejection
audit. Claim the operation, request key, occurrence and optional schedule slot
atomically with actor-bound admission evidence and the expected store revision.
A failed commit exposes no accepted claim or dispatch. Queueing grants no
lasting authority: before dispatch revalidate live authority, target/binding
revision, preconditions, time, budgets, effect reservation and backend
willingness. An invalid queued request is withdrawn with zero dispatch and a
retained claim. No no-op or participant-view fallback may stand for execution.

## EI-04 — Execution and settlement

The abstract relation is:

- unclaimed -> denied, or atomically admitted with immutable claims;
- admitted -> withdrawn before dispatch, or running with durable intent;
- running -> effect-applied, effect-absent, known-partial, or indeterminate;
- terminal -> append linked reconciliation evidence, never refire or rewrite.

These are semantic facts mapped onto existing operation states and stable
diagnostics, not additional persisted enum values in this publication.
An installed executor must write the running attempt/generation before invoking
the backend. Reuse ADR-104's short mutation permit, retained conflicting-effect
reservation, bounded supervision and execution-generation fence. Store CAS
does not fence a remote effect. A lost owner or timeout does not release a
conflicting reservation without evidenced cessation.

Backend support, willingness, acceptance and applied effects are separate facts.
A backend may refuse before any effect, and its refusal still needs the
contractually valid no-effect/cessation basis. After invocation, an exception,
disconnect, cancellation acknowledgement or invalid result proves neither
success nor absence. Unknown or potentially late effects are indeterminate.
Known partial effects require per-binding residual state and cessation evidence
under the admitted outcome contract; missing targets cannot be assumed absent.
For fan-out, retain each binding's outcome: all applied is effect-applied, all
proven absent is effect-absent, a fully known mixture is known-partial, and any
unknown binding makes the aggregate indeterminate while preserving known facts.

Validate outcomes against occurrence, attempt/generation, target/run/binding
revisions, source/input commitment, backend identity, observation/readback basis
and evidence integrity. Queued/bound status, a true boolean, control acceptance
or a nonempty evidence reference is insufficient. Required evidence and produced
evidence are distinct. Atomic terminal commit includes validated state,
operation outcome and immutable actor-bound audit; failure after the world
effect leaves an unsettled/indeterminate attempt for reconciliation.

Recovery observes under the original pins and ownership, never blindly invokes
again. Exact client retries, new retry keys, delivery retries and new processes
cannot bypass retained claims. Later attributable evidence links a resolution
to the original immutable result and generation; it does not rewrite history,
unblock conflicting work without cessation, or upgrade stale results to current
state. There is no exactly-once remote execution, universal rollback, liveness
or physical cancellation guarantee. P0 has only its admitted in-process
guarantees; P1/P2 durability does not imply P3 multi-writer coordination.

## EI-05 — Optional participant composition

World effects, disclosure authorization, delivery, observation and control
acceptance have separate records and outcomes. An environment-only occurrence
may affect services used by undeclared people/agents. A researcher can trigger
an authored world condition without becoming a participant or controller.
Changing a world approval condition is not approval of an API-409 proposal.

An explicit participant binding additionally resolves declared addressee,
episode, authenticated audience, observation boundary, independently pinned
delivery policy, markings/provenance, time and final-sink flow checks. It joins
the exact world occurrence and produced-result identity/evidence, not merely an
inject declaration or the latest narrative event. Pure disclosure of an existing
item retains its existing meaning and need not invent a world effect.

Direction/intervention additionally binds the exact accepted ADR-110 control
occurrence identity/revision, edge/policy, acting source controller, typed
target, authority scope, validity and evidence. The caller's operational role
and the control-subject/audience bindings confer different authority. Do not
classify a participant direction as an environment effect to evade these gates.
One (control occurrence, participant binding) authorizes at most one logical
delivery; independent fan-out uses separately admitted bindings. Reserve that
pair atomically through the existing crossing/history/receipt owner before
emission. Retain the reservation after a lost acknowledgement or crash; unknown
delivery requires reconciliation, never blind emission under a new client key.
An exact receipt lookup is separately authorized; a pending emission still
requires current disclosure gates.

API-424 inject effects require a fresh orchestration occurrence and produced
result with source provenance; a participant status view alone satisfies
neither. If composition requires a world effect, its outcome is a predecessor
to the corresponding result delivery. Optional delivery failure preserves the
world outcome; required delivery failure keeps composed success/dependent
progress withheld without claiming rollback. A failed world effect supplies no
successful effect result for delivery. Any failure notification is a separately
authorized disclosure. Delivery retry reuses the effect/result identity and
cannot refire it. Emission, acknowledgement and observation require their own
evidence; no participant observation follows from transport success.

Legacy DSL-142 anchors still require their original event/script/story fields.
The new semantic join permits an independently admitted external occurrence
without a schedule, but only through explicit versioned occurrence/reader
support. Do not fabricate anchors or make old fields optional to pass validation.

## EI-06 — Ownership, compatibility and assurance

ADR-104/API-403/404 own operations, authorization, retries, storage and recovery.
API-402 and RUN-300/304 own portable submissions and live history. DSL-111 owns
authored narrative identity and this occurrence relation; DSL-142 owns optional
participant binding. ACT-617/API-409/RUN-310 and ADR-110 retain control semantics;
API-423/RUN-319 retain disclosure/delivery; SEM-235/API-424/RUN-320 retain
modular-effect admission, causal budgets and predecessor obligations. API-421
owns shared time and ASR-532 owns backend-result admission. This amendment
composes those owners and creates no second authority for them.

The shared runtime drives execution through the existing orchestrator/backend
boundary. A concrete backend owns artifact execution, native target access,
input/secret handling, cancellation/cessation and readback. The portable
contract fixes identity, admission, ordering, outcomes and evidence without
selecting a transport, container/process model or backend-specific command.
A backend must explicitly admit this versioned invocation/outcome capability;
supports_inject_bindings is insufficient.

The [compatibility contract](../../docs/explain/sdl/external-inject-compatibility.md)
defines producer/reader and history compatibility.
No published schema or runnable parser form changes here. Existing canonical
authoring is reused where sufficient; realization input/target contracts are
explicit adoption artifacts, not new mandatory SDL fields.

Invariants: claims are unique and immutable; denial/retry never dispatches;
every dispatch follows a valid claim and running intent; no stale cut is
silently rebased; unknown effects stay unknown; fan-out retains every selected
binding; participant delivery cannot create a world effect or observation;
historical interpretation and actor attribution remain stable.

The [bounded test relation](../../implementations/python/tests/test_issue_1353_external_inject_design.py)
checks finite claim/order/lifecycle/outcome and
delivery projections. It assumes trusted resolver/authorization/clock/evidence
inputs and an atomic store. Existing parser/compiler and delivery tests witness
legacy behavior. Neither test family proves the new HTTP/core/store/backend
implementation, adversarial ingress security, actual effects or observation.
Coordinated adoption requires behavioral tests at those real consumers.
