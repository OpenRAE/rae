# Issue #1857: Go integration branch enforcement preflight

Date: 2026-11-03. Scope: architecture guidance, not an implementation plan.

The issue defines the required result. This note changes no GitHub
settings, checks, or workflow code and asserts no live enforcement result.
No new ADR is needed. This applies the current check and branch rules.

## Source boundary

The inspected working tree is based on `dev` at
`32abf69cab1d702baf7e9b0474541eaedbf550f8`. Its workflows do not include
`go-cutover` or the Go lanes. The same repository's local tracking ref
`origin/go-cutover`, inspected at `52979ff95d6c5574ec604307a6c679c7b5decbc6`,
contains the #1808 triggers and the Go standards, architecture, and parity gates.
References to Go artifacts below mean that revision, not files present on `dev`.
Neither local ref establishes the current remote tip or current repository rules.
Find final contexts from the live target-branch workflows and their actual
PR check runs before configuring enforcement; do not backport the Go port into
`dev` merely to configure its integration branch.

## Decisions and canonical owners

Use a narrowly targeted active branch ruleset in the existing `merge-policy-*`
family, matching exactly `refs/heads/go-cutover`. Keep `dev`, `main`, and release
tag controls unchanged. Reconcile any existing target rule rather than creating
overlapping copies. Native GitHub rules are the enforcement authority; workflow
triggers and a checked-in description cannot enforce branch admission.
No checked-in branch-rule provisioning owner was found under the repository's
tooling or workflows; reuse the existing maintainer-owned settings boundary
rather than introducing a credentialed reconciliation service.

Require PRs and successful applicable checks while retaining manual maintainer
merges. [GOVERNANCE.md](../../GOVERNANCE.md) and
[MAINTAINERS.md](../../MAINTAINERS.md) establish a single maintainer: do not
introduce a mandatory second approving reviewer. Do not enable auto-merge, a
merge queue, or restrictions that permit only bypass actors to update the branch.
Preserve the incumbent force-push/deletion safeguards without weakening them.

Bypass rights differ from normal merge rights.
Record the rule actors, roles, bypass modes, and scope. State the intended emergency use.
Do not assume that admins can bypass the rule. Do not assume that they cannot. Prefer the narrowest incumbent authority, with
PR-only bypass when sufficient; do not silently grant an always-bypass actor.
Test the normal path without bypass rights.

| Concern | Canonical incumbent and boundary |
| --- | --- |
| Verification composition | `.github/workflows/ci.yml` calls `canonical-verification.yml`; stable `verify` and `sonar` joins preserve distinct outcomes. ADR-014 and `noxfile.py` / `tools/nox_support/` own Python verification. |
| Go standards | Target-branch ADR-121, `implementations/.golangci.yml`, `.gremlins.yaml`, and tooling Go module own lint, mutation thresholds, analyzers, and regression replay. Do not copy their commands into a protection workflow. |
| Architecture | Target-branch ADR-122, `implementations/tooling/go/arch`, `cmd/archcheck`, and `docs/develop/go-architecture.md` own the model and checks. Enforcement adds no product packages or model nodes. |
| Parity | Target-branch `tools/parity_corpus.py`, `parity_inputs.py`, `parity_storage.py`, and `implementations/go/internal/parity` own collection, comparison, completeness, and safe artifact handling. |
| PR policy | `pr-title-lint.yml` / `tools/check_pr_title.py` and `pr-body-policy.yml` / `tools/check_pr_body.py` retain base-revision validators, event-file input, and read-only tokens. |
| Workflow admission | `implementations/tooling/action_policy_yaml.py` and `tools/tooling_artifact_policy_actions.py` own workflow parsing, permissions, pins, secret boundaries, and reusable input contracts. ADR-106 tooling admission remains authoritative. |
| Verification and diagnostics | `implementations/python/tests/test_release_workflows.py`, `test_action_policy_reusable_secrets.py`, and `test_tooling_artifact_policy.py`; native GitHub check results; `PolicyFailure` and `SessionReporter`. Reuse these instead of a new result schema or validator. |

## Check contract and whole-graph guardrails

The target revision exposes these candidate contexts. This inventory is not a
replacement for resolving emitted names and source App identities through the API.
Preserve the incumbent strict/up-to-date policy explicitly; passing checks on an
older head or obsolete comparison base do not establish admission for new code.
An App binding identifies the check producer, not an pinned workflow: workflow
changes still need maintainer review. Avoid duplicate job/status names that can
collide across workflows, and do not infer names from workflow titles.

| Candidate context | What it covers |
| --- | --- |
| `verify` | `canonical.gate-outcome` plus `runtime-supervision`. The reusable gate requires test shards, integration, static/policy/contracts/docs checks, proof, model checks, coverage reduction, the entire Go module matrix, Go architecture, and parity corpus. |
| `sonar` | Independent quality outcome, consuming Python and Go coverage; a passing `verify` cannot stand in for it. |
| `supply-chain` | Networked vulnerability scanning, outside the reusable aggregate. |
| `fuzz` | Separate Python fuzz lane; Go fuzz targets run inside the Go matrix. |
| `CPython 3.14 compatibility` | Distribution/runtime compatibility; the display name differs from job key `distribution`. |
| `title-guard`, `body-guard` | PR title and body repository policy; extra repository policy runs inside `verify`. |

