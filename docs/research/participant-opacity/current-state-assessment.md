# Participant Opacity Current-State Assessment

Date: 2026-07-29

Issue: [#810](https://github.com/OpenRAE/rae/issues/810)

## Finding

The repository has the carriers needed to define participant-relative
predicate opacity, but it did not previously have the relation, a closed
opacity-profile coordinate, or assurance states that distinguish definition,
model checking, proof, runtime enforcement, backend declaration, realization,
and conformance.

Issue #810 should therefore compose existing authorities and extend the shared
behavioral-relation claim surface. It should not create an opacity-specific
policy engine, observation store, participant history, or backend registry.

## Incumbent Authorities

| Existing authority | Reused contribution | Remaining gap before #810 |
| --- | --- | --- |
| ADR-022 / participant semantics | world truth, participant view, local history, action and observation objects | no selected-secret information-cell condition |
| ADR-054 / participant runtime | observable occurrences, delivery bases, history order, participant hiding | no opacity profile or secret predicate |
| ADR-083 / SEM-220 / SEM-226 | decision surface, exposure, redaction, action and affordance visibility | no rule treating supervisor decisions and omissions as opacity observations |
| ADR-085 / SEM-230 | exact-cut policy, declassification, memory, adaptive strategies, projection, policy noninterference | no one-sided predicate-opacity claim |
| ADR-095 | typed decision epoch, state cut, projection, disclosure, delivery, observation, selection, admission | no whole-information-cell secrecy condition |
| ADR-081 / behavioral relations rev4 | relation vocabulary, dimensions, finite evidence boundary, claim binding | no opacity relation, required relation profile, or independent runtime/backend assurance axes |
| ASR-535 | falsification-first information-flow assurance and claim discipline | no opacity-specific negative cases or evidence lanes |
| RUN-319 | fail-closed participant information-flow mediation and durable decisions | no supported opacity runtime profile |
| API-407 | participant-feature strength, contracts, limitations, and backend evidence | no opacity feature declaration or realization evidence |

## Executable Surface

The Python contract layer already centralizes behavioral-relation definitions
and claim validation. `BehavioralClaimBindingModel` is also embedded in the
experiment-study and scientific-completeness taxonomy contracts. The smallest
coherent contract change is therefore:

1. add an optional paired relation-parameter profile reference and revision;
2. require that pair for relations which declare a profile mandatory;
3. add an optional assurance-axis coordinate and require it for opacity;
4. split relation assurance into independent definition, checker, bounded-test,
   model-check, proof, runtime-enforcement, backend-declaration,
   backend-realization, and backend-conformance states; and
5. regenerate every published schema that embeds the shared binding.

Existing relation bindings remain valid because the new coordinates are
relation-selective. The canonical catalog and its byte-identical fixture must
move together from `rev4` to `rev5`.

## Security Assessment

Payload equality is insufficient. The participant may distinguish worlds
through:

- approval, denial, withholding, edit, deferral, or omission;
- action or affordance presence, order, refresh, and constraint changes;
- delivery, acknowledgement, retry, timeout, cadence, or latency;
- policy/release announcements or behavior at an exact cut;
- participant-visible error and rejection detail; or
- external effects of a hidden supervisor or policy.

The observer projection must contain every channel the selected profile makes
observable. Raw secret values, possible worlds, memory contents, policy bodies,
supervisor internals, and unsafe counterexamples must stay out of portable
artifacts, logs, process arguments, and errors.

## Assurance Assessment

The current repository can provide:

- an accepted formal definition and design decision;
- machine-readable relation and binding validation; and
- bounded structural and finite worked-example tests.

It cannot presently provide:

- an opacity checker over authored profiles;
- exhaustive finite-state exploration;
- an independently checkable theorem;
- reference-runtime opacity enforcement;
- backend capability declaration;
- backend-native realization; or
- bounded backend conformance.

Those outcomes are deliberately assigned to issues #961 through #965.
Nothing in issue #810 advances those assurance states.

## Delivery Update Through #965

The repository now retains exact historical bounded, model-check, and proof
authorities and adds one separate finite runtime-enforcement lane. The
`participant-opacity-runtime-reference-v1` profile binds an individual active
observer to a complete concrete inventory for decision occurrence/content,
failures and declared opportunities, delivery, retry, logical order and timing
buckets, policy/supervisor effects, participant retrieval, and evidence
visibility. RUN-319 persists only safe profile/predicate/inventory/rule refs and
digests on the owning API-423 decision; the full inventory remains in the
trusted runtime-support context. The supported enforcement rule normalizes
every protected crossing to the same denial, releases no payload or participant
state, and commits the withheld delivery opportunity atomically. Catalog
runtime assurance is therefore `partial`; useful allowed-action and delivered-
view modes remain absent.

Issue #965 adds one separately governed API-407 feature declaration for
`participant_predicate_opacity` without making it a policy-operation feature.
The reference backend declares bounded support for
`participant-opacity-runtime-reference-v1@sem-231/runtime-rev2`. The generic
target runner records declaration, backend-native realization, and observed
bounded conformance as three independent shared claim bindings, and binds the
exact manifest, profile, configuration, tool, environment, and probe-set
digests. A complete closed observation transcript covers decision and failure
shape, action availability, delivery and omission, retry, logical timing and
order, release-policy effects, external effects, and payload release.
Adversarial changes, unobserved runtime mediation, stale digests, weakening,
and secret-bearing exceptions all fail closed. This remains finite reference-
backend evidence, not proof, universal opacity, or cross-backend equivalence.

## Correction through issue 1374

The #965 transcript was a fixed harness value. It did not observe crossing,
retry, delivery, or scheduling. The generic runner now derives each transcript
from runtime execution and backend readback. It compares the measured
transcript across points, with the profile normal form, and with the reported
transcript. RUN-319 produces the normal form before any protected backend
effect, so a passing case is runtime-mediated and carries only the declaration
claim. The reference backend is no longer part of RAES. Catalog `rev13`
withdraws the backend declaration, realization, and conformance statuses.

## Recommendation

Adopt the one-sided possibilistic kernel in ADR-099 and the focused formal
specification. Keep `SEM-231` in `DRAFT` while the architecture is established.
Reuse `SEM-230`, `ASR-535`, `RUN-319`, and `API-407` for downstream work, and
execute the child program in its declared dependency order.
