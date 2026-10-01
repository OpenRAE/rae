# ADR-014: nox as the Canonical Verification Graph

## Status

accepted

## Date

2026-05-09

## Context

The repository has multiple verification layers — Python tests (pytest +
hypothesis), repo-policy enforcement (Conftest/OPA + Python scripts under
`tools/policy/`), JSON-schema contract validation (`check-jsonschema`),
secret scanning (gitleaks), formatter/linter (ruff), file-hygiene gates
(trailing whitespace, EOF newline, large-file detection, merge-conflict
markers, private-key detection), Sphinx documentation builds, and
property-based fuzz tests. Each gate has its own native invocation. The
gates need shared implementations with different scopes in three places:

1. **Local pre-commit hooks** — fast, scoped to staged files.
2. **Local pre-push hooks** — targeted feedback for changed files and tests.
3. **CI (`ci.yml`)** — full regression, coverage upload, and SonarCloud.

Before this ADR, the only mechanism to keep these three invocations in
agreement was discipline: hand-maintained command lists in
`.pre-commit-config.yaml` and `.github/workflows/ci.yml`, plus prose in
`AGENTS.md` and CONTRIBUTING-style docs. The failure mode of that
arrangement is well known: the three command lists drift, "verified
locally" stops meaning the same thing as "passed in CI," and a
contributor passing the local hook can still find a CI failure that was
preventable with a slightly different local command.

The repository also has policy and contract tooling written in Python
that consumes structured artifacts (the requirement order, ownership
maps, traceability links, ADR index, etc.). A pure-shell orchestrator
(Make, just, plain scripts) has to re-implement Python-aware
composition every time it wants to call into that tooling. A
Python-native orchestrator can call the tooling in-process or via
explicit subprocess and still share the rest of the verification graph
with non-Python checks (gitleaks, OPA, sphinx-build).

## Decision

### 1. nox is the single canonical verification graph

`noxfile.py` at the repository root is the sole public session registry and
entry point. Private configuration, execution, lane, and graph helpers live in
the acyclic `tools/nox_support/` package; support modules do not register nox
sessions or import `noxfile.py`. Together they define every verification stage
with explicit substages, run sequentially through a `SessionReporter` that
emits structured `START` / `PASS` / `FAIL` / `SKIP` events. The canonical
sessions are:

- `hygiene` — text/YAML/JSON/secret/large-file/merge-conflict checks
- `policy` — Conftest self-verify, repo policy, requirement governance
- `lint` — ruff format + check, project and tooling
- `contracts` — generated-schema drift, JSON-artifact validation
- `tests` — full pytest with coverage, CI/CD only
- `fuzz` — full pytest with `-m fuzz`, CI/CD only
- `python-compatibility` — exact-interpreter tests plus clean distribution
  build, installation, import, and CLI checks for one supported CPython release
- `docs` — sphinx-build (added by AUT-805)
- `verify` — full hygiene + policy + lint + contracts + tests + docs, CI/CD only
- `hook-pre-commit` — staged-file hygiene + policy + scoped lint +
  conditional contracts + directly changed test modules
- `verify-fast-feedback` — local default: hygiene + policy + changed-file lint
  + directly changed test modules; advisory, not the merge gate
- `verify-changed`, `hook-pre-push`, and `verify-completion` — the same targeted
  feedback path, with no fallback to full test suites

`verify` is the canonical single-interpreter full CI gate. CI invokes
`nox -s verify`; the pre-push hook invokes `nox -s hook-pre-push`; the
pre-commit hook invokes `nox -s hook-pre-commit`. Local verification uses
explicit affected test modules or cases only. Missing targeted selection means
recording that limitation and deferring full testing to CI/CD, never launching
the full suite locally. This applies to implementation, review repair,
synchronization, and completion. CI additionally invokes
`python-compatibility` once for every supported CPython feature release because
a single local interpreter cannot establish the distribution's cross-version
support claim. All invocations resolve through the same per-gate helpers (`_run_hygiene`,
`_run_policy`, `_run_lint`, `_run_contracts`, `_run_tests`,
`_run_fuzz`, `_run_docs`).

