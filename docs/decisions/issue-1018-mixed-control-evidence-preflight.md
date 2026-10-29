# Mixed-control test guardrails

Issue: #1018.

## Scope

This issue tests RAE through backend test harnesses.
The user set this scope on 2026-10-29:
"It's a backend agnostic upstream repo" and
"You're not doing integration tests, you're testing rae".
This scope replaces the initial native-evidence reading of the issue.
No downstream backend work blocks this test.

RAE owns its contracts, shared runtime, and test tools.
Backend authors own native effects, host access, credentials, and cleanup.
Test providers do not prove native support.
Keep the existing `hermetic-live` report basis.

## Existing owners

Use the existing mixed and modular probe runners.
They own the case catalog, expected results, runtime calls, and verdicts.
Use `BackendConformanceReport` and its validator for reports.
Use the existing test harnesses for fresh inputs and controlled failures.
The collector stays in the repository test directory.
Product commands must not import test helpers.

Keep one shared runtime, its store, and its operation ledger.
Do not add another dispatcher, policy engine, clock model, store, or public schema.
The test bundle is a local index of reports and retained test facts.
It is not an experiment record or a new public contract.

## Cases and claims

The mixed case must run both components in one admitted composition.
Two separate runs do not prove mixed support.
Run a staged handoff with a separate owner reader.
Run repeated control changes on the supported single-target path.
Run a governed effect with its own readback.

The runtime refuses reusable control with mixed execution.
It also refuses distributed dispatch with local portable mixed services.
Keep both results explicit in the matrix.
Do not remove either guard or infer joint support from separate passes.

Pin the test source, manifests, profiles, and config digests.
Retain participant, episode, run, operation, and invocation IDs.
Retain the clock mapping, order cut, policy, stage producers, and declared loss.
Use a non-identity mapping with a cut that differs from identity.
Keep execution, delivery, observation, and ownership as separate facts.

Denied and invalid-order paths must have zero prohibited calls.
Compare the report with test-provider counts and state readback.
Missing delivery must retain execution without inventing observation.
Test refusal, stale transfer, partial execution, and lost delivery.
An unexpected failure does not satisfy an expected rejection.

Use fresh stores for the second process.
Keep its new collection and operation IDs.
Compare fixed inputs and measured behavior.
Keep each run's original digests and records.
Reject reused execution, missing cases, config drift, and changed results.
A second process is fresh recollection, not an independent-party study.

## Security and whole-repository checks

| Boundary | Rule |
| --- | --- |
| Inputs | Use the existing SDL, plan, profile, manifest, and service validators. |
| Authority | Keep actor, controller, role, scope, and final-sink checks. |
| Effects | Keep exact-cut admission, mapped order, one-use dispatch, and commit fences. |
| State | Keep store leases, scope checks, atomic commits, retries, and append-only histories. |
| Results | Use existing result checks and report validation. Count actual provider calls. |
| Output | Select portable fields from synthetic test state. Do not dump the environment or raw exceptions. |
| Host | Use no daemon, credentials, backend discovery, or native resource lifecycle. |
| Files | Create a fresh local output root. Refuse to overwrite prior evidence. |
| Workflow | Use targeted local checks. CI owns broad tests and policy suites. |

Source and report digests identify bytes; they grant no trust or authority.
Test providers are trusted parts of this apparatus.
Their results cover only the named cases and inputs.
No result proves universal equivalence, physical timing, or transfer to an operational system.

## Related decisions

ADR-102 owns mixed composition.
ADR-104 owns the shared control plane.
ADR-108 owns modular control and governed effects.
ADR-110 owns reusable control policy and occurrences.
ADR-115 keeps concrete backends outside RAE.
This test follows those decisions and needs no ADR amendment.
