# Modular control probe guardrails

This note binds ASR-538 and issue #1071.
The first review used commit `8d733a4fe668b6823f2016888aea315e0ea34ebd`.
ASR-538 was DRAFT at that cut.
This note records design rules, not an achieved result or a work plan.

## Existing decisions

The following ADRs already assign each owner:

- [ADR-108](adrs/adr-108-modular-participant-control-and-governed-effects.md): modular control and governed effects.
- [ADR-111](adrs/adr-111-control-applicability-and-effect-decisions.md): applicable subsets, coverage, and phase decisions.
- [ADR-112](adrs/adr-112-external-inject-triggering-and-execution.md): actual world injects and their evidence.
- [ADR-113](adrs/adr-113-reusable-execution-machinery.md): one-use native calls, control, and recovery.
- [ADR-114](adrs/adr-114-ifc-profile-variability-and-publication.md): exact IFC profiles and support.
- [ADR-115](adrs/adr-115-concrete-backends-owned-outside-raes.md): separate backend ownership.

No new ADR, policy engine, provider host, or backend belongs in this change.
The diagnosis at `077f7d04:docs/research/runtime-refactor/diagnosis.md` describes that earlier source cut.

## Reuse the current owners

Use the installed `raes_conformance.conformance` API and its existing report types.
Use `RuntimeTarget` and typed runtime settings.
Keep contract validity, runtime behavior, installed providers, backend claims, native effects, and experiment results separate.
No weaker result implies the next claim.
ASR-535, ASR-536, and ASR-537 retain their own scope.

The current participant-policy probes supply a useful split between inputs and verdicts.
They do not cover this issue unchanged.
They disable the final-sink gate and lack a modular-control binding.
Their inject case sends a status view.
That case does not execute a world inject.
Their counter also omits the operation provider.
The fixture CLI checks contracts; it cannot claim live runtime coverage.

## Required finite probes

| Boundary | Evidence required |
| --- | --- |
| Applicable subset | Retain the full apparatus. Derive the active subset at the exact cut. Cover applies, proven absence, and unresolved coverage. Empty work needs complete proof of absence. |
| Dependencies | Drive A.fact → B.assessment → A.rule. Supply exact detached inputs. Missing, stale, or wrong input must block a dependent call. |
| State | Check shared-state order and conflicting writers. Refusal cannot commit state reserved for parent success. |
| Optional work | A truly optional failure loses advice. It gains no veto, state, permission, or effect. Required advice can block missing work but gains no veto. |
| Support | Compare each admitted strength and constraint with current support. Bounded support needs the exact admitted relation. It is no blanket downgrade. |
| Decisions | Deny and withhold block the parent in every phase. Parent decisions precede effect scheduling. Order cannot resolve conflicting outputs. Check combined dependency cycles. |
| Effects | Each claimed kind must use its actual public owner. Cover a world inject, control change, cancellation/refusal, and a non-IFC mechanism. Non-IFC methods need no fabricated label. |
| Final release | Denial permits no prohibited call, mutation, or disclosure. A separate authorized consequence can survive denial but cannot release the parent. Cover v2 selection with the original caller. Cover API-423 permit followed by final-sink refusal. |
| Cancellation | Join the exact target, attempt, control, revision, and response. Cover prevention, completion winning, partial effects, refusal, and unknown cessation. Accepted control proves no rollback or cessation. |
| Recovery | Preserve authored policy through parse, compile, plan, admission, and invocation. Check exact retry, changed content, stale authority, commit failure, and lost reply. Reopen must retain identities, reservations, budgets, and outcomes. |
| Owner readback | Match durable outcomes to separate owner facts. Missing, stale, or conflicting facts cannot establish an applied effect. Count effects separately from safe readback. |
| Integrity | An apparatus failure invalidates the evidence. It must not become an in-world attack result. |

General native resume is still refused by the current policy capability checks.
A retained effect continuation proves no native checkpoint or general resume support.
New trials, resets, and compensation each need their own authority.

## Trust and security rules

Use the current parser, compiler, planner, and complete-policy resolution.
Use `ContractModel`, bounded JSON ingress, typed operation contracts, and snapshot limits.
Revalidate detached callback values.
Use API-424 contextual checks, exact stage bindings, and exact schema pins.
Keep the published profile and manifest corpora as the sole contract authority.
No runner-local schema or capability registry is needed.

Keep original actor, audience, target, run, and current owner authority.
A drain caller cannot lend its rights to an effect.
A result key grants no read access.
Keep API auth, size limits, role checks, and bounded offload for served claims.
Do not bypass a component restriction or disable a gate to make a case pass.

Reuse the mutation fence, one-use invocation ledger, atomic store, and snapshot CAS.
Make callbacks outside writer permits and store transactions.
Recheck the cut and generation after each callback.
Use finite call budgets and event barriers rather than sleeps.
A timeout does not prove that an external effect stopped.
Use `TimeCoordinator` for scenario time.

Keep private store files, owner leases, and normal close/reopen paths.
Do not edit live SQLite bytes or rewrite terminal history.
Failed commit dispatches nothing.
Unknown work needs trusted recovery evidence; it must not repeat blindly.
Memory-only tests prove no process-loss durability.
Additional stores and profiles need their own executed cases.

Keep secret references, environment classes, and literal/`value_from` checks.
Never read host credentials for a probe.
Do not put secrets in argv, URLs, logs, reports, or errors.
Use safe diagnostics, existing response envelopes, and actor-bound audit.
Keep telemetry, audit, participant disclosure, and experiment evidence separate.
Use secret sentinels to check callback and cleanup failures.

The harness is trusted installed code, not a sandbox or an SDL callback.
It supplies inputs and separate evidence sources.
The runner owns dispatch, counts, coverage, and verdicts.
Each case needs an approved resource scope and cleanup plan.
Keep cleanup failure and unknown residue visible.
No new service, remote fixture source, or data transfer is authorized.

## Report and package rules

Use `ConformanceCaseResult`, `BackendConformanceReport`, and their current validator and serializer.
Bind each case to its exact subset and artifact digests.
Retain declared, admitted, and effective support as distinct facts.
Retain effect, authority, policy, memory, cut, and limitation identities.
A hash adds no authority.
Missing, skipped, unsupported, or failed required coverage prevents a subset pass.
Show excluded subsets without claiming them.
Finite synthetic execution is `hermetic-live`, never native certification.
One native case cannot certify a whole subset.
Keep the existing declaration → realization → conformance claim checks.

The runner must work from an installed wheel without checkout tests, `PYTHONPATH`, or developer credentials.
Reuse corpus resources, build hooks, facade checks, and installed-package CI tests.
Another backend supplies its own bindings and readback.
It must not need a backend-name branch or another dispatcher.
Detailed existing #1069, #1361, #1362, #1369, and #1370 tests remain useful regressions.
Source-only fixtures are not a downstream API.

## Workflow rules

Use `.ground-control.yaml`, `.gc/plan-rules.md`, and current repository tooling.
Set `RAES_REQUIREMENT_UID=ASR-538` on an issue-number branch.
Keep implementation and test traceability with that requirement.
Run only targeted local checks.
Full, integration, fuzz, build/install, and completion suites remain in CI/CD.
Preserve module boundaries, source-size gates, release-owned versions, and immutable research records.

This work grants no universal security, backend equivalence, rollback, or remote exactly-once claim.
It does not implement missing providers, effects, or general resume.
A failed invariant remains an open product finding.
Do not weaken an expected result or turn a probe change into a runtime redesign.
