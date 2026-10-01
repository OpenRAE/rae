# Reusable mixed-control compatibility and migration

This is the adoption contract for
[ADR-110](../decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md)
and [MC-01–MC-09](../../specs/formal/participant-semantics/reusable-mixed-control.md).
It publishes rules, not a working migrator, new parser form or wire schema.

## Producer and reader boundary

`mixed-control-policy-occurrence/rev1` identifies the new semantic decision.
Existing `MixedControlTransition` declarations and
`participant-control-occurrence-v1` / wire `1.0.0` retain their fixed-coordinate
interpretation. A suffix is not a stability promise: the current publication
is draft under ADR-061. Historical meaning remains protected regardless.

Adoption requires explicit, closed authoring/compiled and occurrence/snapshot
interpretation discriminants. A new occurrence lineage must carry the changed
meaning; do not reinterpret historical v1 data through optional fields or
default values. Policy revision, semantic pin, wire discriminator, schema hash
and store version remain independently recorded. The following matrix is the
required adoption behavior, not a claim that a new reader already ships:

| Producer artifact | Existing reader | Reader implementing the amendment |
| --- | --- | --- |
| Legacy fixed-coordinate policy and v1 occurrence | Existing semantics/checks | Dispatch to retained legacy interpretation and pinned compiled policy. |
| Explicit reusable-policy or finite-script under the new semantic pin | Reject unsupported form/version | Validate declared form; instantiate fresh exact occurrence coordinates. |
| Revised accepted/rejected occurrence shapes | Reject unsupported lineage | Resolve pinned policy, kind/target/cut and truthful disposition before use. |
| Archive containing episodes of both forms | Reject unsupported episodes for reconstruction; do not reinterpret | Select each episode's exact reader and policy, preserving archive order and evidence. |
| A new live episode with unsupported compiler, runtime or downstream consumer | Refuse admission | Refuse admission until every selected path supports the required semantics/ranges. |

Structural acceptance alone is neither semantic compatibility nor operational
interoperability. Unknown interpretation cannot fall back to the latest reader,
a generic dictionary, a matching version string or ordinary environment inject.

## Authoring conversion

Retaining legacy authoring is a valid compatibility path; it remains finite.
An explicit source-preserving conversion to **finite-script** is permitted only
when every accepted legacy trace constraint is preserved: initial state,
from/to states, kind, controller/authority, targets/proposal links, exact
revisions, order, windows, evidence and finite extent. A unique total order does
not by itself prove a single executable sequence: legacy graph validation can
establish revision pairs along different declarations. If there is no proven
equivalent sequence, stop conversion and require an author decision.

In particular, a converter must reject automatic conversion when:

- an approval/direction also changes controller identity, contrary to the new
  handoff-only transfer rule;
- acting-source and destination-authority joins disagree;
- an order value was implicitly treated as a clock tick without an admitted
  mapping, or a required historical validity/evidence basis is unavailable;
- target identity/revision or finite branch/sequence intent is ambiguous; or
- delivery/control policy identity was conflated by equal revision strings.

An author can explicitly restructure those cases, recording source digest,
decisions and resulting semantic pin. They are semantic changes, not a claimed
equivalent rewrite. A legacy approval that moved control may need separate
handoff and approval applications with separately admitted order/evidence.

Converting a finite declaration to **reusable-policy** always changes the
permitted trace set and requires an explicit author decision. Removing fixed
revisions or copying the same edge into a cycle does not authorize that change.
Do not deduce new authority, clock mappings or future completion receipts.
Keep transformed-proposal lineage and all original source artifacts.

## Occurrences, snapshots and ongoing episodes

Never rewrite historical IDs, actual order, revisions, dispositions, controller
attribution, evidence or markings. Do not renumber an occurrence revision to
match a state revision: the former may count records across rejections and
episodes. V1 non-handoff history can depend on the original compiled transition
for its resulting state; retain that dependency and its content pin.

Historical v1 rejection records keep their original assertions even where the
new rejected-attempt shape can represent more truthful attempted/evaluated
coordinates. Conversion cannot manufacture evidence that an old record omitted.
Old delivery bindings keep their original equality and destination-state rules;
the new source-controller and independent-policy rules do not apply retroactively.

Live policy or interpretation upgrade inside an episode is unsupported. Drain
or terminate through the incumbent lifecycle, preserve indeterminate effects
for reconciliation, then explicitly admit a new episode with the selected
supported policy. Initialization must validate its authority and mark the
predecessor relation; copying a policy address is insufficient. Process recovery
keeps the existing episode and store keys. Exact old retries remain historical
receipt lookups under current access authorization; a new episode does not
create a new namespace for the same principal/operation/client key.

Mixed-episode archives require per-episode pins and complete original context.
An archive reader verifies each episode using its own interpretation. It may
not fabricate a single contiguous controller-state revision across episodes.
If a reader lacks a historical policy, authority/cut evidence or format, it
reports reconstruction as unsupported/unverifiable and preserves the bytes.

## Coordinated adoption and publication

The implementation boundary is one coherent slice across these incumbents:

1. Closed SDL models, safe parsing, semantic references, variable instantiation,
   composition rewriting and deterministic typed compiler children.
2. API-409 occurrence and rejected-attempt carriers/contextual joins, RUN-310
   target eligibility, state fold and exact-cut atomic history/receipt/audit.
3. DSL-142 directed-delivery declarations and actual control-application joins,
   independent disclosure-policy resolution and delivery consumption/evidence.
4. API-423/SEM-233 crossing joins, API-424 effects and range/ref limits, SEM-234
   provider/phase links, conformance readers and runtime snapshot recovery.

Capability admission must reject a selected path that lacks the new semantics;
do not weaken incumbent validators to make it accept new data. In particular,
an ordinary DSL-142 disclosure with identical source/result refs is not silently
converted to an API-424 inject effect requiring a fresh produced result.

Govern all affected embedded schemas, including SDL authoring, instantiated
scenario, instantiated-scenario snapshot, materialized scenario and
satisfiability evidence, plus direct control occurrences and runtime snapshots.
Use the existing publication manifest's per-contract records, `last_change`
hashes, removal tombstones when applicable and `schema_bundle()` parity under
ADR-009/061. No schema is changed or removed by this design delivery; no
deprecation/removal window begins here. No package version or release history
is edited by this decision.

Required adoption evidence includes two cycles through the same compiled edge
in one real episode; all-kind positive/negative contextual validation; exact
concurrent/stale/authority/time/target rejection; finite-script bounds; mixed
archive replay with old policy pins; unchanged legacy fixtures; failed atomic
commit and lost-response retry; and exact directed-delivery joins at the actual
final sink. The bounded design model is not a substitute for those consumer
tests or backend evidence.
