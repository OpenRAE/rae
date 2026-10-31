# Participant-Crossing Bisimulation Implementation Program

Date: 2026-07-29

Parent issue: [#811](https://github.com/OpenRAE/rae/issues/811)

Milestone: `Participant Information-Flow & Behavioral Equivalence`

The machine-readable authority is
[`implementation-program.json`](implementation-program.json).

## Definition Delivered By #811

Issue #811 delivers ADR-100, the selected theorem/profile, taxonomy revision
`rev8`, the finite carrier and projection design, the proof-tool and evidence
contract, design-scale witness/mutations, SEM-232 ownership (canonical Ground
Control requirement id `860b0b1e-55cc-42e6-9da8-b7eeeab7172c`), and the
dependency-ordered program.

It does not deliver either executable model, the formal equivalence result,
runtime mapping, backend conformance, noninterference, opacity, or independent
reproduction.

## Dependency Graph

```text
#971 formal models
   |
   v
#972 runtime mapping
   |
   v
#973 counterexamples
   |
   v
#974 finite equivalence check
   | \
   |  v
   | #975 independent reproduction
   |  |
   +--+
      v
#976 scientific/public documentation
```

## Work Packages

### #971: Independent formal models

Implement the complete reachable abstract and concrete finite LTSs from
separate transition authorities. Produce deterministic `.aut` artifacts,
complete counts, digests, drift checks, and closed-profile validation.

### #972: Runtime mapping

Map the live API-423/RUN-319 crossing boundary to the concrete formal model
with differential tests for identity, gates, capability, histories, atomic
commit, idempotency, replay, refusal, and projection.

### #973: Counterexample corpus

Implement the four mandatory mutations: hidden visible denial, added internal
divergence, removed delivery branch, and later-cut replay admitted. Publish
bounded sanitized counterexamples or an independent negative-result check.

### #974: Finite equivalence decision

Acquire and verify mCRL2 `202607.0`, run the fixed
`dpbranching-bisim` command over the complete independently generated inputs,
and publish the model-check binding only when every drift and mutation gate
passes.

### #975: Independent reproduction

Recompute all model, source, tool, profile, count, mutation, result, and
artifact identities from a clean environment. Do not reuse an unreviewed
producer result directory.

### #976: Scientific and public documentation

Only after #974 and #975 produce a positive reproduced result, update
scientific-completeness, assurance fulfillment, lineage, and reader-facing
claim surfaces with the exact profile and limitations.

Delivery status: #971 through #976 are delivered. Issue #976 also separates
each retained record's subject identity from its execution provenance and
retains a separately reviewed qualified reproduction. See the
[evidence identity design](../../decisions/issue-976-crossing-evidence-identity-design.md).

## Program Invariants

- The required relation id is
  `divergence-preserving-branching-bisimulation`, not generic weak
  equivalence; its evidence boundary is the complete named finite profile.
- Both LTSs have independent transition authorities.
- The quantified carrier is complete, finite, and not depth/sample bounded.
- Only five governed mediation classes map to `internal`.
- Formal equivalence, runtime realization, backend conformance,
  noninterference, and opacity remain separate.
- The positive finite result uses the `model-check` assurance axis.
- Models and evidence contain synthetic bounded identifiers and safe digests
  only.
- Public/scientific completion waits for independent reproduction.