Ground Control invokes pre-commit against the staged set. It does not add
`--all-files`: that flag expands the hook input to every repository path,
defeats staged change classification, and expands the local hygiene boundary
unnecessarily. Full regression remains required in CI/CD before merge; passing
targeted local checks does not establish that result.

### 2. `.pre-commit-config.yaml` is a thin trigger layer, not a parallel definition

Pre-commit's repo-side configuration declares one hook per nox session
that pre-commit needs to invoke (currently `hook-pre-commit` and
`hook-pre-push`). The substantive command list lives in the canonical graph
rooted at `noxfile.py` and implemented by `tools/nox_support/`, not in
`.pre-commit-config.yaml`. This mirrors a common pattern in
modern Python projects (e.g., calling `pytest` from a single hook
rather than re-listing pytest options in YAML) and removes the
multi-source-of-truth failure mode that the previous configuration had
when pre-commit and CI maintained their own command lists.

### 3. CI consumes the same graph

`.github/workflows/ci.yml` runs `uv tool run --from 'nox[uv]==…' nox
-s verify` for the canonical single-interpreter gate, plus `nox -s fuzz` as a
separate job (fuzz is excluded from `verify` because it is property-based and
slow, not because it is optional). It also runs `nox -s python-compatibility`
as a required-check matrix over every standard CPython feature release named
by package metadata. Those jobs assert the selected runtime, use the frozen
dependency graph, run the hermetic suite, and verify a clean installed
distribution. SonarCloud consumes the coverage XML that the `tests` substage
produces; it is not a parallel test-runner.

The `.ground-control.yaml` workflow block declares each command nox
exposes:

```yaml
workflow:
  test_command:       nox -s verify-fast-feedback   # targeted local feedback
  completion_command: nox -s verify-fast-feedback
  lint_command:       nox -s lint
  format_command:     nox -s hygiene
```

The `/implement` skill consumes those values verbatim. Local completion means
targeted feedback is complete, not that the full CI gate passed. Ground Control
must separately observe required CI and Sonar results before PR readiness.

### 4. Per-session venvs via uv

`nox.options.default_venv_backend = "none"` plus per-session
`uv sync --project implementations/python --all-extras --frozen`
delegates dependency resolution to uv. The `--frozen` flag rejects any
session that would require a lockfile change at run time, so a session
either runs against the locked dependency set or fails fast.

### 5. nox is preferred over the alternatives evaluated

**Make.** Not Python-aware; can drive Python tooling but cannot
compose with our existing Python `tools/policy/` modules without
shelling out. Targets are not first-class composable units in the way
sessions are — there is no native concept of "run subset A on staged
files, subset B on the full tree." Rejected.

**just.** A more ergonomic Make. Same compositional limitations. Adds a
non-standard binary to the contributor toolchain. Rejected.

