# Participant-Crossing Worked Evidence

Date: 2026-07-29

These are design-scale witness and counterexample obligations. They are not
executed results.

The [#973 architecture preflight](../../decisions/issue-973-crossing-counterexample-preflight.md)
defines the executable corpus boundaries, required reuse, and safe publication
guardrails without changing these historical sketches.

## Positive Witness Sketch

Consider abstract:

```text
a0 -crossing.request-> a1
a1 -crossing.decision.permit-> a2
a2 -crossing.delivery-> a3
a3 -crossing.observation-> a4
```

and concrete:

```text
c0 -crossing.request-> c1
c1 -internal-> c2 -internal-> c3 -internal-> c4
c4 -crossing.decision.permit-> c5
c5 -internal-> c6 -internal-> c7
c7 -crossing.delivery-> c8
c8 -crossing.observation-> c9
```

The candidate relation pairs `a1` with `c1` through `c4`, `a2` with `c5`
through `c7`, and the visible delivery/observation targets. The intermediate
concrete states remain related to the same abstract branching point. The
internal rank decreases, so this path contains no hidden divergence.

This sketch demonstrates the intended relation shape only. It neither
enumerates the complete carrier nor establishes the greatest fixed point.

## Mutation: Hide A Visible Denial

Rename `crossing.decision.deny` to `internal` in the concrete model. A denied
participant-visible occurrence can then disappear. Expected result:
not equivalent. The mutation tests projection discipline, not secret payload
content.

## Mutation: Add Hidden Divergence

Add an `internal` self-loop at concrete policy resolution while leaving the
abstract state nondivergent. Ordinary branching matching may retain the same
finite visible traces, but divergence-preserving branching bisimulation must
fail.

## Mutation: Remove A Delivery Branch

Remove concrete `crossing.delivery` after a permitted transform. The abstract
state retains an enabled visible branch that the concrete state cannot match.
Expected result: not equivalent.

## Mutation: Permit Later-Cut Replay

After `policy.cut.advance`, let the concrete model reuse the `p0` result rather
than emit `crossing.replay.reject`. Expected result: not equivalent because the
visible exact-cut replay behavior differs.

## Safe Counterexample Contract

Each mutation records only safe case ids, state ids, label classes, revisions,
counts, and digests. Raw participant/backend payloads, policy bodies, secret
values, native objects, credentials, host paths, tool tracebacks, and
unbounded stderr are prohibited.

When mCRL2 emits a supported diagnostic formula it is stored in bounded
sanitized form. When an exact divergence failure lacks that artifact, the
negative path is independently checked against the explicit-divergence
condition and bound to the same inputs.
