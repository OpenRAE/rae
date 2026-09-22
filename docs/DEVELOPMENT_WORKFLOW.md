# Development workflow

Use this page to find the canonical local checks. Public contribution steps are
in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Install the locked environment

From the repository root:

```shell
uv sync --project implementations/python --all-extras --frozen
```

An optional [development container](explain/development-container.md) performs
this setup for you on Linux x86_64. That page labels each start route verified
or unverified. It cannot run the proof lane; continuous integration does.

## Run verification

Full test suites run in CI/CD only. Its full pull-request gate is:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups nox -f noxfile.py -s verify
```

Use `verify-fast-feedback` (also the default nox session) or `verify-changed`
while you work. These run changed-file checks and directly changed test modules.
Source, deleted, renamed, contract, configuration and unknown changes never
trigger a full local suite. Select additional relevant pytest modules or cases
explicitly when a changed test module does not cover the changed behavior.
`verify-completion` uses the same targeted path; full completion runs in CI/CD.

The docs session checks the curated source boundary, the RAES Vale style,
warning-strict Sphinx HTML, generated route and search inventories, and links:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups nox -f noxfile.py -s docs
```

## Respect package boundaries

`tools/policy/adr_policy.yaml` defines the public import facades allowed across
RAES packages. Adapters import owning domain APIs only through those listed
facades and never through private modules. For example, the semantic CLI calls
SDL compilation through `raes_processor.compiler`; adding another CLI/compiler
interaction extends that public facade instead of importing compiler internals
or duplicating compiler behavior in `raes_cli`.

Run the repository policy session after changing a cross-package import:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups nox -f noxfile.py -s policy
```

## Continuous integration graph

The pull-request gate runs through `.github/workflows/ci.yml`, which calls the
reusable `.github/workflows/canonical-verification.yml`. That reusable graph is
the single exact-SHA full gate for pull requests, protected branches, and
release verification.

Inside the reusable graph the default-marker test suite is split across four
deterministic concurrent shards (`test-shard`, indices 0-3), so a full run
finishes sooner than a single 5,000-plus-test job. Each shard owns a SHA-256
partition of the collected pytest node ids (`tools/pytest_shard.py`); there is no
per-module shard table. Alongside the shards, the `integration`, `checks`
(hygiene, policy, lint, contracts, docs), and `proof` jobs run in parallel. The
`coverage-reduce` job then proves the shard manifests form a complete, disjoint
partition of a freshly collected suite, combines shard and integration coverage,
and enforces the 90% line floor (ADR-103). SonarCloud runs inside the same graph
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
