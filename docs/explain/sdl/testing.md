# SDL testing

Use this guide to select tests for an SDL change.
Complete [contributor setup](../../../CONTRIBUTING.md#set-up-the-repository) first.
Run the commands below from the repository root.
Full suites run in CI/CD only.

## Testing ladder

Select the smallest test that can detect a wrong result.
Use the [coding standards](../reference/coding-standards.md) to classify the change.

1. Use unit tests for parser, model, validator, compiler, and planner behavior.
2. Use property tests for generated inputs and invariants.
3. Use named invariant tests for references, graphs, visibility, and portability.
4. Use the required formal artifacts for the applicable FM level.

Formal tools are outside the ordinary local loop.
The canonical CI graph owns proof replay and its required gate.
See `.github/workflows/canonical-verification.yml` for its current jobs.

## Test suites

### Unit tests (standard run)

For parser or validator changes, select the relevant modules:

```shell
uv run --project implementations/python --frozen pytest implementations/python/tests/test_sdl_models.py implementations/python/tests/test_sdl_validator.py implementations/python/tests/test_sdl_parser.py -q
```

These modules check source decoding, models, references, shorthand, and source-format limits.
Add a pytest node id after the module path to select one case.
Exit `0` means the selected cases passed.
It does not qualify a backend or establish complete requirement coverage.

### Stress tests (standard run)

For a change that affects combined SDL structures, select the relevant module:

```shell
uv run --project implementations/python --frozen pytest implementations/python/tests/test_sdl_stress.py implementations/python/tests/test_sdl_realworld.py -q
```

These fixtures combine infrastructure, objectives, workflows, agents, and teams.
They test the authored structures supported by the current code.
They do not prove production execution or coverage of absent contracts.
Use the case names and fixture definitions as the current scenario inventory.

### Fuzz tests (manual trigger only)

CI runs the `fuzz` nox session with Hypothesis.
The default pytest marker expression excludes fuzz and integration tests.
Do not run fuzz or integration suites locally.
For a regression, select a relevant deterministic case from the owning module.
The parser must return a valid `Scenario` or its documented parse or validation error.

### Full suite

The canonical verification workflow owns full test selection and coverage reduction.
Use the [development workflow](../../DEVELOPMENT_WORKFLOW.md#run-verification) for targeted local commands.
A passing local module does not establish full-suite coverage.

### Example scenarios

Reusable SDL files live in `examples/scenarios/`.
The disk-backed example check is:

```shell
uv run --project implementations/python --frozen pytest implementations/python/tests/test_example_schema_conformance.py -q
```

This module checks strict source decoding and direct validation against the published authoring schema.
It also checks parser serialization against that schema.
`test_scenarios.py` covers loader failures and selected example properties.
The source-profile corpus lives in `contracts/fixtures/sdl/sdl-yaml-v1/`.
The [complex scenario briefs](complex-scenarios.md) explain example design.

A valid example is an authoring input.
It does not prove native deployment or experiment validity.
Exposure, evidence, and participant claims need their own named checks.

## Adding new scenarios

Use the corpus that matches the artifact:

- Put reusable positive examples in `examples/scenarios/*.sdl.yaml`.
- Keep synthetic fixtures in their owning stress or topology test modules.
- Put parser-negative specimens in `implementations/python/tests/data/sdl/invalid/`.
- Keep other refusal cases beside the rule they test.

Do not put invalid SDL in the positive example corpus.
Use `load_scenario()` or `parse_sdl()` for scenario loading.
These boundaries perform source checks, model validation, semantic validation, and advisory handling.
Preserve their documented error types.
Reuse the owning test's path helper when another test needs the same corpus.
Do not create a second corpus root or discovery schema.
