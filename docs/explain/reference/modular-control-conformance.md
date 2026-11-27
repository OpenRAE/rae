# Modular control conformance

ASR-538 publishes a finite runner for the shared runtime boundary.
Install RAES in the backend's test environment.
Import the runner from `raes_conformance.conformance`.
The runner needs no checkout tests or pytest.

```python
from raes_conformance.conformance import (
    backend_conformance_report_payload,
    modular_control_obligations,
    run_modular_control_conformance,
)

def check_target(target, harness):
    report = run_modular_control_conformance(
        target,
        harness=harness,
        obligations=("dependency", "strict-denial", "restart"),
        effect_kinds=("inject", "handoff", "interrupt"),
    )
    payload = backend_conformance_report_payload(report)
    return report.passed, payload
```

The caller selects an authorized test target.
The runner performs real operations on that target.
Use a disposable resource scope approved for the backend's tests.
The runner does not discover, install, download, or connect a backend.
It does not publish reports or load credentials.

## Select the claim

`modular_control_obligations()` returns the installed obligation catalog.
The default run requires the full catalog.
`modular-control-runtime/v2` names this probe suite, not a published backend capability profile.
An explicit `obligations` tuple selects a bounded subset.
Every selected obligation needs at least one case.
Every claimed effect kind also needs an `effect:<kind>` case.
An empty selection, missing case, duplicate case identity, or invalid harness fails.
An empty harness proves no runtime support.

The `authored-recovery` obligation supplies its own bounded SDL cases.
It checks the policy through parse, compile, and public plan steps.
It also checks that unsupported general resume remains refused.
This case performs no backend operation.
It supplies no native retry or checkpoint evidence.

The optional `run_target_conformance` arguments are `modular_control_harness`,
`modular_control_obligations`, and `modular_control_effect_kinds`.
They add the same cases and failures to the existing target report.
Ordinary fixture conformance and the fixture CLI retain their existing claims.
They do not implicitly establish modular runtime conformance.

## Supply installed inputs

Implement `ModularControlHarness.cases(target)` in the backend's test package.
Return a tuple of `ModularControlCase` values from
`raes_conformance.conformance.modular_control_types`.
Use short unique case names.
Use lowercase letters, digits, and identifier marks.

| Case field | Meaning |
| --- | --- |
| `obligation` | One selected catalog obligation or `effect:<kind>`. |
| `participant_address`, `episode_id`, `identity` | Episode start coordinates and the installed caller identity. |
| `options` | Ordinary typed `ControlPlaneOptions`, including exact modular, crossing, inject, and control bindings. |
| `steps` | Bounded `ModularControlStep` inputs for public runtime operations. |
| `expected_compositions` | Independently specified parent dispositions in committed order. Owner evaluations remain separate. |
| `expected_calls` | Exact mutation counts, such as `participant_runtime.admit_action` or `operation_provider.start_operation`. |
| `expected_effects` | Expected logical effect identities and dispositions. |
| `observe` | Independent typed owner readback facts for effect cases. |
| `cleanup` | Resource cleanup that returns residual references; an exception or residue fails the case. |

The runner constructs the runtime and owns dispatch, measurements, and verdicts.
The runner uses a private temporary SQLite store for each case.
Call counts start after episode setup.
`store_root` can select a caller-owned temporary directory.
An admitted `initial_snapshot` can supply a scenario clock and initial state.
Cases cannot replace the runner's store or disable final-sink enforcement.
The `REOPEN` step closes the owner before it opens the same durable store.

Steps cover action admission, v2 selection, control admission, projection,
effect dispatch, inject submission, plan registration, provisioning, and explicit recovery resolution.
A step's arguments are a keyword mapping.
A trusted input factory can derive that mapping from earlier outputs and the live runtime.
Use `expect_refusal=True` only for an expected `PermissionError` or `ValueError`.
An unrelated exception fails the probe.
An unrelated refusal cannot satisfy a negative case.
The runner binds coverage to the reached request, stored decision, or exact refusal audit.

Harnesses, input factories, observers, and cleanup functions are trusted installed code.
They are not sandboxed or accepted from SDL.
Do not compute expected results with the runtime reducer under test.
Do not mutate the target inside an observer or hide operations inside input factories.
Do not use private provider data or secrets as report identifiers.

## Interpret the evidence

Each case's `modular_control` field records its obligation, selected subset,
claimed and excluded effects, artifact digests, support assessments, counts, owner outcomes, and reopen evidence.
It also retains the bound owner readback and its evidence references.
`refusal_causes` records the verified cause for each negative case.
`exact_replays` counts matching inputs with unchanged receipts, claims, budgets, and snapshot.
Restart coverage also requires `replayed_after_reopen`.
Artifact digests bind apparatus, selection, profiles, mechanisms, implementation,
settings, authority, memory, policy, cut, run, trigger, evaluations, and effects when available.
Rejected requests without an evaluation cannot supply evaluation-derived coordinates.
Their missing coordinates are not inferred or invented.

Support records retain required strength, admitted constraints, effective strength, and the checked support relation.
The manifest digest binds the target's separate declarations.
Evidence digests locate the exact committed inputs and outcomes in the case's evidence scope.
A digest supplies no independent authority or authentication.

Effect cases join logical claims to actual owner receipts and separate readback.
Inject cases require a fresh world occurrence and an operation-provider start.
A status view cannot satisfy that check.
Handoff cases observe the actual controller transition.
Cancellation cases distinguish a prevented attempt from accepted control or unknown cessation.
Missing, contradictory, or unbound owner readback facts fail.

Strict denial and invalid authority require zero prohibited mutation calls.
A separate authorized effect can survive denial in a phase case.
It cannot release the denied parent.
Malformed provider values fail closed.
An observer or apparatus failure invalidates the case; it creates no in-world attack classification.
Diagnostics omit raw callback errors and rejected private inputs.

Results are `hermetic-live` runtime evidence, except the `fixture-only` authored-policy case.
This runner always leaves `native_conformance` false.
Native proof needs a bound install, native probes, owner evidence, and host checks.
One backend's selected subset imposes no mechanism parity on another backend.
Finite probes establish no universal assurance, backend equivalence, native resume, or remote exactly-once execution.

## Executable evidence

The portable runner is verified by `test_issue_1071_modular_conformance.py`,
`test_issue_1071_probe_matrix.py`, and `test_issue_1071_effect_conformance.py`.
These cases exercise real shared-runtime admission, world injects, handoff,
cancellation, final-sink refusal, malformed input, support, conflicts, duplicates, and reopen.
`test_corpus_packaging.py` checks the installed public API and corpus without checkout fixture imports in CI.

The detailed #1069, #1361, #1362, #1369, and #1370 regressions remain supplemental evidence.
They cover provider races, state conflicts, lost acknowledgements, cancellation limits,
interrupted outcome commits, and authored policy admission at their owning boundaries.
They supply no concrete backend certification.
