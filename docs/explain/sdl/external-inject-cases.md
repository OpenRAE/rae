# External inject worked cases and evidence

These are semantic cases for [EI-01–EI-06](../../../specs/sdl/external-injects.md),
not proposed SDL or JSON syntax. Each accepted row assumes independently
resolved authority, binding, clock, payload and evidence inputs at its cut.

## Environment and researcher input

An environment declares a compute node and service endpoint, an inject
`release`, and an event `gate` naming it. It declares no agents, behaviors,
scripts or stories. The existing parser/compiler accepts this shape. A
researcher may request one occurrence of `release` against an admitted concrete
binding after `gate`'s assertions hold. The caller is an authenticated operator,
not a synthesized participant or controller. If the realization changes an
authored approval condition, this is a world change; it is not API-409 approval
of a participant proposal. Without an executable realization, triggering is
unsupported even though the declaration is valid.

## Identity, ordering and outcomes

| Request or event | Required result |
| --- | --- |
| `k1/o1`, exact admitted plan/source/input and `host:1`, current head, order 10 | Atomically claim the operation and occurrence; no effect is yet established. |
| Identical authorized retry of `k1` after its original window expires | Return the recorded operation/outcome without re-admission or dispatch. |
| `k1` with changed input, target, run, source or occurrence | Identity conflict; retain the first claim. |
| Another key for `o1`, including another actor | Refuse a second occurrence claim; reveal no other actor's receipt. |
| Fresh key and fresh permitted `o2`, current head, order 20 | May repeat the same authored inject; revalidate every current constraint. |
| External and scheduled contenders share an expected head | Apply trusted order; the later stale request is rejected without rebasing. An unresolved tie has no arrival-selected winner. |
| New occurrence/key reuses a consumed schedule slot | Refuse; fresh naming does not duplicate a scheduled firing. |
| Binding ambiguous after node expansion, unknown event assertion, invalid payload or unmapped clock | Deny before claim; no dispatch. |
| Authority expires, target changes or backend refuses while queued | Withdraw with retained claims and no invocation. |
| Backend proves no effect and cessation for every target | Record effect absence with its evidence; acceptance was not success. |
| Both targets prove application | Record effect-applied with each target's result and readback basis. |
| One applied, one proven absent with residual/cessation evidence | Record known-partial; no atomic fan-out or rollback claim. |
| One applied, one unreported or possibly still running | Record indeterminate aggregate and preserve the known applied result. |
| Effect happens; terminal commit fails or response is lost | Reconcile original attempt under retained claims; never blindly invoke again. |
| Late result names another generation, input or target | Cannot settle the current operation. Preserve uncertainty and investigate through the existing evidence owner. |

Order 10 is not clock tick 10. A temporal window is evaluated in its admitted
domain/clock/segment; script duration normalization retains its existing
whole-second rounding. Neither compiler dependency order nor a queue position
is an execution clock or proof of an effect.

## Participant composition

After `o1` produces result `r1`, an explicit participant binding may disclose
`r1` at its own authorized delivery cut. It must preserve the exact occurrence,
participant/episode, audience, policy, markings and evidence. Ordinary
disclosure of an existing item does not invent a world effect. An API-424
inject effect has its separately required fresh occurrence and produced result.

A direction under reusable edge `direct` binds accepted control application
`c1@1` and its typed target/source-controller authority. A later application
`c2@2` of that edge is different; choosing the latest matching edge is invalid.
The disclosure policy can be `d@7` while the control policy is `p@2`: their
constraints must both hold, not their revision strings match. A different
audience needs its own admitted binding.

Reserve `(c1@1, binding)` before emission. A lost acknowledgement keeps that
reservation; changing the client key cannot emit again. Retrying delivery
cannot re-execute `o1`. A delivery denial leaves `o1` applied. If delivery is
required, composed success and dependent progress remain withheld. A sink
acknowledgement establishes only its admitted delivery fact; participant
observation requires separate evidence. No failed world outcome can be disguised
as a successful result by returning a participant status view.

## What the executable witnesses establish

[`test_issue_1353_external_inject_design.py`](../../../implementations/python/tests/test_issue_1353_external_inject_design.py)
models a single target/run store, fixed resolved inject/source, at most three
claims, two concrete bindings, one attempt per occurrence and a bounded action
alphabet. It exercises claim conflicts, stale order, atomic-write failure,
withdrawal, partial/unknown settlement, immutable terminal results and delivery
reservations. Exhaustive four-action traces check append-only history, immutable
claims and at most one invocation in that projection. It also calls the actual
parser/compiler for the no-participant, no-schedule compatibility witness.

The model receives trusted authorization/clock/resolver/evidence facts. It
does not implement or prove raw ingress, authentication, arbitrary reference
resolution, target interference analysis, distributed scheduling, store crash
durability, backend execution, physical cessation, delivery transport or
observation. The existing DSL-142 and #1351 tests retain their own legacy and
bounded-control evidence. The
[adoption contract](external-inject-compatibility.md) names the required real
consumer tests. Acceptance of this design does not certify those consumers.
