# Multiple-operation participant-crossing models

Requirements: SEM-232, SEM-230, API-423, RUN-319. Issue #1395.
Classification: FM3. This is independent model construction, with no equivalence
or runtime-realization result.

## Exact revision and carrier

`participant-crossing-multi-operation-dpbb-finite-v1@rev1` selects
`sem-230-participant-crossing-multi-abstract@rev1` and
`api-423-run-319-crossing-multi-kernel@rev1`, under
`participant-crossing-multi-operation-projection@rev1` and taxonomy `rev8`.
The separate #971 `participant-crossing-dpbb-finite-v1@rev2` profile, its model
sources and published artifacts retain their identities and semantics.

The environment admits **at most two** fresh durable operations, A then B.
The key, operation and receipt identities for A are `key-a`, `operation-a`,
`receipt-a`; B has the corresponding distinct `-b` identities. No key is
recycled. Each fresh request selects all six declared input classes and the
original body. Retrying either retained key selects every input class and
either original or changed body, including a changed body within the same
class. These are the complete declared synthetic requests, not samples of all
runtime payloads. An accepted governed refusal and an unresolved-policy failure
each consume a fresh identity. Unclaimed authentication/admission rejections
are excluded. Exhaustion disables only fresh requests; retries, authorized
status reads and clean restart remain enabled indefinitely.

`receipt-a` and `receipt-b` are formal references to retained receipt objects.
Runtime receipt binding uses the existing `OperationReceipt.operation_id` field.

An attempt is a traversal of a request edge. Its fresh/retry role is finite;
it has no stored counter, UUID or timestamp. The API-423 request occurrence is
a transient preparation identity, distinct from the retained operation/key
and original receipt. The projection discards its value. Equality of those
transient names is never tested by these rules or disclosed by their labels,
so replacing fresh transient names by their role changes neither enabledness,
retry equality, result provenance nor divergence in this declared carrier.
This does not abstract runtime histories containing all such identities.

Every state coordinate has a finite domain in the profile. Ledger length is
0, 1 or 2; entries retain `(input, body, policy-or-none, decision-head,
result-head, outcome)`. Their ordinal selects the distinct key/operation/receipt
mapping. Intent is absent or `(ordinal, input, body, fresh-or-retry)`. Policy
is p0 or p1. Head is h0, h1 or h2; effects are e0, e1 or e2. Caller knowledge
is the two-bit mask k0 through k3 of observed cached results, separate from
the durable ledger. Abstract/concrete phases and gate/capability domains are
also declared. Integers in state maps are ordinals of these named domains.
The carrier is the complete least reachable fixed point of the rules below;
inconsistent ambient products are not additional initial states. Both models
have one initial state: idle, p0, h0, empty ledger, e0 and k0, no intent.

## Context and history boundary

Retry eligibility compares the original request commitment (input **and**
body), the applicable current policy and the current history head against the
retained decision or result head. Participant, episode, actor, authorization
scope, target/run, kind, audience, controller, authority, subject mapping,
action/projection, marking/evidence/provenance, gates, support/downgrade and
transformation/opacity coordinates are fixed by the synthetic fixture and input
class. Their runtime owners are `OperationAdmissionContext`, `_semantic_request()`
and `_require_same_idempotency_replay()`. Changing any of those fixed coordinates
is outside this profile; input-class equality alone is not general runtime
retry equality. Empty keys, migrated legacy claims and sensitive ephemeral
retry proofs are excluded.

The admitted history vector has four constant components (episode, behavior,
control and control-evaluation) and one crossing-batch component. A governed
result batch appends a new opaque crossing head; its decision/result coordinates
are hN/h(N+1). Unresolved policy persists a failed operation without participant
facts, retaining hN/hN. No other history writer is admitted. Within this carrier
each head denotes exactly one distinct vector, so vector equality is equivalent
to head equality; no unequal heads are merged. h2 is reachable only after two
history-advancing results. Policy advancement never changes any head.
There is no saturation, wraparound, deletion or exploration depth limit.

These heads are logical result-batch identities, **not** counts of API-423
occurrences, store revisions, authorization commits or backend effects. Live
authorization/terminalization can use several commits and history components;
their realization requires a separate #972 mapping. This finite construction
claims neither arbitrary sequential repetition nor a quotient theorem for
unlimited runtime histories.

## Independent abstract rules

`multi_abstract.py` owns its policy table and replay predicate. Plain permits;
transform transforms; unsupported is unsupported; forbidden denies;
declassification denies at p0 and declassifies at p1. Unresolved remains an
accepted failed operation with no resolved policy coordinate.

