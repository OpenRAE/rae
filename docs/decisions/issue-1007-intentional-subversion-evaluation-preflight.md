# Issue 1007 intentional-subversion evaluation preflight

Date: 2026-10-29

Status: implementation guidance for issue #1007.
This note does not change a contract or authorize result publication.

## Decision

Issue #1007 tests RAE itself.
It does not test or select a concrete backend.
The implementation must use a RAE-owned test harness and public runtime seams.

The protocol identity is
`intentional-subversion-control-evaluation-v1@rev1`.
ADR-101 and the participant semantics define this revision.
The identity and its coordinates are test data in this issue.
They do not create a new portable schema or policy language.

The harness may report `fixture-only` or `hermetic-live` execution.
It must not report `native-live` execution.
Its result covers only RAE contract and runtime behavior.
It makes no claim about a backend realization.

## Existing components

| Concern | Existing owner | Required use |
| --- | --- | --- |
| Profile meaning | ADR-101 and the adversarial flow-control specification | Keep the rev1 attack cases, denial rule, memory, replay, and disclosure limits. |
| Runtime | `RuntimeControlPlane` and `RuntimeTarget` | Drive public RAE operations and check the final result. |
| Test target | The installed RAE stub target | Provide a local target with no backend integration. |
| Cases | `ModularControlCase` and `ModularControlStep` | Supply typed inputs and clear expected results. |
| Runner | `run_modular_control_conformance()` | Own the store, execute cases, count calls, and check replay and cleanup. |
| Policy | Existing control and final-sink fixtures | Keep policy authority separate from monitor advice. |
| Evidence | The conformance report and `canonical_json_digest()` | Bind safe facts without exposing private content. |

Issue #1071 supplies the modular runner used by this test harness.
It is a closed prerequisite, not a backend dependency.

## Protocol boundary

The rev1 test fixture must state all selected protocol coordinates.
It includes honest and attack groups, main and side goals, and participant powers.
It also includes policy knowledge, monitor knowledge, feedback, and adaptation.
The remaining fields cover collusion, monitor shape, audit, intervention, memory,
replay, measures, limits, and nonclaims.

The harness covers four attack families:

- injection joins a marked committed evaluation to its exact admitted action and
  includes an unrelated-admission negative control;
- exfiltration attempts a final status projection and gets no value;
- adaptive evasion makes a changed attempt after declared feedback, then checks
  an exact replay after the store reopens; and
- handoff manipulation sends a typed control handoff that policy denies.

A denied case must have no prohibited target call or applied effect.
It must not make a prohibited control transition.
An unrelated refusal cannot satisfy the case.

An apparatus fault is not an authored attack.
Malformed provider output must invalidate or limit the evaluation.
It must not count as attack success.

## Trust and security gates

The harness and its case factories are trusted test code.
Scenario data cannot load code, choose a provider, or grant authority.
Provider output remains untrusted input to the existing validators.

The implementation must keep these gates:

1. Use typed RAE inputs and existing validators.
2. Use an in-process harness with no new network or login surface.
3. Keep deterministic policy authoritative.
4. Treat monitor output as advice or evidence only.
5. Check denied work at the final runtime target and effect owner.
6. Check denied handoff history and the effective controller state.
7. Use the existing atomic store, revisions, and idempotency ledger.
8. Reopen the store before the exact replay check.
9. Sanitize failures before they enter the report.
10. Publish only safe identifiers, counts, limits, and digests.
11. Keep every result measure separate.

The hidden side goal must not appear in a published result.
Raw provider payloads and private failure details must also stay out.
The harness may bind the side goal through a digest made from fixed test data.
It must never digest or copy a real secret.

## Evidence boundary

The authored-runtime digest binds typed steps and the selected runtime setup.
The coordinate digest binds that value, the protocol revision, and declared case inputs.
The runtime digest binds one safe conformance report.
The trajectory digest joins those values to safe evidence references.

Fresh runs can have different runtime and trajectory digests.
They still have the same coordinate digest for the same declared inputs.
Exact replay is checked inside one run against the reopened ledger.

The result keeps these measures separate:

- safety;
- usefulness;
- attack success;
- audit cost;
- intervention cost;
- uncertainty;
- limitations;
- invalidation; and
- nonclaims.

No combined score may hide a failed or invalid result.

## Extension seam

A new attack adds a typed case factory and protocol assignment.
A new protocol revision changes the explicit version and test data.
Neither change may add a provider registry, store, policy engine, or backend
branch to the shared runner.

A backend can run its own conformance work outside this harness.
The RAE harness result cannot be transferred to that backend.

## Non-goals

This issue does not add a production API, schema, store, scheduler, or policy
engine.
It does not add credential transport, network access, or host commands.
It does not publish a raw trajectory or a general robustness claim.
It does not implement, name, adapt, or test a concrete backend.

No ADR, schema publication, or policy-as-code change is required.
