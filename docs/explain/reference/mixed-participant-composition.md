# Mixed participant composition: worked semantic cases

The authority is
[`mixed-cross-backend-participant-control-v1@rev1`](../../../specs/formal/participant-semantics/cross-backend-participant-control.md)
(`sem-234/rev1`). The finite semantic witnesses from #1013 remain separate from
the portable contract published by #1014. Neither is a runnable backend
manifest or evidence that a mixed runtime exists. The semantic oracle is
[sem234_mixed_composition_model.py](../../../implementations/python/tests/sem234_mixed_composition_model.py),
with witnesses in
[test_sem_234_mixed_composition.py](../../../implementations/python/tests/test_sem_234_mixed_composition.py).

## Published portable profile

The normative wire carrier is
[`mixed-participant-composition-profile-v1`](../../../contracts/schemas/plans/mixed-participant-composition-profile-v1.json).
It seals one root containing component identities, compiled-target allocations,
directed edges, cross-clock bindings, mapping loss, evidence obligations, and a
finite phase schedule. Its RFC 8785 digest excludes only the digest field
itself. The profile has no trial or run identity, current phase, retry state,
backend command, HLA/FOM handle, credential, host path, or open metadata map.
Alternative realizations therefore use separate roots and digests; the admitted
trial-plan join owns their separate entry and run identities.

Validation has three explicit stages:

1. Bounded JSON ingress rejects oversized input, duplicate members, non-finite
   numbers, excessive depth or node count, unknown revisions, and non-object
   roots before model construction.
2. Closed model and root-local validation enforce keyed identity equality,
   unique apparatus identities, complete references, one provider per target
   and phase, directed active edges, complete finite phase ordering, mode rules,
   and the canonical root digest.
3. Trusted contextual validation resolves the scenario snapshot, exact compiled
   target kinds, manifest and realization-envelope digests, API-407 feature
   strength per provider, API-423 subjects and policy cuts, time mappings,
   independent authority/controller/routing/disclosure coordinates, evidence,
   and bounded acyclic nested profiles. It performs no I/O, compilation,
   provider selection, repair, dispatch, or mutation.

The root model lives in
[`mixed_composition.py`](../../../implementations/python/packages/raes_contracts/contracts/mixed_composition.py),
with its decomposed local graph checks in
[`mixed_composition_validation.py`](../../../implementations/python/packages/raes_contracts/contracts/mixed_composition_validation.py);
trusted relationship joins live in
[`mixed_composition_resolution.py`](../../../implementations/python/packages/raes_contracts/contracts/mixed_composition_resolution.py).
The generated schema must remain identical to `schema_bundle()`. Positive
and negative fixtures cover alternative, simultaneous-mixed, and staged roots.
Conformance classifies model success as `structural-context-required`: schema
presence or contextual validity does not establish runtime realization,
backend capability, interoperability, transfer, IFC/noninterference,
bisimulation, exactly-once effects, or equivalence.

## Common interpretation

The fixtures hold `scenario:one` and `policy:one` fixed. The trusted compiled
scope interpretation maps `participant.alice` and `action.alice.inspect` to
the same `act` effect, `nodes.target` to `target`, `observations.status` to
`observe`, and `crossings.status` to `cross`. These are illustrative symbolic
addresses, not new public syntax. Sharing an effect across two scope kinds
lets the oracle detect competing providers that a key-only check would miss.

`apparatus:a` declares simulation and `apparatus:b` declares
emulation/operation. Their names carry no realization meaning. Each has its
own clock and an already-resolved effective-support interpretation. The edge
`a → b / crossings.status` binds eight typed identity/revision/digest pins:
adapter, authority, action/observation mapping, participant policy, release
basis, clock mapping, failure behavior and observer profile. It also binds
endpoint clocks and declared loss. Effective support and conformance facts
are trusted finite inputs; a nonempty reference in a real manifest is not proof.

The common cut names Alice, one episode, the selected operator, active
authority, policy revision, capability revision, state revision and history
heads. SEM-230's existing projection model resolves the participant audience.
Provider membership does not create a controller or disclosure permission.

## Four worked realizations