1. Idle enables fresh A, then fresh B, plus all retained-key retries. Requests
   enter offered. Status reads are self-loops. p0 can visibly advance to p1.
2. A retry compares its request/body, applicable policy and recorded head pair.
   Conflict emits only rejection and preserves the ledger. An eligible retry
   observes the retained result and sets the caller's knowledge bit, or loses
   that reply/restarts while preserving prior knowledge. It performs no
   decision, change, delivery, effect or logical commit.
3. A fresh refusal emits deny, unsupported or unresolved and records its result.
   Resolved refusals advance crossing history; unresolved does not.
4. A deliverable fresh result emits permit, then transform/declassify once if
   required, then delivery. Delivery records the logical result and one effect.
5. Responding permits cached-result observation, response loss, or clean restart.
   Each returns to idle. Only observation changes caller knowledge.

## Independent concrete rules

`multi_concrete.py` owns candidate preparation, deny-first selection, claim
matching and commit stages. It imports no abstract policy, replay classifier,
transition function or candidate correspondence.

1. A request enters validation, then policy resolution. Resolved candidates
   resolve effective capability and independent permit/deny gates before claim
   matching. Unresolved resolution proceeds to the safe unresolved outcome.
   These stages assume the admitted current synthetic authority, never a cache
   lookup before authentication. They do not promise zero preparation callbacks.
2. Gating independently compares retained request/context and decision/result
   heads for a retry. It returns the original result, loses that reply/restarts,
   or reports conflict, without record preparation, commit, action execution or
   delivery.
3. Fresh gating selects unresolved, then deny first, unsupported capability,
   transform/declassify or permit. Change emits once before record preparation.
4. Preparation changes no durable coordinate. Atomic commit appends exactly one
   fresh ledger entry; a resolved result advances the crossing-batch head and an
   unresolved result does not. Refusals proceed directly to responding.
5. Deliverable results perform one delivery/effect before responding. Response
   observation, loss and clean restart behave as independent concrete rules.

Hidden rank is validation=6, policy-resolution=5, capability-resolution=4,
gating=3, preparation=2, commit=1 and otherwise=0. Every actual hidden edge
strictly decreases it. Restart, loss, requests, conflicts and reads are visible;
there is no hidden restart loop or fairness assumption.

## Projection, results and bounded failure

Labels identify A/B requests, delivery, rejection and cached outcomes. Input body
values and private context are not visible. Result labels identify the retained
key's original outcome, which fixes original receipt provenance under the
declared identity map. Status labels disclose completed/failed status only;
they do not disclose a delivered participant payload and do not require current
history equality. Thus old-key rejection does not erase authorized status.

Fresh delivery is separate from observing a cached result. These synthetic
labels are the formal result protocol; an action receipt is not an API-406
observation or proof of participant consumption. Actual transport, egress,
supervisory control, directed delivery and inject-dispatch correspondence are
explicit mapping obligations.

Response loss is untimed and occurs only **after durable completion** and any
admitted effect. It makes the attempt's response unknown without inventing a
persisted unknown state or asserting effect absence. A clean P1 service restart
preserves an intact authoritative ledger/history and caller knowledge. Loss or
restart before claim, during an effect, before durable terminalization, corrupt
storage, uncertain commits, INDETERMINATE resolution, reconciliation, cancellation,
late effects and P0 process loss are excluded. The completed-result retry is
safe within the declared exact context; a fresh key may perform the same effect
again. A conflict gives no advice or authorization to rekey a retry.

Only the five original named finite mediation classes become `internal`.
The complete visible alphabet is closed by the profile. Native tau and every
undeclared label are rejected. Projected AUT edges form a set; collisions after
hiding are deduplicated deterministically and projected counts are recorded
separately from semantic counts. Original labels remain in digest-bound maps.

## Assurance and drift

Both independent builders close all admitted transitions without sampled
schedules. Safety caps fail instead of returning prefixes. Export checks
domain membership, initial membership, closure, reachability, independence,
strict AUT readback, exact source/profile identities and artifact counts.
Complete bundles use trusted fixed repository paths and exclusive staged
publication; changed published bytes are never overwritten.

Construction establishes no DPBB result, runtime realization, backend
conformance, noninterference, opacity, latency, throughput, concurrency, handoff,
unlimited-history or universal failure result. Model/profile/projection,
contract or relevant runtime/recovery/source drift invalidates affected current
mapping evidence until reviewed and rechecked. Retained evidence remains tied
to its original source closure; hashes detect drift and do not prove mapping.
The new profile requires its own checking and independent-reproduction evidence.

No production retry behavior, legacy/opt-in/required adoption rule or mandatory
governed check changes. No author annotation, author-time proof, request-path
checker, checker dependency or production store is introduced.
