# Reusable mixed-control worked cases and evidence

These cases instantiate [MC-01–MC-09](../../../specs/formal/participant-semantics/reusable-mixed-control.md)
under [ADR-110](../../decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md).
Names below are semantic notation, not proposed SDL/JSON syntax. Each accepted
row assumes independently resolved authority, scope and evidence at its cut.

## Two cycles under one policy and episode

Policy `P@r1` declares `A` controlled by `self`, `B` controlled by declared agent
`supervisor`, and two handoff permissions `take: A→B`, `return: B→A`. Both agents
have declared, non-widening authority for the controlled participant and target
scope. The policy and both edges remain identical throughout episode `E1`.

| Application / fresh operation key | Edge | Acting controller | Exact prior state | Committed result | Admitted control order | Required completion evidence |
| --- | --- | --- | --- | --- | --- | --- |
| h1 / k1 | take | self | A, 0 | B, 1 | 10 | transfer h1 at its cut |
| h2 / k2 | return | supervisor | B, 1 | A, 2 | 20 | transfer h2 at its cut |
| h3 / k3 | take | self | A, 2 | B, 3 | 30 | transfer h3 at its cut |
| h4 / k4 | return | supervisor | B, 3 | A, 4 | 40 | transfer h4 at its cut |

The old fixed declaration for `take` expects revision 0 and cannot supply h3's
revision 2. The revised permission has no traversal revision; h3 supplies the
exact expected revision itself. Replaying h1 as a *fresh* application after h2
is stale. Retrying k1 with identical content returns h1's receipt without an
application; changing k1's content to h3 conflicts. h1's completion evidence
does not establish completion of h3.

A finite script `[step-1: take, step-2: return]` permits h1 and h2 only. Its
exhausted cursor rejects h3. A script of four explicit steps can permit the
four-row trace. A rejected slot retains its cursor; a corrected fresh request
still needs current authority/validity and an admitted retry budget.

## Same-state facts, proposals and decision conflict

Starting at A,0, a proposal occurrence p1 establishes proposal `q1@1` and A,1.
Handoff h1 moves A,1 to B,2. An approval by B's controller targets **q1@1**,
producing B,3. Proposal revision 1, state revision 3 and history position are
different coordinates. This approval authorizes no execution by itself.

A second denial of q1@1 with a new decision ID is rejected as an already
resolved proposal. Returning to A and taking control again does not reopen
q1. New work uses q2 with its own immutable content/revision; it cannot inherit
q1's approval. A changed proposal uses a fresh identity with explicit source
and transformation provenance. A target that appears only later in an imported
history cannot justify an earlier decision. A same-named proposal in E2 is not
an E1 target. Explicit override/cancellation appends its own eligible fact and
never edits the approval or any action already performed.

## Concurrency, rejection and validity

Two contenders x and y both expect A,2 and the same history head. If the
admitted order establishes x at 30 and y at 40, x can produce B,3; y then
rejects as stale. Reversing HTTP arrival does not change this semantic order.
If the ordering authority cannot resolve a tie, neither contender wins.
Substituting revision 3 into y would be a different request, not revalidation.

The rejection can append a new history record while leaving B,3 and accepted
order 30 unchanged. Its record identifies the attempted old revision/order,
the evaluated current cut, reason and no-state-change result. It creates no
usable proposal or satisfied predecessor. A principal/episode that cannot be
bound safely receives an operation/audit refusal rather than invented
participant evidence.

| Candidate condition | Result |
| --- | --- |
| Source controller is self, but caller has only a supervisor subject binding | Reject controller/subject agreement; destination membership grants nothing. |
| Valid caller role but missing controller grant or widened scope | Reject independently of authentication. |
| Current grant revoked between evaluation and commit | Fence fails; no accepted transition at the old cut. |
| Order 30 in inclusive order window [10,40], trusted tick 900 outside temporal window [100,200] | Reject temporal validity; order 30 is not tick 30. |
| Order at either endpoint and exact clock coordinate at either endpoint | Eligible for those constraints, subject to every other gate. |
| Clock reset to another segment, or unmapped clock domain | Reject unresolved validity; equal numeric ticks do not help. |
| History capacity or selected API-424 count range exhausted | Reject before state advance; no truncation, wrapping or budget reset. |

## Direction, intervention and delivery

At B, a `direct` permission can target a declared eligible proposal, action or
control occurrence; an `intervene` permission can target action, control or
attempt. Both use B's acting controller and preserve its controller identity.
The reusable edge identifies a permission; its two applications d1 and d2 have
different event identities/revisions and evaluated cuts.

Binding L connects one participant, inject I and its original event/script/story
anchor to that permission. The actual delivery D2 must name d2 exactly. Joining
d1 merely because it uses the same edge/controller fails. Joining the destination
authority instead of the acting authority fails when their grant/scope differs.
Authored refs must first resolve to the same canonical compiled identities.

