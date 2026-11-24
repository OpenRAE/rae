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

## Keep the structural ratchets

The policy session also runs the structural checks of
[ADR-117](decisions/adrs/adr-117-ratcheted-structural-checks.md) on the package
source. They fail on a new import cycle, a new private import from another
module and a new class with more than seven package ancestors. The current debt
is in `tools/policy/import_contracts.toml` and
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

### Go integration branch protection

The active [merge-policy-go-cutover ruleset](https://github.com/OpenRAE/rae/rules/26422222)
matches only `refs/heads/go-cutover`. It requires pull requests and these checks:

| Required context | Coverage | GitHub App ID |
| --- | --- | --- |
| `verify` | Canonical aggregate and runtime supervision | 15368 |
| `sonar` | Independent SonarCloud quality gate | 15368 |
| `fuzz` | Separate Python fuzz lane | 15368 |
| `supply-chain` | OSV dependency vulnerability scans | 15368 |
| `CPython 3.14 compatibility` | Interpreter and distribution checks | 15368 |
| `CodeQL` | CodeQL service result | 57789 |
| `Analyze (actions)` | Actions security analysis | 15368 |
| `Analyze (python)` | Python security analysis | 15368 |
| `Analyze (javascript-typescript)` | JavaScript and TypeScript security analysis | 15368 |
| `GitGuardian Security Checks` | Secret scanning | 46505 |
| `title-guard` | PR title policy | 15368 |
| `body-guard` | PR body policy | 15368 |

These names and App identities were checked against live Go-branch runs on
2026-11-03. Workflow job keys alone do not establish emitted check names.

The Go branch's `ci.yml` calls `canonical-verification.yml`. Its `go` matrix
checks product and tooling modules, including changed-line mutation testing.
The `go-architecture` and `parity-corpus` jobs also feed its canonical `gate`.
That gate rejects unsuccessful dependencies and supplies the caller's `verify`
context. No separate check named `mutation`, `architecture`, or `parity` is required.
Parity coverage does not establish that the full Go port is complete.

Regression capture replaces pytest's generated user, session, and worker path
components with stable names. It keeps input bytes and relative dependency paths.
The manifests describe the recorded input snapshot and retain its original
source identities. Every check replays those inputs against the current Python
implementation and checks the Go runners. Live registries, contracts and examples
still determine their required cases. Completeness describes the recorded
collection; it does not claim that every current Python test supplies corpus data.

Unrelated test edits and merges reuse the snapshot. A valid recording receipt
changing alone does not require a rewrite. Changed inputs, results or coverage
still fail comparison and produce a candidate with current source provenance.
Missing or invalid snapshots fail; they do not start collection automatically.
This replaces the automatic source-tree freshness rule in the original
[corpus design](decisions/issue-1778-parity-corpus-design.md).

When new protocol regression cases need golden coverage, explicitly request a
fresh collection on the published branch:

```bash
gh workflow run ci.yml --repo OpenRAE/rae --ref <branch> -f refresh-parity-inputs=true
```

The optional flag defaults to false. Collection still runs only in isolated CI.
Review the generated artifact before promotion. Keep the generated provenance
and credential scans; do not hand-edit expected results to make comparison pass.

The maintainer merges manually after checks pass. Zero required review approvals
preserve the single-maintainer model. There are no configured bypass actors;
administrators must satisfy the rule. Administrators retain authority to edit
repository settings. Automatic merging remains disabled.

The existing Ground Control Phase E workflow includes closed PRs into
`go-cutover`. After a manual merge, it verifies the trusted delivery handoff,
posts the final report, and closes the issue. It does not merge PRs.

Legacy branch protection also remains active. Force pushes and deletion are
prohibited. The existing non-strict base-update policy remains: a PR need not
include the latest base commit. New PR heads still require their own checks.
GitHub can accept neutral or skipped individual checks. The canonical aggregate
requires explicit success from its required dependencies.

Same-repository Go PRs run Sonar analysis. The current Sonar push guard includes
`main` and `dev`, so a Go branch push is not independent quality-gate evidence.
Fork and Dependabot secret restrictions remain applicable. Release bookkeeping
path filters can leave required workflows pending; do not bypass missing checks.

Read the effective rules through `GET /repos/OpenRAE/rae/rules/branches/go-cutover`
and legacy protection through `GET /repos/OpenRAE/rae/branches/go-cutover/protection`.
To verify check blocking, inspect a mergeable, non-draft Go PR with failed or
pending required checks. Confirm its API merge state is blocked. A conflicting
PR cannot supply this evidence. Never attempt a merge as a test.

### Canonical verification

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
