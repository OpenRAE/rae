# ADR-122: Merge Queue for the Dev Branch

## Status

accepted

## Date

2026-11-11

## Classification

Classification: FM0
Required artifacts: repository workflow configuration, the branch merge policy declaration, and focused policy tests
Waivers: none

The decision changes how pull requests merge into `dev`.
It changes no RAES behavior.

## Context

Pull requests to `dev` merge one at a time after their required checks pass.
Issue #2026 moves these merges into a GitHub merge queue.
The queue builds a merge group from `dev`, the queued pull requests in front, and the pull request.
It then runs the required checks again on the merge group commit.

GitHub reports a required check on a merge group only when its producer runs on the `merge_group` event.
Before this decision, no workflow had that trigger.
Three required contexts also had producers that cannot report on a merge group:

- `GitGuardian Security Checks` came from the GitGuardian App, which posts on pull request commits only.
- `CodeQL`, `Analyze (actions)`, and `Analyze (python)` came from code scanning default setup, which does not run on merge groups.
- `title-guard` and `body-guard` read the pull request from the event, and a merge group event has no pull request.

## Decision

1. `dev` uses the GitHub merge queue. The queue builds merge groups that contain more than one pull request. `main` does not use a merge queue, and its merges stay manual.
2. `dev` does not require strict status checks, because the queue tests each pull request against the latest `dev`. `main` requires strict status checks.
3. Each producer of a required `dev` context runs on every merge group and does a real check there:
   - `ci.yml` runs the full canonical graph on the merge group commit. It reads the queued pull request from the API to get the requirement branch. The policy base is the parent commit, so the diff-scoped checks see only the queued pull request.
   - SonarCloud has no merge queue support. The `sonar` job runs a pull request analysis and quality gate for the queued pull request against `dev`, on the merge group commit.
   - `codeql.yml` is the advanced CodeQL setup and replaces default setup.
   - `secret-scan.yml` runs ggshield on `pull_request` and `merge_group` events. Its job produces the `GitGuardian Security Checks` context. The GitGuardian App stays installed.
   - `title-guard` and `body-guard` read the current title and body of the queued pull request from the API. They load their checkers from the merge group base.
4. A failed required check on a merge group removes the pull request from the queue, and the pull request does not merge. No required check is removed, set to non-blocking, or replaced by a check that always passes.
5. `implementations/tooling/branch-merge-policy.json` declares, for each protected branch, the merge queue setting, the strict setting, and the producer of each required context. `tools/check_merge_queue_policy.py` fails when:
   - a branch does not require strict status checks and does not use the merge queue;
   - a required context on a merge queue branch has no workflow producer that runs on every merge group;
   - a declared producer workflow or job does not exist.
6. The workflow security policy treats `merge_group` as an untrusted event, because a merge group commit contains unmerged code. A merge group job holds no write permission, except the reviewed CodeQL scan result upload. The reviewed Sonar boundary admits the Sonar token on merge groups, because only a user with write access can queue a pull request. Only the ggshield step of the reviewed scan job receives the GitGuardian API key. That job runs no repository code and reads no repository ggshield configuration.
7. The Ground Control readiness step adds a ready pull request that targets `dev` to the queue. Readiness writes the Phase E handoff, so the pull request does not merge before readiness. Ground Control owns that step (autarchy-ai/Ground-Control#2000).

## Alternatives Considered

- **Keep strict status checks on `dev` without a queue.** Each merge into `dev` makes the other open pull requests out of date, and each update runs the full CI again.
- **Use the GitGuardian App on merge groups.** The App does not report on a merge group commit, so the queue would not merge any pull request.
- **Run SonarCloud as a branch analysis of the merge group ref.** SonarCloud compares a branch analysis with its main branch. That comparison does not measure the queued pull request.
- **Use the merge group base as the policy base.** The diff then contains the pull requests in front of the queued pull request, and the requirement-scoped checks would assess changes from other pull requests.

## Consequences

- Pull requests merge into `dev` without an update after each merge, and each merge group is tested against the latest `dev`.
- The repository settings must agree with the declaration. GitHub settings are not readable with the CI token, so the maintainer applies the declaration to the settings.
- The ggshield job needs the `GITGUARDIAN_API_KEY` secret in the Actions and Dependabot secret stores. A pull request from a fork has no access to the key, so its `GitGuardian Security Checks` context fails.
- A merge group runs the full CI again after the pull request checks, so each merge uses more CI time.
