# Executable Participant-Crossing Models

Requirement: SEM-232. Construction package: #971. Classification: FM3.

## Revision and scope

`participant-crossing-dpbb-finite-v1@rev2` is the first executable refinement of
the [rev1 design](participant-crossing-bisimulation.md), selected by ADR-100’s
#971 amendment. Both model revisions
are `rev2`; projection `participant-crossing-projection@rev1` and taxonomy
`raes-behavioral-relations@rev8` retain their exact identities. Rev1 was design
authority, not a previously published executable profile. Its theorem sketch
is not an executed result and its candidate abstraction is not a generator.

The user-approved scope is one fresh operation and its retries. Multiple fresh
operations are a separately revisioned scope in #1395. This authority introduces
no runtime changes, mandatory author annotations, or request-time proof work.

## Complete environment

The published profile declares every domain from the rev1 design, including
the singleton participant, audience, controller, episode and request identity;
cuts p0 and p1; all five input classes; all decision, replay and delivery
values; and history heads h0 through h3. A fresh request is admitted only while
no result has been recorded. It chooses one of the five input classes. The
original input is retained in the terminal state's intent. Identity recycling
and changed-input reuse are excluded environment actions, not unexamined input
samples. Every declared request/cut choice is explored to a reachable fixed
point. There is no depth or schedule bound.

Policy advancement is enabled only at idle or terminal and changes p0 to p1
once. At terminal the only request is a retry of the retained input. A retry
at the recorded cut repeats the outcome observations without another logical
commit. After policy advancement it emits request then replay rejection and
preserves the recorded result. These labels describe the formal outcome
protocol, not repeated backend execution. Mapping receipt replay and actual
delivery to that protocol requires #972 evidence. History advancement caused by
other operations is absent here and must not be equated with policy advancement.

## Abstract rules

State coordinates are phase, current cut, intent, decision, delivery, and last
result. Intent is absent or `(request-0, input-class, requested-cut, replay)`;
last is absent or `(request-0, recorded-cut, decision)`. Initial coordinates
are `(idle, p0, none, none, none, none)`.

The independent abstract authority is `abstract.py`. Its total policy table
selects permit for plain, transform for transform, unsupported for unsupported,
deny for forbidden, and deny/declassify for declassify at p0/p1 respectively.

1. A request enters offered, clears decision/delivery, and preserves last.
2. A stale retry emits `crossing.replay.reject` and returns to terminal,
   restoring the recorded decision and its delivered/withheld outcome.
3. A fresh or same-cut offered request selects the policy or recorded result.
   Deny/unsupported emit their decision label and enter terminal with delivery
   withheld and last set. There is no extra silent completion transition.
4. Every deliverable result emits `crossing.decision.permit` and enters decided.
   Plain permit sets delivery pending immediately. Transform/declassify first
   set delivery none, then emit their corresponding change label and set it
   pending. This prevents repeating a change.
5. Decided with delivery pending emits `crossing.delivery` to delivery-pending.
   That phase emits `crossing.observation` to terminal, delivery delivered,
   recording last if absent. The initial completion and all retries preserve
   the original input for future retry selection.

## Concrete rules

The independent concrete authority is `concrete.py`, derived from API-423
predecessor ordering and RUN-319 validation, policy/capability resolution,
deny-first gates, preparation and atomic commit. It imports no abstract
transition or policy function. State adds gate, capability and history head.
Initial gate/capability are unresolved and head is h0.

1. Request stores intent, resets gate/capability/decision/delivery, and enters
   validating. `internal.validate` enters resolving-cut.
2. A mismatched cut emits replay rejection and restores the recorded outcome.
   Otherwise `internal.resolve-policy-cut` enters resolving-capability.
3. `internal.resolve-capability` sets unsupported only for the unsupported
   input. Independently, forbidden and p0 declassification set gate deny;
   the remaining cases set permit. This closed fixture assumes admitted
   synthetic identity/authority coordinates, not live authentication.
4. Gating selects deny first, then unsupported capability, then the requested
   change or plain permit. Its visible label matches that outcome class.
   A replayed refusal completes immediately. Other results enter preparing-record.
5. Changes emit their visible label once using delivery none/pending. Then
   `internal.prepare-record` enters committing without changing last or head.
6. A fresh result atomically sets last and changes h0 to h1 exactly once via
   `internal.atomic-commit`. Refusals enter terminal; deliverable results remain
   committing with last present. Same-cut retries already have last and skip
   logical commit. Committing with last emits delivery, then observation from
   delivery-pending completes the crossing.

Head denotes one logical atomic result batch, not a count of API-423 records.
h2 and h3 remain in the declared domain but are unreachable: the environment
admits at most one fresh logical result. There is no head saturation or wrap.
The internal rank is validating=6, resolving-cut=5, resolving-capability=4,
gating=3, preparing-record=2, uncommitted committing=1, otherwise=0. Every hidden
edge strictly decreases it, including fresh refusal commits. Visible retry
cycles do not establish hidden divergence.

## Observation and export

The ten visible labels and five hidden classes are exactly those in the
published profile. Only the five named hidden classes become `internal`.
Native tau encodings and every undeclared label are rejected. Both exporters
retain semantic labels and ordinal-to-state maps in digest-bound sidecars.

Terminal denotes completion of one crossing, not global LTS termination.
Success, refusal and stale retry have distinct visible completion sequences;
terminal still enables requests and possibly cut advance. No successful-stop
predicate is inferred from AUT or a sidecar. A missing outgoing edge is a
structural deadlock and is not treated as success. The baseline graphs have no
dead ends; faults introducing them remain observable in subsequent comparison.

State numbers follow deterministic breadth-first discovery from ordinal zero;
successors sort by label and the synthetic dataclass state representation,
edges are unique and sorted by source, label, target. AUT is ASCII with LF and
a final newline. Counts describe exactly the emitted graph. JSON identity uses
the incumbent RFC 8785 canonicalizer; byte digests separately bind AUT and sources.

## Assurance boundary

Construction establishes no equivalence, runtime realization, backend
conformance, noninterference, opacity, timing, probability, concurrency,
controller-handoff, or multi-operation result. Resource exhaustion fails;
partial graphs are never published as complete. Live transformed-ingress
revalidation and every additional runtime gate remain explicit mapping
obligations, not silently projected internal transitions.

Run export in a fresh interpreter from the source checkout. Copied inputs must
match the Python source identities captured from that executing checkout;
rebinding a profile to different source bytes cannot relabel the loaded code.
