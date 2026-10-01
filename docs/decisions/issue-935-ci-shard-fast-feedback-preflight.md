# Issue #935 CI Sharding and Fast-Feedback Preflight

Date: 2026-09-16

Issue: #935. This is a requirement-free maintenance run. The issue title, body,
acceptance criteria, accepted ADR-103/ADR-106/ADR-107 decisions, and accepted
package-artifact design set are the implementation contract.

This note records architecture guardrails only. It does not implement a shard,
change a required check, enable a cache, pass a Sonar quality gate, publish an
artifact, or claim latency results.

## Entry gates and present boundary

Implementation remains gated by the live native dependency relationships for
#1168, #1219, and #839. Repository history contains the accepted design and the
verified-installation/action-admission implementations, but history and this
note do not replace a live dependency/status check before execution.

The issue's approximately 5,100-test observation is historical. A collection
snapshot on 2026-09-16 found 10,732 tests: 10,559 default tests, 163 hermetic
`integration` tests, 8 `fuzz` tests, and 2 opt-in `docker` tests, with no overlap
between those marker selections. These counts are diagnostics, not configuration
or acceptance constants. Shard completeness must be derived from the current
collection on every run.

## Canonical incumbents

| Concern | Canonical incumbent | Guardrail for #935 |
|---|---|---|
| Exact-SHA admission and protected check | `.github/workflows/canonical-verification.yml`, the `canonical` call and stable `verify` join in `.github/workflows/ci.yml`, plus release caller `verify-release` | Keep one reusable exact-SHA graph for PR, protected-branch, and release verification. Do not duplicate a cheaper PR graph or let the release caller select a weaker lane set |
| Verification topology | `noxfile.py`, `tools/nox_support/graph.py`, `test_lanes.py`, `runner.py`, `config.py`, and `tools/parallel_verification.py` | Extend the existing lane/session boundaries. CI job topology may distribute those lanes, but must not reimplement their commands, coverage policy, reporting, or exceptions in workflow shell |
| Change classification | `tools/verification_plan.py`, `collect_git_changes()`, `plan_for_changes()`, and `select_changed_python_tests()` | The early lane may reuse these fail-closed Git and direct-test selectors. Do not add path heuristics or a second change schema in YAML. Selection is feedback only and never merge authority |
| Python collection and category ownership | `implementations/python/pyproject.toml` pytest marker/addopts contract | Preserve the default, integration, fuzz, and Docker meanings. CI shards divide only one explicitly named collection domain; they do not redefine markers or make opt-in Docker tests a required hosted lane |
| Coverage authority | ADR-103, Coverage.py configuration in `implementations/python/pyproject.toml`, `_finalize_parallel_coverage()`, `_write_and_check_coverage()`, `_enforce_line_coverage()`, and `sonar-project.properties` | Combine default-shard and hermetic-integration data before generating XML/JSON and enforcing the existing 90% line floor. Do not implement another coverage calculator or rewrite XML to manufacture portability |
| Workflow/action admission | `implementations/tooling/actions-policy.json`, its closed schema, `implementations/tooling/action_policy_*`, and `tools/check_tooling_artifact_policy.py` | Every new job and action occurrence must have an exact job/use-site record. Reuse the admitted upload/download/setup actions and extend the existing reusable-secret contract narrowly if Sonar moves inside the reusable graph; never bypass or weaken the validator |
| Input installation and cache safety | ADR-106, the package-artifact design set, `tools/verified_tool_installation.py`, `tools/bootstrap_profile.py`, the frozen Python closures, and the #1219 qualification harness | Share admitted immutable inputs or read-only seeds, then create private job environments/installations. Do not transfer `.venv`, a writable uv/tool cache, or a previously executable workspace between jobs |
| Diagnostics and gate errors | `SessionReporter`, `VerificationLaneResult`, `PolicyFailure`, pytest/JUnit output, and native GitHub job/check results | Retain these envelopes and stable stage identities. A shard helper may raise sanitized `ValueError`/`RuntimeError` at the tooling boundary; it does not need another exception hierarchy or result schema |

No new ADR is required. This is a distribution of the verification graph under
the accepted coverage, tooling, and artifact decisions, not a new product or
runtime architecture.

## Verification-graph decision

The reusable canonical workflow remains the sole full-gate owner. Its required
coverage producers may run as a bounded matrix, while static/policy, contracts,
proof, docs-local, and other incumbent admission lanes run independently. The
caller-level `verify` context remains an `always()` fail-closed join over the
complete reusable result so branch protection does not silently change meaning.
Fuzz, interpreter compatibility, supply-chain, and the current optional Docker
lane retain their existing caller-level ownership and failure semantics.

A caller sees a reusable workflow invocation as one atomic job; it cannot depend
on an internal coverage-ready job. Therefore Sonar analysis must run inside the
canonical reusable graph and depend only on the exact source context plus the
successful coverage reducer. The reusable graph exposes one bounded Sonar
outcome tied to that source SHA. A top-level `sonar` compatibility join may
preserve the existing branch-protection context by checking only that outcome;
it must not produce analysis or inherit the unrelated canonical result. Missing
or malformed output fails closed. Putting a duplicate test/coverage graph in
`ci.yml` merely to unblock the existing Sonar job is prohibited.