| Case | Allocation and transition | Expected meaning and evidence boundary |
| --- | --- | --- |
| Alternative | One admitted plan assigns all required effects to `a`; another assigns them to `b`. Both hold scenario/policy fixed and have different entry/run identities. | Both satisfy the bounded allocation relation independently. Neither is runtime fallback for the other; no equivalence is inferred. |
| Simultaneous mixed | `a` realizes Alice's action; `b` realizes target state, status observation and the crossing. The directed `a → b` edge resolves its policy/release/time bindings. | One trial has simultaneous distinct forms. The oracle permits the symbolic exchange only after exact-cut admission and projection. |
| Linked inter-trial | The source uses `entry:one/run:one`; the target uses `entry:two/run:two`, with the same scenario/policy and explicit source tuple. | The link records separate trials. A changed scenario/policy cannot masquerade as an alternative of the same input. An emulation-derived simulator additionally needs MCB-029 dataset/model provenance; the link alone does not supply it. |
| Pre-admitted phase | Phase 0 uses `a` and `b`. Phase 1 allocates all four effects to `a`, with `b` inactive. The sealed `trigger:advance` rule commits only after outstanding work is empty. | The provider changes without changing plan, entry, run, controller or prior knowledge. Deactivation is not cleanup. A pinned inactive `b` cannot execute or receive an exchange in phase 1. |

The phase test first delivers `status`, then advances. The returned state
retains that knowledge and the complete history prefix. A reused old cut is
stale. Pending delivery blocks progression; failed storage leaves the entire
state unchanged. The oracle's trigger input represents a trusted admitted
evaluator outcome. It does not implement trigger authentication or evaluation.

## Progressive specification and independent data demand

The #1198 correction and accepted ADR-105 apply to composition:

- A selected abstract action model is complete at that abstraction. A suitable
  realization need not construct OS, package, filesystem or packet details.
- An inherited open scope permits an internal private materialization choice
  while an exact `inspect` action constraint remains binding. A candidate
  changing that action to `attack` is rejected. The private mechanism is not
  an authored catalog entry or a new participant allocation unit.
- The existing finite description relation chooses one supported permitted
  witness. That does not establish universal coverage of every permitted
  completion. Composition adds the joint edge/authority constraints; separate
  per-component witnesses are insufficient when they are mutually inconsistent.
- Choice reports use the requested projection and honestly say
  `backend-selected`. They do not become independent observations or rewrite
  authored constraints. The test supplies the private route in the actual
  selected input and checks that the report omits it.
- Explicit no-experimental-data demand invokes no experimental producer.
  Independently selected exhaustive action demand invokes the finite producer,
  retains only when requested, and does not export by implication. Exact
  scenario constraints never create collection demand.

The test composes the existing #1201 `choose`, `report_choice` and `capture`
oracles; it does not add a second description or evidence engine. The larger
#1201 two-computer/three-action, Linux/Kali and independent-demand acceptance
cases remain in
[partial-description verification](../../research/partial-description/verification.md).
Production preparation and observation admission retain their own negotiated
contracts and capability limits, including refusal of unsupported capture or
export. These model cases do not claim those limits have been lifted.

## Counterexamples and bounded outcomes

| Mutation | Oracle outcome | Preserved boundary |
| --- | --- | --- |
| Remove any edge pin or change its revision/digest | `edge-binding` | No identity or reference existence shortcut |
| Remove the required edge, reverse it, or swap endpoint clocks | `exchange-edge` or `clock-mapping` | Direction and time domains are explicit |
| Assign the overlapping participant/action scopes to different providers | `competing-providers` | Cross-kind scope coverage, not address spelling |
| Remove a required allocation or one provider's support/evidence | `incomplete-allocation`, `unsupported-effect` or `support-evidence` | Another provider's capability does not fill the gap |
| List another form without allocating any effect to it | `mixed-forms` | Membership alone does not realize a mixed composition |
| Add a late component or choose an inactive fallback | `unadmitted-member` or `inactive-provider` | Sealed possible membership differs from active authority |
| Change any expected controller, authority, policy, capability, state or history coordinate | `stale` | Recent timestamps cannot renew the old cut |
| Keep one controller identity but revoke its authority | `inactive-authority` | Identity is not permission |
| Emit secret membership alongside permitted status | `projection-widened` | Metadata is included before output; payload filtering alone is insufficient |
| Borrow another policy or authority with otherwise matching state | `policy-binding` or `authority-binding` | Reference resolution and actual cut binding are distinct |
| Omit the policy decision or use another revision/cut, even with no output | `policy-binding` | Empty projection is not exchange authorization |
| Supply incomparable events or cyclic order | `unresolved-order` or `invalid-order` | No timestamp or arrival-order tie-break |
| Declare coarsened timing without admitted loss | `unadmitted-loss` | Explicit weaker claims cannot satisfy stronger required comparisons |
| Fail commit | `commit-failed`, identical state | No symbolic effect or invented durable failure history |
| Commit an attempt with failed/unknown result | attempt recorded, knowledge unchanged | Commit/attempt is not delivery |
| Advance with outstanding work or an unknown trigger | `in-flight` or `unadmitted-trigger` | No hidden drain, cancellation or phase selection |
| Exceed the finite graph/order budget | `work-limit` | Whole refusal, never truncated admission |