Control policy `P@r1` and disclosure policy `V@r7` may be jointly valid despite
different revision strings. Equal strings on different policy identities prove
nothing. Delivery rechecks V's audience, markings, window, result and final
sink at its own cut. A valid d2 followed by revoked disclosure permission yields
an accepted control fact and a rejected/withheld delivery, not an erased d2.

The pair `(d2,L)` permits one logical delivery. Retrying D2 preserves its
identity and consumption; another D3 cannot spend `(d2,L)` again. Another
control application or separately admitted participant binding is necessary.
A general inject without L remains orchestration input. A disclosure-only L
carries no control authority. Ordinary disclosure may retain item identity;
an API-424 inject effect must create its fresh result and DSL-111 occurrence,
retaining source provenance. Neither a renamed item nor a control receipt is
proof of produced content, delivery or observation.

Independent API-423 delivery/observation evidence must satisfy the declared
basis. Successful serialization alone cannot prove remote acknowledgment or
human observation. If delivery is a required predecessor, the parent remains
withheld until the existing lifecycle can evidence and revalidate it.

## Commit, restart and episode boundary

| Situation | Required interpretation |
| --- | --- |
| Atomic commit fails before h3 is recorded | No h3 state/receipt/history is exposed; a retry may evaluate at the surviving cut. |
| Commit succeeds but response is lost | Identical authorized k3 retry returns the retained receipt; no second transfer. |
| External effect dispatch is indeterminate | Reconcile through the effect owner; a fresh cycle is not evidence that redispatch is safe. |
| Process restarts | Reconstruct E1 and its pinned P@r1; neither revision nor operation keys reset. |
| E1 terminates | No fresh control application; authorized historical reads/retries remain possible. |
| Reset/restart admits E2 with P@r2 | Fresh initial authority/state revision zero, explicit predecessor link, no E1 proposal decisions or cursor. |
| k1 reused with E2 in its request | Conflict under the existing target/run, principal and operation-kind key scope. |
| E1 replay after P@r2 is published | Use retained P@r1 and the historical cuts/evidence. Missing context is unverifiable. |
| Provider/phase handoff or clock replay | Does not establish controller transfer, a fresh episode or renewed causal budgets. |

## Verification and acceptance map

The existing pytest infrastructure runs the finite reference model:

```bash
RAES_REQUIREMENT_UID=ACT-617 implementations/python/.venv/bin/python -m pytest implementations/python/tests/test_issue_1351_mixed_control_design.py -q
```

The initial 27 cases failed with the abstract relation unimplemented. After
implementing it, a second red/green cycle exposed arrival-selected concurrency,
an ambiguous-order winner and coordinate overflow. Review then exposed missing
action/control/attempt target projection; six additional failing cases covered
that gap and a scope-intersection correction. The final 40 cases pass.
The property case enumerates all 64 patterns of six accepted/stale attempts,
checking history-prefix preservation, revision increments and replay continuity.
The ordering case checks both arrival permutations. Window checks exercise
independent order/time endpoints. These finite checks establish no unbounded
theorem or correspondence to the production runtime.

| Issue criterion / canonical amendment | Artifact and evidence |
| --- | --- |
| Separate reusable permissions from occurrence coordinates; retain finite scripts / ACT-617 | MC-01–03, cycle and script tests, first worked case. |
| Exact state, concurrency, authority, validity, retry and episode boundaries / RUN-310 | MC-03–08, stale/authority/window/commit/retry/replay/limit tests and cases above. |
| Portable target/revision/disposition semantics / API-409 | MC-03/05–07, proposal/conflict/target tests; kind matrix and rejected-attempt cases. |
| Direction/intervention bindings without promoting injects or principals / DSL-142 | MC-04/09, exact delivery-join test and delivery cases. |
| Accepted decision, canonical amendments, history and migration | ADR-110, all four requirement files, migration matrix, existing policy and ADR-pin gates. |

The abstract model assumes trusted policy/grant/target resolution, a fixed
target/run, symbolic evidence witnesses and an atomic store. It checks a
handoff/proposal/approval/denial/direction/intervention projection; override,
cancellation, real evidence validation, delivery consumption, audience/flow
enforcement, clock mappings, physical effects and backend behavior are specified
in the cases and normative contract, not implemented by this test model.
The replay projection checks state continuity, not complete historical
authorization. Authentication tests exercise a supplied subject-binding cut,
not the HTTP adapter. Ambiguous-order refusal leaves the abstract state intact;
bounded operational rejection audit is outside that projection.

Every permitted direction/intervention target kind has a positive case and
wrong-kind/revision/episode/identity counterexamples. Control targets are
registered only by accepted model occurrences; action/attempt targets come from
a separate trusted incumbent projection with an availability cut. Future
incumbent targets and rejected control records cannot authorize applications.
The model operates on already validated typed inputs; it is not an ingress
parser or evidence resolver.

The 130 incumbent ACT-617, API-409, RUN-310 and DSL-142 tests pass at the
assessment baseline. They protect the existing fixed-coordinate implementation
and are not evidence that it implements this amendment. Publication pins,
scoped repository/requirement policy and local-link checks protect the design
artifacts; review assesses their semantic completeness.