The reusable interface needs a default-off Sonar enablement input and one
explicitly named optional secret. `ci.yml` enables it; the release caller leaves
it disabled and passes no secret. The existing action-policy `localWorkflow`
shape currently rejects all reusable secrets. Extend that closed schema and the
same semantic validator to admit only the declared secret mapping. Do not use
`secrets: inherit`, an ambient repository token, a second policy file, or an
unparsed expression escape hatch.

The early-feedback lane is distinct from the full gate. It always runs the
incumbent static/lint/policy surfaces that are valid for the exact diff and may
run directly changed pytest modules selected by `verification_plan.py`. An
unknown dependency relationship must produce an explicit “no authoritative
targeted selection” outcome and defer to the already-running full shards; it
must not guess test ownership or claim the selected subset is sufficient.
Selected-test coverage is excluded from final coverage. Re-executing a directly
changed test in this advisory lane does not violate the exactly-once invariant,
which applies to ownership within one full-suite shard run.

## Deterministic shard and coverage contract

One code-owned partition function maps the canonical collected pytest node id
to `int.from_bytes(sha256(nodeid.encode("utf-8")).digest(), "big") %
shard_count`. Python's
randomized `hash()`, xdist scheduling, wall-clock timings, filesystem order, and
GitHub matrix order are not shard authorities. `shard_count` is a validated,
bounded reusable-workflow/Nox parameter; `shard_index` is validated against it.
The workflow must not maintain a second hard-coded module-to-shard table.

The partition applies after the incumbent marker expression defines the suite.
Every shard records its exact source SHA, algorithm version, suite expression,
count/index, and selected node ids. The reducer recollects the same suite in the
same frozen environment and fails unless shard manifests are pairwise disjoint,
their union exactly equals that collection, every index is present once, and
all producers succeeded. Focused tests also prove order independence, stable
ownership, invalid-bound rejection, additions/deletions, parametrized node ids,
and duplicate/missing-manifest failure. xdist may schedule work inside one shard,
but it is not the cross-job partitioner and its worker cap must avoid nested
oversubscription.

Each successful coverage producer emits a uniquely named, exact-SHA/run-attempt/
suite/shard-bound Coverage.py data artifact plus the shard manifest. Missing
files are errors. Raw shard data is combined once with Coverage.py; only then are
`coverage.xml` and `coverage.json` generated, the aggregate line floor enforced,
and the final same-run report exposed to Sonar. The reducer must not run over
partial data under `always()`, accept an absent failed shard, or combine advisory,
fuzz, compatibility, or stale-run coverage.

Coverage data must be portable between clean runner workspaces. Test this with
separate temporary checkout roots. If the current absolute-path configuration
cannot combine correctly, use Coverage.py's own `relative_files`/`[paths]`
facilities and amend ADR-103 deliberately; do not search-and-replace paths in
binary data or generated XML.

Shard data, manifests, JUnit, and ordinary PR coverage remain C03-derived
reports with short retention and `write-untrusted`/`read-same-run` roles. Their
names, cache keys, or existence are not content integrity, release evidence,
promotion, or publication authority. Exact reports retained later by release
admission remain the #1226/#1227 boundary.

## Cross-cutting layers the design must pass

- **Repository/config shape.** Every workflow continues through the bounded
  regular-file YAML parser, duplicate-key/alias rejection, normalized GitHub
  `on` handling, closed condition/expression grammar, exact action SHA checks,
  immutable runner/profile join, least-privilege permission join, and exact
  workflow-job/use-site coverage. Internal policy JSON continues through
  `safe_repo_path()`, no-symlink checks, bounded duplicate-key-rejecting parsing,
  local-only Draft 2020-12 schemas, and semantic joins. Matrix expansion,
  artifact roles, and the new explicit reusable-secret mapping must be understood
  by this one validator or fail closed.
- **Exact source and environment binding.** Validate the full lowercase source
  SHA once and make every checkout use it with `persist-credentials: false`.
  Validate the comparison base before change classification. Preserve
  requirement-branch/UID propagation and requirement-free `--skip-requirement`
  behavior. Shards use the frozen tooling/project locks and the same pytest and
  coverage configuration; no mutable dependency resolution or runner alias may
  influence ownership.
- **Authentication and secret handling.** Public, fork, Dependabot, test, shard,
  reducer, and report jobs have no Sonar, enterprise, promotion, publication,
  package-write, OIDC, or trusted-cache-write credential. Sonar remains limited
  to protected pushes and same-repository non-Dependabot PRs. Its token is passed
  explicitly and only as `SONAR_TOKEN` to the scanner boundary, never in an
  input, artifact, cache key, output, command argument, checkout credential,
  event dump, or log. Gitleaks/private-key checks and action-policy credential
  classes remain in force.