Go mutation coverage reaches `verify` through `go` -> reusable `gate` -> caller
join, not a separate context named "mutation". The two-module Go matrix checks
dependencies, lint/analyzers, race tests, 90% statement coverage, bounded fuzzing,
changed-line gremlins thresholds, and new regression tests against the comparison
base. `go-architecture` and `parity-corpus` independently feed the same aggregate.
Document bounded parity coverage honestly: it does not prove the full port complete.

Keep aggregate jobs unconditional with `always()` and explicit success checks for
every required dependency. Missing output, cancellation, failure, or an unexpected
skip must not become a green aggregate. GitHub accepts some skipped/neutral job
conclusions, while a workflow omitted by branch/path filters can remain pending;
the aggregate must enforce the stronger internal contract. See GitHub's
[required-check troubleshooting](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks).

Audit event and path coverage for every required context. The Release Please
`paths-ignore` exception is existing release bookkeeping, not a general Go-branch
exemption. The target revision includes Go PR triggers for both guards, but
Sonar push guards still name only `main` and `dev`; a green Go push `sonar` join
can therefore represent a scan that did not run. Same-repository PRs have
a different trust path. Preserve explicit fork/Dependabot limitations; do not
expose secrets to make every event green. Do not require advisory
`fast-feedback`, post-merge finalization, scheduled Scorecard, release publication,
or another branch's release-only checks as if they were Go PR admission gates.

## Cross-cutting security and host boundaries

| Layer touched | Required treatment |
| --- | --- |
| GitHub authorization and persistence | Ruleset administration stays outside untrusted CI, using existing authorized GitHub access with repository administration permission only where needed. Read back native API state; capture prior settings for a scoped reversal. No new database or store is needed. |
| Ruleset API shapes | Use native `target`, `enforcement`, `conditions.ref_name`, `pull_request`, `required_status_checks`, source integration identities, and bypass actor/mode fields. Exact branch match, explicit exclusions, and inherited rules must agree. Do not invent a RAES schema for GitHub settings. |
| Workflow parsing and settings | Native Actions shapes and `workflow_call` input/secret declarations must pass `action_policy_yaml.py` and `_target_contract_invalid`; keep pinned action pins and `persist-credentials: false`. No workflow inventory or parallel settings format. |
| Secret guard and environment bindings | `_SONAR_GUARD` and `_sonar_boundary` in `tooling_artifact_policy_actions.py` recognize the precise reviewed trust condition and named secret mapping. Any deliberate Go-push expansion must reconcile the reusable guard, caller `SONAR_REQUIRED`, policy validator, and negative tests together. Keep explicit permissions and no `secrets: inherit` or workflow-wide secret environment. |
| Host/process exposure | Use existing CLI authentication or an already supplied `GH_TOKEN` environment binding; never a literal token/header in argv, URLs, shell tracing, output, or evidence files. Never access `~/.secrets`. Treat branch/PR data as data, with argument-safe calls and structured JSON/file input, not shell code. |
| Errors and observability | Native API HTTP failures and check conclusions remain authoritative. Authorization failure, malformed response, rate limit, and transport failure are not "unprotected" or success. Sanitize recorded diagnostics; never record credential headers or raw unexpected exceptions. If Python tooling is extended, reuse ADR-116 `raes_contracts.errors` / `operational_logging`, `PolicyFailure`, and existing CLI envelopes. No new exception hierarchy or logging setup. |
| Local repository policy | `tools/check_repo_policy.py`, tooling-action admission, ADR pins, and `.ground-control.yaml` remain applicable. Use the frozen Python 3.14 tooling environment, not the older host interpreter. Requirement UID, if needed, must come from actual issue governance rather than a borrowed identifier. |

Branch settings need no runtime code edits. Keep the RAES auth controller and DTO unchanged.
Keep the SDL parser, semantic validator, secret resolver, runtime store, and error types unchanged.
Adding those dependencies would conflate development governance with runtime policy.

## Evidence boundary, extensibility, and non-goals

Acceptance needs both settings and behavior evidence. Read back the ruleset
and effective rules via `GET /repos/OpenRAE/rae/rules/branches/go-cutover`, including
inherited rules and legacy protection where present. A legacy protection 404
alone does not establish absence of a ruleset. The effective-rules endpoint returns
active rules, as documented in the [GitHub rules API](https://docs.github.com/en/rest/repos/rules).

Use a real PR targeting `go-cutover`. Record its head and test merge SHA.
Record the workflow run, attempt, required check names, and App identities.
Record pending or failed conclusions. Show that the API merge state blocks the normal merge path. Wait for an unknown merge state to settle. Conflicts,
draft state, or missing review alone do not demonstrate check blocking. Do not
attempt a merge or direct push as a probe, forge successful contexts, or mistake
an administrator's ability to bypass for absence of enforcement. Local workflow
tests and JSON fixtures cannot prove GitHub's live behavior. Record timestamps
and rule IDs without secrets; do not claim acceptance until that evidence exists.

The existing Go module matrix is the extension seam: a new module joins it while
external enforcement continues to require stable aggregate contexts. Native
branch conditions are the seam for future integration branches. If a small check helper is needed, validate its repository, branch, and PR inputs.
Use native API responses. Do not create a general ruleset manager or a second check registry.
Do not hard-code per-module required contexts.

Non-goals: implementing the Go port; changing contracts or runtime architecture;
rewriting the verification graph; modifying `main`/`dev` protection or release
policy; adding a second reviewer, auto-merging, or publishing data elsewhere.
This preflight introduces no executable behavior, so mutation testing is not
applicable to this document. Subsequent workflow changes reuse focused incumbent
tests locally; full regression, Go mutation, integration, and fuzz stay in CI.