All eight combinations of control-loop, world-assumption and membership axes
are independently admitted when otherwise valid. Closed-loop still needs
action admission. Bounded-open-world does not supply an unknown mapping, and
neither axis determines materialization delegation or observation demand.
Permutation tests check that allocation enumeration is not a scheduling input.

## Clause and assurance matrix

Every row is a definition in the normative specification. Executable evidence
below is finite falsification of the named relation, not full production
fulfillment of the corresponding invariant family.

| Clauses / owner | Definition and executable evidence | Limits |
| --- | --- | --- |
| SEM-234(1–2), MCB-001–009 | `admit`; alternative/mixed, all five scope kinds, support, overlap and permutation tests | Trusted compiled scopes/effective support; no trial compiler change |
| SEM-234(3), MCB-010–012 | Edge pin, endpoint, exchange and clock checks; mutation tests for every pin kind | Flat resolved graph only; no nested-profile resolver or artifact-content verification |
| SEM-234(4), MCB-013–022 | Exact cut, policy/authority joins, existing SEM-230 projection; metadata, revocation and single-controller tests | No provider handshake, new RUN-310 protocol or noninterference proof |
| SEM-234(5), MCB-027–034 | `advance` and `link_trials`; changed provider, immutable identity, stale/pending/commit and history tests | Synthetic result and trigger facts; no cleanup or derived-model realization |
| SEM-234(6), MCB-035–037 | Cartesian axis cases and open-loop actuation refusal | Not description closure or a backend/product catalog |
| SEM-234(7), MCB-023–026, 038–041 | Directed partial-order closure, fresh cuts, explicit loss, refusal and commit tests | Not a clock synchronizer, runtime final sink or distributed transaction |
| MCB-042–045 / ASR-537 | Demonstration and separate-claim definitions; source/nonclaim policy checks | No executed apparatus demonstration, universal transfer, proof or backend conformance result |
| SEM-230 | Existing `project_history`/crossing decisions plus `test_sem_230_information_flow_control.py` | Retains admission, output projection, release, transformation, hidden/visible labels, policy change and quantified claim boundary |
| SCE-002 | `test_sce_002_trial_compiler.py` and immutable phase-plan tests | Incumbent composition/parameterization/randomization are reused; mixed compilation is not claimed |
| API-423 | `test_api_423_participant_crossing_contracts.py` plus edge policy/authority tests | Preserves typed ingress/egress, transformations, disclosure, intervention/inject stage lineage and out-of-line evidence; no generic transport |
| RUN-310 | `test_run_310_supervisory_lifecycle.py`, `test_api_409_participant_control_occurrences.py` and `test_issue_1003_final_sink_flow_enforcement.py` | Incumbent supervision, denial, direction, intervention, handoff, override, cancellation, conflict/idempotency and append-only history; not mixed-runtime execution |
| #1198 clarification | Existing description/lifecycle oracles composed by the new test | No mandatory internal recipe, universal capability or implied collection claim |

## Lineage and nonclaims

Reuse the [edition-pinned #813 source assessment](../../research/cross-backend-participant-control/prior-art-and-design-criteria.md)
and [lineage mapping](../sdl/lineage.md#mixed-simulation-emulation-and-operational-composition).
HLA contributes ownership/time-service precedents; NIST/co-simulation work
contributes explicit coupling and bridge boundaries; cyber-range work motivates
separating transfer evidence from equivalence. ADR-105 supplies the correction
for recursive constraints, supported witnesses and independent observation
demand. No new source-derived API, product vocabulary or compatibility is adopted.

The repository lineage, behavioral-claim, semantic-coverage and assurance
gates check publication consistency. The #813 structural test still checks the
historical design program. Neither these gates nor the finite oracle establishes
runtime enforcement, backend realization, interoperability, leases, simultaneous
scoped/joint control, IFC/noninterference, equivalence or universal transfer.
SEM-234's definition can be ACTIVE while ASR-537's demonstration stays DRAFT.