- **Acquisition/cache boundary.** Reuse setup actions, frozen uv closures,
  admitted local inputs, and verified installations. A producer may carry an
  immutable wheelhouse/raw-object/read-only seed to private shard workspaces;
  every consumer revalidates it through the owning lock/policy. A PR cannot save
  a shared writable cache. Adding `actions/cache/restore` requires its exact
  source/transitive-input admission under #839 and owning byte re-admission;
  cache restoration is optional performance work, not a precondition for
  sharding correctness.
- **OS/process exposure.** Preserve the current pinned runner generations and
  the Ubuntu 22.04 Bubblewrap proof-host exception unless a separately qualified
  host change is accepted. Do not share writable filesystems, daemon sockets,
  fixed temp names, home-directory state, broad environment maps, or executable
  search paths between shards. Tokens never enter argv. Coverage/artifact paths
  are private, normalized, and unique per producer.
- **Errors and observability.** `PolicyFailure` remains the shape for static
  admission failures; `SessionReporter` remains the Nox stage envelope; pytest
  remains the test-failure authority. Log shard/suite/count/index, collected and
  selected counts, duration, exact public source SHA, and stable failure reason,
  but not environment contents, GitHub event payloads, artifact service tokens,
  raw native exceptions, or Sonar credentials. A skipped/missing/cancelled
  producer never becomes a successful aggregate.

## Measurement contract

Latency acceptance must use the current required-check set and comparable PR
cohorts, not the historical 5,100-test count. Record the sample window, number of
runs, head SHA and attempt, event/trust class, queue time, runner time, and
cancellations. For failed attempts, time to first actionable failure is measured
from workflow `run_started_at` to the earliest terminal failing required or
fast-feedback step/check. Successful attempts are not imputed as failures.
Final required-check completion is the latest terminal timestamp among the
branch/ruleset's actual required checks for that same SHA and attempt. Report
median and p95 for baseline and resulting cohorts; separate queueing from
execution and do not cherry-pick only warm-cache or successful runs.

Reuse native GitHub run/job/step timestamps and `SessionReporter` durations.
Do not add a telemetry service, database, credential-bearing log scraper, or
repository schema merely to calculate these issue-level measurements.

## Documentation boundary

Update developer documentation only when the executable graph lands, so it does
not describe commands that do not yet exist. `docs/DEVELOPMENT_WORKFLOW.md` owns
the maintainer-facing fast-feedback/full-gate distinction, shard ownership,
coverage reduction, and one Nox-based reproduction command for a failed shard.
`CONTRIBUTING.md` keeps the public local workflow aligned without exposing CI
implementation detail. `docs/explain/releasing.md` must continue to describe the
same exact-SHA canonical gate after its internal topology changes. Commands in
workflow YAML and prose must call the same Nox/session seam rather than duplicate
raw pytest marker, coverage, or partition arguments.

## Gotchas and anti-patterns

- Do not conflate GitHub job shards with xdist workers, an early selected subset
  with the merge gate, a coverage artifact with a cache, or a cache with admitted
  input/release evidence.
- Do not hard-code today's test count, test filenames, or shard membership in
  workflow YAML; do not use `hash()`, random order, timing-dependent ownership,
  or a third-party sharding service as the coverage authority.
- Do not upload multiple artifacts under one ambiguous name, reuse artifacts
  across workflow attempts, merge partial coverage after a failed shard, or let
  `if: always()` manufacture a final report.
- Do not pass `.venv`, `.cache`, installed executables, or a writable tool tree
  between untrusted jobs. Artifact/cache service isolation does not make bytes
  trusted.
- Do not let matrix `fail-fast` cancellation hide additional shard failures or
  count a cancelled shard as complete. The final join must distinguish failure,
  skip, and cancellation from success.
- Do not move proof execution off its qualified host, disable Bubblewrap, weaken
  repo-policy/contracts/fuzz/integration/supply-chain checks, lower coverage, or
  replace the full suite with change selection to improve a latency number.
- Do not make Sonar secret-bearing execution available to forks/Dependabot, use
  `secrets: inherit`, put the token in argv, or weaken the action-policy grammar
  to accept a reusable workflow the parser cannot classify.
- Do not break the release caller, exact-SHA/base binding, stable `verify`/Sonar
  check contexts, or protected-branch configuration while changing internal job
  topology.

## Non-goals and implementation boundaries

- No application/runtime controller, DTO, service, repository, database,
  persistence model, public schema, SDL semantic, or domain exception change.
- No test deletion, marker redesign, coverage-threshold change, interpreter-
  support change, optional-Docker promotion, proof-host migration, or weakening
  of existing required gates.
- No new package manager, HTTP client, artifact promotion/retention service,
  enterprise credential flow, shared writable cross-tenant cache, or release
  publication authority.
- No branch-protection edit, protected-branch merge, feature-PR merge, release,
  or claim that #1226/#1227 report retention and admission have shipped.
- No general performance framework. This issue owns deterministic CI partition,
  same-run coverage reduction, early feedback, documentation, and evidence of
  the stated latency outcome only.
