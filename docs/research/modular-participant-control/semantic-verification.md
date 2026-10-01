# SEM-235 revision 1: semantic verification

Publication cut: 2026-09-20, issue #1070. Authority:
[`sem-235/rev1`](../../../specs/formal/participant-semantics/modular-participant-control.md).
Architecture lineage: ADR-108 and PC-01–PC-15 at accepted revision
`ebb70a34b8e7d1cc8964c443841ae57e12ed1014`. This record supplements the historical
#1068 design evidence; it does not retrospectively publish those research files.

## Worked publication cases

### A — Teaching influence and a governed inject

Select teaching-influence/rev1, mandatory propagation and session-budget
decision slots, and the admitted hint-followup/1 rule. At K0, H carries
{coached-hint}, retained M carries {worked-example}, and fresh P carries their
union with both source identities. A new episode with retained memory keeps
that union. Both fact and budget slots satisfy their own types; the practice
sink and incumbent gates permit P. Advice cannot supply either mandatory slot.

The rule requests a subsequent reflection-prompt inject. Its own known source
label {} joins P's control influence, yielding both tokens on fresh occurrence
I. At K1, separately resolve teaching authority, addressee, audience projection,
capability and crossing gates, commit its claim and then dispatch. Delivery and
observation remain separately recorded. The reflection may influence a later
proposal; neither a clean prompt source nor reset erases the triggering history.

One firing per root, two total effects, depth two and finite retry/expiry
bounds stop self-triggering. Retry preserves I and the root. A missing source
is unknown, not {}; an exhausted mandatory effect cannot become permission.

### B — Intentional adversarial exposure under SEM-233

Select the unchanged sem-233/rev1 product and its published security-profile
identity. At K0, known declared attacker source A has Conf(A) = {} and
Int(A) = {attacker-influence}. Its observation sink explicitly satisfies that
integrity obligation. After ordinary exact-cut admission and commit, A is
delivered; this is exposure without endorsement. M and fresh P retain that
influence and source lineage. A later action sink accepting no attacker
obligation rejects P even if resource and capability mechanisms permit it.

An admitted adversarial-exposure/1 rule consumes the known influence fact and
requests a fresh evaluator inject. At K1, its supervisor-only projection and
supervisory authority are independently admitted before commit/dispatch. A
subject-facing projection that reveals a hidden condition is withheld; the
supervisor receipt cannot authorize it. Missing labels/source evidence still
fail the incumbent SEM-233 sink predicate. Neither a permissive observation
policy nor a monitor permit discharges an integrity obligation.

The attack is in the admitted world. Replacing the actual tracking engine
outside that world is failed/invalid backend realization, not another portable
attacker occurrence. The finite witness does not instrument that host boundary.

### C–G — Composition counterexamples and recovery

The accepted cases C–G retain their meaning at this publication revision:

| Case | Positive interpretation | Rejected counterexample |
| --- | --- | --- |
| C, advice and review | Optional monitor failure records lost advice; a mandatory assessment slot can feed an admitted review rule. Approval satisfies the predecessor, then parent gates rerun. | Advisory permit overrides mandatory deny; missing required assessment permits release. |
| D, security/capability/budget | All mandatory constraints conjoin; declassification and endorsement affect only their own coordinates and fresh results. | Capability permission erases security refusal; edit/handoff launders influence. |
| E, corrections and resources | Ordered transformations use fresh subjects; delays [10,20] and [15,25] intersect at [15,20]. | Two routes win by arrival order; transforms of the same original compete; disjoint windows pass; shutdown precedes a required live operation. |
| F, stale/restart | Failed expected-head commit makes no claim/call. Same-key replay preserves occurrence identity; changed intent conflicts. Uncertain dispatch stays indeterminate until readback. | New K or retry creates a second effect; commit is reported as delivery; an uncertain non-idempotent call repeats blindly. |
| G, admitted live world | Quota/review are separate prerequisites, target and clock revalidate, backend readback supports realization. | An external credential compromise is relabeled as a successful in-world attack; local persistence proves exactly-once external delivery. |

## Executable evidence and assumptions

Run the finite witnesses and incumbent algebra/projection tests with:

```bash
RAES_REQUIREMENT_UID=SEM-235 implementations/python/.venv/bin/python -m pytest -q \
  implementations/python/tests/test_sem_235_modular_control.py \
  implementations/python/tests/test_sem_235_governance.py \
  implementations/python/tests/test_sem_230_information_flow_control.py \
  implementations/python/tests/test_sem_233_adversarial_boundary_flow.py
```

The new oracle is
[`sem235_modular_control_model.py`](../../../implementations/python/tests/sem235_modular_control_model.py),
used only by tests. It enumerates all 64 triples in the four-element teaching
carrier; mandatory failure statuses and result permutations; selected typed
dependency failures and effect-plan conflicts; and root/depth/per-rule bounds
0–2 over four attempted causal firings. Tests include fresh derivations,
unchanged security sink predicates, symbolic inject claims/dispatch, failed
admission/commit, changed keys, replay and indeterminate/applied outcomes.

