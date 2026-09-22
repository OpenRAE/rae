# ADR-112: External Inject Triggering and Execution

## Status

accepted

Acceptance takes effect when the delivery PR for
[#1353](https://github.com/OpenRAE/rae/issues/1353) merges. An unmerged copy is
proposed delivery state. This decision accepts semantics and requirement
amendments; it does not declare executable backend adoption complete.

## Date

2026-09-22

## Classification

Classification: FM3

Required artifacts: [state relation and invariants](../../../specs/sdl/external-injects.md),
[worked cases](../../explain/sdl/external-inject-cases.md),
[bounded executable model and tests](../../../implementations/python/tests/test_issue_1353_external_inject_design.py),
[compatibility/adoption contract](../../explain/sdl/external-inject-compatibility.md),
and canonical DSL-111/DSL-142 amendments.

Waivers: production typed-IR/wire-contract and concrete backend conformance
evidence are not claimed by this semantic-design delivery. Existing published
schemas and implementations retain their current behavior. The bounded model
provides design falsification, not runtime, transport or world-effect assurance.

## Context

Ordinary injects can already be authored and compiled without participants.
An inject's entity endpoints are optional paired narrative references. Events
need not belong to a script or story. The existing Orchestrator protocol
installs a plan and returns status/results/history; its reference implementation
records bound/queued resources. None of these facts establishes a fresh
externally requested effect. Participant status-view delivery also provides
no evidence that an inject source executed.

The [preflight](../../explain/sdl/issue-1353-external-inject-triggering-preflight.md)
identifies the missing occurrence/realization contract and the incumbent
parser, compiler, authorization, storage, supervision and evidence owners.
ADR-104 owns durable operations and uncertain outcomes; ADR-110 owns reusable
control occurrences and exact participant-delivery joins.

## Decision

Adopt external-inject-occurrence/rev1 as specified by EI-01–EI-06. Reuse authored
injects and narrative placement; add the semantic boundary between a resolved
admitted binding and a versioned portable invocation/outcome contract. The
shared runtime drives admitted execution; concrete backends realize the effect
and supply validated per-target outcome evidence.

An external request instantiates one inject under exact plan/source, target/run,
input, ordering and precondition bindings. Independent triggers need no
synthetic narrative schedule or participant. Request keys, logical occurrences,
schedule slots and backend attempts retain distinct identities and claims.
Repeated execution requires a fresh permitted occurrence; retries preserve it.
One authoritative order governs scheduled and external inputs, while shared
clock validity remains separate.

Reuse ADR-104 actor-bound authorization, authoritative claims before effects,
atomic terminal state/audit, effect reservations and recovery. Refusal, known
absence, known partial application and indeterminacy remain distinguishable.
No successful no-op, status view or automatic redispatch may stand for a
missing or uncertain world effect.

Compose optional participant disclosure/delivery/observation by exact
occurrence and result identity. Real direction/intervention additionally uses
the exact accepted ADR-110 control occurrence, source-controller authority,
typed target and independent delivery policy. A researcher changing the world
is not thereby a participant controller. Required delivery can withhold
dependent progress without undoing an applied world effect.

## Compatibility and migration

The linked compatibility contract preserves old authoring, fixed narrative
anchors, receipts, snapshots and evidence. Existing ACTIVE requirement status
does not establish implementation of the amendment. Unsupported new readers
or backend capabilities refuse explicitly. Versioned coordinated adoption
covers carriers, manifests, runtime/store/backend and optional participant
consumers; no parser field, schema or endpoint is introduced by this prose.

## Alternatives Considered

- Require a participant/controller for every trigger: excludes valid
  environment-only and researcher world-effect scenarios.
- Treat plan start or participant status delivery as execution: confuses intent
  or disclosure with an evidenced world change.
- Drop legacy schedule anchors or reuse declaration IDs as occurrences:
  changes historical meaning and makes repetitions ambiguous.
- Add an arbitrary command/payload endpoint or another scheduler/store:
  bypasses authored intent and duplicates existing authority.
- Automatically retry uncertain effects: can duplicate irreversible world work.

## Consequences

Authors retain the existing language, while implementers have a portable
identity, admission, execution and evidence boundary. Backends can differ in
realization without silently changing the meaning of acceptance or success.

Executable adoption must demonstrate the specified behavior at real consumers.
This design proves no backend support, liveness, universal rollback, physical
cancellation, participant observation or exactly-once remote execution.
