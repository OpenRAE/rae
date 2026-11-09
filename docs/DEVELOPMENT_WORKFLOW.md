# Development workflow

Use this guide to select a local check and investigate its failure.
Start with [contributor setup](../CONTRIBUTING.md#set-up-the-repository).
Use the [coding rules](explain/reference/coding-standards.md) for exact implementation requirements.
Use the [runtime architecture](explain/sdl/runtime-architecture.md) to understand component ownership.
Use the [release guide](explain/releasing.md) for release authorization and automation.

## Install the locked environment

From the repository root:

```shell
uv sync --project implementations/python --all-extras --frozen
uv sync --project implementations/tooling/python --frozen --no-default-groups
```

An optional [development container](explain/development-container.md) performs
this setup for you on Linux x86_64. That page labels each start route verified
or unverified. It cannot run the proof lane; continuous integration does.

## Run verification

Run only targeted checks locally.
Full test, integration, fuzz, proof, and completion suites run in CI/CD.
Run the changed-file path from the repository root:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups nox -f noxfile.py -s verify-fast-feedback
```

`verify-fast-feedback` is also the default nox session.
`verify-changed` and `verify-completion` use the same targeted path.
Unknown changes never authorize a full local suite.
Select relevant modules or cases explicitly when changed tests do not cover the behavior.
For example, check runtime-model changes with:

```shell
uv run --project implementations/python --frozen pytest implementations/python/tests/test_runtime_models.py -q
```

For prose, give the existing writing stage the changed paths:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups nox -s docs-prose -- CONTRIBUTING.md
```

Replace `CONTRIBUTING.md` with your changed Markdown or reStructuredText files.
Exit `0` means that the selected checks passed.
It does not establish full STE conformance or deployed backend behavior.
Follow the [writing guide](explain/reference/documentation-style-guide.md) for meaning and rendered review.
Full documentation and external link checks run in CI.

## Debug a failed check

1. Record the commit with `git rev-parse HEAD`.
2. Read the failed stage and its diagnostic before editing code or policy.
3. For a test failure, select its exact module or pytest node id.
4. For a prose failure, rerun `docs-prose` with that file.
5. Correct the cause and repeat the same targeted check.

Do not clear a failure by weakening a lock, trust boundary, or policy baseline.
For missing tools or digest failures, use the [tooling reference](../implementations/tooling/README.md).
For exception handling and safe diagnostics, use [exceptions and logging](develop/exceptions-and-logging.md).
Remove credentials and private content before attaching diagnostic output.
Report ordinary problems through [SUPPORT.md](../SUPPORT.md).
Report vulnerabilities privately through [SECURITY.md](../SECURITY.md).

## Respect package boundaries

`tools/policy/adr_policy.yaml` defines the public import facades allowed across
RAES packages. Adapters import owning domain APIs only through those listed
facades and never through private modules. The semantic CLI calls SDL compilation through `raes_processor.compiler`.
Extend that public facade for another CLI/compiler interaction.
Do not import compiler internals or duplicate compiler behavior in `raes_cli`.

After a cross-package import change, run the relevant structural check:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups python tools/check_repo_policy.py --check-set structural
```

## Keep the structural ratchets

The structural check enforces the rules of
[ADR-117](decisions/adrs/adr-117-ratcheted-structural-checks.md) on package source. They fail on a new import cycle, a new private import from another
module and a new class with more than seven package ancestors. The recorded debt is in `tools/policy/import_contracts.toml` and
`tools/policy/structural_baseline.json`. The debt can only decrease:

- Do not add an entry to clear a failure. Remove the new import or the new
  inheritance.
- When a change removes debt, remove or lower its entry in the same change. The
  failure message names the entry.

To run only the import contracts, run this command from
`implementations/python/packages`:

```shell
uv run --project ../../tooling/python --frozen --no-default-groups lint-imports --config ../../../tools/policy/import_contracts.toml --no-cache
```

## Continuous integration graph

The pull-request gate runs through `.github/workflows/ci.yml`, which calls the
reusable `.github/workflows/canonical-verification.yml`. That reusable graph is
the single exact-SHA full gate for pull requests, protected branches, and
release verification.

The reusable graph splits the default-marker tests across four deterministic shards.
The `test-shard` indices are 0–3. Each shard owns a SHA-256
partition of the collected pytest node ids (`tools/pytest_shard.py`); there is no
per-module shard table. Alongside the shards, the `integration`, `checks`
(hygiene, policy, lint, contracts, docs), and `proof` jobs run in parallel.

The `coverage-reduce` job proves the shard manifests form a complete, disjoint partition of a freshly collected suite.
It combines shard and integration coverage.
It enforces the 90% line floor (ADR-103).

SonarCloud runs inside the same graph
as soon as the combined coverage is ready. The caller preserves the required
`verify` and `sonar` check contexts as decoupled joins: a red quality gate no
longer blocks the test gate, and vice versa.

The advisory `fast-feedback` job gives early static/lint/policy and directly
changed-test signal on pull requests. It is never a merge gate; the full-suite
shards remain authoritative.

To reproduce a failure locally, select its reported module or test case:

```shell
uv run --project implementations/python --frozen pytest implementations/python/tests/test_runtime_models.py -q
```

Measure feedback latency for a cohort of runs with
`python tools/ci_latency_report.py` (median and p95 time to first failure and to
final required-check completion, computed from native GitHub timestamps).

## Release model

Release Please owns `CHANGELOG.md`, package versions, GitHub releases, and the
release pull request. A feature pull request uses a Conventional Commit title
because its squash-merge title becomes the commit that Release Please reads.
Do not edit the changelog or version by hand.

## Review records

Ground Control stores implementation plans, review findings, readiness, and
traceability records for governed work. These developer records stay outside
the hosted public documentation source.