**Pre-commit only.** Pre-commit's per-hook isolation is a feature for
the staged-file path but a barrier for the full-repo path: there is no
shared state between hooks, no DAG, and no clean way to run the
"pre-commit set" outside of pre-commit's own invocation harness (which
makes the CI invocation differ from the local one, the very failure
mode this ADR is closing). Rejected as the canonical orchestrator;
retained as the trigger layer (Decision #2).

**Plain scripts.** A `scripts/verify.sh` would work but loses session
reuse, structured reporting, the per-stage `SessionReporter` summary
that current contributors and CI logs depend on, and Python-native
composition with `tools/policy/`. Rejected.

**nox.** Python-native. Per-session uv-managed venvs. Sessions
compose. Reuses our policy/contract tooling in-process. Already
familiar to Python contributors. Has a maintained `nox[uv]` integration
that pins the uv version we use elsewhere. Selected.

## Consequences

### Positive

- A single source of truth for each gate: local feedback and full CI reuse the
  same helpers, while explicitly reporting their different verification scopes.
- The verification surface is discoverable via `nox -l`; new
  contributors do not have to search across YAML files to learn what
  "verified" requires.
- Local success cannot be mistaken for full regression success: the former is
  targeted feedback, while CI/CD owns full-suite completion and merge gating.
- Adding a new gate changes one canonical graph: its session registration stays
  in `noxfile.py`, while its implementation and composition are each defined
  once in `tools/nox_support/`. CI and pre-commit pick it up automatically
  through `verify` / `hook-pre-push` / `hook-pre-commit`.
- The `.ground-control.yaml` workflow block is the single point where
  agents (Codex, Claude Code, the `/implement` skill) read these
  commands; they do not have to parse `.pre-commit-config.yaml` or
  `.github/workflows/ci.yml`.

### Negative

- Contributors must learn the nox session names. Mitigated by `nox -l`
  and by the principle that the names describe what they verify
  (`hygiene`, `policy`, `lint`, `contracts`, `tests`, `fuzz`, `docs`,
  `verify`).
- Targeted local feedback can miss regressions outside the selected modules;
  required full CI suites, not a local full-suite fallback, cover that risk.
- nox session startup is not free. Mitigated by
  `nox.options.reuse_existing_virtualenvs = True` and by the uv-backed
  install path, which is fast on a warm cache.
- A bug in `noxfile.py` or `tools/nox_support/` can break every gate at once.
  Mitigated by tooling lint, Coverage.py and Sonar analysis of both surfaces,
  exact session/lane inventory tests, and focused tests under
  `implementations/python/tests/test_repo_policy_tools.py` and
  `test_requirement_governance.py` that exercise the underlying helpers
  independently.

### Risks

- Drift between the `nox` graph and the policy expectations (e.g., the
  `documentation-surfaces` phase ownership) is possible if a new
  session is added without extending policy ownership. This is a
  process risk, not an architectural one; it is the same risk the
  policy gate is designed to surface.
- nox's plugin surface (custom backends, alternative venv managers)
  expands the failure surface compared to plain scripts. We restrict
  ourselves to `default_venv_backend = "none"` plus uv-managed
  installs to keep the surface narrow.

## Notes

The decision codified here is what the repository already does in
practice — it was first introduced by commit `115ea24` (2026-04-11)
without an accompanying ADR. ADR-014 captures the rationale so that
future contributors do not have to reconstruct it from CHANGELOG
entries and tooling code. Sibling repositories in the same ecosystem
make different choices appropriate to their stacks (`aptl` is
multi-language and uses native runners per ecosystem with a
pre-commit-driven gate; `pulsar` is a pnpm monorepo and uses pnpm
workspaces; `shifter` has no top-level runner and documents its
absence). nox is the right answer for this repository specifically
because the verification surface is broad, polyglot at the gate level
(Python + OPA + gitleaks + Sphinx), and shared by local hooks, CI, and
ground-control automation with explicit targeted-local/full-CI scopes.

The #1348 amendment supersedes the local full-regression obligations recorded
by #963 and the local `verify` recommendation in #1134. Their entries below
remain historical records, not current instructions to run full suites locally.

## Amendments

| Date | Commit/PR | Summary |
|---|---|---|
| 2026-07-31 | #963 | Replaced the serial `verify` composition with six isolated, CPU-budgeted concurrent nox lanes, primed shared policy tooling before cold-cache lanes, batched JSON artifacts by shared schema with bounded concurrency, combined unit and integration coverage deterministically, scoped pre-commit to staged changes and directly changed tests without duplicating the mandatory full pre-push/completion regression, and separated network-dependent external-link validation into dedicated docs CI. Ground Control's completion half omits policy because its mechanically enforced policy half runs immediately afterward; direct `verify` and CI retain policy. |
| 2026-08-14 | #1134 | Added a required CI matrix that runs the canonical `python-compatibility` session for each supported CPython feature release while retaining `verify` as the reproducible single-interpreter local gate. |
| 2026-09-03 | #1164 | Split private nox configuration, runner, lane, and graph helpers into the acyclic `tools/nox_support/` package while retaining root `noxfile.py` as the sole public session registry, preserving one canonical graph, and keeping both surfaces in coverage and static analysis. |
| 2026-09-22 | #1348 | Restricted local defaults, pre-push, changed verification, and completion to targeted feedback; reserved full test suites for CI/CD, superseding earlier local full-regression obligations while preserving required CI and Sonar gates. |
