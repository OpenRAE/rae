# Mixed-control test demonstration

Issue #1018 adds a test harness for RAE.
The harness uses test providers that meet the backend protocols.
It needs no backend distribution, daemon, credentials, or network service.
The [control reference](revised-control-semantics.md) connects these results to current semantics and migration.

## Run the demonstration

Use the repository's frozen Python development environment.
Run these commands from the repository root:

```sh
PYTHONPATH=. uv run --project implementations/python --frozen python implementations/python/tests/mixed_control_demonstration.py collect /tmp/rae-mixed-first
PYTHONPATH=. uv run --project implementations/python --frozen python implementations/python/tests/mixed_control_demonstration.py collect /tmp/rae-mixed-second
PYTHONPATH=. uv run --project implementations/python --frozen python implementations/python/tests/mixed_control_demonstration.py compare /tmp/rae-mixed-first/evidence.json /tmp/rae-mixed-second/evidence.json
```

Select new output directories for each collection.
The command refuses an existing directory before it runs.
Each run writes `evidence.json`. It then removes its test stores.
Each command returns a nonzero exit code if its checks fail.
The check prints both evidence digests and states whether the results agree.

Run the targeted acceptance tests with this command:

```sh
RAES_REQUIREMENT_UID=ASR-537 uv run --project implementations/python --frozen pytest -c implementations/python/pyproject.toml implementations/python/tests/test_issue_1018_mixed_control_demonstration.py -q
```

The source digest covers Python code, test providers, contracts, specs, and the Python lock file.
The collector checks that identity before and after execution.
Evidence files are outside the source roots.

## Executed configuration matrix

| Configuration | Test apparatus | Result required by the demonstration |
| --- | --- | --- |
| Simultaneous mixed execution | Two active component runtimes; separate bridge, clock coordinator, delivery reader, and observation reader | One mapped action executes and reaches participant history. |
| Staged execution | Transfer service with a separate owner reader | The phase advances after transfer and owner readback. |
| Reusable control | One policy-capable target and trusted live-cut resolver | Four control changes commit; exact retry adds nothing; a stale change is rejected. |
| Governed effect | Modular control providers and the existing handoff owner | A controller change agrees with independent history observation. |
| Strict denial | A denying modular provider | No participant action is dispatched. |
| Reusable control with mixed runtime | The same controlled inputs offered together | The unsupported configuration stays explicit. |
| Distributed dispatch with portable mixed services | A shaped dispatcher without worker authority | The unsupported configuration stays explicit. |

The mixed configuration runs both components in one admitted composition.
It does not infer mixed execution from two separate single-component runs.
The control and effect configurations are separate supported paths.
Their passes do not establish joint support with mixed execution.

The source clock uses an affine mapping with scale two.
The incomparable-order case distinguishes that mapping from identity.
The bridge also translates the portable action into `native:contain-host`, a test-only action label.
The destination test runtime records its actual action count.

The complete mixed probe catalog also exercises missing and reversed mappings, undeclared loss, and incomparable clock segments.
It tests refusal before and after a time grant. It tests a refused start, partial effects, lost delivery, and stale transfer.
Each negative case must produce its intended disposition.
An unexpected failure does not count as successful rejection.

## Evidence and comparison

The [retained test record](../../examples/mixed-control-demonstration/record.json)
contains two separately collected runs.
It keeps their source and host facts, stable measurements, operation IDs, stage digests, and full-bundle digests.
Run the commands above to collect full reports and histories locally.
New runs have new IDs and full-bundle digests.
The stable comparison digest identifies the measured behavior for the pinned source and setup.

Each bundle contains the existing validated `BackendConformanceReport` payloads.
The mixed report retains its unsupported combinations and therefore has `passed: false`.
The test command succeeds only when every result matches the fixed demonstration expectations.
It does not change that report's meaning.

The bundle also contains selected observations from the harness stores:

- Participant, episode, run, operation, and invocation identities
- Pinned bindings, time models, mappings, and final clock readback
- Complete retained stage reports and composition histories
- Control histories and operation outcomes
- Bridge starts, translated actions, component action counts, and role-call order.

For denied and invalid-order paths, the test requires zero starts and zero action calls.
It joins report evidence digests to the retained stage and control records.
Execution, delivery, observation, and ownership remain separate facts.
Unavailable delivery retains execution without inventing delivery or observation.

The check compares source and host facts, case coverage, config digests, results, and measured behavior.
Each bundle keeps its own operation IDs and timestamps.
The check rejects reused runs and reports drift.

## Limits

This is bounded RAE test evidence.
The test providers are not operational backend implementations.
The results establish no native qualification, universal backend equivalence, physical timing, or simulation-to-operation transfer.
The second process makes a fresh run with the same test tools.
It does not prove that a second party ran the test.

The broader ASR-537 research protocol retains its own scope and lifecycle.
This test demonstration does not promote that requirement.
