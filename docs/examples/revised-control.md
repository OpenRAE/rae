# Run the revised control examples

These examples execute existing repository tests against controlled providers.
They use actual RAE parsing, planning, runtime admission, stores, and public operations.
They need no backend installation, daemon, credential, or external service.
They are checkout examples, not installed-product commands.

Run each command from the repository root with the frozen Python development environment.
Each command exits nonzero when its assertions fail.
The [support reference](../explain/reference/revised-control-semantics.md) defines the limits of these results.

## Repeat two control edges

The [executable case](../../implementations/python/tests/test_issue_1364_reusable_runtime.py)
uses the compiled policy and trusted cut owner in
[reusable_control_runtime_fixtures.py](../../implementations/python/tests/reusable_control_runtime_fixtures.py).
It initializes one episode, then requests `take`, `return`, `take`, and `return`.
Each request has a fresh key and resolved completion evidence.

```sh
RAES_REQUIREMENT_UID=ASR-537 uv run --project implementations/python --frozen pytest -c implementations/python/pyproject.toml implementations/python/tests/test_issue_1364_reusable_runtime.py::test_four_handoffs_reuse_two_edges_in_one_running_episode implementations/python/tests/test_issue_1364_reusable_runtime.py::test_ordered_contenders_are_evaluated_by_admitted_order_without_rebasing implementations/python/tests/test_issue_1364_reusable_runtime.py::test_process_recovery_replays_the_same_episode_and_exact_retry -q
```

Expected: four successful API-409 v2 occurrences with resulting revisions `[1, 2, 3, 4]`.
The stale contender retains its attempted coordinates and is rejected.
Reopening preserves the episode, and an exact retry adds no transition.
This exercises reusable control alone. It establishes no combined reusable-control/mixed-runtime support.

## Execute an inject without participants

The [executable cases](../../implementations/python/tests/test_issue_1367_inject_execution.py)
install [ExecutingFixture](../../implementations/python/tests/inject_execution_fixtures.py) in a private test directory.
The fixture supplies an authored plan, a concrete node binding, an executing provider, and readback.
The case calls `submit_inject` with the exact trigger request.

```sh
RAES_REQUIREMENT_UID=ASR-537 uv run --project implementations/python --frozen pytest -c implementations/python/pyproject.toml implementations/python/tests/test_issue_1367_inject_execution.py::test_authored_world_effect_without_participants_has_its_own_durable_outcome implementations/python/tests/test_issue_1367_inject_execution.py::test_unverified_readback_never_becomes_success_or_a_participant_result implementations/python/tests/test_issue_1367_inject_execution.py::test_crash_after_world_effect_before_terminal_commit_reopens_without_redispatch -q
```

Expected: the successful case writes and reads the fixture's actual file content.
Its operation succeeds, its outcome is `effect-applied`, and its correlation names the exact occurrence.
Participant results remain empty. An exact retry leaves the provider start count at one.
Unverified readback cannot establish success, and crash recovery cannot redispatch consumed work.
This is a local test effect, not qualification of a deployment backend.

## Preserve authored failure and recovery choices

The [policy examples](../../implementations/python/tests/test_issue_1361_execution_policy.py)
parse complete SDL policies and inspect native plans.
They exercise `terminate`, unsupported continuation choices, and materialized retry evidence.
The [conformance case](../../implementations/python/packages/raes_conformance/conformance/modular_control_policy.py)
independently checks `terminate` and `resume` through parse, compile, and public plan projection.

```sh
RAES_REQUIREMENT_UID=ASR-537 uv run --project implementations/python --frozen pytest -c implementations/python/pyproject.toml implementations/python/tests/test_issue_1361_execution_policy.py::test_explicit_never_repeat_survives_plan_projection implementations/python/tests/test_issue_1361_execution_policy.py::test_unsupported_recovery_is_preserved_and_rejected implementations/python/tests/test_issue_1361_execution_policy.py::test_retry_evidence_is_materialized_in_the_native_requirement implementations/python/tests/test_issue_1071_modular_conformance.py::test_authored_recovery_is_checked_from_sdl_to_plan -q
```

Expected: the requested policy and evidence survive projection.
Unsupported recovery produces an explicit admission diagnostic rather than silently changing the request.
The conformance evidence is `fixture-only`.
These cases perform no native retry or checkpoint resume.
The [recovery guide](../explain/reference/execution-recovery-migration.md) gives the authoring and provider obligations.

## Run simultaneous mixed execution and staged handoff

Use the [mixed-control demonstration](../explain/reference/mixed-control-demonstration.md).
Its runnable collector invokes separate component runtimes, a non-identity mapping, time coordination, and independent readers.
It also exercises refusal, incomparable order, partial effects, lost delivery, and stale handoff.

```sh
RAES_REQUIREMENT_UID=ASR-537 uv run --project implementations/python --frozen pytest -c implementations/python/pyproject.toml implementations/python/tests/test_issue_1018_mixed_control_demonstration.py -q
```

Expected: the fixed matrix matches the observed runtime and store facts.
Denied and invalid-order cases dispatch zero prohibited actions.
Partial effects and missing delivery retain their incomplete outcomes.
Unsupported combinations remain explicit, including reusable control with mixed runtime.
The mixed report therefore retains `passed: false` even when the demonstration checks pass.

For full local reports, run the guide's `collect` commands in two separate processes with new output directories.
Then run its `compare` command.
The [retained record](mixed-control-demonstration/record.json) keeps the prior source pins and bounded comparison evidence.
Do not replace that historical record merely to document it.
Fresh-process agreement establishes no independent-party reproduction, native backend equivalence, or simulation-to-operation transfer.