This is bounded falsification, not model checking, provider conformance or a
proof of the full transition system. The model assumes trusted exact binding
resolution, authenticated owner results, finite symbolic refs, atomic immutable
states and a correct final invocation fence. It does not parse wire payloads,
run a provider, persist a store, execute a target or prove complete propagation.
It projects policy gates to owner results; real authority and evidence must
still be established by those owners. Effect ordering uses one symbolic rule
node per request in a plan. Cases with multiple slots of one rule require the
full slot-indexed relation of MPC-07 and are not modeled here.

Full time/expiry and resolution-attempt accounting, shared-resource footprints,
predecessor scheduling, durable restart, readback proving absence, concurrent
commit/fence races, all-or-nothing transactions and diagnostic non-recursion
are normative obligations with worked counterexamples, not claimed executable
coverage of this model. Existing #1068 check_design.py supplies complementary
bounded reducer/trigger exploration. API-424/#1072, RUN-320/#1069 and
ASR-538/#1071 own the separate contract, runtime and independent conformance
evidence. No finite result promotes those DRAFT requirements.

## Clause and acceptance map

Every MPC-nn corresponds to PC-nn at the accepted design revision.

| Requirement / acceptance | Formal authority | Evidence and boundary |
| --- | --- | --- |
| SEM-235 exact revisioned profiles, selection and result kinds | MPC-01–03 | Typed-slot/dependency witnesses; trusted binding resolution assumption. |
| SEM-235 closed IFC domain, order, joins, sources and defaults | MPC-04 | Four-element teaching algebra and unknown-source cases; incumbent SEM-233 tests. |
| SEM-235 propagation, memory and explicit release authority | MPC-04/08 | Fresh derivation and retained-memory counterexamples; SEM-233 coordinate-release tests. |
| SEM-235 finite mechanisms, roles, DAG, conjunction and conflicts | MPC-05–07 | Status/permutation/type/dependency tests and route, replacement, delay, lifecycle conflicts. |
| SEM-235 missing/unknown/unsupported/stale/weakened/failure states | MPC-03/06 | Mandatory state matrix and optional advice cases; no silent fallback. |
| SEM-235 independently authorized typed effects | MPC-08/09 | Owner table, cases A–G, refused symbolic inject admission and SEM-230 projection. |
| SEM-235 exact cuts, fresh identity, provenance and visibility | MPC-03/04/08/10 | Fresh derivation, stale cut and failed commit witnesses, cases A/B/F. |
| SEM-235 ordinary downstream admission, idempotency, finite budgets | MPC-10–12 | Re-entry refusal, replay/content conflict, uncertainty and finite causal chain tests. |
| SEM-235 SEM-233 compatibility and backend integrity boundary | MPC-04/14 | Unchanged security model, case B, explicit realization nonclaims. |
| SEM-230 input admission, output projection, disclosure/declassification and transformation | MPC-04/08/09 | Incumbent information-flow-control.md and its tests; new supervisor-only inject projection. |
| SEM-230 observable/hidden labels, policy change, noninterference relation boundary | MPC-03/08/13 | Incumbent exact-cut projection and memory/strategy relation tests; no new universal claim. |
| SEM-233 independent coordinates and conservative carriage across observations, memory, proposals, arguments, transforms, handoffs, crossings, outputs/sinks | MPC-04 | Existing sem-233/rev1 remains normative; unchanged incumbent algebra/carriage tests plus case B. |
| SEM-233 distinct authentication, authorization, admission, approval, releases, redaction and transformation | MPC-08/09 | Existing independent gate/release tests; typed effect authority counterexamples. |
| SEM-233 exact-cut final-sink mediation including cross-participant/episode flows | MPC-04/10 | Existing sink/carry tests plus stale/fenced symbolic dispatch. No new runtime claim. |
| Issue: security and non-security profiles end to end | MPC-04/15 | Cases A/B and their symbolic witnesses. |
| Issue: intentionally deliver adversarial input, retain influence, govern inject | MPC-04/08–11 | Case B, security sink witness, supervisor projection and independent inject admission. |
| Issue: multiple mechanisms with mandatory/advisory/conflict rules | MPC-05–07 | Cases C–E and typed composition/effect tests. |
| Issue: fresh transform/inject with no implicit authority | MPC-04/08–11 | Derivation freshness, transformed sink refusal and inject claim tests. |
| Issue: all absence and weakening states explicit | MPC-03/06 | State table and tests; unresolved applicability differs from false applicability. |
| Issue: revisioned clauses, concepts, lineage, examples, counterexamples, nonclaims | MPC-15 | Approved concept placement; current lineage ledger/prose; this revisioned record; existing policy consumers. |

SEM-235 proposes ACTIVE for semantic fulfillment in the delivery diff.
SEM-230 and SEM-233 retain their ACTIVE statements and incumbent fulfillment.
Repository ownership tests exercise the real policy evaluator and reject
runtime implementation under SEM-235's semantic-publication phase.
